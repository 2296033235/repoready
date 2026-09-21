import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SMOKE_ASSERTION = ROOT / "scripts" / "assert_smoke_passed.py"


class CiSmokeAssertionTest(unittest.TestCase):
    def run_assertion(self, statuses: list[str]):
        with tempfile.TemporaryDirectory() as tmp:
            run_json = Path(tmp) / "run.json"
            run_json.write_text(
                json.dumps(
                    {
                        "steps": [
                            {"status": status}
                            for status in statuses
                        ]
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.run(
                [sys.executable, str(SMOKE_ASSERTION), str(run_json)],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_smoke_assertion_accepts_a_passed_container_step(self):
        completed = self.run_assertion(["blocked", "passed", "skipped"])

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_smoke_assertion_rejects_all_blocked_steps(self):
        completed = self.run_assertion(["blocked", "blocked"])

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("no step passed", completed.stderr)


if __name__ == "__main__":
    unittest.main()
