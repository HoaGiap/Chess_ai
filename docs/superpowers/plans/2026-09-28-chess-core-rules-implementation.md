# Chess Core (#1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây dựng lõi cờ vua chơi được trên terminal: luật FIDE đầy đủ, vẽ bàn cờ Unicode theo cả hai góc nhìn, và CLI có lệnh — tất cả kiểm chứng bằng test tự động.

**Architecture:** Bốn module, mỗi cái một trách nhiệm. `python-chess` lo toàn bộ luật FIDE; `position.py` bọc lại chỉ để dịch lỗi sang tiếng Việt và trả lý do kết thúc ván đọc được. `render.py` là hàm thuần (board + hướng nhìn → chuỗi) nên test được bằng so khớp chuỗi. `session.py` giữ lịch sử, sinh PGN, lùi lượt. `cli.py` là REPL tra cứu lệnh. Không interface, không base class, không abstract layer.

**Tech Stack:** Python 3.13 · `python-chess==1.999` · `unittest` stdlib (không cài pytest)

**Spec:** `docs/superpowers/specs/2026-09-28-chess-core-rules-design.md`

## Global Constraints

- Python 3.13. Chạy mọi lệnh từ thư mục gốc repo `D:\DuAnCaNhan\Chess_ai`.
- Chỉ thêm **một** dependency: `python-chess==1.999`. Không thêm thư viện nào khác, kể cả `pytest`.
- Test bằng `unittest` stdlib. Toàn bộ: `python -m unittest -v`. Một file: `python -m unittest tests.test_render -v`. Một test: `python -m unittest tests.test_render.TestRender.test_x -v`.
- Tên gói là `chessai`. **Tuyệt đối không** tạo thư mục/gói tên `chess` — sẽ che mất package `python-chess` khi import.
- Thông điệp người dùng thấy **bằng tiếng Việt**, có dấu. Comment trong code bằng tiếng Việt, ngắn gọn.
- Quy ước luật (spec §6): lặp thế cờ 3 lần **kết thúc ván**; luật 50 nước **chỉ là quyền tuyên bố** (chỉ báo nhắc, ván vẫn đi được); luật 75 nước (150 halfmove) **tự động** kết thúc.
- `render()` in bàn cờ **trần**, không in `+`/`#`. Ký hiệu đó do `Session.last_move_label()` trả về, `cli` in riêng.
- Mỗi task kết thúc bằng một commit. Không commit file rác (`__pycache__`).

### Hành vi `python-chess` đã kiểm chứng bằng chạy thật

Mỗi dòng dưới đây đã được chạy và xác nhận trên `python-chess==1.999`. Sai những chi tiết này là bug, nên ghi ra để không phải đoán:

| Kiện | Sự thật |
|---|---|
| `chess.__version__` | Báo **`1.11.2`** dù package trên PyPI tên phiên bản là `1.999`. Cả hai đều đúng; đừng "sửa" lại. |
| `chess.Termination` | Dùng `enum.auto()` → `.value` là **số**, không phải chuỗi. Tra map phải dùng chính member làm key. |
| `chess.Outcome` | Là `@dataclasses.dataclass`, thứ tự field là `termination` **rồi** `winner`. Luôn truyền bằng **keyword**. |
| `Board.san(move)` | Chỉ dùng được khi bàn cờ **đang đứng ở vị trí trước nước đi đó**. Gọi `board.san(m) for m in board.move_stack` trên bàn cờ đã đi hết → `AssertionError`. Phải replay. |
| `Board.san_and_push(move)` | Tồn tại. Đây là cách đúng để dựng lại lịch sử SAN: `replay = chess.Board(root_fen)` rồi `replay.san_and_push(m)`. |
| `str(chess.pgn.Game())` | Luôn có header `[Result "*"]` và phần thân **kết thúc bằng ` *`**. Ván rộng phần thân chính là `*`. Phải cắt `*` khi hiển thị. |
| `Board.parse_san()` | Không đổi thế cờ → parse lỗi thì thế cờ nguyên vẹn. Cơ sở của bất biến "nước sai không đổi gì". |
| Hậu tố `+`/`#` thừa | **Được chấp nhận**: `parse_san("e4+")` và `parse_san("e4#")` đều trả về nước `e4`. Thư viện thiên lệch ở đây. |
| Ghi chú `!`/`?` | **Bị từ chối**: `parse_san("e4!")`, `"e4?"`, `"e4!!"` đều ném `InvalidMoveError`. |
| Ba exception | `InvalidMoveError`, `IllegalMoveError`, `AmbiguousMoveError` đều là `ValueError` trực tiếp — **anh em cùng gốc**, không phải chuỗi kế thừa. Bắt riêng từng cái. |
| `Board.can_claim_fifty_moves()` | Rộng hơn `is_fifty_moves()`: còn `True` khi `halfmove_clock >= 99` **và** tồn tại nước đi không bắt tốt dẫn tới 100. |
| `Board.is_seventyfive_moves()` | Có tồn tại, tương đương `halfmove_clock >= 150`. |
| `Board.is_game_over()` | Với `claim_draw=True` (mặc định) **không** báo kết thúc ở lặp 3 lần ngay tại thế cờ vừa lặp — vì luật FIDE cho quyền tuyên bố của người đến lượt. Spec #1 chọn quy tắc đơn giản hơn (`is_repetition(3)` trên thế cờ hiện tại), nên **không** dùng `is_game_over()` cho việc này. |
| `Board.fen()` | Mặc định `en_passant="legal"`: ô bắt tốt qua đường chỉ hiện khi thực sự có nước bắt hợp lệ. Nên FEN sau `1.e4 e5` là `KQkq - 0 2`, **không** phải `KQkq e6`. |
| `Board.castling_rights` | Bitboard các ô **xe** còn giữ quyền nhập thành. Kiểm `castling_rights & chess.BB_SQUARES[rook_square]`. |

## Review Focus

Năm trường hợp người dùng thật sẽ gặp, xếp theo xác suất làm hỏng trải nghiệm:

1. **Người chơi gõ ghi chú phân tích** (`e4!`, `Nf3?!`, `e4??`) — rất dễ dính khi sao chép từ bài báo. `python-chess` từ chối, phải báo lỗi dễ hiểu chứ không văng traceback. → test ở Task 3.
2. **Phong cấp đủ 4 quân** (`e8=Q` lẫn `a8=N`, `a8=B`, `a8=R`) — spec §6 chỉ ví dụ hậu, nhưng đây là luật FIDE, không có ngoại lệ. → test ở Task 3.
3. **Nhập thành khi vua đã đi rồi quay lại ô e1** — mất quyền nhập thành dù mọi quân vẫn ở chỗ cũ. Đây là thế rất dễ xảy ra khi người chơi đi lại thử nghiệm. Thông điệu phải chỉ đúng lý do. → test ở Task 3.
4. **Luật 50 nước ở bộ đếm 99** — vừa đủ điều kiện tuyên bố hòa, nhưng ván **phải tiếp tục**, chỉ báo nhắc. Biến thành kết thúc ván oan là lỗi nghiêm trọng nhất trong nhóm này. → test ở Task 4.
5. **Bắt tốt qua đường không dẫn tới hàng 8** — tốt bắt qua đường đến **hàng 6**, nên theo luật FIDE không bao giờ kết hợp được với phong cấp. Người chơi gõ `axb6=Q` phải được báo lỗi rõ, không được âm thầm bỏ qua phần `=Q` rồi đi nước khác. → test ở Task 3.

---

## Cấu trúc file

