"""Engine cờ vua tự viết: negamax + alpha-beta.

Không dùng `chess.engine` vì module đó chỉ là cầu nối tới một binary UCI bên
ngoài (Stockfish, lc0...), mà máy này không có và dự án không thêm gói.

Bảng điểm vị trí lấy nguyên văn từ bài "Simplified Evaluation Function" của
Tomasz Michniewski, phổ biến trong sách về lập trình cờ vua (Steven Edwards,
`C++ Chess Programming Cookbook`). Được dùng để học, phát hành cùng mã nguồn.
"""

from __future__ import annotations

import random
import time

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


# (elo, max_depth, blunder_rate, slack_cp, max_seconds)
ELO_TABLE: list[tuple[int, int, float, int, float]] = [
    (600, 1, 0.45, 220, 0.4),
    (900, 2, 0.30, 150, 0.8),
    (1200, 3, 0.18, 95, 1.5),
    (1500, 4, 0.10, 60, 2.5),
    (1800, 5, 0.05, 35, 4.0),
    (2100, 6, 0.02, 20, 6.0),
    (2400, 7, 0.00, 0, 9.0),
]

_MATE = 10_000
_INF = 1_000_000


def profile_for(elo: int) -> tuple[int, float, int, float]:
    """(max_depth, blunder_rate, slack_cp, max_seconds) cho một Elo."""
    if elo <= ELO_TABLE[0][0]:
        row = ELO_TABLE[0]
    elif elo >= ELO_TABLE[-1][0]:
        row = ELO_TABLE[-1]
    else:
        row = ELO_TABLE[-1]
        for thap, cao in zip(ELO_TABLE, ELO_TABLE[1:]):
            if thap[0] <= elo <= cao[0]:
                ty_le = (elo - thap[0]) / (cao[0] - thap[0])
                return (
                    int(thap[1] + ty_le * (cao[1] - thap[1]) + 0.5),
                    round(thap[2] + ty_le * (cao[2] - thap[2]), 4),
                    int(thap[3] + ty_le * (cao[3] - thap[3]) + 0.5),
                    round(thap[4] + ty_le * (cao[4] - thap[4]), 2),
                )
    return row[1], row[2], row[3], row[4]


def clamp_time(board: chess.Board, max_seconds: float, min_seconds: float) -> float:
    """Thời gian tìm, co theo số quân còn trên bàn.

    Thế cờ trống dần thì mỗi nước phải cân nhắc nhiều hơn, nên cho nhiều thời
    gian hơn — nhưng vẫn không vượt trần của Elo.
    """
    con_lai = sum(1 for p in board.piece_map().values() if p.piece_type != chess.KING)
    ty_le = max(0.25, min(1.0, con_lai / 32.0))
    return max(min_seconds, min(max_seconds, max_seconds * ty_le))


def quiesce(board: chess.Board, alpha: int, beta: int, deadline: float) -> int:
    """Đuổi hết chuỗi nước bắt quân, rồi mới chấm điểm.

    Không có bước này, engine sẽ đánh giá một thế đang bị ăn quân là tốt.
    """
    if time.monotonic() > deadline:
        return evaluate(board)
    diem = evaluate(board)
    if diem >= beta:
        return diem
    if diem > alpha:
        alpha = diem
    for move in board.legal_moves:
        if board.is_capture(move) or board.piece_type_at(move.to_square) == chess.PAWN:
            board.push(move)
            diem = -quiesce(board, -beta, -alpha, deadline)
            board.pop()
            if diem >= beta:
                return diem
            if diem > alpha:
                alpha = diem
    return alpha


def negamax(
    board: chess.Board, depth: int, alpha: int, beta: int, deadline: float
) -> int:
    """Điểm tốt nhất cho phe đang đi. Lấy cửa sổ chặn alpha-beta theo cặp."""
    if time.monotonic() > deadline:
        return evaluate(board)

    if board.is_checkmate():
        return -_MATE
    if board.is_stalemate() or board.is_insufficient_material():
        return 0
    if board.is_repetition(2):
        return 0

    if depth <= 0:
        return quiesce(board, alpha, beta, deadline)

    tot = -_INF
    for move in board.legal_moves:
        board.push(move)
        tot = max(tot, -negamax(board, depth - 1, -beta, -alpha, deadline))
        board.pop()
        if tot > alpha:
            alpha = tot
        if alpha >= beta:
            break
    return tot


def _diem_cua(move: chess.Move, board: chess.Board, deadline: float) -> int:
    """Điểm của một nước cụ thể, quy chiều về phe đang đi."""
    board.push(move)
    diem = -negamax(board, 1, -_INF, _INF, deadline)
    board.pop()
    return diem


