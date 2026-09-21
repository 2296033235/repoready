import tempfile
import unittest
from pathlib import Path

from repoready.probe.detect import detect_project
from repoready.probe.sources import extract_steps


def write(root: Path, name: str, body: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


class ExtractStepsTest(unittest.TestCase):
    def test_ci_steps_come_before_readme_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "pyproject.toml", "")
            write(
                root,
                ".github/workflows/ci.yml",
                "jobs:\n  test:\n    steps:\n      - run: pip install -e .\n",
            )
            write(root, "README.md", "# demo\n\n```bash\npytest\n```\n")

            steps = extract_steps(root, detect_project(root))

            self.assertEqual([s.command for s in steps], ["pip install -e .", "pytest"])
            self.assertEqual(steps[0].source.kind, "ci")
            self.assertEqual(steps[0].source.path, ".github/workflows/ci.yml")
            self.assertEqual(steps[0].source.line, 4)
            self.assertEqual(steps[1].source.kind, "readme")

    def test_multi_line_run_block_is_captured_as_one_shell_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/ci.yml",
                "steps:\n"
                "  - run: |\n"
                "      cd package\n"
                "      export EXAMPLE_FLAG=1\n"
                "      pip install -r requirements.txt && \\\n"
                "        pytest -q\n",
            )
            steps = extract_steps(root, detect_project(root))
            self.assertEqual(len(steps), 1)
            self.assertEqual(
                steps[0].command,
                "cd package\n"
                "export EXAMPLE_FLAG=1\n"
                "pip install -r requirements.txt && \\\n"
                "  pytest -q",
            )
            self.assertEqual(steps[0].source.line, 2)

    def test_folded_run_block_uses_yaml_folding_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/ci.yml",
                "steps:\n"
                "  - run: >\n"
                "      pip install -r requirements.txt &&\n"
                "      pytest -q\n",
            )
            steps = extract_steps(root, detect_project(root))
            self.assertEqual(
                [s.command for s in steps],
                ["pip install -r requirements.txt && pytest -q"],
            )

    def test_run_key_outside_steps_block_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/ci.yml",
                "jobs:\n  test:\n    container:\n      run:\n        image: python:3.12\n",
            )
            steps = extract_steps(root, detect_project(root))
            self.assertEqual(steps, [])

    def test_sibling_run_key_under_a_step_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/ci.yml",
                "steps:\n  - name: Run tests\n    run: pytest -q\n",
            )
            steps = extract_steps(root, detect_project(root))
            self.assertEqual([s.command for s in steps], ["pytest -q"])
            self.assertEqual(steps[0].source.line, 3)

    def test_non_allowlisted_issue_workflow_yields_no_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/close-issues.yml",
                "name: Close inactive issues\n"
                "jobs:\n"
                "  close:\n"
                "    steps:\n"
                "      - run: |\n"
                "          gh issue close $ISSUE_URL \\\n"
                "            --comment \"Closed as stale\" \\\n"
                "            --reason completed\n"
                "          gh issue lock $ISSUE_URL --reason off_topic \\\n"
                "            --comment \"Locked as stale\"\n",
            )
            write(
                root,
                ".github/workflows/run-tests.yml",
                "jobs:\n"
                "  test:\n"
                "    steps:\n"
                "      - run: make\n"
                "      - run: python -m pip install -r requirements.txt\n",
            )

            steps = extract_steps(root, detect_project(root))

            self.assertEqual(
                [s.command for s in steps],
                [
                    "make",
                    "python -m pip install -r requirements.txt",
                ],
            )
            self.assertTrue(
                all(
                    s.source.path == ".github/workflows/run-tests.yml"
                    for s in steps
                )
            )

    def test_non_allowlisted_commands_are_filtered_from_onboarding_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/ci.yml",
                "jobs:\n"
                "  test:\n"
                "    steps:\n"
                "      - run: pip install -e .\n"
                "      - run: GH_TOKEN=secret gh issue close 123\n"
                "      - run: pytest -q\n",
            )

            steps = extract_steps(root, detect_project(root))

            self.assertEqual(
                [s.command for s in steps],
                ["pip install -e .", "pytest -q"],
            )

    def test_job_name_does_not_filter_allowlisted_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/ci.yml",
                "jobs:\n"
                "  maintenance:\n"
                "    steps:\n"
                "      - run: pip install -e .\n"
                "      - run: pytest -q\n",
            )

            steps = extract_steps(root, detect_project(root))

            self.assertEqual(
                [s.command for s in steps],
                ["pip install -e .", "pytest -q"],
            )

    def test_release_named_workflow_with_onboarding_commands_is_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/release-tests.yml",
                "jobs:\n"
                "  test:\n"
                "    steps:\n"
                "      - run: pip install -e .\n"
                "      - run: pytest -q\n",
            )

            steps = extract_steps(root, detect_project(root))

            self.assertEqual(
                [s.command for s in steps],
                ["pip install -e .", "pytest -q"],
            )
            self.assertTrue(
                all(
                    s.source.path == ".github/workflows/release-tests.yml"
                    for s in steps
                )
            )

    def test_duplicate_commands_keep_the_higher_priority_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "pyproject.toml", "")
            write(root, ".github/workflows/ci.yml", "steps:\n  - run: pytest\n")
            write(root, "README.md", "```bash\npytest\n```\n")
            steps = extract_steps(root, detect_project(root))
            pytest_steps = [s for s in steps if s.command == "pytest"]
            self.assertEqual(len(pytest_steps), 1)
            self.assertEqual(pytest_steps[0].source.kind, "ci")

    def test_gitlab_ci_script_commands_are_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".gitlab-ci.yml",
                "test:\n"
                "  script:\n"
                "    - pip install -e .\n"
                "    - pytest -q\n"
                "release:\n"
                "  script:\n"
                "    - twine upload dist/*\n",
            )
            steps = extract_steps(root, detect_project(root))
            self.assertEqual(
                [s.command for s in steps],
                ["pip install -e .", "pytest -q"],
            )
            self.assertTrue(all(s.source.path == ".gitlab-ci.yml" for s in steps))

    def test_azure_pipeline_script_commands_are_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                "azure-pipelines.yml",
                "steps:\n"
                "  - script: pip install -e .\n"
                "  - bash: pytest -q\n"
                "  - script: az deployment group create -g demo\n",
            )
            steps = extract_steps(root, detect_project(root))
            self.assertEqual(
                [s.command for s in steps],
                ["pip install -e .", "pytest -q"],
            )
            self.assertTrue(
                all(s.source.path == "azure-pipelines.yml" for s in steps)
            )

    def test_azure_job_name_does_not_filter_allowlisted_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                "azure-pipelines.yml",
                "jobs:\n"
                "- job: Maintenance\n"
                "  steps:\n"
                "  - script: pip install -e .\n"
                "  - script: pytest -q\n",
            )
            steps = extract_steps(root, detect_project(root))
            self.assertEqual(
                [s.command for s in steps],
                ["pip install -e .", "pytest -q"],
            )

    def test_docs_code_blocks_are_captured_as_documentation_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                "docs/install.md",
                "# Install\n\n```bash\npip install -e .\npytest -q\n```\n",
            )
            steps = extract_steps(root, detect_project(root))
            self.assertEqual(
                [s.command for s in steps],
                ["pip install -e .", "pytest -q"],
            )
            self.assertTrue(all(s.source.kind == "readme" for s in steps))
            self.assertTrue(all(s.source.path == "docs/install.md" for s in steps))

    def test_rst_code_block_is_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                "README.rst",
                "Install\n=======\n\n.. code-block:: bash\n\n   pip install -e .\n   pytest -q\n",
            )
            steps = extract_steps(root, detect_project(root))
            self.assertEqual(
                [s.command for s in steps],
                ["pip install -e .", "pytest -q"],
            )
            self.assertTrue(all(s.source.kind == "readme" for s in steps))

    def test_inferred_steps_fill_in_when_no_documents_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "pyproject.toml", "")
            write(root, "tests/test_thing.py", "")
            steps = extract_steps(root, detect_project(root))
            commands = [s.command for s in steps]
            self.assertIn("pip install -e .", commands)
            self.assertIn("python -m pytest", commands)
            self.assertTrue(all(s.source.kind == "inferred" for s in steps))

    def test_inferred_requirements_uses_general_requirements_glob(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "requirements-dev.txt", "")
            steps = extract_steps(root, detect_project(root))
            self.assertEqual(
                [s.command for s in steps],
                ["pip install -r requirements-dev.txt"],
            )

    def test_steps_are_numbered_from_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "pyproject.toml", "")
            write(
                root,
                ".github/workflows/ci.yml",
                "steps:\n  - run: pip install -e .\n  - run: pytest\n",
            )
            steps = extract_steps(root, detect_project(root))
            self.assertEqual([s.id for s in steps], list(range(1, len(steps) + 1)))


if __name__ == "__main__":
    unittest.main()
