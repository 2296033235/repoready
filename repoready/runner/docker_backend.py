from __future__ import annotations

import os
import posixpath
import subprocess
import tempfile
import time
import uuid
from pathlib import Path, PureWindowsPath
from typing import BinaryIO, Optional

from repoready.doctor import DockerStatus, check_docker
from repoready.models import Step
from repoready.runner.base import ExecOutcome, Limits
from repoready.runner.local_backend import as_text

DEFAULT_IMAGE = "python:3.12-slim"
WORKDIR = "/work"
_CAPTURE_READ_BYTES = 8192
_CAPTURE_HEAD_CHARS = 2000
_CAPTURE_TAIL_CHARS = 2000
_CLEANUP_TIMEOUT_S = 10


def _container_workdir(cwd: str) -> str:
    if posixpath.isabs(cwd) or PureWindowsPath(cwd).is_absolute():
        raise ValueError(f"step.cwd must be relative to the repository: {cwd!r}")

    workdir = posixpath.normpath(f"{WORKDIR}/{cwd}")
    if workdir != WORKDIR and not workdir.startswith(f"{WORKDIR}/"):
        raise ValueError(f"step.cwd escapes the repository workdir: {cwd!r}")
    return workdir


def _read_capture(stream: BinaryIO) -> str:
    stream.flush()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    if size <= _CAPTURE_READ_BYTES:
        stream.seek(0)
        return as_text(stream.read())

    stream.seek(0)
    head = as_text(stream.read(_CAPTURE_READ_BYTES))[:_CAPTURE_HEAD_CHARS]
    stream.seek(max(0, size - _CAPTURE_READ_BYTES))
    tail = as_text(stream.read(_CAPTURE_READ_BYTES))[-_CAPTURE_TAIL_CHARS:]
    return f"{head}\0{tail}"


def _force_remove_container(container_name: str) -> None:
    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=_CLEANUP_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _docker_unreachable_outcome(status: DockerStatus) -> ExecOutcome:
    detail = status.detail or "docker daemon is unreachable"
    stderr = detail if not status.hint else f"{detail}\n{status.hint}"
    return ExecOutcome(
        exit_code=None,
        duration_ms=0,
        stdout="",
        stderr=stderr,
        blocked_reason=detail,
    )


def build_docker_command(
    repo_root: Path,
    step: Step,
    image: str,
    limits: Limits,
    network: bool,
) -> list[str]:
    workdir = _container_workdir(step.cwd)
    container_name = f"repoready-{uuid.uuid4().hex}"
    argv = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--stop-timeout",
        str(limits.timeout_s),
        "--cpus",
        "2",
        "--memory",
        "2048m",
        "--mount",
        f"type=bind,source={Path(repo_root).resolve()},target={WORKDIR}",
        "--workdir",
        workdir,
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
        self._docker_status: Optional[DockerStatus] = None

    def prepare(self, repo_root: Path) -> None:
        self._root = Path(repo_root).resolve()
        self._docker_status = check_docker()

    def execute(self, step: Step, limits: Limits, network: bool) -> ExecOutcome:
        if self._root is None or self._docker_status is None:
            raise RuntimeError("prepare() must be called before execute()")
        if not self._docker_status.daemon_reachable:
            return _docker_unreachable_outcome(self._docker_status)

        argv = build_docker_command(self._root, step, self.image, limits, network)
        container_name = argv[argv.index("--name") + 1]
        started = time.monotonic()
        stdout_file: Optional[BinaryIO] = None
        stderr_file: Optional[BinaryIO] = None
        try:
            stdout_file = tempfile.TemporaryFile()
            stderr_file = tempfile.TemporaryFile()
            completed = subprocess.run(
                argv,
                stdout=stdout_file,
                stderr=stderr_file,
                timeout=limits.timeout_s,
                check=False,
            )
            stdout = _read_capture(stdout_file)
            stderr = _read_capture(stderr_file)
        except subprocess.TimeoutExpired:
            _force_remove_container(container_name)
            elapsed = int((time.monotonic() - started) * 1000)
            return ExecOutcome(
                exit_code=None,
                duration_ms=elapsed,
                stdout=_read_capture(stdout_file) if stdout_file else "",
                stderr=_read_capture(stderr_file) if stderr_file else "",
                blocked_reason="timeout",
            )
        except OSError as exc:
            _force_remove_container(container_name)
            elapsed = int((time.monotonic() - started) * 1000)
            return ExecOutcome(
                exit_code=None,
                duration_ms=elapsed,
                stdout=_read_capture(stdout_file) if stdout_file else "",
                stderr=_read_capture(stderr_file) if stderr_file else str(exc),
                blocked_reason="docker_unavailable",
            )
        except BaseException:
            _force_remove_container(container_name)
            raise
        finally:
            if stdout_file is not None:
                stdout_file.close()
            if stderr_file is not None:
                stderr_file.close()

        elapsed = int((time.monotonic() - started) * 1000)
        return ExecOutcome(
            exit_code=completed.returncode,
            duration_ms=elapsed,
            stdout=stdout,
            stderr=stderr,
        )

    def cleanup(self) -> None:
        self._root = None
        self._docker_status = None
