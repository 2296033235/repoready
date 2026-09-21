from __future__ import annotations

from repoready.models import RunRecord, StepResult

LABELS = {
    "passed": "PASS",
    "failed": "FAIL",
    "blocked": "BLOCK",
    "skipped": "SKIP",
}
STATUS_ORDER = ("passed", "failed", "blocked", "skipped")


def _backtick_run(text: str) -> int:
    longest = 0
    current = 0
    for character in text:
        if character == "`":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _code_span(text: str) -> str:
    value = str(text).replace("\r\n", "\n").replace("\n", " ")
    delimiter = "`" * (max(1, _backtick_run(value)) + 1)
    if not value:
        return f"{delimiter}{delimiter}"
    if value.startswith(("`", " ")) or value.endswith(("`", " ")):
        value = f" {value} "
    return f"{delimiter}{value}{delimiter}"


def _fence(text: str) -> str:
    return "`" * max(3, _backtick_run(text) + 1)


def _source_label(step: StepResult) -> str:
    if step.source.line is None:
        return step.source.path
    return f"{step.source.path}:{step.source.line}"


def _summary(record: RunRecord) -> str:
    counts = {name: 0 for name in STATUS_ORDER}
    for step in record.steps:
        counts[step.status] = counts.get(step.status, 0) + 1
    return ", ".join(f"{counts[name]} {name}" for name in STATUS_ORDER)


def render_markdown(record: RunRecord) -> str:
    lines: list[str] = []
    lines.append(f"# Onboarding verification: {record.repo_url}")
    lines.append("")
    lines.append(f"- commit: {_code_span(record.commit)}")
    lines.append(f"- backend: {_code_span(record.backend)}")
    if record.image:
        lines.append(f"- image: {_code_span(record.image)}")
    if record.image_digest:
        lines.append(f"- image digest: {_code_span(record.image_digest)}")
    lines.append(f"- started: {record.started_at}")
    lines.append(f"- finished: {record.finished_at}")
    lines.append(f"- summary: {_summary(record)}")
    lines.append("")
    lines.append("## Steps")
    lines.append("")

    for step in record.steps:
        label = LABELS.get(step.status, step.status.upper())
        lines.append(f"### {step.id}. [{label}] {_code_span(step.command)}")
        lines.append("")
        lines.append(
            f"- declared in: {_code_span(_source_label(step))} ({step.source.kind})"
        )
        lines.append(f"- exit code: {step.exit_code}")
        lines.append(f"- duration: {step.duration_ms} ms")
        if step.attribution is not None:
            lines.append(
                f"- category: {_code_span(step.attribution.category)}"
            )
            lines.append(f"- suggestion: {step.attribution.suggestion}")
            for item in step.attribution.evidence:
                lines.append(f"- evidence: {_code_span(item)}")
        output = (step.stderr_tail or step.stdout_tail).strip()
        if output:
            lines.append("")
            fence = _fence(output)
            lines.append(f"{fence}text")
            lines.append(output)
            lines.append(fence)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
