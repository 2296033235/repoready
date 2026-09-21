from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Optional, TextIO

MIN_PYTHON = (3, 10)


@dataclass(frozen=True)
class DockerStatus:
    cli_present: bool
    daemon_reachable: bool
    server_version: Optional[str]
    docker_host: Optional[str]
    detail: str
    hint: str


def interpret_docker_output(returncode: int, stdout: str, stderr: str) -> DockerStatus:
    text = (stderr or stdout or "").strip()
    first_line = text.splitlines()[0] if text else "unknown error"

    if returncode == 0:
        return DockerStatus(
            cli_present=True,
            daemon_reachable=True,
            server_version=stdout.strip() or None,
            docker_host=os.environ.get("DOCKER_HOST"),
            detail="ok",
            hint="",
        )

    lowered = text.lower()
    if "permission denied" in lowered:
        hint = (
            "Permission denied: this account may not talk to the Docker engine. "
            "Add it to the docker-users group, then restart Docker Desktop."
        )
    elif (
        "cannot find the file" in lowered
        or "is the docker daemon running" in lowered
    ):
        hint = (
            "The Docker engine is not running. Start Docker Desktop and wait until "
            "it reports 'Engine running'."
        )
    else:
        hint = (
            "Could not reach the Docker engine. Run 'docker info' in your own "
            "terminal to see the full error."
        )

    return DockerStatus(
        cli_present=True,
        daemon_reachable=False,
        server_version=None,
        docker_host=os.environ.get("DOCKER_HOST"),
        detail=first_line,
        hint=hint,
    )


def check_docker(
    which: Callable[[str], Optional[str]] = shutil.which,
    run: Callable[..., object] = subprocess.run,
) -> DockerStatus:
    exe = which("docker")
    if not exe:
        return DockerStatus(
            cli_present=False,
            daemon_reachable=False,
            server_version=None,
            docker_host=os.environ.get("DOCKER_HOST"),
            detail="docker CLI not found on PATH",
            hint=(
                "Docker is optional: repoready falls back to the local backend. "
                "Install Docker Desktop if you want container isolation."
            ),
        )

    try:
        completed = run(
            [exe, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return DockerStatus(
            cli_present=True,
            daemon_reachable=False,
            server_version=None,
            docker_host=os.environ.get("DOCKER_HOST"),
            detail=str(exc),
            hint="'docker info' did not complete. Check Docker Desktop.",
        )

    return interpret_docker_output(
        completed.returncode, completed.stdout or "", completed.stderr or ""
    )


def run_doctor(
    out: TextIO = sys.stdout, docker: Optional[DockerStatus] = None
) -> int:
    info = sys.version_info
    python_ok = (info.major, info.minor) >= MIN_PYTHON

    print("repoready doctor", file=out)
    print("=" * 40, file=out)
    suffix = "ok" if python_ok else "too old, need >= 3.10"
    print(f"Python {info.major}.{info.minor}.{info.micro}  [{suffix}]", file=out)

    status = docker if docker is not None else check_docker()
    if status.cli_present and status.daemon_reachable:
        print(f"docker {status.server_version}  [ok]", file=out)
    elif not status.cli_present:
        print("docker  [not installed - local backend will be used]", file=out)
    else:
        print(f"docker daemon  [unreachable: {status.detail}]", file=out)

    if status.docker_host:
        print(f"DOCKER_HOST = {status.docker_host}", file=out)
    if status.hint:
        print(f"hint: {status.hint}", file=out)

    return 0 if python_ok else 1
