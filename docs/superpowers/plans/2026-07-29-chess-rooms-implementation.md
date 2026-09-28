# Phòng chơi người thật (#3C) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or
> superpowers:subagent-driven-development) to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hai người mở cùng máy chủ, vào cùng một phòng, đấu với nhau trên bàn
cờ web đã có — có danh sách phòng, phòng chờ, nút mời bằng link, và cập nhật
qua WebSocket.

**Architecture:** `chessai/web/rooms.py` giữ phòng trong RAM, mỗi phòng trỏ tới
một `game_id` của `GameStore` sẵn có. Lệnh đi qua HTTP POST (luật cờ vua giữ ở
một chỗ); WebSocket **chỉ chiều máy chủ → trình duyệt** để đẩy trạng thái, có
dự phòng bằng poll nếu WebSocket không mở. `Session.human_color` của ván trong
phòng luôn là `None` nên `AIController` không can thiệp.

**Tech Stack:** FastAPI + WebSocket (`websockets` **đã cài sẵn**), pydantic,
`threading`, HTML/CSS/JS thuần. Không thêm gói, không bước build.

**Spec:** `docs/superpowers/specs/2026-09-29-chess-rooms-design.md`

## Global Constraints

- **Không thêm phụ thuộc.** `websockets` đã có sẵn — đã kiểm bằng `import`.
- **Máy chủ giữ toàn bộ luật cờ vua; trình duyệt KHÔNG có một dòng luật cờ vua.**
- **Mọi thông điệp người thấy bằng tiếng Việt có dấu.**
- **Khoá theo từng ván, giữ ngắn.** Không giữ khoá qua lúc tìm nước.
- **Không có "Lùi 1 lượt" trong phòng** (đặc tả C4). Route phải từ chối.
- **296 test của #1/#3A/#3B phải xanh.**
- **Dòng cờ phải chạy thật qua python-chess** để xác minh — không viết từ trí nhớ.
  (Đã vấp 3 lần ở #3B.)
- **Ghi `Ruling:` vào ledger** cho mọi quyết định lệch khỏi plan.

## Review Focus

Năm điều dưới đây là loại lỗi mà đặc tả hứa nhưng test tự nhiên dễ bỏ sót, và
sẽ làm người chơi thấy sai:

1. **Người thứ ba đi nước thay người đã vào phòng.** Nếu token kiểm chỉ ở
   middleware mà route không so với ghế, thì bất kỳ ai giả token cũng đi được.
2. **Ván đi nước đúng thứ tự nhưng sai người** — phải chặn theo **ghế**, không
   chỉ theo `turn`.
3. **Hai người không thấy nước của nhau** — WebSocket chỉ đẩy cho người vừa
   đi, thì người kia đứng yên mãi.
4. **Người chơi Đen thấy bàn không xoay** trong phòng (nếu chỉ xoay cho AI).
5. **"Bắt đầu" sử dụng được khi chưa đủ hai người** — vào phòng một mình rồi bấm
   thì vào ván với một ghế trống.

---

### Task 1: `RoomStore` — phòng trong RAM

**Files:**
- Create: `chessai/web/rooms.py`
- Test: `tests/test_rooms.py`

**Interfaces:**
- Consumes: `GameStore` (Task #3A) — `create`, `snapshot`, `submit`, `new_game`,
  `session`, `_lock` (chỉ dùng `create`/`snapshot`/`new_game`)
- Produces:
  - `class RoomError(Exception)` — lỗi nghiệp vụ, có `.http_status` và message tiếng Việt
  - `class NotFound(RoomError)` — 404, `.status_code = 404`
  - `class Full(RoomError)` — 409
  - `class NotHost(RoomError)` — 403
  - `class NotEnough(RoomError)` — 400
  - `class NotStarted(RoomError)` — 400
  - `class NotYourTurn(RoomError)` — 400
  - `class RoomView(BaseModel)` — `id, status, white, black, host, started, finished, result_text, you, connected`
  - `class RoomStore` — `__init__(self, games: GameStore, capacity: int = 200)`,
    `.create(host_token) -> str`, `.join(room_id, token) -> RoomView`,
    `.view(room_id, token=None) -> RoomView`, `.start(room_id, token) -> RoomView`,
    `.move(room_id, token, san) -> tuple[RoomView, GameState]`,
    `.resign(room_id, token) -> tuple[RoomView, GameState]`,
    `.rematch(room_id, token) -> RoomView`, `.leave(room_id, token) -> RoomView`,
    `.list(token=None) -> list[RoomView]`, `.set_connected(room_id, token, value) -> None`

- [ ] **Step 1: Viết test đỏ — `tests/test_rooms.py`**

```python
"""Phòng chơi: ghế, quyền host, và nối sang ván của GameStore."""

import unittest

import chess

from chessai.web.games import GameStore
from chessai.web.rooms import (
    Full, NotEnough, NotFound, NotHost, RoomStore,
)

AL = "nguoi-a"
BL = "nguoi-b"
CC = "nguoi-c"


def bo() -> tuple[RoomStore, GameStore]:
    games = GameStore()
    return RoomStore(games), games


def _play(rooms: RoomStore, gid: str, token: str, *sans: str) -> None:
    for san in sans:
        rooms.move(gid, token, san)


class TestGhe(unittest.TestCase):
    def test_tao_phong_thi_hai_ghe_trong(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        view = rooms.view(rid, AL)
        self.assertIsNone(view.white)
        self.assertIsNone(view.black)
        self.assertEqual(view.host, AL)
        self.assertFalse(view.started)
        self.assertEqual(view.you, None)

    def test_vao_thi_nguoi_trong_di_ghe_trang(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        view = rooms.join(rid, BL)
        self.assertEqual(view.white, BL)
        self.assertIsNone(view.black)
        self.assertEqual(view.you, "white")

    def test_nguoi_thu_hai_di_ghe_den(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        view = rooms.join(rid, CC)
        self.assertEqual(view.black, CC)
        self.assertEqual(view.you, "black")

    def test_phong_day_hai_nguoi_thi_ba_nguoi_bi_tu_choi(self) -> None:
        """Review Focus: người thứ ba không được chen vào phòng."""
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        with self.assertRaises(Full):
            rooms.join(rid, CC)

    def test_vao_lai_phong_da_vao_thi_tra_ve_cho_cu(self) -> None:
        """Tải lại trang là việc bình thường, không được coi là lỗi."""
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        view = rooms.join(rid, BL)
        self.assertEqual(view.white, BL)
        self.assertIsNone(view.black)

    def test_roi_phong_thi_ghe_trong_lai(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        view = rooms.leave(rid, BL)
        self.assertIsNone(view.white)
        self.assertEqual(view.host, AL)

    def test_phong_khong_ton_tai(self) -> None:
        rooms, games = bo()
        with self.assertRaises(NotFound):
            rooms.view("khongco")

    def test_ma_phong_khong_de_ky_tu_nham(self) -> None:
        """Đọc to ra cho người khác thì dễ nhầm l/o/i/0/1."""
        rooms, games = bo()
        rid = rooms.create(AL)
        self.assertEqual(len(rid), 8)
        self.assertFalse(set(rid) & set("loi01"), rid)

    def test_ma_phong_khac_nhau(self) -> None:
        rooms, games = bo()
        self.assertEqual(len({rooms.create(AL) for _ in range(50)}), 50)


class TestQuyen(unittest.TestCase):
    def _hai_nguoi(self):
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        return rooms, rid

    def test_khong_phai_host_thi_bam_bat_dau_bi_tu_choi(self) -> None:
        rooms, rid = self._hai_nguoi()
        with self.assertRaises(NotHost):
            rooms.start(rid, BL)

    def test_chua_du_hai_nguoi_thi_khong_bat_dau_duoc(self) -> None:
        """Review Focus 5: một mình bấm "Bắt đầu" thì vào ván với ghế trống."""
        rooms, games = bo()
        rid = rooms.create(AL)
        with self.assertRaises(NotEnough):
            rooms.start(rid, AL)

    def test_host_bat_dau_duoc_khi_du_hai_nguoi(self) -> None:
        rooms, rid = self._hai_nguoi()
        view = rooms.start(rid, AL)
        self.assertTrue(view.started)
        self.assertEqual(view.status, "Đang đấu")

    def test_chua_bat_dau_thi_di_nuoc_bi_tu_choi(self) -> None:
        from chessai.web.rooms import NotStarted
        rooms, rid = self._hai_nguoi()
        with self.assertRaises(NotStarted):
            rooms.move(rid, AL, "e4")

    def test_di_nuoc_thay_nguoi_khong_co_ghe_bi_tu_choi(self) -> None:
        """Review Focus 1: token lạ không được đi nước thay người đã vào."""
        from chessai.web.rooms import NotInRoom
        rooms, rid = self._hai_nguoi()
        rooms.start(rid, AL)
        with self.assertRaises(NotInRoom):
            rooms.move(rid, CC, "e4")

    def test_di_nuoc_cho_khong_phai_luot_gi(self) -> None:
        """Review Focus 2: phải chặn theo GHẾ, không chỉ theo lượt."""
        from chessai.web.rooms import NotYourTurn
        rooms, rid = self._hai_nguoi()
        rooms.start(rid, AL)
        rooms.move(rid, AL, "e4")
        with self.assertRaises(NotYourTurn):
            rooms.move(rid, AL, "e5")
        rooms.move(rid, BL, "e5")
        self.assertEqual(rooms.games.snapshot(rooms.game_id_of(rid)).moves, ["e4", "e5"])


class TestChoiThat(unittest.TestCase):
    def _hai_nguoi(self):
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        rooms.start(rid, AL)
        return rooms, rid

    def test_di_nuoc_hop_le_thi_vao_lich_su(self) -> None:
        rooms, rid = self._hai_nguoi()
        view, state = rooms.move(rid, AL, "e4")
        self.assertEqual(state.moves, ["e4"])
        self.assertEqual(state.turn, "black")

    def test_van_xong_thi_khong_di_duoc(self) -> None:
        from chessai.web.rooms import GameOver
        rooms, rid = self._hai_nguoi()
        _play(rooms, rid, AL, "f3", "e5", "g4", "Qh4#", "Nxf4")
        with self.assertRaises(GameOver):
            rooms.move(rid, BL, "Nxf4")

    def test_dau_hang_thi_ket_qua_dung_nguoi(self) -> None:
        rooms, rid = self._hai_nguoi()
        view, state = rooms.resign(rid, BL)
        self.assertTrue(state.over)
        self.assertIn("Trắng thắng", state.result_text)
        self.assertTrue(view.finished)

    def test_phong_hoi_lai_thi_giu_dung_lich_su_cu(self) -> None:
        rooms, rid = self._hai_nguoi()
        rooms.move(rid, AL, "e4")
        view = rooms.rematch(rid, AL)
        self.assertEqual(view.started, False)
        self.assertEqual(rooms.games.snapshot(rooms.game_id_of(rid)).moves, [])

    def test_trang_thai_ket_noi(self) -> None:
        rooms, rid = self._hai_nguoi()
        self.assertTrue(rooms.view(rid, AL).connected)
        rooms.set_connected(rid, AL, False)
        view = rooms.view(rid, AL)
        self.assertFalse(view.connected)

    def test_biet_doi_thu_co_ngon_tai_khong(self) -> None:
        """`connected` là của chính người gọi; `opponent_connected` mới là của
        đối thủ — nhầm hai cái thì mất kết nối của nhau sẽ không bao giờ hiện."""
        rooms, rid = self._hai_nguoi()
        self.assertTrue(rooms.view(rid, AL).opponent_connected)
        rooms.set_connected(rid, BL, False)
        self.assertFalse(rooms.view(rid, AL).opponent_connected)
        # Người bị mất kết nối thì vẫn thấy đối thủ đang nối
        self.assertTrue(rooms.view(rid, BL).opponent_connected)
        # Người ngoài phòng thì không có ý kiến gì
        self.assertTrue(rooms.view(rid, CC).opponent_connected)


class TestDanhSach(unittest.TestCase):
    def test_danh_sach_co_phong_vua_tao(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        danh = rooms.list()
        self.assertEqual([v.id for v in danh], [rid])
        self.assertEqual(danh[0].status, "Sẵn sàng")

    def test_phong_day_nguoi_thi_van_hien_de_roi(self) -> None:
        """Phòng đã đủ hai người thì người thứ ba không vào được, nên vẫn nên
        thấy trong danh sách để biết đang bận."""
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        self.assertEqual(rooms.list()[0].status, "Sẵn sàng")

    def test_tran_so_phong_thi_phong_cu_bi_bo(self) -> None:
        games = GameStore()
        rooms = RoomStore(games, capacity=2)
        a = rooms.create(AL)
        b = rooms.create(AL)
        c = rooms.create(AL)
        with self.assertRaises(NotFound):
            rooms.view(a)
        rooms.view(c)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `python -m unittest tests.test_rooms`
Expected: `ModuleNotFoundError: No module named 'chessai.web.rooms'`

- [ ] **Step 3: Viết `chessai/web/rooms.py`**

```python
"""Phòng chơi người thật. Mọi thứ nằm trong RAM — mất hết khi máy chủ dừng.

Mỗi phòng có một `game_id` trỏ vào `GameStore`, và `human_color` của ván đó
LUÔN là `None` (không có AI trong phòng) — nên `AIController` không can thiệp
và `Session` không chặn lượt; việc chặn lượt là của tầng này, theo **ghế**.
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


class NoUndo(RoomError):
    def __init__(self) -> None:
        super().__init__("Trong phòng không có nút lùi nước.")


class RoomView:
    """Thông tin công khai của một phòng, đã cắt bớt cho người gọi."""

    __slots__ = ("id", "white", "black", "host", "started", "finished",
                 "result_text", "you", "connected", "opponent_connected",
                 "created_at")

    def __init__(self, **kw) -> None:
        for ten in self.__slots__:
            setattr(self, ten, kw.get(ten))

    def as_dict(self) -> dict:
        return {ten: getattr(self, ten) for ten in self.__slots__
                if ten != "created_at"}

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
        # Ghế của ĐỐI THỦ: người gọi cần biết họ còn nối không. `connected` là
        # của chính người gọi, dùng cho phòng chờ; `opponent_connected` mới là
        # thứ trình duyệt hiện "đối thủ mất kết nối".
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

    # ---- thao tác phòng ---------------------------------------------

    def create(self, host_token: str) -> str:
        game_id = self.games.create(None)          # human_color=None: hai người
        room_id = self._new_id()
        with self._guard:
            self._rooms[room_id] = _Room(room_id, game_id, host_token)
            self._locks[room_id] = threading.Lock()
            self._order.append(room_id)
            while len(self._order) > self.capacity:
                self._drop(self._order[0])
        return room_id

    def join(self, room_id: str, token: str) -> RoomView:
        with self._lock(room_id):
            room = self._require(room_id)
            if room.white == token or room.black == token:
                return self._view(room, token)     # vào lại: trả về chỗ cũ
            if room.white is None:
                room.white = token
            elif room.black is None:
                room.black = token
            else:
                raise Full()
            room.connected.add(token)
            return self._view(room, token)

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
            return self._view(room, token)

    def start(self, room_id: str, token: str) -> RoomView:
        with self._lock(room_id):
            room = self._require(room_id)
            if room.host != token:
                raise NotHost()
            if room.white is None or room.black is None:
                raise NotEnough()
            room.started = True
            return self._view(room, token)

    def rematch(self, room_id: str, token: str) -> RoomView:
        with self._lock(room_id):
            room = self._require(room_id)
            if room.host != token:
                raise NotHost()
            if room.white is None or room.black is None:
                raise NotEnough()
            self.games.new_game(room.game_id)
            room.started = False
            return self._view(room, token)

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
            # Chặn theo GHẾ, không chỉ theo lượt — và so với `turn` của ván.
            if seat != state.turn:
                raise NotYourTurn()
            new_state = self.games.submit(room.game_id, san)
            return self._view(room, token), new_state

    def resign(self, room_id: str, token: str) -> tuple[RoomView, GameState]:
        with self._lock(room_id):
            room = self._require(room_id)
            seat = self._seat_of(room, token)
            color = chess.WHITE if seat == "white" else chess.BLACK
            self.games.session(room.game_id).resign(color)
            state = self.games.snapshot(room.game_id)
            return self._view(room, token), state


# Bảng chữ cái và độ dài: đã kiểm 31 ký hiệu, 8 ký tự ≈ 2^40 — đủ để link
# ngắn mà khó đoán. Đây là CHE MỜ, không phải bí mật: bí mật thật là mã người
# chơi (2^128) trong `localStorage`.
```

- [ ] **Step 4: Chạy, kỳ vọng PASS**

Run: `python -m unittest tests.test_rooms`
Expected: `Ran 31 tests ... OK`

Nếu `TestChoiThat.test_van_xong_thi_khong_di_duoc` đỏ, kiểm lại dòng cờ bằng
python-chess trước khi sửa — đừng đoán.

- [ ] **Step 5: Chạy cả bộ**

Run: `python -m unittest`
Expected: `Ran 327 tests ... OK`

- [ ] **Step 6: Commit**

```bash
git add chessai/web/rooms.py tests/test_rooms.py
git commit -m "feat(web): add in-memory room store with seats and turn checks"
```

---

### Task 2: Route phòng + WebSocket đẩy trạng thái

**Files:**
- Modify: `chessai/web/app.py`
- Test: `tests/test_web_rooms.py`

**Interfaces:**
- Consumes: `RoomStore` (Task 1), `MoveRequest` (#3A), `GameState` (#3A)
- Produces: route và WebSocket theo đặc tả §5; app lấy thêm tham số
  `rooms: RoomStore | None = None`

- [ ] **Step 1: Viết test đỏ — `tests/test_web_rooms.py`**

```python
"""Route phòng: mã HTTP và thông điệp tiếng Việt."""

import json
import unittest

from chessai.web.app import create_app
from chessai.web.games import GameStore
from chessai.web.rooms import RoomStore

AL = "nguoi-a"
BL = "nguoi-b"
CC = "nguoi-c"


class TestPhong(unittest.TestCase):
    def setUp(self) -> None:
        self.games = GameStore()
        self.rooms = RoomStore(self.games)
        self.app = create_app(self.games, rooms=self.rooms)

    def call(self, method: str, path: str, token: str | None = None, **kw):
        endpoint, params = self.match(method, path)
        if token is not None:
            kw["token"] = token
        return endpoint(**params, **kw)

    def match(self, method: str, path: str):
        import re
        for route in self.app.routes:
            template = getattr(route, "path", None)
            if template is None or method not in getattr(route, "methods", set()):
                continue
            escaped = re.escape(template)
            names = re.findall(r"\\\{([^}]+)\\\}", escaped)
            found = re.fullmatch(
                re.sub(r"\\\{[^}]+\\\}", "([^/]+)", escaped), path
            )
            if found:
                return route.endpoint, dict(zip(names, found.groups()))
        raise AssertionError(f"khong tim thay route {method} {path}")

    def body(self, response) -> dict:
        return json.loads(response.body)

    def tao_phong(self, host: str = AL) -> str:
        return self.body(self.call("POST", "/api/rooms", host))["room_id"]

    def hai_nguoi(self):
        rid = self.tao_phong()
        self.call("POST", f"/api/rooms/{rid}/join", BL)
        self.call("POST", f"/api/rooms/{rid}/start", AL)
        return rid

    # ---- danh tính ---------------------------------------------------

    def test_me_cap_ma_nguoi_hoi_dai(self) -> None:
        a = self.body(self.call("GET", "/api/me"))["player"]
        b = self.body(self.call("GET", "/api/me"))["player"]
        self.assertNotEqual(a, b)
        self.assertGreaterEqual(len(a), 20)

    def test_thieu_ma_nguoi_hoi_thi_401(self) -> None:
        response = self.call("POST", "/api/rooms")
        self.assertEqual(response.status_code, 401)
        self.assertIn("tải lại trang", self.body(response)["error"])

    # ---- vòng đời phòng ----------------------------------------------

    def test_tao_phong_thi_201_va_co_ma_dai_8(self) -> None:
        response = self.call("POST", "/api/rooms", AL)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(self.body(response)["room_id"]), 8)

    def test_danh_sach_phong(self) -> None:
        rid = self.tao_phong()
        self.call("POST", f"/api/rooms/{rid}/join", BL)
        danh = self.body(self.call("GET", "/api/rooms"))
        self.assertEqual([r["id"] for r in danh["rooms"]], [rid])
        self.assertEqual(danh["rooms"][0]["status"], "Sẵn sàng")

    def test_phong_khong_ton_tai_thi_404(self) -> None:
        response = self.call("POST", "/api/rooms/khongco/join", BL)
        self.assertEqual(response.status_code, 404)
        self.assertIn("Phòng", self.body(response)["error"])

    def test_phong_day_thi_409(self) -> None:
        rid = self.tao_phong()
        self.call("POST", f"/api/rooms/{rid}/join", BL)
        response = self.call("POST", f"/api/rooms/{rid}/join", CC)
        self.assertEqual(response.status_code, 409)
        self.assertIn("đủ hai người", self.body(response)["error"])

    def test_bat_dau_khong_phai_host_thi_403(self) -> None:
        rid = self.tao_phong()
        self.call("POST", f"/api/rooms/{rid}/join", BL)
        response = self.call("POST", f"/api/rooms/{rid}/start", BL)
        self.assertEqual(response.status_code, 403)

    def test_bat_dau_thieu_nguoi_thi_400(self) -> None:
        rid = self.tao_phong()
        response = self.call("POST", f"/api/rooms/{rid}/start", AL)
        self.assertEqual(response.status_code, 400)
        self.assertIn("hai người", self.body(response)["error"])

    def test_view_phong_co_you_la_mau_cua_nguoi_goi(self) -> None:
        rid = self.hai_nguoi()
        self.assertEqual(self.body(self.call("GET", f"/api/rooms/{rid}", AL))["you"],
                         "white")
        self.assertEqual(self.body(self.call("GET", f"/api/rooms/{rid}", BL))["you"],
                         "black")

    # ---- chơi thật ---------------------------------------------------

    def test_di_nuoc_hop_le_thi_200(self) -> None:
        rid = self.hai_nguoi()
        response = self.call("POST", f"/api/rooms/{rid}/move", AL, san="e4")
        self.assertEqual(response.status_code, 200)
        state = self.body(response)
        self.assertEqual(state["game"]["moves"], ["e4"])
        self.assertEqual(state["game"]["turn"], "black")

    def test_di_nuoc_sai_luot_thi_400_va_ban_khong_doi(self) -> None:
        rid = self.hai_nguoi()
        self.call("POST", f"/api/rooms/{rid}/move", AL, san="e4")
        truoc = self.body(self.games.snapshot(self.rooms.game_id_of(rid)))["fen"]
        response = self.call("POST", f"/api/rooms/{rid}/move", AL, san="e5")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Chưa đến lượt bạn", self.body(response)["error"])
        self.assertEqual(
            self.body(self.games.snapshot(self.rooms.game_id_of(rid)))["fen"], truoc
        )

    def test_nguoi_la_thi_di_nuoc_bi_403(self) -> None:
        """Review Focus 1: token lạ không được đi nước thay người đã vào."""
        rid = self.hai_nguoi()
        response = self.call("POST", f"/api/rooms/{rid}/move", CC, san="e4")
        self.assertEqual(response.status_code, 403)

    def test_di_nuoc_khi_chua_bat_dau_thi_400(self) -> None:
        rid = self.tao_phong()
        self.call("POST", f"/api/rooms/{rid}/join", BL)
        response = self.call("POST", f"/api/rooms/{rid}/move", AL, san="e4")
        self.assertEqual(response.status_code, 400)
        self.assertIn("chưa bắt đầu", self.body(response)["error"])

    def test_phong_khong_cho_lui(self) -> None:
        """C4: trong phòng không có nút lùi nước."""
        rid = self.hai_nguoi()
        self.call("POST", f"/api/rooms/{rid}/move", AL, san="e4")
        response = self.call("POST", f"/api/rooms/{rid}/undo", AL)
        self.assertEqual(response.status_code, 400)
        self.assertIn("không có nút lùi", self.body(response)["error"])

    def test_dau_hang_thi_ket_qua_dung(self) -> None:
        rid = self.hai_nguoi()
        self.call("POST", f"/api/rooms/{rid}/move", AL, san="e4")
        response = self.call("POST", f"/api/rooms/{rid}/resign", AL)
        self.assertEqual(response.status_code, 200)
        state = self.body(response)["game"]
        self.assertTrue(state["over"])
        self.assertIn("Đen thắng", state["result_text"])

    def test_di_nuoc_khi_van_xong_thi_400(self) -> None:
        rid = self.hai_nguoi()
        self.call("POST", f"/api/rooms/{rid}/resign", AL)
        response = self.call("POST", f"/api/rooms/{rid}/move", BL, san="e5")
        self.assertEqual(response.status_code, 400)
        self.assertIn("đã kết thúc", self.body(response)["error"])

    def test_choi_lai_thi_xoa_lich_su(self) -> None:
        rid = self.hai_nguoi()
        self.call("POST", f"/api/rooms/{rid}/move", AL, san="e4")
        response = self.call("POST", f"/api/rooms/{rid}/rematch", AL)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.body(response)["started"])
        self.assertEqual(
            self.body(self.games.snapshot(self.rooms.game_id_of(rid)))["moves"], []
        )

    def test_roi_phong_thi_ghe_trong(self) -> None:
        rid = self.hai_nguoi()
        response = self.call("POST", f"/api/rooms/{rid}/leave", BL)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.body(response)["black"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `python -m unittest tests.test_web_rooms`
Expected: `AssertionError: khong tim thay route POST /api/rooms`

- [ ] **Step 3: Thêm route vào `chessai/web/app.py`**

Thêm import: `from fastapi import Header, WebSocket, WebSocketDisconnect` và
`from .rooms import RoomError, RoomStore`.

Đổi chữ ký `create_app`:

```python
def create_app(
    store: GameStore | None = None,
    ai: AIController | None = None,
    rooms: RoomStore | None = None,
) -> FastAPI:
    games = store if store is not None else GameStore()
    controller = ai if ai is not None else AIController(games)
    phong = rooms if rooms is not None else RoomStore(games)
```

Thêm các route (đặt trước `app.mount("/static", ...)`):

```python
    def _token(x_player: str | None) -> str:
        if not x_player or len(x_player) < 16:
            raise Unauthorized()
        return x_player

    @app.get("/api/me")
    def me() -> JSONResponse:
        return JSONResponse({"player": secrets.token_urlsafe(16)})

    @app.get("/api/rooms")
    def list_rooms(x_player: str | None = Header(default=None)) -> JSONResponse:
        token = _token(x_player)
        return JSONResponse({"rooms": [v.as_dict() for v in phong.list(token)]})

    @app.post("/api/rooms", status_code=201)
    def create_room(x_player: str | None = Header(default=None)) -> JSONResponse:
        token = _token(x_player)
        return JSONResponse({"room_id": phong.create(token)})

    @app.get("/api/rooms/{room_id}")
    def read_room(
        room_id: str, x_player: str | None = Header(default=None)
    ) -> JSONResponse:
        token = _token(x_player)
        return _guard(lambda: phong.view(room_id, token).as_dict())

    @app.post("/api/rooms/{room_id}/join")
    def join_room(
        room_id: str, x_player: str | None = Header(default=None)
    ) -> JSONResponse:
        token = _token(x_player)
        return _guard(lambda: phong.join(room_id, token).as_dict())

    @app.post("/api/rooms/{room_id}/leave")
    def leave_room(
        room_id: str, x_player: str | None = Header(default=None)
    ) -> JSONResponse:
        token = _token(x_player)
        return _guard(lambda: phong.leave(room_id, token).as_dict())

    @app.post("/api/rooms/{room_id}/start")
    def start_room(
        room_id: str, x_player: str | None = Header(default=None)
    ) -> JSONResponse:
        token = _token(x_player)
        return _guard(lambda: phong.start(room_id, token).as_dict())

    @app.post("/api/rooms/{room_id}/rematch")
    def rematch_room(
        room_id: str, x_player: str | None = Header(default=None)
    ) -> JSONResponse:
        token = _token(x_player)
        return _guard(lambda: phong.rematch(room_id, token).as_dict())

    @app.post("/api/rooms/{room_id}/move")
    def room_move(
        room_id: str, payload: MoveRequest, x_player: str | None = Header(default=None)
    ) -> JSONResponse:
        token = _token(x_player)
        return _guard(_phong_move, phong, room_id, token, payload.san)

    @app.post("/api/rooms/{room_id}/resign")
    def room_resign(
        room_id: str, x_player: str | None = Header(default=None)
    ) -> JSONResponse:
        token = _token(x_player)
        return _guard(_phong_resign, phong, room_id, token)

    @app.post("/api/rooms/{room_id}/undo")
    def room_undo(
        room_id: str, x_player: str | None = Header(default=None)
    ) -> JSONResponse:
        _token(x_player)
        return JSONResponse({"error": "Trong phòng không có nút lùi nước."},
                            status_code=400)
```

Thêm `Unauthorized` vào `rooms.py`:

```python
class Unauthorized(RoomError):
    status_code = 401

    def __init__(self) -> None:
        super().__init__("Chưa nhận diện được người chơi — tải lại trang.")
```

Và sửa `_guard` để bắt thêm `RoomError`:

```python
def _guard(action, *args) -> JSONResponse:
    try:
        result = action(*args)
    except GameNotFound as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except (MoveError, RoomError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status_code)
    return JSONResponse(jsonable_encoder(result))
```

Thêm hai hàm module-level (để `create_app` gọn):

```python
def _phong_move(phong, room_id, token, san) -> dict:
    view, state = phong.move(room_id, token, san)
    return {"room": view.as_dict(), "game": state.model_dump()}


def _phong_resign(phong, room_id, token) -> dict:
    view, state = phong.resign(room_id, token)
    return {"room": view.as_dict(), "game": state.model_dump()}
```

Thêm WebSocket (chỉ đẩy, không nhận lệnh):

```python
    @app.websocket("/ws/room/{room_id}")
    async def ws_room(websocket: WebSocket, room_id: str) -> None:
        token = websocket.query_params.get("p") or ""
        if len(token) < 16:
            await websocket.close(code=1008)
            return
        try:
            phong.view(room_id, token)
        except RoomError:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        phong.set_connected(room_id, token, True)
        try:
            await websocket.send_json(
                {"type": "state", "data": _room_state(phong, room_id, token)}
            )
            while True:
                # Máy chủ KHÔNG nhận lệnh qua đây — lệnh đi qua HTTP POST để
                # luật cờ vua chỉ nằm ở một chỗ. Vòng lặp này chỉ để giữ kết
                # nối mở và phát hiện client đã đóng.
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            phong.set_connected(room_id, token, False)


def _room_state(phong: RoomStore, room_id: str, token: str) -> dict:
    room = phong.view(room_id, token)
    out = {"room": room.as_dict(), "game": None}
    if room.started:
        out["game"] = phong.games.snapshot(phong.game_id_of(room_id)).model_dump()
    return out
```

**Bắt buộc thêm** cơ chế đẩy: sau mỗi lệnh phòng, máy chủ phải gửi trạng thái
mới cho mọi người. Thêm vào `RoomStore` một danh sách người đang nối và một
callback, rồi gọi nó ở `move`/`resign`/`join`/`leave`/`start`/`rematch`:

```python
# trong RoomStore.__init__
        self._listeners: dict[str, list] = {}

    def add_listener(self, room_id: str, send) -> None:
        with self._guard:
            self._listeners.setdefault(room_id, []).append(send)

    def remove_listener(self, room_id: str, send) -> None:
        with self._guard:
            danh = self._listeners.get(room_id) or []
            if send in danh:
                danh.remove(send)

    def _notify(self, room_id: str) -> None:
        with self._guard:
            nhan = list(self._listeners.get(room_id, ()))
        for send in nhan:
            try:
                send()
            except Exception:
                self.remove_listener(room_id, send)
```

Và trong mỗi hàm thao tác phòng, gọi `self._notify(room_id)` **trước khi
return** (sau khi đã thả khoá phòng — gọi `_notify` khi còn khoá sẽ khiến
`_room_state` tự khoá lại và tự treo).

- [ ] **Step 4: Chạy, kỳ vọng PASS**

Run: `python -m unittest tests.test_web_rooms`
Expected: `Ran 21 tests ... OK`

- [ ] **Step 5: Chạy cả bộ**

Run: `python -m unittest`
Expected: `Ran 348 tests ... OK`

- [ ] **Step 6: Commit**

```bash
git add chessai/web/app.py chessai/web/rooms.py tests/test_web_rooms.py
git commit -m "feat(web): add room routes and a server-push websocket"
```

---

### Task 3: Giao diện phòng chơi

**Files:**
- Modify: `chessai/web/static/index.html`
- Modify: `chessai/web/static/style.css`
- Modify: `chessai/web/static/app.js`
- Test: kiểm bằng trình duyệt (đặc tả §7.3)

**Interfaces:**
- Consumes: mọi route của Task 2; `GameState` của #3A (qua `/api/rooms/{id}/move`)
- Produces: ba màn trong `index.html`

- [ ] **Step 1: Thêm khung ba màn vào `index.html`**

Trong `<aside class="panel">`, trên đầu, thêm:

```html
    <nav class="tabs" id="tabs">
      <button data-view="home" class="on">Chơi</button>
      <button data-view="lobby">Phòng</button>
    </nav>

    <section class="view" id="view-home">
      <div class="home">
        <button id="play-ai" class="primary">Chơi với máy</button>
        <button id="play-rooms">Chơi với người</button>
        <button id="play-both">Hai bên</button>
      </div>
    </section>

    <section class="view" id="view-lobby" hidden>
      <div class="lobby">
        <button id="make-room" class="primary">Tạo phòng</button>
        <div class="join-row">
          <input id="room-code" placeholder="mã phòng" maxlength="8" autocomplete="off">
          <button id="join-code">Vào</button>
        </div>
        <ul class="room-list" id="room-list"></ul>
      </div>
    </section>

    <section class="view" id="view-room" hidden>
      <div class="waiting" id="waiting">
        <p class="room-code" id="room-code-big">—</p>
        <ul class="seats">
          <li><span class="dot white"></span> Trắng: <b id="seat-white">trống</b></li>
          <li><span class="dot black"></span> Đen: <b id="seat-black">trống</b></li>
        </ul>
        <div class="invite-row">
          <input id="invite" readonly>
          <button id="copy-invite">Sao chép link</button>
        </div>
        <p class="note" id="room-note"></p>
        <button id="start-room" class="primary" disabled>Bắt đầu</button>
      </div>
    </section>
```

Đổi nút `Lùi 1 lượt` thành `id="undo"` (giữ nguyên), thêm nút mới cạnh nó:

```html
      <button id="undo">Lùi 1 lượt</button>
      <button id="resign" hidden>Đầu hàng</button>
```

Thêm dòng trạng thái phòng ngay dưới `<p class="message">`:

```html
    <p class="room-status" id="room-status" hidden></p>
```

- [ ] **Step 2: Thêm kiểu vào `style.css`**

```css
/* ---- #3C: ba màn, danh sách phòng, phòng chờ ---- */
.tabs { display: flex; gap: 4px; margin-bottom: 10px; }
.tabs button {
  flex: 1; padding: 5px; font-size: 12px; cursor: pointer;
  background: var(--btn); color: var(--btn-fg);
  border: 1px solid var(--btn-border); border-radius: 4px;
}
.tabs button.on { background: #4a7dd6; border-color: #4a7dd6; color: #fff; }
.view[hidden] { display: none; }
.home { display: grid; gap: 6px; }
.home button, .lobby button, .waiting button {
  padding: 7px 8px; font-size: 13px; cursor: pointer;
  background: var(--btn); color: var(--btn-fg);
  border: 1px solid var(--btn-border); border-radius: 5px;
}
.home button.primary, .waiting button.primary { background: #4a7dd6; border-color: #4a7dd6; color: #fff; }
.home button.primary:disabled { opacity: .45; cursor: not-allowed; }
.join-row, .invite-row { display: flex; gap: 4px; margin-top: 6px; }
.join-row input, .invite-row input {
  flex: 1; min-width: 0; padding: 5px 6px; font-size: 12px;
  background: var(--page); color: var(--fg);
  border: 1px solid var(--btn-border); border-radius: 4px;
}
.room-list { list-style: none; margin: 8px 0 0; padding: 0; display: grid; gap: 4px; }
.room-list li {
  display: flex; align-items: center; gap: 6px; padding: 5px 7px;
  border: 1px solid var(--border); border-radius: 5px; font-size: 12px;
}
.room-list .ma { font-family: ui-monospace, monospace; font-weight: 600; }
.room-list .trang { margin-left: auto; color: var(--muted); }
.room-list button { padding: 3px 8px; font-size: 12px; }
.room-code { font-family: ui-monospace, monospace; font-size: 20px; text-align: center; margin: 0 0 8px; }
.seats { list-style: none; margin: 0 0 8px; padding: 0; display: grid; gap: 4px; font-size: 13px; }
.seats .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; border: 1px solid #888; }
.seats .dot.white { background: #f2f2f2; }
.seats .dot.black { background: #3a3f4a; }
.note { font-size: 12px; color: var(--muted); margin: 6px 0; }
.room-status { margin: 4px 0 0; font-size: 12px; color: var(--muted); }
.room-status.warn { color: #ffb45a; }
```

- [ ] **Step 3: Viết phần JavaScript**

Thêm vào đầu `app.js`:

```javascript
// ---- #3C: phòng chơi người thật ----
let playerToken = localStorage.getItem("chessai-player") || "";
let view = "home";           // "home" | "lobby" | "room" | "game"
let room = null;             // RoomView hiện tại
let socket = null;           // WebSocket
let socketTriedAt = 0;
let roomPollTimer = null;
```

Sửa `api()` để gửi mã người chơi, và thêm hàm riêng cho phòng:

```javascript
async function apiRoom(path, method = "GET", payload) {
  if (!playerToken) {
    const me = await api("/api/me", "GET");
    playerToken = me.player;
    localStorage.setItem("chessai-player", playerToken);
  }
  return api(path, method, payload, { "X-Player": playerToken });
}
```

Sửa chữ ký `api` để nhận thêm `extraHeaders`:

```javascript
async function api(path, method, payload, extraHeaders) {
  const options = { method, headers: { ...(extraHeaders || {}) } };
  // ... phần còn lại giữ nguyên
}
```

Các hàm hiển thị:

```javascript
function showView(ten) {
  view = ten;
  for (const id of ["home", "lobby", "room"]) {
    document.getElementById("view-" + id).hidden = id !== ten;
  }
  for (const b of document.querySelectorAll("#tabs button")) {
    b.classList.toggle("on", b.dataset.view === (ten === "game" ? "lobby" : ten));
  }
  const vanPhong = ten === "room" || ten === "game";
  el.setup.hidden = true;
  document.getElementById("undo").hidden = vanPhong;
  document.getElementById("resign").hidden = !vanPhong;
  el.roomStatus.hidden = !vanPhong;
  el.boardArea.classList.toggle("choi-phong", vanPhong);
}

function renderRoom() {
  if (!room) return;
  el.roomCodeBig.textContent = room.id;
  el.seatWhite.textContent = room.white ? "có người" : "trống";
  el.seatBlack.textContent = room.black ? "có người" : "trống";
  const link = location.origin + "/?room=" + room.id;
  el.invite.value = link;
  const laHost = room.host === playerToken;
  el.startRoom.disabled = !room.started && !(laHost && room.white && room.black);
  el.startRoom.textContent = room.started ? "Ván đang đấu" : "Bắt đầu";
  const ghe = room.you === "white" ? "Trắng" : room.you === "black" ? "Đen" : null;
  el.roomNote.textContent = !ghe
    ? "Bạn đang xem phòng của người khác."
    : room.started
      ? `Bạn đánh phe ${ghe}.`
      : (laHost ? "Bạn là người tạo phòng — chờ đối thủ rồi bấm Bắt đầu." : "Chờ người tạo phòng bấm Bắt đầu.");
}

function renderLobby(danh) {
  el.roomList.innerHTML = "";
  if (danh.length === 0) {
    const li = document.createElement("li");
    li.textContent = "Chưa có phòng nào. Bấm “Tạo phòng” để mở một phòng.";
    el.roomList.appendChild(li);
    return;
  }
  for (const r of danh) {
    const li = document.createElement("li");
    const ma = document.createElement("span");
    ma.className = "ma";
    ma.textContent = r.id;
    const trang = document.createElement("span");
    trang.className = "trang";
    trang.textContent = r.status;
    const nut = document.createElement("button");
    nut.textContent = "Vào";
    nut.disabled = !r.white || !r.black ? false : (r.white === playerToken || r.black === playerToken);
    nut.addEventListener("click", () => vaoPhong(r.id));
    li.append(ma, trang, nut);
    el.roomList.appendChild(li);
  }
}
```

Nối WebSocket, có dự phòng poll:

```javascript
function openSocket(roomId) {
  closeSocket();
  if (!playerToken) return;
  try {
    const ws = new WebSocket(
      `${location.origin.replace(/^http/, "ws")}/ws/room/${roomId}?p=${encodeURIComponent(playerToken)}`
    );
    socket = ws;
    ws.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      if (msg.type !== "state") return;
      room = msg.data.room;
      if (msg.data.game) applyRoomGame(msg.data);
      renderRoom();
    };
    ws.onopen = () => { stopRoomPoll(); socketTriedAt = 0; };
    ws.onclose = () => {
      socket = null;
      if (view === "room" || view === "game") startRoomPoll();
    };
    ws.onerror = () => { /* onclose sẽ lo */ };
  } catch {
    startRoomPoll();
  }
}

function closeSocket() { if (socket) { try { socket.close(); } catch {} socket = null; } }

function startRoomPoll() {
  stopRoomPoll();
  roomPollTimer = setInterval(async () => {
    if (view !== "room" && view !== "game") return;
    try {
      room = await apiRoom(`/api/rooms/${room.id}`, "GET");
      renderRoom();
    } catch { /* thông báo đã hiện ở chỗ khác */ }
  }, 1000);
}

function stopRoomPoll() { if (roomPollTimer) { clearInterval(roomPollTimer); roomPollTimer = null; } }
```

Các hàm điều hướng:

```javascript
async function vaoPhong(roomId) {
  try {
    room = await apiRoom(`/api/rooms/${roomId}/join`, "POST");
    const url = new URL(location.href);
    url.searchParams.set("room", roomId);
    url.searchParams.delete("g");
    history.replaceState(null, "", url);
    showView("room");
    renderRoom();
    openSocket(roomId);
  } catch (error) {
    say(error.message, true);
    if (view !== "home") showView("lobby");
  }
}

async function moPhong() {
  try {
    const { room_id } = await apiRoom("/api/rooms", "POST");
    await vaoPhong(room_id);
  } catch (error) { say(error.message, true); }
}

async function taiDanhSach() {
  try {
    renderLobby((await apiRoom("/api/rooms", "GET")).rooms);
  } catch (error) { say(error.message, true); }
}

function applyRoomGame(data) {
  const g = data.game;
  // Bàn xoay theo ghế của người chơi, giống chế độ đấu máy.
  if (data.room.you === "black") orientation = "b";
  else if (data.room.you === "white") orientation = "w";
  state = {
    ...g,
    human_color: data.room.you,
    elo: 0,
    thinking: false,
  };
  selected = null;
  hidePicker();
  buildSquares();
  const cells = boardFromFen(state.fen);
  paintPieces(cells);
  paintBoard(cells);
  paintPanel();
  showInUrl(null);
  el.roomStatus.hidden = false;
  const doi = data.room.you === "white" ? data.room.black : data.room.white;
  const ketNoi = doi ? data.room.opponent_connected : true;
  el.roomStatus.textContent = g.over
    ? g.result_text
    : (state.turn === data.room.you
        ? "Đến lượt bạn."
        : (ketNoi ? "Đến lượt đối thủ." : "Đối thủ đang mất kết nối."));
  el.roomStatus.classList.toggle("warn", !g.over && !ketNoi);
}
```

Gắn sự kiện:

```javascript
document.getElementById("tabs").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-view]");
  if (!b) return;
  if (b.dataset.view === "lobby") { showView("lobby"); taiDanhSach(); return; }
  showView("home");
});

document.getElementById("play-rooms").addEventListener("click", () => {
  showView("lobby"); taiDanhSach();
});
document.getElementById("play-both").addEventListener("click", async () => {
  const next = await api("/api/game", "POST");
  showView("game");
  apply(next);
});
document.getElementById("make-room").addEventListener("click", moPhong);
document.getElementById("join-code").addEventListener("click", () => {
  const code = el.roomCode.value.trim().toLowerCase();
  if (code) vaoPhong(code);
});

Sửa dòng cuối cho đúng (nút trong danh sách phòng đã gắn sự kiện riêng):

```javascript
document.getElementById("start-room").addEventListener("click", async () => {
  try {
    room = await apiRoom(`/api/rooms/${room.id}/start`, "POST");
    renderRoom();
  } catch (error) { say(error.message, true); }
});
document.getElementById("copy-invite").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(el.invite.value);
    say("Đã sao chép link phòng.");
  } catch {
    el.invite.select();
    say("Không tự sao chép được — bạn tự copy ô link bên trên.");
  }
});
document.getElementById("resign").addEventListener("click", async () => {
  if (view !== "game") return;
  try {
    const data = await apiRoom(`/api/rooms/${room.id}/resign`, "POST");
    applyRoomGame(data);
  } catch (error) { say(error.message, true); }
});
```

Trong `apply()` của #3B, chèn vào đầu:

```javascript
  if (view === "room" || view === "game") return;   // phòng dùng applyRoomGame
```

Và ở cuối file, đổi bootstrap thành:

```javascript
buildSquares();

const roomTrongUrl = new URLSearchParams(location.search).get("room");
if (roomTrongUrl) {
  try {
    room = await apiRoom(`/api/rooms/${roomTrongUrl}`, "GET");
    await vaoPhong(roomTrongUrl);
  } catch (error) {
    say(error.message, true);
    showView("home");
  }
} else {
  try {
    apply(await loadOrCreateGame());
  } catch (error) {
    say(error.message, true);
  }
}
```

Cuối cùng, thêm các phần tử mới vào `el` và bảo đảm `el.boardArea` tồn tại
(đặt `id="board-area"` trong `index.html`):

```javascript
  boardArea: document.getElementById("board-area"),
  roomStatus: document.getElementById("room-status"),
  roomCode: document.getElementById("room-code"),
  roomCodeBig: document.getElementById("room-code-big"),
  seatWhite: document.getElementById("seat-white"),
  seatBlack: document.getElementById("seat-black"),
  invite: document.getElementById("invite"),
  roomNote: document.getElementById("room-note"),
  startRoom: document.getElementById("start-room"),
  roomList: document.getElementById("room-list"),
  resign: document.getElementById("resign"),
```

- [ ] **Step 4: Chạy test, kỳ vọng PASS**

Run: `python -m unittest`
Expected: `Ran 348 tests ... OK`

Run: `node --check chessai/web/static/app.js`
Expected: không xuất

- [ ] **Step 5: Kiểm bằng trình duyệt (đặc tả §7.3)**

Chạy `python -m chessai.web`, mở `http://127.0.0.1:8000`. Kiểm 8 mục:

1. Bấm "Chơi với người" → thấy danh sách phòng, nút "Tạo phòng".
2. Tạo phòng → URL có `?room=`, hiện mã phòng 8 ký tự, link mời, hai ghế trống.
3. Mở **tab thứ hai** cùng link → tab một báo đủ 2 người, nút "Bắt đầu" bật.
4. Bấm "Bắt đầu" ở tab một → cả hai tab có bàn cờ, **mỗi tab xoay đúng phe**,
   tab Đen có hàng 8 ở dưới.
5. Ở tab Trắng đi `e4` → nước đó hiện ở **tab Đen** mà không tải lại.
6. Ở tab Trắng thử đi tiếp khi chưa tới lượt → "Chưa đến lượt bạn.", bàn không đổi.
7. Bấm "Đầu hàng" → cả hai tab thấy kết quả.
8. Đóng tab thứ hai → tab còn lại thấy "đối thủ đang mất kết nối".
9. Console: **0 lỗi**.

Nếu mục nào sai, **sửa `app.js` và kiểm lại mục đó**. Không sang Task 4.

- [ ] **Step 6: Commit**

```bash
git add chessai/web/static
git commit -m "feat(web): add room list, waiting room and realtime board"
```

---

## Kiểm lại toàn nhánh

Sau khi cả 3 task xong, chạy một vòng review bằng ngữ cảnh tươi trên toàn bộ
nhánh, rồi ghi kết quả vào
`.superpowers/sdd/2026-07-29-chess-rooms-implementation/progress.md`.

**Lưu ý khi review:** nói rõ với reviewer rằng mọi thứ nằm trong RAM và chỉ
chạy được trong một tiến trình máy chủ — đó là quyết định có chủ ý của đặc tả
§8, không phải sơ suất.
