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

# Nhập thành hai bên đều cần XE ở h1/a1 (h8/a8) — không phải tượng.
_CASTLING_ROOK_VN = "xe"

_PIECE_LETTERS = {
    "K": chess.KING,
    "Q": chess.QUEEN,
    "R": chess.ROOK,
    "B": chess.BISHOP,
    "N": chess.KNIGHT,
}


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
        return (
            f"thiếu {_CASTLING_ROOK_VN} ở ô {chess.square_name(rook_at)} "
            f"(nhập thành {side_name})."
        )

    if not board.castling_rights & chess.BB_SQUARES[rook_at]:
        # castling_rights là bitboard các ô XE, không phân biệt vua hay xe đã đi.
        return (
            f"vua hoặc {_CASTLING_ROOK_VN} đã từng rời ô xuất phát, "
            f"nên mất quyền nhập thành {side_name}."
        )

    for raw in king_path:
        sq = _shift(raw, turn)
        # Hỏi phe ĐỐI THỦ có đang chiếu ô này không. Truyền `turn` sẽ hỏi
        # chính phe đi và luôn trả về True ở ô vua, nên luôn báo nhầm e1/e8.
        if board.is_attacked_by(not turn, sq):
            return f"ô {chess.square_name(sq)} đang bị chiếu — không được nhập thành qua ô bị tấn công."

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


def _target_of(san: str) -> tuple[int, int | None]:
    """(loại quân, ô đích) suy ra từ SAN. Ô đích là None nếu không đọc được.

    Không dùng `Board.parse_san` vì nước đang bị từ chối — thư viện ném lỗi.
    """
    text = san.replace(" ", "")
    for suffix in ("+", "#", "!", "?"):
        text = text.replace(suffix, "")
    text = text.split("=")[0]
    if not text:
        return chess.PAWN, None
    # Phải phân biệt HOA/thường: "Bxd3" là tượng, còn "bxd3" là tốt từ cột b.
    head = text[:1]
    piece = _PIECE_LETTERS[head] if head in _PIECE_LETTERS else chess.PAWN
    try:
        return piece, chess.parse_square(text[-2:].lower())
    except ValueError:
        return piece, None


def _explain_illegal(board: chess.Board, san: str) -> str:
    """Giải thích tiếng Việt vì sao nước đi không hợp lệ.

    Ưu tiên các nguyên nhân hay gặp, thay vì lộ chuỗi của thư viện kèm FEN.
    """
    piece_type, dest = _target_of(san)
    if dest is not None:
        name = chess.square_name(dest)
        occupant = board.piece_at(dest)
        if occupant is not None and occupant.color == board.turn:
            return f"ô {name} đang có {_PIECE_VN[occupant.piece_type]} CỦA BẠN — không bắt được quân của chính mình."
        if occupant is not None and occupant.piece_type == chess.KING:
            return f"không được bắt vua của đối thủ."
        if board.is_attacked_by(not board.turn, dest):
            return f"ô {name} đang bị chiếu — không được đi vào."
        if piece_type == chess.PAWN and chess.square_rank(dest) in (0, 7):
            return f"tốt tới {name} phải được phong cấp, ví dụ: {san}=Q."
    if piece_type != chess.PAWN and not any(
        board.pieces(piece_type, color) for color in (chess.WHITE, chess.BLACK)
    ):
        return f"bàn cờ không còn {_PIECE_VN[piece_type]} nào."
    return "không phải nước đi hợp lệ trong thế cờ này — đã kiểm tra luật, quân và chiếu."


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

    def apply_san(self, san: str) -> str:
        """Đi một nước, trả về SAN chuẩn của nó.

        Ném `MoveError` và giữ nguyên thế cờ nếu nước sai.
        """
        text = san.strip()
        if not text:
            raise MoveError(f"Chưa nhập nước đi. Ví dụ hợp lệ: {_POPULAR}.")
        try:
            move = self._board.parse_san(text)
        except chess.AmbiguousMoveError:
            raise MoveError(
                f"Không rõ quân nào đi '{text}'. Ghi rõ hậu tốc, ví dụ: Nbd2."
            ) from None
        except chess.IllegalMoveError:
            raise MoveError(self._illegal_message(text)) from None
        except chess.InvalidMoveError:
            raise MoveError(
                f"Không hiểu '{text}' như nước đi cờ vua. "
                f"Nước hợp lệ gần nhất: {self._suggestion(text)}. "
                f"Ví dụ: {_POPULAR}."
            ) from None
        # san() phải gọi TRƯỚC push: nó cần bàn cờ đứng ở vị trí trước nước đi.
        canonical = self._board.san(move)
        self._board.push(move)
        return canonical

    def _suggestion(self, san: str) -> str:
        """Vài nước hợp lệ gần nhất, ưu tiên nước cùng chữ cái đầu."""
        head = san[:1].lower()
        same = [s for s in self.legal_sans() if s[:1].lower() == head]
        pool = same or self.legal_sans()
        return ", ".join(pool[:6]) or "không có nước đi hợp lệ nào"

    def _illegal_message(self, san: str) -> str:
        blocker = _castling_blocker(self._board, san)
        if blocker:
            return f"Nhập thành không hợp lệ: {blocker}"
        note = _en_passant_note(self._board, san) + _castle_notation_note(san)
        return f"'{san}' không hợp lệ: {_explain_illegal(self._board, san)}{note}"

    def outcome(self) -> chess.Outcome | None:
        """Kết quả ván, hoặc None nếu ván còn đi.

        Kiểm theo thứ tự ưu tiên của luật (spec §6). Không dùng
        `Board.is_game_over()` / `Board.outcome()` vì chúng coi lặp thế 3 lần
        và 50 nước là quyền tuyên bố của người đến lượt, trái với spec:
        ở đây lặp 3 lần tự kết thúc, còn 50 nước thì chỉ báo nhắc.
        """
        b = self._board
        if b.is_checkmate():
            return chess.Outcome(termination=chess.Termination.CHECKMATE, winner=not b.turn)
        if b.is_stalemate():
            return chess.Outcome(termination=chess.Termination.STALEMATE, winner=None)
        if b.is_insufficient_material():
            return chess.Outcome(termination=chess.Termination.INSUFFICIENT_MATERIAL, winner=None)
        if b.is_seventyfive_moves():
            return chess.Outcome(termination=chess.Termination.SEVENTYFIVE_MOVES, winner=None)
        if b.is_repetition(3):
            return chess.Outcome(termination=chess.Termination.THREEFOLD_REPETITION, winner=None)
        return None

    def is_game_over(self) -> bool:
        return self.outcome() is not None

    def termination_text(self) -> str:
        outcome = self.outcome()
        if outcome is None:
            return "ván đang diễn ra"
        reason = _TERMINATION_VN.get(outcome.termination, "kết thúc")
        if outcome.winner is None:
            return f"HÒA: {reason}"
        return f"{'Trắng' if outcome.winner else 'Đen'} thắng: {reason}"

    def can_claim_fifty_moves(self) -> bool:
        """Luật 50 nước là quyền tuyên bố, không tự kết thúc ván."""
        return self._board.can_claim_fifty_moves()

    def undo(self) -> None:
        if not self._board.move_stack:
            raise MoveError("Không có nước nào để lùi.")
        self._board.pop()
