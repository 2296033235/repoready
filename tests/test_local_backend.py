import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from repoready.models import SourceRef, Step
from repoready.runner.base import Limits
from repoready.runner.local_backend import LocalBackend

TIMEOUT_REASON = (
    "timeout_termination_unconfirmed" if os.name == "nt" else "timeout"
)


def make_step(command: str) -> Step:
    return Step(id=1, command=command, source=SourceRef(kind="ci", path="x", line=1))


class LocalBackendTest(unittest.TestCase):
    def test_environment_is_scrubbed_and_uses_an_independent_virtualenv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backend = LocalBackend(venv=True)
            backend.prepare(root)
            previous = os.environ.get("REPOREADY_TEST_SECRET")
            os.environ["REPOREADY_TEST_SECRET"] = "must-not-leak"
            try:
                command = (
                    'python -c "'
                    "import os, sys; "
                    'print(os.environ.get(\'REPOREADY_TEST_SECRET\', \'scrubbed\')); '
                    "print(sys.prefix)\""
                )
                outcome = backend.execute(make_step(command), Limits(), network=True)
            finally:
                if previous is None:
                    os.environ.pop("REPOREADY_TEST_SECRET", None)
                else:
                    os.environ["REPOREADY_TEST_SECRET"] = previous
                backend.cleanup()

            self.assertEqual(outcome.exit_code, 0)
            self.assertIn("scrubbed", outcome.stdout)
            self.assertNotIn("must-not-leak", outcome.stdout)
            self.assertIn("repoready-venv", outcome.stdout)

    def test_successful_command_reports_zero_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(venv=False)
            backend.prepare(Path(tmp))
            outcome = backend.execute(
                make_step(f'"{sys.executable}" -c "print(1)"'), Limits(), network=True
            )
            self.assertEqual(outcome.exit_code, 0)
            self.assertIn("1", outcome.stdout)
            self.assertIsNone(outcome.blocked_reason)

    def test_failing_command_reports_non_zero_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(venv=False)
            backend.prepare(Path(tmp))
            outcome = backend.execute(
                make_step(f'"{sys.executable}" -c "import sys; sys.exit(3)"'),
                Limits(),
                network=True,
            )
            self.assertEqual(outcome.exit_code, 3)
            self.assertIsNone(outcome.blocked_reason)

    def test_command_runs_inside_the_repository_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "marker.txt").write_text("here", encoding="utf-8")
            backend = LocalBackend(venv=False)
            backend.prepare(root)
            code = (
                "import os; print('FOUND' if os.path.exists('marker.txt') else 'MISSING')"
            )
            outcome = backend.execute(
                make_step(f'"{sys.executable}" -c "{code}"'), Limits(), network=True
            )
            self.assertIn("FOUND", outcome.stdout)

    def test_network_false_blocks_before_command_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backend = LocalBackend(venv=False)
            backend.prepare(root)
            marker = root / "network-ran.txt"
            code = (
                "from pathlib import Path; "
                "Path('network-ran.txt').write_text('ran')"
            )
            outcome = backend.execute(
                make_step(f'"{sys.executable}" -c "{code}"'),
                Limits(),
                network=False,
            )
            self.assertIsNone(outcome.exit_code)
            self.assertEqual(
                outcome.blocked_reason, "network_isolation_unavailable"
            )
            self.assertFalse(marker.exists())

    def test_timeout_is_reported_as_blocked_not_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(venv=False)
            backend.prepare(Path(tmp))
            started = time.monotonic()
            outcome = backend.execute(
                make_step(f'"{sys.executable}" -c "import time; time.sleep(5)"'),
                Limits(timeout_s=1),
                network=True,
            )
            elapsed = time.monotonic() - started
            self.assertIsNone(outcome.exit_code)
            self.assertEqual(outcome.blocked_reason, TIMEOUT_REASON)
            self.assertLess(elapsed, 3.0)

    def test_timeout_terminates_child_that_ignores_sigbreak(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "heartbeat.py").write_text(
                "import signal\n"
                "import time\n"
                "from pathlib import Path\n"
                "\n"
                'signal.signal(getattr(signal, "SIGBREAK", signal.SIGTERM), '
                "signal.SIG_IGN)\n"
                'marker = Path("heartbeat.txt")\n'
                "end = time.monotonic() + 10\n"
                "while time.monotonic() < end:\n"
                '    with marker.open("a", encoding="utf-8") as output:\n'
                '        output.write("x\\n")\n'
                "    time.sleep(0.05)\n",
                encoding="utf-8",
            )
            backend = LocalBackend(venv=False)
            backend.prepare(root)
            started = time.monotonic()
            outcome = backend.execute(
                make_step(f'"{sys.executable}" "heartbeat.py"'),
                Limits(timeout_s=1),
                network=True,
            )
            elapsed = time.monotonic() - started
            marker = root / "heartbeat.txt"
            self.assertTrue(marker.exists())
            size_at_return = marker.stat().st_size
            time.sleep(0.5)
            self.assertIsNone(outcome.exit_code)
            self.assertEqual(outcome.blocked_reason, TIMEOUT_REASON)
            self.assertLess(elapsed, 3.0)
            self.assertGreater(size_at_return, 0)
            self.assertEqual(marker.stat().st_size, size_at_return)


if __name__ == "__main__":
    unittest.main()
