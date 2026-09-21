# repoready MVP 纵向切片 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `python -m repoready check <仓库>` 能对一个真实开源仓库产出带执行证据的 `run.json` 与 Markdown 上手指南,失败步骤带分类归因。

**Architecture:** 三层单向数据流。探测层做纯静态分析产出候选步骤;执行层在可插拔沙箱后端里逐步执行并记录证据;报告层只渲染不判断。所有判断在执行层写入 `run.json`,报告层不重新解释。

**Tech Stack:** Python 3.10+ 标准库(argparse、dataclasses、subprocess、json、unittest),外部依赖仅 docker CLI(可选,缺失时降级到 local 后端)。

**Spec:** `docs/superpowers/specs/2026-09-20-repoready-design.md`

## Global Constraints

- 零第三方运行时依赖。不允许在实现中 import 任何不在标准库内的模块。
- 包目录位于仓库根(`repoready/`),`git clone` 后无需安装即可 `python -m repoready`。
- 测试框架固定为 `unittest`,统一用 `python -m unittest discover -s tests -t . -v` 运行。
- 一切 shell 调用走 `subprocess`,不使用 `os.system`。
- 步骤状态只允许四个值:`passed`、`failed`、`blocked`、`skipped`。`failed` 表示命令返回非零,`blocked` 表示环境不具备条件(超时、缺密钥、需 GPU)。两者不得混用。
- 归因分类只允许七个值:`missing_system_dep`、`version_conflict`、`network_required`、`credential_required`、`hardware_required`、`doc_drift`、`unknown`。
- 归因证据必须能在该步骤自身输出中原样找到;找不到即整条归因降级为 `unknown`。
- `check` 命令在项目本身失败时仍返回退出码 0;只有工具自身出错才返回非 0。
- `run.json` 的字段名即对外接口,一旦写入不得更名。

---

### Task 1: 项目骨架、CLI 入口与 CI

**Files:**
- Create: `repoready/__init__.py`
- Create: `repoready/__main__.py`
- Create: `repoready/cli.py`
- Create: `tests/__init__.py`
- Create: `tests/test_cli.py`
- Create: `pyproject.toml`
- Create: `.github/workflows/ci.yml`
- Create: `README.md`

**Interfaces:**
- Consumes: 无(首个任务)
- Produces: `repoready.cli.build_parser() -> argparse.ArgumentParser`,`repoready.cli.main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
import unittest

from repoready.cli import build_parser, main


class CliSmokeTest(unittest.TestCase):
    def test_parser_exposes_check_and_doctor(self):
        parser = build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if action.__class__.__name__ == "_SubParsersAction"
        )
        self.assertEqual(sorted(subparsers.choices), ["check", "doctor"])

    def test_check_parses_flags(self):
        parser = build_parser()
        args = parser.parse_args(
            ["check", "https://example.com/x.git", "--ref", "v1", "--backend", "docker"]
        )
        self.assertEqual(args.command, "check")
        self.assertEqual(args.ref, "v1")
        self.assertEqual(args.backend, "docker")
        self.assertEqual(args.timeout, 600)
        self.assertFalse(args.no_network)

    def test_main_without_args_returns_usage_error_code(self):
        self.assertEqual(main([]), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -t . -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'repoready'`

- [ ] **Step 3: Write minimal implementation**

```python
# repoready/__init__.py
"""repoready - verify open-source onboarding instructions by actually running them."""

__version__ = "0.1.0"
```

```python
# repoready/cli.py
from __future__ import annotations

import argparse
import sys

from repoready import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repoready",
        description="Verify open-source onboarding instructions by actually running them.",
    )
    parser.add_argument(
        "--version", action="version", version=f"repoready {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="verify a single repository")
    check.add_argument("repo", help="local path or git URL")
    check.add_argument("--ref", default=None, help="branch, tag or commit")
    check.add_argument("--out", default="reports", help="output directory")
    check.add_argument("--backend", choices=["docker", "local"], default=None)
    check.add_argument(
        "--timeout", type=int, default=600, help="per-step timeout in seconds"
    )
    check.add_argument(
        "--no-network", action="store_true", help="run steps without network access"
    )

    subparsers.add_parser("doctor", help="check the local environment")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        print("doctor: not implemented yet", file=sys.stderr)
        return 2

    if args.command == "check":
        print("check: not implemented yet", file=sys.stderr)
        return 2

    parser.print_usage()
    return 2
```

```python
# repoready/__main__.py
from __future__ import annotations

import sys

from repoready.cli import main

if __name__ == "__main__":
    sys.exit(main())
```

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "repoready"
version = "0.1.0"
description = "Verify open-source onboarding instructions by actually running them."
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
dependencies = []

[project.scripts]
repoready = "repoready.cli:main"

[tool.setuptools.packages.find]
include = ["repoready*"]
```

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Show CLI entry point works
        run: python -m repoready --version
      - name: Run unit tests
        run: python -m unittest discover -s tests -t . -v
```

```markdown
<!-- README.md -->
# repoready

Verify open-source onboarding instructions by actually running them.

`repoready` takes a repository and a commit, executes the install and test steps
that the project itself declares, and reports which steps really work - with the
evidence, not a guess.

## Status

Under active development. See `docs/superpowers/specs/` for the design.

## Requirements

- Python 3.10 or newer
- Docker (optional; without it `repoready` falls back to a local backend)

## Usage

```bash
python -m repoready doctor
python -m repoready check https://github.com/psf/requests --ref v2.32.0
```
```

Also create an empty `tests/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS,3 tests OK

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml README.md .github/workflows/ci.yml repoready tests
git commit -m "feat: add package skeleton, CLI entry point and CI"
```

---

### Task 2: doctor 命令

**Files:**
- Create: `repoready/doctor.py`
- Create: `tests/test_doctor.py`
- Modify: `repoready/cli.py`

**Interfaces:**
- Consumes: `repoready.cli.build_parser`
- Produces: `repoready.doctor.check_docker(which=..., run=...) -> DockerStatus`,`repoready.doctor.interpret_docker_output(returncode: int, stdout: str, stderr: str) -> DockerStatus`,`repoready.doctor.run_doctor(out=..., docker=...) -> int`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_doctor.py
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
        self.assertIn("engine", status.hint.lower())

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_doctor -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'repoready.doctor'`

- [ ] **Step 3: Write minimal implementation**

```python
# repoready/doctor.py
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Optional, TextIO

