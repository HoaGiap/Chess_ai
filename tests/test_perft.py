"""Perft: đếm số nước đi hợp lệ ở từng tầng sâu.

Lưu ý: luật do python-chess thực hiện, nên perft chỉ chứng minh phần nối
của ta đúng (đếm ply, áp nước, gọi đúng API) — KHÔNG chứng minh luật FIDE
đúng. Giá trị thật của test nằm ở các task sau.
"""

import unittest

import chess

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
KIWIPETE = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
PAWNS = "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"
PROMOTION = "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1"


def perft(board: chess.Board, depth: int) -> int:
    """Số nước đi hợp lệ ở độ sâu `depth`, tính từ thế cờ hiện tại."""
    if depth == 0:
        return 1
    total = 0
    for move in board.legal_moves:
        board.push(move)
        total += perft(board, depth - 1)
        board.pop()
    return total


class TestPerft(unittest.TestCase):
    def _check(self, fen: str, depth: int, expected: int) -> None:
        board = chess.Board(fen)
        self.assertEqual(perft(board, depth), expected, f"{fen} depth={depth}")

    def test_start_position(self) -> None:
        for depth, expected in ((1, 20), (2, 400), (3, 8902), (4, 197281)):
            with self.subTest(depth=depth):
                self._check(START, depth, expected)

    def test_kiwipete_castling_and_pins(self) -> None:
        for depth, expected in ((1, 48), (2, 2039), (3, 97862)):
            with self.subTest(depth=depth):
                self._check(KIWIPETE, depth, expected)

    def test_rook_pawn_endgame_en_passant(self) -> None:
        for depth, expected in ((1, 14), (2, 191), (3, 2812)):
            with self.subTest(depth=depth):
                self._check(PAWNS, depth, expected)

    def test_promotion_with_castling_rights(self) -> None:
        for depth, expected in ((1, 6), (2, 264), (3, 9467)):
            with self.subTest(depth=depth):
                self._check(PROMOTION, depth, expected)
