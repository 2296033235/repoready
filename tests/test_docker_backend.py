import subprocess
import unittest
from pathlib import Path
from unittest import mock

from repoready.doctor import DockerStatus
from repoready.models import SourceRef, Step
from repoready.runner.base import Limits
from repoready.runner.docker_backend import (
    DEFAULT_IMAGE,
    DockerBackend,
    build_docker_command,
)
from repoready.runner.executor import clip


def docker_status(
    reachable: bool,
    detail: str = "ok",
    hint: str = "",
) -> DockerStatus:
    return DockerStatus(
        cli_present=True,
        daemon_reachable=reachable,
        server_version="29.8.0" if reachable else None,
        docker_host=None,
        detail=detail,
        hint=hint,
    )


class FakeCompleted:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


class BuildDockerCommandTest(unittest.TestCase):
    def setUp(self):
        self.step = Step(
            id=1,
            command="pip install -e .",
            source=SourceRef(kind="ci", path="ci.yml", line=1),
        )

    def test_mounts_repository_and_runs_command_through_sh(self):
        argv = build_docker_command(
            Path("/tmp/repo"), self.step, DEFAULT_IMAGE, Limits(), network=True
        )
        self.assertEqual(argv[0], "docker")
        self.assertEqual(argv[1], "run")
        self.assertIn("--rm", argv)
        self.assertTrue(
            any(part.startswith("type=bind,source=") and part.endswith("target=/work") for part in argv)
        )
        self.assertEqual(argv[-3:-1], ["sh", "-lc"])
        self.assertEqual(argv[-1], "pip install -e .")

    def test_workdir_follows_step_cwd(self):
        step = Step(
            id=2,
            command="pytest",
            source=SourceRef(kind="ci", path="ci.yml", line=2),
            cwd="subdir",
        )
        argv = build_docker_command(
            Path("/tmp/repo"), step, DEFAULT_IMAGE, Limits(), network=True
        )
        self.assertEqual(argv[argv.index("--workdir") + 1], "/work/subdir")

    def test_safe_nested_cwd_is_normalised(self):
        step = Step(
            id=2,
            command="pytest",
            source=SourceRef(kind="ci", path="ci.yml", line=2),
            cwd="subdir/../pkg",
        )
        argv = build_docker_command(
            Path("/tmp/repo"), step, DEFAULT_IMAGE, Limits(), network=True
        )
        self.assertEqual(argv[argv.index("--workdir") + 1], "/work/pkg")

    def test_parent_directory_cwd_is_rejected(self):
        step = Step(
            id=2,
            command="pytest",
            source=SourceRef(kind="ci", path="ci.yml", line=2),
            cwd="..",
        )
        with self.assertRaises(ValueError):
            build_docker_command(
                Path("/tmp/repo"), step, DEFAULT_IMAGE, Limits(), network=True
            )

    def test_nested_parent_traversal_cwd_is_rejected(self):
        step = Step(
            id=2,
            command="pytest",
            source=SourceRef(kind="ci", path="ci.yml", line=2),
            cwd="subdir/../../outside",
        )
        with self.assertRaises(ValueError):
            build_docker_command(
                Path("/tmp/repo"), step, DEFAULT_IMAGE, Limits(), network=True
            )

    def test_absolute_cwd_is_rejected(self):
        step = Step(
            id=2,
            command="pytest",
            source=SourceRef(kind="ci", path="ci.yml", line=2),
            cwd="/tmp",
        )
        with self.assertRaises(ValueError):
            build_docker_command(
                Path("/tmp/repo"), step, DEFAULT_IMAGE, Limits(), network=True
            )

    def test_network_can_be_disabled(self):
        argv = build_docker_command(
            Path("/tmp/repo"), self.step, DEFAULT_IMAGE, Limits(), network=False
        )
        self.assertIn("--network", argv)
        self.assertEqual(argv[argv.index("--network") + 1], "none")

    def test_timeout_is_forwarded_to_stop_timeout(self):
        argv = build_docker_command(
            Path("/tmp/repo"), self.step, DEFAULT_IMAGE, Limits(timeout_s=42), network=True
        )
        self.assertEqual(argv[argv.index("--stop-timeout") + 1], "42")

    def test_no_network_flag_is_absent_when_network_enabled(self):
        argv = build_docker_command(
            Path("/tmp/repo"), self.step, DEFAULT_IMAGE, Limits(), network=True
        )
        self.assertNotIn("--network", argv)

    def test_each_container_gets_a_unique_name(self):
        first = build_docker_command(
            Path("/tmp/repo"), self.step, DEFAULT_IMAGE, Limits(), network=True
        )
        second = build_docker_command(
            Path("/tmp/repo"), self.step, DEFAULT_IMAGE, Limits(), network=True
        )
        self.assertIn("--name", first)
        self.assertIn("--name", second)
        self.assertNotEqual(
            first[first.index("--name") + 1],
            second[second.index("--name") + 1],
        )


