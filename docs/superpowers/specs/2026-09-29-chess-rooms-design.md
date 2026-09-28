# Đặc tả #3C — Phòng chơi người thật

**Ngày:** 2026-09-29
**Trạng thái:** đã duyệt (người dùng uỷ quyền chọn toàn bộ quyết định còn lại)
**Dựa trên:** #3A (web core) và #3B (đấu với máy) — đã xong

---

## 1. Mục tiêu

Hai người mở cùng một máy chủ, vào cùng một phòng, đấu với nhau trên cùng
bàn cờ web đã có.

**Ngoài phạm vi #3C:**

- Tài khoản, đăng nhập, mật khẩu
- Trò chuyện, bình luận
- Bảng xếp hạng, ghi lại ván, phân tích sau ván
- Lưu ván lâu dài (mọi thứ nằm trong RAM máy chủ)
- Chơi qua nhiều tiến trình máy chủ (xem §8)

---

## 2. Các quyết định đã chốt

| # | Quyết định | Vì sao |
|---|---|---|
| C1 | **Không tài khoản.** Mỗi trình duyệt nhận một mã người chơi ngẫu nhiên, giữ trong `localStorage` | Đủ để phân biệt hai người; không cần mật khẩu, không cần bảng cơ sở dữ liệu |
| C2 | **WebSocket chỉ chiều máy chủ → trình duyệt.** Lệnh vẫn đi qua HTTP POST | Luật cờ vua nằm ở một chỗ; không mở đường ghi mới cần bảo vệ |
| C3 | **Có dự phòng bằng cách hỏi lại (poll)** nếu WebSocket không mở được | Không để một lần kết nối hỏng chặn cả trò chơi |
| C4 | **Không có nút "Lùi 1 lượt" khi đang đấu người** | Lùi nước của đối thủ là hành vi không công bằng; thêm luật riêng là phạm vi khác |
| C5 | **Ghế trống vẫn giữ chỗ cho người đã ngắt kết nối** để họ quay lại bằng đúng link | Không có tài khoản nên link + mã người chơi là cơ chế quay lại duy nhất |
| C6 | **Hồi quy lượt bấm ngắt kết nối**: đối thủ thấy "đối thủ mất kết nối" và có thể chấp nhận đầu hàng | Không để một người treo cả ván bằng cách đóng tab |
| C7 | **Phòng nằm trong RAM, trần 200 phòng**, cắt bỏ phòng cũ nhất khi đầy | Khớp với cách `GameStore` đã làm; không thêm bảng cơ sở dữ liệu |
| C8 | **Mã phòng 8 ký tự** từ bảng chữ không dễ nhầm (không l, o, i, 0, 1) | Người ta sẽ đọc to nó ra cho người khác; ngắn mà vẫn đủ khó đoán |

---

## 3. Dữ liệu

### 3.1 Người chơi

```
PlayerToken = 22 ký tự urlsafe (secrets.token_urlsafe(16))
```

Máy chủ cấp qua `GET /api/me`; trình duyệt giữ trong `localStorage` và gửi kèm
mọi yêu cầu qua header `X-Player`.

### 3.2 Phòng

```
Room
  id          str    8 ký tự, ví dụ "k7m2p9qx"
  created_at  float
  seats       { player_token: "white" | "black" }   0, 1 hoặc 2 người
  host        player_token | None                  ai tạo phòng
  game_id     str | None                            trỏ vào GameStore
  started     bool                                   đã bắt đầu hay chưa
  finished    bool
  result_text str | None
```

Một phòng luôn có **đúng một** `game_id`, tạo lúc phòng được tạo (không phải
lúc bắt đầu) — vì `GameStore` cần một ván để giữ lịch sử nước đi, và tạo sớm
giúp phòng hỏng vẫn xem được bàn cờ.

`human_color` của ván luôn là `None` (không có AI trong phòng), nên
`AIController` không can thiệp.

### 3.3 Trạng thái hiển thị

Tính lúc đọc, không lưu:

| Tình huống | Nhãn |
|---|---|
| 0 người (vừa tạo) | "Chờ người" |
| 1 người | "Chờ đối thủ" |
| 2 người, chưa bắt đầu | "Sẵn sàng" |
| đã bắt đầu, còn quân | "Đang đấu" |
| ván xong | "Xong" |

---

## 4. Luồng

