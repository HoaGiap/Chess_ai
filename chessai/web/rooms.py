"""Phòng chơi người thật. Mọi thứ nằm trong RAM — mất hết khi máy chủ dừng.

Mỗi phòng có một `game_id` trỏ vào `GameStore`, và `human_color` của ván đó
LUÔN là `None` (không có AI trong phòng) — nên `AIController` không can thiệp
và `Session` không chặn lượt; việc chặn lượt là của tầng này, theo **ghế**.

BÍ MẬT: mã người chơi (`X-Player`, 2^128) là thứ duy nhất chứng minh "bạn là
bạn". Vì vậy nó **KHÔNG BAO GIỜ** nằm trong `RoomView` — chỉ ghế trống/đầy và
vài câu hỏi đã trả lời sẵn mới ra ngoài. Gửi token thật thì bất kỳ ai cũng
lấy được từ `GET /api/rooms` rồi chơi thay người đó.

Giới hạn đã biết: chỉ chạy được trong MỘT tiến trình máy chủ. Chạy
`--workers 2` thì hai người ở hai phòng khác tiến trình sẽ không thấy nhau —
cần khoá dùng chung mới xử lý được.
"""

from __future__ import annotations

import secrets
import threading
import time

import chess

from .games import GameNotFound, GameStore
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


class OpponentOnline(RoomError):
    def __init__(self) -> None:
        super().__init__("Đối thủ vẫn đang ở trong phòng.")


class TooManyRooms(RoomError):
    status_code = 429

    def __init__(self) -> None:
        super().__init__(
            "Bạn tạo phòng hơi nhiều. Chờ một chút rồi thử lại nhé."
        )


class RoomView:
    """Thông tin công khai của phòng.

    CỐ TÌNH KHÔNG chứa token người chơi: chỉ có câu trả lời ("ghế này có
    người", "bạn có phải host", "bạn có ngồi trong phòng"). `token` là tham số
    vào để so sánh nội bộ rồi bỏ đi.
    """

    __slots__ = (
        "id", "seat_white", "seat_black", "host_is_you", "you_in_room", "you",
        "started", "finished", "result_text", "connected",
        "opponent_connected", "status", "created_at",
    )

    def __init__(self, **kw) -> None:
        for ten in self.__slots__:
            setattr(self, ten, kw.get(ten))

    def as_dict(self) -> dict:
        return {ten: getattr(self, ten) for ten in self.__slots__
                if ten != "created_at"}


class _Room:
    __slots__ = ("id", "created_at", "white", "black", "host", "game_id",
                 "started", "connected")

    def __init__(self, room_id: str, game_id: str, host: str) -> None:
        self.id = room_id
        self.created_at = time.monotonic()
        self.white: str | None = None
        self.black: str | None = None
        self.host: str | None = host
        self.game_id = game_id
        self.started = False
        self.connected: set[str] = set()

    def seat_of(self, token: str | None) -> str | None:
        if token is None:
            return None
        if token == self.white:
            return "white"
        if token == self.black:
            return "black"
        return None

    def other(self, token: str) -> str | None:
        return self.black if token == self.white else self.white


