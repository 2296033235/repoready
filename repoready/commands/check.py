from __future__ import annotations

import argparse
import datetime as dt
import platform
import re
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


class BackendUnavailable(RuntimeError):
    pass


_FULL_COMMIT = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")


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
        raise SystemExit(f"could not resolve a commit for {path}")
    sha = completed.stdout.strip()
    if completed.returncode != 0 or not _FULL_COMMIT.fullmatch(sha):
        detail = completed.stderr.strip() or "not a git checkout"
        raise SystemExit(f"could not resolve a full commit for {path}: {detail}")
    return sha.lower()


def materialize(repo: str, ref: str | None, workdir: Path) -> tuple[Path, str]:
    """Return the checkout path and the resolved commit SHA."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    target = workdir / "repo"
    source = repo
    if "://" not in repo:
        local = Path(repo).expanduser().resolve()
        if local.is_dir():
            source = str(local)
        elif not repo.endswith(".git") and "@" not in repo:
            raise SystemExit(f"not a directory: {local}")
    try:
        subprocess.run(
            ["git", "clone", "--quiet", source, str(target)],
            check=True,
            timeout=900,
            capture_output=True,
        )
        if ref:
            subprocess.run(
                ["git", "-C", str(target), "checkout", "--quiet", ref],
                check=True,
                timeout=300,
                capture_output=True,
            )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
        message = detail or f"git exited with {exc.returncode}"
        raise SystemExit(f"could not materialize {repo!r}: {message}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"timed out materializing {repo!r}") from exc
    return target, _head_sha(target)


def select_backend(name: str | None):
    if name == "local":
        return LocalBackend(venv=True)
    if name == "docker":
        return DockerBackend()
    status = check_docker()
    if status.daemon_reachable:
        return DockerBackend()
    detail = status.detail or "Docker is unavailable"
    hint = f" {status.hint}" if status.hint else ""
    raise BackendUnavailable(
        f"{detail}.{hint} Local execution is not used automatically; "
        "pass --backend local to opt in explicitly."
    )


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

        try:
            backend = select_backend(args.backend)
        except BackendUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        network = not args.no_network
        if getattr(backend, "name", None) == "local":
            allow_local_network = bool(
                getattr(args, "allow_local_network", False)
            )
            if allow_local_network:
                print(
                    "warning: local backend runs repository commands directly "
                    "on the host with a scrubbed environment. Prefer Docker for "
                    "untrusted repositories.",
                    file=sys.stderr,
                )
            else:
                print(
                    "warning: local backend uses weak host isolation; network "
                    "access is disabled by default. Pass --allow-local-network "
                    "only if you trust the repository.",
                    file=sys.stderr,
                )
                network = False
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
            network=network,
            repo_root=checkout,
            log_dir=out_dir,
        )
        if hasattr(backend, "resolve_image_digest"):
            backend.resolve_image_digest()

    for result in results:
        if result.status in {"failed", "blocked"}:
            result.attribution = classify(result, out_dir)

    record = RunRecord(
        schema_version=SCHEMA_VERSION,
        repo_url=args.repo,
        commit=commit,
        backend=getattr(backend, "name", "unknown"),
        image=getattr(backend, "image", None),
        image_digest=getattr(backend, "image_digest", None),
        started_at=started,
        finished_at=_now(),
        environment={
            "os": platform.platform(),
            "python": sys.version.split()[0],
            "docker": getattr(backend, "docker_version", None),
        },
        steps=results,
    )

    json_path = write_run_json(record, out_dir)
    markdown_path = out_dir / "report.md"
    markdown_path.write_text(render_markdown(record), encoding="utf-8")

    print(f"run written to {json_path}")
    print(f"report written to {markdown_path}")
    return 0
