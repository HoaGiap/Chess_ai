# Đặc tả #3B — Đấu với máy

**Ngày:** 2026-09-28
**Trạng thái:** đã duyệt (người dùng uỷ quyền chọn toàn bộ quyết định còn lại)
**Dựa trên:** #3A (web core, đã xong — 7 commit trên `feature/chess-web`)

---

## 1. Mục tiêu

Bổ sung đối thủ máy vào bàn cờ web đã có. Người chơi bấm một nước, thấy quân
mình di chuyển ngay, rồi AI suy nghĩ và đáp lại.

**Ngoài phạm vi #3B** (đẩy sang #4 trở đi, không làm bây giờ):

- Gợi ý nước đi, giải thích nước đi, phân tích sau ván (chế độ `coach`)
- Nhiều phong cách chơi (field `style` giữ nguyên giá trị `karpov`)
- Bàn xếp hạng, đánh giá Elo thật sau ván
- Phòng chơi, nhiều người, WebSocket → #3C

---

## 2. Các quyết định đã chốt

| # | Quyết định | Vì sao |
|---|---|---|
| D1 | **Elo thật 600–2400** | `Session.elo` đã có sẵn từ #1; #3C cũng cần chính con số này |
| D2 | **Người đi ngay, AI nghĩ sau** (thread nền + client hỏi lại) | Không để người chơi nhìn bàn đứng yên 1–3 giây |
| D3 | **Chỉ chơi với AI**, không có coach | Rút ngắn #3B để có thứ chơi được sớm |
| D4 | **AI luôn chờ tối thiểu 600 ms** | Ở Elo thấp tìm nước xong trong ~10 ms, không có độ trễ thì cảm giác như đấu máy in |
| D5 | **Người chọn phe (Trắng/Đen) lúc mở ván mới** | `human_color` đã là tham số của `GameStore.create` từ #3A |
| D6 | **Tự viết engine**, không thêm phụ thuộc | Máy không có binary engine nào; ràng buộc "không thêm gói" của dự án |

---

## 3. Engine — `chessai/engine.py`

Negamax + alpha-beta cắt alpha-beta, quiescence, lặp tăng dần theo độ sâu.
Làm việc trên `chess.Board` (python-chess), không dùng `chess.engine` vì cái đó
cần một binary UCI bên ngoài.

### 3.1 Cấu trúc

```
chessai/engine.py
  PieceSquareTables   bảng điểm vị trí cho từng loại quân (mỗi màu 2 bảng)
  evaluate(board)     điểm: vật chất + bảng vị trí, điểm tương đối từ góc nhìn
                      phe đang đi; kéo về 0 dần theo số quân còn lại
  quiesce(board, …)   đuổi đuổi các nước bắt quân cho tới khi hết nước bắt
  negamax(board, depth, alpha, beta)  lướt nước, đảo phe, trả -điểm
  search(board, …)    lặp tăng dần độ sâu, giữ nước tốt nhất từ vòng trước làm
                      thứ tự khởi động, cắt theo thời gian và theo độ sâu
  think(board, elo, min_seconds) -> chess.Move | None
```

`think` là **hàm duy nhất** mà lớp web gọi. Nó:

1. Chọn `(max_depth, blunder_rate)` từ Elo.
2. Tìm nước tốt nhất trong khoảng `min_seconds`…`max_seconds`.
3. Với xác suất `blunder_rate`, **cố tình chọn một nước trong biên độ
   `slack_centipawns`** thay vì nước tốt nhất.
4. Trả về `None` nếu không còn nước đi.

### 3.2 Bảng điểm vị trí

Vị trí tĩnh, viết tay, **không học từ dữ liệu** (dự án không được thêm gói
dữ liệu, và số học thuần tay trong sách là đủ cho mức Elo này).

- Tốt: thưởng trung tâm, phạt biên, thưởng đôi tiến
- Mã: thưởng trung tâm và chéo, phạt rìa
- Tượng: thưởng đường chéo dài
- Hậu: bảng phản đối xứng, giá trị cao hơn ở trung tâm
- Vua: bảng an toàn (đi xa thì tốt hơn khi đã ổn định); phần "mở vua" xử lý
  riêng bằng chi phí phải di chuyển

### 3.3 Elo → tham số

Bảng cố định, chỉnh tay được:

| Elo | `max_depth` | `blunder_rate` | `slack_cp` | `max_seconds` |
|---|---|---|---|---|
| 600 | 1 | 0.45 | 220 | 0.4 |
| 900 | 2 | 0.30 | 150 | 0.8 |
| 1200 | 3 | 0.18 | 95 | 1.5 |
| 1500 | 4 | 0.10 | 60 | 2.5 |
| 1800 | 5 | 0.05 | 35 | 4.0 |
| 2100 | 6 | 0.02 | 20 | 6.0 |
| 2400 | 7 | 0.00 | 0 | 9.0 |

Giá trị giữa các mốc **nội suy tuyến tính**. Ngoài khoảng thì kẹp về hai đầu.

### 3.4 Sai sót phải trông như người, không phải như máy

Ở Elo thấp AI được phép chọn nước tệ, nhưng nước tệ đó vẫn phải **hợp lệ và
có lý do** (chặn, đuổi, phát triển). Cách làm: xếp các nước hợp lệ theo điểm
sau quiescence, rồi chọn ngẫu nhiên trong nhóm có điểm ≥ `điểm tốt nhất − slack_cp`.
Không bao giờ chọn nước làm mất quân trong khi còn nước bình thường.

---

## 4. Luồng dữ liệu — từ cú bấm đến nước AI

```
người bấm ô → POST /api/game/{id}/move
  └─ GameStore.submit()            (giữ khoá ván)
       ├─ Session.apply_san(nuoc)  → on_move(san, phe)
       │     └─ AIController: nếu tới lượt AI và ván chưa xong
       │          → đặt thinking = True, đẩy việc vào hàng đợi
       └─ trả GameState (thinking=True)  ← trả NGAY, không đợi AI
trình duyệt vẽ bàn, hiện "AI đang nghĩ…"
  └─ mỗi 300 ms: GET /api/game/{id} cho tới khi thinking = False
        └─ server: GameStore.snapshot()  (giữ khoá, trả kèm thinking)
```

**Trường hợp người chọn phe Đen.** Trắng đi trước, nên AI phải nghĩ ngay khi
ván vừa tạo chứ không đợi người đi. `POST /api/game` với `human_color="black"`
phải trả `thinking=true` và bật luồng AI, giống hệt sau một nước của người.

**Trường hợp hai bên** (`human_color=null`): không có AI, `thinking` luôn
`false`, `elo` bị bỏ qua. Đây là chế độ `--both` của #1, giữ nguyên.

### 4.1 Luật an toàn khi áp nước AI

Thread AI giữ FEN lúc bắt đầu. Trước khi áp nước, nó so FEN hiện tại với FEN
đó:

- **khác** → bỏ nước (người chơi đã bấm "Ván mới" / "Lùi" / đóng tab giữa chừng)
- **giống nhưng không còn tới lượt AI** → bỏ
- **giống nhau và vẫn tới lượt AI** → áp nước

Việc kiểm tra FEN và áp nước nằm chung một lần giữ khoá, nên không có khe hở.

### 4.2 Khoá

