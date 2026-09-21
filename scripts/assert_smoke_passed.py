from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(
            "usage: python scripts/assert_smoke_passed.py RUN_JSON",
            file=sys.stderr,
        )
        return 2

    path = Path(args[0])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"could not read run record {path}: {exc}", file=sys.stderr)
        return 2

    steps = payload.get("steps")
    if not isinstance(steps, list):
        print("run record has no steps list", file=sys.stderr)
        return 2
    if not any(
        isinstance(step, dict) and step.get("status") == "passed"
        for step in steps
    ):
        print(
            "Docker smoke failed: no step passed; the container did not execute",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
