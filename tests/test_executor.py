import unittest
from pathlib import Path

from repoready.models import SourceRef, Step
from repoready.runner.base import ExecOutcome, Limits
from repoready.runner.executor import clip, run_steps


def make_step(number: int, command: str) -> Step:
    return Step(
        id=number,
        command=command,
        source=SourceRef(kind="ci", path="ci.yml", line=number),
    )


def outcome(exit_code, stdout="", stderr="", blocked=None):
    return ExecOutcome(
        exit_code=exit_code,
        duration_ms=10,
        stdout=stdout,
        stderr=stderr,
        blocked_reason=blocked,
    )


class FakeBackend:
    name = "fake"

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.executed = []

    def prepare(self, repo_root):
        self.repo_root = repo_root

    def execute(self, step, limits, network):
        self.executed.append(step.command)
        return self._outcomes.pop(0)

    def cleanup(self):
        self.cleaned = True


class ClipTest(unittest.TestCase):
    def test_short_text_is_kept_in_full_at_both_ends(self):
        head, tail = clip("hello")
        self.assertEqual(head, "hello")
        self.assertEqual(tail, "hello")

    def test_long_text_keeps_head_and_tail(self):
        text = "A" * 5000 + "B" * 5000
        head, tail = clip(text)
        self.assertTrue(head.startswith("A"))
        self.assertTrue(tail.endswith("B"))
        self.assertLess(len(head), len(text))


class RunStepsTest(unittest.TestCase):
    def test_all_passing_steps_are_recorded(self):
        backend = FakeBackend([outcome(0, "ok"), outcome(0, "ok")])
        results = run_steps(
            [make_step(1, "a"), make_step(2, "b")], backend, Limits(), network=True
        )
        self.assertEqual([r.status for r in results], ["passed", "passed"])
        self.assertEqual(backend.executed, ["a", "b"])
        self.assertTrue(backend.cleaned)

    def test_first_failure_marks_the_rest_as_skipped(self):
        backend = FakeBackend([outcome(1, stderr="boom")])
        results = run_steps(
            [make_step(1, "a"), make_step(2, "b"), make_step(3, "c")],
            backend,
            Limits(),
            network=True,
        )
        self.assertEqual([r.status for r in results], ["failed", "skipped", "skipped"])
        self.assertEqual(backend.executed, ["a"])
        self.assertIsNone(results[1].exit_code)

    def test_blocked_step_also_skips_the_rest(self):
        backend = FakeBackend([outcome(None, blocked="timeout")])
        results = run_steps(
            [make_step(1, "a"), make_step(2, "b")], backend, Limits(), network=True
        )
        self.assertEqual([r.status for r in results], ["blocked", "skipped"])

    def test_results_carry_command_source_and_exit_code(self):
        backend = FakeBackend([outcome(0)])
        results = run_steps([make_step(1, "a")], backend, Limits(), network=True)
        self.assertEqual(results[0].command, "a")
        self.assertEqual(results[0].source.path, "ci.yml")
        self.assertEqual(results[0].exit_code, 0)

    def test_repo_root_is_forwarded_to_the_backend(self):
        backend = FakeBackend([outcome(0)])
        run_steps(
            [make_step(1, "a")], backend, Limits(), network=True, repo_root=Path("/tmp/x")
        )
        self.assertEqual(backend.repo_root, Path("/tmp/x"))


if __name__ == "__main__":
    unittest.main()
