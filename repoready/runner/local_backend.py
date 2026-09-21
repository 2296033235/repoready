from __future__ import annotations

import os
import signal
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


def _kill_process_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.CalledProcessError):
            # Signal the new process group before the single-process fallback.
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
            except OSError:
                pass
            process.kill()
        return

    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except OSError:
        process.kill()


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

        if not network:
            return ExecOutcome(
                exit_code=None,
                duration_ms=0,
                stdout="",
                stderr="",
                blocked_reason="network_isolation_unavailable",
            )

        workdir = (self._root / step.cwd).resolve()
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                step.command,
                shell=True,
                cwd=workdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                ),
                start_new_session=os.name != "nt",
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

        try:
            stdout, stderr = process.communicate(timeout=limits.timeout_s)
        except subprocess.TimeoutExpired:
            _kill_process_tree(process)
            stdout, stderr = process.communicate()
            elapsed = int((time.monotonic() - started) * 1000)
            return ExecOutcome(
                exit_code=None,
                duration_ms=elapsed,
                stdout=as_text(stdout),
                stderr=as_text(stderr),
                blocked_reason="timeout",
            )

        elapsed = int((time.monotonic() - started) * 1000)
        return ExecOutcome(
            exit_code=process.returncode,
            duration_ms=elapsed,
            stdout=as_text(stdout),
            stderr=as_text(stderr),
        )

    def cleanup(self) -> None:
        self._root = None
