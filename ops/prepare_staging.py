"""Create local-only rehearsal secrets/certificates, never overwrite existing files."""

import argparse
import os
import secrets
import subprocess
from pathlib import Path
from urllib.parse import quote


def prepare(directory: Path, https_port: int, http_port: int) -> Path:
    directory = directory.resolve()
    if directory.exists():
        raise ValueError(
            "Use a new empty directory; existing staging secrets are never overwritten."
        )
    directory.mkdir(mode=0o700, parents=True)
    secret_directory = directory / "secrets"
    secret_directory.mkdir(mode=0o700)
    backups = directory / "backups"
    backups.mkdir(mode=0o700)
    uid, gid = os.getuid() or 1000, os.getgid() or 1000
    if os.getuid() == 0:
        os.chown(backups, uid, gid)
    for role in ["bootstrap", "owner", "runtime"]:
        password = secrets.token_urlsafe(36)
        (secret_directory / f"{role}_password").write_text(password + "\n")
        if role != "bootstrap":
            url = (
                f"postgresql+psycopg://cck_{role}:{quote(password, safe='')}@db:5432/cck_rehearsal"
            )
            (secret_directory / f"{role}_database_url").write_text(url + "\n")
            if role == "owner":
                (secret_directory / "restore_database_url").write_text(
                    url.replace("/cck_rehearsal", "/cck_rehearsal_restore") + "\n"
                )
    for purpose in ["tls", "backup"]:
        args = [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:3072",
            "-nodes",
            "-days",
            "2",
            "-subj",
            f"/CN=CCK LOCAL REHEARSAL {purpose}",
            "-keyout",
            str(secret_directory / f"{purpose}_private_key.pem"),
            "-out",
            str(secret_directory / f"{purpose}_certificate.pem"),
        ]
        if purpose == "tls":
            args += [
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
                "-addext",
                "extendedKeyUsage=serverAuth",
            ]
        subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    # Compose file secrets are bind mounts: files must be readable by container UIDs.
    # Their enclosing host directory remains 0700, protecting all host traversal.
    for path in secret_directory.iterdir():
        path.chmod(0o644)
    env = directory / "staging.env"
    env.write_text(
        f"CCK_HOSTNAME=localhost\nCCK_PUBLIC_ORIGIN=https://localhost:{https_port}\n"
        f"CCK_HTTP_PORT={http_port}\nCCK_HTTPS_PORT={https_port}\nCCK_BIND_ADDRESS=127.0.0.1\n"
        f"CCK_SECRET_DIRECTORY={secret_directory}\nCCK_BACKUP_DIRECTORY={backups}\n"
        f"CCK_BACKUP_UID={uid}\nCCK_BACKUP_GID={gid}\nCCK_DATABASE_NAME=cck_rehearsal\n"
        "API_REPLICAS=1\nAPI_WORKERS=2\nCANDIDATE_LOGIN_IP_LIMIT=20000\nGOOGLE_CLIENT_ID=\n"
    )
    env.chmod(0o600)
    return env


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a LOCAL CCK production-stack rehearsal")
    parser.add_argument("--directory", type=Path, default=Path("test-results/production-rehearsal"))
    parser.add_argument("--https-port", type=int, default=8443)
    parser.add_argument("--http-port", type=int, default=8080)
    args = parser.parse_args()
    if not all(1024 <= port <= 65535 for port in [args.https_port, args.http_port]):
        parser.error("Local ports must be between 1024 and 65535.")
    try:
        env = prepare(args.directory, args.https_port, args.http_port)
    except (ValueError, OSError, subprocess.SubprocessError):
        parser.exit(1, "Staging preparation failed. Check the empty directory and OpenSSL.\n")
    print(f"Local rehearsal configuration created: {env}")


if __name__ == "__main__":
    main()
