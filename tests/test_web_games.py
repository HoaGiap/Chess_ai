import unittest

import chess

from chessai.position import MoveError
from chessai.web.games import GameNotFound, GameStore


def fresh(fen: str | None = None) -> tuple[GameStore, str]:
    store = GameStore()
    game_id = store.create(None)
    if fen is not None:
        store.set_fen(game_id, fen)
    return store, game_id


class TestCreate(unittest.TestCase):
    def test_create_returns_id_and_starting_state(self) -> None:
        store, game_id = fresh()
        self.assertEqual(len(game_id), 12)
        state = store.snapshot(game_id)
        self.assertEqual(state.fen, chess.STARTING_FEN)
        self.assertEqual(state.turn, "white")
        self.assertFalse(state.over)
        self.assertEqual(state.moves, [])

    def test_starting_position_has_twenty_legal_moves(self) -> None:
        store, game_id = fresh()
        self.assertEqual(len(store.snapshot(game_id).legal), 20)

    def test_legal_moves_carry_from_and_to_squares(self) -> None:
        store, game_id = fresh()
        e4 = [m for m in store.snapshot(game_id).legal if m.san == "e4"]
        self.assertEqual(len(e4), 1)
        self.assertEqual(e4[0].from_sq, "e2")
        self.assertEqual(e4[0].to_sq, "e4")
        self.assertFalse(e4[0].capture)
        self.assertFalse(e4[0].promotion)

    def test_ids_are_unique(self) -> None:
        store = GameStore()
        self.assertEqual(len({store.create(None) for _ in range(50)}), 50)


class TestMove(unittest.TestCase):
    def test_submit_updates_fen_and_moves(self) -> None:
        store, game_id = fresh()
        store.submit(game_id, "e4")
        state = store.submit(game_id, "e5")
        self.assertEqual(state.moves, ["e4", "e5"])
        self.assertNotEqual(state.fen, chess.STARTING_FEN)
        self.assertEqual(state.turn, "white")

    def test_submit_sets_last_from_and_to(self) -> None:
        store, game_id = fresh()
        state = store.submit(game_id, "e4")
        self.assertEqual(state.last_move, "e4")
        self.assertEqual(state.last_from, "e2")
        self.assertEqual(state.last_to, "e4")

    def test_illegal_move_raises_and_leaves_state_untouched(self) -> None:
        store, game_id = fresh()
        before = store.snapshot(game_id).fen
        with self.assertRaises(MoveError):
            store.submit(game_id, "e5")
        self.assertEqual(store.snapshot(game_id).fen, before)

    def test_castling_option_has_king_start_and_end(self) -> None:
        store, game_id = fresh("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        options = [m for m in store.snapshot(game_id).legal if m.san == "O-O"]
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].from_sq, "e1")
        self.assertEqual(options[0].to_sq, "g1")

    def test_castling_blocked_message_names_the_attacked_square(self) -> None:
        """Review Focus #2: phải nêu f1 (ô đi qua), không phải e1 (ô vua)."""
        store, game_id = fresh("4k3/5r2/8/8/8/8/8/4K2R w K - 0 1")
        with self.assertRaises(MoveError) as ctx:
            store.submit(game_id, "O-O")
        message = str(ctx.exception)
        self.assertIn("f1", message)
        self.assertNotIn("ô e1 ", message)

    def test_promotion_option_is_flagged(self) -> None:
        store, game_id = fresh("8/P6k/8/8/8/8/8/K7 w - - 0 1")
        options = [m for m in store.snapshot(game_id).legal if m.to_sq == "a8"]
        self.assertTrue(options)
        for option in options:
            self.assertTrue(option.promotion, option.san)
            self.assertEqual(option.from_sq, "a7")

    def test_en_passant_option_lands_on_empty_square(self) -> None:
        """Tốt a5 đi được 2 nước: a6 (đẩy) và b6 (bắt qua đường)."""
        store, game_id = fresh("4k3/8/8/Pp6/8/8/8/4K3 w - b6 0 1")
        options = [m for m in store.snapshot(game_id).legal if m.from_sq == "a5"]
        self.assertEqual(len(options), 2)
        capture = [m for m in options if m.to_sq == "b6"]
        self.assertEqual(len(capture), 1)
        self.assertTrue(capture[0].capture)
        self.assertFalse(capture[0].promotion)

    def test_check_is_reported(self) -> None:
        store, game_id = fresh("4k3/8/8/8/8/8/4r3/4K3 w - - 0 1")
        self.assertTrue(store.snapshot(game_id).check)