MIN_PYTHON = (3, 10)


@dataclass(frozen=True)
class DockerStatus:
    cli_present: bool
    daemon_reachable: bool
    server_version: Optional[str]
    docker_host: Optional[str]
    detail: str
    hint: str


def interpret_docker_output(returncode: int, stdout: str, stderr: str) -> DockerStatus:
    text = (stderr or stdout or "").strip()
    first_line = text.splitlines()[0] if text else "unknown error"

    if returncode == 0:
        return DockerStatus(
            cli_present=True,
            daemon_reachable=True,
            server_version=stdout.strip() or None,
            docker_host=os.environ.get("DOCKER_HOST"),
            detail="ok",
            hint="",
        )

    lowered = text.lower()
    if "permission denied" in lowered:
        hint = (
            "Permission denied: this account may not talk to the Docker engine. "
            "Add it to the docker-users group, then restart Docker Desktop."
        )
    elif "cannot find the file" in lowered or "docker daemon is running" in lowered:
        hint = (
            "The Docker engine is not running. Start Docker Desktop and wait until "
            "it reports 'Engine running'."
        )
    else:
        hint = (
            "Could not reach the Docker engine. Run 'docker info' in your own "
            "terminal to see the full error."
        )

    return DockerStatus(
        cli_present=True,
        daemon_reachable=False,
        server_version=None,
        docker_host=os.environ.get("DOCKER_HOST"),
        detail=first_line,
        hint=hint,
    )


