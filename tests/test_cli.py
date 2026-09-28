import unittest

import chess

from chessai import cli
from chessai.position import MoveError, Position
from chessai.session import Session


def both() -> Session:
    return Session(human_color=None)


class TestArgParsing(unittest.TestCase):
    def test_defaults(self) -> None:
        args = cli._parse_args([])
        self.assertEqual(args.side, "white")
        self.assertFalse(args.both)
        self.assertEqual(args.elo, 1500)
        self.assertEqual(args.style, "karpov")
        self.assertEqual(args.mode, "coach")

    def test_overrides(self) -> None:
        args = cli._parse_args(
            ["--side", "black", "--elo", "2400", "--style", "tal", "--mode", "match"]
        )
        self.assertEqual(args.side, "black")
        self.assertEqual(args.elo, 2400)
        self.assertEqual(args.style, "tal")
        self.assertEqual(args.mode, "match")

    def test_both_flag_wins_over_side(self) -> None:
        session = cli._build_session(cli._parse_args(["--side", "white", "--both"]))
        self.assertIsNone(session.human_color)

    def test_side_black(self) -> None:
        session = cli._build_session(cli._parse_args(["--side", "black"]))
        self.assertEqual(session.human_color, chess.BLACK)


class TestDispatch(unittest.TestCase):
    def test_move_returns_report(self) -> None:
        out = cli._dispatch(both(), "e4")
        self.assertIn("♙", out)
        self.assertIn("Nước vừa đi: e4", out)
        self.assertIn("1. e4", out)

    def test_board_command(self) -> None:
        self.assertIn("♜", cli._dispatch(both(), "/board"))

    def test_fen_command(self) -> None:
        self.assertEqual(cli._dispatch(both(), "/fen"), chess.STARTING_FEN)

    def test_pgn_command(self) -> None:
        s = both()
        s.apply_san("e4")
        self.assertEqual(cli._dispatch(s, "/pgn"), "1. e4")

    def test_help_lists_commands(self) -> None:
        out = cli._dispatch(both(), "/help")
        for name in ("/board", "/fen", "/pgn", "/undo", "/resign", "/draw", "/quit"):
            self.assertIn(name, out)

    def test_unknown_command(self) -> None:
        out = cli._dispatch(both(), "/khongco")
        self.assertIn("/khongco", out)
        self.assertIn("/help", out)

    def test_coming_soon_commands(self) -> None:
        for name in ("/hint", "/best", "/eval", "/analyze", "/puzzle", "/elo", "/style"):
            with self.subTest(name=name):
                self.assertIn("chưa hỗ trợ", cli._dispatch(both(), name))

    def test_coming_soon_ignores_arguments(self) -> None:
        self.assertIn("chưa hỗ trợ", cli._dispatch(both(), "/elo 2400"))

    def test_undo_command(self) -> None:
        s = both()
        s.apply_san("e4")
        out = cli._dispatch(s, "/undo")
        self.assertIn("Đã lùi", out)
        self.assertEqual(s.position.fen(), chess.STARTING_FEN)

    def test_undo_command_at_start(self) -> None:
        self.assertIn("Không có nước", cli._dispatch(both(), "/undo"))

    def test_resign_command(self) -> None:
        self.assertIn("đầu hàng", cli._dispatch(both(), "/resign"))

    def test_draw_command(self) -> None:
        self.assertIn("HÒA", cli._dispatch(both(), "/draw"))

    def test_illegal_move_propagates(self) -> None:
        with self.assertRaises(MoveError):
            cli._dispatch(both(), "e5")

    def test_quit_raises(self) -> None:
        with self.assertRaises(cli.Quit):
            cli._dispatch(both(), "/quit")


class TestReport(unittest.TestCase):
    def test_perspective_follows_human_colour(self) -> None:
        self.assertEqual(cli._perspective(Session(human_color=chess.BLACK)), chess.BLACK)

    def test_perspective_defaults_white_in_both_mode(self) -> None:
        self.assertEqual(cli._perspective(Session(human_color=None)), chess.WHITE)

    def test_report_mentions_fifty_move_advisory(self) -> None:
        s = Session(human_color=None)
        s.position = Position("4k3/8/8/8/8/8/8/4K2R w K - 99 100")
        self.assertIn("50 nước", cli._report(s))

    def test_report_shows_end_of_game(self) -> None:
        s = both()
        for san in ["f3", "e5", "g4", "Qh4"]:
            s.apply_san(san)
        report = cli._report(s)
        self.assertIn("KẾT THÚC", report)
        self.assertIn("chiếu hết", report)

    def test_report_board_matches_position(self) -> None:
        s = both()
        s.apply_san("e4")
        s.apply_san("e5")
        out = cli._report(s)
        self.assertIn("5 | . | . | . | . | ♟ | . | . | . | 5", out)
        self.assertIn("4 | . | . | . | . | ♙ | . | . | . | 4", out)