- `GameStore` giữ khoá **ngắn** quanh `submit` / `snapshot` / `undo` (như #3A).
- Thread AI **không** giữ khoá trong lúc tìm. Nó chỉ giữ khoá để đọc FEN lúc
  bắt đầu và để áp nước lúc kết thúc.
- Hệ quả: `GET`, `Lùi`, `Lật bàn` vẫn phản hồi trong lúc AI đang nghĩ.

### 4.3 Huỷ

Mỗi ván có một nối huỷ đơn giản (biến `bool` trong `AIController`). "Ván mới"
và "Lùi" báo huỷ để thread đang tìm biết kết quả của nó đã lỗi thời. Thread
vẫn chạy tới hết thời gian rồi tự kết thúc — tốn CPU nhưng không giữ tài nguyên
nào, nên **không cần** huỷ cưỡng bức (Python không huỷ được thread).

---

## 5. API

`GameState` thêm một trường:

| Trường | Kiểu | Nghĩa |
|---|---|---|
| `thinking` | `bool` | `true` khi AI đang tìm nước |

Route mới:

| Method | Đường dẫn | Việc |
|---|---|---|
| `POST` | `/api/game` | body `{human_color: "white"\|"black"\|null, elo: int}` — `null` = chơi hai bên (như cũ) |
| `GET` | `/api/game/{id}` | không đổi, giờ kèm `thinking` |

Không thêm route nào nữa. Client dùng lại `GET` để hỏi lại.

---

## 6. Giao diện

Thêm vào `index.html` / `style.css` / `app.js`:

1. **Bảng chọn ván mới**: hai nút **Trắng** / **Đen** và một thanh trượt Elo
   600–2400 (bước 100, mặc định 1200). Nằm trong khung thông tin, hiện khi
   bấm "Ván mới".
2. **Thanh trạng thái AI**: khi `thinking` thì hiện "AI đang nghĩ…" cạnh tên
   phe máy, kèm một dấu ba chấm nhấp nháy.
3. **Cấu trúc bàn cờ**: khi `human_color` khác `null`, bàn cờ **xoay theo phe
   người chơi** lúc mở ván (Trắng → quân dưới; Đen → quân trên), và bấm vào quân
   của máy thì không có chấm tròn nào hiện ra. Nút "Lật bàn" vẫn dùng được để
   xem ngược lại; xoay tay **không** ghi đè lựa chọn phe, và mở ván mới thì
   lại xoay về phe người chơi.
4. **Ván đang chơi**: hiện Elo của đối thủ trong khung thông tin.
5. **Chế độ hai bên**: không có bảng chọn phe nào hiện lên, `mode` đặt là
   `"play"`, `Session.mode` không dùng giá trị `"coach"` trong #3B.

Không có giao diện riêng cho coach. Không có bảng xếp hạng.

---

## 7. Kiểm thử

### 7.1 Engine (`tests/test_engine.py`)

| Kiểm thử | Vì sao |
|---|---|
| `evaluate` đối xứng: đổi phe thì điểm đổi dấu | bảng điểm bị lệch phe sẽ hỏng im lặng |
| Thế trắng +1 quân, đen trắng trừ 1, cân bằng = 0 | điểm vật chất sai là lỗi nền |
| Quân về ô đích luôn được thưởng vị trí | bảng vị trí không dùng |
| Ở Elo 2400, tìm được nước chặn chiếu tướng 1 nước | engine phải "thấy" chiếu tướng |
| Ở Elo 2400, không trả nước làm mất quân vô điều kiện | điều kiện tối thiểu sai sẽ ăn quân |
| Ở Elo 600, vẫn phải trả nước **hợp lệ** (luôn) | `blunder_rate` không được sinh nước bất hợp pháp |
| Quân hơn thì điểm dương ở mọi vị trí hợp lệ | bảng vị trí không được đảo dấu |
| Trên 20 thế mở, nước trả về luôn hợp lệ | hỏng chung |
| `think` tôn trọng `max_seconds` (không vượt quá 2×) | không treo |
| Vua bị chiếu thì trả nước đi chiếu lại (khi có nước) | đây là luật, không phải điểm |

### 7.2 Luồng (`tests/test_web_ai.py`)

| Kiểm thử | Vì sao |
|---|---|
| `thinking` mở đúng lúc: sau nước người thì `true`, sau nước AI thì `false` | trạng thái này quyết định client poll hay dừng |
| `human_color` truyền vào thì `is_human_turn` chặn đúng phe | lõi của chế độ đấu |
| Người đi nhầm phe thì 400 | lỗi phải rõ |
| Nước AI áp đúng, `turn` đổi, `moves` dài thêm 1 | chứng minh thread áp nước thật |
| FEN đổi giữa lúc nghĩ → nước AI **không** được áp | điều khoản 4.1 |
| `new_game` / `undo` huỷ nước AI đang chờ | cùng lý do |
| Cấu trúc ván (mode, elo, human_color) đi qua `new_game` | #3A đã sửa, giữ được |
| Bộ nhớ không rò khi AI tìm (khoá ngắn) | `GET` phải trả lời được khi AI đang nghĩ |

Vì thread tìm nước thật, các test luồng dùng **engine giả** (một `think` trả
nước đã biết, không tìm) — nhanh và xác định. Test khoá dùng engine giả có
`think` ngủ.

### 7.3 Trình duyệt

Theo §6 của spec #3A (kiểm bằng trình duyệt thật, không có framework JS):
chọn phe, chọn Elo, đi một nước, thấy "AI đang nghĩ…", thấy nước AI trượt vào,
không lỗi console.

---

## 8. Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Tìm nước quá chậm ở độ sâu 7 | `max_seconds` cắt tìm; bảng 7 là khoảng 20–60M nút trên máy yếu |
| Người chơi đóng tab lúc AI đang nghĩ | thread tự kết thúc; điều khoản 4.1 chặn hậu quả |
| Bảng điểm vị trí viết tay cân bằng kém | bảng Elo tỉ lệ theo `blunder_rate`; điều chỉnh được mà không đụng code khác |
| Trình duyệt poll 300 ms tạo tải | chỉ poll khi `thinking`; mỗi lần chỉ là `GET` nhỏ |
| Bộ nhớ đầy ván | trần 200 ván đã có từ #3A |