def check_docker(
    which: Callable[[str], Optional[str]] = shutil.which,
    run: Callable[..., object] = subprocess.run,
) -> DockerStatus:
    exe = which("docker")
    if not exe:
        return DockerStatus(
            cli_present=False,
            daemon_reachable=False,
            server_version=None,
            docker_host=os.environ.get("DOCKER_HOST"),
            detail="docker CLI not found on PATH",
            hint=(
                "Docker is optional: repoready falls back to the local backend. "
                "Install Docker Desktop if you want container isolation."
            ),
        )

    try:
        completed = run(
            [exe, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return DockerStatus(
            cli_present=True,
            daemon_reachable=False,
            server_version=None,
            docker_host=os.environ.get("DOCKER_HOST"),
            detail=str(exc),
            hint="'docker info' did not complete. Check Docker Desktop.",
        )

    return interpret_docker_output(
        completed.returncode, completed.stdout or "", completed.stderr or ""
    )


def run_doctor(
    out: TextIO = sys.stdout, docker: Optional[DockerStatus] = None
) -> int:
    info = sys.version_info
    python_ok = (info.major, info.minor) >= MIN_PYTHON

    print("repoready doctor", file=out)
    print("=" * 40, file=out)
    suffix = "ok" if python_ok else "too old, need >= 3.10"
    print(f"Python {info.major}.{info.minor}.{info.micro}  [{suffix}]", file=out)

    status = docker if docker is not None else check_docker()
    if status.cli_present and status.daemon_reachable:
        print(f"docker {status.server_version}  [ok]", file=out)
    elif not status.cli_present:
        print("docker  [not installed - local backend will be used]", file=out)
    else:
        print(f"docker daemon  [unreachable: {status.detail}]", file=out)

    if status.docker_host:
        print(f"DOCKER_HOST = {status.docker_host}", file=out)
    if status.hint:
        print(f"hint: {status.hint}", file=out)

    return 0 if python_ok else 1
```

Modify `repoready/cli.py`: replace the `doctor` branch with

```python
    if args.command == "doctor":
        from repoready.doctor import run_doctor

        return run_doctor()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS,all tests OK

- [ ] **Step 5: Verify the real command works**

Run: `python -m repoready doctor`
Expected: prints a Python line and reports `docker 29.8.0  [ok]` on this machine.

- [ ] **Step 6: Commit**

```bash
git add repoready/doctor.py repoready/cli.py tests/test_doctor.py
git commit -m "feat: add doctor command with targeted Docker diagnostics"
```

---

### Task 3: 共享数据模型与 run.json 序列化

**Files:**
- Create: `repoready/models.py`
- Create: `repoready/report/__init__.py`
- Create: `repoready/report/json_report.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Consumes: 无
- Produces: `SourceRef`、`Step`、`Attribution`、`StepResult`、`RunRecord` 五个 dataclass;`SCHEMA_VERSION: str`;`output_text(step: StepResult) -> str`;`write_run_json(record: RunRecord, out_dir: Path) -> Path`;`load_run_json(path: Path) -> RunRecord`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
import json
import tempfile
import unittest
from pathlib import Path

from repoready.models import (
    SCHEMA_VERSION,
    Attribution,
    RunRecord,
    SourceRef,
    Step,
    StepResult,
    output_text,
)
from repoready.report.json_report import load_run_json, write_run_json


def sample_record() -> RunRecord:
    return RunRecord(
        schema_version=SCHEMA_VERSION,
        repo_url="https://github.com/example/demo",
        commit="a" * 40,
        backend="local",
        image=None,
        started_at="2026-09-21T10:00:00+08:00",
        finished_at="2026-09-21T10:00:05+08:00",
        environment={"python": "3.12.8"},
        steps=[
            StepResult(
                id=1,
                command="pip install -e .",
                status="failed",
                exit_code=1,
                duration_ms=1200,
                source=SourceRef(kind="ci", path=".github/workflows/ci.yml", line=42),
                stderr_head="ERROR: conflicting dependencies",
                stderr_tail="ERROR: conflicting dependencies",
                attribution=Attribution(
                    category="version_conflict",
                    evidence=["ERROR: conflicting dependencies"],
                    suggestion="Relax the pinned version in requirements.txt.",
                    generated_by="rules",
                ),
            )
        ],
    )


class RunRecordSerializationTest(unittest.TestCase):
    def test_round_trip_preserves_every_field(self):
        record = sample_record()
        with tempfile.TemporaryDirectory() as tmp:
            path = write_run_json(record, Path(tmp))
            self.assertEqual(load_run_json(path), record)

    def test_written_file_uses_documented_field_names(self):
        record = sample_record()
        with tempfile.TemporaryDirectory() as tmp:
            path = write_run_json(record, Path(tmp))
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["schema_version"], SCHEMA_VERSION)
            self.assertEqual(data["backend"], "local")
            self.assertEqual(data["steps"][0]["source"]["kind"], "ci")
            self.assertEqual(
                data["steps"][0]["attribution"]["category"], "version_conflict"
            )


class OutputTextTest(unittest.TestCase):
    def test_joins_all_captured_streams(self):
        step = StepResult(
            id=1,
            command="x",
            status="failed",
            exit_code=1,
            duration_ms=1,
            source=SourceRef(kind="readme", path="README.md", line=3),
            stdout_head="out-head",
            stdout_tail="out-tail",
            stderr_head="err-head",
            stderr_tail="err-tail",
        )
        text = output_text(step)
        for fragment in ("out-head", "out-tail", "err-head", "err-tail"):
            self.assertIn(fragment, text)


class StepDefaultsTest(unittest.TestCase):
    def test_step_defaults_to_repository_root(self):
        step = Step(
            id=1,
            command="pytest",
            source=SourceRef(kind="inferred", path="<inferred>"),
        )
        self.assertEqual(step.cwd, ".")
        self.assertIsNone(step.source.line)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_models -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'repoready.models'`

- [ ] **Step 3: Write minimal implementation**

```python
# repoready/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

SCHEMA_VERSION = "1"

SourceKind = Literal["ci", "readme", "inferred"]
StepStatus = Literal["passed", "failed", "blocked", "skipped"]
BackendName = Literal["docker", "local"]
AttributionCategory = Literal[
    "missing_system_dep",
    "version_conflict",
    "network_required",
    "credential_required",
    "hardware_required",
    "doc_drift",
    "unknown",
]


@dataclass(frozen=True)
class SourceRef:
    kind: SourceKind
    path: str
    line: Optional[int] = None


@dataclass(frozen=True)
class Step:
    id: int
    command: str
    source: SourceRef
    cwd: str = "."


@dataclass
class Attribution:
    category: AttributionCategory
    evidence: list[str] = field(default_factory=list)
    suggestion: str = ""
    generated_by: Literal["rules", "llm"] = "rules"


@dataclass
class StepResult:
    id: int
    command: str
    status: StepStatus
    exit_code: Optional[int]
    duration_ms: int
    source: SourceRef
    stdout_head: str = ""
    stdout_tail: str = ""
    stderr_head: str = ""
    stderr_tail: str = ""
    attribution: Optional[Attribution] = None


@dataclass
class RunRecord:
    schema_version: str
    repo_url: str
    commit: str
    backend: BackendName
    image: Optional[str]
    started_at: str
    finished_at: str
    environment: dict
    steps: list[StepResult] = field(default_factory=list)


def output_text(step: StepResult) -> str:
    """All captured output for a step, used for evidence checks."""
    return "\n".join(
        part
        for part in (
            step.stdout_head,
            step.stdout_tail,
            step.stderr_head,
            step.stderr_tail,
        )
        if part
    )
```

```python
# repoready/report/json_report.py
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from repoready.models import Attribution, RunRecord, SourceRef, StepResult


def write_run_json(record: RunRecord, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "run.json"
    payload = dataclasses.asdict(record)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def _attribution_from_dict(data: dict | None) -> Attribution | None:
    if not data:
        return None
    return Attribution(
        category=data["category"],
        evidence=list(data.get("evidence", [])),
        suggestion=data.get("suggestion", ""),
        generated_by=data.get("generated_by", "rules"),
    )


def _step_from_dict(data: dict) -> StepResult:
    return StepResult(
        id=data["id"],
        command=data["command"],
        status=data["status"],
        exit_code=data.get("exit_code"),
        duration_ms=data["duration_ms"],
        source=SourceRef(**data["source"]),
        stdout_head=data.get("stdout_head", ""),
        stdout_tail=data.get("stdout_tail", ""),
        stderr_head=data.get("stderr_head", ""),
        stderr_tail=data.get("stderr_tail", ""),
        attribution=_attribution_from_dict(data.get("attribution")),
    )


def load_run_json(path: Path) -> RunRecord:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return RunRecord(
        schema_version=data["schema_version"],
        repo_url=data["repo_url"],
        commit=data["commit"],
        backend=data["backend"],
        image=data.get("image"),
        started_at=data["started_at"],
        finished_at=data["finished_at"],
        environment=data.get("environment", {}),
        steps=[_step_from_dict(item) for item in data.get("steps", [])],
    )
```

Also create an empty `repoready/report/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add repoready/models.py repoready/report tests/test_models.py
git commit -m "feat: add shared data model and run.json serialization"
```

---

### Task 4: 探测层 - 项目识别

**Files:**
- Create: `repoready/probe/__init__.py`
- Create: `repoready/probe/detect.py`
- Create: `tests/test_detect.py`

**Interfaces:**
- Consumes: 无
- Produces: `detect_project(root: Path) -> ProjectProfile`;`ProjectProfile(languages: tuple[str, ...], package_manager: str | None, signals: tuple[str, ...])`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_detect.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_detect -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'repoready.probe'`

- [ ] **Step 3: Write minimal implementation**

```python
# repoready/probe/detect.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PYTHON_SIGNALS = (
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "setup.py",
    "setup.cfg",
    "poetry.lock",
    "Pipfile",
    "environment.yml",
    "tox.ini",
)

OTHER_LANGUAGE_SIGNALS = {
    "package.json": "node",
    "pom.xml": "java",
    "build.gradle": "java",
    "go.mod": "go",
    "Cargo.toml": "rust",
}

PACKAGE_MANAGER_PRECEDENCE = (
    ("poetry.lock", "poetry"),
    ("Pipfile", "pipenv"),
    ("environment.yml", "conda"),
    ("pyproject.toml", "pip"),
    ("requirements.txt", "pip"),
    ("setup.py", "pip"),
    ("setup.cfg", "pip"),
)


@dataclass(frozen=True)
class ProjectProfile:
    languages: tuple[str, ...]
    package_manager: str | None
    signals: tuple[str, ...]


def detect_project(root: Path) -> ProjectProfile:
    root = Path(root)
    signals: list[str] = []
    languages: list[str] = []

    for name in PYTHON_SIGNALS:
        if (root / name).is_file():
            signals.append(name)
    if signals:
        languages.append("python")

    for name, language in OTHER_LANGUAGE_SIGNALS.items():
        if (root / name).is_file():
            signals.append(name)
            if language not in languages:
                languages.append(language)

    package_manager: str | None = None
    for name, manager in PACKAGE_MANAGER_PRECEDENCE:
        if (root / name).is_file():
            package_manager = manager
            break

    return ProjectProfile(
        languages=tuple(languages),
        package_manager=package_manager,
        signals=tuple(signals),
    )
```

Also create an empty `repoready/probe/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add repoready/probe tests/test_detect.py
git commit -m "feat: detect project language and package manager"
```

---

### Task 5: 探测层 - 步骤抽取

**Files:**
- Create: `repoready/probe/sources.py`
- Create: `tests/test_sources.py`

**Interfaces:**
- Consumes: `detect_project`、`ProjectProfile`(Task 4);`Step`、`SourceRef`(Task 3)
- Produces: `extract_steps(root: Path, profile: ProjectProfile) -> list[Step]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sources.py
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

    def test_multi_line_run_block_is_captured_as_separate_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root,
                ".github/workflows/ci.yml",
                "steps:\n  - run: |\n      pip install -r requirements.txt\n      pytest -q\n",
            )
            steps = extract_steps(root, detect_project(root))
            self.assertEqual(
                [s.command for s in steps],
                ["pip install -r requirements.txt", "pytest -q"],
            )

    def test_duplicate_commands_keep_the_higher_priority_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "pyproject.toml", "")
            write(root, ".github/workflows/ci.yml", "steps:\n  - run: pytest\n")
            write(root, "README.md", "```bash\npytest\n```\n")
            steps = extract_steps(root, detect_project(root))
            self.assertEqual(len(steps), 1)
            self.assertEqual(steps[0].source.kind, "ci")

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_sources -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'repoready.probe.sources'`

- [ ] **Step 3: Write minimal implementation**

```python
# repoready/probe/sources.py
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
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        index = 0
        while index < len(lines):
            match = RUN_KEY.match(lines[index])
            if not match:
                index += 1
                continue

            rest = match.group("rest").strip()
            if rest and rest not in {"|", ">", "|-", ">-"}:
                found.append((rest, str(path.relative_to(root)), index + 1))
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
                    found.append((command, str(path.relative_to(root)), index + 1))
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add repoready/probe/sources.py tests/test_sources.py
git commit -m "feat: extract onboarding steps from CI config, docs and inference"
```

---

### Task 6: 执行层 - 后端协议与 local 后端

**Files:**
- Create: `repoready/runner/__init__.py`
- Create: `repoready/runner/base.py`
- Create: `repoready/runner/local_backend.py`
- Create: `tests/test_local_backend.py`

**Interfaces:**
- Consumes: `Step`(Task 3)
- Produces: `Limits(timeout_s: int = 600)`;`ExecOutcome(exit_code, duration_ms, stdout, stderr, blocked_reason)`;`LocalBackend()` 实现 `prepare / execute / cleanup`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_local_backend.py
import sys
import tempfile
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

    def test_timeout_is_reported_as_blocked_not_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend()
            backend.prepare(Path(tmp))
            outcome = backend.execute(
                make_step(f'"{sys.executable}" -c "import time; time.sleep(5)"'),
                Limits(timeout_s=1),
                network=True,
            )
            self.assertIsNone(outcome.exit_code)
            self.assertEqual(outcome.blocked_reason, "timeout")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_local_backend -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'repoready.runner'`

