"""Nơi duy nhất giữ ván đấu.

Route HTTP không bao giờ đụng `chessai.Session` trực tiếp — chỉ qua đây. Khi
lên Internet, thay lớp này bằng SQLite/Postgres mà không phải sửa route.
"""

from __future__ import annotations

import secrets
import threading

import chess

from ..position import MoveError, Position
from ..session import Session
from .schema import GameState, MoveOption

# Bản thân thư viện không có Board.captured_pieces, nên phải quét lịch sử.
_PIECE_LETTER = {
    chess.PAWN: "P",
    chess.KNIGHT: "N",
    chess.BISHOP: "B",
    chess.ROOK: "R",
    chess.QUEEN: "Q",
    chess.KING: "K",
}

_ID_LENGTH = 12

# Trần số ván trong bộ nhớ. `POST /api/game` là CORS simple request nên bất kỳ
# trang nào cũng POST vòng lòng vào được; không có trần thì bộ nhớ phình vô hạn.
_DEFAULT_CAPACITY = 200

_MISSING = (
    "Ván không còn tồn tại — máy chủ đã khởi động lại. Bấm 'Ván mới' để chơi tiếp."
)


class GameNotFound(Exception):
    """Ván không tồn tại — thường vì máy chủ đã khởi động lại."""


def _move_options(board: chess.Board) -> list[MoveOption]:
    return [
        MoveOption(
            from_sq=chess.square_name(move.from_square),
            to_sq=chess.square_name(move.to_square),
            san=board.san(move),
            capture=board.is_capture(move),
            promotion=(
                chess.piece_symbol(move.promotion).upper() if move.promotion else None
            ),
        )
        for move in board.legal_moves
    ]


def _captured(board: chess.Board) -> tuple[list[str], list[str]]:
    """(quân phe Trắng đã bắt, quân phe Đen đã bắt), chữ cái viết HOA.

    Bắt tốt qua đường: quân bị ăn nằm lùi 1 hàng về phía phe bắt — trắng
    thì `to_rank - 1`, đen thì `to_rank + 1`.
    """
    by_white: list[str] = []
    by_black: list[str] = []
    replay = chess.Board(board.root().fen())
    for move in board.move_stack:
        taker_is_white = replay.turn == chess.WHITE
        if replay.is_capture(move):
            if replay.is_en_passant(move):
                rank = chess.square_rank(move.to_square)
                victim_square = chess.square(
                    chess.square_file(move.to_square),
                    rank - 1 if taker_is_white else rank + 1,
                )
            else:
                victim_square = move.to_square
            victim = replay.piece_at(victim_square)
            if victim is not None:
                target = by_white if taker_is_white else by_black
                target.append(_PIECE_LETTER[victim.piece_type])
        replay.push(move)
    return by_white, by_black


def _plies_per_turn(session: Session) -> int:
    """Chơi hai bên thì lùi 1 ply; có đối thủ thì lùi 2 ply."""
    return 1 if session.human_color is None else 2


class GameStore:
    def __init__(self, capacity: int = _DEFAULT_CAPACITY) -> None:
        if capacity < 1:
            raise ValueError("capacity phải >= 1")
        self.capacity = capacity
        self._games: dict[str, Session] = {}
        self._locks: dict[str, threading.Lock] = {}
        # Thứ tự chèn, để cắt bỏ ván cũ nhất khi đầy (thay cho OrderedDict
        # để `dict` chỉ cần hỗ trợ xoá giữa chừng).
        self._order: list[str] = []
        self._guard = threading.Lock()

    def create(self, human_color: chess.Color | None) -> str:
        game_id = secrets.token_urlsafe(16)[:_ID_LENGTH]
        with self._guard:
            self._games[game_id] = Session(human_color=human_color)
            self._locks[game_id] = threading.Lock()
            self._order.append(game_id)
            while len(self._order) > self.capacity:
                self._drop(self._order[0])
        return game_id

    def forget(self, game_id: str) -> None:
        """Xoá ván khỏi bộ nhớ — mô phỏng hành vi mất ván khi máy chủ restart."""
        with self._guard:
            self._require(game_id)
            self._drop(game_id)

    def session(self, game_id: str) -> Session:
        """Trả về `Session` để #3B cắm engine qua `on_move`."""
        return self._require(game_id)

    def set_fen(self, game_id: str, fen: str) -> None:
        """Nạp một thế cờ cụ thể. Dùng cho kiểm thử và #4 (`Review`)."""
        with self._lock(game_id):
            self._require(game_id).position = Position(fen)

    def snapshot(self, game_id: str) -> GameState:
        # Phải khoá CẢ nhánh đọc: `board.san()` bên trong `_move_options` tạm
        # đẩy rồi lùi trên `chess.Board` dùng chung, nên đọc song song với
        # một nước đi sẽ gặp bàn cờ nửa vời và python-chess ném AssertionError.
        with self._lock(game_id):
            return self._snapshot(game_id)

    def _snapshot(self, game_id: str) -> GameState:
        """Thân của `snapshot`, KHÔNG khoá — dùng bên trong khoá đã có.

        `threading.Lock` không reentrant nên không khoá lồng được.
        """
        session = self._require(game_id)
        board = session.position.board
        by_white, by_black = _captured(board)
        last_from = last_to = None
        if board.move_stack:
            played = board.move_stack[-1]
            last_from = chess.square_name(played.from_square)
            last_to = chess.square_name(played.to_square)
        check_square = None
        if board.is_check():
            check_square = chess.square_name(board.king(board.turn))
        return GameState(
            game_id=game_id,
            fen=board.fen(),
            turn="white" if board.turn else "black",
            legal=_move_options(board),
            last_move=session.last_move_label(),
            last_from=last_from,
            last_to=last_to,
            check=board.is_check(),
            check_square=check_square,
            over=session.is_game_over(),
            result_text=session.result_text(),
            moves=session.position.san_history(),
            captured_by_white=by_white,
            captured_by_black=by_black,
            can_undo=session.position.ply_count() >= _plies_per_turn(session),
        )

    def submit(self, game_id: str, san: str) -> GameState:
        with self._lock(game_id):
            session = self._require(game_id)
            session.apply_san(san)
            return self._snapshot(game_id)

    def undo(self, game_id: str) -> GameState:
        with self._lock(game_id):
            session = self._require(game_id)
            # Session.undo_turn() trả False chứ không ném, nên phải kiểm:
            # im lặng bỏ qua sẽ khiến route trả 200 cho một lệnh không làm gì.
            if not session.undo_turn():
                raise MoveError("Không có nước nào để lùi.")
            return self._snapshot(game_id)

    def new_game(self, game_id: str) -> GameState:
        with self._lock(game_id):
            session = self._require(game_id)
            # `restart()` chứ không tạo `Session` mới: tạo mới sẽ âm thầm mất
            # `on_move` — hook mà #3B cắm engine vào.
            session.restart()
            return self._snapshot(game_id)

    def pgn_text(self, game_id: str) -> str:
        with self._lock(game_id):
            return self._require(game_id).pgn()

    def _drop(self, game_id: str) -> None:
        """Bỏ một ván khỏi bộ nhớ. Phải giữ `_guard` (không reentrant)."""
        self._games.pop(game_id, None)
        self._locks.pop(game_id, None)
        if game_id in self._order:
            self._order.remove(game_id)

    def _require(self, game_id: str) -> Session:
        try:
            return self._games[game_id]
        except KeyError:
            raise GameNotFound(_MISSING) from None

    def _lock(self, game_id: str) -> threading.Lock:
        self._require(game_id)
        return self._locks[game_id]
