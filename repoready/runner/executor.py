from __future__ import annotations

from pathlib import Path

from repoready.models import Step, StepResult
from repoready.runner.base import ExecOutcome, Limits, SandboxBackend

HEAD_CHARS = 2000
TAIL_CHARS = 2000
HALTING_STATUSES = {"failed", "blocked"}


def clip(text: str) -> tuple[str, str]:
    if len(text) <= HEAD_CHARS + TAIL_CHARS:
        return text, text
    return text[:HEAD_CHARS], text[-TAIL_CHARS:]


def _to_result(step: Step, outcome: ExecOutcome) -> StepResult:
    if outcome.blocked_reason is not None:
        status = "blocked"
    elif outcome.exit_code == 0:
        status = "passed"
    else:
        status = "failed"

    stdout_head, stdout_tail = clip(outcome.stdout)
    stderr_head, stderr_tail = clip(outcome.stderr)

    return StepResult(
        id=step.id,
        command=step.command,
        status=status,
        exit_code=outcome.exit_code,
        duration_ms=outcome.duration_ms,
        source=step.source,
        stdout_head=stdout_head,
        stdout_tail=stdout_tail,
        stderr_head=stderr_head,
        stderr_tail=stderr_tail,
    )


def _skipped_result(step: Step) -> StepResult:
    return StepResult(
        id=step.id,
        command=step.command,
        status="skipped",
        exit_code=None,
        duration_ms=0,
        source=step.source,
    )


def run_steps(
    steps: list[Step],
    backend: SandboxBackend,
    limits: Limits,
    network: bool,
    repo_root: Path = Path("."),
) -> list[StepResult]:
    """Execute steps in order; the first failure skips everything after it.

    Onboarding instructions are a linear sequence: step N+1 assumes step N
    succeeded. Continuing after a failure would only produce noise.
    """
    backend.prepare(repo_root)
    results: list[StepResult] = []
    halted = False
    try:
        for step in steps:
            if halted:
                results.append(_skipped_result(step))
                continue
            outcome = backend.execute(step, limits, network)
            result = _to_result(step, outcome)
            results.append(result)
            if result.status in HALTING_STATUSES:
                halted = True
    finally:
        backend.cleanup()
    return results
