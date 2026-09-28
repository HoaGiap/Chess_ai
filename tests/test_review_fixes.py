"""Test cho cac fix sau final review. Moi fix co test RED truoc khi sua code."""

import io
import os
import unittest
from contextlib import redirect_stdout

import chess

from chessai import cli
from chessai.position import MoveError, Position
from chessai.session import Session

# FEN dung chung
IN_CHECK = "4k3/8/8/8/8/8/4r3/4K3 w - - 0 1"
CASTLE_READY = "4k3/8/8/8/8/8/8/4K2R w K - 0 1"
PROMOTION_READY = "8/P6k/8/8/8/8/8/K7 w - - 0 1"


def err(fen: str, san: str) -> str:
    try:
        Position(fen).apply_san(san)
    except MoveError as exc:
        return str(exc)
    raise AssertionError(f"{san!r} phai bi tu choi o {fen}")


class TestCritical1_ErrorsAreActuallyTranslated(unittest.TestCase):
    """C1: loi illegal phai la tieng Viet, khong loay chuoi thu vien hay FEN."""

    def test_no_library_string_or_fen_leaks(self) -> None:
        for fen, san in (
            (IN_CHECK, "Kd2"),
            ("4k3/8/8/8/8/3P4/8/3RK3 w - - 0 1", "Rxd3"),
            (PROMOTION_READY, "a8"),
        ):
            with self.subTest(san=san):
                message = err(fen, san)
                self.assertNotIn("illegal san", message)
                self.assertNotIn(" in ", message)
                self.assertNotIn("/", message)

    def test_king_into_check_names_the_square(self) -> None:
        message = err(IN_CHECK, "Kd2")
        self.assertIn("d2", message)
        self.assertIn("chiếu", message)

    def test_capturing_own_piece_names_square_and_piece(self) -> None:
        # Xe d1, đường d2 trống, nhưng d3 do TỐT CỦA BẠN đứng.
        message = err("4k3/8/8/8/8/3P4/8/3RK3 w - - 0 1", "Rxd3")
        self.assertIn("d3", message)
        self.assertIn("tốt", message)

    def test_pawn_on_last_rank_without_piece_is_explained(self) -> None:
        message = err(PROMOTION_READY, "a8")
        self.assertIn("phong cấp", message)
        self.assertIn("a8=Q", message)

    def test_missing_piece_names_square(self) -> None:
        message = err(chess.STARTING_FEN, "Nzz3")
        self.assertIn("3", message)

    def test_knight_really_is_absent_message_is_specific(self) -> None:
        message = err(chess.STARTING_FEN, "Na6")
        self.assertNotIn("illegal san", message)


class TestImportant2_CastlingNamesTheRightSquare(unittest.TestCase):
    """I2: is_attacked_by phai hoi doi thu, va phai goi ten o that su bi chan."""

    def _blocker(self, fen: str, san: str) -> str:
        from chessai.position import _castling_blocker

        return _castling_blocker(chess.Board(fen), san)

    def test_transit_square_named_not_home_square(self) -> None:
        message = self._blocker("4k3/5r2/8/8/8/8/8/4K2R w K - 0 1", "O-O")
        self.assertIn("f1", message)
        self.assertNotIn("ô e1 ", message)

    def test_destination_square_named(self) -> None:
        # Qg7 đe dọa g-file nên g1 bị chiếu, còn e1/f1 thì không.
        message = self._blocker("4k3/8/6q1/8/8/8/8/4K2R w K - 0 1", "O-O")
        self.assertIn("g1", message)
        self.assertNotIn("ô e1 ", message)

    def test_queenside_transit_named_for_black(self) -> None:
        # Rf7 đe dọa f8 — ô vua đen phải đi qua khi nhập thành ngắn.
        # Quyền của phe Đen viết THƯỜNG: 'k', không phải 'K'.
        message = self._blocker("r3k2r/5R2/8/8/8/8/8/4K3 b k - 0 1", "O-O")
        self.assertIn("f8", message)

    def test_king_genuinely_in_check_still_reported(self) -> None:
        message = self._blocker("4k3/8/8/8/8/8/4r3/4K2R w K - 0 1", "O-O")
        self.assertIn("e1", message)

    def test_existing_castling_test_is_strengthened(self) -> None:
        """Test cũ chỉ assert khoảng trắng nên pass dù code hỏng — phải nói tên ô."""
        message = err("4k3/5r2/8/8/8/8/8/4K2R w K - 0 1", "O-O")
        self.assertIn("f1", message)

    def test_king_in_check_names_the_king_square(self) -> None:
        """Khi chính vua đang bị chiếu thì e1 mới là câu trả lời đúng."""
        message = err("4k3/8/8/8/8/8/4r3/4K2R w K - 0 1", "O-O")
        self.assertIn("e1", message)


