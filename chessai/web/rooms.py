"""Phòng chơi người thật. Mọi thứ nằm trong RAM — mất hết khi máy chủ dừng.

Mỗi phòng có một `game_id` trỏ vào `GameStore`, và `human_color` của ván đó
LUÔN là `None` (không có AI trong phòng) — nên `AIController` không can thiệp
và `Session` không chặn lượt; việc chặn lượt là của tầng này, theo **ghế**.

Giới hạn đã biết: chỉ chạy được trong MỘT tiến trình máy chủ. Chạy
`--workers 2` thì hai người ở hai phòng khác tiến trình sẽ không thấy nhau —
cần khoá dùng chung mới xử lý được.
"""

from __future__ import annotations

import secrets
import threading
import time

import chess

from .games import GameStore
from .schema import GameState

# Không dùng l, o, i, 0, 1: người ta sẽ đọc to mã phòng cho người khác.
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_ROOM_ID_LENGTH = 8
_DEFAULT_CAPACITY = 200


class RoomError(Exception):
    """Lỗi nghiệp vụ, mang theo mã HTTP và câu tiếng Việt."""

    status_code = 400


class NotFound(RoomError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__("Phòng không tồn tại hoặc đã đóng.")


class NotInRoom(RoomError):
    status_code = 403

    def __init__(self) -> None:
        super().__init__("Bạn không ở trong phòng này.")


class NotHost(RoomError):
    status_code = 403

    def __init__(self) -> None:
        super().__init__("Chỉ người tạo phòng mới được bắt đầu.")


class Full(RoomError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("Phòng đã đủ hai người chơi.")


class NotEnough(RoomError):
    def __init__(self) -> None:
        super().__init__("Cần đủ hai người chơi mới bắt đầu được.")


class NotStarted(RoomError):
    def __init__(self) -> None:
        super().__init__("Ván chưa bắt đầu.")


class NotYourTurn(RoomError):
    def __init__(self) -> None:
        super().__init__("Chưa đến lượt bạn.")


class GameOver(RoomError):
    def __init__(self) -> None:
        super().__init__("Ván đã kết thúc.")


class Unauthorized(RoomError):
    status_code = 401

    def __init__(self) -> None:
        super().__init__("Chưa nhận diện được người chơi — tải lại trang.")


class NoUndo(RoomError):
    def __init__(self) -> None:
        super().__init__("Trong phòng không có nút lùi nước.")


class RoomView:
    """Thông tin công khai của một phòng, đã cắt bớt cho người gọi."""

    __slots__ = (
        "id", "white", "black", "host", "started", "finished", "result_text",
        "you", "connected", "opponent_connected", "created_at",
    )

    def __init__(self, **kw) -> None:
        for ten in self.__slots__:
            setattr(self, ten, kw.get(ten))

    def as_dict(self) -> dict:
        du = {ten: getattr(self, ten) for ten in self.__slots__
              if ten != "created_at"}
        # `status` là property nên không nằm trong __slots__ — phải thêm tay,
        # nếu không trình duyệt không có gì để hiện trong danh sách phòng.
        du["status"] = self.status
        return du

    @property
    def status(self) -> str:
        if self.finished:
            return "Xong"
        if self.started:
            return "Đang đấu"
        if self.white and self.black:
            return "Sẵn sàng"
        if self.white or self.black:
            return "Chờ đối thủ"
        return "Chờ người"


class _Room:
    __slots__ = ("id", "created_at", "white", "black", "host", "game_id",
                 "started", "connected")

    def __init__(self, room_id: str, game_id: str, host: str) -> None:
        self.id = room_id
        self.created_at = time.monotonic()
        self.white: str | None = None
        self.black: str | None = None
        self.host = host
        self.game_id = game_id
        self.started = False
        self.connected: set[str] = set()


class RoomStore:
    def __init__(self, games: GameStore, capacity: int = _DEFAULT_CAPACITY) -> None:
        if capacity < 1:
            raise ValueError("capacity phải >= 1")
        self.capacity = capacity
        self.games = games
        self._rooms: dict[str, _Room] = {}
        self._order: list[str] = []
        self._locks: dict[str, threading.Lock] = {}
        self._listeners: dict[str, list] = {}
        self._guard = threading.Lock()

    # ---- đọc / ghi cơ bản -------------------------------------------

    def _require(self, room_id: str) -> _Room:
        try:
            return self._rooms[room_id]
        except KeyError:
            raise NotFound() from None

    def _lock(self, room_id: str) -> threading.Lock:
        self._require(room_id)
        return self._locks[room_id]

    def _new_id(self) -> str:
        while True:
            rid = "".join(secrets.choice(_ALPHABET) for _ in range(_ROOM_ID_LENGTH))
            if rid not in self._rooms:
                return rid

    def _drop(self, room_id: str) -> None:
        self._rooms.pop(room_id, None)
        self._locks.pop(room_id, None)
        self._listeners.pop(room_id, None)
        if room_id in self._order:
            self._order.remove(room_id)

    def _view(self, room: _Room, token: str | None) -> RoomView:
        state = None
        if room.started:
            state = self.games.snapshot(room.game_id)
        you = None
        if token is not None:
            if room.white == token:
                you = "white"
            elif room.black == token:
                you = "black"
        # Ghế của ĐỐI THỦ: `connected` là của chính người gọi (dùng cho phòng
        # chờ), `opponent_connected` mới là thứ trình duyệt dùng để báo mất
        # kết nối. Nhầm hai cái thì cảnh báo sẽ không bao giờ hiện.
        opponent_connected = True
        if you == "white":
            opponent_connected = room.black in room.connected
        elif you == "black":
            opponent_connected = room.white in room.connected
        return RoomView(
            id=room.id,
            white=room.white,
            black=room.black,
            host=room.host,
            started=room.started,
            finished=bool(state.over) if state is not None else False,
            result_text=state.result_text if state is not None else None,
            you=you,
            connected=(token in room.connected) if token is not None else False,
            opponent_connected=opponent_connected,
            created_at=room.created_at,
        )

    def view(self, room_id: str, token: str | None = None) -> RoomView:
        with self._lock(room_id):
            return self._view(self._require(room_id), token)

    def list(self, token: str | None = None) -> list[RoomView]:
        with self._guard:
            ids = list(self._order)
            rooms = [self._rooms[i] for i in ids if i in self._rooms]
        return [self._view(r, token) for r in rooms]

    def game_id_of(self, room_id: str) -> str:
        with self._lock(room_id):
            return self._require(room_id).game_id

    # ---- người nghe để đẩy trạng thái --------------------------------

    def add_listener(self, room_id: str, send) -> None:
        with self._guard:
            self._listeners.setdefault(room_id, []).append(send)

    def remove_listener(self, room_id: str, send) -> None:
        with self._guard:
            danh = self._listeners.get(room_id) or []
            if send in danh:
                danh.remove(send)

    def _notify(self, room_id: str) -> None:
        """Gọi SAU khi đã thả khoá phòng — `send` sẽ đọc trạng thái, mà đọc
        trạng thái thì lại lấy khoá phòng, nên gọi lúc còn khoá sẽ tự treo."""
        with self._guard:
            nhan = list(self._listeners.get(room_id, ()))
        for send in nhan:
            try:
                send()
            except Exception:
                self.remove_listener(room_id, send)

    # ---- thao tác phòng ---------------------------------------------

    def create(self, host_token: str) -> str:
        game_id = self.games.create(None)          # human_color=None: hai người
        room_id = self._new_id()
        with self._guard:
            room = _Room(room_id, game_id, host_token)
            # Người tạo phòng vào ghế Trắng luôn. Nếu để ghế trống thì họ
            # phải tự bấm "Vào" mới chơi được — lúc đó "người tạo phòng" chỉ là
            # một nhãn, và một người lạ có thể ngồi ghế Trắng trước họ.
            room.white = host_token
            self._rooms[room_id] = room
            self._locks[room_id] = threading.Lock()
            self._order.append(room_id)
            while len(self._order) > self.capacity:
                self._drop(self._order[0])
        self._notify(room_id)
        return room_id

    def join(self, room_id: str, token: str) -> RoomView:
        with self._lock(room_id):
            room = self._require(room_id)
            if room.white == token or room.black == token:
                view = self._view(room, token)      # vào lại: trả về chỗ cũ
            else:
                if room.white is None:
                    room.white = token
                elif room.black is None:
                    room.black = token
                else:
                    raise Full()
                # KHÔNG đánh dấu `connected` ở đây: cờ đó có nghĩa là "đang có
                # WebSocket sống", nên chỉ lớp WebSocket được quyết định. Nếu
                # đánh dấu lúc vào phòng thì người vào bằng link mà WebSocket
                # hỏng sẽ không bao giờ thấy cảnh báo mất kết nối.
                view = self._view(room, token)
        self._notify(room_id)
        return view

    def leave(self, room_id: str, token: str) -> RoomView:
        with self._lock(room_id):
            room = self._require(room_id)
            if room.white == token:
                room.white = None
            elif room.black == token:
                room.black = None
            room.connected.discard(token)
            if room.host == token:
                # Ghế host trống: nhường quyền cho người còn lại, nếu có.
                room.host = room.white or room.black or token
            if room.white is None or room.black is None:
                room.started = False
            view = self._view(room, token)
        self._notify(room_id)
        return view

    def start(self, room_id: str, token: str) -> RoomView:
        with self._lock(room_id):
            room = self._require(room_id)
            if room.host != token:
                raise NotHost()
            if room.white is None or room.black is None:
                raise NotEnough()
            room.started = True
            view = self._view(room, token)
        self._notify(room_id)
        return view

    def rematch(self, room_id: str, token: str) -> RoomView:
        with self._lock(room_id):
            room = self._require(room_id)
            if room.host != token:
                raise NotHost()
            if room.white is None or room.black is None:
                raise NotEnough()
            self.games.new_game(room.game_id)
            room.started = False
            view = self._view(room, token)
        self._notify(room_id)
        return view

    def set_connected(self, room_id: str, token: str, value: bool) -> None:
        try:
            with self._lock(room_id):
                room = self._require(room_id)
                if value:
                    room.connected.add(token)
                else:
                    room.connected.discard(token)
        except NotFound:
            pass      # phòng đã bị cắt khỏi bộ nhớ: không còn gì để cập nhật
        self._notify(room_id)

    # ---- chơi --------------------------------------------------------

    def _seat_of(self, room: _Room, token: str) -> str:
        if room.white == token:
            return "white"
        if room.black == token:
            return "black"
        raise NotInRoom()

    def move(self, room_id: str, token: str, san: str) -> tuple[RoomView, GameState]:
        with self._lock(room_id):
            room = self._require(room_id)
            if not room.started:
                raise NotStarted()
            seat = self._seat_of(room, token)
            state = self.games.snapshot(room.game_id)
            if state.over:
                raise GameOver()
            # Chặn theo GHẾ, không chỉ theo lượt.
            if seat != state.turn:
                raise NotYourTurn()
            new_state = self.games.submit(room.game_id, san)
            view = self._view(room, token)
        self._notify(room_id)
        return view, new_state

    def resign(self, room_id: str, token: str) -> tuple[RoomView, GameState]:
        with self._lock(room_id):
            room = self._require(room_id)
            seat = self._seat_of(room, token)
            color = chess.WHITE if seat == "white" else chess.BLACK
            self.games.session(room.game_id).resign(color)
            state = self.games.snapshot(room.game_id)
            view = self._view(room, token)
        self._notify(room_id)
        return view, state


# Bảng chữ cái và độ dài: đã kiểm 31 ký hiệu, 8 ký tự ≈ 2^40 — đủ để link
# ngắn mà khó đoán. Đây là CHE MỜ, không phải bí mật: bí mật thật là mã người
# chơi (2^128) trong `localStorage`.