- [ ] **Step 3: Write minimal implementation**

```python
# repoready/runner/base.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from repoready.models import Step


@dataclass(frozen=True)
class Limits:
    timeout_s: int = 600


@dataclass(frozen=True)
class ExecOutcome:
    exit_code: Optional[int]
    duration_ms: int
    stdout: str
    stderr: str
    blocked_reason: Optional[str] = None


class SandboxBackend(Protocol):
    name: str

    def prepare(self, repo_root: Path) -> None: ...

    def execute(self, step: Step, limits: Limits, network: bool) -> ExecOutcome: ...

    def cleanup(self) -> None: ...
```

```python
# repoready/runner/local_backend.py
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional

from repoready.models import Step
from repoready.runner.base import ExecOutcome, Limits


def as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class LocalBackend:
    """Runs steps directly on the host. Weak isolation, zero dependencies."""

    name = "local"

    def __init__(self) -> None:
        self._root: Optional[Path] = None

    def prepare(self, repo_root: Path) -> None:
        self._root = Path(repo_root).resolve()

    def execute(self, step: Step, limits: Limits, network: bool) -> ExecOutcome:
        if self._root is None:
            raise RuntimeError("prepare() must be called before execute()")

        workdir = (self._root / step.cwd).resolve()
        started = time.monotonic()
        try:
            completed = subprocess.run(
                step.command,
                shell=True,
                cwd=workdir,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=limits.timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            return ExecOutcome(
                exit_code=None,
                duration_ms=elapsed,
                stdout=as_text(exc.stdout),
                stderr=as_text(exc.stderr),
                blocked_reason="timeout",
            )
        except OSError as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            return ExecOutcome(
                exit_code=None,
                duration_ms=elapsed,
                stdout="",
                stderr=str(exc),
                blocked_reason="spawn_failed",
            )

        elapsed = int((time.monotonic() - started) * 1000)
        return ExecOutcome(
            exit_code=completed.returncode,
            duration_ms=elapsed,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )

    def cleanup(self) -> None:
        self._root = None
```

Also create an empty `repoready/runner/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add repoready/runner tests/test_local_backend.py
git commit -m "feat: add backend protocol and local fallback backend"
```

---

### Task 7: 执行层 - docker 后端与执行器状态机

**Files:**
- Create: `repoready/runner/docker_backend.py`
- Create: `repoready/runner/executor.py`
- Create: `tests/test_docker_backend.py`
- Create: `tests/test_executor.py`

**Interfaces:**
- Consumes: `SandboxBackend`、`Limits`、`ExecOutcome`(Task 6);`Step`、`StepResult`(Task 3);`as_text`(Task 6)
- Produces: `DEFAULT_IMAGE: str`;`build_docker_command(repo_root: Path, step: Step, image: str, limits: Limits, network: bool) -> list[str]`;`DockerBackend(image: str = DEFAULT_IMAGE)`;`clip(text: str) -> tuple[str, str]`;`run_steps(steps, backend, limits, network, repo_root=Path(".")) -> list[StepResult]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_docker_backend.py
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
```

```python
# tests/test_executor.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_docker_backend tests.test_executor -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'repoready.runner.docker_backend'`

