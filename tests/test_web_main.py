import unittest

from chessai.web import __main__ as entry


class TestArguments(unittest.TestCase):
    def test_defaults(self) -> None:
        args = entry.parse_args([])
        self.assertEqual(args.port, 8000)
        self.assertEqual(args.host, "127.0.0.1")

    def test_overrides(self) -> None:
        args = entry.parse_args(["--port", "9000", "--host", "0.0.0.0"])
        self.assertEqual(args.port, 9000)
        self.assertEqual(args.host, "0.0.0.0")

    def test_port_must_be_a_number(self) -> None:
        with self.assertRaises(SystemExit):
            entry.parse_args(["--port", "sai"])


if __name__ == "__main__":
    unittest.main()
