from __future__ import annotations

from pathlib import Path
from typing import Optional

from repoready.models import Attribution, StepResult, output_text

SUGGESTIONS: dict[str, str] = {
    "missing_system_dep": (
        "Install the missing system package in the execution image, or document it "
        "as a prerequisite."
    ),
    "version_conflict": (
        "Relax or align the pinned versions; the declared constraints cannot be "
        "satisfied together."
    ),
    "network_required": (
        "This step needs network access or an external host. Re-run with network "
        "enabled, or document the requirement."
    ),
    "credential_required": (
        "This step needs credentials or access to a private resource. Supply them "
        "through environment variables and document it."
    ),
    "hardware_required": (
        "This step needs specific hardware such as a GPU. Document the requirement "
        "so contributors know before they start."
    ),
    "doc_drift": (
        "The documented command references a file or target that no longer exists. "
        "The documentation has drifted from the code."
    ),
    "unknown": (
        "Could not classify this failure automatically. Read the raw log for this step."
    ),
}

PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "hardware_required",
        ("no cuda gpus", "cuda is not available", "nvidia-smi", "no gpu"),
    ),
    (
        "credential_required",
        (
            "authentication failed",
            "permission denied (publickey)",
            "invalid api key",
            "401 unauthorized",
            "no credentials",
        ),
    ),
    (
        "network_required",
        (
            "could not resolve host",
            "temporary failure in name resolution",
            "connection timed out",
            "network is unreachable",
        ),
    ),
    (
        "version_conflict",
        (
            "conflicting dependencies",
            "resolutionimpossible",
            "version solving failed",
            "could not find a version that satisfies",
        ),
    ),
    (
        "doc_drift",
        ("can't open file", "unknown command:", "no such file or directory: 'scripts/"),
    ),
    (
        "missing_system_dep",
        (
            "command not found",
            "is not recognized as an internal or external command",
            "fatal error:",
            "no such file or directory",
        ),
    ),
)


def _matching_line(text: str, needle: str) -> Optional[str]:
    for line in text.splitlines():
        if needle in line.lower():
            return line.strip()
    return None


def classify(
    step: StepResult, base_dir: Path | None = None
) -> Optional[Attribution]:
    if step.status == "passed":
        return None

    text = output_text(step, base_dir)
    lowered = text.lower()
    for category, needles in PATTERNS:
        for needle in needles:
            if needle in lowered:
                line = _matching_line(text, needle)
                return Attribution(
                    category=category,  # type: ignore[arg-type]
                    evidence=[line] if line else [],
                    suggestion=SUGGESTIONS[category],
                    generated_by="rules",
                )

    return Attribution(
        category="unknown",
        evidence=[],
        suggestion=SUGGESTIONS["unknown"],
        generated_by="rules",
    )