- [ ] **Step 3: Write minimal implementation**

```python
# repoready/runner/executor.py
from __future__ import annotations

from pathlib import Path

from repoready.models import Step, StepResult
from repoready.runner.base import ExecOutcome, Limits, SandboxBackend

HEAD_CHARS = 2000
TAIL_CHARS = 2000
HALTING_STATUSES = {"failed", "blocked"}


def clip(text: str) -> tuple[str, str]:
    if len(text) <= HEAD_CHARS + TAIL_CHARS:
        return text, text
    return text[:HEAD_CHARS], text[-TAIL_CHARS:]


def _to_result(step: Step, outcome: ExecOutcome) -> StepResult:
    if outcome.blocked_reason is not None:
        status = "blocked"
    elif outcome.exit_code == 0:
        status = "passed"
    else:
        status = "failed"

    stdout_head, stdout_tail = clip(outcome.stdout)
    stderr_head, stderr_tail = clip(outcome.stderr)

    return StepResult(
        id=step.id,
        command=step.command,
        status=status,
        exit_code=outcome.exit_code,
        duration_ms=outcome.duration_ms,
        source=step.source,
        stdout_head=stdout_head,
        stdout_tail=stdout_tail,
        stderr_head=stderr_head,
        stderr_tail=stderr_tail,
    )


def _skipped_result(step: Step) -> StepResult:
    return StepResult(
        id=step.id,
        command=step.command,
        status="skipped",
        exit_code=None,
        duration_ms=0,
        source=step.source,
    )


def run_steps(
    steps: list[Step],
    backend: SandboxBackend,
    limits: Limits,
    network: bool,
    repo_root: Path = Path("."),
) -> list[StepResult]:
    """Execute steps in order; the first failure skips everything after it.

    Onboarding instructions are a linear sequence: step N+1 assumes step N
    succeeded. Continuing after a failure would only produce noise.
    """
    backend.prepare(repo_root)
    results: list[StepResult] = []
    halted = False
    try:
        for step in steps:
            if halted:
                results.append(_skipped_result(step))
                continue
            outcome = backend.execute(step, limits, network)
            result = _to_result(step, outcome)
            results.append(result)
            if result.status in HALTING_STATUSES:
                halted = True
    finally:
        backend.cleanup()
    return results
```

```python
# repoready/runner/docker_backend.py
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional

from repoready.models import Step
from repoready.runner.base import ExecOutcome, Limits
from repoready.runner.local_backend import as_text

DEFAULT_IMAGE = "python:3.12-slim"
WORKDIR = "/work"


def build_docker_command(
    repo_root: Path,
    step: Step,
    image: str,
    limits: Limits,
    network: bool,
) -> list[str]:
    argv = [
        "docker",
        "run",
        "--rm",
        "--stop-timeout",
        str(limits.timeout_s),
        "--cpus",
        "2",
        "--memory",
        "2048m",
        "--mount",
        f"type=bind,source={Path(repo_root).resolve()},target={WORKDIR}",
        "--workdir",
        f"{WORKDIR}/{step.cwd}".rstrip("/"),
    ]
    if not network:
        argv += ["--network", "none"]
    argv += [image, "sh", "-lc", step.command]
    return argv


class DockerBackend:
    """Runs each step in a throwaway container. Preferred backend."""

    name = "docker"

    def __init__(self, image: str = DEFAULT_IMAGE) -> None:
        self.image = image
        self._root: Optional[Path] = None

    def prepare(self, repo_root: Path) -> None:
        self._root = Path(repo_root).resolve()

    def execute(self, step: Step, limits: Limits, network: bool) -> ExecOutcome:
        if self._root is None:
            raise RuntimeError("prepare() must be called before execute()")

        argv = build_docker_command(self._root, step, self.image, limits, network)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=limits.timeout_s + 60,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            return ExecOutcome(
                exit_code=None,
                duration_ms=elapsed,
                stdout=as_text(exc.stdout),
                stderr=as_text(exc.stderr),
                blocked_reason="timeout",
            )
        except OSError as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            return ExecOutcome(
                exit_code=None,
                duration_ms=elapsed,
                stdout="",
                stderr=str(exc),
                blocked_reason="docker_unavailable",
            )

        elapsed = int((time.monotonic() - started) * 1000)
        stderr = completed.stderr or ""
        blocked_reason = None
        if completed.returncode != 0 and "permission denied" in stderr.lower():
            blocked_reason = "docker_permission_denied"

        return ExecOutcome(
            exit_code=None if blocked_reason else completed.returncode,
            duration_ms=elapsed,
            stdout=completed.stdout or "",
            stderr=stderr,
            blocked_reason=blocked_reason,
        )

    def cleanup(self) -> None:
        self._root = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add repoready/runner tests/test_docker_backend.py tests/test_executor.py
git commit -m "feat: add docker backend and step executor state machine"
```

---

### Task 8: 归因规则与证据校验

**Files:**
- Create: `repoready/attribution/__init__.py`
- Create: `repoready/attribution/validate.py`
- Create: `repoready/attribution/rules.py`
- Create: `tests/test_attribution.py`

