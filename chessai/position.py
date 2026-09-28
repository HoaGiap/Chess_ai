"""Thế cờ và luật FIDE.

Bọc `python-chess`: mọi kiểm tra luật do thư viện đảm nhiệm. Tệp này chỉ làm
hai việc thư viện không làm sẵn — dịch lỗi sang tiếng Việt, và trả lý do kết
thúc ván dạng đọc được.

Quy ước luật (spec §6): lặp thế cờ 3 lần kết thúc ván; luật 50 nước chỉ là
quyền tuyên bố, nên chỉ báo nhắc chứ không kết thúc; luật 75 nước tự kết thúc.
"""

from __future__ import annotations

import chess

Color = chess.Color

# Board.parse_san() chỉ phân tích, không đổi thế cờ. Đây là cơ sở của bất biến
# "nước sai không đổi gì": parse lỗi thì ném trước kịp push.
_POPULAR = "e4, Nf3, O-O, exd5, e8=Q"

_PIECE_VN = {
    chess.PAWN: "tốt",
    chess.KNIGHT: "mã",
    chess.BISHOP: "tượng",
    chess.ROOK: "xe",
    chess.QUEEN: "hậu",
    chess.KING: "vua",
}

# Termination dùng enum.auto() nên .value là số — tra map bằng chính member.
_TERMINATION_VN = {
    chess.Termination.CHECKMATE: "chiếu hết",
    chess.Termination.STALEMATE: "bế tắc — hòa do hết nước đi hợp lệ",
    chess.Termination.INSUFFICIENT_MATERIAL: "hòa — không đủ lực lượng chiếu hết",
    chess.Termination.SEVENTYFIVE_MOVES: "hòa — luật 75 nước",
    chess.Termination.THREEFOLD_REPETITION: "hòa — lặp thế cờ 3 lần",
}

# (ô phải trống, ô xe, ô vua, đường vua đi qua) — tính theo phe Trắng.
_CASTLING_TEXT = {
    "O-O": ((chess.F1, chess.G1), chess.H1, chess.E1, (chess.E1, chess.F1, chess.G1)),
    "O-O-O": ((chess.D1, chess.C1, chess.B1), chess.A1, chess.E1, (chess.E1, chess.D1, chess.C1)),
}

_CASTLING_DEST = ("g1", "c1", "g8", "c8")


class MoveError(Exception):
    """Nước không hợp lệ. Thông điệp đã bằng tiếng Việt, in thẳng ra được."""


def _shift(square: int, turn: chess.Color) -> int:
    """Dịch ô của phe Trắng sang ô cùng vị trí của phe Đen."""
    return square + (56 if turn == chess.BLACK else 0)


def _castle_key(san: str) -> str:
    """Chuẩn hoá ký hiệu nhập thành về 'O-O' hoặc 'O-O-O'."""
    return san.replace(" ", "").replace("0", "O").upper()


def _castling_blocker(board: chess.Board, san: str) -> str:
    """Nêu lý do cụ thể không nhập thành được, hoặc '' nếu không xác định được."""
    key = _castle_key(san)
    if key not in _CASTLING_TEXT:
        return ""
    turn = board.turn
    empty_sqs, rook_sq, king_sq, king_path = _CASTLING_TEXT[key]

    if board.king(turn) != _shift(king_sq, turn):
        home = chess.square_name(_shift(king_sq, turn))
        return f"vua không còn ở ô {home} — nhập thành cần vua ở đúng ô xuất phát."

    for raw in empty_sqs:
        sq = _shift(raw, turn)
        piece = board.piece_at(sq)
        if piece is not None and piece.color == turn:
            name = _PIECE_VN[piece.piece_type]
            return f"ô {chess.square_name(sq)} chưa trống — {name} của bạn đang ở đó."

    rook_at = _shift(rook_sq, turn)
    piece = board.piece_at(rook_at)
    side_name = "ngắn" if key == "O-O" else "dài"
    if piece is None or piece.piece_type != chess.ROOK or piece.color != turn:
        kind = "xe" if key == "O-O" else "tượng"
        return f"thiếu {kind} ở ô {chess.square_name(rook_at)} (nhập thành {side_name})."

    if not board.castling_rights & chess.BB_SQUARES[rook_at]:
        return f"vua đã từng rời ô xuất phát nên mất quyền nhập thành {side_name}."

    for raw in king_path:
        sq = _shift(raw, turn)
        if board.is_attacked_by(turn, sq):
            return f"ô {chess.square_name(sq)} đang bị tấn công — không được nhập thành qua ô bị chiếu."

    return ""


