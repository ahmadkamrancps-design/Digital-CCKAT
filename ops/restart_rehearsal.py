"""Coordinate real service outages with a synthetic browser; never a public API."""

import argparse
import json
import os
import ssl
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


def run_browser_with_restarts(
    root: Path,
    directory: Path,
    env: dict[str, str],
    stop_services: Callable[[], None],
    start_api: Callable[[], None],
    start_worker: Callable[[], None],
) -> None:
    manifest = json.loads((directory / "manifest.json").read_text())
    origin = env["CCK_BASE_URL"]
    url = urlsplit(origin)
    if (
        manifest.get("kind") != "CCK_REHEARSAL_ONLY"
        or manifest.get("origin") != origin
        or url.scheme != "https"
        or url.hostname != "localhost"
        or url.username
        or url.password
        or url.path
        or url.query
        or url.fragment
    ):
        raise ValueError("Restart rehearsal requires an isolated localhost synthetic manifest.")
    control = directory / "restart-control"
    control.mkdir(mode=0o700)
    context = ssl.create_default_context(cafile=str(directory / "secrets/tls_certificate.pem"))
    browser_env = {**env, "CCK_RESTART_CONTROL_DIRECTORY": str(control)}
    with (directory / "browser.log").open("wb") as log:
        browser = subprocess.Popen(
            ["node", "e2e/production-rehearsal.mjs"],
            cwd=root / "frontend",
            env=browser_env,
            stdout=log,
            stderr=log,
        )

        def wait_until(predicate: Callable[[], bool], stage: str, timeout: float = 90) -> None:
            deadline = time.monotonic() + timeout
            while not predicate():
                if browser.poll() is not None:
                    raise RuntimeError(
                        f"Browser stopped during {stage}; inspect private browser.log."
                    )
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Restart rehearsal timed out during {stage}.")
                time.sleep(0.2)

        def status(path: str) -> int:
            try:
                with urlopen(origin + path, context=context, timeout=3) as response:
                    return int(response.status)
            except HTTPError as error:
                return error.code
            except (URLError, OSError):
                return 0

        def marker(name: str) -> None:
            (control / name).touch(mode=0o600, exist_ok=False)

        try:
            wait_until(lambda: (control / "before-restart").exists(), "candidate preparation")
            stop_services()
            wait_until(lambda: status("/api/health") in {502, 503}, "API outage")
            marker("services-stopped")
            wait_until(lambda: (control / "draft-preserved").exists(), "local draft preservation")
            start_api()
            wait_until(lambda: status("/api/health") == 200, "API liveness")
            # Let the configured 30-second worker heartbeat expire naturally. The
            # gateway/API remain alive while readiness reports the stopped worker.
            wait_until(lambda: status("/api/health/ready") == 503, "worker failure detection", 50)
            marker("api-restarted")
            wait_until(lambda: (control / "api-recovery-verified").exists(), "answer recovery")
            start_worker()
            wait_until(lambda: status("/api/health/ready") == 200, "worker recovery")
            marker("worker-restarted")
            if browser.wait(timeout=180) != 0:
                raise RuntimeError(
                    "Browser recovery verification failed; inspect private browser.log."
                )
            (directory / "restart-report.json").write_text(
                json.dumps(
                    {
                        "kind": "LOCAL_SYNTHETIC_RESTART_REHEARSAL",
                        "api_outage": "verified",
                        "worker_readiness_failure": "verified",
                        "worker_readiness_recovery": "verified",
                        "draft_sync_and_deadline": "verified",
                        "relogin_resume": "verified",
                        "production_capacity_certified": False,
                    },
                    indent=2,
                )
                + "\n"
            )
            print(
                "PASS: API/worker restart, readiness signals, draft recovery and re-login",
                flush=True,
            )
        finally:
            if browser.poll() is None:
                browser.terminate()
                try:
                    browser.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    browser.kill()
                    browser.wait()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restart only the disposable CCK Compose rehearsal"
    )
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    root = Path(__file__).resolve().parents[1]
    compose = [
        "docker",
        "compose",
        "-p",
        "cck-rehearsal",
        "--env-file",
        str(directory / "staging.env"),
        "-f",
        str(root / "compose.production.yml"),
    ]

    def command(*arguments: str) -> None:
        subprocess.run([*compose, *arguments], cwd=root, check=True, timeout=90)

    try:
        run_browser_with_restarts(
            root,
            directory,
            dict(os.environ),
            lambda: command("stop", "api", "expiry-worker"),
            lambda: command("up", "-d", "--no-deps", "api"),
            lambda: command("up", "-d", "--no-deps", "expiry-worker"),
        )
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Restart rehearsal failed: {type(error).__name__}: {error}\n")


if __name__ == "__main__":
    main()
