import json
import os
import shutil
import ssl
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import pytest

from app import monitoring
from app.monitoring import (
    CheckState,
    MonitorConfig,
    MonitorError,
    Probe,
    backup_probe,
    collect,
    disk_probe,
    load_state,
    observe,
    run_once,
    state_lock,
)


class HealthHandler(BaseHTTPRequestHandler):
    status = 200
    body = b'{"status":"ready"}'
    requests: list[str] = []

    def do_GET(self) -> None:
        self.requests.append(self.path)
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        if self.status == 302:
            self.send_header("Location", "/PRIVATE-REDIRECT-TARGET")
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args: Any) -> None:
        pass


@contextmanager
def serve(context: ssl.SSLContext | None = None) -> Iterator[ThreadingHTTPServer]:
    HealthHandler.status, HealthHandler.body, HealthHandler.requests = (
        200,
        b'{"status":"ready"}',
        [],
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
    if context:
        server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def config() -> MonitorConfig:
    return MonitorConfig("https://cck.example.test")


@pytest.mark.parametrize(
    "origin",
    [
        "http://public.example.test",
        "http://localhost.attacker.test",
        "https://user:PRIVATE_PASSWORD@cck.example.test",
        "https://cck.example.test/path",
        "https://cck.example.test?PRIVATE_QUERY",
        "https://cck.example.test?",
        "https://cck.example.test#fragment",
        "https://cck.example.test:0",
        "https://cck.example.test:99999",
        "https://cck.example.test\\other",
        "https://cck.example.test\n",
        "file:///private/file",
    ],
)
def test_rejects_unsafe_or_ambiguous_origins(origin: str) -> None:
    with pytest.raises(MonitorError) as failure:
        MonitorConfig(origin, allow_local_http=True)
    assert str(failure.value) == "MONITOR_CONFIGURATION_INVALID"


def test_http_requires_explicit_loopback_exception() -> None:
    with pytest.raises(MonitorError):
        MonitorConfig("http://localhost:8000")
    assert MonitorConfig("http://[::1]:8000", allow_local_http=True)


def test_real_readiness_rejects_bad_bodies_errors_and_redirects(tmp_path: Path) -> None:
    with serve() as server:
        config = MonitorConfig(f"http://localhost:{server.server_port}", allow_local_http=True)
        state = tmp_path / "monitor.json"
        first = run_once(config, state)
        assert first["healthy"] and first["events"] == []
        assert first["skipped_checks"] == ["backup_freshness", "disk_space", "tls_certificate"]
        assert first["checks"][0]["code"] == "READY"
        for status, body in [
            (503, b"PRIVATE_EXCEPTION_AND_ANSWER"),
            (200, b"PRIVATE_NOT_JSON"),
            (200, b'{"status":"ok"}'),
            (200, b"[]"),
            (200, b"x" * 1025),
            (302, b"PRIVATE_REDIRECT_BODY"),
        ]:
            HealthHandler.status, HealthHandler.body = status, body
            report = run_once(config, state)
            assert not report["healthy"]
            assert "PRIVATE" not in json.dumps(report)
        assert set(HealthHandler.requests) == {"/api/health/ready"}
    # A closed port is a failed probe, without a raw socket error or private URL.
    assert not run_once(config, state)["healthy"]


def test_https_verifies_chain_and_hostname_and_warns_before_expiry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not shutil.which("openssl"):
        pytest.skip("OpenSSL required for the local TLS probe")
    key, certificate = tmp_path / "key.pem", tmp_path / "certificate.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "2",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost",
            "-keyout",
            str(key),
            "-out",
            str(certificate),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, key)
    keylog = tmp_path / "debug-keys.log"
    monkeypatch.setenv("SSLKEYLOGFILE", str(keylog))
    with serve(context) as server:
        config = MonitorConfig(
            f"https://localhost:{server.server_port}",
            ca_file=certificate,
            certificate_warning_days=0,
        )
        checks = collect(config, datetime.now(UTC))
        assert all(check.healthy for check in checks)
        soon = collect(replace(config, certificate_warning_days=3), datetime.now(UTC))
        assert soon[0].healthy and soon[1].code == "TLS_EXPIRING"
        untrusted = collect(replace(config, ca_file=None), datetime.now(UTC))
        assert not untrusted[0].healthy and untrusted[1].code == "TLS_VERIFICATION_FAILED"
        wrong_host = collect(
            replace(config, origin=f"https://127.0.0.1:{server.server_port}"), datetime.now(UTC)
        )
        assert not wrong_host[0].healthy and wrong_host[1].code == "TLS_VERIFICATION_FAILED"
    logged = keylog.read_text() if keylog.exists() else ""
    assert "CLIENT_" not in logged and "SERVER_" not in logged


