from __future__ import annotations

import re
from pathlib import Path

from repoready.models import SourceRef, Step
from repoready.probe.detect import ProjectProfile

WORKFLOW_GLOBS = ("*.yml", "*.yaml")
README_NAMES = ("README.md", "README.rst", "CONTRIBUTING.md")
SHELL_LANGUAGES = {"bash", "sh", "shell", "console", "zsh", ""}

RUN_KEY = re.compile(r"^(?P<indent>[ \t]*)(?:-[ \t]+)?run:[ \t]*(?P<rest>.*)$")
STEPS_KEY = re.compile(r"^(?P<indent>[ \t]*)steps:[ \t]*(?P<rest>.*)$")
BLOCK_SCALAR = re.compile(r"^(?P<style>[|>])(?P<modifiers>[0-9+-]*)$")
COMMAND_PREFIXES = (
    "cd ",
    "export ",
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
RST_DIRECTIVE = re.compile(
    r"^(?P<indent>[ \t]*)\.\.\s+(?:code-block|code)::[ \t]*(?P<lang>[^ \t]*)[ \t]*$"
)


def _workflow_files(root: Path) -> list[Path]:
    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.is_dir():
        return []
    files: list[Path] = []
    for pattern in WORKFLOW_GLOBS:
        files.extend(sorted(workflow_dir.glob(pattern)))
    return files


def _fold_block(lines: list[str]) -> str:
    folded: list[str] = []
    for index, line in enumerate(lines):
        if not line:
            folded.append("\n")
            continue
        previous = lines[index - 1] if index else ""
        if (
            folded
            and previous
            and not previous.startswith(" ")
            and not line.startswith(" ")
        ):
            folded.append(" ")
        folded.append(line)
    return "".join(folded)


def _block_scalar(
    lines: list[str], start: int, parent_indent: int, indicator: str
) -> tuple[str, int]:
    collected: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            collected.append("")
            index += 1
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= parent_indent:
            break
        collected.append(line)
        index += 1

    content_indent = min(
        (len(line) - len(line.lstrip()) for line in collected if line.strip()),
        default=parent_indent + 1,
    )
    dedented = [
        line[content_indent:] if line.strip() else "" for line in collected
    ]
    chomp = "-" if "-" in indicator[1:] else "" if "+" not in indicator[1:] else "+"
    if chomp != "+":
        while dedented and not dedented[-1]:
            dedented.pop()

    if indicator.startswith(">"):
        command = _fold_block(dedented)
    else:
        command = "\n".join(dedented)
    return command.strip(), index


def _extract_github_workflows(root: Path) -> list[Step]:
    found: list[tuple[str, str, int]] = []
    for path in _workflow_files(root):
        rel = path.relative_to(root).as_posix()
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        steps_indent: int | None = None
        index = 0
        while index < len(lines):
            line = lines[index]
            if line.strip():
                indent = len(line) - len(line.lstrip())
                if steps_indent is not None and indent <= steps_indent:
                    steps_indent = None
                steps_match = STEPS_KEY.match(line)
                if steps_match:
                    steps_indent = len(steps_match.group("indent"))
                    index += 1
                    continue

            match = RUN_KEY.match(line)
            if not match:
                index += 1
                continue
            if steps_indent is None or len(match.group("indent")) <= steps_indent:
                index += 1
                continue

            rest = match.group("rest").strip()
            block_match = BLOCK_SCALAR.match(rest)
            if rest and not block_match:
                command = _shell_command(rest)
                if command is not None:
                    found.append((command, rel, index + 1))
                index += 1
                continue

            if block_match:
                run_line = index + 1
                command, index = _block_scalar(
                    lines,
                    index + 1,
                    len(match.group("indent")),
                    block_match.group("style") + block_match.group("modifiers"),
                )
                command = _shell_command(command)
                if command is not None:
                    found.append((command, rel, run_line))
                continue
            index += 1

    return [
        Step(id=0, command=command, source=SourceRef(kind="ci", path=path, line=line))
        for command, path, line in found
    ]


def _extract_gitlab(root: Path) -> list[Step]:
    path = root / ".gitlab-ci.yml"
    if not path.is_file():
        return []
    rel = path.relative_to(root).as_posix()
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    reserved = {
        "after_script",
        "before_script",
        "cache",
        "default",
        "image",
        "include",
        "pages",
        "services",
        "stages",
        "variables",
        "workflow",
    }
    found: list[tuple[str, str, int]] = []
    current_job: str | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue

        top_level = re.match(
            r"^(?P<indent>[ \t]*)(?P<key>[A-Za-z0-9_.-]+):[ \t]*(?P<rest>.*)$",
            line,
        )
        if top_level and not top_level.group("indent"):
            key = top_level.group("key")
            if key not in reserved:
                current_job = key

        script_match = re.match(
            r"^(?P<indent>[ \t]*)(?:-[ \t]+)?"
            r"(?P<key>before_script|script):[ \t]*(?P<rest>.*)$",
            line,
        )
        if (
            script_match is None
            or current_job is None
        ):
            index += 1
            continue

        parent_indent = len(script_match.group("indent"))
        rest = script_match.group("rest").strip()
        block_match = BLOCK_SCALAR.match(rest)
        if block_match:
            line_number = index + 1
            command, index = _block_scalar(
                lines,
                index + 1,
                parent_indent,
                block_match.group("style") + block_match.group("modifiers"),
            )
            command = _shell_command(command)
            if command is not None:
                found.append((command, rel, line_number))
            continue
        if rest:
            command = _shell_command(rest)
            if command is not None:
                found.append((command, rel, index + 1))
            index += 1
            continue

        index += 1
        while index < len(lines):
            item = re.match(
                r"^(?P<indent>[ \t]*)-[ \t]+(?P<command>.+)$", lines[index]
            )
            if item is None:
                if lines[index].strip():
                    break
                index += 1
                continue
            if len(item.group("indent")) <= parent_indent:
                break
            command = item.group("command").strip()
            command = _shell_command(command)
            if command is not None:
                found.append((command, rel, index + 1))
            index += 1

    return [
        Step(id=0, command=command, source=SourceRef(kind="ci", path=path, line=line))
        for command, path, line in found
    ]


def _extract_azure(root: Path) -> list[Step]:
    path = root / "azure-pipelines.yml"
    if not path.is_file():
        return []
    rel = path.relative_to(root).as_posix()
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    found: list[tuple[str, str, int]] = []
    index = 0
    step_key = re.compile(
        r"^(?P<indent>[ \t]*)-[ \t]+"
        r"(?P<key>script|bash|sh|pwsh|powershell):[ \t]*(?P<rest>.*)$"
    )
    while index < len(lines):
        match = step_key.match(lines[index])
        if match is None:
            index += 1
            continue
        rest = match.group("rest").strip()
        block_match = BLOCK_SCALAR.match(rest)
        if block_match:
            line_number = index + 1
            command, index = _block_scalar(
                lines,
                index + 1,
                len(match.group("indent")),
                block_match.group("style") + block_match.group("modifiers"),
            )
            command = _shell_command(command)
            if command is not None:
                found.append((command, rel, line_number))
            continue
        if rest:
            command = _shell_command(rest)
            if command is not None:
                found.append((command, rel, index + 1))
        index += 1

    return [
        Step(id=0, command=command, source=SourceRef(kind="ci", path=path, line=line))
        for command, path, line in found
    ]


def extract_from_workflows(root: Path) -> list[Step]:
    return (
        _extract_github_workflows(root)
        + _extract_gitlab(root)
        + _extract_azure(root)
    )


def _shell_command(raw: str) -> str | None:
    command = raw.strip().lstrip("$ ").strip()
    if not command or command.startswith("#"):
        return None
    allowed_verbs = {prefix.strip() for prefix in COMMAND_PREFIXES}
    if command.split(maxsplit=1)[0] not in allowed_verbs:
        return None
    return command


def _markdown_code_lines(lines: list[str]) -> list[tuple[int, str]]:
    collected: list[tuple[int, str]] = []
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
        if in_block and block_is_shell:
            collected.append((number, line))
    return collected


def _rst_code_lines(lines: list[str]) -> list[tuple[int, str]]:
    collected: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        match = RST_DIRECTIVE.match(lines[index])
        if not match:
            index += 1
            continue
        directive_indent = len(match.group("indent"))
        language = match.group("lang").strip().lower()
        index += 1
        if language not in SHELL_LANGUAGES:
            continue
        while index < len(lines):
            line = lines[index]
            if not line.strip():
                index += 1
                continue
            indent = len(line) - len(line.lstrip())
            if indent <= directive_indent:
                break
            collected.append((index + 1, line))
            index += 1
    return collected


def extract_from_readme(root: Path) -> list[Step]:
    steps: list[Step] = []
    paths = [root / name for name in README_NAMES]
    docs = root / "docs"
    if docs.is_dir():
        paths.extend(sorted(docs.rglob("*.md")))
        paths.extend(sorted(docs.rglob("*.rst")))

    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        code_lines = _markdown_code_lines(lines) + _rst_code_lines(lines)
        for number, raw in sorted(code_lines):
            command = _shell_command(raw)
            if command is None:
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
        requirements = sorted(
            path
            for path in root.glob("requirements*.txt")
            if path.is_file()
        )
        if requirements:
            preferred = next(
                (path for path in requirements if path.name == "requirements.txt"),
                requirements[0],
            )
            commands.append(f"pip install -r {preferred.name}")
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
