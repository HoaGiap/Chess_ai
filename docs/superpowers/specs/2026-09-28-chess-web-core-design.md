# Spec: Chess Web Core — bàn cờ web, máy chủ giữ luật (Sub-project #3A)

- **Ngày:** 2026-09-28
- **Nhánh:** `feature/chess-web` (nhánh mới, tách từ `feature/chess-core`)
- **Bối cảnh:** sub-project #1 (luật FIDE + CLI) đã xong, 158 test. Sub-project này đưa cùng lớp luật đó lên web.
- **Quan hệ:** #3A là nền. #3B (đối thủ AI) và #3C (phòng chờ + chơi người thật) xây trên nền này.

---

## 1. Vì sao tách #3 thành ba

| | Nội dung | Vì sao tách |
|---|---|---|
| **#3A** (tài liệu này) | Máy chủ FastAPI, bàn cờ web, đi nước bằng HTTP, lùi, lật bàn, đổi nền. Chơi hai bên trên một trình duyệt. | Không cần thời gian thực, không cần engine — kiểm chứng được bằng test tự động và bằng mắt ngay |
| **#3B** | Engine AI (minimax + alpha-beta) cắm vào `Session.on_move` | Search chặn event loop, cần kiến trúc thread riêng |
| **#3C** | Phòng chờ, danh sách phòng, nút mời, WebSocket | Kỹ thuật thời gian thực và lỗi mất kết nối, khác hẳn #3A |

Gộp #3A với #3C là sai vì "phòng chờ" mà không có đồng bộ thời gian thực thì vô nghĩa. Gộp #3A với #3B thì mọi lỗi UI lẫn lộn với lỗi search.

## 2. Ràng buộc đã chốt

| Quyết định | Lý do |
|---|---|
| FastAPI + uvicorn + WebSocket (sẵn có sẵn) | Thang ưu tiên mục 2 và 5: không thêm dependency nào |
| HTML/CSS/JS thuần, **không có bước build** | Không `npm`, không `node_modules`, không chuỗi lỗi toolchain |
| **Python giữ toàn bộ luật.** Trình duyệt không có một dòng luật cờ vua | Một nguồn sự thật duy nhất; 158 test của #1 tiếp tục bảo vệ cả web |
| CSS grid, **không dùng Canvas** | Bàn 64 ô: DOM cho sẵn bắt chuột, hit-test, zoom, highlight. Canvas phải tự viết lại tất cả |
| Quân: SVG cburnett, **bundle trong repo** + `CREDITS.md` | Wikimedia chặn hotlink; bàn cờ trống khi không tải được ảnh là lỗi nặng nhất. Dự án chạy offline |
| Bàn `#eeeed2` / `#769656` (xanh cổ điển) | Đã chọn qua mẫu hình ảnh |
| Nước đi hợp lệ: chấm tròn ~25% ô trống · vòng tròn viền ô có quân địch | Đã chọn |
| Bố cục A: bàn trái, cột thông tin phải cao bằng bàn | Đã chọn qua mẫu hình ảnh |
| Nền tối mặc định, **có nút đổi nền**, nhớ qua `localStorage` | Đã chọn. Dùng biến CSS + `prefers-color-scheme` |
| Không bảng xếp hạng, không đăng nhập | Ngoài phạm vi. `OPENCODE.md` Ponytail mục 1 |
| Chạy local trước | Khi lên Internet sẽ thêm đăng nhập + lưu bền, không phải viết lại #3A |

## 3. Phạm vi

**Có:** bàn cờ web, chơi hai bên trong một trình duyệt, đi nước qua HTTP, thông điệp lỗi tiếng Việt, lùi, lật bàn, ván mới, đổi nền, nhập thành, bắt tốt qua đường, phong cấp.

**"Chơi hai bên" nghĩa là gì — chốt rõ để không hiểu nhầm:** cả Trắng và Đen do **cùng một trình duyệt** đi, giống hệt chế độ `--both` đã có sẵn ở #1. Đây là bàn cờ để kiểm chứng tương tác, **không phải** đấu với máy. Ở #3B một phe sẽ do engine đi, và điều đó chỉ đổi một tham số cấu hình, không phải viết lại giao diện.

