from __future__ import annotations

import argparse

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
    check.add_argument(
        "--allow-local-network",
        action="store_true",
        help="explicitly allow network access in the weakly isolated local backend",
    )

    subparsers.add_parser("doctor", help="check the local environment")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code is None else int(exc.code)

    if args.command == "doctor":
        from repoready.doctor import run_doctor

        return run_doctor()

    if args.command == "check":
        from repoready.commands.check import run_check

        return run_check(args)