def _en_passant_note(board: chess.Board, san: str) -> str:
    """Gợi ý khi người chơi thử bắt tốt qua đường ở thế không cho phép."""
    text = san.replace(" ", "").lower()
    if len(text) < 4 or text[1] != "x":
        return ""
    landing = "6" if board.turn == chess.WHITE else "3"
    if text[-1] != landing or board.ep_square is not None:
        return ""
    return " Bắt tốt qua đường chỉ được ngay sau khi đối thủ vừa đi tốt 2 ô bằng một nước."


def _castle_notation_note(san: str) -> str:
    """Gợi ý dùng đúng ký hiệu nhập thành thay vì đi vua bằng ký hiệu ô."""
    text = san.replace(" ", "").lower()
    if text[:1] == "k" and text[-2:] in _CASTLING_DEST:
        return " Nếu bạn muốn nhập thành, hãy dùng ký hiệu O-O hoặc O-O-O."
    return ""


class Position:
    """Thế cờ: vị trí quân, lượt đi, lịch sử. Luật do python-chess kiểm tra."""

    def __init__(self, fen: str = chess.STARTING_FEN) -> None:
        self._root_fen = fen
        self._board = chess.Board(fen)

    @property
    def board(self) -> chess.Board:
        """Thằng `chess.Board` để render và test dùng. Đọc-only từ phía ngoài."""
        return self._board

    @property
    def root_fen(self) -> str:
        """FEN vị trí xuất phát — mốc để dựng lại lịch sử."""
        return self._root_fen

    @property
    def side_to_move(self) -> chess.Color:
        return self._board.turn

    def fen(self) -> str:
        return self._board.fen()

    def legal_sans(self) -> list[str]:
        return sorted(self._board.san(m) for m in self._board.legal_moves)

    def san_history(self) -> list[str]:
        """SAN từng nước trong lịch sử.

        `Board.san(move)` chỉ đúng khi bàn cờ đang đứng ở vị trí trước nước
        đi, nên phải dựng lại từ FEN gốc thay vì duyệt move_stack trên bàn
        cờ đã đi hết (cách đó sẽ ném AssertionError).
        """
        replay = chess.Board(self._root_fen)
        return [replay.san_and_push(move) for move in self._board.move_stack]

    def ply_count(self) -> int:
        return len(self._board.move_stack)

    def apply_san(self, san: str) -> None:
        """Đi một nước. Ném `MoveError` và giữ nguyên thế cờ nếu nước sai."""
        text = san.strip()
        if not text:
            raise MoveError(f"Chưa nhập nước đi. Ví dụ hợp lệ: {_POPULAR}.")
        try:
            move = self._board.parse_san(text)
        except chess.AmbiguousMoveError:
            raise MoveError(
                f"Không rõ quân nào đi '{text}'. Ghi rõ hậu tốc, ví dụ: Nbd2."
            ) from None
        except chess.IllegalMoveError as exc:
            raise MoveError(self._illegal_message(text, exc)) from None
        except chess.InvalidMoveError:
            raise MoveError(
                f"Không hiểu '{text}' như nước đi cờ vua. "
                f"Nước hợp lệ gần nhất: {self._suggestion(text)}. "
                f"Ví dụ: {_POPULAR}."
            ) from None
        self._board.push(move)

    def _suggestion(self, san: str) -> str:
        """Vài nước hợp lệ gần nhất, ưu tiên nước cùng chữ cái đầu."""
        head = san[:1].lower()
        same = [s for s in self.legal_sans() if s[:1].lower() == head]
        pool = same or self.legal_sans()
        return ", ".join(pool[:6]) or "không có nước đi hợp lệ nào"

    def _illegal_message(self, san: str, exc: chess.IllegalMoveError) -> str:
        blocker = _castling_blocker(self._board, san)
        if blocker:
            return f"Nhập thành không hợp lệ: {blocker}"
        reason = getattr(exc, "message", None) or str(exc) or "vi phạm luật cờ vua."
        note = _en_passant_note(self._board, san) + _castle_notation_note(san)
        return f"'{san}' không hợp lệ: {reason}{note}"

    def undo(self) -> None:
        if not self._board.move_stack:
            raise MoveError("Không có nước nào để lùi.")
        self._board.pop()