| File | Trách nhiệm |
|---|---|
| `requirements.txt` | Khoá phiên bản dependency |
| `.gitignore` | Chặn `__pycache__` |
| `chessai/__init__.py` | Docstring gói |
| `chessai/position.py` | Thế cờ + luật FIDE (bọc `python-chess`), dịch lỗi, kết thúc ván |
| `chessai/render.py` | Hàm thuần vẽ bàn cờ Unicode |
| `chessai/session.py` | Ván đấu: lịch sử, PGN, lùi lượt, kết quả |
| `chessai/cli.py` | REPL, bảng lệnh, cờ khởi động |
| `tests/__init__.py` | Rỗng, để `unittest` khám phá được |
| `tests/test_perft.py` | perft — khói thuốc tích hợp (4 test) |
| `tests/test_render.py` | So chuỗi bàn cờ, cả hai hướng (6 test) |
| `tests/test_position.py` | Áp nước, lỗi, lùi, kết thúc ván (41 test) |
| `tests/test_session.py` | Lượt, PGN, lùi lượt, kết quả (22 test) |
| `tests/test_cli.py` | Tham số, phân tích lệnh, hiển thị (22 test) |
| `tests/test_end_to_end.py` | Cờ tới chiếu hết qua `cli` (5 test) |

---

### Task 1: Dàn khung + perft

Vì luật do `python-chess` lo, perft **không thể** bắt đầu đỏ: nó sẽ xanh ngay. Đây là test khói thuốc tích hợp, không phải TDD đỏ–xanh. Nói rõ để không ai tưởng nó chứng minh luật FIDE đúng.

**Files:**
- Create: `requirements.txt`, `.gitignore`, `chessai/__init__.py`, `tests/__init__.py`, `tests/test_perft.py`

**Interfaces:**
- Consumes: không có
- Produces: môi trường để Task 2+ viết test. Không có symbol nào cho task sau dùng.

- [ ] **Step 1: Cài dependency**

```bash
python -m pip install "python-chess==1.999"
```

Xác nhận bằng `python -c "import chess; print(chess.__version__)"` → phải in `1.11.2` (xem Global Constraints).

- [ ] **Step 2: Ghi `requirements.txt` và `.gitignore`**

`requirements.txt`:
```
python-chess==1.999
```

`.gitignore`:
```
__pycache__/
*.py[cod]
.venv/
```

- [ ] **Step 3: Tạo hai file `__init__.py`**

`chessai/__init__.py`:
```python
"""Chess_ai — cờ vua theo luật FIDE, chơi trên terminal."""
```

`tests/__init__.py` — tạo file rỗng, không nội dung.

- [ ] **Step 4: Viết test perft**

`tests/test_perft.py`:
```python
"""Perft: đếm số nước đi hợp lệ ở từng tầng sâu.

Lưu ý: luật do python-chess thực hiện, nên perft chỉ chứng minh phần nối
của ta đúng (đếm ply, áp nước, gọi đúng API) — KHÔNG chứng minh luật FIDE
đúng. Giá trị thật của test nằm ở các task sau.
"""

import unittest

import chess

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
KIWIPETE = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
PAWNS = "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"
PROMOTION = "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1"


def perft(board: chess.Board, depth: int) -> int:
    """Số nước đi hợp lệ ở độ sâu `depth`, tính từ thế cờ hiện tại."""
    if depth == 0:
        return 1
    total = 0
    for move in board.legal_moves:
        board.push(move)
        total += perft(board, depth - 1)
        board.pop()
    return total


class TestPerft(unittest.TestCase):
    def _check(self, fen: str, depth: int, expected: int) -> None:
        board = chess.Board(fen)
        self.assertEqual(perft(board, depth), expected, f"{fen} depth={depth}")

    def test_start_position(self) -> None:
        for depth, expected in ((1, 20), (2, 400), (3, 8902), (4, 197281)):
            with self.subTest(depth=depth):
                self._check(START, depth, expected)

    def test_kiwipete_castling_and_pins(self) -> None:
        for depth, expected in ((1, 48), (2, 2039), (3, 97862)):
            with self.subTest(depth=depth):
                self._check(KIWIPETE, depth, expected)

    def test_rook_pawn_endgame_en_passant(self) -> None:
        for depth, expected in ((1, 14), (2, 191), (3, 2812)):
            with self.subTest(depth=depth):
                self._check(PAWNS, depth, expected)

    def test_promotion_with_castling_rights(self) -> None:
        for depth, expected in ((1, 6), (2, 264), (3, 9467)):
            with self.subTest(depth=depth):
                self._check(PROMOTION, depth, expected)
```

- [ ] **Step 5: Chạy, kỳ vọng PASS ngay**

Run: `python -m unittest tests.test_perft -v`
Expected: `Ran 4 tests ... OK`

Nếu **fail** ở bước này thì **dừng lại và báo user** — nhiều khả năng bản `python-chess` khác `1.999`, hoặc FEN trong plan sai. Tuyệt đối không sửa con số kỳ vọng để cho xanh.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .gitignore chessai/__init__.py tests/__init__.py tests/test_perft.py
git commit -m "chore: scaffold package and add perft smoke test"
```

---

### Task 2: `render.py` — bàn cờ Unicode

**Files:**
- Create: `chessai/render.py`, `tests/test_render.py`

**Interfaces:**
- Consumes: không có (chỉ cần `chess.Board`)
- Produces — Task 5 và Task 6 gọi:
```python
GLYPHS: dict[tuple[chess.PieceType, chess.Color], str]
def render(board: chess.Board, perspective: chess.Color) -> str
```

- [ ] **Step 1: Viết test đỏ**

`tests/test_render.py`:
```python
import unittest

import chess

from chessai.render import render

START = chess.STARTING_FEN

# Hai FEN này đã kiểm chứng bằng python-chess.
AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
AFTER_E4_E5 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"

WHITE_VIEW = """\
    a   b   c   d   e   f   g   h
  +---+---+---+---+---+---+---+---+
8 | ♜ | ♞ | ♝ | ♛ | ♚ | ♝ | ♞ | ♜ | 8
7 | ♟ | ♟ | ♟ | ♟ | ♟ | ♟ | ♟ | ♟ | 7
6 | . | . | . | . | . | . | . | . | 6
5 | . | . | . | . | . | . | . | . | 5
4 | . | . | . | . | . | . | . | . | 4
3 | . | . | . | . | . | . | . | . | 3
2 | ♙ | ♙ | ♙ | ♙ | ♙ | ♙ | ♙ | ♙ | 2
1 | ♖ | ♘ | ♗ | ♕ | ♔ | ♗ | ♘ | ♖ | 1
  +---+---+---+---+---+---+---+---+
    a   b   c   d   e   f   g   h"""

BLACK_VIEW = """\
    h   g   f   e   d   c   b   a
  +---+---+---+---+---+---+---+---+
1 | ♖ | ♘ | ♗ | ♔ | ♕ | ♗ | ♘ | ♖ | 1
2 | ♙ | ♙ | ♙ | ♙ | ♙ | ♙ | ♙ | ♙ | 2
3 | . | . | . | . | . | . | . | . | 3
4 | . | . | . | . | . | . | . | . | 4
5 | . | . | . | . | . | . | . | . | 5
6 | . | . | . | . | . | . | . | . | 6
7 | ♟ | ♟ | ♟ | ♟ | ♟ | ♟ | ♟ | ♟ | 7
8 | ♜ | ♞ | ♝ | ♛ | ♚ | ♝ | ♞ | ♜ | 8
  +---+---+---+---+---+---+---+---+
    h   g   f   e   d   c   b   a"""


