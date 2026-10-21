"""Operator-only probes and persistent incident signals. No notifications or exam writes."""

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import socket
import ssl
import stat
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener
from uuid import UUID, uuid4

from app.backup import BackupError, latest_backup_age

CHECK_NAMES = {"readiness", "tls_certificate", "disk_space", "backup_freshness"}


class MonitorError(Exception):
    """Only fixed, safe error codes may be included in command output."""


@dataclass(frozen=True)
class MonitorConfig:
    origin: str
    ca_file: Path | None = None
    disk_path: Path | None = None
    backup_directory: Path | None = None
    allow_local_http: bool = False
    timeout: int = 6
    certificate_warning_days: int = 14
    minimum_free_bytes: int = 5 * 1024**3
    minimum_free_percent: int = 15
    backup_max_age_seconds: int = 7200
    failure_threshold: int = 3
    recovery_threshold: int = 2

    def __post_init__(self) -> None:
        try:
            url = urlsplit(self.origin)
            if (
                not url.hostname
                or url.username is not None
                or url.password is not None
                or url.path not in {"", "/"}
                or url.query
                or url.fragment
                or any(character in self.origin for character in "?#\\")
                or any(character.isspace() for character in self.origin)
                or not 1 <= (url.port if url.port is not None else 443) <= 65535
                or not (
                    url.scheme == "https"
                    or (
                        self.allow_local_http
                        and url.scheme == "http"
                        and url.hostname in {"localhost", "127.0.0.1", "::1"}
                    )
                )
            ):
                raise ValueError
            if not (
                1 <= self.timeout <= 30
                and 0 <= self.certificate_warning_days <= 365
                and self.minimum_free_bytes >= 0
                and 0 <= self.minimum_free_percent <= 100
                and 60 <= self.backup_max_age_seconds <= 604800
                and 1 <= self.failure_threshold <= 100
                and 1 <= self.recovery_threshold <= 100
            ):
                raise ValueError
        except ValueError:
            raise MonitorError("MONITOR_CONFIGURATION_INVALID") from None

    def identity(self) -> str:
        # Bind persisted counters to their target and thresholds; paths/URLs stay private.
        values = {
            key: str(value.absolute() if isinstance(value, Path) else value)
            for key, value in asdict(self).items()
        }
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Probe:
    name: str
    healthy: bool
    code: str
    measurements: dict[str, int | float] = field(default_factory=dict)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def readiness_probe(config: MonitorConfig, context: ssl.SSLContext) -> Probe:
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())
    request = Request(
        config.origin.rstrip("/") + "/api/health/ready",
        headers={"Accept": "application/json", "User-Agent": "CCK-Operational-Monitor/1"},
    )
    try:
        with opener.open(request, timeout=config.timeout) as response:
            body = response.read(1025)
            if response.status != 200 or len(body) > 1024:
                return Probe("readiness", False, "READINESS_RESPONSE_INVALID")
            data = json.loads(body)
            if not isinstance(data, dict) or data.get("status") != "ready":
                return Probe("readiness", False, "READINESS_RESPONSE_INVALID")
    except HTTPError as error:
        error.close()
        return Probe("readiness", False, "READINESS_HTTP_FAILURE", {"http_status": error.code})
    except (URLError, OSError, HTTPException):
        return Probe("readiness", False, "READINESS_UNREACHABLE")
    except (ValueError, UnicodeError):
        return Probe("readiness", False, "READINESS_RESPONSE_INVALID")
    return Probe("readiness", True, "READY")


