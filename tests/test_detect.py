import tempfile
import unittest
from pathlib import Path

from repoready.probe.detect import detect_project


def touch(root: Path, *names: str) -> None:
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")


class DetectProjectTest(unittest.TestCase):
    def test_pyproject_marks_python_and_pip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            touch(root, "pyproject.toml")
            profile = detect_project(root)
            self.assertIn("python", profile.languages)
            self.assertEqual(profile.package_manager, "pip")
            self.assertIn("pyproject.toml", profile.signals)

    def test_poetry_lock_wins_over_pip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            touch(root, "pyproject.toml", "poetry.lock")
            self.assertEqual(detect_project(root).package_manager, "poetry")

    def test_requirements_only_project_is_python_with_pip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            touch(root, "requirements.txt")
            profile = detect_project(root)
            self.assertEqual(profile.languages, ("python",))
            self.assertEqual(profile.package_manager, "pip")

    def test_required_python_signals_cover_version_makefile_and_requirements_globs(self):
        for name in (".python-version", "Makefile", "requirements-dev.txt"):
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    touch(root, name)
                    profile = detect_project(root)
                    self.assertIn("python", profile.languages)
                    self.assertIn(name, profile.signals)

    def test_node_project_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            touch(root, "package.json")
            self.assertIn("node", detect_project(root).languages)

    def test_empty_directory_yields_empty_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = detect_project(Path(tmp))
            self.assertEqual(profile.languages, ())
            self.assertIsNone(profile.package_manager)
            self.assertEqual(profile.signals, ())


if __name__ == "__main__":
    unittest.main()