class TestImportant3_BlameNotPinnedToKing(unittest.TestCase):
    def _message_after(self, sans: tuple[str, ...]) -> str:
        pos = Position(CASTLE_READY)
        for san in sans:
            pos.apply_san(san)
        try:
            pos.apply_san("O-O")
        except MoveError as exc:
            return str(exc)
        raise AssertionError("O-O phai bi tu choi sau khi mất quyền nhập thành")

    def test_rook_moved_does_not_blame_king(self) -> None:
        """Chỉ XE đã đi và quay lại; không được quy hết cho vua.

        `castling_rights` là bitboard ô XE nên không phân biệt được nguyên nhân,
        nên thông điệp phải nêu cả hai khả năng thay vì khẳng định là vua.
        """
        message = self._message_after(("Rh2", "Kd7", "Rh1", "Ke8"))
        self.assertIn("vua", message)
        self.assertIn("xe", message)
        self.assertIn("quyền nhập thành", message)

    def test_king_moved_still_mentions_king(self) -> None:
        message = self._message_after(("Kd2", "Ke7", "Ke1", "Ke8"))
        self.assertIn("quyền nhập thành", message)


class TestRegradedMinor_QueensideNeedsRookNotBishop(unittest.TestCase):
    def test_queenside_missing_rook_says_rook(self) -> None:
        message = err("4k3/8/8/8/8/8/8/4K2N w Q - 0 1", "O-O-O")
        self.assertIn("xe", message)
        self.assertNotIn("tượng", message)

    def test_kingside_missing_rook_says_rook(self) -> None:
        self.assertIn("xe", err("4k3/8/8/8/8/8/8/4K2N w K - 0 1", "O-O"))


class TestImportant4_QuitWithArguments(unittest.TestCase):
    def test_dispatch_quit_with_args_still_raises_quit(self) -> None:
        with self.assertRaises(cli.Quit):
            cli._dispatch(Session(human_color=None), "/quit now")

    def test_main_returns_zero_when_quit_has_arguments(self) -> None:
        import sys

        stdin = sys.stdin
        sys.stdin = io.StringIO("/quit now\n")
        try:
            with redirect_stdout(io.StringIO()):
                code = cli.main(["--both"])
        finally:
            sys.stdin = stdin
        self.assertEqual(code, 0)

    def test_main_returns_zero_on_plain_quit(self) -> None:
        import sys

        stdin = sys.stdin
        sys.stdin = io.StringIO("/quit\n")
        try:
            with redirect_stdout(io.StringIO()):
                code = cli.main(["--both"])
        finally:
            sys.stdin = stdin
        self.assertEqual(code, 0)


class TestImportant5_NonUtf8Console(unittest.TestCase):
    def test_main_survives_a_console_that_cannot_encode_unicode(self) -> None:
        import sys

        class LegacyConsole(io.StringIO):
            """Console kiểu cp1252: không mã hóa được ♔ hay tiếng Việt có dấu."""

            encoding = "cp1252"

            def write(self, text: str) -> int:  # noqa: D102
                text.encode(self.encoding)
                return len(text)

            def reconfigure(self, *, encoding=None, errors=None):
                self.encoding = encoding or self.encoding
                return self

        original = sys.stdout
        sys.stdout = LegacyConsole()
        stdin = sys.stdin
        sys.stdin = io.StringIO("/quit\n")
        try:
            code = cli.main(["--both"])
        finally:
            sys.stdout = original
            sys.stdin = stdin
        self.assertEqual(code, 0)

    def test_reconfigure_is_safe_when_stdout_has_no_reconfigure(self) -> None:
        class Bare:
            pass

        cli._force_utf8_stdout(Bare())  # phai khong nem