```
Mở /  ──►  màn hình chính
              ├─ "Chơi với máy" ──► hộp chọn phe + Elo (#3B, đã có)
              ├─ "Chơi hai bên"  ──► POST /api/game (đã có)
              └─ "Chơi với người" ──► màn hình danh sách phòng
                                        ├─ "Tạo phòng" ──► POST /api/rooms
                                        └─ bấm "Vào"    ─► POST /api/rooms/{id}/join
                      vào phòng:  /?room=<id>
                          ├─ chưa đủ 2 người ──► phòng chờ: link mời + nút sao chép
                          └─ đủ và đã bắt đầu ──► bàn cờ
```

Bấm "Tạo phòng" hoặc "Vào" đều chuyển sang `/?room=<id>`.

---

## 5. API

### 5.1 Bộ đệm dùng chung

| Method | Đường dẫn | Body | Trả về |
|---|---|---|---|
| `GET` | `/api/me` | — | `{player: "<token>"}` |
| `GET` | `/api/rooms` | — | `{rooms: [RoomView]}` |
| `POST` | `/api/rooms` | — | `{room_id}` |
| `POST` | `/api/rooms/{id}/join` | — | `RoomView` |
| `POST` | `/api/rooms/{id}/leave` | — | `RoomView` |
| `POST` | `/api/rooms/{id}/start` | — | `RoomView` |
| `POST` | `/api/rooms/{id}/move` | `{san}` | `RoomState` |
| `POST` | `/api/rooms/{id}/resign` | — | `RoomState` |
| `POST` | `/api/rooms/{id}/rematch` | — | `RoomView` |

`RoomView` = thông tin công khai: `id`, `status`, `seats` (`white`/`black` là
mã người chơi đã cắt bớt, `null` nếu trống), `host`, `started`, `finished`,
`you` (màu của người gọi hoặc `null`).

