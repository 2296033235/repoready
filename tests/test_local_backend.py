import sys
import tempfile
import time
import unittest
from pathlib import Path

from repoready.models import SourceRef, Step
from repoready.runner.base import Limits
from repoready.runner.local_backend import LocalBackend


def make_step(command: str) -> Step:
    return Step(id=1, command=command, source=SourceRef(kind="ci", path="x", line=1))


class LocalBackendTest(unittest.TestCase):
    def test_successful_command_reports_zero_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend()
            backend.prepare(Path(tmp))
            outcome = backend.execute(
                make_step(f'"{sys.executable}" -c "print(1)"'), Limits(), network=True
            )
            self.assertEqual(outcome.exit_code, 0)
            self.assertIn("1", outcome.stdout)
            self.assertIsNone(outcome.blocked_reason)

    def test_failing_command_reports_non_zero_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend()
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
            backend = LocalBackend()
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
            backend = LocalBackend()
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
            backend = LocalBackend()
            backend.prepare(Path(tmp))
            started = time.monotonic()
            outcome = backend.execute(
                make_step(f'"{sys.executable}" -c "import time; time.sleep(5)"'),
                Limits(timeout_s=1),
                network=True,
            )
            elapsed = time.monotonic() - started
            self.assertIsNone(outcome.exit_code)
            self.assertEqual(outcome.blocked_reason, "timeout")
            self.assertLess(elapsed, 3.0)

    def test_timeout_terminates_child_that_ignores_sigbreak(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend()
            backend.prepare(Path(tmp))
            code = (
                "import signal, time; "
                "signal.signal(getattr(signal, 'SIGBREAK', signal.SIGTERM), "
                "signal.SIG_IGN); "
                "time.sleep(10)"
            )
            started = time.monotonic()
            outcome = backend.execute(
                make_step(f'"{sys.executable}" -c "{code}"'),
                Limits(timeout_s=1),
                network=True,
            )
            elapsed = time.monotonic() - started
            self.assertIsNone(outcome.exit_code)
            self.assertIn(
                outcome.blocked_reason,
                ("timeout", "timeout_termination_unconfirmed"),
            )
            self.assertLess(elapsed, 3.0)


if __name__ == "__main__":
    unittest.main()
