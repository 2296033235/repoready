from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import BinaryIO, Optional

from repoready.models import Step
from repoready.runner.base import ExecOutcome, Limits

_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_POST_KILL_WAIT_S = 2.0


class _JobObjectBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_void_p),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _JobObjectExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobObjectBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _WindowsJob:
    def __init__(self) -> None:
        self.handle: Optional[int] = None
        self.assigned = False
        self.error_code: Optional[int] = None
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateJobObjectW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
        ]
        self._kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        self._kernel32.SetInformationJobObject.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        self._kernel32.SetInformationJobObject.restype = ctypes.c_int
        self._kernel32.AssignProcessToJobObject.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self._kernel32.AssignProcessToJobObject.restype = ctypes.c_int
        self._kernel32.TerminateJobObject.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        self._kernel32.TerminateJobObject.restype = ctypes.c_int
        self._kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self._kernel32.CloseHandle.restype = ctypes.c_int

        handle = self._kernel32.CreateJobObjectW(None, None)
        if not handle:
            self.error_code = ctypes.get_last_error()
            return

        self.handle = handle
        info = _JobObjectExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self._kernel32.SetInformationJobObject(
            self.handle,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            self.error_code = ctypes.get_last_error()
            self.close()

    def assign(self, process: subprocess.Popen) -> bool:
        if self.handle is None:
            return False
        if not self._kernel32.AssignProcessToJobObject(
            self.handle, int(process._handle)
        ):
            self.error_code = ctypes.get_last_error()
            return False
        self.assigned = True
        return True

    def terminate(self) -> bool:
        if self.handle is None or not self.assigned:
            return False
        if not self._kernel32.TerminateJobObject(self.handle, 1):
            self.error_code = ctypes.get_last_error()
            return False
        return True

    def close(self) -> None:
        if self.handle is not None:
            self._kernel32.CloseHandle(self.handle)
            self.handle = None
        self.assigned = False


def as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _read_output(output: BinaryIO) -> str:
    output.seek(0)
    return as_text(output.read())


def _wait_for_process(process: subprocess.Popen, timeout_s: float) -> bool:
    try:
        process.wait(timeout=timeout_s)
        return True
    except subprocess.TimeoutExpired:
        return False


def _terminate_process_tree(
    process: subprocess.Popen, job: Optional[_WindowsJob]
) -> bool:
    if os.name == "nt":
        if job is not None and job.terminate():
            return True

        try:
            completed = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=_POST_KILL_WAIT_S,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        else:
            if completed.returncode == 0:
                return True

        try:
            process.kill()
        except OSError:
            pass
        return False

    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        return True
    except OSError:
        try:
            process.kill()
        except OSError:
            pass
        return False


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
        job = _WindowsJob() if os.name == "nt" else None
        stdout_file: Optional[BinaryIO] = None
        stderr_file: Optional[BinaryIO] = None
        process: Optional[subprocess.Popen] = None
        try:
            stdout_file = tempfile.TemporaryFile()
            stderr_file = tempfile.TemporaryFile()
            try:
                process = subprocess.Popen(
                    step.command,
                    shell=True,
                    cwd=workdir,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    creationflags=(
                        subprocess.CREATE_NEW_PROCESS_GROUP
                        if os.name == "nt"
                        else 0
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

            if job is not None:
                job.assign(process)

            try:
                process.wait(timeout=limits.timeout_s)
            except subprocess.TimeoutExpired:
                terminated = _terminate_process_tree(process, job)
                exited = _wait_for_process(process, _POST_KILL_WAIT_S)
                elapsed = int((time.monotonic() - started) * 1000)
                return ExecOutcome(
                    exit_code=None,
                    duration_ms=elapsed,
                    stdout=_read_output(stdout_file),
                    stderr=_read_output(stderr_file),
                    blocked_reason=(
                        "timeout"
                        if terminated and exited
                        else "timeout_termination_unconfirmed"
                    ),
                )

            elapsed = int((time.monotonic() - started) * 1000)
            return ExecOutcome(
                exit_code=process.returncode,
                duration_ms=elapsed,
                stdout=_read_output(stdout_file),
                stderr=_read_output(stderr_file),
            )
        finally:
            if job is not None:
                job.close()
            if stdout_file is not None:
                stdout_file.close()
            if stderr_file is not None:
                stderr_file.close()

    def cleanup(self) -> None:
        self._root = None
