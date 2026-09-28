import unittest

import chess

from chessai.position import MoveError, Position


def play(fen: str, sans: list[str]) -> Position:
    """Dựng thế cờ từ FEN rồi đi lần lượt các nước đã cho."""
    pos = Position(fen)
    for san in sans:
        pos.apply_san(san)
    return pos


class TestApplySan(unittest.TestCase):
    def test_start_position_fen(self) -> None:
        self.assertEqual(Position().fen(), chess.STARTING_FEN)

    def test_side_to_move(self) -> None:
        pos = Position()
        self.assertEqual(pos.side_to_move, chess.WHITE)
        pos.apply_san("e4")
        self.assertEqual(pos.side_to_move, chess.BLACK)

    def test_apply_san_updates_fen(self) -> None:
        # Ô bắt tốt qua đường là '-' vì không tốt nào bắt được (xem Global Constraints).
        pos = play(chess.STARTING_FEN, ["e4", "e5"])
        self.assertEqual(
            pos.fen(), "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
        )

    def test_legal_sans(self) -> None:
        self.assertEqual(len(Position().legal_sans()), 20)

    def test_san_history(self) -> None:
        pos = play(chess.STARTING_FEN, ["e4", "e5", "Nf3"])
        self.assertEqual(pos.san_history(), ["e4", "e5", "Nf3"])

    def test_san_history_from_custom_fen(self) -> None:
        """Lịch sử phải replay từ FEN gốc, không phải từ vị trí xuất phát."""
        pos = play("4k3/8/8/8/8/8/8/4K2R w K - 0 1", ["O-O", "Kd8"])
        self.assertEqual(pos.san_history(), ["O-O", "Kd8"])

    def test_ply_count(self) -> None:
        self.assertEqual(play(chess.STARTING_FEN, ["e4", "e5"]).ply_count(), 2)