**Interfaces:**
- Consumes: `StepResult`、`Attribution`、`output_text`(Task 3)
- Produces: `normalize(text: str) -> str`;`evidence_supported(evidence: list[str], outputs: list[str]) -> bool`;`validate_attribution(candidate: Attribution, step: StepResult) -> Attribution`;`classify(step: StepResult) -> Attribution | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_attribution.py
import unittest

from repoready.attribution.rules import classify
from repoready.attribution.validate import (
    evidence_supported,
    normalize,
    validate_attribution,
)
from repoready.models import Attribution, SourceRef, StepResult


def make_step(stderr="", stdout="", status="failed", exit_code=1) -> StepResult:
    return StepResult(
        id=1,
        command="make install",
        status=status,
        exit_code=exit_code,
        duration_ms=5,
        source=SourceRef(kind="ci", path="ci.yml", line=1),
        stdout_head=stdout,
        stdout_tail=stdout,
        stderr_head=stderr,
        stderr_tail=stderr,
    )


class NormalizeTest(unittest.TestCase):
    def test_collapses_whitespace_and_lowercases(self):
        self.assertEqual(
            normalize("  ERROR:\tMissing\nPackage "), "error: missing package"
        )


class EvidenceSupportedTest(unittest.TestCase):
    def test_real_line_is_supported(self):
        step = make_step(stderr="ERROR: Could not find a version that satisfies it")
        self.assertTrue(
            evidence_supported(
                ["ERROR: Could not find a version that satisfies it"],
                [step.stderr_head],
            )
        )

    def test_fabricated_line_is_rejected(self):
        step = make_step(stderr="ERROR: Could not find a version")
        self.assertFalse(
            evidence_supported(
                ["ModuleNotFoundError: no module named 'torch'"], [step.stderr_head]
            )
        )

    def test_whitespace_differences_still_match(self):
        step = make_step(stderr="something  failed\nhere")
        self.assertTrue(evidence_supported(["something failed here"], [step.stderr_head]))

    def test_empty_evidence_is_not_supported(self):
        self.assertFalse(evidence_supported([], ["anything"]))


class ValidateAttributionTest(unittest.TestCase):
    def test_fabricated_evidence_downgrades_to_unknown(self):
        step = make_step(stderr="real output line")
        candidate = Attribution(
            category="version_conflict",
            evidence=["this line never appeared"],
            suggestion="pin the version",
            generated_by="llm",
        )
        result = validate_attribution(candidate, step)
        self.assertEqual(result.category, "unknown")
        self.assertEqual(result.evidence, [])
        self.assertEqual(result.generated_by, "llm")

    def test_supported_evidence_is_kept_unchanged(self):
        step = make_step(stderr="real output line")
        candidate = Attribution(
            category="version_conflict",
            evidence=["real output line"],
            suggestion="pin the version",
            generated_by="llm",
        )
        self.assertEqual(validate_attribution(candidate, step), candidate)

    def test_empty_suggestion_downgrades_to_unknown(self):
        step = make_step(stderr="real output line")
        candidate = Attribution(
            category="version_conflict",
            evidence=["real output line"],
            suggestion="   ",
            generated_by="llm",
        )
        self.assertEqual(validate_attribution(candidate, step).category, "unknown")


class ClassifyTest(unittest.TestCase):
    def test_missing_system_dependency(self):
        result = classify(make_step(stderr="gcc: command not found"))
        self.assertEqual(result.category, "missing_system_dep")
        self.assertEqual(result.evidence, ["gcc: command not found"])

    def test_version_conflict(self):
        step = make_step(
            stderr="ERROR: Cannot install a and b because these packages have conflicting dependencies"
        )
        self.assertEqual(classify(step).category, "version_conflict")

    def test_network_required(self):
        self.assertEqual(
            classify(make_step(stderr="Could not resolve host: pypi.org")).category,
            "network_required",
        )

    def test_credential_required(self):
        step = make_step(stderr="fatal: Authentication failed for 'https://github.com/x'")
        self.assertEqual(classify(step).category, "credential_required")

    def test_hardware_required(self):
        step = make_step(stderr="RuntimeError: No CUDA GPUs are available")
        self.assertEqual(classify(step).category, "hardware_required")

    def test_doc_drift_when_referenced_script_is_gone(self):
        step = make_step(stderr="python: can't open file 'scripts/setup.py': [Errno 2]")
        self.assertEqual(classify(step).category, "doc_drift")

    def test_unrecognised_output_falls_back_to_unknown(self):
        step = make_step(stderr="something completely unexpected happened")
        result = classify(step)
        self.assertEqual(result.category, "unknown")
        self.assertEqual(result.evidence, [])

    def test_passing_step_is_not_classified(self):
        self.assertIsNone(classify(make_step(status="passed", exit_code=0)))

    def test_blocked_step_is_classified_too(self):
        step = make_step(stderr="Could not resolve host: example.com", status="blocked", exit_code=None)
        self.assertEqual(classify(step).category, "network_required")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_attribution -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'repoready.attribution'`

- [ ] **Step 3: Write minimal implementation**

```python
# repoready/attribution/validate.py
from __future__ import annotations

from repoready.models import Attribution, StepResult, output_text


def normalize(text: str) -> str:
    return " ".join(text.split()).lower()


def evidence_supported(evidence: list[str], outputs: list[str]) -> bool:
    usable = [item for item in evidence if item.strip()]
    if not usable:
        return False
    haystack = normalize("\n".join(outputs))
    return all(normalize(item) in haystack for item in usable)


def validate_attribution(candidate: Attribution, step: StepResult) -> Attribution:
    """Downgrade to unknown unless every quoted line really appears in the output."""
    if not evidence_supported(list(candidate.evidence), [output_text(step)]):
        return Attribution(
            category="unknown",
            evidence=[],
            suggestion=(
                "Attribution could not be supported by the captured output; "
                "read the raw log for this step."
            ),
            generated_by=candidate.generated_by,
        )
    if not candidate.suggestion.strip():
        return Attribution(
            category="unknown",
            evidence=[],
            suggestion="Attribution came with no actionable suggestion.",
            generated_by=candidate.generated_by,
        )
    return candidate
```

```python
# repoready/attribution/rules.py
from __future__ import annotations

from typing import Optional

from repoready.models import Attribution, AttributionCategory, StepResult, output_text

SUGGESTIONS: dict[str, str] = {
    "missing_system_dep": (
        "Install the missing system package in the execution image, or document it "
        "as a prerequisite."
    ),
    "version_conflict": (
        "Relax or align the pinned versions; the declared constraints cannot be "
        "satisfied together."
    ),
    "network_required": (
        "This step needs network access or an external host. Re-run with network "
        "enabled, or document the requirement."
    ),
    "credential_required": (
        "This step needs credentials or access to a private resource. Supply them "
        "through environment variables and document it."
    ),
    "hardware_required": (
        "This step needs specific hardware such as a GPU. Document the requirement "
        "so contributors know before they start."
    ),
    "doc_drift": (
        "The documented command references a file or target that no longer exists. "
        "The documentation has drifted from the code."
    ),
    "unknown": (
        "Could not classify this failure automatically. Read the raw log for this step."
    ),
}

PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "hardware_required",
        ("no cuda gpus", "cuda is not available", "nvidia-smi", "no gpu"),
    ),
    (
        "credential_required",
        (
            "authentication failed",
            "permission denied (publickey)",
            "invalid api key",
            "401 unauthorized",
            "no credentials",
        ),
    ),
    (
        "network_required",
        (
            "could not resolve host",
            "temporary failure in name resolution",
            "connection timed out",
            "network is unreachable",
        ),
    ),
    (
        "version_conflict",
        (
            "conflicting dependencies",
            "resolutionimpossible",
            "version solving failed",
            "could not find a version that satisfies",
        ),
    ),
    (
        "doc_drift",
        ("can't open file", "unknown command:", "no such file or directory: 'scripts/"),
    ),
    (
        "missing_system_dep",
        (
            "command not found",
            "is not recognized as an internal or external command",
            "fatal error:",
            "no such file or directory",
        ),
    ),
)


def _matching_line(text: str, needle: str) -> Optional[str]:
    for line in text.splitlines():
        if needle in line.lower():
            return line.strip()
    return None


def classify(step: StepResult) -> Optional[Attribution]:
    if step.status == "passed":
        return None

    text = output_text(step)
    lowered = text.lower()
    for category, needles in PATTERNS:
        for needle in needles:
            if needle in lowered:
                line = _matching_line(text, needle)
                return Attribution(
                    category=category,  # type: ignore[arg-type]
                    evidence=[line] if line else [],
                    suggestion=SUGGESTIONS[category],
                    generated_by="rules",
                )

    return Attribution(
        category="unknown",
        evidence=[],
        suggestion=SUGGESTIONS["unknown"],
        generated_by="rules",
    )
```