def certificate_probe(config: MonitorConfig, context: ssl.SSLContext, now: datetime) -> Probe:
    url = urlsplit(config.origin)
    assert url.hostname is not None  # Validated operator configuration.
    try:
        with socket.create_connection((url.hostname, url.port or 443), config.timeout) as tcp:
            with context.wrap_socket(tcp, server_hostname=url.hostname) as connection:
                certificate = connection.getpeercert()
        if not certificate or not isinstance(certificate.get("notAfter"), str):
            raise ValueError
        seconds = ssl.cert_time_to_seconds(str(certificate["notAfter"])) - now.timestamp()
    except ssl.SSLCertVerificationError:
        return Probe("tls_certificate", False, "TLS_VERIFICATION_FAILED")
    except (OSError, ValueError):
        return Probe("tls_certificate", False, "TLS_UNAVAILABLE")
    healthy = seconds > config.certificate_warning_days * 86400
    return Probe(
        "tls_certificate",
        healthy,
        "TLS_VALID" if healthy else "TLS_EXPIRING",
        {"remaining_seconds": max(0, int(seconds))},
    )


def disk_probe(config: MonitorConfig) -> Probe:
    assert config.disk_path is not None
    try:
        usage = shutil.disk_usage(config.disk_path)
        percent = 100 * usage.free / usage.total
    except (OSError, ZeroDivisionError):
        return Probe("disk_space", False, "DISK_UNAVAILABLE")
    healthy = usage.free >= config.minimum_free_bytes and percent >= config.minimum_free_percent
    return Probe(
        "disk_space",
        healthy,
        "DISK_OK" if healthy else "DISK_LOW",
        {"free_bytes": usage.free, "free_percent": round(percent, 2)},
    )


def backup_probe(config: MonitorConfig) -> Probe:
    assert config.backup_directory is not None
    try:
        age = latest_backup_age(config.backup_directory)
    except (BackupError, OSError, ValueError, KeyError, TypeError, AttributeError):
        return Probe("backup_freshness", False, "BACKUP_UNAVAILABLE")
    healthy = 0 <= age <= config.backup_max_age_seconds
    return Probe(
        "backup_freshness",
        healthy,
        "BACKUP_RECENT" if healthy else "BACKUP_STALE_OR_FUTURE",
        {"age_seconds": round(age)},
    )


def collect(config: MonitorConfig, now: datetime) -> list[Probe]:
    try:
        context = ssl.create_default_context(cafile=config.ca_file)
        # An inherited debugging variable must never turn operational probes into TLS key logs.
        context.keylog_filename = None  # type: ignore[assignment]  # CPython accepts None to disable it.
    except (OSError, ssl.SSLError):
        raise MonitorError("MONITOR_CA_CONFIGURATION_INVALID") from None
    probes = [readiness_probe(config, context)]
    if urlsplit(config.origin).scheme == "https":
        probes.append(certificate_probe(config, context, now))
    if config.disk_path is not None:
        probes.append(disk_probe(config))
    if config.backup_directory is not None:
        probes.append(backup_probe(config))
    return probes


@dataclass
class CheckState:
    failures: int = 0
    successes: int = 0
    incident_id: UUID | None = None
    opened_at: datetime | None = None


def observe(
    probes: list[Probe], states: dict[str, CheckState], config: MonitorConfig, now: datetime
) -> list[dict[str, str]]:
    events = []
    for probe in probes:
        state = states.setdefault(probe.name, CheckState())
        if probe.healthy:
            state.failures = 0
            state.successes = min(state.successes + 1, config.recovery_threshold)
            recovered = (
                state.incident_id is not None and state.successes >= config.recovery_threshold
            )
            event = "MONITOR_RECOVERED" if recovered else None
        else:
            state.successes = 0
            state.failures = min(state.failures + 1, config.failure_threshold)
            opened = state.incident_id is None and state.failures >= config.failure_threshold
            event = "MONITOR_INCIDENT" if opened else None
            if opened:
                state.incident_id, state.opened_at = uuid4(), now
        if event:
            assert state.incident_id is not None and state.opened_at is not None
            events.append(
                {
                    "event": event,
                    "check": probe.name,
                    "code": probe.code,
                    "incident_id": str(state.incident_id),
                    "opened_at": state.opened_at.isoformat(),
                    "observed_at": now.isoformat(),
                }
            )
            if event == "MONITOR_RECOVERED":
                state.incident_id, state.opened_at = None, None
    return events