class TestCaptured(unittest.TestCase):
    def _captured(self, *sans: str) -> tuple[list[str], list[str]]:
        store, game_id = fresh()
        for san in sans:
            store.submit(game_id, san)
        state = store.snapshot(game_id)
        return state.captured_by_white, state.captured_by_black

    def test_white_captures_a_black_pawn(self) -> None:
        white, black = self._captured("e4", "d5", "exd5")
        self.assertEqual(white, ["P"])
        self.assertEqual(black, [])

    def test_black_captures_a_white_pawn(self) -> None:
        white, black = self._captured("e4", "d5", "exd5", "Qxd5")
        self.assertEqual(white, ["P"])
        self.assertEqual(black, ["P"])

    def test_en_passant_capture_is_counted(self) -> None:
        white, _ = self._captured("e4", "a6", "e5", "d5", "exd6")
        self.assertEqual(white, ["P"])

    def test_no_captures_yields_empty_lists(self) -> None:
        white, black = self._captured("e4", "e5")
        self.assertEqual(white, [])
        self.assertEqual(black, [])


class TestUndoAndReset(unittest.TestCase):
    def test_undo_restores_previous_fen(self) -> None:
        store, game_id = fresh()
        start = store.snapshot(game_id).fen
        store.submit(game_id, "e4")
        self.assertTrue(store.snapshot(game_id).can_undo)
        after = store.undo(game_id)
        self.assertEqual(after.fen, start)
        self.assertEqual(after.moves, [])

    def test_undo_on_new_game_raises(self) -> None:
        store, game_id = fresh()
        self.assertFalse(store.snapshot(game_id).can_undo)
        with self.assertRaises(MoveError):
            store.undo(game_id)

    def test_new_game_resets_but_keeps_id(self) -> None:
        store, game_id = fresh()
        store.submit(game_id, "e4")
        state = store.new_game(game_id)
        self.assertEqual(state.game_id, game_id)
        self.assertEqual(state.fen, chess.STARTING_FEN)
        self.assertEqual(state.moves, [])

    def test_undo_clears_captured_pieces(self) -> None:
        store, game_id = fresh()
        for san in ("e4", "d5", "exd5"):
            store.submit(game_id, san)
        self.assertEqual(store.snapshot(game_id).captured_by_white, ["P"])
        store.undo(game_id)
        self.assertEqual(store.snapshot(game_id).captured_by_white, [])

    def test_pgn_text_after_move(self) -> None:
        store, game_id = fresh()
        store.submit(game_id, "e4")
        store.submit(game_id, "e5")
        self.assertIn("1. e4 e5", store.pgn_text(game_id))

    def test_pgn_text_of_unknown_id_raises(self) -> None:
        with self.assertRaises(GameNotFound):
            GameStore().pgn_text("khongco")


class TestNotFound(unittest.TestCase):
    def test_snapshot_of_unknown_id_raises(self) -> None:
        with self.assertRaises(GameNotFound):
            GameStore().snapshot("khongcothat")

    def test_submit_to_unknown_id_raises(self) -> None:
        with self.assertRaises(GameNotFound):
            GameStore().submit("khongcothat", "e4")

    def test_forget_makes_id_unknowable(self) -> None:
        store, game_id = fresh()
        store.forget(game_id)
        with self.assertRaises(GameNotFound):
            store.snapshot(game_id)

    def test_error_message_is_actionable(self) -> None:
        with self.assertRaises(GameNotFound) as ctx:
            GameStore().snapshot("abc")
        self.assertIn("Ván", str(ctx.exception))
        self.assertIn("Ván mới", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
