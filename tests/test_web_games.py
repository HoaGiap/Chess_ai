import threading
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

    def test_promotion_option_names_the_piece_to_promote_to(self) -> None:
        """Review #1: phải biết quân nào, không chỉ biết CÓ phong cấp.

        Trình duyệt từng lấy ký tự cuối của SAN để đoán quân. SAN của một nước
        phong cấp kèm chiếu có đuôi `+` (g8=Q+), nên ký tự cuối là `+`, không
        phải tên quân — bấm nút Q/R sẽ gửi san=undefined và hỏng.
        """
        store, game_id = fresh("7k/6P1/8/8/8/8/8/4K3 w - - 0 1")
        options = [m for m in store.snapshot(game_id).legal if m.to_sq == "g8"]
        self.assertEqual({m.promotion for m in options}, {"Q", "R", "B", "N"})
        # Khoá lại bằng chứng của cái bẫy: ở thế này phải CÓ nước mà ký tự
        # cuối của SAN khác tên quân. Nếu sau này SAN không còn đuôi `+` thì
        # assertion này đỏ và buộc phải cân nhắc lại, chứ im lặng cho phép ai
        # đó quay lại dùng san.slice(-1).
        self.assertTrue(
            any(m.san[-1] != m.promotion for m in options),
            "thế này không còn chứng minh được cái bẫy san.slice(-1)",
        )

    def test_promotion_letter_is_stable_regardless_of_check(self) -> None:
        store, game_id = fresh("7k/6P1/8/8/8/8/8/4K3 w - - 0 1")
        options = [m for m in store.snapshot(game_id).legal if m.to_sq == "g8"]
        by_letter = {m.promotion: m.san for m in options}
        self.assertEqual(by_letter["Q"], "g8=Q+")   # có chiếu
        self.assertEqual(by_letter["B"], "g8=B")    # không chiếu
        self.assertEqual(by_letter["N"], "g8=N")

    def test_non_promotion_has_no_piece_letter(self) -> None:
        store, game_id = fresh()
        for option in store.snapshot(game_id).legal:
            self.assertIsNone(option.promotion, option.san)

    def test_check_square_names_the_king_in_check(self) -> None:
        """Review 1a: trình duyệt không được tự suy ra vua nào bị chiếu."""
        store, game_id = fresh("4k3/8/8/8/8/8/4r3/4K3 w - - 0 1")
        self.assertEqual(store.snapshot(game_id).check_square, "e1")

    def test_no_check_means_no_check_square(self) -> None:
        store, game_id = fresh()
        self.assertIsNone(store.snapshot(game_id).check_square)

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


