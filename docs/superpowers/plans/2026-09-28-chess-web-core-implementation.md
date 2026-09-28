# Chess Web Core (#3A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng bàn cờ cờ vua chạy trên trình duyệt, máy chủ Python giữ toàn bộ luật FIDE, chơi hai bên trong một trình duyệt.

**Architecture:** FastAPI phục vụ một trang tĩnh + API JSON. `games.py` là nơi duy nhất giữ ván đấu; nó biến `chessai.Session` thành DTO gửi cho trình duyệt. Trình duyệt **không có một dòng luật cờ vua nào** — máy chủ gửi sẵn danh sách nước hợp lệ dạng `{from_sq, to_sq}`, trình duyệt chỉ khớp chuỗi với ô người dùng bấm.

**Tech Stack:** Python 3.13 · FastAPI 0.138 + uvicorn 0.40 + pydantic 2.12 (đều đã cài) · `python-chess==1.999` · HTML/CSS/JS thuần, **không có bước build** · `unittest` stdlib

**Spec:** `docs/superpowers/specs/2026-09-28-chess-web-core-design.md`

**Nhánh:** tạo `feature/chess-web` từ `feature/chess-core`. **Không merge** `feature/chess-core` vào `master` giữa chừng. Remote `origin` đã thêm nhưng **không push** — không được push nếu chưa được yêu cầu.

## Global Constraints

- **Không thêm dependency nào.** Mọi thứ dùng đều đã có sẵn. Nếu phát hiện cần cài gì mới thì **dừng lại hỏi**, đừng tự cài.
- **Không dùng `fastapi.testclient.TestClient`** — máy này không có `httpx` (đã kiểm: `ModuleNotFoundError`; cái đang cài tên là `httpx2`, tên khác). Test gọi thẳng handler qua `asyncio.run(handler(...))` và kiểm `JSONResponse.status_code` / `.body`.
- **Không dùng `Board.captured_pieces`** — thuộc tính này không tồn tại trong bản đang cài (đã kiểm: `AttributeError`). Phải quét `move_stack`.
- **Không dùng `exception_handler` của FastAPI** cho lỗi ván. Nó chỉ chạy qua ASGI stack, còn test gọi thẳng hàm — dùng nó khiến test im lặng bỏ qua. Mọi lỗi phải bắt bằng `try/except` trong thân handler.
- **Trình duyệt không chứa luật cờ vua.** Không `chess.js`, không hàm kiểm tra luật, không phân tích chuỗi SAN.
- Thông điệp người dùng thấy **tiếng Việt có dấu**, lấy nguyên văn từ `Position`/`Session` — không viết lại thông báo nào.
- Task 4 (giao diện) **không dùng TDD** vì không cài framework test JS. Xem mục đó.
- Mỗi task kết thúc bằng một commit. Không commit `node_modules`, `__pycache__`, `.superpowers/`.
- Chạy mọi lệnh từ `D:\DuAnCaNhan\Chess_ai`.

### API `python-chess` đã kiểm chạy thật

| Kiện | Kết quả kiểm chứng |
|---|---|
| `Move.from_square` / `.to_square` | `e4` → `e2`→`e4`; `O-O` → `e1`→`g1`; `exd6` → `e5`→`d6` |
| `Move.promotion` | `a8=Q` → `5`; nước thường → `None`. `chess.QUEEN == 5` |
| `board.is_capture/is_castling/is_en_passant` | đều tồn tại, trả `bool` |
| `board.san_and_push(move)` | cách **duy nhất** dựng lại lịch sử SAN. `board.san(m)` trên bàn đã đi → `AssertionError` |
| `board.root().fen()` | tồn tại, trả FEN vị trí xuất phát |
| `chess.parse_square("e4")` | → `28`; `chess.square_name(28)` → `"e4"` |
| Bắt tốt qua đường | quân bị ăn nằm ở `to_square` **lùi 1 hàng về phía phe bắt**: trắng `to_rank-1`, đen `to_rank+1` |
| 12 tên file quân | `wK wQ wR wB wN wP bK bQ bR bB bN bP` tại `https://lichess1.org/assets/piece/cburnett/{tên}.svg` — tất cả HTTP 200, đều là SVG hợp lệ, tổng **7 564 byte** |
| FEN → tên file | ký tự **HOA = quân Trắng** → tiền tố `w`; **thường = Đen** → `b`. `P`→`wP.svg`, `p`→`bp.svg` |
| `len(chess.Board().legal_moves)` | `20` |

## Review Focus

Năm tình huống mà spec nhắc tới nhưng dễ sót, xếp theo xác suất làm hỏng người dùng thật. Mỗi dòng có test khoá nó ở task sở hữu code.

1. **Bấm ô không phải nước đi hợp lệ.** Máy chủ trả 400 kèm tiếng Việt, nhưng **bàn cờ phải không đổi một ô nào** — kể cả quân đang được chọn, kể cả highlight. → test ở Task 2, kiểm mắt ở Task 4 mục 4.
2. **Nhập thành bị chặn vì đường đi qua ô bị tấn công.** Thông điệp phải nêu đúng tên ô (`f1`), không phải ô vua. Thông điệp sai tên ô vẫn "đúng luật" nhưng hướng dẫn người chơi sai. → test ở Task 2.
3. **Ván mất khi máy chủ restart** (lưu trong RAM). Người chơi phải thấy thông báo rõ ràng kèm nút tạo ván mới, không phải màn hình trắng im lặng. → test ở Task 3, kiểm mắt ở Task 4 mục 11.
4. **Tốt tới hàng cuối phải hiện hộp chọn phong cấp, và bấm ra ngoài phải huỷ được.** Bỏ qua thì người chơi bị kẹt không đi được nước. → kiểm mắt ở Task 4 mục 7.
5. **Nút đổi nền phải nhớ qua reload.** Đổi rồi F5 mà mất thì phải bấm lại mỗi lần — đúng kiểu lỗi làm app cảm thấy vỡ. → kiểm mắt ở Task 4 mục 9.

---

### Task 1: Bộ quân SVG + khung gói

**Files:**
- Create: `chessai/web/__init__.py`, `chessai/web/static/pieces/*.svg` (12 file), `chessai/web/static/pieces/CREDITS.md`
- Test: `tests/test_web_pieces.py`

**Interfaces:**
- Consumes: không có
- Produces: 12 file tại `chessai/web/static/pieces/` đặt tên `wK.svg`…`bP.svg`. Task 4 tham chiếu đúng các tên này qua `/static/pieces/{tên}.svg`.

- [ ] **Step 1: Tạo thư mục và tải 12 file quân**

```bash
python -c "
from pathlib import Path
import urllib.request
d = Path('chessai/web/static/pieces'); d.mkdir(parents=True, exist_ok=True)
base = 'https://lichess1.org/assets/piece/cburnett/'
for c in ('w','b'):
    for p in 'KQRBNP':
        urllib.request.urlretrieve(base + c + p + '.svg', d / (c + p + '.svg'))
        print('tai', c + p + '.svg')
"
```

