"""Engine cờ vua tự viết: negamax + alpha-beta.

Không dùng `chess.engine` vì module đó chỉ là cầu nối tới một binary UCI bên
ngoài (Stockfish, lc0...), mà máy này không có và dự án không thêm gói.

Bảng điểm vị trí lấy nguyên văn từ bài "Simplified Evaluation Function" của
Tomasz Michniewski, phổ biến trong sách về lập trình cờ vua (Steven Edwards,
`C++ Chess Programming Cookbook`). Được dùng để học, phát hành cùng mã nguồn.
"""

from __future__ import annotations

import chess

# Đơn vị: centipawn. Vua có giá trị rất lớn để không bao giờ bị đổi — người
# chơi không thể ăn vua, nên điểm này chỉ để giữ số lớn không bị "xổ vỡ".
VALUES: dict[int, int] = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20_000,
}

# Bảng viết theo góc nhìn phe TRẮNG, chỉ số 0 = a8, 63 = h1. Vì vậy tốt càng
# đi lên (chỉ số càng nhỏ) càng tốt, và bảng của phe ĐEN lấy đảo chiều.
PST: dict[str, list[int]] = {
    "P": [
        0, 0, 0, 0, 0, 0, 0, 0,
        50, 50, 50, 50, 50, 50, 50, 50,
        10, 10, 20, 30, 30, 20, 10, 10,
        5, 5, 10, 27, 27, 10, 5, 5,
        0, 0, 0, 25, 25, 0, 0, 0,
        5, -5, -10, 0, 0, -10, -5, 5,
        5, 10, 10, -25, -25, 10, 10, 5,
        0, 0, 0, 0, 0, 0, 0, 0,
    ],
    "N": [
        -50, -40, -30, -30, -30, -30, -40, -50,
        -40, -20, 0, 5, 5, 0, -20, -40,
        -30, 5, 10, 15, 15, 10, 5, -30,
        -30, 0, 15, 20, 20, 15, 0, -30,
        -30, 5, 15, 20, 20, 15, 5, -30,
        -30, 0, 10, 15, 15, 10, 0, -30,
        -40, -20, 0, 0, 0, 0, -20, -40,
        -50, -40, -30, -30, -30, -30, -40, -50,
    ],
    "B": [
        -20, -10, -10, -10, -10, -10, -10, -20,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -10, 0, 5, 10, 10, 5, 0, -10,
        -10, 5, 5, 10, 10, 5, 5, -10,
        -10, 0, 10, 10, 10, 10, 0, -10,
        -10, 10, 10, 10, 10, 10, 10, -10,
        -10, 5, 0, 0, 0, 0, 5, -10,
        -20, -10, -10, -10, -10, -10, -10, -20,
    ],
    "R": [
        0, 0, 0, 0, 0, 0, 0, 0,
        5, 10, 10, 10, 10, 10, 10, 5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        0, 0, 0, 5, 5, 0, 0, 0,
    ],
    "Q": [
        -20, -10, -10, -5, -5, -10, -10, -20,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -10, 0, 5, 5, 5, 5, 0, -10,
        -5, 0, 5, 5, 5, 5, 0, -5,
        0, 0, 5, 5, 5, 5, 0, -5,
        -10, 5, 5, 5, 5, 5, 0, -10,
        -10, 0, 5, 0, 0, 0, 0, -10,
        -20, -10, -10, -5, -5, -10, -10, -20,
    ],
    "K": [
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -20, -30, -30, -40, -40, -30, -30, -20,
        -10, -20, -20, -20, -20, -20, -20, -10,
        20, 20, 0, 0, 0, 0, 20, 20,
        20, 30, 10, 0, 0, 10, 30, 20,
    ],
}