class TestIllegalMoves(unittest.TestCase):
    """Bất biến quan trọng nhất: nước sai KHÔNG được đổi thế cờ một ô nào."""

    def _fen_unchanged(self, pos: Position, san: str) -> None:
        before = pos.fen()
        with self.assertRaises(MoveError):
            pos.apply_san(san)
        self.assertEqual(pos.fen(), before)

    def test_illegal_move_leaves_position_untouched(self) -> None:
        self._fen_unchanged(Position(), "e5")

    def test_pawn_blocked_by_enemy_pawn(self) -> None:
        # Tốt trắng e2, tốt đen e3: e3 và e4 đều bị chặn, exd3 cũng vô lý.
        pos = Position("4k3/8/8/8/4p3/4P3/8/4K3 w - - 0 1")
        for san in ("e3", "e4", "exd3"):
            with self.subTest(san=san):
                self._fen_unchanged(pos, san)

    def test_wrong_side_to_move(self) -> None:
        # Tốt trắng không đi được 2 ô từ hàng 2 lên hàng 7.
        self._fen_unchanged(Position(), "a7")

    def test_garbage_input(self) -> None:
        self._fen_unchanged(Position(), "hello")

    def test_illegal_after_history(self) -> None:
        self._fen_unchanged(play(chess.STARTING_FEN, ["e4"]), "Qh4")

    def test_king_into_check_rejected(self) -> None:
        # Vua e1 đang bị xe e2 chiếu; e1 và d2, f2 đều nằm trên đường chiếu.
        # Mỗi nước dùng một Position riêng, nếu không chúng phá nhau.
        for san in ("Ke1", "Kd2", "Kf2"):
            with self.subTest(san=san):
                self._fen_unchanged(Position("4k3/8/8/8/8/8/4r3/4K3 w - - 0 1"), san)
        # Kf1/Kd1 phải vẫn hợp lệ — nếu "sửa" cho xanh thì hỏng luật.
        for san in ("Kf1", "Kd1"):
            with self.subTest(san=san):
                Position("4k3/8/8/8/8/8/4r3/4K3 w - - 0 1").apply_san(san)

    def test_ambiguous_knight_message(self) -> None:
        pos = Position("4k3/8/8/8/8/8/8/1N1K1N2 w - - 0 1")
        before = pos.fen()
        with self.assertRaises(MoveError) as ctx:
            pos.apply_san("Nd2")
        self.assertIn("Nbd2", str(ctx.exception))
        self.assertEqual(pos.fen(), before)

    def test_garbage_input_suggests_nearby_moves(self) -> None:
        """Input vô nghĩa phải gợi ý nước hợp lệ bắt đầu bằng cùng chữ cái."""
        with self.assertRaises(MoveError) as ctx:
            Position().apply_san("hello")
        message = str(ctx.exception)
        self.assertIn("h3", message)
        self.assertIn("Nước hợp lệ gần nhất", message)

    def test_castling_notation_accepted(self) -> None:
        pos = play("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", ["O-O"])
        self.assertEqual(pos.board.piece_at(chess.G1).piece_type, chess.KING)
        self.assertEqual(pos.board.piece_at(chess.F1).piece_type, chess.ROOK)
        self.assertIsNone(pos.board.piece_at(chess.E1))
        self.assertIsNone(pos.board.piece_at(chess.H1))

    def test_annotation_is_rejected(self) -> None:
        """Review Focus #1: người chơi hay gõ kèm ! / ? / ?! từ bài phân tích."""
        for san in ("e4!", "e4?", "e4!!", "Nf3?!"):
            with self.subTest(san=san):
                self._fen_unchanged(Position(), san)

    def test_stray_check_suffix_is_tolerated(self) -> None:
        """python-chess chấp nhận hậu tố +/# thừa. Ghi lại để không ai tưởng là lỗi."""
        for san in ("e4+", "e4#"):
            with self.subTest(san=san):
                pos = Position()
                pos.apply_san(san)
                self.assertEqual(pos.san_history(), ["e4"])

    def test_promotion_queen(self) -> None:
        pos = play("8/P6k/8/8/8/8/8/K7 w - - 0 1", ["a8=Q"])
        self.assertEqual(pos.board.piece_at(chess.A8).piece_type, chess.QUEEN)

    def test_promotion_knight_bishop_rook(self) -> None:
        """Review Focus #2: phong cấp đủ 4 quân, không chỉ hậu."""
        for san, piece in (
            ("a8=N", chess.KNIGHT),
            ("a8=B", chess.BISHOP),
            ("a8=R", chess.ROOK),
        ):
            with self.subTest(san=san):
                pos = play("8/P6k/8/8/8/8/8/K7 w - - 0 1", [san])
                self.assertEqual(pos.board.piece_at(chess.A8).piece_type, piece)


class TestEnPassant(unittest.TestCase):
    def test_en_passant_capture_legal(self) -> None:
        pos = play(chess.STARTING_FEN, ["e4", "a6", "e5", "d5", "exd6"])
        self.assertEqual(pos.board.piece_at(chess.D6).color, chess.WHITE)
        self.assertIsNone(pos.board.piece_at(chess.D5))

    def test_en_passant_unavailable_gets_hint(self) -> None:
        pos = Position("4k3/8/8/3pP3/8/8/8/4K3 w - - 0 1")
        before = pos.fen()
        with self.assertRaises(MoveError) as ctx:
            pos.apply_san("exd6")
        self.assertIn("2 ô", str(ctx.exception))
        self.assertEqual(pos.fen(), before)

    def test_en_passant_lands_on_rank_six(self) -> None:
        """Review Focus #5: bắt qua đường đưa tốt tới hàng 6, không phải hàng 8."""
        pos = Position("4k3/8/8/Pp6/8/8/8/4K3 w - b6 0 1")
        pos.apply_san("axb6")
        self.assertEqual(pos.board.piece_at(chess.B6).piece_type, chess.PAWN)
        self.assertEqual(pos.board.piece_at(chess.B6).color, chess.WHITE)
        self.assertIsNone(pos.board.piece_at(chess.B5))

    def test_en_passant_promotion_syntax_rejected(self) -> None:
        """Vì đến hàng 6 nên ghi =Q / =N là sai luật, phải báo lỗi chứ không bỏ qua."""
        for san in ("axb6=Q", "axb6=N"):
            with self.subTest(san=san):
                pos = Position("4k3/8/8/Pp6/8/8/8/4K3 w - b6 0 1")
                before = pos.fen()
                with self.assertRaises(MoveError) as ctx:
                    pos.apply_san(san)
                self.assertIn("không hợp lệ", str(ctx.exception))
                self.assertEqual(pos.fen(), before)


