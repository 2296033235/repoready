from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

SCHEMA_VERSION = "1"

SourceKind = Literal["ci", "readme", "inferred"]
StepStatus = Literal["passed", "failed", "blocked", "skipped"]
BackendName = Literal["docker", "local"]
AttributionCategory = Literal[
    "missing_system_dep",
    "version_conflict",
    "network_required",
    "credential_required",
    "hardware_required",
    "doc_drift",
    "unknown",
]


@dataclass(frozen=True)
class SourceRef:
    kind: SourceKind
    path: str
    line: Optional[int] = None


@dataclass(frozen=True)
class Step:
    id: int
    command: str
    source: SourceRef
    cwd: str = "."


@dataclass
class Attribution:
    category: AttributionCategory
    evidence: list[str] = field(default_factory=list)
    suggestion: str = ""
    generated_by: Literal["rules", "llm"] = "rules"


@dataclass
class StepResult:
    id: int
    command: str
    status: StepStatus
    exit_code: Optional[int]
    duration_ms: int
    source: SourceRef
    stdout_head: str = ""
    stdout_tail: str = ""
    stderr_head: str = ""
    stderr_tail: str = ""
    attribution: Optional[Attribution] = None


@dataclass
class RunRecord:
    schema_version: str
    repo_url: str
    commit: str
    backend: BackendName
    image: Optional[str]
    started_at: str
    finished_at: str
    environment: dict
    steps: list[StepResult] = field(default_factory=list)


def output_text(step: StepResult) -> str:
    """All captured output for a step, used for evidence checks."""
    return "\n".join(
        part
        for part in (
            step.stdout_head,
            step.stdout_tail,
            step.stderr_head,
            step.stderr_tail,
        )
        if part
    )