def _table_index(square: chess.Square) -> int:
    """Ô -> chỉ số bảng 0..63, với 0 = a8 và 63 = h1 (ngược với python-chess).

    Chỉ số phải là **hàng trước, cột sau**: hàng 0 là hàng 8. Viết
    `file * 8 + (7 - rank)` sẽ hoán đổi hàng với cột, và bảng sẽ được đọc
    nằm ngang — hàng cột trong bảng thành cột hàng.
    """
    return (7 - chess.square_rank(square)) * 8 + chess.square_file(square)


def _mirror(index: int) -> int:
    """Đảo chỉ số bảng qua đường giữa bàn: hàng 8 <-> hàng 1."""
    return index ^ 56


def piece_square(piece_type: int, color: chess.Color, square: chess.Square) -> int:
    """Điểm vị trí của một quân, luôn viết theo góc nhìn phe TRẮNG.

    Ô là tham số riêng vì `chess.Piece` chỉ giữ loại quân và màu, không giữ ô.
    """
    index = _table_index(square)
    if color == chess.BLACK:
        index = _mirror(index)
    return PST[chess.piece_symbol(piece_type).upper()][index]


def material(board: chess.Board, color: chess.Color) -> int:
    """Tổng giá trị quân của một phe, kể cả vua."""
    return sum(
        VALUES[p.piece_type]
        for p in board.piece_map().values()
        if p.color == color
    )


def min_material(board: chess.Board) -> int:
    """Tổng giá trị quân của phe ÍT quân hơn (bỏ vua: vua không bị ăn)."""
    white = 0
    black = 0
    for p in board.piece_map().values():
        if p.piece_type == chess.KING:
            continue          # vua không bao giờ bị ăn, tính vào sẽ phóng đại thang
        if p.color == chess.WHITE:
            white += VALUES[p.piece_type]
        else:
            black += VALUES[p.piece_type]
    return min(white, black)


def _scale(value: int, num: int, den: int) -> int:
    """Nhân rồi CẮT bỏ phần thập phân, thay vì làm tròn xuống.

    Phải cắt chứ không `//`, vì `//` của số âm làm tròn xuống và phá vỡ đối
    xứng: (-5*5)//10 = -3 trong khi (5*5)//10 = 2. Mà đối xứng chính là thứ
    giữ cho engine không chơi mạnh hơn ở một màu.
    """
    total = value * num
    return total // den if total >= 0 else -((-total) // den)


# Tổng giá trị quân (không tính vua) của MỘT phe lúc khai cuộc:
# 8*100 + 2*320 + 2*330 + 2*500 + 900 = 4000. Dùng làm mốc đo "còn bao nhiêu ván".
_PHASE_FULL = 4_000


def phase(board: chess.Board) -> int:
    """Mức còn quân, 0 (hết ván) .. 10 (khai cuộc)."""
    con_lai = 0
    for piece in board.piece_map().values():
        if piece.piece_type != chess.KING:
            con_lai += VALUES[piece.piece_type]
    return min(10, con_lai * 10 // (2 * _PHASE_FULL))


def evaluate(board: chess.Board) -> int:
    """Điểm tương đối, **theo góc nhìn phe đang đi**.

    Vật chất luôn tính đủ; chỉ phần **vị trí** mờ dần khi bàn trống dần (xuống
    còn 3/10 ở cuối ván). Nếu kéo cả vật chất về 0 thì hết quân là bàn cờ rỗng
    và mọi thế thưa đều ra 0 điểm — máy sẽ đánh cặn mắt.
    """
    van_chat = 0
    vi_tri = 0
    for square, piece in board.piece_map().items():
        gia_tri = piece_square(piece.piece_type, piece.color, square)
        if piece.color == chess.WHITE:
            van_chat += VALUES[piece.piece_type]
            vi_tri += gia_tri
        else:
            van_chat -= VALUES[piece.piece_type]
            vi_tri -= gia_tri
    score = van_chat + _scale(vi_tri, 3 + phase(board), 10)
    return score if board.turn == chess.WHITE else -score