def _xep_hang(
    board: chess.Board, deadline: float
) -> list[tuple[int, chess.Move]]:
    """Xếp MỌI nước hợp lệ theo điểm, tốt nhất trước. Đắt — chỉ gọi khi cần."""
    ket_qua: list[tuple[int, chess.Move]] = []
    for move in board.legal_moves:
        ket_qua.append((_diem_cua(move, board, deadline), move))
    ket_qua.sort(key=lambda cap: -cap[0])
    return ket_qua


def search(
    board: chess.Board, max_depth: int, deadline: float, max_seconds: float
) -> tuple[chess.Move | None, list[tuple[int, chess.Move]]]:
    """Lặp tăng dần độ sâu.

    Trả (nước tốt nhất, MỌI nước kèm điểm, xếp tốt nhất trước). Trả kèm điểm để
    `think` chọn nước sai mà không phải đánh giá lại — đánh giá lại toàn bộ 40
    nước là tốn gấp đôi thời gian và vỡ trần thời gian.
    """
    nuoc_tot_nhat: chess.Move | None = None
    bang: list[tuple[int, chess.Move]] = []
    het_gio = time.monotonic() + max_seconds
    for depth in range(1, max_depth + 1):
        moi: list[tuple[int, chess.Move]] = []
        # Nước tốt nhất vòng trước thử trước: thường cắt được hàng loạt nhánh.
        if nuoc_tot_nhat is not None and nuoc_tot_nhat in board.legal_moves:
            moi.append((_diem_cua(nuoc_tot_nhat, board, deadline), nuoc_tot_nhat))
        for move in board.legal_moves:
            if move == nuoc_tot_nhat:
                continue
            moi.append((_diem_cua(move, board, deadline), move))
            if time.monotonic() > het_gio and depth > 1:
                break            # giữ chỗ cho vòng sâu hơn thay vì kết thúc
        if not moi:
            break
        moi.sort(key=lambda cap: -cap[0])
        bang, nuoc_tot_nhat = moi, moi[0][1]
        if time.monotonic() > het_gio or depth >= max_depth:
            break
    if not bang:
        bang = _xep_hang(board, deadline)
        return (bang[0][1] if bang else None), bang
    return nuoc_tot_nhat, bang


def think(
    board: chess.Board,
    elo: int = 1500,
    min_seconds: float = 0.6,
    rng=None,
) -> chess.Move | None:
    """Nước đi của máy. `None` nghĩa là hết nước (hoặc thế đã chết).

    `rng` là nguồn ngẫu nhiên dùng cho bước "cố tình chơi sai". Mặc định lấy
    `random` toàn cục — hợp lý khi chơi thật, nhưng test phải truyền
    `random.Random(seed)` nếu muốn ván hỏng tái lập được. Truyền `rng` không
    đụng tới call site nào.
    """
    nguon = rng if rng is not None else random
    if board.is_game_over():
        return None
    bat_dau = time.monotonic()
    max_depth, blunder_rate, slack_cp, max_seconds = profile_for(elo)
    ngan = clamp_time(board, max_seconds, min_seconds)
    deadline = time.monotonic() + ngan
    nuoc, bang = search(board, max_depth, deadline, ngan)
    if nuoc is None:
        return None

    # Đặc tả §3.4: máy chơi yếu bằng cách chọn nước kém hơn nước tốt nhất
    # trong biên độ slack_cp — KHÔNG phải bằng cách chọn nước bất hợp lệ.
    # Điểm lấy LUÔN từ lần xếp hạng của `search`. Đánh giá lại cả 40 nước để
    # lọc nhóm thì tốn gấp đôi thời gian và làm vỡ trần thời gian (đo thật:
    # Elo 2100 mất 11.3 giây thay vì 6).
    if blunder_rate > 0.0 and slack_cp > 0 and len(bang) > 1:
        diem_tot_nhat = bang[0][0]
        nhom = [m for d, m in bang if d >= diem_tot_nhat - slack_cp]
        if len(nhom) > 1 and nguon.random() < blunder_rate:
            bo_qua = max(1, len(nhom) // 3)   # không đánh rơi cả nước đúng nhất
            nuoc = nguon.choice(nhom[bo_qua:])

    # Ở Elo thấp, tìm xong trong ~10 ms. Không chờ thêm thì máy đi tức thì và
    # cảm giác như đang đấu máy in — nên chờ cho đủ min_seconds.
    con_lai = min_seconds - (time.monotonic() - bat_dau)
    if con_lai > 0:
        time.sleep(con_lai)
    return nuoc