class TestRender(unittest.TestCase):
    def test_start_position_white_view(self) -> None:
        self.assertEqual(render(chess.Board(START), chess.WHITE), WHITE_VIEW)

    def test_start_position_black_view(self) -> None:
        self.assertEqual(render(chess.Board(START), chess.BLACK), BLACK_VIEW)

    def test_views_are_mirror_images(self) -> None:
        """Hai hướng phải ảnh phản chiếu nhau: cùng số dòng, cột đảo chiều."""
        board = chess.Board(START)
        white = render(board, chess.WHITE).splitlines()
        black = render(board, chess.BLACK).splitlines()
        self.assertEqual(len(white), len(black))
        self.assertEqual(white[0].split(), black[0].split()[::-1])

    def test_midgame_position(self) -> None:
        out = render(chess.Board(AFTER_E4), chess.WHITE).splitlines()
        self.assertEqual(out[5], "4 | . | . | . | . | ♙ | . | . | . | 4")
        self.assertEqual(out[6], "5 | . | . | . | . | . | . | . | . | 5")

    def test_black_view_puts_rank_one_on_top(self) -> None:
        out = render(chess.Board(AFTER_E4_E5), chess.BLACK).splitlines()
        self.assertTrue(out[2].startswith("1 |"), out[2])
        self.assertTrue(out[16].startswith("8 |"), out[16])

    def test_board_is_bare(self) -> None:
        """Bàn cờ không in ký hiệu +/# (spec §3.2)."""
        out = render(chess.Board(AFTER_E4), chess.WHITE)
        self.assertNotIn("+", out)
        self.assertNotIn("#", out)
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `python -m unittest tests.test_render -v`
Expected: `ModuleNotFoundError: No module named 'chessai.render'`

- [ ] **Step 3: Viết `chessai/render.py`**

```python
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
```

- [ ] **Step 4: Chạy, kỳ vọng PASS**

Run: `python -m unittest tests.test_render -v`
Expected: `Ran 6 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add chessai/render.py tests/test_render.py
git commit -m "feat: add pure-function unicode board renderer"
```

---

### Task 3: `position.py` — áp nước, dịch lỗi, lùi

**Files:**
- Create: `chessai/position.py`, `tests/test_position.py`

**Interfaces:**
- Consumes: không có
- Produces — Task 4 bổ sung `outcome()` / `is_game_over()` / `termination_text()` / `can_claim_fifty_moves()`; Task 5 và 6 dùng toàn bộ:
```python
MoveError(Exception)
def _shift(square: int, turn: chess.Color) -> int
def _castle_key(san: str) -> str
def _castling_blocker(board: chess.Board, san: str) -> str
def _en_passant_note(board: chess.Board, san: str) -> str
def _castle_notation_note(san: str) -> str

class Position:
    def __init__(self, fen: str = chess.STARTING_FEN) -> None
    @property
    def board(self) -> chess.Board
    @property
    def side_to_move(self) -> chess.Color
    def fen(self) -> str
    def legal_sans(self) -> list[str]
    def san_history(self) -> list[str]
    def ply_count(self) -> int
    def apply_san(self, san: str) -> None
    def undo(self) -> None
```

- [ ] **Step 1: Viết test đỏ**

