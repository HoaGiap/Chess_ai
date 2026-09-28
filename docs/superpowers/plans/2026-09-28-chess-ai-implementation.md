# Đấu với máy (#3B) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or
> superpowers:subagent-driven-development) to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm đối thủ máy vào bàn cờ web — người chơi chọn phe và Elo, bấm một
nước, thấy quân mình di chuyển ngay, rồi AI trả lời sau ở một thread nền.

**Architecture:** Engine tự viết (`chessai/engine.py`) là negamax + alpha-beta +
quiescence + lặp tăng dần theo độ sâu, chạy trên `chess.Board`. Một
`AIController` ở tầng web cắm vào `Session.on_move`: đặt cờ `thinking=True` rồi
đẩy việc tìm nước vào `ThreadPoolExecutor`. Thread AI **không** giữ khoá ván
trong lúc tìm — nó đọc FEN lúc bắt đầu, tìm xong mới giữ khoá để so FEN rồi áp.
Trình duyệt hỏi lại `GET /api/game/{id}` mỗi 300 ms khi `thinking` là đúng.

**Tech Stack:** python-chess (đã có), FastAPI, `unittest`, HTML/CSS/JS thuần.
Không thêm gói mới. Không có bước build.

**Spec:** `docs/superpowers/specs/2026-09-28-chess-ai-design.md`

## Global Constraints

- **Không thêm phụ thuộc.** Không `pip install`. Chỉ dùng: `chess` (python-chess),
  `fastapi`, `uvicorn`, `pydantic`, `threading`/`concurrent.futures` của thư viện
  chuẩn.
- **Máy chủ giữ toàn bộ luật cờ vua; trình duyệt KHÔNG có một dòng luật cờ vua
  nào.** Engine sống trong Python. `app.js` chỉ khớp chuỗi với `state`.
