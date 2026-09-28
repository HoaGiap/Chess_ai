"""Vẽ bàn cờ Unicode.

Hàm thuần: nhận board + hướng nhìn, trả về chuỗi. Không đọc biến toàn cục,
không giữ trạng thái — nên test được bằng so khớp chuỗi, không cần dựng ván.
"""

from __future__ import annotations

import chess

GLYPHS: dict[tuple[chess.PieceType, chess.Color], str] = {
    (chess.KING, chess.WHITE): "♔",
    (chess.KING, chess.BLACK): "♚",
    (chess.QUEEN, chess.WHITE): "♕",
    (chess.QUEEN, chess.BLACK): "♛",
    (chess.ROOK, chess.WHITE): "♖",
    (chess.ROOK, chess.BLACK): "♜",
    (chess.BISHOP, chess.WHITE): "♗",
    (chess.BISHOP, chess.BLACK): "♝",
    (chess.KNIGHT, chess.WHITE): "♘",
    (chess.KNIGHT, chess.BLACK): "♞",
    (chess.PAWN, chess.WHITE): "♙",
    (chess.PAWN, chess.BLACK): "♟",
}

_FILES = "abcdefgh"
_BORDER = "  +" + "---+" * 8


def render(board: chess.Board, perspective: chess.Color) -> str:
    """Trả về bàn cờ 8x8 nhìn từ phía `perspective` (quân ấy nằm ở dưới)."""
    ranks = range(7, -1, -1) if perspective == chess.WHITE else range(8)
    files = range(8) if perspective == chess.WHITE else range(7, -1, -1)
    header = "    " + "   ".join(_FILES[f] for f in files)

    lines = [header, _BORDER]
    for rank in ranks:
        cells = []
        for f in files:
            piece = board.piece_at(chess.square(f, rank))
            cells.append(GLYPHS[(piece.piece_type, piece.color)] if piece else ".")
        label = str(rank + 1)
        lines.append(f"{label} | " + " | ".join(cells) + f" | {label}")
        lines.append(_BORDER)
    lines.append(header)
    return "\n".join(lines)