`RoomState` = `RoomView` + `game` (đúng `GameState` mà #3A đã định nghĩa).

### 5.2 WebSocket

- `WS /ws/room/{id}?p=<token>` — máy chủ **chỉ đẩy**.
- Khi có thay đổi (người vào/ra, bắt đầu, có nước đi, đầu hàng), máy chủ gửi
  `{"type": "state", "data": <RoomState>}` cho **mọi** người đang ở phòng,
  kể cả người vừa gây ra thay đổi.
- Kết nối không hợp lệ (thiếu token, phòng không tồn tại) → đóng với mã 1008.

### 5.3 Bắt buộc về mã HTTP

| Tình huống | Mã | Thông điệp (tiếng Việt) |
|---|---|---|
| Thiếu / sai `X-Player` | 401 | "Chưa nhận diện được người chơi — tải lại trang." |
| Không tìm thấy phòng | 404 | "Phòng không tồn tại hoặc đã đóng." |
| Phòng đã đủ 2 người | 409 | "Phòng đã đủ hai người chơi." |
| Không phải host mà bấm "Bắt đầu" | 403 | "Chỉ người tạo phòng mới được bắt đầu." |
| Chưa đủ 2 người mà bấm "Bắt đầu" | 400 | "Cần đủ hai người chơi mới bắt đầu được." |
| Đi nước khi chưa tới lượt mình | 400 | "Chưa đến lượt bạn." |
| Đi nước khi phòng chưa bắt đầu | 400 | "Ván chưa bắt đầu." |
| Cố dùng "Lùi 1 lượt" trong phòng | 400 | "Trong phòng không có nút lùi nước." |
| Ván đã xong mà vẫn đi nước | 400 | "Ván đã kết thúc." |

---

## 6. Giao diện

Một trang, ba màn, dùng chung `index.html`:

1. **Màn chính** — ba lựa chọn ở trên bàn cờ, kèm nút "Chơi với máy" mở hộp
   chọn phe/Elo đã có (#3B).
2. **Danh sách phòng** — bảng: mã phòng, trạng thái, số người, cột nút "Vào".
   Trên cùng: nút "Tạo phòng" và ô nhập mã phòng để vào bằng tay.
3. **Phòng chờ** — hai ghế (Trắng / Đen) hiện đã có ai, ô link mời kèm nút
   **Sao chép**, nút "Bắt đầu" (chỉ host thấy và chỉ bật khi đủ 2 người).

Khi đã bắt đầu: bàn cờ như #3A, ẩn nút "Lùi 1 lượt", thêm nút **Đầu hàng**.

Trên đầu khung thông tin hiện một dòng trạng thái phòng: ai đang đi, đối thủ
mất kết nối hay không.

---

## 7. Kiểm thử

### 7.1 Bộ nhớ phòng (`tests/test_rooms.py`)

| Kiểm thử | Vì sao |
|---|---|
| Tạo phòng → ghế trống, là host | nền tảng |
| Vào phòng → ghế trắng, ghế đen trống | ai bên nào phải xác định |
| Vào phòng lần hai bằng mã khác → ghế đen | bổ sung ghế còn trống |
| Vào phòng đã đủ → `FullRoom` | chặn người thứ ba |
| Vào lại phòng đã vào → trả về chỗ cũ, không lỗi | tải lại trang là việc bình thường |
| Không tạo host mà bấm bắt đầu → `NotHost` | tránh người lạ giành quyền |
| Chưa đủ người mà bắt đầu → `NotEnough` | |
| Rời phòng → ghế trống lại, ghế kia giữ nguyên | |
| Phòng đầy thì ván vẫn giữ đúng lịch sử nước đi | nối `GameStore` |
| Mã phòng đủ dài và không có ký tự dễ nhầm | tránh đoán và tránh đọc nhầm |
| Tràn số phòng → phòng cũ nhất bị bỏ | |

### 7.2 Route (`tests/test_web_rooms.py`)

Gọi thẳng handler như các test #3A:

| Kiểm thử |
|---|
| `GET /api/me` trả token dài, token khác mỗi lần |
| Thiếu `X-Player` → 401 kèm tiếng Việt |
| `POST /api/rooms` → 200, trả `room_id` dài 8 |
| Vào phòng rồi đi nước hợp lệ → `moves` dài 1 |
| Đi nước khi chưa tới lượt mình → 400, `moves` **không đổi** |
| Đi nước khi phòng chưa bắt đầu → 400 |
| `/start` bởi host khi đủ 2 người → 200, `started` đúng |
| `/start` bởi người không phải host → 403 |
| `/start` khi thiếu người → 400 |
| `/resign` → `over` đúng, `result_text` nói ai đầu hàng |
| `/move` sau khi xong → 400 |
| `/move` trong phòng không chấp nhận lùi nước |
| Phòng không tồn tại → 404 |
| Token giả mạo (người thứ ba) không được đi nước thay người đã vào |

### 7.3 Trình duyệt

Vì máy không có `httpx` nên WebSocket không kiểm được bằng `TestClient`. Vì
vậy kiểm bằng trình duyệt thật:

1. Tạo phòng → URL có `?room=`, hiện link mời và nút sao chép.
2. Mở tab thứ hai với cùng link → tab một thấy đủ 2 người, nút "Bắt đầu" bật.
3. Bắt đầu → cả hai tab thấy bàn cờ, mỗi tab **xoay đúng phe của mình**.
4. Đi một nước → nước đó hiện ở **cả hai tab** mà không cần tải lại.
5. Tab hai cố đi khi chưa tới lượt → báo "Chưa đến lượt bạn.", bàn không đổi.
6. Nút "Đầu hàng" → cả hai tab thấy kết quả.
7. Đóng tab giữa ván → tab còn lại thấy "đối thủ mất kết nối".
8. Console: **0 lỗi**.

---

## 8. Rủi ro và giới hạn đã biết

| Rủi ro / giới hạn | Người dùng thấy gì | Xử lý |
|---|---|---|
| Phòng nằm trong RAM | Máy chủ khởi động lại là mất hết phòng | Ghi rõ trong phòng chờ. Sửa được sau bằng SQLite |
| **Chỉ chạy được trong MỘT tiến trình máy chủ** | Chạy `--workers 2` thì hai người vào phòng khác tiến trình sẽ không thấy nhau | Ghi rõ trong `__main__.py` và README. Cần khoá dùng chung (Redis/Postgres) mới chạy nhiều tiến trình |
| Không có đăng nhập | Ai có mã người chơi của người khác thì vào được phòng | Chấp nhận được cho dự án cá nhân; mã người chơi không nằm trong URL nên không rò qua lịch sử trình duyệt |
| **Mã phòng KHÔNG phải bí mật** — nó chỉ che mờ | 8 ký tự từ 31 ký hiệu ≈ 2^40, đoán mò thì được nhưng rất chậm; và ai đoán trúng cũng chỉ vào được phòng đang **chờ** | Đây là cố ý. Bí mật thật là **mã người chơi** (2^128), nằm trong `localStorage` và không nằm trong URL. Nếu sau này cần phòng kín thật sự thì phải thêm mật khẩu phòng, không phải làm dài mã phòng |
| Máy chủ tắt giữa ván | Ván mất | Tương tự `GameStore`, đã nói rõ từ #3A |
