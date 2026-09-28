import unittest

import chess

from chessai.render import GLYPHS, render

START = chess.STARTING_FEN

# Hai FEN này đã kiểm chứng bằng python-chess.
AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
AFTER_E4_E5 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"

# Bàn cờ có đường kẻ sau MỌI hàng, nên 19 dòng: 1 nhãn + 8x(hàng + kẻ) + 1 nhãn.
WHITE_VIEW = """\
    a   b   c   d   e   f   g   h
  +---+---+---+---+---+---+---+---+
8 | ♜ | ♞ | ♝ | ♛ | ♚ | ♝ | ♞ | ♜ | 8
  +---+---+---+---+---+---+---+---+
7 | ♟ | ♟ | ♟ | ♟ | ♟ | ♟ | ♟ | ♟ | 7
  +---+---+---+---+---+---+---+---+
6 | . | . | . | . | . | . | . | . | 6
  +---+---+---+---+---+---+---+---+
5 | . | . | . | . | . | . | . | . | 5
  +---+---+---+---+---+---+---+---+
4 | . | . | . | . | . | . | . | . | 4
  +---+---+---+---+---+---+---+---+
3 | . | . | . | . | . | . | . | . | 3
  +---+---+---+---+---+---+---+---+
2 | ♙ | ♙ | ♙ | ♙ | ♙ | ♙ | ♙ | ♙ | 2
  +---+---+---+---+---+---+---+---+
1 | ♖ | ♘ | ♗ | ♕ | ♔ | ♗ | ♘ | ♖ | 1
  +---+---+---+---+---+---+---+---+
    a   b   c   d   e   f   g   h"""

# Góc nhìn Đen: hàng 1 ở trên, đọc từ h về a. Nên hàng 8 là
# h8..a8 = ♜ ♞ ♝ ♚ ♛ ♝ ♞ ♜ — vua (e8) đứng TRƯỚC hậu (d8).
BLACK_VIEW = """\
    h   g   f   e   d   c   b   a
  +---+---+---+---+---+---+---+---+
1 | ♖ | ♘ | ♗ | ♔ | ♕ | ♗ | ♘ | ♖ | 1
  +---+---+---+---+---+---+---+---+
2 | ♙ | ♙ | ♙ | ♙ | ♙ | ♙ | ♙ | ♙ | 2
  +---+---+---+---+---+---+---+---+
3 | . | . | . | . | . | . | . | . | 3
  +---+---+---+---+---+---+---+---+
4 | . | . | . | . | . | . | . | . | 4
  +---+---+---+---+---+---+---+---+
5 | . | . | . | . | . | . | . | . | 5
  +---+---+---+---+---+---+---+---+
6 | . | . | . | . | . | . | . | . | 6
  +---+---+---+---+---+---+---+---+
7 | ♟ | ♟ | ♟ | ♟ | ♟ | ♟ | ♟ | ♟ | 7
  +---+---+---+---+---+---+---+---+
8 | ♜ | ♞ | ♝ | ♚ | ♛ | ♝ | ♞ | ♜ | 8
  +---+---+---+---+---+---+---+---+
    h   g   f   e   d   c   b   a"""

_BORDER_LINE = "  +---+---+---+---+---+---+---+---+"


class TestRender(unittest.TestCase):
    def test_start_position_white_view(self) -> None:
        self.assertEqual(render(chess.Board(START), chess.WHITE), WHITE_VIEW)

    def test_start_position_black_view(self) -> None:
        self.assertEqual(render(chess.Board(START), chess.BLACK), BLACK_VIEW)

    def test_views_are_mirror_images(self) -> None:
        """Hai hướng phải ảnh phản chiếu nhau: cùng số dòng, cột đảo chiều."""
        board = chess.Board(START)
        white = render(board, chess.WHITE).splitlines()
        black = render(board, chess.BLACK).splitlines()
        self.assertEqual(len(white), len(black))
        self.assertEqual(white[0].split(), black[0].split()[::-1])

    def test_border_after_every_rank(self) -> None:
        """Kẻ phải xuất hiện sau MỌI hàng, không chỉ hai đầu."""
        lines = render(chess.Board(START), chess.WHITE).splitlines()
        self.assertEqual(len(lines), 19)
        for index in (1, 3, 5, 7, 9, 11, 13, 15, 17):
            self.assertEqual(lines[index], _BORDER_LINE, f"dòng {index}")

    def test_midgame_position(self) -> None:
        out = render(chess.Board(AFTER_E4), chess.WHITE).splitlines()
        self.assertIn("4 | . | . | . | . | ♙ | . | . | . | 4", out)
        self.assertIn("5 | . | . | . | . | . | . | . | . | 5", out)

    def test_black_view_puts_rank_one_on_top(self) -> None:
        out = render(chess.Board(AFTER_E4_E5), chess.BLACK).splitlines()
        self.assertTrue(out[2].startswith("1 |"), out[2])
        self.assertTrue(out[16].startswith("8 |"), out[16])

    def test_board_uses_only_layout_characters(self) -> None:
        """Bàn cờ trần: chỉ ký tự quân, ô trống và khung — không ký hiệu +/# của SAN."""
        allowed = set(".|+- \n\t") | set("12345678") | set("abcdefgh") | set(GLYPHS.values())
        for board in (chess.Board(START), chess.Board(AFTER_E4)):
            out = render(board, chess.WHITE)
            self.assertEqual({c for c in out if c not in allowed}, set())