def load_state(path: Path, identity: str) -> dict[str, CheckState]:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return {}
    with os.fdopen(descriptor) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 32768:
            raise MonitorError("MONITOR_STATE_INVALID")
        data = json.load(stream)
    if data.get("version") != 1 or data.get("configuration_id") != identity:
        raise MonitorError("MONITOR_STATE_CONFIGURATION_MISMATCH")
    states = {}
    for name, raw in data["checks"].items():
        if name not in CHECK_NAMES:
            raise MonitorError("MONITOR_STATE_INVALID")
        for key in ("failures", "successes"):
            if type(raw[key]) is not int or not 0 <= raw[key] <= 100:
                raise MonitorError("MONITOR_STATE_INVALID")
        incident = UUID(raw["incident_id"]) if raw["incident_id"] else None
        opened_at = datetime.fromisoformat(raw["opened_at"]) if raw["opened_at"] else None
        if bool(incident) != bool(opened_at) or (opened_at and opened_at.tzinfo is None):
            raise MonitorError("MONITOR_STATE_INVALID")
        states[name] = CheckState(raw["failures"], raw["successes"], incident, opened_at)
    return states


@contextmanager
def state_lock(path: Path) -> Iterator[None]:
    descriptor = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        info = os.fstat(lock.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise MonitorError("MONITOR_STATE_INVALID")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise MonitorError("MONITOR_ALREADY_RUNNING") from None
        yield


def save_state(path: Path, identity: str, states: dict[str, CheckState]) -> None:
    data = {
        "version": 1,
        "configuration_id": identity,
        "checks": {name: asdict(state) for name, state in states.items()},
    }
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, default=str)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run_once(config: MonitorConfig, state_file: Path) -> dict[str, Any]:
    try:
        with state_lock(state_file):
            states = load_state(state_file, config.identity())
            now = datetime.now(UTC)
            probes = collect(config, now)
            events = observe(probes, states, config, now)
            save_state(state_file, config.identity(), states)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise MonitorError("MONITOR_STATE_OR_STORAGE_FAILURE") from None
    enabled = {probe.name for probe in probes}
    active = [
        {"check": name, "incident_id": str(state.incident_id), "opened_at": str(state.opened_at)}
        for name, state in sorted(states.items())
        if state.incident_id
    ]
    return {
        "kind": "CCK_OPERATIONAL_MONITOR",
        "configuration_id": config.identity(),
        "observed_at": now.isoformat(),
        "healthy": all(probe.healthy for probe in probes) and not active,
        "checks": [asdict(probe) for probe in probes],
        "skipped_checks": sorted(CHECK_NAMES - enabled),
        "active_incidents": active,
        "events": events,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only CCK operational monitoring (Linux/WSL)")
    parser.add_argument("--origin", required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--ca-file", type=Path)
    parser.add_argument("--disk-path", type=Path)
    parser.add_argument("--backup-directory", type=Path)
    parser.add_argument("--allow-local-http", action="store_true")
    parser.add_argument("--timeout", type=int, default=6)
    parser.add_argument("--certificate-warning-days", type=int, default=14)
    parser.add_argument("--minimum-free-bytes", type=int, default=5 * 1024**3)
    parser.add_argument("--minimum-free-percent", type=int, default=15)
    parser.add_argument("--backup-max-age-seconds", type=int, default=7200)
    parser.add_argument("--failure-threshold", type=int, default=3)
    parser.add_argument("--recovery-threshold", type=int, default=2)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args()
    options = vars(args).copy()
    state_file, loop, interval = (options.pop(key) for key in ("state_file", "loop", "interval"))
    try:
        if not 10 <= interval <= 3600:
            raise MonitorError("MONITOR_INTERVAL_INVALID")
        config = MonitorConfig(**options)
        while True:
            report = run_once(config, state_file)
            print(json.dumps(report), flush=True)
            if not loop:
                raise SystemExit(0 if report["healthy"] else 1)
            time.sleep(interval)
    except MonitorError as error:
        print(json.dumps({"kind": "CCK_OPERATIONAL_MONITOR", "error": str(error)}), flush=True)
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
