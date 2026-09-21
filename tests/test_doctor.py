import io
import unittest

from repoready.doctor import check_docker, interpret_docker_output, run_doctor


class InterpretDockerOutputTest(unittest.TestCase):
    def test_success_reports_reachable(self):
        status = interpret_docker_output(0, "29.8.0\n", "")
        self.assertTrue(status.daemon_reachable)
        self.assertEqual(status.server_version, "29.8.0")

    def test_permission_denied_gets_targeted_hint(self):
        status = interpret_docker_output(
            1, "", "permission denied while trying to connect to the Docker daemon"
        )
        self.assertFalse(status.daemon_reachable)
        self.assertIn("permission", status.hint.lower())

    def test_missing_daemon_gets_targeted_hint(self):
        status = interpret_docker_output(
            1,
            "",
            "error during connect: The system cannot find the file specified.",
        )
        self.assertFalse(status.daemon_reachable)
        self.assertIn("start docker desktop", status.hint.lower())

    def test_canonical_daemon_down_gets_start_hint(self):
        status = interpret_docker_output(
            1,
            "",
            "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. "
            "Is the docker daemon running?",
        )
        self.assertFalse(status.daemon_reachable)
        self.assertIn("start docker desktop", status.hint.lower())

    def test_unexpected_failure_still_produces_a_hint(self):
        status = interpret_docker_output(1, "", "some unexpected failure")
        self.assertFalse(status.daemon_reachable)
        self.assertTrue(status.hint)


class CheckDockerTest(unittest.TestCase):
    def test_missing_cli_is_reported_without_running_commands(self):
        def explode(*args, **kwargs):
            raise AssertionError("must not run docker when the CLI is absent")

        status = check_docker(which=lambda name: None, run=explode)
        self.assertFalse(status.cli_present)
        self.assertFalse(status.daemon_reachable)

    def test_cli_present_and_daemon_ok(self):
        class FakeCompleted:
            returncode = 0
            stdout = "29.8.0\n"
            stderr = ""

        status = check_docker(
            which=lambda name: "docker", run=lambda *a, **k: FakeCompleted()
        )
        self.assertTrue(status.cli_present)
        self.assertTrue(status.daemon_reachable)


class RunDoctorTest(unittest.TestCase):
    def test_reports_python_and_docker_and_exits_zero(self):
        buffer = io.StringIO()
        code = run_doctor(out=buffer, docker=check_docker(which=lambda name: None))
        self.assertIn("Python", buffer.getvalue())
        self.assertIn("docker", buffer.getvalue().lower())
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