**Không có (đẩy sang #3B/#3C):** đối thủ AI, phòng chờ, danh sách phòng, nút mời, WebSocket, đồng bộ thời gian thực, lưu ván bền, đăng nhỉp, xem lại ván cũ, bảng xếp hạng.

## 4. Kiến trúc

```
chessai/
├── position.py          giữ nguyên từ #1
├── session.py           giữ nguyên từ #1
├── render.py            giữ nguyên từ #1 (chỉ dùng cho terminal)
├── cli.py               giữ nguyên từ #1
└── web/
    ├── __init__.py
    ├── __main__.py      chạy uvicorn
    ├── app.py           FastAPI: route + xử lý lỗi
    ├── games.py         GameStore: các ván trong RAM, có khoá theo ván
    ├── schema.py        Pydantic: request/response
    └── static/
        ├── index.html
        ├── app.js
        ├── style.css
        └── pieces/      12 file SVG + CREDITS.md
```

Mỗi tệp một trách nhiệm. `app.py` không chứa luật cờ, `games.py` không biết HTTP, `app.js` không biết luật cờ.

### 4.1 `games.py` — nơi duy nhất giữ ván đấu

```python
class GameStore:
    def create(self, human_color: Color | None) -> str
    def get(self, game_id: str) -> Session
    def snapshot(self, game_id: str) -> dict      # DTO gửi cho trình duyệt
    def submit(self, game_id: str, san: str) -> dict
    def undo(self, game_id: str) -> dict
    def new_game(self, game_id: str) -> dict
```

Lưu trong `dict` kèm `threading.Lock` cho **từng ván**, không một khoá toàn cục — vì search của #3B sẽ chiếm một ván trong nhiều giây và không được chặn các ván khác.

**Lưu trữ nằm sau `GameStore` cố ý.** Khi lên Internet sẽ thay lớp này bằng SQLite/Postgres mà không đổi route nào. Hiện tại **không** viết lớp trừu tượng cho lưu trữ — chưa cần, và viết sớm là chi phí phải trả trước khi biết cần gì.

`game_id` là chuỗi 12 ký tự từ `secrets.token_urlsafe`.

### 4.2 `schema.py` — DTO

```python
class MoveOption(BaseModel):
    from_sq: str      # "e2"
    to_sq: str        # "e4"
    san: str          # "e4"
    capture: bool
    promotion: bool   # cần hộp chọn quân

class GameState(BaseModel):
    game_id: str
    fen: str
    turn: Color
    legal: list[MoveOption]
    last_move: str | None
    check: bool
    over: bool
    result_text: str
    moves: list[str]
    captured_by_white: list[str]   # quân phe TRẮNG đã bắt — chữ HOA (quân Đen bị ăn)
    captured_by_black: list[str]   # quân phe ĐEN đã bắt — chữ HOA (quân Trắng bị ăn)
    can_undo: bool
```

Tên `captured_by_*` dùng theo góc nhìn **người bắt**. Chữ cái loại quân luôn viết **HOA** kể cả quân Trắng, để trình duyệt không phải đoán màu — quân bị ăn luôn mang màu đối phương với người bắt, nên chỉ cần `b{P}` trong thư mục `pieces/`.

**Không dùng `Board.captured_pieces`** — bản `python-chess` đang cài **không có thuộc tính này** (đã kiểm: `AttributeError: 'Board' object has no attribute 'captured_pieces'`). Phải quét `move_stack` thủ công: với mỗi nước đi, nếu `board.is_capture(move)` thì lấy quân tại `to_square`; riêng bắt tốt qua đường thì quân bị ăn nằm ở ô **lùi 1 hàng về phía phe bắt** (kiểm chạy thật: `exd6` có `to_square=d6`, quân bị ăn ở `d5`).

**`legal` là `MoveOption`, không phải chuỗi SAN.** Trình duyệt cần khớp cú bấm chuột (ô nào → ô nào) với nước hợp lệ. Nếu chỉ gửi SAN thì trình duyệt phải tự phân tích SAN để biết ô đi và ô đến — tức là viết lại một phần luật cờ vua ở phía JS, đúng cái điều #3A cấm. Dạng `{from_sq, to_sq}` là **dữ liệu**, không phải luật: trình duyệt khớp chuỗi, không tự quyết đoán.

Bắt tốt qua đường dùng `to_sq` = ô trống mà tốt tới (ví dụ `d6`), vì đó đúng là `chess.Move.to_square`.

### 4.3 Route

| Route | Việc | Lỗi |
|---|---|---|
| `GET /` | `index.html` | |
| `POST /api/game` | tạo ván → `GameState` | |
| `GET /api/game/{id}` | `GameState` | 404 nếu không có |
| `POST /api/game/{id}/move` `{san}` | đi nước → `GameState` | 400 kèm thông điệp tiếng Việt |
| `POST /api/game/{id}/undo` | lùi 1 lượt → `GameState` | 404 |
| `POST /api/game/{id}/new` | ván mới, cùng `game_id` | 404 |
| `GET /api/game/{id}/pgn` | tải PGN | 404 |

**Xử lý lỗi dùng lại nguyên văn thông điệp của `position.py`.** `MoveError` được bắt và trả về `{"error": str(exc)}` với mã 400. Nhờ vậy web được đủ thông điệp tiếng Việt mà không viết lại một dòng thông báo nào — và mọi thông điệp đó đã có test.

### 4.4 `app.js` — trình duyệt không biết luật

- `GET /api/game/{id}` → vẽ bàn từ `fen`
- Bấm ô nguồn → tìm `MoveOption` nào có `from_sq` khớp → tô sáng đích hợp lệ (chấm tròn nếu `capture` false, vòng tròn nếu `capture` true)
- Bấm ô đích → `POST move` với `san`
- 400 → hiện `error` trong bảng thông tin, **không** đổi bàn cờ
- Đến `state.promotion` true → hiện hộp chọn Q/R/B/N, chờ chọn rồi mới gửi
- `GET /pgn` → tải file

**Không có `python-chess` ở phía JS.** Không có hàm kiểm tra luật nào. Trình duyệt chỉ khớp chuỗi từ `from_sq`/`to_sq` mà máy chủ gửi.

### 4.5 Hiển thị quân — hai lớp

- **Lớp ô:** CSS grid 8×8, màu ô, highlight (đang chọn / nước vừa đi / nước hợp lệ / vua bị chiếu), nhãn a–h và 1–8
- **Lớp quân:** một `div` phủ kín bàn; mỗi quân là `<img>` với `transform: translate(col, row)`

Nhờ tách hai lớp, việc quân trượt là **đổi `transform` → CSS transition tự chạy** (`transition: transform .15s ease`). Không cần JS tween, không cần Canvas.

Bí mật: `<img>` không nhận CSS transition tốt trên mọi trình duyệt khi kích thước cũng đổi. Vì vậy quân là `<img>` có kích thước **cố định theo %** và chỉ `transform` thay đổi.

**Kích thước bàn:** bàn là hình vuông, `width: min(640px, 92vw)`, căn giữa trong cột trái. Cột thông tin phải rộng 260px cố định. Dưới 720px chiều ngang, cột thông tin xuống dưới bàn và chiếm hết bề ngang — một quy tắc media query duy nhất.

**Màu highlight (chốt cụ thể để không mỗi lần hiểu một kiểu):**

| Trạng thái | Màu |
|---|---|
| Nước vừa đi (from/to) | vàng `#ffd54a` phủ 35% |
| Ô đang chọn (nguồn) | viền trong 4px `#ffd54a` |
| Ô hợp lệ, đích trống | chấm tròn đen 28% trên ô sáng / trắng 55% trên ô tối |
| Ô hợp lệ, đích có quân địch | vòng tròn viền 4px `rgba(255,80,80,.95)` |
| Vua đang bị chiếu | nền đỏ `rgba(220,60,60,.55)` |
| Nhãn a–h / 1–8 | `#769656` trên ô sáng, `#eeeed2` trên ô tối, cỡ 11px |

Vòng tròn viền đặt ở `inset: 1%` để **không che hình quân đứng trên ô** — đã chốt qua mẫu hình ảnh.

**Hộp chọn phong cấp:** khi nước đã chọn có `promotion: true`, hiện bốn nút Q/R/B/N **đè lên ô đích**. Bấm ô khác hoặc bấm lại ô nguồn thì **huỷ hẳn**, quay về trạng thái chọn quân, không gửi gì lên máy chủ. Không có nút "hủy" riêng — chính việc bấm ra ngoài là cách huỷ.

### 4.6 Đổi nền

Biến CSS trên `:root`, `[data-theme="sáng"]`. Mặc định theo `prefers-color-scheme`. Nút đổi ghi `data-theme` vào `<html>` và lưu `localStorage`. Không đụng JS khác.

### 4.7 Chạy

```
python -m chessai.web          # mặc định localhost:8000
python -m chessai.web --port 9000 --host 0.0.0.0   # để máy khác cùng mạng vào
```

`__main__.py` gọi `uvicorn.run` với tham số từ `argparse`. Một lệnh duy nhất, không bắt gõ đường dẫn module của uvicorn.

## 5. Trạng thái ván mất khi máy chủ khởi động lại

Ván nằm trong RAM nên **mất sạch khi restart**. Trình duyệt phải xử lý 404 bằng cách hiện "Ván không còn tồn tại (máy chủ đã khởi động lại)" kèm nút tạo ván mới. Đây là hành vi thật, phải có test — không phải chi tiết bỏ qua.

## 6. Kiểm thử

**Máy chủ — `unittest` thuần, gọi trực tiếp handler.** `fastapi.testclient.TestClient` **không dùng được** vì máy này không có `httpx` (đã kiểm: `import httpx` → `ModuleNotFoundError`; thứ đang cài tên là `httpx2`, hoàn toàn khác). Cài `httpx` là thêm dependency, trái §2.

Thay vào đó: route handler của FastAPI là hàm Python thường, nên test gọi thẳng `asyncio.run(handler(...))` rồi kiểm `JSONResponse.status_code` và `.body`. **Đã kiểm chạy thật** — cách này cho ra 400 kèm đúng thông điệp tiếng Việt.

Còn một mảnh mà cách này không phủ: định tuyến URL và tuần tự hoá JSON. Mảng đó kiểm bằng trình duyệt thật ở mục kế tiếp.

| Nhóm | Kiểm |
|---|---|
| Route cơ bản | Tạo ván trả `GameState` đúng cấu trúc; `legal` ở vị trí xuất phát có 20 nước |
| Đi nước | `e2e4` hợp lệ → FEN đổi, `moves == ["e4"]` |
| Nước sai | 400, `error` bằng tiếng Việt, **FEN không đổi** |
| Thông điệp lỗi | Không chứa `illegal san` hay FEN — chống hồi quy về lỗi của #1 |
| Lùi | `can_undo` đúng; lùi ở ván mới trả lỗi chứ không 500 |
| Ván mới | FEN về vị trí xuất phát, `moves` rỗng |
| 404 | `game_id` bịa trả 404 kèm thông điệp |
| Mất ván | Xoá ván khỏi store rồi `GET` → 404 |
| Mã `from_sq`/`to_sq` | Với `e2e4`, `MoveOption` đó có `from_sq=="e2"`, `to_sq=="e4"` |
| Đồng bộ FEN | `POST move` với SAN hợp lệ rồi `GET` phải trả cùng FEN |
| Đặc biệt | `MoveOption` cho `O-O` có `from_sq="e1"`, `to_sq="g1"`; cho `exd6` có `to_sq="d6"` và `capture=true`; cho `a8=Q` có `promotion=true` |
| Quân bị bắt | Sau `e4 d5 exd5`, `captured_by_white == ["P"]`; sau `Qxd5`, `captured_by_black == ["P"]` |

**Giao diện — không cài framework test JS.** Kiểm bằng trình duyệt thật: mở `localhost:8000`, đi vài nước, chụp màn hình, đọc console không có lỗi. Lý do: thêm Playwright/Cypress nghĩa là thêm dependency vào đúng dự án mà 3 câu trên vừa nói là không thêm gì. Đánh đổi được vì #3A chỉ có vài chức năng và kiểm thử thủ công có thật.

**Hồi quy:** 158 test của #1 phải xanh sau mọi thay đổi.

## 7. Tiêu chí hoàn thành

1. `python -m unittest` — tất cả xanh, gồm 158 test cũ và test web mới
2. `python -m chessai.web` → mở `http://localhost:8000` thấy bàn 8×8 đúng vị trí quân
3. Bấm `e2` rồi `e4`: quân trượt, bảng thông tin hiện `1. e4`, ô hợp lệ tô sáng trước khi bấm
4. Bấm một ô không hợp lệ: hiện thông điệp tiếng Việt, **bàn cờ không đổi một ô nào**
5. Bấm lại một nước hợp lệ: lỗi biến mất, bàn cờ cập nhật
6. Nhập thành: highlight đúng, bàn cờ sau đó đúng
7. Tốt tới hàng cuối: hộp chọn phong cấp hiện ra, chọn quân xong bàn cờ đúng
8. Lật bàn, ván mới, lùi: hoạt động
9. Nút đổi nền: đổi ngay và **nhớ qua reload**
10. Console trình duyệt không có lỗi
11. Không file nào dưới `chessai/web/static/pieces/` nằm ngoài bộ cburnett; có `CREDITS.md`

## 8. Điểm móc cho #3B và #3C

- **`Session.on_move(canonical_san, mover_color)`** — sẵn sàng. #3B gán callback chạy search rồi gọi `position.apply_san`.
- **`can_claim_fifty_moves()`** — sẵn sàng để hiện cảnh báo trong bảng thông tin.
- **`GameStore` có khoá theo từng ván** — #3B sẽ chạy search **ngoài** khoá, vì giữ khoá suốt lúc search sẽ chặn mọi ván khác.
- **Cần `asyncio.to_thread` cho search** — `python-chess` là generator Python, gọi trực tiếp trong route async sẽ chặn event loop. Đã ghi để #3B không phát hiện lại từ đầu.
- **`POST /api/game/{id}/pgn`** đã có sẵn để tải ván trước khi lên Internet.

## 9. Rủi ro đã biết

| Rủi ro | Giảm thiểu |
|---|---|
| Trình duyệt lọt luật cờ vua khi cần hiện hộp phong cấp | `MoveOption.promotion` do máy chủ tính; trình duyệt chỉ hiện lựa chọn |
| `<img>` không chạy transition | Quân dùng kích thước cố định, chỉ đổi `transform`; kiểm bằng mắt ở tiêu chí 3 |
| Ván mất khi restart gây trải nghiệm tệ | §5 bắt buộc xử lý 404 kèm nút tạo ván mới, có test |
| 12 tên file SVG trên Commons chưa xác minh | Xem §10 — có phương pháp tra cứu và đường dẫn dự phòng đã kiểm chạy thật |
| Bảng thông tin lệch khi ván dài | Danh sách nước đi cuộn riêng, không làm giãn trang |

## 10. Lấy bộ quân — ghi rõ vì chưa xác minh được tên file

Tôi **không** ghi 12 tên file vào spec này vì đã thử tra và **không xác minh được** bộ tên chuẩn trên Wikimedia Commons. Ghi tên file đoán vào spec chính là loại lỗi tôi đã mắc nhiều lần trong #1.

**Đã kiểm chạy thật:** `https://lichess1.org/assets/piece/cburnett/wK.svg`, `bK.svg`, `wP.svg` — cả ba trả HTTP 200, dung lượng 400–783 byte. Cùng bộ cburnett, cùng giấy phép.

**Thứ tự thực hiện:**
1. Tra Commons bằng API: `action=query&list=allimages&aiprefix=Chess_` rồi lọc theo mô tả trang tệp để lấy đủ 12 tên, kiểm `extmetadata.LicenseShortName` là `CC BY-SA 3.0` trước khi dùng.
2. Nếu không lấy đủ 12 từ Commons: tải từ `lichess1.org` (đường dẫn đã kiểm) — **vẫn là cburnett CC BY-SA 3.0**, ghi rõ nguồn trong `CREDITS.md`.
3. `CREDITS.md` phải ghi: tên tác giả, nguồn tải, giấy phép, và ghi chú rằng ảnh được dùng **không sửa đổi** nên nghĩa vụ share-alike không lan sang mã nguồn dự án.

**Tiêu chí chấp nhận:** 12 file SVG, tổng dưới 40 KB, mỗi file là SVG hợp lệ, và `CREDITS.md` nêu đúng giấy phép.