Also create an empty `repoready/attribution/__init__.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add repoready/attribution tests/test_attribution.py
git commit -m "feat: classify failures and enforce evidence-backed attribution"
```

---

### Task 9: Markdown 报告与端到端 check 命令

**Files:**
- Create: `repoready/report/markdown.py`
- Create: `repoready/commands/__init__.py`
- Create: `repoready/commands/check.py`
- Create: `tests/test_markdown.py`
- Modify: `repoready/cli.py`

**Interfaces:**
- Consumes: 全部前置任务的产出
- Produces: `render_markdown(record: RunRecord) -> str`;`run_check(args: argparse.Namespace) -> int`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_markdown.py
import unittest

from repoready.models import SCHEMA_VERSION, Attribution, RunRecord, SourceRef, StepResult
from repoready.report.markdown import render_markdown


def record_with(steps) -> RunRecord:
    return RunRecord(
        schema_version=SCHEMA_VERSION,
        repo_url="https://github.com/example/demo",
        commit="abcdef1234567890",
        backend="docker",
        image="python:3.12-slim",
        started_at="2026-09-21T10:00:00+08:00",
        finished_at="2026-09-21T10:00:09+08:00",
        environment={"python": "3.12.8"},
        steps=list(steps),
    )


def step_result(**overrides) -> StepResult:
    base = dict(
        id=1,
        command="pip install -e .",
        status="passed",
        exit_code=0,
        duration_ms=1200,
        source=SourceRef(kind="ci", path=".github/workflows/ci.yml", line=42),
    )
    base.update(overrides)
    return StepResult(**base)


