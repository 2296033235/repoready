from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional

from repoready.models import Step
from repoready.runner.base import ExecOutcome, Limits


def as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class LocalBackend:
    """Runs steps directly on the host. Weak isolation, zero dependencies."""

    name = "local"

    def __init__(self) -> None:
        self._root: Optional[Path] = None

    def prepare(self, repo_root: Path) -> None:
        self._root = Path(repo_root).resolve()

    def execute(self, step: Step, limits: Limits, network: bool) -> ExecOutcome:
        if self._root is None:
            raise RuntimeError("prepare() must be called before execute()")

        workdir = (self._root / step.cwd).resolve()
        started = time.monotonic()
        try:
            completed = subprocess.run(
                step.command,
                shell=True,
                cwd=workdir,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=limits.timeout_s,
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
                blocked_reason="spawn_failed",
            )

        elapsed = int((time.monotonic() - started) * 1000)
        return ExecOutcome(
            exit_code=completed.returncode,
            duration_ms=elapsed,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )

    def cleanup(self) -> None:
        self._root = None
