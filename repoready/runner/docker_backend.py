from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional

from repoready.models import Step
from repoready.runner.base import ExecOutcome, Limits
from repoready.runner.local_backend import as_text

DEFAULT_IMAGE = "python:3.12-slim"
WORKDIR = "/work"


def build_docker_command(
    repo_root: Path,
    step: Step,
    image: str,
    limits: Limits,
    network: bool,
) -> list[str]:
    argv = [
        "docker",
        "run",
        "--rm",
        "--stop-timeout",
        str(limits.timeout_s),
        "--cpus",
        "2",
        "--memory",
        "2048m",
        "--mount",
        f"type=bind,source={Path(repo_root).resolve()},target={WORKDIR}",
        "--workdir",
        f"{WORKDIR}/{step.cwd}".rstrip("/"),
    ]
    if not network:
        argv += ["--network", "none"]
    argv += [image, "sh", "-lc", step.command]
    return argv


class DockerBackend:
    """Runs each step in a throwaway container. Preferred backend."""

    name = "docker"

    def __init__(self, image: str = DEFAULT_IMAGE) -> None:
        self.image = image
        self._root: Optional[Path] = None

    def prepare(self, repo_root: Path) -> None:
        self._root = Path(repo_root).resolve()

    def execute(self, step: Step, limits: Limits, network: bool) -> ExecOutcome:
        if self._root is None:
            raise RuntimeError("prepare() must be called before execute()")

        argv = build_docker_command(self._root, step, self.image, limits, network)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=limits.timeout_s + 60,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            return ExecOutcome(
                exit_code=None,
                duration_ms=elapsed,
                stdout=as_text(exc.stdout),
                stderr=as_text(exc.stderr),
                blocked_reason="timeout",
            )
        except OSError as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            return ExecOutcome(
                exit_code=None,
                duration_ms=elapsed,
                stdout="",
                stderr=str(exc),
                blocked_reason="docker_unavailable",
            )

        elapsed = int((time.monotonic() - started) * 1000)
        stderr = completed.stderr or ""
        blocked_reason = None
        if completed.returncode != 0 and "permission denied" in stderr.lower():
            blocked_reason = "docker_permission_denied"

        return ExecOutcome(
            exit_code=None if blocked_reason else completed.returncode,
            duration_ms=elapsed,
            stdout=completed.stdout or "",
            stderr=stderr,
            blocked_reason=blocked_reason,
        )

    def cleanup(self) -> None:
        self._root = None