class RenderMarkdownTest(unittest.TestCase):
    def test_header_contains_repo_commit_and_backend(self):
        text = render_markdown(record_with([]))
        self.assertIn("https://github.com/example/demo", text)
        self.assertIn("abcdef1234567890", text)
        self.assertIn("docker", text)

    def test_passing_step_is_listed_with_source_location(self):
        text = render_markdown(record_with([step_result()]))
        self.assertIn("pip install -e .", text)
        self.assertIn(".github/workflows/ci.yml:42", text)
        self.assertIn("passed", text)

    def test_failed_step_shows_category_evidence_and_suggestion(self):
        failed = step_result(
            status="failed",
            exit_code=1,
            stderr_head="ERROR: conflicting dependencies",
            stderr_tail="ERROR: conflicting dependencies",
            attribution=Attribution(
                category="version_conflict",
                evidence=["ERROR: conflicting dependencies"],
                suggestion="Align the pinned versions.",
                generated_by="rules",
            ),
        )
        text = render_markdown(record_with([failed]))
        self.assertIn("version_conflict", text)
        self.assertIn("ERROR: conflicting dependencies", text)
        self.assertIn("Align the pinned versions.", text)

    def test_summary_counts_every_status(self):
        steps = [
            step_result(id=1),
            step_result(id=2, status="failed", exit_code=1),
            step_result(id=3, status="skipped", exit_code=None),
        ]
        text = render_markdown(record_with(steps))
        self.assertIn("1 passed", text)
        self.assertIn("1 failed", text)
        self.assertIn("1 skipped", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_markdown -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'repoready.report.markdown'`

- [ ] **Step 3: Write minimal implementation**

```python
# repoready/report/markdown.py
from __future__ import annotations

from repoready.models import RunRecord, StepResult

LABELS = {
    "passed": "PASS",
    "failed": "FAIL",
    "blocked": "BLOCK",
    "skipped": "SKIP",
}
STATUS_ORDER = ("passed", "failed", "blocked", "skipped")


def _source_label(step: StepResult) -> str:
    if step.source.line is None:
        return step.source.path
    return f"{step.source.path}:{step.source.line}"


def _summary(record: RunRecord) -> str:
    counts = {name: 0 for name in STATUS_ORDER}
    for step in record.steps:
        counts[step.status] = counts.get(step.status, 0) + 1
    return ", ".join(f"{counts[name]} {name}" for name in STATUS_ORDER)


def render_markdown(record: RunRecord) -> str:
    lines: list[str] = []
    lines.append(f"# Onboarding verification: {record.repo_url}")
    lines.append("")
    lines.append(f"- commit: `{record.commit}`")
    lines.append(f"- backend: `{record.backend}`")
    if record.image:
        lines.append(f"- image: `{record.image}`")
    lines.append(f"- started: {record.started_at}")
    lines.append(f"- finished: {record.finished_at}")
    lines.append(f"- summary: {_summary(record)}")
    lines.append("")
    lines.append("## Steps")
    lines.append("")

    for step in record.steps:
        label = LABELS.get(step.status, step.status.upper())
        lines.append(f"### {step.id}. [{label}] `{step.command}`")
        lines.append("")
        lines.append(f"- declared in: `{_source_label(step)}` ({step.source.kind})")
        lines.append(f"- exit code: {step.exit_code}")
        lines.append(f"- duration: {step.duration_ms} ms")
        if step.attribution is not None:
            lines.append(f"- category: `{step.attribution.category}`")
            lines.append(f"- suggestion: {step.attribution.suggestion}")
            for item in step.attribution.evidence:
                lines.append(f"- evidence: `{item}`")
        output = (step.stderr_tail or step.stdout_tail).strip()
        if output:
            lines.append("")
            lines.append("```text")
            lines.append(output)
            lines.append("```")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
```

```python
# repoready/commands/check.py
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
import tempfile
from pathlib import Path

from repoready.attribution.rules import classify
from repoready.doctor import check_docker
from repoready.models import SCHEMA_VERSION, RunRecord
from repoready.probe.detect import detect_project
from repoready.probe.sources import extract_steps
from repoready.report.json_report import write_run_json
from repoready.report.markdown import render_markdown
from repoready.runner.base import Limits
from repoready.runner.docker_backend import DockerBackend
from repoready.runner.executor import run_steps
from repoready.runner.local_backend import LocalBackend


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _head_sha(path: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def materialize(repo: str, ref: str | None, workdir: Path) -> tuple[Path, str]:
    """Return the checkout path and the resolved commit SHA."""
    if "://" in repo or repo.endswith(".git"):
        target = workdir / "repo"
        subprocess.run(
            ["git", "clone", "--quiet", repo, str(target)], check=True, timeout=900
        )
        if ref:
            subprocess.run(
                ["git", "-C", str(target), "checkout", "--quiet", ref],
                check=True,
                timeout=300,
            )
        return target, _head_sha(target)

    local = Path(repo).expanduser().resolve()
    if not local.is_dir():
        raise SystemExit(f"not a directory: {local}")
    return local, _head_sha(local)


def select_backend(name: str | None):
    if name == "local":
        return LocalBackend()
    if name == "docker":
        return DockerBackend()
    return DockerBackend() if check_docker().daemon_reachable else LocalBackend()


def run_check(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    started = _now()

    with tempfile.TemporaryDirectory(prefix="repoready-") as tmp:
        checkout, commit = materialize(args.repo, args.ref, Path(tmp))
        profile = detect_project(checkout)
        steps = extract_steps(checkout, profile)

        if not steps:
            print("no onboarding steps found; nothing to verify", file=sys.stderr)
            return 1

        backend = select_backend(args.backend)
        results = run_steps(
            steps,
            backend,
            Limits(timeout_s=args.timeout),
            network=not args.no_network,
            repo_root=checkout,
        )

    for result in results:
        if result.status in {"failed", "blocked"}:
            result.attribution = classify(result)

    record = RunRecord(
        schema_version=SCHEMA_VERSION,
        repo_url=args.repo,
        commit=commit,
        backend=getattr(backend, "name", "unknown"),
        image=getattr(backend, "image", None),
        started_at=started,
        finished_at=_now(),
        environment={"python": sys.version.split()[0]},
        steps=results,
    )

    json_path = write_run_json(record, out_dir)
    markdown_path = out_dir / "report.md"
    markdown_path.write_text(render_markdown(record), encoding="utf-8")

    print(f"run written to {json_path}")
    print(f"report written to {markdown_path}")
    return 0
```

Modify `repoready/cli.py`: replace the `check` branch with

```python
    if args.command == "check":
        from repoready.commands.check import run_check

        return run_check(args)
```

Also create an empty `repoready/commands/__init__.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS

- [ ] **Step 5: End-to-end verification on a real repository**

Run:

```bash
python -m repoready check https://github.com/psf/requests --ref v2.32.0 --backend docker --out reports/requests
```

Expected: `reports/requests/run.json` and `reports/requests/report.md` are written;
the Markdown lists every step with its source location; the command exits 0 even
when individual steps fail.

Then inspect the report and confirm each failed or blocked step carries a
category and an evidence line that really appears in that step's captured output.

- [ ] **Step 6: Commit**

```bash
git add repoready/report/markdown.py repoready/commands repoready/cli.py tests/test_markdown.py
git commit -m "feat: render markdown reports and wire up the check command"
```

---

## Plan Self-Review

**Spec coverage**

| Spec section | Task | Status |
| --- | --- | --- |
| 5.1 探测层识别 | Task 4 | covered |
| 5.1 探测层抽取与出处标注 | Task 5 | covered |
| 5.2 执行层后端与状态机 | Task 6, Task 7 | covered |
| 5.2 Docker 连接三类失败区分 | Task 2 | covered |
| 5.3 报告层 JSON | Task 3 | covered |
| 5.3 报告层 Markdown | Task 9 | covered |
| 5.3 报告层 HTML | - | 后续计划 2026-09-28-bench-and-evaluation.md |
| 6 数据模型 | Task 3 | covered |
| 7 失败归因与防幻觉约束 | Task 8 | covered |
| 7.2 LLM 归因阶段 | - | 后续计划(规则阶段已覆盖主流程) |
| 8 评测集与 bench | - | 后续计划 2026-09-28-bench-and-evaluation.md |
| 9 CLI:doctor | Task 2 | covered |
| 9 CLI:check | Task 9 | covered |
| 9 CLI:bench / report | - | 后续计划 |
| 10 标准库优先 | Global Constraints + 各任务实现 | covered |
| 12 测试策略 | 每个任务的 Step 1/2/4 | covered |
| 14 MIT 与第三方披露 | - | 后续计划 2026-10-02-release-and-compliance.md |

本计划产出可运行、可测试的纵向切片。未覆盖项由两份后续计划承接,不在此重复。

**Placeholder scan:** 无 TBD,无"稍后补充",无"与 Task N 相同"的偷懒引用。每个代码步骤都给出可直接落盘的完整代码。

**Type consistency:** 跨任务复用的签名逐一对齐 -
`Limits(timeout_s=600)`、`ExecOutcome(exit_code, duration_ms, stdout, stderr, blocked_reason)`
(Task 6 定义,Task 7 使用)、`Step(id, command, source, cwd=".")`、`SourceRef(kind, path, line=None)`、
`StepResult(...)`、`RunRecord(...)`、`SCHEMA_VERSION`(Task 3 定义,Task 9 使用)、
`output_text(step)`(Task 3 定义,Task 8 使用)、
`run_steps(steps, backend, limits, network, repo_root)`(Task 7 定义,Task 9 使用)、
`as_text(value)`(Task 6 定义,Task 7 复用)、
`check_docker()`(Task 2 定义,Task 9 使用)。

**Checklist syntax:** 每个任务用 `- [ ]` 标记步骤,便于执行器逐条勾选。