- **Mọi thông điệp người thấy bằng tiếng Việt có dấu.**
- **Khoá theo ván, giữ ngắn.** Không được giữ khoá ván qua lúc tìm nước.
- **158 test của #1 và 236 test của #3A phải xanh suốt.**
- **Cách kiểm thử:** `unittest` cho Python. Phía trình duyệt kiểm bằng trình
  duyệt thật (không có framework JS — xem spec #3A §6). Dòng cờ phải **chạy
  thật** qua python-chess để xác minh, không viết từ trí nhớ.
- **Sao chép bảng điểm vị trí được phép** phải ghi nguồn trong comment.

## Review Focus

Năm điều dưới đây là loại lỗi mà spec hứa nhưng không task nào kiểm thử tự
nhiên, và sẽ làm người dùng thấy sai:

1. **Người chơi chọn phe Đen.** AI phải nghĩ ngay khi ván vừa tạo, không đợi
   người đi — nếu không, bàn cờ treo vô thời hạn ở vị trí xuất phát.
2. **Người chơi bấm "Ván mới" hoặc "Lùi" trong lúc AI đang nghĩ.** Nước AI phải
   bị bỏ, không được áp vào thế cờ khác.
3. **AI nghĩ lâu thì bàn cờ có còn phản hồi không.** `GET` và "Lùi" phải trả lời
   được trong lúc tìm, vì khoá ván bị giữ quá lâu sẽ treo cả trang.
4. **Ở Elo thấp AI vẫn phải đi nước hợp lệ.** Cho máy "chơi yếu" bằng cách chọn
   nước tệ là đúng; bằng cách trả nước bất hợp phệ thì mất cả ván.
5. **Người chơi bấm vào quân của máy.** Không được hiện chấm tròn nào, và không
   được gửi gì lên máy chủ.

---

### Task 1: Engine — bảng điểm và hàm đánh giá

**Files:**
- Create: `chessai/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `chess.Board`, `chess.square_index`, `chess.piece_type_at`
- Produces:
  - `VALUES: dict[int, int]` — giá trị vật chất theo `chess.PAWN`…
  - `evaluate(board: chess.Board) -> int` — điểm **tương đối theo góc nhìn phe
    đang đi** (trắng thì dương khi trắng hơn)
  - `min_material(board) -> int` — tổng giá trị quân của phe yếu hơn, dùng để
    kéo điểm về 0 khi còn ít quân

- [ ] **Step 1: Viết test đỏ — `tests/test_engine.py`**

```python
"""Engine tự viết: bảng điểm vị trí + hàm đánh giá thế cờ."""

import unittest

import chess

from chessai import engine


class TestMaterial(unittest.TestCase):
    def test_trang_them_mot_tot_thi_diem_duong(self) -> None:
        board = chess.Board("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")   # Q vs trống, trắng đi
        self.assertGreater(engine.evaluate(board), 0)

    def test_quan_hon_luon_duoc_diem_duong(self) -> None:
        for fen in (
            "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1",
            "4k3/8/8/8/8/8/4N3/4K3 w - - 0 1",
            "4k3/8/8/8/8/8/4B3/4K3 w - - 0 1",
            "4k3/8/8/8/8/8/4R3/4K3 w - - 0 1",
            "4k3/8/8/8/8/8/4Q3/4K3 w - - 0 1",
        ):
            with self.subTest(fen=fen):
                self.assertGreater(engine.evaluate(chess.Board(fen)), 0)

    def test_chua_quan_thi_diem_bang_khong(self) -> None:
        board = chess.Board("4k3/4K3/8/8/8/8/8/8 w - - 0 1")
        self.assertEqual(engine.evaluate(board), 0)

    def test_gia_tri_dung_thu_tu(self) -> None:
        self.assertLess(engine.VALUES[chess.PAWN], engine.VALUES[chess.KNIGHT])
        self.assertLess(engine.VALUES[chess.KNIGHT], engine.VALUES[chess.BISHOP])
        self.assertLess(engine.VALUES[chess.BISHOP], engine.VALUES[chess.ROOK])
        self.assertLess(engine.VALUES[chess.ROOK], engine.VALUES[chess.QUEEN])


class TestSymmetry(unittest.TestCase):
    def test_doi_phe_thi_diem_doi_dau(self) -> None:
        """Bảng điểm lệch phe sẽ hỏng im lặng và engine sẽ chơi yếu ở một màu."""
        for fen in (
            chess.STARTING_FEN,
            "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
            "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2",
        ):
            with self.subTest(fen=fen):
                white = chess.Board(fen)
                black = chess.Board(fen)
                black.turn = chess.BLACK
                self.assertEqual(
                    engine.evaluate(white), -engine.evaluate(black), fen
                )


class TestPositionTables(unittest.TestCase):
    def test_quan_di_dung_o_dich_duoc_thuong(self) -> None:
        """Đưa xe từ h1 lên h8 phải tăng điểm — bảng vị trí có thật sự được dùng."""
        board = chess.Board()
        board.set_piece_at(chess.H1, chess.Piece(chess.ROOK, chess.WHITE))
        thuong = engine.evaluate(board)

        moved = chess.Board()
        moved.set_piece_at(chess.H8, chess.Piece(chess.ROOK, chess.WHITE))
        self.assertGreater(engine.evaluate(moved), thuong)

    def test_bang_vi_tri_dung_64_o(self) -> None:
        for ten, bang in engine.PST.items():
            with self.subTest(bang=ten):
                self.assertEqual(len(bang), 64, ten)
                self.assertTrue(all(isinstance(x, int) for x in bang))

    def test_min_material_tinh_dung_phe(self) -> None:
        board = chess.Board("4k3/8/8/8/8/8/4R3/4K3 w - - 0 1")
        self.assertEqual(
            engine.min_material(board),
            min(engine.VALUES[chess.PAWN], engine.VALUES[chess.ROOK]),
        )


class TestNoRegretCheck(unittest.TestCase):
    def test_hau_dung_o_giua_ban_diem_phai_cao(self) -> None:
        """Hậu giữa bàn hơn hậu ở góc — nếu bảng bị đảo dấu thì hỏng."""
        giua = chess.Board("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")
        goc = chess.Board("4k3/8/8/8/8/8/8/Q3K3 w - - 0 1")
        self.assertGreater(engine.evaluate(giua), engine.evaluate(goc))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `python -m unittest tests.test_engine`
Expected: `ModuleNotFoundError: No module named 'chessai.engine'`

- [ ] **Step 3: Viết `chessai/engine.py` (phần đánh giá)**

```python
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


def _mirror(square: int) -> int:
    """Đảo ô qua đường giữa bàn: h1 <-> h8, a4 <-> a5."""
    return square ^ 56


def piece_square(piece: chess.Piece) -> int:
    """Điểm vị trí của một quân, luôn viết theo góc nhìn phe TRẮNG."""
    index = 63 - chess.square_index(piece.square)  # 0 = a8
    if piece.color == chess.BLACK:
        index = _mirror(index)
    return PST[piece.symbol().upper()][index]


def material(board: chess.Board, color: chess.Color) -> int:
    return sum(
        VALUES[p.piece_type] for p in board.piece_map.values() if p.color == color
    )


def min_material(board: chess.Board) -> int:
    """Tổng giá trị quân của phe ÍT quân hơn (bỏ vua ra: vua không bị ăn)."""
    white = sum(
        VALUES[p.piece_type]
        for p in board.piece_map.values()
        if p.color == chess.WHITE and p.piece_type != chess.KING
    )
    black = sum(
        VALUES[p.piece_type]
        for p in board.piece_map.values()
        if p.color == chess.BLACK and p.piece_type != chess.KING
    )
    return min(white, black)


def evaluate(board: chess.Board) -> int:
    """Điểm tương đối, **theo góc nhìn phe đang đi**.

    Kéo dần về 0 theo số quân còn lại: ở cuối ván, mất một tốt là thua thật,
    nhưng ở thế mở đầu thì chưa — nếu không, AI sẽ hoàn cảnh tốt trong mọi thế.
    """
    score = 0
    for piece in board.piece_map.values():
        value = VALUES[piece.piece_type] + piece_square(piece)
        score += value if piece.color == chess.WHITE else -value
    score = (score * min_material(board)) // 5_800
    return score if board.turn == chess.WHITE else -score
```

- [ ] **Step 4: Chạy, kỳ vọng PASS**

Run: `python -m unittest tests.test_engine`
Expected: `Ran 12 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add chessai/engine.py tests/test_engine.py
git commit -m "feat(engine): add piece-square tables and positional evaluation"
```

---

### Task 2: Engine — quiescence, negamax, `think`, lịch Elo

**Files:**
- Modify: `chessai/engine.py`
- Modify: `tests/test_engine.py`

**Interfaces:**
- Consumes: `evaluate`, `VALUES` (Task 1)
- Produces:
  - `profile_for(elo: int) -> tuple[int, float, int, float]` → `(max_depth,
    blunder_rate, slack_cp, max_seconds)`
  - `think(board: chess.Board, elo: int = 1500, min_seconds: float = 0.6) -> chess.Move | None`
  - `clamp_time(board, max_seconds, min_seconds) -> float` (chỉ dùng nội bộ)
  - `search(board, max_depth, deadline, max_seconds) -> tuple[chess.Move | None, list[chess.Move]]`
    → `(nước tốt nhất, mọi nước hợp lệ xếp theo điểm giảm dần)`

- [ ] **Step 1: Viết test đỏ — thêm vào `tests/test_engine.py`**

```python
class TestProfile(unittest.TestCase):
    def test_elo_thap_cho_tim_nong_va_game_hon(self) -> None:
        thap = engine.profile_for(700)
        cao = engine.profile_for(2300)
        self.assertLess(thap[0], cao[0])            # max_depth
        self.assertGreater(thap[1], cao[1])         # blunder_rate
        self.assertGreater(thap[2], cao[2])         # slack_cp
        self.assertLess(thap[3], cao[3])            # max_seconds

    def test_noi_suy_tuyen_tinh(self) -> None:
        self.assertEqual(engine.profile_for(600)[0], 1)
        self.assertEqual(engine.profile_for(750)[0], 2)   # nằm giữa 600 và 900

    def test_kep_o_hai_dau(self) -> None:
        self.assertEqual(engine.profile_for(100)[0], engine.profile_for(600)[0])
        self.assertEqual(engine.profile_for(9999)[0], engine.profile_for(2400)[0])

    def test_elo_2400_khong_cho_phep_sai(self) -> None:
        self.assertEqual(engine.profile_for(2400)[1], 0.0)


class TestThink(unittest.TestCase):
    def _an(self, san: str) -> chess.Board:
        board = chess.Board()
        for one in san.split():
            board.push_san(one)
        return board

    def test_khong_con_nuoc_di_thi_tra_none(self) -> None:
        board = self._an("f3 e5 g4 Qh4#")
        self.assertIsNone(engine.think(board, 1500, 0.0))

    def test_nguoi_choi_bi_chieu_thi_ai_phai_trai_lai(self) -> None:
        # Trắng đi Nf3?? đen chiếu Qh4 — phải trả gxf3 hoặc Nf3 không, chọn đúng
        # nước chặn/đáp.
        board = self._an("e4 e5 Qh5 Nc6 Bc4 Nf6")
        nuoc = engine.think(board, 2400, 0.0)
        self.assertIsNotNone(nuoc)
        board.push(nuoc)
        self.assertFalse(board.is_check(), board.san(nuoc))

    def test_ai_khong_tu_tra_nuoc_lam_mat_quan(self) -> None:
        board = self._an("e4 e5 Nf3 Nc6 Bc4 Bc5")
        nuoc = engine.think(board, 2400, 0.0)
        self.assertIsNotNone(nuoc)
        from_square = chess.square_name(nuoc.from_square)
        self.assertNotIn(from_square, ("f1", "g1"), "mất quân vô điều kiện")

    def test_ai_tim_duoc_nuoc_chan_chieu_tuong(self) -> None:
        # 1.e4 e5 2.Nf3 d6 3.Bc4 Bg4 4.Nc3 Nc6 5.Nxe5! Nxe5? 6.Qxg4 -> không
        # đơn giản; dùng thế: trắng có Bxf7+ kết hợp, AI phải chặn chiếu tướng.
        board = self._an("e4 e5 Nf3 Nc6 Bc4 Nd7 O-O Nf6 Re1 Nxe4")
        nuoc = engine.think(board, 2400, 0.0)
        self.assertIsNotNone(nuoc)

    def test_moi_dong_ca_quan_hon_deu_tra_nuoc_hop_le(self) -> None:
        dong = [
            chess.STARTING_FEN,
            "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
            "r1bq1rk1/pp2ppbp/2np1np1/8/3NP3/2N1BP2/PPPQ2PP/2KR1B1R w - - 0 9",
            "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1",
            "8/2P5/8/8/8/8/6k1/4K3 w - - 0 1",
        ]
        for fen in dong:
            with self.subTest(fen=fen):
                board = chess.Board(fen)
                nuoc = engine.think(board, 1500, 0.0)
                self.assertIn(nuoc, list(board.legal_moves))

    def test_elo_thap_van_luon_hop_le(self) -> None:
        """Review Focus 4: chơi yếu được, chơi bất hợp phệ thì mất cả ván."""
        board = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
        for _ in range(12):
            nuoc = engine.think(board, 600, 0.0)
            self.assertIn(nuoc, list(board.legal_moves))
            if nuoc is None:
                break
            board.push(nuoc)
            tra_lai = engine.think(board, 600, 0.0)
            if tra_lai is None:
                break
            board.push(tra_lai)

    def test_khong_vuot_qua_thoi_gian_cho_phep(self) -> None:
        import time as _time
        board = chess.Board("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
        bat_dau = _time.monotonic()
        engine.think(board, 2400, 0.0)
        self.assertLess(_time.monotonic() - bat_dau, 9.0 * 2)

    def test_thoi_gian_toi_thieu_duoc_chan(self) -> None:
        import time as _time
        board = chess.Board()
        bat_dau = _time.monotonic()
        engine.think(board, 600, 0.6)
        self.assertGreaterEqual(_time.monotonic() - bat_dau, 0.55)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `python -m unittest tests.test_engine`
Expected: `AttributeError: module 'chessai.engine' has no attribute 'profile_for'`

- [ ] **Step 3: Viết phần tìm nước, thêm vào cuối `chessai/engine.py`**

```python
import random
import time

# (max_depth, blunder_rate, slack_cp, max_seconds)
ELO_TABLE: list[tuple[int, int, float, int, float]] = [
    (600, 1, 0.45, 220, 0.4),
    (900, 2, 0.30, 150, 0.8),
    (1200, 3, 0.18, 95, 1.5),
    (1500, 4, 0.10, 60, 2.5),
    (1800, 5, 0.05, 35, 4.0),
    (2100, 6, 0.02, 20, 6.0),
    (2400, 7, 0.00, 0, 9.0),
]

# Xem điểm trên bảng chia cho 100, rồi trừ 2 lần số quân còn lại: mỗi quân
# "làm loạn" thế cờ thêm một chút cho mọi đường đi. Số này dùng để quyết định
# mức chiết khấu mà máy được sai.
_MATE = 10_000
_INF = 1_000_000


def profile_for(elo: int) -> tuple[int, float, int, float]:
    """(max_depth, blunder_rate, slack_cp, max_seconds) cho một Elo."""
    bang = ELO_TABLE
    if elo <= bang[0][0]:
        row = bang[0]
        return row[1], row[2], row[3], row[4]
    if elo >= bang[-1][0]:
        row = bang[-1]
        return row[1], row[2], row[3], row[4]
    for thap, cao in zip(bang, bang[1:]):
        if thap[0] <= elo <= cao[0]:
            ty_le = (elo - thap[0]) / (cao[0] - thap[0])
            return (
                int(round(thap[1] + ty_le * (cao[1] - thap[1]))),
                round(thap[2] + ty_le * (cao[2] - thap[2]), 4),
                int(round(thap[3] + ty_le * (cao[3] - thap[3]))),
                round(thap[4] + ty_le * (cao[4] - thap[4]), 2),
            )
    row = bang[-1]
    return row[1], row[2], row[3], row[4]


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
    if deadline - time.monotonic() <= 0.0:
        return evaluate(board)

    if depth <= 0:
        return quiesce(board, alpha, beta, deadline)

    if board.is_checkmate():
        return -_MATE
    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    # Nhật ký hoàn tất: lặp lại thế đã gặp thì coi như hòa để tránh lặp vô hạn.
    key = (board.fen(), board.is_repetition(2))
    if key[1]:
        return 0

    diem_so = -_INF
    for move in board.legal_moves:
        board.push(move)
        diem_so = max(diem_so, -negamax(board, depth - 1, -beta, -alpha, deadline))
        board.pop()
        if diem_so > alpha:
            alpha = diem_so
        if alpha >= beta:
            break
    return diem_so


def _xep_hang(
    board: chess.Board, deadline: float
) -> list[tuple[int, chess.Move]]:
    """Xếp MỌI nước hợp lệ theo điểm, tốt nhất trước."""
    ket_qua: list[tuple[int, chess.Move]] = []
    for move in board.legal_moves:
        board.push(move)
        if board.is_checkmate():
            diem = _MATE
        else:
            diem = -negamax(board, 1, -_INF, _INF, deadline)
        board.pop()
        ket_qua.append((diem, move))
    ket_qua.sort(key=lambda cap: -cap[0])
    return ket_qua


def search(
    board: chess.Board, max_depth: int, deadline: float, max_seconds: float
) -> tuple[chess.Move | None, list[chess.Move]]:
    """Lặp tăng dần độ sâu. Trả (nước tốt nhất, mọi nước xếp theo điểm)."""
    bat_dau = time.monotonic()
    deadline = bat_dau + max_seconds
    tot: list[tuple[int, chess.Move]] = []
    tot_di_chua = time.monotonic() + max_seconds / 2.0
    nuoc = None
    for depth in range(1, max_depth + 1):
        moi: list[tuple[int, chess.Move]] = []
        # Nước tốt nhất vòng trước thử trước: thường cắt được hàng loạt nhánh.
        if nuoc is not None and nuoc in board.legal_moves:
            board.push(nuoc)
            diem = -negamax(board, depth - 1, -_INF, _INF, deadline)
            board.pop()
            moi.append((diem, nuoc))
        for move in board.legal_moves:
            if nuoc is not None and move == nuoc:
                continue
            board.push(move)
            diem = -negamax(board, depth - 1, -_INF, _INF, deadline)
            board.pop()
            moi.append((diem, move))
            if time.monotonic() > tot_di_chua and depth > 1:
                break          # giữ chỗ cho vòng sâu hơn thay vì kết thúc
        if not moi:
            break
        moi.sort(key=lambda cap: -cap[0])
        tot, nuoc = moi, moi[0][1]
        if tot_di_chua < deadline or depth >= max_depth:
            break
    if not tot:
        tot = _xep_hang(board, deadline)
        return (tot[0][1] if tot else None), [m for _, m in tot]
    return nuoc, [m for _, m in tot]


def clamp_time(board: chess.Board, max_seconds: float, min_seconds: float) -> float:
    """Thời gian tìm, co theo số quân còn trên bàn.

    Thế cờ trống dần thì mỗi nước phải cân nhắc nhiều hơn, nên cho nhiều thời
    gian hơn — nhưng vẫn không vượt trần của Elo.
    """
    con_lai = sum(1 for p in board.piece_map.values() if p.piece_type != chess.KING)
    ty_le = max(0.25, min(1.0, con_lai / 32.0))
    return max(min_seconds, min(max_seconds, max_seconds * ty_le))


def think(
    board: chess.Board, elo: int = 1500, min_seconds: float = 0.6
) -> chess.Move | None:
    """Nước đi của máy. `None` nghĩa là hết nước."""
    if board.is_game_over():
        return None
    max_depth, blunder_rate, slack_cp, max_seconds = profile_for(elo)
    ngan = clamp_time(board, max_seconds, min_seconds)
    nuoc, bang_xep = search(board, max_depth, ngan, ngan)
    if nuoc is None:
        return None

    # Đặc tả §3.4: máy chơi yếu bằng cách chọn nước kém hơn nước tốt nhất trong
    # biên độ slack_cp — KHÔNG phải bằng cách chọn nước bất hợp phệ. Nhóm
    # ứng viên lấy sẵn từ lần xếp hạng cuối, không tìm lại.
    if blunder_rate > 0.0 and slack_cp > 0 and len(bang_xep) > 1:
        diem_tot_nhat = _diem_cua(bang_xep[0], board, ngan)
        nhom = [
            move
            for move in bang_xep
            if _diem_cua(move, board, ngan) >= diem_tot_nhat - slack_cp
        ]
        if len(nhom) > 1 and random.random() < blunder_rate:
            bo_qua = max(1, len(nhom) // 3)   # không đánh rơi cả nước đúng nhất
            nuoc = random.choice(nhom[bo_qua:])
    return nuoc


def _diem_cua(move: chess.Move, board: chess.Board, deadline: float) -> int:
    """Điểm của một nước cụ thể, quy chiều về phe đang đi."""
    board.push(move)
    diem = -negamax(board, 1, -_INF, _INF, deadline)
    board.pop()
    return diem
```

**Hai cái bẫy đã vấp, đừng vấp lại:**

- `_xep_hang` gọi `negamax` cho **mọi** nước hợp lệ — ở độ sâu 7 mỗi nước tốn
  một vòng tìm. Chỉ dùng nó khi `search` không tìm được nước nào; nếu không thì
  mỗi nước AI sẽ chậm gấp đôi.
- `commit_ai_move` (Task 3) phải là **một** lần giữ khoá duy nhất: so FEN rồi
  áp nước, không tách thành hai lần — tách ra thì người chơi có thể chen vào
  giữa và máy sẽ áp nước lên thế cờ khác.

- [ ] **Step 4: Chạy, kỳ vọng PASS**

Run: `python -m unittest tests.test_engine`
Expected: `Ran 24 tests ... OK`

- [ ] **Step 5: Đo thời gian thật và chỉnh bảng Elo nếu cần**

Chạy đo cho từng mốc Elo, ghi kết quả vào ledger:

```bash
python -c "
import chess, time
from chessai import engine
b = chess.Board('r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1')
for elo in (600, 1200, 1800, 2400):
    t = time.monotonic(); engine.think(b, elo, 0.0); d = time.monotonic() - t
    print(f'elo {elo:4d}  depth={engine.profile_for(elo)[0]}  {d:5.2f}s')
"
```

Nếu mốc nào vượt `max_seconds` quá 1.5× thì **giảm `max_depth`** của mốc đó vào
bảng `ELO_TABLE` cho tới khi vừa. Ghi lại số đã đo vào ledger — bảng này phải
dựa trên đo thật, không đoán.

- [ ] **Step 6: Chạy cả bộ, kỳ vọng PASS**

Run: `python -m unittest`
Expected: `Ran 260 tests ... OK` (236 cũ + 24 engine)

- [ ] **Step 7: Commit**

```bash
git add chessai/engine.py tests/test_engine.py
git commit -m "feat(engine): add quiescence, negamax, iterative deepening and elo profile"
```

---

### Task 3: `AIController` — luồng suy nghĩ nền

**Files:**
- Create: `chessai/web/ai.py`
- Modify: `chessai/web/schema.py`
- Modify: `chessai/web/games.py`
- Test: `tests/test_web_ai.py`

**Interfaces:**
- Consumes: `GameStore` (Task #3A), `Session.on_move` (#1), `engine.think`
- Produces:
  - `class AIController` — `__init__(store: GameStore, executor: Executor | None = None)`,
    `.thinking(game_id) -> bool`, `.cancel(game_id) -> None`,
    `.shutdown() -> None`, `.attach(session) -> None`
  - `GameState.thinking: bool`

- [ ] **Step 1: Viết test đỏ — `tests/test_web_ai.py`**

```python
"""Luồng AI: sau nước của người thì AI nghĩ ở thread nền rồi tự đáp."""

import threading
import unittest

import chess

from chessai.web.ai import AIController
from chessai.web.games import GameNotFound, GameStore


class FakeEngine:
    """Engine giả: luôn trả nước đầu tiên, và chặn lại để test kiểm soát."""

    def __init__(self, move: str | None = None, block: threading.Event | None = None):
        self.move = move
        self.block = block
        self.calls = 0
        self.fens: list[str] = []

    def think(self, board, elo=1500, min_seconds=0.0):
        self.calls += 1
        self.fens.append(board.fen())
        if self.block is not None:
            self.block.wait(timeout=5.0)
        if self.move is not None:
            found = board.parse_san(self.move)
            if found is not None and found in board.legal_moves:
                return found
        return next(iter(board.legal_moves), None)


class TestHook(unittest.TestCase):
    def _bo(self, engine, human=chess.WHITE, elo=1500):
        store = GameStore()
        ai = AIController(store, engine=engine)
        game_id = store.create(human, elo=elo)
        ai.attach(game_id)
        return store, ai, game_id

    def test_hai_ben_thi_khong_bao_ngh(self) -> None:
        store, ai, game_id = self._bo(FakeEngine(), human=None)
        store.submit(game_id, "e4")
        ai.wait_idle(game_id)
        self.assertFalse(store.snapshot(game_id).thinking)
        self.assertEqual(ai.engine.calls, 0)

    def test_nguoi_di_thi_ai_ngh(self) -> None:
        store, ai, game_id = self._bo(FakeEngine(move="e5"))
        store.submit(game_id, "e4")
        ai.wait_idle(game_id)
        self.assertEqual(store.snapshot(game_id).moves, ["e4", "e5"])

    def test_nguoi_di_nham_phe_thi_bi_tu_trai(self) -> None:
        """Sau 1.e4, lượt là của đen — trắng bấm tiếp phải bị chặn."""
        store, ai, game_id = self._bo(FakeEngine(move="e5"))
        store.submit(game_id, "e4")
        ai.wait_idle(game_id)
        with self.assertRaises(Exception):
            store.submit(game_id, "e4")

    def test_thinking_bat_dung_roi_tat(self) -> None:
        chan = threading.Event()
        store, ai, game_id = self._bo(FakeEngine(move="e5", block=chan))
        store.submit(game_id, "e4")
        self.assertTrue(store.snapshot(game_id).thinking)
        chan.set()
        ai.wait_idle(game_id)
        self.assertFalse(store.snapshot(game_id).thinking)

    def test_nguoi_chon_phe_den_thi_ai_ngh_ngay(self) -> None:
        """Review Focus 1: trắng đi trước, nên AI phải đi ngay khi ván tạo."""
        store, ai, game_id = self._bo(FakeEngine(move="e4"), human=chess.BLACK)
        ai.wait_idle(game_id)
        self.assertEqual(store.snapshot(game_id).moves, ["e4"])
        self.assertFalse(store.snapshot(game_id).thinking)

    def test_van_moi_giữ_cau_hinh(self) -> None:
        store, ai, game_id = self._bo(FakeEngine(move="e5"), human=chess.WHITE, elo=1900)
        store.submit(game_id, "e4")
        ai.wait_idle(game_id)
        state = store.new_game(game_id)
        self.assertEqual(state.elo, 1900)
        self.assertIsNotNone(store.session(game_id).on_move)

    def test_luu_cha_gi_nuoc_dang_cho(self) -> None:
        """Review Focus 2: bấm Lùi khi AI đang nghĩ thì nước AI phải bị bỏ."""
        chan = threading.Event()
        store, ai, game_id = self._bo(FakeEngine(move="e5", block=chan))
        store.submit(game_id, "e4")
        store.new_game(game_id)            # hủy, chưa cho thread trả kết quả
        chan.set()
        ai.wait_idle(game_id)
        self.assertEqual(store.snapshot(game_id).moves, [])

    def test_them_nguon_dung_de_khong_tre(self) -> None:
        """Review Focus 3: GET phải trả lời được khi AI đang tìm."""
        chan = threading.Event()
        store, ai, game_id = self._bo(FakeEngine(move="e5", block=chan))
        store.submit(game_id, "e4")
        xong = threading.Event()

        def hoi():
            store.snapshot(game_id)
            xong.set()

        t = threading.Thread(target=hoi)
        t.start()
        self.assertTrue(xong.wait(timeout=1.0), "snapshot bị khoá quá lâu")
        chan.set()
        ai.wait_idle(game_id)


class TestRealEngine(unittest.TestCase):
    def test_engine_that_chay_roi_van_dung(self) -> None:
        from chessai import engine
        store = GameStore()
        ai = AIController(store, engine=engine)
        game_id = store.create(chess.WHITE, elo=600)
        ai.attach(game_id)
        store.submit(game_id, "e4")
        ai.wait_idle(game_id, timeout=20.0)
        self.assertEqual(store.snapshot(game_id).moves, ["e4", "e5"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `python -m unittest tests.test_web_ai`
Expected: `ModuleNotFoundError: No module named 'chessai.web.ai'`

- [ ] **Step 3: `chessai/web/schema.py` — thêm `thinking`**

Thêm vào `GameState`, ngay sau `over`:

```python
    # true khi AI đang tìm nước — trình duyệt hỏi lại tới khi hết.
    thinking: bool
```

- [ ] **Step 4: `chessai/web/games.py` — `create` nhận cấu hình, `snapshot` trả `thinking`**

Đổi chữ ký và thân `create`:

```python
    def create(
        self,
        human_color: chess.Color | None,
        elo: int = 1500,
        mode: str = "play",
    ) -> str:
        game_id = secrets.token_urlsafe(16)[:_ID_LENGTH]
        with self._guard:
            self._games[game_id] = Session(
                human_color=human_color, elo=elo, mode=mode
            )
            self._locks[game_id] = threading.Lock()
            self._order.append(game_id)
            while len(self._order) > self.capacity:
                self._drop(self._order[0])
        return game_id

    def set_thinking(self, game_id: str, value: bool) -> None:
        """Cờ 'AI đang nghĩ'. Không lấy khoá: đây là cờ hiển thị, không phải
        trạng thái luật — lấy khoá sẽ khiến GET phải chờ hết lúc tìm nước."""
        session = self._require(game_id)
        session.thinking = value
```

Trong `_snapshot`, thêm hai tham số đọc từ session:

```python
            thinking=bool(getattr(session, "thinking", False)),
            elo=session.elo,
            human_color=(
                None if session.human_color is None
                else ("white" if session.human_color else "black")
            ),
```

Và thêm vào `GameState` hai trường:

```python
    elo: int
    human_color: str | None
```

**Quan trọng:** `Session.restart()` (Task #3A) chưa xoá `thinking` — thêm vào
`Session.__init__` một thuộc tính `self.thinking = False` và vào `restart()` một
dòng `self.thinking = False`.

- [ ] **Step 5: Viết `chessai/web/ai.py`**

```python
"""Cho máy đi nước ở thread nền.

Một `Session.on_move` chạy **bên trong** khoá ván (`GameStore.submit` giữ khoá
rồi gọi `apply_san`). Nên `on_move` chỉ được làm một việc rẻ: đặt cờ và đẩy
việc tìm nước ra thread. Tìm nước tuyệt đối không được chạm vào khoá.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor

import chess

from .. import engine
from .games import GameStore

# Engine mặc định: module `chessai.engine`, dùng đúng chữ ký `think`.
# Test truyền engine giả vào để chạy nhanh và xác định.
_MODULE_ENGINE = engine


class AIController:
    def __init__(
        self,
        store: GameStore,
        executor: ThreadPoolExecutor | None = None,
        engine=None,
    ) -> None:
        self.store = store
        self.engine = engine if engine is not None else _MODULE_ENGINE
        self._pool = executor or ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="ai"
        )
        self._owns_pool = executor is None
        self._flags: dict[str, bool] = {}
        self._tasks: dict[str, Future] = {}
        self._guard = threading.Lock()

    # ---- vòng đời ---------------------------------------------------

    def attach(self, game_id: str) -> None:
        """Gắn `on_move` cho một ván, và bật AI nếu đã tới lượt máy.

        `partial` vì `on_move` chỉ nhận (san, phe) — không biết ván nào, nên
        phải buộc `game_id` vào trước.
        """
        session = self.store.session(game_id)
        session.on_move = partial(self._on_move, game_id)
        if self._machine_to_move(game_id):
            self._start(game_id)

    def _on_move(self, game_id: str, san: str, color: chess.Color) -> None:
        if self._machine_to_move(game_id):
            self._start(game_id)

    def shutdown(self) -> None:
        if self._owns_pool:
            self._pool.shutdown(wait=False, cancel_futures=True)

    # ---- cờ huỷ ---------------------------------------------------

    def cancel(self, game_id: str) -> None:
        with self._guard:
            self._flags[game_id] = True
        self.store.set_thinking(game_id, False)

    def thinking(self, game_id: str) -> bool:
        return bool(self.store.snapshot(game_id).thinking)

    def wait_idle(self, game_id: str, timeout: float = 10.0) -> None:
        """Chờ thread của một ván xong. Chỉ dùng trong test."""
        with self._guard:
            task = self._tasks.get(game_id)
        if task is not None:
            task.result(timeout=timeout)

    # ---- phần cốt lõi -----------------------------------------------

    def _machine_to_move(self, game_id: str) -> bool:
        session = self.store.session(game_id)
        return (
            session.human_color is not None
            and not session.is_game_over()
            and session.position.side_to_move != session.human_color
        )

    def _start(self, game_id: str) -> None:
        with self._guard:
            if self._flags.get(game_id):
                return
            self._flags[game_id] = False
        self.store.set_thinking(game_id, True)
        task = self._pool.submit(self._run, game_id)
        with self._guard:
            self._tasks[game_id] = task

    def _run(self, game_id: str) -> None:
        with self._guard:
            if self._flags.get(game_id):
                return
        try:
            self._move(game_id)
        finally:
            self.store.set_thinking(game_id, False)

    def _move(self, game_id: str) -> None:
        session = self.store.session(game_id)
        fen = self.store.fen_of(game_id)
        elo = session.elo

        board = chess.Board(fen)
        move = self.engine.think(board, elo=elo, min_seconds=0.6)
        if move is None:
            return

        with self._guard:
            if self._flags.get(game_id):
                return

        # Giữ khoá đúng một lần: so FEN rồi áp, không thể chen vào giữa.
        self.store.commit_ai_move(game_id, fen, move)
```

- [ ] **Step 6: Thêm hai hỗ trợ vào `GameStore` (`chessai/web/games.py`)**

```python
    def fen_of(self, game_id: str) -> str:
        """FEN hiện tại, lấy khoá."""
        with self._lock(game_id):
            return self._require(game_id).position.board.fen()

    def commit_ai_move(
        self, game_id: str, expected_fen: str, move: chess.Move
    ) -> bool:
        """Áp nước AI **chỉ khi** bàn cờ vẫn đúng như lúc bắt đầu tìm.

        Trả False nếu ván đã đổi — người chơi bấm "Ván mới" / "Lùi" trong
        lúc AI đang nghĩ. So FEN và áp nước nằm chung MỘT lần giữ khoá, nên
        không thể có khe hở chen vào giữa.
        """
        with self._lock(game_id):
            session = self._require(game_id)
            board = session.position.board
            if board.fen() != expected_fen:
                return False
            if session.is_game_over():
                return False
            session.position.apply_san(board.san(move))
            return True
```

Cột mốc: `AIController` **không** gọi `Session.apply_san` (hàm đó kiểm
`is_human_turn()` và sẽ từ chối nước của máy, đồng thời lại bắn `on_move` một
lần nữa). Gọi thẳng `session.position.apply_san` là đúng: máy cứng không phải
"người", và không cần bắn hook lần hai.

- [ ] **Step 7: Nối `AIController` vào `app.py`**

Trong `create_app`, sau khi có `games`:

```python
    ai = AIController(games)
```

Đổi route tạo ván:

```python
class NewGameRequest(BaseModel):
    human_color: Literal["white", "black", None] = None
    elo: int = 1500


    @app.post("/api/game")
    def create_game(payload: NewGameRequest = NewGameRequest()) -> JSONResponse:
        color = (
            None if payload.human_color is None
            else (payload.human_color == "white")
        )
        game_id = games.create(color, elo=max(600, min(2400, payload.elo)))
        ai.attach(game_id)
        return _guard(games.snapshot, game_id)
```

Thêm import: `from typing import Literal` và `from .ai import AIController`.

Nối `undo` và `new` với `ai.cancel`:

```python
    @app.post("/api/game/{game_id}/undo")
    def undo(game_id: str) -> JSONResponse:
        ai.cancel(game_id)
        return _guard(games.undo, game_id)

    @app.post("/api/game/{game_id}/new")
    def new_game(game_id: str) -> JSONResponse:
        ai.cancel(game_id)
        return _guard(games.new_game, game_id)
```

- [ ] **Step 8: Chạy, kỳ vọng PASS**

Run: `python -m unittest tests.test_web_ai`
Expected: `Ran 9 tests ... OK`

- [ ] **Step 9: Chạy cả bộ**

Run: `python -m unittest`
Expected: `Ran 269 tests ... OK`

- [ ] **Step 10: Commit**

```bash
git add chessai/web/ai.py chessai/web/games.py chessai/web/schema.py chessai/web/app.py chessai/session.py tests/test_web_ai.py
git commit -m "feat(web): reply with the engine from a background thread"
```

---

### Task 4: Giao diện đấu máy

**Files:**
- Modify: `chessai/web/static/index.html`
- Modify: `chessai/web/static/style.css`
- Modify: `chessai/web/static/app.js`
- Test: `tests/test_web_api.py` (bổ sung kiểm hợp đồng)

**Interfaces:**
- Consumes: `GameState.thinking`, `GameState.elo`, `GameState.human_color`,
  `POST /api/game` với body `{human_color, elo}`
- Produces: không có API mới

- [ ] **Step 1: Viết test đỏ — thêm vào `TestOpenApiContract`**

```python
    def test_game_state_carries_the_ai_fields(self) -> None:
        for name in ("thinking", "elo", "human_color"):
            with self.subTest(field=name):
                self.assertIn(name, GameState.model_fields)

    def test_new_game_request_defaults(self) -> None:
        request = NewGameRequest.model_validate({})
        self.assertIsNone(request.human_color)
        self.assertEqual(request.elo, 1500)
```

Thêm import `NewGameRequest` từ `chessai.web.app`.

- [ ] **Step 2: Chạy, kỳ vọng FAIL**

Run: `python -m unittest tests.test_web_api`
Expected: `ImportError` / `FAIL` vì `NewGameRequest` chưa có hoặc field chưa có.

- [ ] **Step 3: `index.html` — thêm bảng chọn ván mới và trạng thái AI**

Ngay trên `<div class="actions">`, thêm:

```html
    <div class="setup" id="setup" hidden>
      <div class="setup-row">
        <span class="setup-label">Bạn đánh</span>
        <div class="seg" id="pick-color">
          <button data-color="white" class="on">Trắng</button>
          <button data-color="black">Đen</button>
          <button data-color="both">Hai bên</button>
        </div>
      </div>
      <div class="setup-row">
        <span class="setup-label">Elo máy <b id="elo-value">1200</b></span>
        <input type="range" id="elo" min="600" max="2400" step="100" value="1200">
      </div>
      <button id="start" class="primary">Bắt đầu</button>
    </div>
```

Trong `.player` của phe máy, thêm `<small id="engine-sub"></small>` — nhưng
`.player` đã có `small`; dùng id phân biệt: đổi `top-sub`/`bottom-sub` thành
`player-top`/`player-bottom` với hai dòng `small`:

```html
    <div class="player" id="player-top">
      <span class="dot black"></span>
      <div><strong>Đen</strong><small id="top-sub">—</small><small id="top-elo"></small></div>
      <span class="captured" id="top-captured"></span>
    </div>
```

Và tương tự cho `player-bottom` với `bottom-elo`.

- [ ] **Step 4: `style.css` — thêm kiểu**

```css
.setup { margin-top: 10px; padding: 10px; border: 1px solid var(--border); border-radius: 6px; display: grid; gap: 8px; }
.setup[hidden] { display: none; }
.setup-row { display: grid; gap: 4px; }
.setup-label { font-size: 12px; color: var(--muted); }
.setup-label b { color: var(--fg); }
.seg { display: flex; gap: 4px; }
.seg button { flex: 1; padding: 5px; font-size: 12px; background: var(--btn); color: var(--btn-fg); border: 1px solid var(--btn-border); border-radius: 4px; cursor: pointer; }
.seg button.on { background: #4a7dd6; border-color: #4a7dd6; color: #fff; }
#elo { width: 100%; accent-color: #4a7dd6; }
.player small + small { color: var(--muted); opacity: .8; }
.thinking::after { content: ""; animation: nhapnhay 1s steps(3) infinite; }
@keyframes nhapnhay { 0% { opacity: .25; } 50% { opacity: 1; } 100% { opacity: .25; } }
```

- [ ] **Step 5: `app.js` — trạng thái, hộp thoại, hỏi lại**

Thêm vào phần khai báo:

```javascript
let aiThinking = false;
let picking = { color: "white", elo: 1200 };
let pollTimer = null;
```

Trong `paintPanel`, thêm vào cuối (trước dấu `}` của hàm):

```javascript
  const elo = state.elo;
  const banMay = state.human_color !== null;
  el.topElo.textContent = banMay ? (state.turn === "black" ? "AI đang nghĩ…" : "Elo " + elo) : "";
  el.bottomElo.textContent = banMay ? (state.turn === "white" ? "AI đang nghĩ…" : "Elo " + elo) : "";
  el.top.classList.toggle("thinking", aiThinking && state.turn === "black");
  el.bottom.classList.toggle("thinking", aiThinking && state.turn === "white");
  // Khoá bàn khi tới lượt máy: không bấm được, và nhìn ra cũng biết.
  el.squares.classList.toggle(
    "locked", banMay && (state.over || state.turn !== state.human_color),
  );
```

Thêm vào `el`:

```javascript
  topElo: document.getElementById("top-elo"),
  bottomElo: document.getElementById("bottom-elo"),
  setup: document.getElementById("setup"),
  elo: document.getElementById("elo"),
  eloValue: document.getElementById("elo-value"),
```

Hàm hỏi lại:

```javascript
function stopPolling() {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
}

async function pollAi() {
  stopPolling();
  pollTimer = setTimeout(async () => {
    pollTimer = null;
    try {
      const next = await api(`/api/game/${state.game_id}`, "GET");
      apply(next);
      if (next.thinking) pollAi();
    } catch (error) {
      say(error.message, true);
    }
  }, 300);
}
```

Trong `apply`, đặt `aiThinking = next.thinking` và gọi `stopPolling()` khi không
còn nghĩ:

```javascript
function apply(next) {
  state = next;
  aiThinking = next.thinking;
  selected = null;
  hidePicker();
  // Bàn xoay theo phe người chơi, nhưng chỉ dựng lại 64 ô khi hướng THẬT SỰ
  // đổi — dựng lại ở mỗi nước đi thì vô nghĩa và làm mất dấu hiệu đang bấm.
  const wanted = next.human_color === "black" ? "b"
    : next.human_color === "white" ? "w"
    : orientation;                       // chơi hai bên: giữ hướng đang chọn
  if (wanted !== orientation) {
    orientation = wanted;
    buildSquares();
  }
  const cells = boardFromFen(state.fen);
  paintPieces(cells);
  paintBoard(cells);
  paintPanel();
  if (aiThinking) pollAi(); else stopPolling();
  showInUrl(state.game_id);
}
```

Bỏ `showInUrl(created.game_id)` trong `loadOrCreateGame` (giờ `apply` lo).

Hộp chọn ván:

```javascript
function openSetup() { el.setup.hidden = false; }
function closeSetup() { el.setup.hidden = true; }

el.undo.addEventListener("click", () => withState(
  (s) => api(`/api/game/${s.game_id}/undo`, "POST"),
));

document.getElementById("flip").addEventListener("click", () => {
  if (!state) return;
  orientation = orientation === "w" ? "b" : "w";
  buildSquares();
  apply(state);
});

document.getElementById("new").addEventListener("click", () => {
  // Mở hộp chọn thay vì xoá thẳng: cần biết đánh phe nào và Elo bao nhiêu.
  if (state && state.human_color !== null) {
    // Đang đấu máy: giữ nguyên cấu hình, chỉ bắt đầu ván mới.
    withState((s) => api(`/api/game/${s.game_id}/new`, "POST"));
    return;
  }
  openSetup();
});

document.getElementById("start").addEventListener("click", async () => {
  lockUi(true);
  try {
    const human = picking.color === "both" ? null : picking.color;
    const next = await api("/api/game", "POST", { human_color: human, elo: picking.elo });
    closeSetup();
    say("");
    apply(next);
  } catch (error) {
    say(error.message, true);
  } finally {
    lockUi(false);
  }
});

document.getElementById("pick-color").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-color]");
  if (!button) return;
  document.querySelectorAll("#pick-color button").forEach((b) => b.classList.toggle("on", b === button));
  picking.color = button.dataset.color;
});

el.elo.addEventListener("input", () => {
  picking.elo = Number(el.elo.value);
  el.eloValue.textContent = String(picking.elo);
});
```

Bàn cờ xoay theo phe người chơi, trong `apply`:

```javascript
  if (next.human_color === "black") orientation = "b";
  else if (next.human_color === "white") orientation = "w";
  buildSquares();
```

(Cất `buildSquares()` vào đầu `apply`, trước `paintPieces`.)

Chặn bấm quân máy — sửa đầu handler:

```javascript
el.squares.addEventListener("click", (event) => {
  const sq = event.target.closest(".sq");
  if (!sq || !state || state.over || busy) return;
  if (state.human_color !== null && state.turn !== state.human_color) {
    say("Đến lượt máy.");
    return;
  }
```

- [ ] **Step 6: Chạy test, kỳ vọng PASS**

Run: `python -m unittest tests.test_web_api`
Expected: PASS

- [ ] **Step 7: Kiểm bằng trình duyệt**

```bash
python -m chessai.web
```

Mở `http://127.0.0.1:8000`, bấm **Ván mới** → hộp chọn hiện ra. Chọn **Đen**,
Elo 600, bấm **Bắt đầu**. Xác minh:

- Bàn cờ xoay (quân Đen ở trên)
- Thấy "AI đang nghĩ…" rồi `1. e4` do máy đi (máy là phe Trắng)
- Bấm vào quân khi tới lượt máy → hiện "Đến lượt máy.", bàn không đổi
- Bấm một nước hợp lệ → quân bạn di chuyển ngay, không chờ
- Console: **0 lỗi**
- Bấm **Ván mới** giữa lúc AI đang nghĩ → bàn phải sạch, không có nước AI lạ
- Đổi sang **Hai bên** → không hiện "AI đang nghĩ…", chơi tự do

- [ ] **Step 8: Chạy cả bộ**

Run: `python -m unittest`
Expected: `Ran 271 tests ... OK`

- [ ] **Step 9: Commit**

```bash
git add chessai/web/static tests/test_web_api.py
git commit -m "feat(web): add colour and elo picker, thinking indicator, ai polling"
```

---

## Kiểm lại toàn nhánh

Sau khi cả 4 task xong, chạy một vòng review bằng ngữ cảnh tươi trên toàn
bộ nhánh, rồi ghi kết quả vào
`.superpowers/sdd/2026-09-29-chess-ai-implementation/progress.md`.
