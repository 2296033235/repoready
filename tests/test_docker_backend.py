import unittest
from pathlib import Path

from repoready.models import SourceRef, Step
from repoready.runner.base import Limits
from repoready.runner.docker_backend import DEFAULT_IMAGE, build_docker_command


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


if __name__ == "__main__":
    unittest.main()
