from __future__ import annotations

from repoready.models import Attribution, StepResult, output_text


def normalize(text: str) -> str:
    return " ".join(text.split()).lower()


def evidence_supported(evidence: list[str], outputs: list[str]) -> bool:
    usable = [item for item in evidence if item.strip()]
    if not usable:
        return False
    haystack = normalize("\n".join(outputs))
    return all(normalize(item) in haystack for item in usable)


def validate_attribution(candidate: Attribution, step: StepResult) -> Attribution:
    """Downgrade to unknown unless every quoted line really appears in the output."""
    if not evidence_supported(list(candidate.evidence), [output_text(step)]):
        return Attribution(
            category="unknown",
            evidence=[],
            suggestion=(
                "Attribution could not be supported by the captured output; "
                "read the raw log for this step."
            ),
            generated_by=candidate.generated_by,
        )
    if not candidate.suggestion.strip():
        return Attribution(
            category="unknown",
            evidence=[],
            suggestion="Attribution came with no actionable suggestion.",
            generated_by=candidate.generated_by,
        )
    return candidate
