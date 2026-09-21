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
