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
        stdout_log=data.get("stdout_log", ""),
        stderr_log=data.get("stderr_log", ""),
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
        image_digest=data.get("image_digest"),
    )