def test_disk_space_checks_absolute_and_percentage_limits(
    config: MonitorConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    usage = shutil.disk_usage(tmp_path)
    monkeypatch.setattr(monitoring.shutil, "disk_usage", lambda _: type(usage)(1000, 900, 100))
    config = replace(config, disk_path=tmp_path, minimum_free_bytes=50, minimum_free_percent=5)
    assert disk_probe(config).healthy
    assert disk_probe(replace(config, minimum_free_bytes=101)).code == "DISK_LOW"
    assert disk_probe(replace(config, minimum_free_percent=11)).code == "DISK_LOW"


def test_backup_freshness_handles_missing_corrupt_stale_and_future_metadata(
    config: MonitorConfig, tmp_path: Path
) -> None:
    config = replace(config, backup_directory=tmp_path)
    assert backup_probe(config).code == "BACKUP_UNAVAILABLE"
    archive = tmp_path / "synthetic.dump.cms"
    archive.write_bytes(b"synthetic fixture, not a recoverable archive")
    sidecar = archive.with_suffix(".cms.json")
    for age, healthy in [(60, True), (7201, False), (-60, False)]:
        sidecar.write_text(
            json.dumps(
                {
                    "format": "CCK-PGDUMP-CMS-AES256GCM-v1",
                    "created_at": (datetime.now(UTC) - timedelta(seconds=age)).isoformat(),
                }
            )
        )
        assert backup_probe(config).healthy is healthy
    for bad in ["not json PRIVATE", "[]", "{}", '{"format":"CCK-PGDUMP-CMS-AES256GCM-v1"}']:
        sidecar.write_text(bad)
        assert backup_probe(config).code == "BACKUP_UNAVAILABLE"


def test_incident_thresholds_recovery_and_flapping(config: MonitorConfig) -> None:
    states: dict[str, CheckState] = {}
    now = datetime.now(UTC)
    failed, healthy = (
        Probe("readiness", False, "READINESS_HTTP_FAILURE"),
        Probe("readiness", True, "READY"),
    )
    assert observe([failed], states, config, now) == []
    assert (
        observe([healthy], states, config, now) == []
    )  # Isolated transient does not open incident.
    for _ in range(2):
        assert observe([failed], states, config, now) == []
    incident = observe([failed], states, config, now)[0]
    assert incident["event"] == "MONITOR_INCIDENT"
    assert observe([failed], states, config, now) == []
    assert observe([healthy], states, config, now) == []
    assert observe([failed], states, config, now) == []  # A flap resets the recovery streak.
    assert observe([healthy], states, config, now) == []
    recovered = observe([healthy], states, config, now)[0]
    assert recovered["event"] == "MONITOR_RECOVERED"
    assert recovered["incident_id"] == incident["incident_id"]
    assert observe([healthy], states, config, now) == []


def test_persistence_deduplicates_incidents_across_processes_and_configuration_changes_fail_closed(
    config: MonitorConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "monitor.json"
    probes = [Probe("readiness", False, "READINESS_UNREACHABLE")]
    monkeypatch.setattr(monitoring, "collect", lambda *_: probes)
    assert run_once(config, state)["events"] == []
    assert run_once(config, state)["events"] == []
    report = run_once(config, state)
    incident = report["events"][0]
    assert run_once(config, state)["events"] == []
    assert state.stat().st_mode & 0o777 == 0o600
    assert "cck.example.test" not in state.read_text()
    assert str(state) not in json.dumps(report)
    with pytest.raises(MonitorError, match="CONFIGURATION_MISMATCH"):
        run_once(replace(config, origin="https://another.example.test"), state)
    probes[:] = [Probe("readiness", True, "READY")]
    assert not run_once(config, state)["healthy"]  # Two successes are required to close.
    recovered = run_once(config, state)
    assert recovered["healthy"] and recovered["events"][0]["incident_id"] == incident["incident_id"]
    # New failures start a distinct incident after the previous one has recovered.
    probes[:] = [Probe("readiness", False, "READINESS_UNREACHABLE")]
    run_once(config, state)
    run_once(config, state)
    assert run_once(config, state)["events"][0]["incident_id"] != incident["incident_id"]


def test_corrupt_public_symlink_or_concurrent_state_never_resets_counters(
    config: MonitorConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "monitor.json"
    monkeypatch.setattr(monitoring, "collect", lambda *_: [Probe("readiness", True, "READY")])
    run_once(config, state)
    original = state.read_bytes()
    with state_lock(state):
        with pytest.raises(MonitorError, match="ALREADY_RUNNING"):
            run_once(config, state)
    assert state.read_bytes() == original
    state.chmod(0o644)
    with pytest.raises(MonitorError, match="STATE_INVALID"):
        run_once(config, state)
    state.chmod(0o600)
    state.write_text("PRIVATE_CORRUPTED_STATE")
    with pytest.raises(MonitorError, match="STORAGE_FAILURE"):
        run_once(config, state)
    target = tmp_path / "target"
    target.write_bytes(original)
    state.unlink()
    state.symlink_to(target)
    with pytest.raises(MonitorError, match="STORAGE_FAILURE"):
        run_once(config, state)
    assert target.read_bytes() == original


def test_invalid_state_fields_never_appear_in_output(config: MonitorConfig, tmp_path: Path) -> None:
    state = tmp_path / "monitor.json"
    for raw in [
        {"failures": -1, "successes": 0, "incident_id": None, "opened_at": None},
        {"failures": 1, "successes": 0, "incident_id": "PRIVATE_TOKEN", "opened_at": None},
        {"failures": True, "successes": 0, "incident_id": None, "opened_at": None},
    ]:
        state.write_text(
            json.dumps(
                {"version": 1, "configuration_id": config.identity(), "checks": {"readiness": raw}}
            )
        )
        state.chmod(0o600)
        with pytest.raises((ValueError, MonitorError)):
            load_state(state, config.identity())


def test_cli_emits_safe_exit_codes_and_no_private_error_details(tmp_path: Path) -> None:
    state = tmp_path / "monitor.json"
    with serve() as server:
        arguments = [
            os.sys.executable,
            "-m",
            "app.monitoring",
            "--origin",
            f"http://localhost:{server.server_port}",
            "--allow-local-http",
            "--state-file",
            str(state),
        ]
        ready = subprocess.run(arguments, capture_output=True, text=True, check=False)
        assert ready.returncode == 0 and json.loads(ready.stdout)["healthy"]
        HealthHandler.status = 503
        unavailable = subprocess.run(arguments, capture_output=True, text=True, check=False)
        assert unavailable.returncode == 1 and not json.loads(unavailable.stdout)["healthy"]
        state.write_text("PRIVATE_STATE_CONTENT")
        broken = subprocess.run(arguments, capture_output=True, text=True, check=False)
        assert broken.returncode == 2 and not broken.stderr
        assert json.loads(broken.stdout)["error"] == "MONITOR_STATE_OR_STORAGE_FAILURE"
        assert "PRIVATE" not in broken.stdout
