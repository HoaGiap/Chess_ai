import unittest

import chess

from chessai.position import MoveError
from chessai.session import Session


class TestTurnEnforcement(unittest.TestCase):
    def test_both_sides_mode_allows_anything(self) -> None:
        s = Session(human_color=None)
        s.apply_san("e4")
        s.apply_san("e5")
        self.assertEqual(s.position.ply_count(), 2)

    def test_not_human_turn_rejected(self) -> None:
        s = Session(human_color=chess.WHITE)
        s.apply_san("e4")
        with self.assertRaises(MoveError) as ctx:
            s.apply_san("e5")
        self.assertIn("lượt", str(ctx.exception))
        self.assertEqual(s.position.ply_count(), 1)

    def test_is_human_turn(self) -> None:
        s = Session(human_color=chess.WHITE)
        self.assertTrue(s.is_human_turn())
        s.apply_san("e4")
        self.assertFalse(s.is_human_turn())

    def test_move_after_game_over_rejected(self) -> None:
        s = Session(human_color=None)
        for san in ["f3", "e5", "g4", "Qh4"]:
            s.apply_san(san)
        self.assertTrue(s.is_game_over())
        with self.assertRaises(MoveError) as ctx:
            s.apply_san("a3")
        self.assertIn("kết thúc", str(ctx.exception))


class TestUndoTurn(unittest.TestCase):
    def test_undo_pops_one_ply_in_both_mode(self) -> None:
        s = Session(human_color=None)
        s.apply_san("e4")
        s.apply_san("e5")
        after_e4 = s.position.fen()
        s.apply_san("Nf3")
        self.assertTrue(s.undo_turn())
        self.assertEqual(s.position.fen(), after_e4)

    def test_undo_pops_two_plies_when_human_has_a_side(self) -> None:
        s = Session(human_color=chess.WHITE)
        start = s.position.fen()
        s.apply_san("e4")
        s.position.apply_san("e5")  # giả lập nước AI; #1 chưa có AI
        self.assertTrue(s.undo_turn())
        self.assertEqual(s.position.fen(), start)

    def test_undo_returns_false_at_start(self) -> None:
        self.assertFalse(Session(human_color=None).undo_turn())

    def test_undo_returns_false_when_only_one_move(self) -> None:
        s = Session(human_color=chess.WHITE)
        s.apply_san("e4")
        self.assertFalse(s.undo_turn())

    def test_undo_clears_declared_result(self) -> None:
        s = Session(human_color=None)
        s.apply_san("e4")
        s.resign(chess.WHITE)
        self.assertTrue(s.is_game_over())
        s.undo_turn()
        self.assertFalse(s.is_game_over())


class TestPgn(unittest.TestCase):
    def test_pgn_keeps_headers(self) -> None:
        s = Session(human_color=None)
        s.apply_san("e4")
        self.assertIn('[Result "*"]', s.pgn())
        self.assertIn("1. e4", s.pgn())

    def test_movetext_strips_headers_and_result_marker(self) -> None:
        s = Session(human_color=None)
        s.apply_san("e4")
        self.assertEqual(s.movetext(), "1. e4")

    def test_movetext_placeholder_when_empty(self) -> None:
        self.assertEqual(Session(human_color=None).movetext(), "*")

    def test_movetext_keeps_check_suffix(self) -> None:
        s = Session(human_color=None)
        for san in ["f3", "e5", "g4", "Qh4"]:
            s.apply_san(san)
        self.assertEqual(s.movetext(), "1. f3 e5 2. g4 Qh4#")

    def test_movetext_multi_move_numbering(self) -> None:
        s = Session(human_color=None)
        for san in ["e4", "e5", "Nf3", "Nc6"]:
            s.apply_san(san)
        self.assertEqual(s.movetext(), "1. e4 e5 2. Nf3 Nc6")


class TestResults(unittest.TestCase):
    def test_resign_awards_win_to_opponent(self) -> None:
        s = Session(human_color=chess.WHITE)
        s.resign(chess.WHITE)
        self.assertTrue(s.is_game_over())
        self.assertIn("Đen thắng", s.result_text())
        self.assertIn("đầu hàng", s.result_text())

    def test_agree_draw(self) -> None:
        s = Session(human_color=chess.WHITE)
        s.agree_draw()
        self.assertTrue(s.is_game_over())
        self.assertIn("HÒA", s.result_text())

    def test_resign_is_ignored_after_game_over(self) -> None:
        s = Session(human_color=None)
        for san in ["f3", "e5", "g4", "Qh4"]:
            s.apply_san(san)
        s.resign(chess.WHITE)
        self.assertIn("chiếu hết", s.result_text())

    def test_result_text_while_running(self) -> None:
        self.assertIn("đang diễn ra", Session(human_color=chess.WHITE).result_text())


class TestStatusLine(unittest.TestCase):
    def test_status_line_shows_config(self) -> None:
        s = Session(human_color=chess.WHITE, elo=2100, style="tal", mode="match")
        line = s.status_line()
        self.assertIn("2100", line)
        self.assertIn("tal", line)
        self.assertIn("match", line)
        self.assertIn("Trắng", line)

    def test_status_line_labels_both_sides(self) -> None:
        self.assertIn("cả hai bên", Session(human_color=None).status_line())

    def test_last_move_label(self) -> None:
        s = Session(human_color=None)
        self.assertIsNone(s.last_move_label())
        s.apply_san("e4")
        self.assertEqual(s.last_move_label(), "e4")


class TestMoveHook(unittest.TestCase):
    def test_on_move_hook_called(self) -> None:
        s = Session(human_color=None)
        seen: list[str] = []
        s.on_move = seen.append
        s.apply_san("e4")
        self.assertEqual(seen, ["e4"])

    def test_on_move_hook_not_called_on_error(self) -> None:
        s = Session(human_color=None)
        seen: list[str] = []
        s.on_move = seen.append
        with self.assertRaises(MoveError):
            s.apply_san("e5")
        self.assertEqual(seen, [])
