import argparse
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from repoready.models import SCHEMA_VERSION, Attribution, RunRecord, SourceRef, StepResult
from repoready.report.markdown import render_markdown


def record_with(steps) -> RunRecord:
    return RunRecord(
        schema_version=SCHEMA_VERSION,
        repo_url="https://github.com/example/demo",
        commit="abcdef1234567890",
        backend="docker",
        image="python:3.12-slim",
        started_at="2026-09-21T10:00:00+08:00",
        finished_at="2026-09-21T10:00:09+08:00",
        environment={"python": "3.12.8"},
        steps=list(steps),
    )


def step_result(**overrides) -> StepResult:
    base = dict(
        id=1,
        command="pip install -e .",
        status="passed",
        exit_code=0,
        duration_ms=1200,
        source=SourceRef(kind="ci", path=".github/workflows/ci.yml", line=42),
    )
    base.update(overrides)
    return StepResult(**base)


class RenderMarkdownTest(unittest.TestCase):
    def test_header_contains_repo_commit_and_backend(self):
        text = render_markdown(record_with([]))
        self.assertIn("https://github.com/example/demo", text)
        self.assertIn("abcdef1234567890", text)
        self.assertIn("docker", text)

    def test_passing_step_is_listed_with_source_location(self):
        text = render_markdown(record_with([step_result()]))
        self.assertIn("pip install -e .", text)
        self.assertIn(".github/workflows/ci.yml:42", text)
        self.assertIn("passed", text)

    def test_failed_step_shows_category_evidence_and_suggestion(self):
        failed = step_result(
            status="failed",
            exit_code=1,
            stderr_head="ERROR: conflicting dependencies",
            stderr_tail="ERROR: conflicting dependencies",
            attribution=Attribution(
                category="version_conflict",
                evidence=["ERROR: conflicting dependencies"],
                suggestion="Align the pinned versions.",
                generated_by="rules",
            ),
        )
        text = render_markdown(record_with([failed]))
        self.assertIn("version_conflict", text)
        self.assertIn("ERROR: conflicting dependencies", text)
        self.assertIn("Align the pinned versions.", text)

    def test_summary_counts_every_status(self):
        steps = [
            step_result(id=1),
            step_result(id=2, status="failed", exit_code=1),
            step_result(id=3, status="skipped", exit_code=None),
        ]
        text = render_markdown(record_with(steps))
        self.assertIn("1 passed", text)
        self.assertIn("1 failed", text)
        self.assertIn("1 skipped", text)


class CheckCommandTest(unittest.TestCase):
    def test_local_backend_with_no_network_is_a_configuration_error(self):
        from repoready.commands.check import run_check

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            workflow = root / ".github" / "workflows" / "ci.yml"
            workflow.parent.mkdir(parents=True)
            (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
            marker = root / "command-ran"
            workflow.write_text(
                "steps:\n"
                "  - run: python -c \"open('command-ran', 'w').close()\"\n",
                encoding="utf-8",
            )
            out = Path(tmp) / "out"
            args = argparse.Namespace(
                repo=str(root),
                ref=None,
                out=str(out),
                backend="local",
                timeout=600,
                no_network=True,
            )
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                exit_code = run_check(args)

            self.assertEqual(exit_code, 2)
            self.assertIn("Docker", stderr.getvalue())
            self.assertIn("--no-network", stderr.getvalue())
            self.assertFalse(marker.exists())
            self.assertFalse((out / "run.json").exists())
            self.assertFalse((out / "report.md").exists())


if __name__ == "__main__":
    unittest.main()
