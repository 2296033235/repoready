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
        if getattr(backend, "name", None) == "local" and args.no_network:
            print(
                "error: --no-network requires Docker; the local backend cannot "
                "isolate network access.\n"
                "Install and start Docker, or drop --no-network.",
                file=sys.stderr,
            )
            return 2

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
