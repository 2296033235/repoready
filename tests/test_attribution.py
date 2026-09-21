import unittest

from repoready.attribution.rules import classify
from repoready.attribution.validate import (
    evidence_supported,
    normalize,
    validate_attribution,
)
from repoready.models import Attribution, SourceRef, StepResult


def make_step(stderr="", stdout="", status="failed", exit_code=1) -> StepResult:
    return StepResult(
        id=1,
        command="make install",
        status=status,
        exit_code=exit_code,
        duration_ms=5,
        source=SourceRef(kind="ci", path="ci.yml", line=1),
        stdout_head=stdout,
        stdout_tail=stdout,
        stderr_head=stderr,
        stderr_tail=stderr,
    )


class NormalizeTest(unittest.TestCase):
    def test_collapses_whitespace_and_lowercases(self):
        self.assertEqual(
            normalize("  ERROR:\tMissing\nPackage "), "error: missing package"
        )


class EvidenceSupportedTest(unittest.TestCase):
    def test_real_line_is_supported(self):
        step = make_step(stderr="ERROR: Could not find a version that satisfies it")
        self.assertTrue(
            evidence_supported(
                ["ERROR: Could not find a version that satisfies it"],
                [step.stderr_head],
            )
        )

    def test_fabricated_line_is_rejected(self):
        step = make_step(stderr="ERROR: Could not find a version")
        self.assertFalse(
            evidence_supported(
                ["ModuleNotFoundError: no module named 'torch'"], [step.stderr_head]
            )
        )

    def test_whitespace_differences_still_match(self):
        step = make_step(stderr="something  failed\nhere")
        self.assertTrue(evidence_supported(["something failed here"], [step.stderr_head]))

    def test_empty_evidence_is_not_supported(self):
        self.assertFalse(evidence_supported([], ["anything"]))


class ValidateAttributionTest(unittest.TestCase):
    def test_fabricated_evidence_downgrades_to_unknown(self):
        step = make_step(stderr="real output line")
        candidate = Attribution(
            category="version_conflict",
            evidence=["this line never appeared"],
            suggestion="pin the version",
            generated_by="llm",
        )
        result = validate_attribution(candidate, step)
        self.assertEqual(result.category, "unknown")
        self.assertEqual(result.evidence, [])
        self.assertEqual(result.generated_by, "llm")

    def test_supported_evidence_is_kept_unchanged(self):
        step = make_step(stderr="real output line")
        candidate = Attribution(
            category="version_conflict",
            evidence=["real output line"],
            suggestion="pin the version",
            generated_by="llm",
        )
        self.assertEqual(validate_attribution(candidate, step), candidate)

    def test_empty_suggestion_downgrades_to_unknown(self):
        step = make_step(stderr="real output line")
        candidate = Attribution(
            category="version_conflict",
            evidence=["real output line"],
            suggestion="   ",
            generated_by="llm",
        )
        self.assertEqual(validate_attribution(candidate, step).category, "unknown")


class ClassifyTest(unittest.TestCase):
    def test_missing_system_dependency(self):
        result = classify(make_step(stderr="gcc: command not found"))
        self.assertEqual(result.category, "missing_system_dep")
        self.assertEqual(result.evidence, ["gcc: command not found"])

    def test_version_conflict(self):
        step = make_step(
            stderr="ERROR: Cannot install a and b because these packages have conflicting dependencies"
        )
        self.assertEqual(classify(step).category, "version_conflict")

    def test_network_required(self):
        self.assertEqual(
            classify(make_step(stderr="Could not resolve host: pypi.org")).category,
            "network_required",
        )

    def test_credential_required(self):
        step = make_step(stderr="fatal: Authentication failed for 'https://github.com/x'")
        self.assertEqual(classify(step).category, "credential_required")

    def test_hardware_required(self):
        step = make_step(stderr="RuntimeError: No CUDA GPUs are available")
        self.assertEqual(classify(step).category, "hardware_required")

    def test_doc_drift_when_referenced_script_is_gone(self):
        step = make_step(stderr="python: can't open file 'scripts/setup.py': [Errno 2]")
        self.assertEqual(classify(step).category, "doc_drift")

    def test_unrecognised_output_falls_back_to_unknown(self):
        step = make_step(stderr="something completely unexpected happened")
        result = classify(step)
        self.assertEqual(result.category, "unknown")
        self.assertEqual(result.evidence, [])

    def test_passing_step_is_not_classified(self):
        self.assertIsNone(classify(make_step(status="passed", exit_code=0)))

    def test_blocked_step_is_classified_too(self):
        step = make_step(stderr="Could not resolve host: example.com", status="blocked", exit_code=None)
        self.assertEqual(classify(step).category, "network_required")


if __name__ == "__main__":
    unittest.main()
