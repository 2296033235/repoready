import argparse
import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from repoready.commands.check import materialize, run_check
from repoready.doctor import DockerStatus
from repoready.report.json_report import load_run_json


def docker_status(reachable: bool) -> DockerStatus:
    return DockerStatus(
        cli_present=True,
        daemon_reachable=reachable,
        server_version="29.8.0" if reachable else None,
        docker_host=None,
        detail="ok" if reachable else "cannot connect to daemon",
        hint="" if reachable else "start Docker Desktop",
    )


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def init_repo(root: Path) -> None:
    root.mkdir(parents=True)
    git(root, "init", "--quiet")
    git(root, "config", "user.email", "tests@example.com")
    git(root, "config", "user.name", "RepoReady Tests")


def commit_file(root: Path, name: str, body: str, message: str) -> str:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    git(root, "add", name)
    git(root, "commit", "--quiet", "-m", message)
    return git(root, "rev-parse", "HEAD")


class BackendSelectionTest(unittest.TestCase):
    def test_auto_backend_does_not_fall_back_to_local_when_docker_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            workflow = root / ".github" / "workflows" / "ci.yml"
            workflow.parent.mkdir(parents=True)
            marker = root / "command-ran"
            workflow.write_text(
                "steps:\n"
                "  - run: python -c \"open('command-ran', 'w').close()\"\n",
                encoding="utf-8",
            )
            args = argparse.Namespace(
                repo=str(root),
                ref=None,
                out=str(Path(tmp) / "out"),
                backend=None,
                timeout=600,
                no_network=False,
                allow_local_network=False,
            )
            stderr = io.StringIO()

            with mock.patch(
                "repoready.commands.check.check_docker",
                return_value=docker_status(reachable=False),
            ):
                with mock.patch(
                    "repoready.commands.check.materialize",
                    return_value=(root, "a" * 40),
                ):
                    with contextlib.redirect_stderr(stderr):
                        exit_code = run_check(args)

            self.assertEqual(exit_code, 2)
            self.assertFalse(marker.exists())
            self.assertIn("explicit", stderr.getvalue().lower())


class MaterializeTest(unittest.TestCase):
    def test_local_checkout_is_clean_and_ref_is_honoured(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source"
            init_repo(source)
            first = commit_file(source, "version.txt", "one\n", "first")
            second = commit_file(source, "version.txt", "two\n", "second")
            (source / "dirty.txt").write_text("dirty\n", encoding="utf-8")

            checkout, commit = materialize(str(source), first, base / "work")

            self.assertEqual(commit, first)
            self.assertEqual((checkout / "version.txt").read_text(encoding="utf-8"), "one\n")
            self.assertFalse((checkout / "dirty.txt").exists())
            self.assertNotEqual(commit, second)

    def test_local_path_must_be_a_git_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source"
            source.mkdir()
            (source / "README.md").write_text("not a checkout\n", encoding="utf-8")

            with self.assertRaises(SystemExit):
                materialize(str(source), None, base / "work")

    def test_scp_style_remote_is_passed_to_git_clone(self):
        with tempfile.TemporaryDirectory() as tmp:
            clone = mock.Mock(returncode=0, stdout="", stderr="")
            head = mock.Mock(returncode=0, stdout="b" * 40 + "\n", stderr="")
            with mock.patch(
                "repoready.commands.check.subprocess.run",
                side_effect=[clone, head],
            ) as run:
                _, commit = materialize(
                    "git@github.com:example/demo.git",
                    None,
                    Path(tmp) / "work",
                )

            self.assertEqual(commit, "b" * 40)
            self.assertEqual(
                run.call_args_list[0].args[0][:4],
                ["git", "clone", "--quiet", "git@github.com:example/demo.git"],
            )


class LocalOptInTest(unittest.TestCase):
    def test_explicit_local_without_network_opt_in_warns_and_does_not_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source"
            init_repo(source)
            workflow = source / ".github" / "workflows" / "ci.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text(
                "steps:\n"
                "  - run: python -c \"open('command-ran', 'w').close()\"\n",
                encoding="utf-8",
            )
            commit_file(
                source,
                ".github/workflows/ci.yml",
                workflow.read_text(encoding="utf-8"),
                "ci",
            )
            args = argparse.Namespace(
                repo=str(source),
                ref=None,
                out=str(base / "out"),
                backend="local",
                timeout=600,
                no_network=False,
                allow_local_network=False,
            )
            stderr = io.StringIO()
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                with contextlib.redirect_stderr(stderr):
                    exit_code = run_check(args)

            self.assertEqual(exit_code, 0)
            self.assertFalse((source / "command-ran").exists())
            self.assertIn("warning", stderr.getvalue().lower())
            self.assertIn("network", stderr.getvalue().lower())
            record = load_run_json(Path(args.out) / "run.json")
            self.assertIn("os", record.environment)
            self.assertIn("python", record.environment)
            self.assertIsNone(record.image_digest)

    def test_project_failure_is_recorded_but_check_still_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source"
            init_repo(source)
            workflow = source / ".github" / "workflows" / "ci.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text(
                "steps:\n"
                "  - run: python -c \"import sys; sys.exit(3)\"\n",
                encoding="utf-8",
            )
            commit_file(
                source,
                ".github/workflows/ci.yml",
                workflow.read_text(encoding="utf-8"),
                "failing ci",
            )
            args = argparse.Namespace(
                repo=str(source),
                ref=None,
                out=str(base / "out"),
                backend="local",
                timeout=600,
                no_network=False,
                allow_local_network=True,
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                with contextlib.redirect_stderr(stderr):
                    exit_code = run_check(args)

            self.assertEqual(exit_code, 0)
            record = load_run_json(Path(args.out) / "run.json")
            self.assertEqual(record.steps[0].status, "failed")
            self.assertEqual(record.steps[0].exit_code, 3)
            self.assertTrue((Path(args.out) / "report.md").is_file())


if __name__ == "__main__":
    unittest.main()