class DockerBackendExecuteTest(unittest.TestCase):
    def setUp(self):
        self.step = Step(
            id=1,
            command="pytest",
            source=SourceRef(kind="ci", path="ci.yml", line=1),
        )

    def test_unreachable_daemon_blocks_each_step_with_one_preflight(self):
        status = docker_status(
            reachable=False,
            detail="cannot connect to daemon",
            hint="start Docker Desktop",
        )
        with mock.patch(
            "repoready.runner.docker_backend.check_docker",
            return_value=status,
        ) as check:
            with mock.patch("repoready.runner.docker_backend.subprocess.run") as run:
                backend = DockerBackend()
                backend.prepare(Path("/tmp/repo"))
                first = backend.execute(self.step, Limits(), network=True)
                second = backend.execute(self.step, Limits(), network=True)

        self.assertEqual(check.call_count, 1)
        run.assert_not_called()
        self.assertEqual(first.blocked_reason, "cannot connect to daemon")
        self.assertEqual(second.blocked_reason, "cannot connect to daemon")
        self.assertIn("start Docker Desktop", first.stderr)
        self.assertIsNone(first.exit_code)
        self.assertIsNone(second.exit_code)

    def test_container_permission_denied_is_a_normal_failure(self):
        def fake_run(argv, **kwargs):
            kwargs["stdout"].write(b"")
            kwargs["stderr"].write(b"permission denied")
            return FakeCompleted(returncode=1)

        with mock.patch(
            "repoready.runner.docker_backend.check_docker",
            return_value=docker_status(reachable=True),
        ):
            with mock.patch(
                "repoready.runner.docker_backend.subprocess.run",
                side_effect=fake_run,
            ):
                backend = DockerBackend()
                backend.prepare(Path("/tmp/repo"))
                outcome = backend.execute(self.step, Limits(), network=True)

        self.assertEqual(outcome.exit_code, 1)
        self.assertIsNone(outcome.blocked_reason)
        self.assertEqual(outcome.stderr, "permission denied")

    def test_timeout_uses_real_deadline_and_force_removes_container(self):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            if len(calls) == 1:
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            return FakeCompleted(returncode=0)

        with mock.patch(
            "repoready.runner.docker_backend.check_docker",
            return_value=docker_status(reachable=True),
        ):
            with mock.patch(
                "repoready.runner.docker_backend.subprocess.run",
                side_effect=fake_run,
            ):
                backend = DockerBackend()
                backend.prepare(Path("/tmp/repo"))
                limits = Limits(timeout_s=7)
                outcome = backend.execute(self.step, limits, network=True)

        container_name = calls[0][0][calls[0][0].index("--name") + 1]
        self.assertEqual(calls[0][1]["timeout"], 7)
        self.assertEqual(
            calls[1][0],
            ["docker", "rm", "-f", container_name],
        )
        self.assertGreater(calls[1][1]["timeout"], 0)
        self.assertEqual(outcome.blocked_reason, "timeout")
        self.assertIsNone(outcome.exit_code)

    def test_oserror_force_removes_container_before_returning(self):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            if len(calls) == 1:
                raise OSError("docker disappeared")
            return FakeCompleted(returncode=0)

        with mock.patch(
            "repoready.runner.docker_backend.check_docker",
            return_value=docker_status(reachable=True),
        ):
            with mock.patch(
                "repoready.runner.docker_backend.subprocess.run",
                side_effect=fake_run,
            ):
                backend = DockerBackend()
                backend.prepare(Path("/tmp/repo"))
                outcome = backend.execute(self.step, Limits(), network=True)

        container_name = calls[0][0][calls[0][0].index("--name") + 1]
        self.assertEqual(
            calls[1][0],
            ["docker", "rm", "-f", container_name],
        )
        self.assertEqual(outcome.blocked_reason, "docker_unavailable")
        self.assertIsNone(outcome.exit_code)

    def test_large_output_is_streamed_and_bounded(self):
        stdout = b"A" * 100_000 + b"Z" * 100_000
        stderr = b"E" * 100_000 + b"F" * 100_000

        def fake_run(argv, **kwargs):
            kwargs["stdout"].write(stdout)
            kwargs["stderr"].write(stderr)
            return FakeCompleted(returncode=0)

        with mock.patch(
            "repoready.runner.docker_backend.check_docker",
            return_value=docker_status(reachable=True),
        ):
            with mock.patch(
                "repoready.runner.docker_backend.subprocess.run",
                side_effect=fake_run,
            ):
                backend = DockerBackend()
                backend.prepare(Path("/tmp/repo"))
                outcome = backend.execute(self.step, Limits(), network=True)

        stdout_head, stdout_tail = clip(outcome.stdout)
        stderr_head, stderr_tail = clip(outcome.stderr)
        self.assertEqual(stdout_head, "A" * 2000)
        self.assertEqual(stdout_tail, "Z" * 2000)
        self.assertEqual(stderr_head, "E" * 2000)
        self.assertEqual(stderr_tail, "F" * 2000)
        self.assertLess(len(outcome.stdout), 10_000)
        self.assertLess(len(outcome.stderr), 10_000)


if __name__ == "__main__":
    unittest.main()