class TestCastlingErrors(unittest.TestCase):
    def test_blocked_king_side_castling_reports_square(self) -> None:
        pos = Position("4k3/8/8/8/8/8/8/R3KB1R w KQ - 0 1")
        before = pos.fen()
        with self.assertRaises(MoveError) as ctx:
            pos.apply_san("O-O")
        self.assertIn("f1", str(ctx.exception))
        self.assertEqual(pos.fen(), before)

    def test_blocked_queen_side_castling_reports_square(self) -> None:
        # Hậu d1 chặn đường nhập thành dài; b1/c1 vẫn trống.
        pos = Position("4k3/8/8/8/8/8/8/R2QK2R w KQ - 0 1")
        with self.assertRaises(MoveError) as ctx:
            pos.apply_san("O-O-O")
        self.assertIn("d1", str(ctx.exception))

    def test_missing_rook_reported(self) -> None:
        # FEN hợp lệ: quyền K còn, g1 trống, nhưng không có xe ở h1.
        pos = Position("4k3/8/8/8/8/8/8/4K2N w K - 0 1")
        with self.assertRaises(MoveError) as ctx:
            pos.apply_san("O-O")
        self.assertIn("h1", str(ctx.exception))

    def test_king_returned_to_home_lost_rights(self) -> None:
        """Review Focus #3: vua đi rồi quay lại e1 — quân vẫn ở chỗ, mất quyền."""
        pos = play("4k3/8/8/8/8/8/8/4K2R w K - 0 1", ["Kd2", "Ke7", "Ke1", "Ke8"])
        with self.assertRaises(MoveError) as ctx:
            pos.apply_san("O-O")
        self.assertIn("quyền nhập thành", str(ctx.exception))

    def test_castling_through_attacked_square(self) -> None:
        pos = Position("4k3/8/8/8/8/8/5q2/4K2R w K - 0 1")
        with self.assertRaises(MoveError) as ctx:
            pos.apply_san("O-O")
        self.assertIn("bị tấn công", str(ctx.exception))

    def test_castling_notation_hint_for_king_move(self) -> None:
        pos = Position("4k3/8/8/8/8/8/8/R3K3 w Q - 0 1")
        with self.assertRaises(MoveError) as ctx:
            pos.apply_san("Kg1")
        self.assertIn("O-O", str(ctx.exception))


class TestUndo(unittest.TestCase):
    def test_undo_restores_fen_exactly(self) -> None:
        pos = Position()
        start = pos.fen()
        pos.apply_san("e4")
        pos.apply_san("e5")
        pos.undo()
        pos.undo()
        self.assertEqual(pos.fen(), start)

    def test_undo_restores_ep_and_clocks(self) -> None:
        pos = Position()
        pos.apply_san("e4")
        pos.apply_san("d5")
        target = pos.fen()
        pos.apply_san("exd5")
        pos.undo()
        self.assertEqual(pos.fen(), target)

    def test_undo_on_empty_raises(self) -> None:
        with self.assertRaises(MoveError):
            Position().undo()