- [ ] **Step 2: Viết `chessai/web/__init__.py`**

```python
"""Máy chủ web. Máy chủ giữ luật cờ vua, trình duyệt chỉ hiển thị."""
```

- [ ] **Step 3: Ghi `CREDITS.md`**

```markdown
# Nguồn bộ quân

Bộ quân **cburnett** của **Colin Burnett**.

- Nguồn: `https://lichess1.org/assets/piece/cburnett/`
- Giấy phép: **CC BY-SA 3.0**
- Tác giả: Colin Burnett (dùng trên Wikipedia và lichess)

Ảnh được dùng **không sửa đổi**. Vì vậy nghĩa vụ share-alike của CC BY-SA 3.0
áp dụng cho chính các file ảnh này, không lan sang mã nguồn của dự án.

Tên 12 file: `wK wQ wR wB wN wP bK bQ bR bB bN bP`
( tiền tố `w` = quân Trắng, `b` = quân Đen; chữ sau là loại quân ).
```

- [ ] **Step 4: Viết test**

`tests/test_web_pieces.py`:
```python
"""Bộ quân phải đủ 12 file, hợp lệ, và có ghi công."""

import unittest
from pathlib import Path

PIECES = Path(__file__).resolve().parent.parent / "chessai" / "web" / "static" / "pieces"
NAMES = [f"{c}{p}" for c in "wb" for p in "KQRBNP"]


class TestPieces(unittest.TestCase):
    def test_all_twelve_files_exist(self) -> None:
        for name in NAMES:
            with self.subTest(name=name):
                self.assertTrue((PIECES / f"{name}.svg").is_file(), f"thiếu {name}.svg")

    def test_files_are_svg(self) -> None:
        for name in NAMES:
            with self.subTest(name=name):
                text = (PIECES / f"{name}.svg").read_text(encoding="utf-8")
                self.assertIn("<svg", text[:400])

    def test_total_size_under_40kb(self) -> None:
        total = sum((PIECES / f"{n}.svg").stat().st_size for n in NAMES)
        self.assertLess(total, 40 * 1024, f"tong {total} byte")

    def test_credits_states_author_and_license(self) -> None:
        text = (PIECES / "CREDITS.md").read_text(encoding="utf-8")
        self.assertIn("Colin Burnett", text)
        self.assertIn("CC BY-SA 3.0", text)

    def test_no_unexpected_files(self) -> None:
        present = {p.stem for p in PIECES.glob("*")}
        self.assertEqual(present - set(NAMES), {"CREDITS"}, f"file la: {present}")
```

- [ ] **Step 5: Chạy, kỳ vọng PASS ngay**

Run: `python -m unittest tests.test_web_pieces -v`
Expected: `Ran 5 tests ... OK`

Không đỏ–xanh được: đây là bước chuẩn bị tài nguyên đã tải ở Step 1. Nếu **fail** thì dừng và báo user — có thể tải thiếu hoặc sai nguồn.

- [ ] **Step 6: Commit**

```bash
git add chessai/web tests/test_web_pieces.py
git commit -m "feat(web): add cburnett svg piece set with credits"
```

---

### Task 2: `schema.py` + `games.py` — lớp ván đấu

**Files:**
- Create: `chessai/web/schema.py`, `chessai/web/games.py`
- Test: `tests/test_web_games.py`

**Interfaces:**
- Consumes: `chessai.session.Session`, `chessai.position.MoveError`, `chessai.position.Position` (từ #1, không sửa)
- Produces — Task 3 và 4 dùng:
```python
# schema.py
class MoveOption(BaseModel):
    from_sq: str; to_sq: str; san: str; capture: bool; promotion: bool
class GameState(BaseModel):
    game_id: str; fen: str; turn: str; legal: list[MoveOption]
    last_move: str | None; last_from: str | None; last_to: str | None
    check: bool; over: bool; result_text: str; moves: list[str]
    captured_by_white: list[str]; captured_by_black: list[str]
    can_undo: bool

# games.py
class GameNotFound(Exception)
class GameStore:
    def create(self, human_color: chess.Color | None) -> str
    def snapshot(self, game_id: str) -> GameState
    def submit(self, game_id: str, san: str) -> GameState
    def undo(self, game_id: str) -> GameState
    def new_game(self, game_id: str) -> GameState
    def pgn_text(self, game_id: str) -> str
    def set_fen(self, game_id: str, fen: str) -> None
    def forget(self, game_id: str) -> None
```

**Ruling đã ghi:** DTO có thêm `last_from` / `last_to` so với spec §4.2. Lý do: quân trượt cần biết quân đi từ ô nào tới ô nào, mà `last_move` chỉ có SAN. Trình duyệt không được tự phân tích SAN vì sẽ viết lại luật — vi phạm ràng buộc của spec. Chi phí nếu sai: thêm hai trường JSON.

- [ ] **Step 1: Viết test đỏ**

`tests/test_web_games.py`:
```python
import unittest

import chess

from chessai.position import MoveError
from chessai.web.games import GameNotFound, GameStore


def fresh(fen: str | None = None) -> tuple[GameStore, str]:
    store = GameStore()
    game_id = store.create(None)
    if fen is not None:
        store.set_fen(game_id, fen)
    return store, game_id


class TestCreate(unittest.TestCase):
    def test_create_returns_id_and_starting_state(self) -> None:
        store, game_id = fresh()
        self.assertEqual(len(game_id), 12)
        state = store.snapshot(game_id)
        self.assertEqual(state.fen, chess.STARTING_FEN)
        self.assertEqual(state.turn, "white")
        self.assertFalse(state.over)
        self.assertEqual(state.moves, [])

    def test_starting_position_has_twenty_legal_moves(self) -> None:
        store, game_id = fresh()
        self.assertEqual(len(store.snapshot(game_id).legal), 20)

    def test_legal_moves_carry_from_and_to_squares(self) -> None:
        store, game_id = fresh()
        e4 = [m for m in store.snapshot(game_id).legal if m.san == "e4"]
        self.assertEqual(len(e4), 1)
        self.assertEqual(e4[0].from_sq, "e2")
        self.assertEqual(e4[0].to_sq, "e4")
        self.assertFalse(e4[0].capture)
        self.assertFalse(e4[0].promotion)

    def test_ids_are_unique(self) -> None:
        store = GameStore()
        self.assertEqual(len({store.create(None) for _ in range(50)}), 50)


