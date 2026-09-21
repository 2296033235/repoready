from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from repoready.models import Step


@dataclass(frozen=True)
class Limits:
    timeout_s: int = 600


@dataclass(frozen=True)
class ExecOutcome:
    exit_code: Optional[int]
    duration_ms: int
    stdout: str
    stderr: str
    blocked_reason: Optional[str] = None


class SandboxBackend(Protocol):
    name: str

    def prepare(self, repo_root: Path) -> None: ...

    def execute(self, step: Step, limits: Limits, network: bool) -> ExecOutcome: ...

    def cleanup(self) -> None: ...