class TestGameEnd(unittest.TestCase):
    """Vị trí lặp phải CÓ TỐT, nếu không sẽ dính insufficient_material."""

    def test_checkmate(self) -> None:
        """1. f3 e5 2. g4 Qh4# — thắng thì phải báo thắng, không báo hòa."""
        pos = play(chess.STARTING_FEN, ["f3", "e5", "g4", "Qh4"])
        self.assertTrue(pos.is_game_over())
        self.assertEqual(pos.outcome().termination, chess.Termination.CHECKMATE)
        self.assertEqual(pos.outcome().winner, chess.BLACK)
        self.assertIn("Đen thắng", pos.termination_text())
        self.assertIn("chiếu hết", pos.termination_text())

    def test_stalemate_is_draw_not_checkmate(self) -> None:
        pos = Position("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
        self.assertTrue(pos.is_game_over())
        self.assertEqual(pos.outcome().termination, chess.Termination.STALEMATE)
        self.assertIsNone(pos.outcome().winner)
        self.assertIn("bế tắc", pos.termination_text())

    def test_insufficient_material(self) -> None:
        for fen in (
            "7k/8/8/8/8/8/8/K7 w - - 0 1",
            "7k/8/8/8/8/8/8/K6N w - - 0 1",
            "7k/8/8/8/8/8/8/KB6 w - - 0 1",
        ):
            with self.subTest(fen=fen):
                pos = Position(fen)
                self.assertTrue(pos.is_game_over())
                self.assertEqual(
                    pos.outcome().termination,
                    chess.Termination.INSUFFICIENT_MATERIAL,
                )

    def test_king_bishop_knight_can_still_mate(self) -> None:
        """KBN vẫn chiếu hết được — không được kết luận hòa sớm."""
        pos = Position("7k/8/8/8/8/8/8/KBN5 w - - 0 1")
        self.assertFalse(pos.is_game_over())

    def test_threefold_repetition_ends_game(self) -> None:
        pos = play(
            "4k3/8/8/8/8/8/4P3/4K1N1 w - - 0 1",
            ["Nf3", "Kd7", "Ng1", "Ke8", "Nf3", "Kd7", "Ng1", "Ke8"],
        )
        self.assertTrue(pos.is_game_over())
        self.assertEqual(
            pos.outcome().termination, chess.Termination.THREEFOLD_REPETITION
        )
        self.assertIn("lặp thế cờ 3 lần", pos.termination_text())

    def test_single_repetition_does_not_end_game(self) -> None:
        pos = play("4k3/8/8/8/8/8/4P3/4K1N1 w - - 0 1", ["Nf3", "Kd7", "Ng1", "Ke8"])
        self.assertFalse(pos.is_game_over())
        self.assertIsNone(pos.outcome())

    def test_seventyfive_moves_ends_automatically(self) -> None:
        pos = Position("4k3/8/8/8/8/8/8/4K2R w K - 149 200")
        pos.apply_san("Rh2")
        self.assertTrue(pos.is_game_over())
        self.assertEqual(
            pos.outcome().termination, chess.Termination.SEVENTYFIVE_MOVES
        )
        self.assertIn("75", pos.termination_text())

    def test_fifty_moves_is_only_claimable(self) -> None:
        """Review Focus #4: ở bộ đếm 99 chỉ được BÁO, ván phải đi tiếp."""
        pos = Position("4k3/8/8/8/8/8/8/4K2R w K - 99 100")
        pos.apply_san("Rh2")
        self.assertTrue(pos.can_claim_fifty_moves())
        self.assertFalse(pos.is_game_over())
        self.assertEqual(pos.termination_text(), "ván đang diễn ra")

    def test_termination_text_while_running(self) -> None:
        self.assertEqual(Position().termination_text(), "ván đang diễn ra")

    def test_ongoing_position_has_no_outcome(self) -> None:
        pos = play(chess.STARTING_FEN, ["e4", "e5"])
        self.assertIsNone(pos.outcome())
        self.assertFalse(pos.is_game_over())