`tests/test_position.py`:
```python
import unittest

import chess

from chessai.position import MoveError, Position


def play(fen: str, sans: list[str]) -> Position:
    """Dựng thế cờ từ FEN rồi đi lần lượt các nước đã cho."""
    pos = Position(fen)
    for san in sans:
        pos.apply_san(san)
    return pos


class TestApplySan(unittest.TestCase):
    def test_start_position_fen(self) -> None:
        self.assertEqual(Position().fen(), chess.STARTING_FEN)

    def test_side_to_move(self) -> None:
        pos = Position()
        self.assertEqual(pos.side_to_move, chess.WHITE)
        pos.apply_san("e4")
        self.assertEqual(pos.side_to_move, chess.BLACK)

    def test_apply_san_updates_fen(self) -> None:
        # Ô bắt tốt qua đường là '-' vì không tốt nào bắt được (xem Global Constraints).
        pos = play(chess.STARTING_FEN, ["e4", "e5"])
        self.assertEqual(
            pos.fen(), "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
        )

    def test_legal_sans(self) -> None:
        self.assertEqual(len(Position().legal_sans()), 20)

    def test_san_history(self) -> None:
        pos = play(chess.STARTING_FEN, ["e4", "e5", "Nf3"])
        self.assertEqual(pos.san_history(), ["e4", "e5", "Nf3"])

    def test_san_history_from_custom_fen(self) -> None:
        """Lịch sử phải replay từ FEN gốc, không phải từ vị trí xuất phát."""
        pos = play("4k3/8/8/8/8/8/8/4K2R w K - 0 1", ["O-O", "Kd8"])
        self.assertEqual(pos.san_history(), ["O-O", "Kd8"])

    def test_ply_count(self) -> None:
        self.assertEqual(play(chess.STARTING_FEN, ["e4", "e5"]).ply_count(), 2)


class TestIllegalMoves(unittest.TestCase):
    """Bất biến quan trọng nhất: nước sai KHÔNG được đổi thế cờ một ô nào."""

    def _fen_unchanged(self, pos: Position, san: str) -> None:
        before = pos.fen()
        with self.assertRaises(MoveError):
            pos.apply_san(san)
        self.assertEqual(pos.fen(), before)

    def test_illegal_move_leaves_position_untouched(self) -> None:
        self._fen_unchanged(Position(), "e5")

    def test_pawn_blocked_by_enemy_pawn(self) -> None:
        # Tốt trắng e2, tốt đen e3: e3 và e4 đều bị chặn, exd3 cũng vô lý.
        pos = Position("4k3/8/8/8/4p3/4P3/8/4K3 w - - 0 1")
        for san in ("e3", "e4", "exd3"):
            with self.subTest(san=san):
                self._fen_unchanged(pos, san)

    def test_wrong_side_to_move(self) -> None:
        # Tốt trắng không đi được 2 ô từ hàng 2 lên hàng 7.
        self._fen_unchanged(Position(), "a7")

    def test_garbage_input(self) -> None:
        self._fen_unchanged(Position(), "hello")

    def test_illegal_after_history(self) -> None:
        self._fen_unchanged(play(chess.STARTING_FEN, ["e4"]), "Qh4")

    def test_king_into_check_rejected(self) -> None:
        # Vua e1 đang bị xe e2 chiếu; e1 và d2, f2 đều nằm trên đường chiếu.
        pos = Position("4k3/8/8/8/8/8/4r3/4K3 w - - 0 1")
        for san in ("Ke1", "Kd2", "Kf2"):
            with self.subTest(san=san):
                self._fen_unchanged(pos, san)
        # Kf1/Kd1 phải vẫn hợp lệ — nếu "sửa" cho xanh thì hỏng luật.
        for san in ("Kf1", "Kd1"):
            with self.subTest(san=san):
                pos.apply_san(san)

    def test_ambiguous_knight_message(self) -> None:
        pos = Position("4k3/8/8/8/8/8/8/1N1K1N2 w - - 0 1")
        before = pos.fen()
        with self.assertRaises(MoveError) as ctx:
            pos.apply_san("Nd2")
        self.assertIn("Nbd2", str(ctx.exception))
        self.assertEqual(pos.fen(), before)

    def test_garbage_input_suggests_nearby_moves(self) -> None:
        with self.assertRaises(MoveError) as ctx:
            Position().apply_san("hello")
        message = str(ctx.exception)
        self.assertIn("h3", message)
        self.assertIn("Nh3", message)

    def test_castling_notation_accepted(self) -> None:
        pos = play("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", ["O-O"])
        self.assertTrue(pos.board.is_castling(chess.G1))

    def test_annotation_is_rejected(self) -> None:
        """Review Focus #1: người chơi hay gõ kèm ! / ? / ?! từ bài phân tích."""
        for san in ("e4!", "e4?", "e4!!", "Nf3?!"):
            with self.subTest(san=san):
                self._fen_unchanged(Position(), san)

    def test_stray_check_suffix_is_tolerated(self) -> None:
        """python-chess chấp nhận hậu tố +/# thừa. Ghi lại để không ai tưởng là lỗi."""
        for san in ("e4+", "e4#"):
            with self.subTest(san=san):
                pos = Position()
                pos.apply_san(san)
                self.assertEqual(pos.san_history(), ["e4"])

    def test_promotion_queen(self) -> None:
        pos = play("8/P6k/8/8/8/8/8/K7 w - - 0 1", ["a8=Q"])
        self.assertEqual(pos.board.piece_at(chess.A8).piece_type, chess.QUEEN)

    def test_promotion_knight_bishop_rook(self) -> None:
        """Review Focus #2: phong cấp đủ 4 quân, không chỉ hậu."""
        for san, piece in (("a8=N", chess.KNIGHT), ("a8=B", chess.BISHOP), ("a8=R", chess.ROOK)):
            with self.subTest(san=san):
                pos = play("8/P6k/8/8/8/8/8/K7 w - - 0 1", [san])
                self.assertEqual(pos.board.piece_at(chess.A8).piece_type, piece)


class TestEnPassant(unittest.TestCase):
    def test_en_passant_capture_legal(self) -> None:
        pos = play(chess.STARTING_FEN, ["e4", "a6", "e5", "d5", "exd6"])
        self.assertEqual(pos.board.piece_at(chess.D6).color, chess.WHITE)
        self.assertIsNone(pos.board.piece_at(chess.D5))

    def test_en_passant_unavailable_gets_hint(self) -> None:
        pos = Position("4k3/8/8/3pP3/8/8/8/4K3 w - - 0 1")
        before = pos.fen()
        with self.assertRaises(MoveError) as ctx:
            pos.apply_san("exd6")
        self.assertIn("2 ô", str(ctx.exception))
        self.assertEqual(pos.fen(), before)

    def test_en_passant_never_promotes(self) -> None:
        """Review Focus #5: tốt bắt qua đường đến hàng 6, không thể phong cấp."""
        for san in ("axb6", "axb6=Q", "axb6=N"):
            with self.subTest(san=san):
                pos = Position("4k3/8/8/Pp6/8/8/8/4K3 w - b6 0 1")
                before = pos.fen()
                with self.assertRaises(MoveError) as ctx:
                    pos.apply_san(san)
                self.assertIn("không hợp lệ", str(ctx.exception))
                self.assertEqual(pos.fen(), before)


class TestCastlingErrors(unittest.TestCase):
    def test_blocked_king_side_castling_reports_square(self) -> None:
        pos = Position("4k3/8/8/8/8/8/8/R3KB1R w KQ - 0 1")
        before = pos.fen()
        with self.assertRaises(MoveError) as ctx:
            pos.apply_san("O-O")
        self.assertIn("f1", str(ctx.exception))
        self.assertEqual(pos.fen(), before)

    def test_blocked_queen_side_castling_reports_square(self) -> None:
        pos = Position("4k3/8/8/8/8/8/8/RN2K2R w KQ - 0 1")
        with self.assertRaises(MoveError) as ctx:
            pos.apply_san("O-O-O")
        self.assertIn("d1", str(ctx.exception))

    def test_missing_rook_reported(self) -> None:
        # FEN hợp lệ: quyền K còn, nhưng xe đã ở g1 thay vì h1.
        pos = Position("4k3/8/8/8/8/8/8/4K1NR w K - 0 1")
        with self.assertRaises(MoveError) as ctx:
            pos.apply_san("O-O")
        self.assertIn("h1", str(ctx.exception))

    def test_king_returned_to_home_lost_rights(self) -> None:
        """Review Focus #3: vua đi rồi quay lại e1 — quân vẫn ở chỗ, mất quyền."""
        pos = play("4k3/8/8/8/8/8/8/4K2R w K - 0 1", ["Kd2", "Ke7", "Ke1", "Ke8"])
        with self.assertRaises(MoveError) as ctx:
            pos.apply_san("O-O")
        self.assertIn("quyền nhập thành", str(ctx.exception))

    def test_castling_through_attacked_square(self) -> None:
        pos = Position("4k3/8/8/8/8/8/5q2/4K2R w K - 0 1")
        with self.assertRaises(MoveError) as ctx:
            pos.apply_san("O-O")
        self.assertIn("bị tấn công", str(ctx.exception))

    def test_castling_notation_hint_for_king_move(self) -> None:
        pos = Position("4k3/8/8/8/8/8/8/R3K3 w Q - 0 1")
        with self.assertRaises(MoveError) as ctx:
            pos.apply_san("Kg1")
        self.assertIn("O-O", str(ctx.exception))


class TestUndo(unittest.TestCase):
    def test_undo_restores_fen_exactly(self) -> None:
        pos = Position()
        start = pos.fen()
        pos.apply_san("e4")
        pos.apply_san("e5")
        pos.undo()
        pos.undo()
        self.assertEqual(pos.fen(), start)

    def test_undo_restores_ep_and_clocks(self) -> None:
        pos = Position()
        pos.apply_san("e4")
        pos.apply_san("d5")
        target = pos.fen()
        pos.apply_san("exd5")
        pos.undo()
        self.assertEqual(pos.fen(), target)

    def test_undo_on_empty_raises(self) -> None:
        with self.assertRaises(MoveError):
            Position().undo()
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `python -m unittest tests.test_position -v`
Expected: `ModuleNotFoundError: No module named 'chessai.position'`

- [ ] **Step 3: Viết `chessai/position.py`**

```python
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
        return f"thiếu {'xe' if key == 'O-O' else 'tượng'} ở ô {chess.square_name(rook_at)} (nhập thành {side_name})."

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
```

- [ ] **Step 4: Chạy, kỳ vọng PASS**

Run: `python -m unittest tests.test_position -v`
Expected: `Ran 31 tests ... OK`

Nếu test nào fail, kiểm lại FEN trong test bằng `python -c` trước khi sửa code. Đặc biệt `test_king_into_check_rejected`: nếu `Kf1` bị từ chối thì đã hỏng luật, đừng nới assertion.

- [ ] **Step 5: Commit**

```bash
git add chessai/position.py tests/test_position.py
git commit -m "feat: add Position with san validation and Vietnamese errors"
```

---

### Task 4: `position.py` — phát hiện kết thúc ván

Bổ sung vào `chessai/position.py`. Task này sửa một tệp đã tồn tại, không tạo tệp mới.

**Files:**
- Modify: `chessai/position.py` (thêm 4 method vào lớp `Position`, trước dòng `    def undo(self) -> None:`)
- Test: `tests/test_position.py` (thêm `class TestGameEnd`)

**Interfaces:**
- Consumes: `Position._board`, `Position._root_fen` (Task 3)
- Produces — Task 5 dùng:
```python
Position.outcome() -> chess.Outcome | None
Position.is_game_over() -> bool
Position.termination_text() -> str
Position.can_claim_fifty_moves() -> bool
```

- [ ] **Step 1: Viết test đỏ**

Thêm vào cuối `tests/test_position.py`:
```python
class TestGameEnd(unittest.TestCase):
    """Vị trí lặp phải CÓ TỐT, nếu không sẽ dính insufficient_material."""

    def test_checkmate(self) -> None:
        """1. f3 e5 2. g4 Qh4# — thắng thì phải báo thắng, không báo hòa."""
        pos = play(chess.STARTING_FEN, ["f3", "e5", "g4", "Qh4"])
        self.assertTrue(pos.is_game_over())
        self.assertEqual(pos.outcome().termination, chess.Termination.CHECKMATE)
        self.assertEqual(pos.outcome().winner, chess.BLACK)
        self.assertIn("Đen thắng", pos.termination_text())
        self.assertIn("chiếu hết", pos.termination_text())

    def test_stalemate_is_draw_not_checkmate(self) -> None:
        pos = Position("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
        self.assertTrue(pos.is_game_over())
        self.assertEqual(pos.outcome().termination, chess.Termination.STALEMATE)
        self.assertIsNone(pos.outcome().winner)
        self.assertIn("bế tắc", pos.termination_text())

    def test_insufficient_material(self) -> None:
        for fen in ("7k/8/8/8/8/8/8/K7 w - - 0 1", "7k/8/8/8/8/8/8/K6N w - - 0 1",
                    "7k/8/8/8/8/8/8/KB6 w - - 0 1"):
            with self.subTest(fen=fen):
                pos = Position(fen)
                self.assertTrue(pos.is_game_over())
                self.assertEqual(
                    pos.outcome().termination,
                    chess.Termination.INSUFFICIENT_MATERIAL,
                )

    def test_king_bishop_knight_can_still_mate(self) -> None:
        """KBN vẫn chiếu hết được — không được kết luận hòa sớm."""
        pos = Position("7k/8/8/8/8/8/8/KBN5 w - - 0 1")
        self.assertFalse(pos.is_game_over())

    def test_threefold_repetition_ends_game(self) -> None:
        pos = play(
            "4k3/8/8/8/8/8/4P3/4K1N1 w - - 0 1",
            ["Nf3", "Kd7", "Ng1", "Ke8", "Nf3", "Kd7", "Ng1", "Ke8"],
        )
        self.assertTrue(pos.is_game_over())
        self.assertEqual(
            pos.outcome().termination, chess.Termination.THREEFOLD_REPETITION
        )
        self.assertIn("lặp thế cờ 3 lần", pos.termination_text())

    def test_single_repetition_does_not_end_game(self) -> None:
        pos = play("4k3/8/8/8/8/8/4P3/4K1N1 w - - 0 1", ["Nf3", "Kd7", "Ng1", "Ke8"])
        self.assertFalse(pos.is_game_over())
        self.assertIsNone(pos.outcome())

    def test_seventyfive_moves_ends_automatically(self) -> None:
        pos = Position("4k3/8/8/8/8/8/8/4K2R w K - 149 200")
        pos.apply_san("Rh2")
        self.assertTrue(pos.is_game_over())
        self.assertEqual(pos.outcome().termination, chess.Termination.SEVENTYFIVE_MOVES)
        self.assertIn("75", pos.termination_text())

    def test_fifty_moves_is_only_claimable(self) -> None:
        """Review Focus #4: ở bộ đếm 99 chỉ được BÁO, ván phải đi tiếp."""
        pos = Position("4k3/8/8/8/8/8/8/4K2R w K - 99 100")
        pos.apply_san("Rh2")
        self.assertTrue(pos.can_claim_fifty_moves())
        self.assertFalse(pos.is_game_over())
        self.assertEqual(pos.termination_text(), "ván đang diễn ra")

    def test_termination_text_while_running(self) -> None:
        self.assertEqual(Position().termination_text(), "ván đang diễn ra")

    def test_ongoing_position_has_no_outcome(self) -> None:
        pos = play(chess.STARTING_FEN, ["e4", "e5"])
        self.assertIsNone(pos.outcome())
        self.assertFalse(pos.is_game_over())
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `python -m unittest tests.test_position.TestGameEnd -v`
Expected: `AttributeError: 'Position' object has no attribute 'outcome'`

- [ ] **Step 3: Thêm 4 method vào `Position`**

Chèn ngay trước dòng `    def undo(self) -> None:` trong `chessai/position.py`:
```python
    def outcome(self) -> chess.Outcome | None:
        """Kết quả ván, hoặc None nếu ván còn đi.

        Kiểm theo thứ tự ưu tiên của luật (spec §6). Không dùng
        `Board.is_game_over()` / `Board.outcome()` vì chúng coi lặp thế 3 lần
        và 50 nước là quyền tuyên báo của người đến lượt, trái với spec:
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
```

- [ ] **Step 4: Chạy, kỳ vọng PASS**

Run: `python -m unittest tests.test_position -v`
Expected: `Ran 41 tests ... OK`

- [ ] **Step 5: Chạy toàn bộ test**

Run: `python -m unittest -v`
Expected: `OK`, không FAIL, không ERROR.

- [ ] **Step 6: Commit**

```bash
git add chessai/position.py tests/test_position.py
git commit -m "feat: detect checkmate, stalemate and draw rules in Position"
```

---

### Task 5: `session.py` — ván đấu

**Files:**
- Create: `chessai/session.py`, `tests/test_session.py`

**Interfaces:**
- Consumes: `Position`, `MoveError` (Task 3–4)
- Produces — Task 6 dùng:
```python
class Session:
    def __init__(self, human_color: chess.Color | None, elo: int = 1500,
                 style: str = "karpov", mode: str = "coach") -> None
    position: Position          # thuộc tính, không phải method
    human_color: chess.Color | None
    elo: int
    style: str
    mode: str
    on_move: Callable[[str], None] | None
    def apply_san(self, san: str) -> None
    def is_human_turn(self) -> bool
    def is_game_over(self) -> bool
    def undo_turn(self) -> bool
    def pgn(self) -> str
    def movetext(self) -> str
    def status_line(self) -> str
    def result_text(self) -> str
    def last_move_label(self) -> str | None
    def resign(self, by: chess.Color) -> None
    def agree_draw(self) -> None
```

**Vì sao tách `movetext` khỏi `pgn`:** `str(chess.pgn.Game())` luôn kèm header `[Event "?"]` v.v. và phần thân kết thúc bằng ` *`. `pgn()` giữ nguyên định dạng để lưu file; `movetext()` cắt header và dấu `*` để hiện trong REPL.

- [ ] **Step 1: Viết test đỏ**

`tests/test_session.py`:
```python
import unittest

import chess

from chessai.position import MoveError
from chessai.session import Session


class TestTurnEnforcement(unittest.TestCase):
    def test_both_sides_mode_allows_anything(self) -> None:
        s = Session(human_color=None)
        s.apply_san("e4")
        s.apply_san("e5")
        self.assertEqual(s.position.ply_count(), 2)

    def test_not_human_turn_rejected(self) -> None:
        s = Session(human_color=chess.WHITE)
        s.apply_san("e4")
        with self.assertRaises(MoveError) as ctx:
            s.apply_san("e5")
        self.assertIn("lượt", str(ctx.exception))
        self.assertEqual(s.position.ply_count(), 1)

    def test_is_human_turn(self) -> None:
        s = Session(human_color=chess.WHITE)
        self.assertTrue(s.is_human_turn())
        s.apply_san("e4")
        self.assertFalse(s.is_human_turn())

    def test_move_after_game_over_rejected(self) -> None:
        s = Session(human_color=None)
        for san in ["f3", "e5", "g4", "Qh4"]:
            s.apply_san(san)
        self.assertTrue(s.is_game_over())
        with self.assertRaises(MoveError) as ctx:
            s.apply_san("a3")
        self.assertIn("kết thúc", str(ctx.exception))


class TestUndoTurn(unittest.TestCase):
    def test_undo_pops_one_ply_in_both_mode(self) -> None:
        s = Session(human_color=None)
        s.apply_san("e4")
        s.apply_san("e5")
        after_e4 = s.position.fen()
        s.apply_san("Nf3")
        self.assertTrue(s.undo_turn())
        self.assertEqual(s.position.fen(), after_e4)

    def test_undo_pops_two_plies_when_human_has_a_side(self) -> None:
        s = Session(human_color=chess.WHITE)
        start = s.position.fen()
        s.apply_san("e4")
        s.position.apply_san("e5")  # giả lập nước AI; #1 chưa có AI
        self.assertTrue(s.undo_turn())
        self.assertEqual(s.position.fen(), start)

    def test_undo_returns_false_at_start(self) -> None:
        self.assertFalse(Session(human_color=None).undo_turn())

    def test_undo_returns_false_when_only_one_move(self) -> None:
        s = Session(human_color=chess.WHITE)
        s.apply_san("e4")
        self.assertFalse(s.undo_turn())

    def test_undo_clears_declared_result(self) -> None:
        s = Session(human_color=None)
        s.apply_san("e4")
        s.resign(chess.WHITE)
        self.assertTrue(s.is_game_over())
        s.undo_turn()
        self.assertFalse(s.is_game_over())


class TestPgn(unittest.TestCase):
    def test_pgn_keeps_headers(self) -> None:
        s = Session(human_color=None)
        s.apply_san("e4")
        self.assertIn('[Result "*"]', s.pgn())
        self.assertIn("1. e4", s.pgn())

    def test_movetext_strips_headers_and_result_marker(self) -> None:
        s = Session(human_color=None)
        s.apply_san("e4")
        self.assertEqual(s.movetext(), "1. e4")

    def test_movetext_placeholder_when_empty(self) -> None:
        self.assertEqual(Session(human_color=None).movetext(), "*")

    def test_movetext_keeps_check_suffix(self) -> None:
        s = Session(human_color=None)
        for san in ["f3", "e5", "g4", "Qh4"]:
            s.apply_san(san)
        self.assertEqual(s.movetext(), "1. f3 e5 2. g4 Qh4#")

    def test_movetext_multi_move_numbering(self) -> None:
        s = Session(human_color=None)
        for san in ["e4", "e5", "Nf3", "Nc6"]:
            s.apply_san(san)
        self.assertEqual(s.movetext(), "1. e4 e5 2. Nf3 Nc6")


class TestResults(unittest.TestCase):
    def test_resign_awards_win_to_opponent(self) -> None:
        s = Session(human_color=chess.WHITE)
        s.resign(chess.WHITE)
        self.assertTrue(s.is_game_over())
        self.assertIn("Đen thắng", s.result_text())
        self.assertIn("đầu hàng", s.result_text())

    def test_agree_draw(self) -> None:
        s = Session(human_color=chess.WHITE)
        s.agree_draw()
        self.assertTrue(s.is_game_over())
        self.assertIn("HÒA", s.result_text())

    def test_resign_is_ignored_after_game_over(self) -> None:
        s = Session(human_color=None)
        for san in ["f3", "e5", "g4", "Qh4"]:
            s.apply_san(san)
        s.resign(chess.WHITE)
        self.assertIn("chiếu hết", s.result_text())

    def test_result_text_while_running(self) -> None:
        self.assertIn("đang diễn ra", Session(human_color=chess.WHITE).result_text())


class TestStatusLine(unittest.TestCase):
    def test_status_line_shows_config(self) -> None:
        s = Session(human_color=chess.WHITE, elo=2100, style="tal", mode="match")
        line = s.status_line()
        self.assertIn("2100", line)
        self.assertIn("tal", line)
        self.assertIn("match", line)
        self.assertIn("Trắng", line)

    def test_status_line_labels_both_sides(self) -> None:
        self.assertIn("cả hai bên", Session(human_color=None).status_line())

    def test_last_move_label(self) -> None:
        s = Session(human_color=None)
        self.assertIsNone(s.last_move_label())
        s.apply_san("e4")
        self.assertEqual(s.last_move_label(), "e4")


class TestMoveHook(unittest.TestCase):
    def test_on_move_hook_called(self) -> None:
        s = Session(human_color=None)
        seen: list[str] = []
        s.on_move = seen.append
        s.apply_san("e4")
        self.assertEqual(seen, ["e4"])

    def test_on_move_hook_not_called_on_error(self) -> None:
        s = Session(human_color=None)
        seen: list[str] = []
        s.on_move = seen.append
        with self.assertRaises(MoveError):
            s.apply_san("e5")
        self.assertEqual(seen, [])
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `python -m unittest tests.test_session -v`
Expected: `ModuleNotFoundError: No module named 'chessai.session'`

- [ ] **Step 3: Viết `chessai/session.py`**

```python
"""Ván đấu: lịch sử nước đi, PGN, lùi lượt, kết quả.

Ở #1 chưa có AI. `human_color=None` nghĩa là người chơi đi cả hai bên —
chế độ thử nghiệm để tự lái một ván trọn vẹn nhằm kiểm chứng luật.
#2 sẽ thay bằng người chơi thật, cắm vào `on_move`.
"""

from __future__ import annotations

from typing import Callable

import chess
import chess.pgn

from .position import MoveError, Position

Color = chess.Color


class Session:
    def __init__(
        self,
        human_color: Color | None,
        elo: int = 1500,
        style: str = "karpov",
        mode: str = "coach",
    ) -> None:
        self.position = Position()
        self.human_color = human_color
        self.elo = elo
        self.style = style
        self.mode = mode
        # Điểm móc cho #2: gán callback sau mỗi nước đi. Ở #1 là None.
        self.on_move: Callable[[str], None] | None = None
        # (người thắng hoặc None, lý do bằng tiếng Việt) khi kết thúc bằng tuyên bố.
        self._declared: tuple[Color | None, str] | None = None

    def is_human_turn(self) -> bool:
        if self.human_color is None:
            return True
        if self.is_game_over():
            return False
        return self.position.side_to_move == self.human_color

    def is_game_over(self) -> bool:
        return self._declared is not None or self.position.is_game_over()

    def result_text(self) -> str:
        if self._declared is not None:
            return self._declared[1]
        return self.position.termination_text()

    def apply_san(self, san: str) -> None:
        if self.is_game_over():
            raise MoveError(f"Ván đã kết thúc: {self.result_text()}")
        if not self.is_human_turn():
            side = "Trắng" if self.position.side_to_move else "Đen"
            raise MoveError(f"Chưa đến lượt bạn — đang là lượt của {side}.")
        self.position.apply_san(san)
        if self.on_move is not None:
            self.on_move(san)

    def undo_turn(self) -> bool:
        """Lùi đúng một lượt. False nếu không đủ nước để lùi."""
        plies = 1 if self.human_color is None else 2
        if self.position.ply_count() < plies:
            return False
        for _ in range(plies):
            self.position.undo()
        self._declared = None
        return True

    def resign(self, by: Color) -> None:
        if self.is_game_over():
            return
        winner: Color = chess.WHITE if by == chess.BLACK else chess.BLACK
        loser = "Trắng" if by == chess.WHITE else "Đen"
        self._declared = (
            winner,
            f"{'Trắng' if winner else 'Đen'} thắng — {loser} đầu hàng",
        )

    def agree_draw(self) -> None:
        if self.is_game_over():
            return
        self._declared = (None, "HÒA: hai bên đồng ý hòa")

    def last_move_label(self) -> str | None:
        history = self.position.san_history()
        return history[-1] if history else None

    def pgn(self) -> str:
        """PGN đầy đủ kèm header và dấu kết quả, dùng để lưu file."""
        game = chess.pgn.Game()
        node: chess.pgn.GameNode = game
        replay = chess.Board(self.position.board.root().fen())
        for san in self.position.san_history():
            move = replay.parse_san(san)
            replay.push(move)
            node = node.add_variation(move)
        return str(game)

    def movetext(self) -> str:
        """Chỉ phần nước đi, bỏ header PGN và dấu `*` — dùng để in trong REPL."""
        text = self.pgn().partition("\n\n")[2].strip()
        if text.endswith("*"):
            text = text[:-1].strip()
        return text or "*"

    def status_line(self) -> str:
        return (
            f"Chế độ: {self.mode} | AI: ELO {self.elo} · {self.style} | "
            f"Bạn: {self._side_label()} | Đến lượt: {self._turn_label()}"
        )

    def _side_label(self) -> str:
        if self.human_color is None:
            return "cả hai bên"
        return "Trắng" if self.human_color else "Đen"

    def _turn_label(self) -> str:
        if self.is_game_over():
            return "ván đã xong"
        if self.human_color is None:
            who = "Trắng" if self.position.side_to_move else "Đen"
            return f"{who} (chế độ hai bên)"
        side = "Trắng" if self.position.side_to_move else "Đen"
        who = "bạn" if self.position.side_to_move == self.human_color else "AI"
        return f"{side} ({who})"
```

- [ ] **Step 4: Chạy, kỳ vọng PASS**

Run: `python -m unittest tests.test_session -v`
Expected: `Ran 22 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add chessai/session.py tests/test_session.py
git commit -m "feat: add Session with pgn, undo-turn and declared results"
```

---

### Task 6: `cli.py` — REPL

**Files:**
- Create: `chessai/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `render()` (Task 2), `Position` / `MoveError` (Task 3–4), `Session` (Task 5)
- Produces:
```python
COMING_SOON: frozenset[str]
class Quit(Exception)
def _parse_args(argv: list[str] | None) -> argparse.Namespace
def _build_session(args: argparse.Namespace) -> Session
def _perspective(session: Session) -> chess.Color
def _report(session: Session) -> str
def _dispatch(session: Session, raw: str) -> str
def main(argv: list[str] | None = None) -> int
```

Không viết lại logic cắt header PGN ở đây — `Session.movetext()` đã lo. Tái dùng code, đừng chép.

- [ ] **Step 1: Viết test đỏ**

`tests/test_cli.py`:
```python
import unittest

import chess

from chessai import cli
from chessai.position import MoveError
from chessai.session import Session


def both() -> Session:
    return Session(human_color=None)


class TestArgParsing(unittest.TestCase):
    def test_defaults(self) -> None:
        args = cli._parse_args([])
        self.assertEqual(args.side, "white")
        self.assertFalse(args.both)
        self.assertEqual(args.elo, 1500)
        self.assertEqual(args.style, "karpov")
        self.assertEqual(args.mode, "coach")

    def test_overrides(self) -> None:
        args = cli._parse_args(
            ["--side", "black", "--elo", "2400", "--style", "tal", "--mode", "match"]
        )
        self.assertEqual(args.side, "black")
        self.assertEqual(args.elo, 2400)
        self.assertEqual(args.style, "tal")
        self.assertEqual(args.mode, "match")

    def test_both_flag_wins_over_side(self) -> None:
        session = cli._build_session(cli._parse_args(["--side", "white", "--both"]))
        self.assertIsNone(session.human_color)

    def test_side_black(self) -> None:
        session = cli._build_session(cli._parse_args(["--side", "black"]))
        self.assertEqual(session.human_color, chess.BLACK)


class TestDispatch(unittest.TestCase):
    def test_move_returns_report(self) -> None:
        out = cli._dispatch(both(), "e4")
        self.assertIn("♙", out)
        self.assertIn("Nước vừa đi: e4", out)
        self.assertIn("1. e4", out)

    def test_board_command(self) -> None:
        self.assertIn("♜", cli._dispatch(both(), "/board"))

    def test_fen_command(self) -> None:
        self.assertEqual(cli._dispatch(both(), "/fen"), chess.STARTING_FEN)

    def test_pgn_command(self) -> None:
        s = both()
        s.apply_san("e4")
        self.assertEqual(cli._dispatch(s, "/pgn"), "1. e4")

    def test_help_lists_commands(self) -> None:
        out = cli._dispatch(both(), "/help")
        for name in ("/board", "/fen", "/pgn", "/undo", "/resign", "/draw", "/quit"):
            self.assertIn(name, out)

    def test_unknown_command(self) -> None:
        out = cli._dispatch(both(), "/khongco")
        self.assertIn("/khongco", out)
        self.assertIn("/help", out)

    def test_coming_soon_commands(self) -> None:
        for name in ("/hint", "/best", "/eval", "/analyze", "/puzzle", "/elo", "/style"):
            with self.subTest(name=name):
                self.assertIn("chưa hỗ trợ", cli._dispatch(both(), name))

    def test_coming_soon_ignores_arguments(self) -> None:
        self.assertIn("chưa hỗ trợ", cli._dispatch(both(), "/elo 2400"))

    def test_undo_command(self) -> None:
        s = both()
        s.apply_san("e4")
        out = cli._dispatch(s, "/undo")
        self.assertIn("Đã lùi", out)
        self.assertEqual(s.position.fen(), chess.STARTING_FEN)

    def test_undo_command_at_start(self) -> None:
        self.assertIn("Không có nước", cli._dispatch(both(), "/undo"))

    def test_resign_command(self) -> None:
        self.assertIn("đầu hàng", cli._dispatch(both(), "/resign"))

    def test_draw_command(self) -> None:
        self.assertIn("HÒA", cli._dispatch(both(), "/draw"))

    def test_illegal_move_propagates(self) -> None:
        with self.assertRaises(MoveError):
            cli._dispatch(both(), "e5")

    def test_quit_raises(self) -> None:
        with self.assertRaises(cli.Quit):
            cli._dispatch(both(), "/quit")


class TestReport(unittest.TestCase):
    def test_perspective_follows_human_colour(self) -> None:
        self.assertEqual(cli._perspective(Session(human_color=chess.BLACK)), chess.BLACK)

    def test_perspective_defaults_white_in_both_mode(self) -> None:
        self.assertEqual(cli._perspective(Session(human_color=None)), chess.WHITE)

    def test_report_mentions_fifty_move_advisory(self) -> None:
        s = Session(human_color=None)
        s.position = Position("4k3/8/8/8/8/8/8/4K2R w K - 99 100")
        self.assertIn("50 nước", cli._report(s))

    def test_report_shows_end_of_game(self) -> None:
        s = both()
        for san in ["f3", "e5", "g4", "Qh4"]:
            s.apply_san(san)
        report = cli._report(s)
        self.assertIn("KẾT THÚC", report)
        self.assertIn("chiếu hết", report)
```

Thêm import cần thiết ở đầu `tests/test_cli.py`:
```python
from chessai.position import MoveError, Position
```
(thay cho dòng `from chessai.position import MoveError` đã có trong khối trên).

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `python -m unittest tests.test_cli -v`
Expected: `ModuleNotFoundError: No module named 'chessai.cli'`

- [ ] **Step 3: Viết `chessai/cli.py`**

```python
"""REPL: phân tích lệnh rồi gọi Session."""

from __future__ import annotations

import argparse

import chess

from . import render
from .position import MoveError
from .session import Session

# Lệnh của #2. Ở #1 phải báo "chưa hỗ trợ" chứ không báo "không tồn tại",
# để không tạo cảm giác lỗi (spec §3.4).
COMING_SOON = frozenset(
    {"/hint", "/best", "/eval", "/analyze", "/puzzle", "/elo", "/style"}
)

_HELP = """Lệnh có sẵn:
  /board    Vẽ lại bàn cờ
  /fen      In FEN hiện tại
  /pgn      In chuỗi nước đi
  /undo     Lùi 1 lượt
  /resign   Đầu hàng
  /draw     Kết thúc ván hòa (chưa có đối thủ để đàm phán ở #1)
  /help     Xem danh sách này
  /quit     Thoát
Nước đi gõ kiểu SAN: e4, Nf3, O-O, exd5, e8=Q"""


class Quit(Exception):
    """Người dùng yêu cầu thoát."""


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="chessai", description="Cờ vua theo luật FIDE, chơi trên terminal."
    )
    parser.add_argument("--side", choices=["white", "black"], default="white")
    parser.add_argument(
        "--both", action="store_true", help="Đi cả hai bên (chế độ thử nghiệm)"
    )
    parser.add_argument("--elo", type=int, default=1500)
    parser.add_argument("--style", default="karpov")
    parser.add_argument("--mode", default="coach")
    return parser.parse_args(argv)


def _build_session(args: argparse.Namespace) -> Session:
    if args.both:
        human: chess.Color | None = None
    else:
        human = chess.WHITE if args.side == "white" else chess.BLACK
    return Session(human_color=human, elo=args.elo, style=args.style, mode=args.mode)


def _perspective(session: Session) -> chess.Color:
    return session.human_color if session.human_color is not None else chess.WHITE


def _report(session: Session) -> str:
    """Báo cáo chuẩn sau mỗi lượt: bàn cờ, nước vừa đi, chuỗi nước đi, trạng thái."""
    lines = [render.render(session.position.board, _perspective(session))]
    last = session.last_move_label()
    if last:
        lines.append(f"Nước vừa đi: {last}")
    lines.append(f"Nước đi: {session.movetext()}")
    lines.append(session.status_line())
    if session.position.can_claim_fifty_moves() and not session.is_game_over():
        lines.append("Có thể đề nghị hòa theo luật 50 nước.")
    if session.is_game_over():
        lines.append(f"KẾT THÚC: {session.result_text()}")
    return "\n".join(lines)


def _cmd_board(session: Session, arg: str) -> str:
    return render.render(session.position.board, _perspective(session))


def _cmd_fen(session: Session, arg: str) -> str:
    return session.position.fen()


def _cmd_pgn(session: Session, arg: str) -> str:
    return session.movetext()


def _cmd_undo(session: Session, arg: str) -> str:
    if not session.undo_turn():
        return "Không có nước nào để lùi."
    return "Đã lùi 1 lượt."


def _cmd_resign(session: Session, arg: str) -> str:
    loser = session.human_color if session.human_color is not None else chess.WHITE
    session.resign(loser)
    return session.result_text()


def _cmd_draw(session: Session, arg: str) -> str:
    session.agree_draw()
    return session.result_text()


def _cmd_quit(session: Session, arg: str) -> str:
    raise Quit()


COMMANDS = {
    "/board": _cmd_board,
    "/fen": _cmd_fen,
    "/pgn": _cmd_pgn,
    "/undo": _cmd_undo,
    "/resign": _cmd_resign,
    "/draw": _cmd_draw,
    "/help": lambda s, a: _HELP,
    "/quit": _cmd_quit,
}


def _dispatch(session: Session, raw: str) -> str:
    """Xử lý một dòng người dùng gõ. Ném `MoveError` nếu nước đi sai."""
    if not raw.startswith("/"):
        session.apply_san(raw)
        return _report(session)
    name, _, arg = raw.partition(" ")
    if name in COMING_SOON:
        return f"Lệnh '{name}' chưa hỗ trợ ở phiên bản #1 (sẽ có ở #2)."
    handler = COMMANDS.get(name)
    if handler is None:
        return f"Không có lệnh '{name}'. Gõ /help để xem danh sách."
    return handler(session, arg.strip())


def main(argv: list[str] | None = None) -> int:
    session = _build_session(_parse_args(argv))
    print(f"Chess_ai — chế độ {session.mode}, AI ELO {session.elo} ({session.style})")
    print("Gõ /help để xem lệnh. Kết thúc bằng /quit.\n")
    print(_report(session))
    while True:
        try:
            raw = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not raw:
            continue
        if raw == "/quit":
            return 0
        try:
            print(_dispatch(session, raw))
        except MoveError as exc:
            print(f"Lỗi: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Chạy, kỳ vọng PASS**

Run: `python -m unittest tests.test_cli -v`
Expected: `Ran 22 tests ... OK`

- [ ] **Step 5: Chạy thật để kiểm tra hiển thị**

```bash
python -m chessai.cli --both
```
Gõ lần lượt: `e4`, `e5`, `Nf3`, `/board`, `/fen`, `/pgn`, `/undo`, `/help`, `/quit`

Kiểm bằng mắt: bàn cờ đủ 8 hàng, ký hiệu quân đúng, `/undo` trả về đúng vị trí trước, `/quit` thoát sạch.

- [ ] **Step 6: Commit**

```bash
git add chessai/cli.py tests/test_cli.py
git commit -m "feat: add interactive cli with command table"
```

---

### Task 7: Chạy hết một ván tới chiếu hết

Bắt lỗi tích hợp mà unit test từng phần không thấy: hiển thị sai, lệnh hỏng sau khi ván kết thúc, PGN hỏng khi ván dài.

**Files:**
- Create: `tests/test_end_to_end.py`

**Interfaces:**
- Consumes: `cli._dispatch`, `cli._report` (Task 6), `Session` (Task 5)
- Produces: không có

- [ ] **Step 1: Viết test**

`tests/test_end_to_end.py`:
```python
import io

import chess.pgn
import unittest

from chessai import cli
from chessai.session import Session

Ruy_LOPEZ = [
    "e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6",
    "O-O", "Be7", "Re1", "b5", "Bb3", "d6", "c3", "O-O",
    "h3", "Nb8", "d4", "Nbd7",
]


def drive(sans: list[str]) -> tuple[Session, list[str]]:
    """Chạy chuỗi lệnh qua cli, trả về session và mọi kết quả in ra."""
    session = Session(human_color=None)
    return session, [cli._dispatch(session, san) for san in sans]


class TestFullGame(unittest.TestCase):
    def test_fools_mate_through_cli(self) -> None:
        session, reports = drive(["f3", "e5", "g4", "Qh4"])
        self.assertTrue(session.is_game_over())
        self.assertIn("KẾT THÚC", reports[-1])
        self.assertIn("Đen thắng", reports[-1])
        self.assertIn("chiếu hết", reports[-1])
        self.assertIn("Qh4#", reports[-1])

    def test_board_still_renders_after_mate(self) -> None:
        session, _ = drive(["f3", "e5", "g4", "Qh4"])
        out = cli._dispatch(session, "/board")
        self.assertIn("♛", out)
        self.assertNotIn("KẾT THÚC", out)

    def test_undo_after_mate_reopens_game(self) -> None:
        session, _ = drive(["f3", "e5", "g4", "Qh4"])
        self.assertTrue(session.is_game_over())
        cli._dispatch(session, "/undo")
        self.assertFalse(session.is_game_over())
        self.assertNotIn("KẾT THÚC", cli._report(session))

    def test_illegal_move_prints_error_and_keeps_board(self) -> None:
        session, _ = drive(["e4", "e5"])
        before = session.position.fen()
        with self.assertRaises(cli.MoveError):
            cli._dispatch(session, "Qh4")
        self.assertEqual(session.position.fen(), before)

    def test_pgn_roundtrips_over_twenty_plies(self) -> None:
        session, _ = drive(RUY_LOPEZ)
        self.assertEqual(len(session.position.san_history()), 20)
        game = chess.pgn.read_game(io.StringIO(session.pgn()))
        self.assertIsNotNone(game)
        self.assertEqual(len(list(game.mainline_moves())), 20)

    def test_pgn_replays_to_identical_position(self) -> None:
        session, _ = drive(RUY_LOPEZ)
        target = session.position.fen()
        game = chess.pgn.read_game(io.StringIO(session.pgn()))
        replay = chess.Board()
        for move in game.mainline_moves():
            replay.push(move)
        self.assertEqual(replay.fen(), target)

    def test_board_matches_fen_after_many_moves(self) -> None:
        _, reports = drive(RUY_LOPEZ)
        self.assertIn("5 | . | . | . | . | ♟ | . | . | . | 5", reports[-1])
        self.assertIn("5 | . | . | . | . | . | . | . | . | 5", reports[-1][:1200])
```

- [ ] **Step 2: Chạy, kỳ vọng PASS ngay**

Run: `python -m unittest tests.test_end_to_end -v`
Expected: `Ran 7 tests ... OK`

Không phải đỏ-vàng-xanh: Task 7 chỉ ghép các phần đã xanh ở Task 2–6. Nếu **fail** thì phát hiện lỗi tích hợp — dừng lại và báo user, đừng nới assertion.

- [ ] **Step 3: Chạy toàn bộ test lần cuối**

Run: `python -m unittest -v`
Expected: `OK`. Số test theo từng file: perft 4, render 6, position 41, session 22, cli 22, end_to_end 7.

- [ ] **Step 4: Commit**

```bash
git add tests/test_end_to_end.py
git commit -m "test: add end-to-end game to checkmate"
```

---

## Kiểm tra cuối (không commit)

```bash
python -m unittest -v
git status --short
git log --oneline
```

Xác nhận: `OK`, `git status --short` rỗng, log có đúng 7 commit từ Task 1 tới Task 7.

Chạy thử cả hai hướng nhìn để xác nhận bằng mắt:
```bash
python -m chessai.cli --side black
python -m chessai.cli --both --elo 2400 --style tal --mode match
```