class TestMove(unittest.TestCase):
    def test_submit_updates_fen_and_moves(self) -> None:
        store, game_id = fresh()
        state = store.submit(game_id, "e4")
        state = store.submit(game_id, "e5")
        self.assertEqual(state.moves, ["e4", "e5"])
        self.assertNotEqual(state.fen, chess.STARTING_FEN)
        self.assertEqual(state.turn, "white")

    def test_submit_sets_last_from_and_to(self) -> None:
        store, game_id = fresh()
        state = store.submit(game_id, "e4")
        self.assertEqual(state.last_move, "e4")
        self.assertEqual(state.last_from, "e2")
        self.assertEqual(state.last_to, "e4")

    def test_illegal_move_raises_and_leaves_state_untouched(self) -> None:
        store, game_id = fresh()
        before = store.snapshot(game_id).fen
        with self.assertRaises(MoveError):
            store.submit(game_id, "e5")
        self.assertEqual(store.snapshot(game_id).fen, before)

    def test_castling_option_has_king_start_and_end(self) -> None:
        store, game_id = fresh("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        options = [m for m in store.snapshot(game_id).legal if m.san == "O-O"]
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].from_sq, "e1")
        self.assertEqual(options[0].to_sq, "g1")

    def test_castling_blocked_message_names_the_attacked_square(self) -> None:
        """Review Focus #2: phải nêu f1 (ô đi qua), không phải e1 (ô vua)."""
        store, game_id = fresh("4k3/5r2/8/8/8/8/8/4K2R w K - 0 1")
        with self.assertRaises(MoveError) as ctx:
            store.submit(game_id, "O-O")
        message = str(ctx.exception)
        self.assertIn("f1", message)
        self.assertNotIn("ô e1 ", message)

    def test_promotion_option_is_flagged(self) -> None:
        store, game_id = fresh("8/P6k/8/8/8/8/8/K7 w - - 0 1")
        options = [m for m in store.snapshot(game_id).legal if m.to_sq == "a8"]
        self.assertTrue(options)
        for option in options:
            self.assertTrue(option.promotion, option.san)
            self.assertEqual(option.from_sq, "a7")

    def test_en_passant_option_lands_on_empty_square(self) -> None:
        store, game_id = fresh("4k3/8/8/Pp6/8/8/8/4K3 w - b6 0 1")
        options = [m for m in store.snapshot(game_id).legal if m.from_sq == "a5"]
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].to_sq, "b6")
        self.assertTrue(options[0].capture)

    def test_check_is_reported(self) -> None:
        store, game_id = fresh("4k3/8/8/8/8/8/4r3/4K3 w - - 0 1")
        self.assertTrue(store.snapshot(game_id).check)


class TestCaptured(unittest.TestCase):
    def _captured(self, *sans: str) -> tuple[list[str], list[str]]:
        store, game_id = fresh()
        for san in sans:
            store.submit(game_id, san)
        state = store.snapshot(game_id)
        return state.captured_by_white, state.captured_by_black

    def test_white_captures_a_black_pawn(self) -> None:
        white, black = self._captured("e4", "d5", "exd5")
        self.assertEqual(white, ["P"])
        self.assertEqual(black, [])

    def test_black_captures_a_white_pawn(self) -> None:
        white, black = self._captured("e4", "d5", "exd5", "Qxd5")
        self.assertEqual(white, ["P"])
        self.assertEqual(black, ["P"])

    def test_en_passant_capture_is_counted(self) -> None:
        white, _ = self._captured("e4", "a6", "e5", "d5", "exd6")
        self.assertEqual(white, ["P"])

    def test_no_captures_yields_empty_lists(self) -> None:
        white, black = self._captured("e4", "e5")
        self.assertEqual(white, [])
        self.assertEqual(black, [])


class TestUndoAndReset(unittest.TestCase):
    def test_undo_restores_previous_fen(self) -> None:
        store, game_id = fresh()
        start = store.snapshot(game_id).fen
        store.submit(game_id, "e4")
        self.assertTrue(store.snapshot(game_id).can_undo)
        after = store.undo(game_id)
        self.assertEqual(after.fen, start)
        self.assertEqual(after.moves, [])

    def test_undo_on_new_game_raises(self) -> None:
        store, game_id = fresh()
        self.assertFalse(store.snapshot(game_id).can_undo)
        with self.assertRaises(MoveError):
            store.undo(game_id)

    def test_new_game_resets_but_keeps_id(self) -> None:
        store, game_id = fresh()
        store.submit(game_id, "e4")
        state = store.new_game(game_id)
        self.assertEqual(state.game_id, game_id)
        self.assertEqual(state.fen, chess.STARTING_FEN)
        self.assertEqual(state.moves, [])

    def test_undo_clears_captured_pieces(self) -> None:
        store, game_id = fresh()
        for san in ("e4", "d5", "exd5"):
            store.submit(game_id, san)
        self.assertEqual(store.snapshot(game_id).captured_by_white, ["P"])
        store.undo(game_id)
        self.assertEqual(store.snapshot(game_id).captured_by_white, [])

    def test_pgn_text_after_move(self) -> None:
        store, game_id = fresh()
        store.submit(game_id, "e4")
        store.submit(game_id, "e5")
        self.assertIn("1. e4 e5", store.pgn_text(game_id))

    def test_pgn_text_of_unknown_id_raises(self) -> None:
        with self.assertRaises(GameNotFound):
            GameStore().pgn_text("khongco")