class RoomStore:
    def __init__(
        self,
        games: GameStore,
        capacity: int = _DEFAULT_CAPACITY,
        create_quota: int = 20,
        create_window: float = 3600.0,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity phải >= 1")
        self.capacity = capacity
        self.games = games
        # Không giới hạn tạo phòng thì ai cũng tạo được, và phòng mới sẽ đẩy
        # phòng cũ của người khác ra khỏi bộ nhớ. Tính theo mã người chơi, cửa
        # sổ lưu thời điểm tạo phòng gần nhất.
        self.create_quota = create_quota
        self.create_window = create_window
        self._tao_luc: dict[str, list[float]] = {}
        self._rooms: dict[str, _Room] = {}
        self._order: list[str] = []
        self._locks: dict[str, threading.Lock] = {}
        self._listeners: dict[str, list] = {}
        self._guard = threading.Lock()

    def _kiem_quota(self, token: str) -> None:
        if self.create_quota <= 0:
            return
        bay = time.monotonic()
        khoang = self.create_window
        danh = [x for x in self._tao_luc.get(token, ()) if bay - x < khoang]
        if len(danh) >= self.create_quota:
            self._tao_luc[token] = danh
            raise TooManyRooms()
        danh.append(bay)
        self._tao_luc[token] = danh

    def _cat_binh_ho_phong(self) -> None:
        """Cắt bỏ phòng cũ nhất, nhưng ưu tiên phòng CHỜ trước phòng ĐANG CHƠI.

        Nếu chỉ cắt theo thứ tự tạo, một người mở nhiều phòng rỗng sẽ đẩy
        ván đang đấu của người khác ra — ván đó mất trắng dù không ai động vào
        nó. Cắt phòng chờ trước thì ván đang đấu được bảo vệ ngay cả khi bị
        dồn phòng.
        """
        if len(self._order) <= self.capacity:
            return
        thu_tu = sorted(
            self._order,
            key=lambda rid: (
                self._rooms[rid].started,     # False (chờ) trước True (đang chơi)
                self._rooms[rid].created_at,
            ),
        )
        can_cut = len(self._order) - self.capacity
        for rid in thu_tu[:can_cut]:
            self._drop(rid)

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
        self._tao_luc = {}          # sổ thời điểm không gắn với phòng nào
        self._rooms.pop(room_id, None)
        self._locks.pop(room_id, None)
        self._listeners.pop(room_id, None)
        if room_id in self._order:
            self._order.remove(room_id)

    def _snapshot_or_hong(self, room: _Room) -> GameState:
        """Trạng thái ván, hoặc `GameNotFound` nếu ván đã biến mất."""
        return self.games.snapshot(room.game_id)

    def _view(self, room: _Room, token: str | None) -> RoomView:
        # Kiểm ván còn không, kể cả lúc phòng CHƯA bắt đầu: ván có thể biến
        # mất bất cứ lúc nào, và phòng mà mất ván thì phải bị coi là hỏng.
        # `exists` rẻ hơn `snapshot` nên `list()` vẫn không tốn.
        if not self.games.exists(room.game_id):
            raise GameNotFound(room.game_id)
        state = self._snapshot_or_hong(room) if room.started else None
        you = room.seat_of(token)
        doi = room.other(token) if you else None
        return RoomView(
            id=room.id,
            seat_white=room.white is not None,
            seat_black=room.black is not None,
            host_is_you=(token is not None and room.host == token),
            you_in_room=you is not None,
            you=you,
            started=room.started,
            finished=bool(state.over) if state is not None else False,
            result_text=state.result_text if state is not None else None,
            connected=(token in room.connected) if token is not None else False,
            opponent_connected=(doi in room.connected) if doi else True,
            status=self._status(room, state),
            created_at=room.created_at,
        )

    @staticmethod
    def _status(room: _Room, state: GameState | None) -> str:
        if state is not None and state.over:
            return "Xong"
        if room.started:
            return "Đang đấu"
        if room.white and room.black:
            return "Sẵn sàng"
        if room.white or room.black:
            return "Chờ đối thủ"
        return "Chờ người"

    def view(self, room_id: str, token: str | None = None) -> RoomView:
        with self._lock(room_id):
            room = self._require(room_id)
            try:
                return self._view(room, token)
            except GameNotFound:
                # Ván biến mất (máy chủ restart, hoặc bị cắt sai) — phòng này
                # hỏng thật, phải bỏ đi chứ không để lỗi lọt ra ngoài.
                # `GameNotFound` KHÔNG phải `RoomError`, nên nếu lọt ra nó sẽ
                # làm hỏng cả danh sách phòng, không chỉ phòng này.
                self._drop(room_id)
                raise NotFound() from None

    def list(self, token: str | None = None) -> list[RoomView]:
        with self._guard:
            ids = list(self._order)
        ket_qua: list[RoomView] = []
        for rid in ids:
            try:
                ket_qua.append(self.view(rid, token))
            except NotFound:
                continue          # phòng hỏng: bỏ qua, không làm hỏng cả danh sách
        return ket_qua

    def game_id_of(self, room_id: str) -> str:
        with self._lock(room_id):
            return self._require(room_id).game_id

    def state(self, room_id: str, token: str | None = None) -> dict:
        """Cặp (phòng, ván) đọc trong MỘT lần giữ khoá.

        Tách thành hai lệnh `view` + `snapshot` thì có thể ghép phòng thời điểm
        T1 với ván thời điểm T2 — và phòng bị bỏ giữa hai lúc thì ném lỗi ra
        ngoài. Đây là dữ liệu WebSocket và dự phòng poll đều dùng.
        """
        with self._lock(room_id):
            room = self._require(room_id)
            try:
                return {
                    "room": self._view(room, token).as_dict(),
                    "game": self._snapshot_or_hong(room).model_dump(),
                }
            except GameNotFound:
                self._drop(room_id)
                raise NotFound() from None

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
        with self._guard:
            self._kiem_quota(host_token)
        # `protected=True`: ván phòng không được cắt khi trần bộ nhớ đầy, và
        # `POST /api/game/{id}/...` phải từ chối nó.
        game_id = self.games.create(None, protected=True)
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
            self._cat_binh_ho_phong()
        self._notify(room_id)
        return room_id

    def _chuan_hoa_host(self, room: _Room) -> None:
        """Host phải là người ĐANG NGỒI ghế.

        Nếu host rời phòng mà `host` vẫn trỏ về token của họ, thì người còn lại
        bấm "Bắt đầu" sẽ bị từ chối vĩnh viễn — phòng treo không ai cứu được.
        """
        if room.host is not None and room.seat_of(room.host) is not None:
            return
        room.host = room.white or room.black

    def join(self, room_id: str, token: str) -> RoomView:
        with self._lock(room_id):
            room = self._require(room_id)
            if room.seat_of(token) is not None:
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
                self._chuan_hoa_host(room)
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
            self._chuan_hoa_host(room)
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
        seat = room.seat_of(token)
        if seat is None:
            raise NotInRoom()
        return seat

    def move(self, room_id: str, token: str, san: str) -> tuple[RoomView, GameState]:
        with self._lock(room_id):
            room = self._require(room_id)
            if not room.started:
                raise NotStarted()
            seat = self._seat_of(room, token)
            state = self._snapshot_or_hong(room)
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
            # Chặn đầu hàng lúc chưa bắt đầu: ván sẽ thành "xong" vĩnh viễn
            # mà không ai xoá được, phòng treo.
            if not room.started:
                raise NotStarted()
            seat = self._seat_of(room, token)
            color = chess.WHITE if seat == "white" else chess.BLACK
            self.games.session(room.game_id).resign(color)
            state = self._snapshot_or_hong(room)
            view = self._view(room, token)
        self._notify(room_id)
        return view, state

    def forfeit(self, room_id: str, token: str) -> tuple[RoomView, GameState]:
        """Kết thúc ván vì đối thủ biến mất (C6).

        Không có cách này thì đối thủ chỉ cần đóng tab là cả ván treo: người
        còn lại không thể đầu hàng (đó là thua), và host cũng chẳng làm được
        gì nếu không có nút chơi lại.
        """
        with self._lock(room_id):
            room = self._require(room_id)
            if not room.started:
                raise NotStarted()
            self._seat_of(room, token)
            state = self._snapshot_or_hong(room)
            if state.over:
                raise GameOver()
            doi = room.other(token)
            if doi is None or doi in room.connected:
                raise OpponentOnline()
            # `Session.resign` nhận MÀU (WHITE/BLACK), không phải token —
            # truyền nhầm token sẽ khiến mọi token khác đều thành "Trắng".
            mau = chess.WHITE if doi == room.white else chess.BLACK
            self.games.session(room.game_id).resign(mau)
            new_state = self._snapshot_or_hong(room)
            view = self._view(room, token)
        self._notify(room_id)
        return view, new_state


# Bảng chữ cái và độ dài: 31 ký hiệu, 8 ký tự ≈ 2^40 — đủ để link ngắn mà khó
# đoán. Đây là CHE MỜ, không phải bí mật: bí mật thật là mã người chơi (2^128)
# trong `localStorage`, và nó không bao giờ rời máy chủ.

class PhongChoi(RoomError):
    """Ván thuộc về một phòng — phải dùng route của phòng, không phải
    `POST /api/game/{id}/...` (lệnh đó không có token, không kiểm ghế)."""

    status_code = 400

    def __init__(self) -> None:
        super().__init__("Ván này thuộc một phòng chơi — hãy dùng nút trong phòng.")

