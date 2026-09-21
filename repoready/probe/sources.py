from __future__ import annotations

import re
from pathlib import Path

from repoready.models import SourceRef, Step
from repoready.probe.detect import ProjectProfile

WORKFLOW_GLOBS = ("*.yml", "*.yaml")
README_NAMES = ("README.md", "README.rst", "CONTRIBUTING.md")
SHELL_LANGUAGES = {"bash", "sh", "shell", "console", "zsh", ""}

RUN_KEY = re.compile(r"^(?P<indent>[ \t]*)(?:-[ \t]+)?run:[ \t]*(?P<rest>.*)$")
COMMAND_PREFIXES = (
    "pip ",
    "python ",
    "python3 ",
    "pytest",
    "tox",
    "poetry ",
    "make ",
    "npm ",
    "yarn ",
    "uv ",
)


def _workflow_files(root: Path) -> list[Path]:
    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.is_dir():
        return []
    files: list[Path] = []
    for pattern in WORKFLOW_GLOBS:
        files.extend(sorted(workflow_dir.glob(pattern)))
    return files


def extract_from_workflows(root: Path) -> list[Step]:
    found: list[tuple[str, str, int]] = []
    for path in _workflow_files(root):
        rel = path.relative_to(root).as_posix()
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        index = 0
        while index < len(lines):
            match = RUN_KEY.match(lines[index])
            if not match:
                index += 1
                continue

            rest = match.group("rest").strip()
            if rest and rest not in {"|", ">", "|-", ">-"}:
                found.append((rest, rel, index + 1))
                index += 1
                continue

            block_indent = len(match.group("indent"))
            index += 1
            while index < len(lines):
                line = lines[index]
                if not line.strip():
                    index += 1
                    continue
                indent = len(line) - len(line.lstrip())
                if indent <= block_indent:
                    break
                command = line.strip()
                if command:
                    found.append((command, rel, index + 1))
                index += 1

    return [
        Step(id=0, command=command, source=SourceRef(kind="ci", path=path, line=line))
        for command, path, line in found
    ]


def extract_from_readme(root: Path) -> list[Step]:
    steps: list[Step] = []
    for name in README_NAMES:
        path = root / name
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        in_block = False
        block_is_shell = False
        for number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("```"):
                if not in_block:
                    language = stripped[3:].strip().lower()
                    in_block = True
                    block_is_shell = language in SHELL_LANGUAGES
                else:
                    in_block = False
                    block_is_shell = False
                continue
            if not in_block or not block_is_shell:
                continue
            command = stripped.lstrip("$ ").strip()
            if not command or command.startswith("#"):
                continue
            if not command.startswith(COMMAND_PREFIXES):
                continue
            steps.append(
                Step(
                    id=0,
                    command=command,
                    source=SourceRef(kind="readme", path=name, line=number),
                )
            )
    return steps


def infer_steps(root: Path, profile: ProjectProfile) -> list[Step]:
    commands: list[str] = []
    if profile.package_manager == "poetry":
        commands.append("poetry install")
    elif profile.package_manager == "pipenv":
        commands.append("pipenv install --dev")
    elif profile.package_manager == "conda":
        commands.append("conda env create -f environment.yml")
    elif profile.package_manager == "pip":
        if (root / "requirements.txt").is_file():
            commands.append("pip install -r requirements.txt")
        if (root / "pyproject.toml").is_file() or (root / "setup.py").is_file():
            commands.append("pip install -e .")

    if (root / "tests").is_dir():
        commands.append("python -m pytest")

    return [
        Step(
            id=0,
            command=command,
            source=SourceRef(kind="inferred", path="<inferred>", line=None),
        )
        for command in commands
    ]


def _dedupe(steps: list[Step]) -> list[Step]:
    seen: set[str] = set()
    unique: list[Step] = []
    for step in steps:
        key = " ".join(step.command.split())
        if key in seen:
            continue
        seen.add(key)
        unique.append(step)
    return unique


def extract_steps(root: Path, profile: ProjectProfile) -> list[Step]:
    ordered = (
        extract_from_workflows(root)
        + extract_from_readme(root)
        + infer_steps(root, profile)
    )
    return [
        Step(id=index, command=step.command, source=step.source, cwd=step.cwd)
        for index, step in enumerate(_dedupe(ordered), start=1)
    ]