class TestNotFound(unittest.TestCase):
    def test_snapshot_of_unknown_id_raises(self) -> None:
        with self.assertRaises(GameNotFound):
            GameStore().snapshot("khongcothat")

    def test_submit_to_unknown_id_raises(self) -> None:
        with self.assertRaises(GameNotFound):
            GameStore().submit("khongcothat", "e4")

    def test_forget_makes_id_unknowable(self) -> None:
        store, game_id = fresh()
        store.forget(game_id)
        with self.assertRaises(GameNotFound):
            store.snapshot(game_id)

    def test_error_message_is_actionable(self) -> None:
        with self.assertRaises(GameNotFound) as ctx:
            GameStore().snapshot("abc")
        self.assertIn("Ván", str(ctx.exception))
        self.assertIn("Ván mới", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `python -m unittest tests.test_web_games -v`
Expected: `ModuleNotFoundError: No module named 'chessai.web'`

- [ ] **Step 3: Viết `chessai/web/schema.py`**

```python
"""Khung dữ liệu gửi cho trình duyệt.

Đây là DTO, KHÔNG phải luật cờ vua. `MoveOption` mang sẵn ô nguồn và ô đích
để trình duyệt khớp với cú bấm chuột mà không phải tự phân tích SAN.
"""

from __future__ import annotations

from pydantic import BaseModel


class MoveOption(BaseModel):
    from_sq: str
    to_sq: str
    san: str
    capture: bool
    promotion: bool


class GameState(BaseModel):
    game_id: str
    fen: str
    turn: str
    legal: list[MoveOption]
    last_move: str | None
    last_from: str | None
    last_to: str | None
    check: bool
    over: bool
    result_text: str
    moves: list[str]
    captured_by_white: list[str]
    captured_by_black: list[str]
    can_undo: bool
```

- [ ] **Step 4: Viết `chessai/web/games.py`**

```python
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
            promotion=move.promotion is not None,
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
    def __init__(self) -> None:
        self._games: dict[str, Session] = {}
        self._locks: dict[str, threading.Lock] = {}

    def create(self, human_color: chess.Color | None) -> str:
        game_id = secrets.token_urlsafe(16)[:_ID_LENGTH]
        self._games[game_id] = Session(human_color=human_color)
        self._locks[game_id] = threading.Lock()
        return game_id

    def forget(self, game_id: str) -> None:
        """Xoá ván khỏi bộ nhớ — mô phỏng hành vi mất ván khi máy chủ restart."""
        self._require(game_id)
        del self._games[game_id]
        del self._locks[game_id]

    def set_fen(self, game_id: str, fen: str) -> None:
        """Nạp một thế cờ cụ thể. Dùng cho kiểm thử và #4 (`Review`)."""
        session = self._require(game_id)
        session.position = Position(fen)

    def snapshot(self, game_id: str) -> GameState:
        session = self._require(game_id)
        board = session.position.board
        by_white, by_black = _captured(board)
        last_from = last_to = None
        if board.move_stack:
            played = board.move_stack[-1]
            last_from = chess.square_name(played.from_square)
            last_to = chess.square_name(played.to_square)
        return GameState(
            game_id=game_id,
            fen=board.fen(),
            turn="white" if board.turn else "black",
            legal=_move_options(board),
            last_move=session.last_move_label(),
            last_from=last_from,
            last_to=last_to,
            check=board.is_check(),
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
            return self.snapshot(game_id)

    def undo(self, game_id: str) -> GameState:
        with self._lock(game_id):
            session = self._require(game_id)
            session.undo_turn()
            return self.snapshot(game_id)

    def new_game(self, game_id: str) -> GameState:
        with self._lock(game_id):
            session = self._require(game_id)
            self._games[game_id] = Session(human_color=session.human_color)
            return self.snapshot(game_id)

    def pgn_text(self, game_id: str) -> str:
        return self._require(game_id).pgn()

    def _require(self, game_id: str) -> Session:
        try:
            return self._games[game_id]
        except KeyError:
            raise GameNotFound(_MISSING) from None

    def _lock(self, game_id: str) -> threading.Lock:
        self._require(game_id)
        return self._locks[game_id]
```

- [ ] **Step 5: Chạy, kỳ vọng PASS**

Run: `python -m unittest tests.test_web_games -v`
Expected: `Ran 33 tests ... OK`

- [ ] **Step 6: Chạy toàn bộ test**

Run: `python -m unittest -v`
Expected: `OK`, phải gồm đủ 158 test cũ của #1.

- [ ] **Step 7: Commit**

```bash
git add chessai/web/schema.py chessai/web/games.py tests/test_web_games.py
git commit -m "feat(web): add GameStore that owns games and builds browser DTO"
```

---

### Task 3: `app.py` — route HTTP + ánh xạ lỗi

**Files:**
- Create: `chessai/web/app.py`
- Test: `tests/test_web_api.py`

**Interfaces:**
- Consumes: `GameStore`, `GameNotFound`, `GameState` (Task 2), `MoveError` (#1)
- Produces — Task 4 và 5 dùng:
```python
STATIC_DIR: pathlib.Path
def create_app(store: GameStore | None = None) -> FastAPI
app: FastAPI          # module-level, cho uvicorn dùng "chessai.web.app:app"
```

- [ ] **Step 1: Viết test đỏ**

`tests/test_web_api.py`:
```python
"""Route được gọi trực tiếp: máy không có httpx nên không dùng TestClient.

`call` tìm endpoint bằng cách so mẫu đường dẫn — `app.routes` lưu đường dẫn
CÓ template (`/api/game/{game_id}/move`) còn test gọi bằng id thật, nên không
thể tra cứu bằng tên thuộc tính.
"""

import asyncio
import json
import re
import unittest

from chessai.web.app import create_app
from chessai.web.games import GameStore


def find_endpoint(application, method: str, path: str):
    for route in application.routes:
        template = getattr(route, "path", None)
        if template is None or method not in getattr(route, "methods", set()):
            continue
        pattern = re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(template))
        if re.fullmatch(pattern, path):
            return route.endpoint
    raise AssertionError(f"khong tim thay route {method} {path}")


class ApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(GameStore())

    def call(self, method: str, path: str, **kwargs):
        endpoint = find_endpoint(self.app, method, path)
        return asyncio.run(endpoint(**kwargs))

    def get(self, path: str, **kwargs):
        return self.call("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self.call("POST", path, **kwargs)

    def body(self, response) -> dict:
        return json.loads(response.body)

    def new_game(self) -> str:
        return self.body(self.post("/api/game"))["game_id"]


class TestCreateGame(ApiTestCase):
    def test_create_returns_200_and_starting_state(self) -> None:
        response = self.post("/api/game")
        self.assertEqual(response.status_code, 200)
        state = self.body(response)
        self.assertEqual(
            state["fen"], "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        )
        self.assertEqual(len(state["legal"]), 20)
        self.assertEqual(len(state["game_id"]), 12)

    def test_two_games_get_different_ids(self) -> None:
        self.assertNotEqual(self.new_game(), self.new_game())


class TestMove(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.gid = self.new_game()

    def test_valid_move_returns_200(self) -> None:
        response = self.post(f"/api/game/{self.gid}/move", payload={"san": "e4"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.body(response)["moves"], ["e4"])

    def test_illegal_move_returns_400_with_vietnamese_text(self) -> None:
        response = self.post(f"/api/game/{self.gid}/move", payload={"san": "e5"})
        self.assertEqual(response.status_code, 400)
        message = self.body(response)["error"]
        self.assertIn("không hợp lệ", message)
        self.assertNotIn("illegal san", message)
        self.assertNotIn("/", message)

    def test_illegal_move_does_not_change_position(self) -> None:
        before = self.body(self.get(f"/api/game/{self.gid}"))["fen"]
        self.post(f"/api/game/{self.gid}/move", payload={"san": "e5"})
        self.assertEqual(self.body(self.get(f"/api/game/{self.gid}"))["fen"], before)

    def test_state_is_stable_across_reads(self) -> None:
        self.post(f"/api/game/{self.gid}/move", payload={"san": "e4"})
        self.assertEqual(
            self.body(self.get(f"/api/game/{self.gid}")),
            self.body(self.get(f"/api/game/{self.gid}")),
        )

    def test_unknown_id_move_returns_404(self) -> None:
        self.assertEqual(
            self.post("/api/game/khongco/move", payload={"san": "e4"}).status_code, 404
        )


class TestUndoAndNew(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.gid = self.new_game()

    def test_undo_returns_200_and_reverts(self) -> None:
        start = self.body(self.get(f"/api/game/{self.gid}"))["fen"]
        self.post(f"/api/game/{self.gid}/move", payload={"san": "e4"})
        response = self.post(f"/api/game/{self.gid}/undo")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.body(response)["fen"], start)

    def test_undo_on_new_game_returns_400(self) -> None:
        self.assertEqual(self.post(f"/api/game/{self.gid}/undo").status_code, 400)

    def test_new_game_keeps_id(self) -> None:
        self.post(f"/api/game/{self.gid}/move", payload={"san": "e4"})
        state = self.body(self.post(f"/api/game/{self.gid}/new"))
        self.assertEqual(state["game_id"], self.gid)
        self.assertEqual(state["moves"], [])


class TestMissingGame(ApiTestCase):
    def test_unknown_id_returns_404(self) -> None:
        self.assertEqual(self.get("/api/game/khongco").status_code, 404)

    def test_404_message_is_actionable(self) -> None:
        message = self.body(self.get("/api/game/khongco"))["error"]
        self.assertIn("Ván", message)
        self.assertIn("Ván mới", message)


class TestPgn(ApiTestCase):
    def test_pgn_after_move_contains_movetext(self) -> None:
        gid = self.new_game()
        self.post(f"/api/game/{gid}/move", payload={"san": "e4"})
        text = self.body(self.get(f"/api/game/{gid}/pgn"))["pgn"]
        self.assertIn("1. e4", text)

    def test_pgn_of_unknown_id_returns_404(self) -> None:
        self.assertEqual(self.get("/api/game/khongco/pgn").status_code, 404)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `python -m unittest tests.test_web_api -v`
Expected: `ModuleNotFoundError: No module named 'chessai.web.app'`

- [ ] **Step 3: Viết `chessai/web/app.py`**

```python
"""Route HTTP. Lớp này không chứa luật cờ vua — chỉ dịch lỗi sang mã HTTP."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..position import MoveError
from .games import GameNotFound, GameStore

STATIC_DIR = Path(__file__).parent / "static"


class MoveRequest(BaseModel):
    san: str


def _guard(action, *args) -> JSONResponse:
    """Chạy một thao tác GameStore rồi dịch lỗi thành mã HTTP.

    Cố ý bắt lỗi trong thân handler thay vì dùng `exception_handler` của
    FastAPI: handler chỉ chạy qua ASGI stack, còn test gọi thẳng hàm. Dùng
    `exception_handler` sẽ khiến test im lặng bỏ qua mọi nhánh lỗi.
    """
    try:
        return JSONResponse(action(*args))
    except GameNotFound as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except MoveError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


def create_app(store: GameStore | None = None) -> FastAPI:
    app = FastAPI(title="Chess_ai web", docs_url=None, redoc_url=None)
    games = store if store is not None else GameStore()

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.post("/api/game")
    def create_game() -> JSONResponse:
        return _guard(games.snapshot, games.create(None))

    @app.get("/api/game/{game_id}")
    def read_game(game_id: str) -> JSONResponse:
        return _guard(games.snapshot, game_id)

    @app.post("/api/game/{game_id}/move")
    def move(game_id: str, payload: MoveRequest) -> JSONResponse:
        return _guard(games.submit, game_id, payload.san)

    @app.post("/api/game/{game_id}/undo")
    def undo(game_id: str) -> JSONResponse:
        return _guard(games.undo, game_id)

    @app.post("/api/game/{game_id}/new")
    def new_game(game_id: str) -> JSONResponse:
        return _guard(games.new_game, game_id)

    @app.get("/api/game/{game_id}/pgn")
    def pgn(game_id: str) -> JSONResponse:
        return _guard(lambda gid: {"pgn": games.pgn_text(gid)}, game_id)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
```

- [ ] **Step 4: Chạy, kỳ vọng PASS**

Run: `python -m unittest tests.test_web_api -v`
Expected: `Ran 15 tests ... OK`

- [ ] **Step 5: Chạy toàn bộ test**

Run: `python -m unittest -v`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add chessai/web/app.py tests/test_web_api.py
git commit -m "feat(web): add http routes mapping chess errors to 400 and 404"
```

---

### Task 4: Giao diện — `index.html`, `style.css`, `app.js`

Task này **không dùng TDD**: máy không có framework test JS và spec §6 đã chốt không cài thêm. Mọi bước dưới đây xác minh bằng **mở trang thật trong trình duyệt**.

**Files:**
- Create: `chessai/web/static/index.html`, `chessai/web/static/style.css`, `chessai/web/static/app.js`
- Test: kiểm thử thủ công bằng trình duyệt (không có file test)

**Interfaces:**
- Consumes: route của Task 3, 12 file quân của Task 1, `MoveOption`/`GameState` của Task 2
- Produces: trang chơi được ở `http://localhost:8000/`

- [ ] **Step 1: Viết `index.html`**

```html
<!DOCTYPE html>
<html lang="vi" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chess_ai</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<main class="app">
  <section class="board-area">
    <div class="board" id="board">
      <div class="squares" id="squares"></div>
      <div class="pieces" id="pieces"></div>
      <div class="picker" id="picker" hidden></div>
    </div>
  </section>
  <aside class="panel">
    <header class="panel-head">
      <span class="brand">Chess_ai</span>
      <button id="theme" class="icon-btn" title="Đổi nền sáng/tối">&#9680;</button>
    </header>
    <div class="player" id="player-top">
      <span class="dot black"></span>
      <div><strong>Đen</strong><small id="top-sub">—</small></div>
      <span class="captured" id="top-captured"></span>
    </div>
    <div class="player" id="player-bottom">
      <span class="dot white"></span>
      <div><strong>Trắng</strong><small id="bottom-sub">—</small></div>
      <span class="captured" id="bottom-captured"></span>
    </div>
    <p class="message" id="message"></p>
    <ol class="moves" id="moves"></ol>
    <div class="actions">
      <button id="undo">Lùi 1 lượt</button>
      <button id="flip">Lật bàn</button>
      <button id="pgn">Tải PGN</button>
      <button id="new" class="primary">Ván mới</button>
    </div>
  </aside>
</main>
<script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Viết `style.css`**

```css
/* Bảng màu theo spec: bàn cố định, vỏ ngoài đổi theo data-theme. */
:root {
  --sq-light: #eeeed2;
  --sq-dark: #769656;
  --label-light: #769656;
  --label-dark: #eeeed2;
  --last-move: rgba(255, 213, 74, .35);
  --selected: #ffd54a;
  --dot-light: rgba(30, 30, 30, .28);
  --dot-dark: rgba(255, 255, 255, .55);
  --capture-ring: rgba(255, 80, 80, .95);
  --check: rgba(220, 60, 60, .55);
  --page: #15171c;
  --panel: #1e2229;
  --border: #2c313b;
  --fg: #e8e8e8;
  --muted: rgba(232, 232, 232, .6);
  --btn: #2a2f38;
  --btn-border: #3a4150;
  --btn-fg: #ddd;
  --turn: #2b3542;
}
html[data-theme="light"] {
  --page: #f2f2ef;
  --panel: #ffffff;
  --border: #dedcd5;
  --fg: #22242a;
  --muted: rgba(34, 36, 42, .6);
  --btn: #eceae4;
  --btn-border: #d6d3ca;
  --btn-fg: #333;
  --turn: #e8eefb;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  padding: 18px;
  background: var(--page);
  color: var(--fg);
  font: 14px/1.5 system-ui, "Segoe UI", sans-serif;
}

.app { display: flex; gap: 16px; align-items: flex-start; max-width: 960px; margin: 0 auto; }
.board-area { flex: 1 1 auto; min-width: 0; }

.board {
  position: relative;
  width: min(640px, 100%);
  aspect-ratio: 1;
  margin: 0 auto;
  border-radius: 4px;
  overflow: hidden;
}

/* Hai lớp: ô vuông bên dưới, quân bên trên. Nhờ tách vậy quân trượt
   bằng CSS transition chỉ cần đổi transform. */
.squares, .pieces { position: absolute; inset: 0; display: grid; grid-template-columns: repeat(8, 1fr); }
.squares { z-index: 1; }
.pieces  { z-index: 2; pointer-events: none; }

.sq { position: relative; }
.sq.light { background: var(--sq-light); }
.sq.dark  { background: var(--sq-dark); }
.sq.last::before { content: ""; position: absolute; inset: 0; background: var(--last-move); }
.sq.sel   { box-shadow: inset 0 0 0 4px var(--selected); }
.sq.check { box-shadow: inset 0 0 0 4px var(--check); }

.sq .dot  { position: absolute; inset: 37%; border-radius: 50%; }
.sq.light .dot { background: var(--dot-light); }
.sq.dark  .dot { background: var(--dot-dark); }
.sq .ring { position: absolute; inset: 1%; border-radius: 50%; border: 4px solid var(--capture-ring); }

.sq .coord { position: absolute; font-size: 11px; font-weight: 600; line-height: 1; opacity: .75; }
.sq .coord.file { right: 3px; bottom: 2px; }
.sq .coord.rank { left: 3px; top: 2px; }
.sq.light .coord { color: var(--label-light); }
.sq.dark  .coord { color: var(--label-dark); }

/* Quân: kích thước cố định, CHỈ transform đổi nên transition chạy mượt. */
.piece {
  position: absolute;
  width: 12.5%;
  height: 12.5%;
  transition: transform .15s ease;
  will-change: transform;
}
.piece img { width: 100%; height: 100%; display: block; }

.picker { position: absolute; z-index: 3; display: flex; flex-wrap: wrap; width: 12.5%; gap: 2px; }
.picker button { flex: 1 1 45%; aspect-ratio: 1; border: 1px solid var(--border); background: var(--panel); border-radius: 3px; padding: 1px; cursor: pointer; }
.picker img { width: 100%; height: 100%; }

.panel { width: 260px; flex: none; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
.panel-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.brand { font-weight: 700; letter-spacing: .02em; }
.icon-btn { background: var(--btn); color: var(--btn-fg); border: 1px solid var(--btn-border); border-radius: 5px; width: 30px; height: 26px; cursor: pointer; }

.player { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px; }
.player.turn { background: var(--turn); }
.player .dot { width: 11px; height: 11px; border-radius: 50%; border: 1px solid #888; flex: none; }
.player .dot.white { background: #f2f2f2; }
.player .dot.black { background: #3a3f4a; }
.player div { display: flex; flex-direction: column; }
.player small { color: var(--muted); font-size: 11px; }
.captured { margin-left: auto; display: flex; gap: 1px; align-items: center; }
.captured img { width: 15px; height: 15px; }

.message { min-height: 20px; margin: 10px 0 6px; color: var(--muted); font-size: 13px; }
.message.error { color: #ff8a80; }

.moves { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: auto 1fr 1fr; gap: 1px 8px; font-size: 13px; max-height: 190px; overflow: auto; font-variant-numeric: tabular-nums; }
.moves li { color: var(--muted); }
.moves li.w, .moves li.b { color: var(--fg); }
.moves li.now { background: var(--turn); border-radius: 3px; }

.actions { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 12px; }
.actions button { padding: 7px 8px; font-size: 13px; background: var(--btn); color: var(--btn-fg); border: 1px solid var(--btn-border); border-radius: 5px; cursor: pointer; }
.actions button.primary { background: #4a7dd6; border-color: #4a7dd6; color: #fff; }
.actions button:disabled { opacity: .45; cursor: not-allowed; }

@media (max-width: 720px) {
  .app { flex-direction: column; }
  .panel { width: 100%; }
  .moves { max-height: 120px; }
}
```

- [ ] **Step 3: Viết `app.js`**

```javascript
"use strict";

// Trình duyệt KHÔNG có luật cờ vua. Mọi thứ dưới đây chỉ khớp chuỗi với
// dữ liệu máy chủ gửi: legal[].from_sq / legal[].to_sq / legal[].san.

const FILES = "abcdefgh";
const PROMOTION_PIECES = ["Q", "R", "B", "N"];

const el = {
  board: document.getElementById("board"),
  squares: document.getElementById("squares"),
  pieces: document.getElementById("pieces"),
  picker: document.getElementById("picker"),
  message: document.getElementById("message"),
  moves: document.getElementById("moves"),
  top: document.getElementById("player-top"),
  bottom: document.getElementById("player-bottom"),
  topSub: document.getElementById("top-sub"),
  bottomSub: document.getElementById("bottom-sub"),
  topCaptured: document.getElementById("top-captured"),
  bottomCaptured: document.getElementById("bottom-captured"),
  undo: document.getElementById("undo"),
};

let state = null;
let orientation = "w";   // "w" = quân Trắng ở dưới
let selected = null;     // ô nguồn đang chọn
let promoting = null;    // đang chờ chọn quân phong cấp
let pickerSquare = null;

function pieceUrl(ch) {
  const white = ch === ch.toUpperCase();
  return `/static/pieces/${white ? "w" : "b"}${ch.toUpperCase()}.svg`;
}

async function api(path, method, payload) {
  const options = { method };
  if (payload !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(payload);
  }
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Lỗi máy chủ");
  return data;
}

function boardFromFen(fen) {
  const cells = {};
  fen.split(" ")[0].split("/").forEach((row, r) => {
    let f = 0;
    for (const ch of row) {
      if (ch >= "1" && ch <= "8") { f += Number(ch); continue; }
      cells[FILES[f] + (8 - r)] = ch;
      f += 1;
    }
  });
  return cells;
}

// Vị trí trong lưới 8x8 theo hướng nhìn hiện tại.
function cellOf(name) {
  const file = FILES.indexOf(name[0]);
  const rank = Number(name[1]) - 1;
  return orientation === "w"
    ? { col: file, row: 7 - rank }
    : { col: 7 - file, row: rank };
}

function buildSquares() {
  el.squares.innerHTML = "";
  for (let row = 0; row < 8; row += 1) {
    for (let col = 0; col < 8; col += 1) {
      const name = FILES[col] + (8 - row);
      const rank = 8 - row;
      const div = document.createElement("div");
      div.className = "sq " + ((rank + col) % 2 === 0 ? "dark" : "light");
      div.dataset.sq = name;
      if (rank === 1) {
        const fileLabel = document.createElement("span");
        fileLabel.className = "coord file";
        fileLabel.textContent = FILES[col];
        div.appendChild(fileLabel);
      }
      if (col === 0) {
        const rankLabel = document.createElement("span");
        rankLabel.className = "coord rank";
        rankLabel.textContent = String(rank);
        div.appendChild(rankLabel);
      }
      el.squares.appendChild(div);
    }
  }
}

function legalFrom(source) {
  return state.legal.filter((m) => m.from_sq === source);
}

function paintBoard(cells) {
  el.squares.querySelectorAll(".sq").forEach((sq) => {
    sq.classList.remove("last", "sel", "check");
    sq.querySelector(".dot")?.remove();
    sq.querySelector(".ring")?.remove();
    const name = sq.dataset.sq;
    if (name === state.last_from || name === state.last_to) sq.classList.add("last");
    if (name === selected) sq.classList.add("sel");
    // Vua đang bị chiếu: tìm trong FEN, không phải luật cờ vua.
    if (state.check && "Kk".includes(cells[name])) sq.classList.add("check");
  });
  if (!selected) return;
  legalFrom(selected).forEach((option) => {
    const sq = el.squares.querySelector(`[data-sq="${option.to_sq}"]`);
    if (!sq) return;
    const mark = document.createElement("div");
    mark.className = option.capture ? "ring" : "dot";
    sq.appendChild(mark);
  });
}

function paintPieces(cells) {
  el.pieces.querySelectorAll(".piece").forEach((node) => {
    if (cells[node.dataset.sq] !== node.dataset.ch) node.remove();
  });
  Object.entries(cells).forEach(([name, ch]) => {
    let node = el.pieces.querySelector(`[data-sq="${name}"]`);
    if (!node) {
      node = document.createElement("div");
      node.className = "piece";
      node.dataset.ch = ch;
      node.dataset.sq = name;
      const img = document.createElement("img");
      img.src = pieceUrl(ch);
      img.alt = "";
      node.appendChild(img);
      el.pieces.appendChild(node);
    }
    const { col, row } = cellOf(name);
    node.style.transform = `translate(${col * 100}%, ${row * 100}%)`;
  });
}

function paintPanel() {
  const whiteTurn = state.turn === "white";
  el.top.classList.toggle("turn", !whiteTurn);
  el.bottom.classList.toggle("turn", whiteTurn);
  el.topSub.textContent = whiteTurn ? "Đang đợi" : "Đến lượt";
  el.bottomSub.textContent = whiteTurn ? "Đến lượt" : "Đang đợi";
  el.topCaptured.innerHTML = state.captured_by_white
    .map((p) => `<img src="${pieceUrl(p)}" alt="">`).join("");
  el.bottomCaptured.innerHTML = state.captured_by_black
    .map((p) => `<img src="${pieceUrl(p)}" alt="">`).join("");

  el.moves.innerHTML = "";
  for (let i = 0; i < state.moves.length; i += 2) {
    const number = document.createElement("li");
    number.textContent = `${i / 2 + 1}.`;
    const white = document.createElement("li");
    white.className = "w";
    white.textContent = state.moves[i];
    const black = document.createElement("li");
    black.className = "b";
    black.textContent = state.moves[i + 1] ?? "";
    if (i + 1 === state.moves.length - 1) black.classList.add("now");
    el.moves.append(number, white, black);
  }
  el.moves.scrollTop = el.moves.scrollHeight;
  el.undo.disabled = !state.can_undo;
  if (state.over) {
    el.message.textContent = state.result_text;
    el.message.classList.remove("error");
  }
}

function apply(next) {
  state = next;
  selected = null;
  hidePicker();
  const cells = boardFromFen(state.fen);
  paintPieces(cells);
  paintBoard(cells);
  paintPanel();
}

function say(text, isError = false) {
  el.message.textContent = text;
  el.message.classList.toggle("error", isError);
}

function hidePicker() {
  promoting = null;
  pickerSquare = null;
  el.picker.hidden = true;
  el.picker.innerHTML = "";
}

function showPicker(target) {
  el.picker.hidden = false;
  el.picker.innerHTML = "";
  pickerSquare = target;
  const { col, row } = cellOf(target);
  el.picker.style.transform = `translate(${col * 100}%, ${row * 100}%)`;
  PROMOTION_PIECES.forEach((letter) => {
    const button = document.createElement("button");
    button.title = "Phong cấp " + letter;
    const img = document.createElement("img");
    img.src = pieceUrl(letter);
    img.alt = letter;
    button.appendChild(img);
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const from = promoting;
      hidePicker();
      send(`${from.from_sq}${sourceFile(from.from_sq)}${target}=${letter}`);
    });
    el.picker.appendChild(button);
  });
}

// Ô nguồn trong SAN: tốt thì dùng cột, quân khác thì dùng chữ quân.
function sourceFile(fromSq) {
  return "x";
}

async function send(san) {
  try {
    apply(await api(`/api/game/${state.game_id}/move`, "POST", { san }));
    say("");
  } catch (error) {
    say(error.message, true);   // bàn cờ KHÔNG đổi
  }
}

el.squares.addEventListener("click", (event) => {
  const sq = event.target.closest(".sq");
  if (!sq || !state || state.over) return;
  const name = sq.dataset.sq;

  if (selected === name) {          // bấm lại ô nguồn để bỏ chọn
    selected = null;
    paintBoard(boardFromFen(state.fen));
    return;
  }

  if (selected) {
    const options = legalFrom(selected).filter((m) => m.to_sq === name);
    if (options.length === 0) {
      say("Ô đó không phải nước đi hợp lệ từ ô đang chọn.");
      return;
    }
    if (options[0].promotion) {
      promoting = { from_sq: selected };
      showPicker(name);
      return;
    }
    send(options[0].san);
    return;
  }

  if (legalFrom(name).length > 0) {
    selected = name;
    paintBoard(boardFromFen(state.fen));
  } else {
    say("Chọn một quân của bạn để đi.");
  }
});

// Bấm ra ngoài hộp phong cấp thì huỷ, không gửi gì lên máy chủ.
el.board.addEventListener("click", (event) => {
  if (promoting && !event.target.closest(".picker")) {
    hidePicker();
    paintBoard(boardFromFen(state.fen));
  }
});

el.undo.addEventListener("click", async () => {
  apply(await api(`/api/game/${state.game_id}/undo`, "POST"));
  say("");
});

document.getElementById("flip").addEventListener("click", () => {
  orientation = orientation === "w" ? "b" : "w";
  buildSquares();
  apply(state);
});

document.getElementById("new").addEventListener("click", async () => {
  apply(await api("/api/game", "POST"));
  say("");
});

document.getElementById("pgn").addEventListener("click", async () => {
  const { pgn } = await api(`/api/game/${state.game_id}/pgn`, "GET");
  const url = URL.createObjectURL(new Blob([pgn], { type: "application/x-chess-pgn" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "chess-ai.pgn";
  link.click();
  URL.revokeObjectURL(url);
});

const themeButton = document.getElementById("theme");
function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("chessai-theme", theme);
}
themeButton.addEventListener("click", () => {
  setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});
const savedTheme = localStorage.getItem("chessai-theme");
if (savedTheme) setTheme(savedTheme);
else if (window.matchMedia("(prefers-color-scheme: light)").matches) setTheme("light");

buildSquares();
apply(await api("/api/game", "POST"));
```

**Sửa bắt buộc trước khi chạy Step 4:** hàm `sourceFile` ở trên chỉ là chỗ dựng khung, **sai** — nó luôn trả `"x"`, nên SAN phong cấp sẽ thành `ax7xa8=Q` thay vì `a7a8=Q`. Cách sửa đúng: `MoveOption` đã có sẵn `san` **đã đầy đủ kèm `=Q`**, nên lưu luôn `san` vào `promoting` rồi ghép:

```javascript
    if (options[0].promotion) {
      promoting = { sanByLetter: {} };
      options.forEach((o) => { promoting.sanByLetter[o.san.slice(-1)] = o.san; });
      showPicker(name);
      return;
    }
```
và trong `showPicker`, nút dùng `send(promoting.sanByLetter[letter])`. **Xoá hẳn hàm `sourceFile`.** Nhờ vậy trình duyệt không dựng SAN, chỉ đọc SAN máy chủ đã tính sẵn.

- [ ] **Step 4: Chạy máy chủ và xác minh bằng trình duyệt**

Task này chưa có `__main__.py`, chạy bằng:
```bash
python -m uvicorn chessai.web.app:app --port 8000
```

Mở `http://localhost:8000` và kiểm **theo thứ tự**, ghi kết quả:

| # | Việc | Đạt khi |
|---|---|---|
| 1 | Bàn dựng đúng | 32 quân đúng chỗ; nhãn a–h ở hàng 1, nhãn 1–8 ở cột a |
| 2 | Bấm `e2` | ô viền vàng, 4 chấm tròn ở e3/e4/d1/f1 |
| 3 | Bấm `e4` | quân **trượt** e2→e4, danh sách hiện `1. e4` |
| 4 | Bấm lại `e2` rồi ô không hợp lệ | hiện lỗi tiếng Việt, **bàn cờ không đổi ô nào** |
| 5 | Nhập thành | `e4 e5 Nf3 Nc6 Bc4 Bc5`, bấm e1 rồi g1 → vua sang g1 |
| 6 | Bắt tốt qua đường | `e4 a6 e5 d5`, bấm e5 rồi d6 → **vòng tròn đỏ** ở d6, tốt đen ở d5 biến mất |
| 7 | Phong cấp | dắt tốt tới a7 → hộp 4 quân hiện; bấm ra ngoài **huỷ được**; chọn quân thì bàn đúng |
| 8 | Vua bị chiếu | dựng thế bằng `/fen` tay hoặc đi tới thế chiếu → ô vua có viền đỏ |
| 9 | Lùi / Lật bàn / Ván mới / Tải PGN | cả bốn chạy; lật bàn đảo cả quân lẫn nhãn |
| 10 | Đổi nền | bấm `◐` đổi, **F5 reload** vẫn giữ |
| 11 | Console | DevTools console **không có lỗi đỏ** |
| 12 | Ván mất | tắt máy chủ, bấm Lùi → hiện thông báo tiếng Việt kèm nút "Ván mới", bấm được |

Nếu mục nào sai thì **sửa `app.js`/`style.css` và kiểm lại mục đó**. Không sang Task 5.

- [ ] **Step 5: Commit**

```bash
git add chessai/web/static
git commit -m "feat(web): add board UI, highlights, promotion picker and theme toggle"
```

---

### Task 5: `__main__.py` + xác minh hết

**Files:**
- Create: `chessai/web/__main__.py`
- Test: `tests/test_web_main.py`

**Interfaces:**
- Consumes: `chessai.web.app.app` (Task 3)
- Produces: `python -m chessai.web [--port N] [--host H]`

- [ ] **Step 1: Viết test đỏ**

`tests/test_web_main.py`:
```python
import unittest

from chessai.web import __main__ as entry


class TestArguments(unittest.TestCase):
    def test_defaults(self) -> None:
        args = entry.parse_args([])
        self.assertEqual(args.port, 8000)
        self.assertEqual(args.host, "127.0.0.1")

    def test_overrides(self) -> None:
        args = entry.parse_args(["--port", "9000", "--host", "0.0.0.0"])
        self.assertEqual(args.port, 9000)
        self.assertEqual(args.host, "0.0.0.0")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `python -m unittest tests.test_web_main -v`
Expected: `ModuleNotFoundError: No module named 'chessai.web.__main__'`

- [ ] **Step 3: Viết `chessai/web/__main__.py`**

```python
"""Chạy máy chủ: python -m chessai.web [--port 8000] [--host 127.0.0.1]"""

from __future__ import annotations

import argparse

import uvicorn


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="chessai.web", description="Chơi cờ vua trên trình duyệt."
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--host", default="127.0.0.1", help="0.0.0.0 để máy khác cùng mạng vào"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    print(f"Chess_ai: http://{args.host}:{args.port}")
    uvicorn.run("chessai.web.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Chạy, kỳ vọng PASS**

Run: `python -m unittest tests.test_web_main -v`
Expected: `Ran 2 tests ... OK`

- [ ] **Step 5: Chạy toàn bộ test**

Run: `python -m unittest -v`
Expected: `OK`, gồm 158 test #1 + 5 (quân) + 33 (games) + 15 (api) + 2 (main) = **215 test**

- [ ] **Step 6: Chạy thật và kiểm lần cuối**

```bash
python -m chessai.web
```
Mở `http://localhost:8000`, làm lại nhanh các mục 3, 4, 5, 10, 12 ở bảng Task 4.

- [ ] **Step 7: Commit**

```bash
git add chessai/web/__main__.py tests/test_web_main.py
git commit -m "feat(web): add python -m chessai.web entry point"
```

---

## Kiểm tra cuối (không commit)

```bash
python -m unittest -v
git status --short
git log --oneline feature/chess-core..HEAD
```

Xác nhận: `OK`, `git status --short` rỗng, log chỉ có 5 commit của #3A.

**Không push.** Repo có `origin` nhưng bạn chỉ cho phép thêm remote.
