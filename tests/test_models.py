import json
import tempfile
import unittest
from pathlib import Path

from repoready.models import (
    SCHEMA_VERSION,
    Attribution,
    RunRecord,
    SourceRef,
    Step,
    StepResult,
    output_text,
)
from repoready.report.json_report import load_run_json, write_run_json


def sample_record() -> RunRecord:
    return RunRecord(
        schema_version=SCHEMA_VERSION,
        repo_url="https://github.com/example/demo",
        commit="a" * 40,
        backend="local",
        image=None,
        started_at="2026-09-21T10:00:00+08:00",
        finished_at="2026-09-21T10:00:05+08:00",
        environment={"python": "3.12.8"},
        steps=[
            StepResult(
                id=1,
                command="pip install -e .",
                status="failed",
                exit_code=1,
                duration_ms=1200,
                source=SourceRef(kind="ci", path=".github/workflows/ci.yml", line=42),
                stderr_head="ERROR: conflicting dependencies",
                stderr_tail="ERROR: conflicting dependencies",
                attribution=Attribution(
                    category="version_conflict",
                    evidence=["ERROR: conflicting dependencies"],
                    suggestion="Relax the pinned version in requirements.txt.",
                    generated_by="rules",
                ),
            )
        ],
    )


class RunRecordSerializationTest(unittest.TestCase):
    def test_round_trip_preserves_every_field(self):
        record = sample_record()
        with tempfile.TemporaryDirectory() as tmp:
            path = write_run_json(record, Path(tmp))
            self.assertEqual(load_run_json(path), record)

    def test_written_file_uses_documented_field_names(self):
        record = sample_record()
        with tempfile.TemporaryDirectory() as tmp:
            path = write_run_json(record, Path(tmp))
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["schema_version"], SCHEMA_VERSION)
            self.assertEqual(data["backend"], "local")
            self.assertEqual(data["steps"][0]["source"]["kind"], "ci")
            self.assertEqual(
                data["steps"][0]["attribution"]["category"], "version_conflict"
            )


class OutputTextTest(unittest.TestCase):
    def test_joins_all_captured_streams(self):
        step = StepResult(
            id=1,
            command="x",
            status="failed",
            exit_code=1,
            duration_ms=1,
            source=SourceRef(kind="readme", path="README.md", line=3),
            stdout_head="out-head",
            stdout_tail="out-tail",
            stderr_head="err-head",
            stderr_tail="err-tail",
        )
        text = output_text(step)
        for fragment in ("out-head", "out-tail", "err-head", "err-tail"):
            self.assertIn(fragment, text)


class StepDefaultsTest(unittest.TestCase):
    def test_step_defaults_to_repository_root(self):
        step = Step(
            id=1,
            command="pytest",
            source=SourceRef(kind="inferred", path="<inferred>"),
        )
        self.assertEqual(step.cwd, ".")
        self.assertIsNone(step.source.line)


if __name__ == "__main__":
    unittest.main()