class TestImportant6_PgnRecordsResult(unittest.TestCase):
    def _finished(self) -> Session:
        s = Session(human_color=None)
        for san in ["f3", "e5", "g4", "Qh4"]:
            s.apply_san(san)
        return s

    def test_pgn_result_after_checkmate(self) -> None:
        self.assertIn('[Result "0-1"]', self._finished().pgn())

    def test_pgn_result_after_white_resigns(self) -> None:
        # TRẮNG đầu hàng thì ĐEN thắng.
        s = Session(human_color=chess.WHITE)
        s.resign(chess.WHITE)
        self.assertIn('[Result "0-1"]', s.pgn())

    def test_pgn_result_after_black_resigns(self) -> None:
        s = Session(human_color=chess.WHITE)
        s.resign(chess.BLACK)
        self.assertIn('[Result "1-0"]', s.pgn())

    def test_pgn_result_after_draw(self) -> None:
        s = Session(human_color=chess.WHITE)
        s.agree_draw()
        self.assertIn('[Result "1/2-1/2"]', s.pgn())

    def test_pgn_result_after_stalemate(self) -> None:
        s = Session(human_color=None)
        s.position = Position("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
        self.assertIn('[Result "1/2-1/2"]', s.pgn())

    def test_pgn_result_stays_unfinished_while_playing(self) -> None:
        s = Session(human_color=None)
        s.apply_san("e4")
        self.assertIn('[Result "*"]', s.pgn())

    def test_old_test_asserting_asterisk_for_finished_game_is_wrong(self) -> None:
        """Khong con game nao ket thuc ma PGN van ghi Result '*'."""
        self.assertNotIn('[Result "*"]', self._finished().pgn())


class TestImportant7_DefaultRunIsNotADeadEnd(unittest.TestCase):
    def test_help_mentions_both_mode(self) -> None:
        self.assertIn("--both", cli._HELP)

    def test_banner_mentions_both_mode(self) -> None:
        """main() phải in ra lời nhắc --both trước khi người dùng gặp bức tường."""
        import sys

        stdin = sys.stdin
        sys.stdin = io.StringIO("/quit\n")
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                cli.main([])
        finally:
            sys.stdin = stdin
        self.assertIn("--both", buf.getvalue())

    def test_not_your_turn_message_points_at_both_mode(self) -> None:
        s = Session(human_color=chess.WHITE)
        s.apply_san("e4")
        with self.assertRaises(MoveError) as ctx:
            s.apply_san("e5")
        self.assertIn("--both", str(ctx.exception))

    def test_startup_warning_when_no_opponent_exists(self) -> None:
        self.assertIn("--both", cli._startup_note(chess.WHITE))
        self.assertEqual(cli._startup_note(None), "")


class TestImportant8_MoveHookIsUsableBySubProject2(unittest.TestCase):
    def test_hook_receives_canonical_san_not_raw_text(self) -> None:
        s = Session(human_color=None)
        seen: list[tuple[str, chess.Color]] = []
        s.on_move = lambda san, color: seen.append((san, color))
        s.apply_san("e4+")  # người dùng gõ thừa dấu +
        self.assertEqual(seen, [("e4", chess.WHITE)])

    def test_hook_receives_the_colour_that_moved(self) -> None:
        s = Session(human_color=None)
        seen: list[tuple[str, chess.Color]] = []
        s.on_move = lambda san, color: seen.append((san, color))
        s.apply_san("e4")
        s.apply_san("e5")
        self.assertEqual(seen, [("e4", chess.WHITE), ("e5", chess.BLACK)])

    def test_hook_failure_is_reported_not_raised(self) -> None:
        s = Session(human_color=None)

        def boom(san: str, color: chess.Color) -> None:
            raise RuntimeError("engine lỗi")

        s.on_move = boom
        with self.assertRaises(MoveError) as ctx:
            s.apply_san("e4")
        self.assertIn("engine", str(ctx.exception))

    def test_hook_failure_does_not_corrupt_the_position(self) -> None:
        """Lượt đã đi xong thì ván vẫn phải đúng, chỉ báo lỗi ra ngoài."""
        s = Session(human_color=None)

        def boom(san: str, color: chess.Color) -> None:
            raise RuntimeError("x")

        s.on_move = boom
        with self.assertRaises(MoveError):
            s.apply_san("e4")
        self.assertEqual(s.position.ply_count(), 1)
        expected = Position(chess.STARTING_FEN)
        expected.apply_san("e4")
        self.assertEqual(s.position.fen(), expected.fen())


if __name__ == "__main__":
    unittest.main()


class TestBug1_OnlyKingIsForbiddenFromAttackedSquares(unittest.TestCase):
    """Chỉ VUA bị cấm đi vào ô bị chiếu. Xe/ma/tuong/hau/tot deu duoc."""

    def test_rook_capturing_empty_attacked_square(self) -> None:
        """"Rxd5" bi tu choi vi d5 TRONG — khong phai vi d5 bi chieu."""
        message = err("4k3/8/2b5/8/8/8/8/R3K3 w - - 0 1", "Rxd5")
        self.assertNotIn("bị chiếu", message)
        self.assertIn("d5", message)
        self.assertIn("trống", message)

    def test_pawn_blocked_by_enemy_pawn(self) -> None:
        """Tot khong bat duoc thang phia truoc."""
        message = err("4k3/8/8/3b4/4p3/4P3/8/4K3 w - - 0 1", "e4")
        self.assertNotIn("bị chiếu", message)
        self.assertIn("e4", message)
        self.assertIn("phía trước", message)

    def test_king_into_attacked_square_still_explained(self) -> None:
        message = err(IN_CHECK, "Kd2")
        self.assertIn("bị chiếu", message)
        self.assertIn("d2", message)

    def test_rook_may_legally_move_to_an_attacked_square(self) -> None:
        """Luật cờ vua: chỉ VUA bị cấm đi vào ô bị chiếu. Xe thì được.

        Xe d1 lên d5 là nước hợp lệ dù Tượng c6 đang nhắm d5.
        """
        pos = Position("4k3/8/2b5/8/8/8/8/3RK3 w - - 0 1")
        pos.apply_san("Rd5")
        self.assertEqual(pos.board.piece_at(chess.D5).piece_type, chess.ROOK)


class TestBug2_1_CastlingBlockedByEnemyPiece(unittest.TestCase):
    def test_enemy_piece_on_castling_path_named(self) -> None:
        message = err("4k3/8/8/8/8/8/8/R2bK2R w KQ - 0 1", "O-O-O")
        self.assertIn("d1", message)
        self.assertIn("đối thủ", message)

    def test_own_piece_still_says_cua_ban(self) -> None:
        message = err("4k3/8/8/8/8/8/8/R3KB1R w KQ - 0 1", "O-O")
        self.assertIn("f1", message)
        self.assertIn("của bạn", message)


class TestBug2_2_EnPassantHintOnlyForPawns(unittest.TestCase):
    QUEEN_ONLY = "4k3/8/8/8/8/8/8/4K2Q w - - 0 1"

    def test_queen_capture_gets_no_en_passant_hint(self) -> None:
        message = err(self.QUEEN_ONLY, "Qxd6")
        self.assertNotIn("Bắt tốt qua đường", message)

    def test_rook_capture_gets_no_en_passant_hint(self) -> None:
        message = err("4k3/8/8/8/8/8/8/4KR2 w - - 0 1", "Rxd6")
        self.assertNotIn("Bắt tốt qua đường", message)

    def test_bishop_capture_gets_no_en_passant_hint(self) -> None:
        message = err("4k3/8/8/8/8/8/8/2B1K3 w - - 0 1", "Bxd6")
        self.assertNotIn("Bắt tốt qua đường", message)

    def test_pawn_capture_still_gets_en_passant_hint(self) -> None:
        message = err("4k3/8/8/3pP3/8/8/8/4K3 w - - 0 1", "exd6")
        self.assertIn("Bắt tốt qua đường", message)

    def test_pawn_capture_on_wrong_rank_gets_no_hint(self) -> None:
        message = err(chess.STARTING_FEN, "exd3")
        self.assertNotIn("Bắt tốt qua đường", message)


class TestBug2_3_UnresolvedCheckExplained(unittest.TestCase):
    IN_CHECK_BY_BISHOP = "4k3/8/8/8/8/8/3b4/4K1N1 w - - 0 1"

    def test_moving_other_piece_while_in_check(self) -> None:
        message = err(self.IN_CHECK_BY_BISHOP, "Nf3")
        self.assertIn("đang bị chiếu", message)
        self.assertIn("che chắn", message)

    def test_own_piece_reason_still_wins(self) -> None:
        # Vua e1 đang bị xe e8 chiếu, nhưng lý do cụ thể hơn là a2 có tốt CỦA BẠN.
        message = err("4r3/8/8/8/8/8/P7/R3K3 w - - 0 1", "Rxa2")
        self.assertIn("CỦA BẠN", message)


class TestBug3_UndoRedrawsBoard(unittest.TestCase):
    def test_undo_returns_the_board(self) -> None:
        s = Session(human_color=None)
        s.apply_san("e4")
        out = cli._dispatch(s, "/undo")
        self.assertIn("Đã lùi", out)
        self.assertIn("♔", out)
        self.assertIn("+---", out)
