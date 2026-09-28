"""Chạy trọn ván tới chiếu hết qua tầng CLI.

Bắt lỗi tích hợp mà unit test từng phần không thấy: hiển thị sai, lệnh hỏng
sau khi ván kết thúc, PGN hỏng khi ván dài.
"""

import io
import unittest

import chess
import chess.pgn

from chessai import cli
from chessai.session import Session

RUY_LOPEZ = [
    "e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6",
    "O-O", "Be7", "Re1", "b5", "Bb3", "d6", "c3", "O-O",
    "h3", "Nb8", "d4", "Nbd7",
]


def drive(sans: list[str]) -> tuple[Session, list[str]]:
    """Chạy chuỗi lệnh qua cli, trả về session và mọi kết quả in ra."""
    session = Session(human_color=None)
    return session, [cli._dispatch(session, san) for san in sans]


class TestFullGame(unittest.TestCase):
    def test_fools_mate_through_cli(self) -> None:
        session, reports = drive(["f3", "e5", "g4", "Qh4"])
        self.assertTrue(session.is_game_over())
        self.assertIn("KẾT THÚC", reports[-1])
        self.assertIn("Đen thắng", reports[-1])
        self.assertIn("chiếu hết", reports[-1])
        self.assertIn("Qh4#", reports[-1])

    def test_board_still_renders_after_mate(self) -> None:
        session, _ = drive(["f3", "e5", "g4", "Qh4"])
        out = cli._dispatch(session, "/board")
        self.assertIn("♛", out)
        self.assertNotIn("KẾT THÚC", out)

    def test_undo_after_mate_reopens_game(self) -> None:
        session, _ = drive(["f3", "e5", "g4", "Qh4"])
        self.assertTrue(session.is_game_over())
        cli._dispatch(session, "/undo")
        self.assertFalse(session.is_game_over())
        self.assertNotIn("KẾT THÚC", cli._report(session))

    def test_illegal_move_prints_error_and_keeps_board(self) -> None:
        session, _ = drive(["e4", "e5"])
        before = session.position.fen()
        with self.assertRaises(cli.MoveError):
            cli._dispatch(session, "Qh4")
        self.assertEqual(session.position.fen(), before)

    def test_pgn_roundtrips_over_twenty_plies(self) -> None:
        session, _ = drive(RUY_LOPEZ)
        self.assertEqual(len(session.position.san_history()), 20)
        game = chess.pgn.read_game(io.StringIO(session.pgn()))
        self.assertIsNotNone(game)
        self.assertEqual(len(list(game.mainline_moves())), 20)

    def test_pgn_replays_to_identical_position(self) -> None:
        session, _ = drive(RUY_LOPEZ)
        target = session.position.fen()
        game = chess.pgn.read_game(io.StringIO(session.pgn()))
        replay = chess.Board()
        for move in game.mainline_moves():
            replay.push(move)
        self.assertEqual(replay.fen(), target)

    def test_report_board_matches_position_after_long_game(self) -> None:
        _, reports = drive(RUY_LOPEZ)
        report = reports[-1]
        # Cả hai đã nhập thành, tốt đen còn ở b5 và e5 sau toàn bộ khai cuộc.
        self.assertIn("5 | . | ♟ | . | . | ♟ | . | . | . | 5", report)
        # Vua trắng ở g1, xe từ f1 đã sang e1 (nước Re1).
        self.assertIn("1 | ♖ | ♘ | ♗ | ♕ | ♖ | . | ♔ | . | 1", report)