class TestOver(unittest.TestCase):
    """Review: `over` và `result_text` chưa từng được assert là đúng.

    Hai field này đóng băng bàn cờ và sinh dòng kết quả ở trình duyệt, nên sai
    thì toàn bộ UX 'hết ván' hỏng mà không test nào đỏ.
    """

    def _play(self, sans: tuple[str, ...]) -> tuple[GameStore, str, object]:
        store, game_id = fresh()
        for san in sans:
            store.submit(game_id, san)
        return store, game_id, store.snapshot(game_id)

    def test_mate_sets_over_and_names_checkmate(self) -> None:
        _, _, state = self._play(("f3", "e5", "g4", "Qh4#"))
        self.assertTrue(state.over)
        self.assertIn("chiếu hết", state.result_text)
        self.assertEqual(state.legal, [])
        self.assertFalse(state.can_undo is False and state.moves == [])

    def test_stalemate_sets_over_and_names_stalemate(self) -> None:
        store, game_id = fresh("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
        state = store.snapshot(game_id)
        self.assertTrue(state.over)
        self.assertIn("bế tắc", state.result_text)

    def test_declared_draw_sets_over_and_names_draw(self) -> None:
        store, game_id = fresh()
        store.session(game_id).agree_draw()
        state = store.snapshot(game_id)
        self.assertTrue(state.over)
        self.assertIn("HÒA", state.result_text)

    def test_moving_after_the_end_is_refused(self) -> None:
        store, game_id, _ = self._play(("f3", "e5", "g4", "Qh4#"))
        with self.assertRaises(MoveError):
            store.submit(game_id, "Nf3")

    def test_new_game_clears_a_finished_game(self) -> None:
        store, game_id, state = self._play(("f3", "e5", "g4", "Qh4#"))
        self.assertTrue(state.over)
        after = store.new_game(game_id)
        self.assertFalse(after.over)
        self.assertEqual(after.moves, [])


class TestNewGameKeepsSession(unittest.TestCase):
    """Review #7: `new_game` tạo Session mới thì mất `on_move` — hook của #3B.

    Sau khi cắm engine, bấm 'Ván mới' sẽ âm thầm mất callback AI.
    """

    def test_new_game_keeps_the_same_session_object(self) -> None:
        store, game_id = fresh()
        before = store.session(game_id)
        before.on_move = lambda san, color: None
        store.new_game(game_id)
        after = store.session(game_id)
        self.assertIs(after, before)
        self.assertIsNotNone(after.on_move)

    def test_new_game_resets_declared_result(self) -> None:
        store, game_id = fresh()
        store.session(game_id).resign(chess.WHITE)
        self.assertTrue(store.snapshot(game_id).over)
        self.assertFalse(store.new_game(game_id).over)

    def test_new_game_keeps_configuration(self) -> None:
        store, game_id = fresh()
        store.session(game_id).elo = 2100
        store.session(game_id).style = "tal"
        store.session(game_id).mode = "play"
        store.new_game(game_id)
        after = store.session(game_id)
        self.assertEqual((after.elo, after.style, after.mode), (2100, "tal", "play"))


class TestCapacity(unittest.TestCase):
    """Review #6: ván tích luỹ vô hạn trong bộ nhớ.

    `POST /api/game` là CORS simple request, nên bất kỳ trang nào cũng POST
    vòng lòng vào được. Phải có trần.
    """

    def test_store_takes_a_capacity(self) -> None:
        self.assertGreater(GameStore(capacity=2).capacity, 0)

    def test_oldest_game_is_forgotten_over_capacity(self) -> None:
        store = GameStore(capacity=2)
        ids = [store.create(None) for _ in range(4)]
        with self.assertRaises(GameNotFound):
            store.snapshot(ids[0])
        store.snapshot(ids[3])   # ván mới nhất vẫn còn

    def test_creating_a_game_makes_room(self) -> None:
        store = GameStore(capacity=1)
        first = store.create(None)
        store.create(None)
        with self.assertRaises(GameNotFound):
            store.snapshot(first)

    def test_default_capacity_is_finite(self) -> None:
        self.assertLess(0, GameStore().capacity < 100_000)


class TestConcurrency(unittest.TestCase):
    """Review #2: `board.san()` tạm ĐẨY rồi LÙI trên Board dùng chung.

    Nên nhánh đọc (`snapshot`, `pgn_text`) cũng phải khoá. Trước khi sửa, một
    writer + vài reader chạy song song làm `san()` gặp nước nửa vời và ném
    AssertionError — HTTP 500 với body không phải JSON.
    """

    def test_reading_during_a_move_never_raises(self) -> None:
        store, game_id = fresh()
        errors: list[BaseException] = []

        def writer() -> None:
            try:
                for san in ("e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "O-O"):
                    store.submit(game_id, san)
            except BaseException as exc:  # noqa: BLE001 - đang đi săn lỗi
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(500):
                    store.snapshot(game_id)
            except BaseException as exc:  # noqa: BLE001 - đang đi săn lỗi
                errors.append(exc)

        threads = [threading.Thread(target=writer)] + [
            threading.Thread(target=reader) for _ in range(3)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual([str(e) for e in errors], [])

    def test_pgn_while_moving_never_raises(self) -> None:
        store, game_id = fresh()
        errors: list[BaseException] = []

        def writer() -> None:
            try:
                for san in ("e4", "e5", "Nf3", "Nc6"):
                    store.submit(game_id, san)
            except BaseException as exc:  # noqa: BLE001 - đang đi săn lỗi
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(300):
                    store.pgn_text(game_id)
            except BaseException as exc:  # noqa: BLE001 - đang đi săn lỗi
                errors.append(exc)

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual([str(e) for e in errors], [])

class TestBaoVeAI(unittest.TestCase):
    """Test TRỰC TIẾP cho lớp bảo vệ của đặc tả §4.1.

    Trước đây các hàm này chỉ được cover gián tiếp qua AIController, mà
    controller dùng engine giả — nên chính lớp chặn nước sai thì chưa từng
    được gọi với nước thật.
    """

    def _game(self, fen: str | None = None) -> tuple[GameStore, str]:
        store = GameStore()
        game_id = store.create(chess.WHITE)
        if fen is not None:
            store.set_fen(game_id, fen)
        return store, game_id

    def test_fen_khop_thi_ap_duoc(self) -> None:
        store, game_id = self._game()
        store.submit(game_id, "e4")
        fen = store.fen_of(game_id)
        nuoc = chess.Move.from_uci("e7e5")
        self.assertTrue(store.commit_ai_move(game_id, fen, nuoc))
        self.assertEqual(store.snapshot(game_id).moves, ["e4", "e5"])

    def test_fen_khac_thi_khong_ap(self) -> None:
        store, game_id = self._game()
        store.submit(game_id, "e4")
        self.assertFalse(
            store.commit_ai_move(game_id, "ban sai", chess.Move.from_uci("e7e5"))
        )
        self.assertEqual(store.snapshot(game_id).moves, ["e4"])

    def test_den_luot_nguoi_thi_khong_ap(self) -> None:
        """Một lớp bảo vệ nữa: máy chỉ được đi khi CHƯA tới lượt người."""
        store = GameStore()
        game_id = store.create(chess.WHITE)
        fen = store.fen_of(game_id)          # vừa tạo, lượt là của người
        self.assertFalse(
            store.commit_ai_move(game_id, fen, chess.Move.from_uci("e2e4"))
        )
        self.assertEqual(store.snapshot(game_id).moves, [])

    def test_van_xong_thi_khong_ap(self) -> None:
        # Ván hai bên: không có ràng buộc lượt, để dựng nhanh thế chiếu hết.
        store = GameStore()
        game_id = store.create(None)
        for nuoc in ("f3", "e5", "g4", "Qh4#"):
            store.submit(game_id, nuoc)
        self.assertTrue(store.snapshot(game_id).over)
        self.assertFalse(
            store.commit_ai_move(
                game_id, store.fen_of(game_id), chess.Move.from_uci("d1d2")
            )
        )

    def test_fen_now_khong_lay_khoa(self) -> None:
        """`fen_now` dùng BÊN TRONG khoá ván — phải đọc được chứ không treo."""
        store, game_id = self._game()
        done = threading.Event()

        def doc():
            store.fen_now(game_id)
            done.set()

        t = threading.Thread(target=doc)
        t.start()
        self.assertTrue(done.wait(timeout=2.0))

    def test_fen_now_va_fen_of_cho_cung_ket_qua(self) -> None:
        store, game_id = self._game()
        store.submit(game_id, "d4")
        self.assertEqual(store.fen_of(game_id), store.fen_now(game_id))

    def test_set_thinking_phai_la_co_hoi_thi(self) -> None:
        store, game_id = self._game()
        self.assertFalse(store.snapshot(game_id).thinking)
        store.set_thinking(game_id, True)
        self.assertTrue(store.snapshot(game_id).thinking)
        store.set_thinking(game_id, False)
        self.assertFalse(store.snapshot(game_id).thinking)

    def test_van_moi_xoa_thong_bao_nghi(self) -> None:
        store, game_id = self._game()
        store.set_thinking(game_id, True)
        store.new_game(game_id)
        self.assertFalse(store.snapshot(game_id).thinking)


if __name__ == "__main__":
    unittest.main()
