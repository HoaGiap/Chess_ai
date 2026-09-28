# Spec: Chess Core — Luật FIDE + Render + CLI (Sub-project #1)

- **Ngày:** 2026-09-28
- **Dự án:** `Chess_ai` (dự án cá nhân, repo trống tại thời điểm thiết kế)
- **Phạm vi:** sub-project #1 trong chuỗi 3 (#1 luật+render → #2 search+eval → #3 LLM coaching)

---

## 1. Bối cảnh

Đặc tả gốc mô tả hệ thống "GM-CHESS-AI" với 4 chế độ (`Match`/`Coach`/`Puzzle`/`Review`), mô phỏng ELO 600–2800, phân tích chiến thuật bằng ngôn ngữ tự nhiên. Toàn bộ đặc tả **không thể cài đặt trực tiếp thành code** vì ba lý do đã thống nhất:

1. Coaching bằng văn bản tự nhiên không thể do search engine sinh ra → cần LLM API (đẩy sang #3).
2. ELO không thể mô phỏng trung thực chỉ bằng độ sâu search → phải giới hạn theo tham số và **ghi rõ giới hạn**, không được tự dán nhãn ELO như thông số đo lường.
3. Puzzle mode cần nguồn câu đố → chưa quyết, để #2.

Đã chốt hướng **B**: dùng `python-chess` cho luật FIDE, tự viết search/eval/coaching. Repo được tách thành 3 sub-project, mỗi cái một vòng spec → plan → code riêng. **Tài liệu này chỉ phủ #1.**

## 2. Các quyết định đã chốt

| Quyết định | Lý do |
|---|---|
| Python 3.13 | `openai` 3.7.0 đã cài sẵn → #3 không cần dependency mới. |
| `python-chess` cho luật FIDE | Luật FIDE là phần ít thú vị nhất để tự viết nhưng tốn nhiều công sức nhất; thư viện đã được kiểm thử rộng rãi hơn bất kỳ code tự viết nào. |
| `unittest` stdlib cho test | `pytest` không cài. Ưu tiên stdlib trước khi cài dependency mới. |
| Tên gói `chessai`, **không** phải `chess` | Tên `chess` sẽ che mất package `python-chess` khi import — lỗi thật, không phải loại hình thức. |
| Không interface / base class / abstract layer | Không tạo abstraction cho code chỉ dùng một lần. |
| `git init` tại repo gốc | Repo chưa phải git repo khi bắt đầu. |

## 3. Kiến trúc

```
Chess_ai/
├── OPENCODE.md
├── docs/superpowers/specs/2026-09-28-chess-core-rules-design.md
├── chessai/
│   ├── __init__.py
│   ├── position.py   # Trạng thái thế cờ + luật FIDE
│   ├── render.py     # Vẽ bàn cờ Unicode (hàm thuần)
│   ├── session.py    # Ván đấu: lịch sử, PGN, undo, phát hiện kết thúc
│   └── cli.py        # Vòng lặp REPL + phân tích lệnh
└── tests/
    ├── test_position.py
    ├── test_render.py
    ├── test_session.py
    └── test_perft.py
```

Bốn module, mỗi cái một trách nhiệm duy nhất. Ranh giới quan trọng nhất: **`render.py` là hàm thuần** — nhận `(board, perspective)`, trả về `str`, không đọc biến toàn cục, không giữ trạng thái. Nhờ vậy kiểm thử bằng so khớp chuỗi, không cần dựng ván đấu.

### 3.1 `position.py` — tầng luật

Sở hữu một `chess.Board`. Tồn tại để làm hai việc `python-chess` không làm sẵn: **dịch lỗi sang tiếng Việt** và **trả về lý do kết thúc ván dạng đọc được**.

```python
Color = chess.Color  # chess.WHITE | chess.BLACK

class MoveError(Exception):
    """Nước người dùng nhập không hợp lệ. Thông điệp đã bằng tiếng Việt, sẵn sàng in ra."""

class Position:
    def __init__(self, fen: str = chess.STARTING_FEN) -> None: ...
    @property
    def side_to_move(self) -> Color: ...
    def legal_sans(self) -> list[str]: ...          # SAN hợp lệ, đã sắp xếp
    def apply_san(self, san: str) -> None: ...     # ném MoveError nếu sai
    def undo(self) -> None: ...                    # ném MoveError nếu không có nước để lùi
    def fen(self) -> str: ...
    def is_game_over(self) -> bool: ...
    def outcome(self) -> chess.Outcome | None: ... # None nếu ván chưa xong
    def termination_text(self) -> str: ...         # lý do kết thúc, tiếng Việt
    def can_claim_fifty_moves(self) -> bool: ...   # luật 50 nước: quyền tuyên bố
```

`apply_san` bắt và dịch các ngoại lệ của `python-chess` thành `MoveError` với thông điệp cụ thể (bảng ở §5). **Chỉ ghi vào lịch sử sau khi `push` thành công** — nước sai không được làm thay đổi thế cờ một ô nào.

### 3.2 `render.py` — bàn cờ Unicode

Một hàm công khai, thuần:

```python
def render(board: chess.Board, perspective: Color) -> str: ...
```

Quy ước: phe nhìn từ dưới lên. Trắng → hàng `1` ở dưới, hàng `8` ở trên. Đen → đảo cả hàng và cột. Quân trắng dùng ký tự rỗng (`♔♕♖♗♘♙`), quân đen dùng ký tự đặc (`♚♛♜♝♞♟`), ô trống là `.`.

Bàn cờ **không** in ký hiệu `+` / `#`. Nước vừa đi kèm ký hiệu đó do `Session.last_move_label()` trả về và được in riêng bởi `cli`, nên `render` không cần tham số phụ nào và test của nó chỉ cần so bàn cờ trần.

### 3.3 `session.py` — ván đấu

```python
class Session:
    def __init__(self, human_color: Color | None, elo: int = 1500,
                 style: str = "karpov", mode: str = "coach") -> None: ...
    def apply_san(self, san: str) -> None: ...      # ném MoveError
    def undo_turn(self) -> bool: ...                # lùi đúng 1 lượt, False nếu không đủ
    def pgn(self) -> str: ...
    def status_line(self) -> str: ...               # ELO, phong cách, chế độ, lượt đi
    def is_human_turn(self) -> bool: ...
    def last_move_label(self) -> str | None: ...    # "e4" hoặc "Nf3+"
```

`human_color=None` nghĩa là **người chơi đi cả hai bên** — chế đng thử nghiệm của #1, dùng để tự lái một ván trọn vẹn để kiểm chứng luật, chiếu hết, bế tắc, lặp thế. #2 thay bằng AI thật. `undo_turn` lùi **2 ply** (nước người + nước AI) hoặc 1 ply nếu đang ở chế độ hai bên.

`status_line` mang các tham số ELO/phong cách/chế độ từ #1 trở đi. Ở #1 chúng chỉ hiển thị, chưa có tác dụng — nhưng phải tồn tại để lệnh `/elo` và `/style` không phải sửa lại kiến trúc ở #2.

### 3.4 `cli.py` — REPL

`main() -> int`. Bảng lệnh tra cứu, không phải chuỗi `if/elif` dài.

Khởi động:

```
python -m chessai.cli [--side white|black] [--both] [--elo N] [--style T] [--mode M]
```

| Cờ | Mặc định | Ý nghĩa |
|---|---|---|
| `--side` | `white` | Phe người chơi. |
| `--both` | tắt | Đi cả hai bên (chế độ thử nghiệm §3.3). Ghi đè `--side`. |
| `--elo` | `1500` | Chỉ hiển thị ở #1. |
| `--style` | `karpov` | Chỉ hiển thị ở #1. |
| `--mode` | `coach` | Chỉ hiển thị ở #1. |

Lệnh trong REPL:

| Lệnh | Việc |
|---|---|
| *(SAN)* | Đi nước hợp lệ, ví dụ `e4`, `Nf3`, `O-O`, `exd5`, `e8=Q` |
| `/board` | Vẽ lại bàn cờ |
| `/fen` | In FEN hiện tại |
| `/pgn` | In PGN ván đang đấu |
| `/undo` | Lùi 1 lượt |
| `/resign` | Người chơi đầu hàng |
| `/draw` | Người chơi đề nghị hòa |
| `/help` | Liệt kê lệnh |
| `/quit` | Thoát |

Lệnh của #2 (`/hint`, `/best`, `/eval`, `/analyze`, `/puzzle`) **chưa có trong bảng này**. Ở #1, gõ phải trả lời "chưa hỗ trợ ở phiên bản này" chứ không phải "lệnh không tồn tại" — để không tạo cảm giác lỗi.

## 4. Luồng dữ liệu

```
chuỗi người dùng
   └─> cli.parse ──lệnh?──> bảng lệnh ──> session (undo/resign/…)
   │                          │
   │                          └─ không phải lệnh
   ↓
   san
   ↓
   session.apply_san ──> position.apply_san ──> chess.Board.push
   │                          │
   │  MoveError ──────────────┘  (thế cờ giữ nguyên, in lỗi)
   ↓
   session.is_game_over? ──> termination_text() nếu có
   ↓
   cli in: render(position.board, perspective) + pgn() + status_line()
```

## 5. Xử lý lỗi

| Tình huống | Thông điệp cho người chơi |
|---|---|
| Không phải SAN hợp lệ | Liệt kê vài nước hợp lệ gần nhất để gợi ý |
| Đi vào ô đang bị chiếu / không xử lý được chiếu | Nêu rõ điểm không hợp lệ |
| Nhập thành: đã di chuyển vua, hoặc qua/đến ô bị tấn công | Nêu rõ điều kiện nào không thỏa |
| Nhập thành: thiếu tốt | Nêu rõ thiếu tốt nào |
| Bắt tốt qua đường không hợp lệ | Nói rõ tốt bị bắt phải vừa đi 2 ô bằng một nước |
| Nhập thành bằng vua (`Kg1`) | Nói phải dùng ký hiệu `O-O` / `O-O-O` |
| Không rõ quân nào (`Nd2` khi 2 mã cùng đi được) | Yêu cầu chỉ rõ hậu tốc, ví dụ `Nbd2` |
| Không đến lượt người chơi | Chặn, không đổi lượt |
| Ván đã kết thúc | Chặn, nhắc lại kết quả |
| `undo` khi chưa có nước nào để lùi | Báo không có nước trước đó |

Bất biến bắt buộc: **mọi đường lỗi đều để lại thế cờ và lịch sử PGN không đổi.**

## 6. Luật FIDE phải hỗ trợ

- Nhập thành (`O-O`, `O-O-O`) kèm mọi điều kiện: vua chưa đi, ô vua không bị tấn công, ô đi qua không bị tấn công, tốt còn tại chỗ.
- Bắt tốt qua đường.
- Phong cấp tốt (`e8=Q`, kể cả phong cấp bắt tốt qua đường).
- Chiếu tướng và chiếu hết.
- Kết thúc ván: chiếu hết, bế tắc, không đủ lực lượng, lặp thế cờ 3 lần.
- Luật 50 nước: **đây là quyền tuyên bố, không phải hòa tự động.** Tự động hòa chỉ ở luật 75 nước (150 ply). Báo "có thể đề nghị hòa" khi đủ điều kiện 50 nước, tự kết thúc khi chạm 75 nước. Nhiều bản cờ điện tửng sai chỗ này.

## 7. Kiểm thử và tiêu chí hoàn thành

Dùng `unittest` stdlib, chạy bằng `python -m unittest`.

| # | Tiêu chí | Cách kiểm chứng |
|---|---|---|
| 1 | Toàn bộ test pass | `python -m unittest` exit 0 |
| 2 | perft đúng | Bảng §7.1 khớp tuyệt đối |
| 3 | `/undo` khôi phục nguyên thể cờ | So **chuỗi FEN byte-for-byte** trước và sau một lượt, trên nhiều thế cờ |
| 4 | Render đúng cả hai góc nhìn | So khớp chuỗi với bàn dựng tay, cả Trắng lẫn Đen |
| 5 | Nước sai không đổi thế cờ | Chụp FEN trước, nhập nước lỗi, so FEN sau — bằng nhau |
| 6 | PGN đúng định dạng | Chuỗi PGN khớp kỳ vọng cho ván mẫu |
| 7 | Phát hiện kết thúc ván | Bộ FEN mẫu cho chiếu hết, bế tắc, KvK, KvKN, lặp 3 lần, 50 và 75 nước |

### 7.1 Bộ perft

| Vị trí | FEN | Kỳ vọng |
|---|---|---|
| Xuất phát | `rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1` | d1=`20`, d2=`400`, d3=`8902`, d4=`197281` |
| Kiwipete (ghim, chồng quân, nhập thành cả hai bên) | `r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1` | d1=`48`, d2=`2039`, d3=`97862` |
| Kết cục tốt–xe (bắt tốt qua đường) | `8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1` | d1=`14`, d2=`191`, d3=`2812` |
| Phong cấp + quyền nhập thành | `r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1` | d1=`6`, d2=`264`, d3=`9467` |

**Giới hạn trung thực của tiêu chí này:** vì luật do `python-chess` thực hiện, perft chỉ chứng minh *phần nối của tôi đúng* (đếm ply, áp nước, gọi đúng API) — **không** chứng minh luật FIDE đúng, vì luật không phải code của tôi. Giá trị thật nằm ở tiêu chí 1, 3, 4, 5, 6, 7. Không được trích dẫn perft như bằng chứng mạnh hơn thực tế.

## 8. Ngoài phạm vi (YAGNI)

Không viết dòng nào cho tới #2: đánh giá thế cờ, alpha-beta, quiescence, mô phỏng ELO, `/hint`, `/best`, `/eval`, `/analyze`, AI đối thủ, `Puzzle`, `Review`, gọi LLM, lưu ván, opening book.

Một điểm móc duy nhất được để lại: `Session` báo sự kiện khi một lượt kết thúc, để #2 cắm search vào mà không phải sửa lại kiến trúc của #1.

## 9. Điểm móc cho #2 (ghi chép, không thiết kế chi tiết)

- `Session(human_color, elo, style, mode)` đã mang tham số → #2 chỉ cần đọc chúng.
- Lệnh CLI là bảng tra cứu → thêm mục, không sửa logic.
- Thay `human_color=None` bằng người chơi thật, cắm vào điểm móc ở §8.

## 10. Rủi ro đã biết

| Rủi ro | Giảm thiểu |
|---|---|
| Sai hướng render khi đảo góc nhìn | `render` là hàm thuần, test so chuỗi cả hai hướng (tiêu chí 4) |
| Bế tắc bị báo nhầm thành chiếu hết | Test bằng FEN bế tắc riêng biệt, không dùng chung case với chiếu hết |
| Lùi 1 ply thay vì 1 lượt | Tiêu chí 3 so FEN, sẽ bắt ngay |
| Nhầm luật 50 với 75 nước | §6 nêu rõ; test có FEN cho cả hai mốc |
| `python-chess` đổi API ở bản sau | Ghi bản cài đặt vào `requirements.txt` khi cài đặt lần đầu |
