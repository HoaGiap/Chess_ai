# Chess_ai

Cờ vua trên trình duyệt. Chơi với máy (Elo 600–2400), chơi với người thật qua
phòng, hoặc chơi hai bên trên cùng máy.

## Chạy

```bash
pip install -r requirements.txt
python -m chessai.web            # http://127.0.0.1:8000
python -m chessai.web --host 0.0.0.0   # cho máy khác cùng mạng vào
```

Dòng lệnh cũ vẫn còn:

```bash
python -m chessai --both         # chơi hai bên ở terminal
```

Chạy test:

```bash
python -m unittest               # 379 test
```

## Cách chơi

| Chế độ | Cách vào |
|---|---|
| Với máy | Trang chủ → **Chơi với máy** → chọn phe Trắng/Đen và Elo |
| Với người | Trang chủ → **Phòng** → **Tạo phòng**, rồi gửi link mời cho đối thủ |
| Hai bên | Trang chủ → **Hai bên** |

Không cần đăng nhập. Mỗi trình duyệt nhận một mã người chơi ngẫu nhiên và giữ
trong `localStorage`; mã đó **không** rời khỏi máy chủ trong bất kỳ phản hồi nào.
Muốn vào đúng phòng cũ thì mở lại link phòng, hoặc nhập mã phòng 8 ký tự.

Ván đang chơi nằm trong địa chỉ (`/?g=…` cho ván thường, `/?room=…` cho phòng),
nên F5 không mất ván.

## Kiến trúc

```
chessai/
  position.py      luật cờ vua (python-chess)
  session.py       một ván: phe người chơi, Elo, kết quả
  engine.py        máy chơi: negamax + alpha-beta + quiescence, Elo 600–2400
  cli.py           chơi ở terminal
  web/
    app.py         route FastAPI + WebSocket
    games.py       bộ nhớ ván
    rooms.py       bộ nhớ phòng (ghế, quyền host)
    ai.py          máy đi ở thread nền
    static/        giao diện (HTML/CSS/JS thuần, không bước build)
```

**Máy chủ giữ toàn bộ luật cờ vua.** Trình duyệt không có một dòng luật cờ vua
nào — nó chỉ khớp chuỗi với dữ liệu máy chủ gửi. Máy chủ gửi sẵn cả danh sách
nước hợp lệ, nên trình duyệt không bao giờ phải tự kiểm nước đi.

Không dùng framework JavaScript, không có bước build, không có `npm`.

## Phụ thuộc

```
python-chess     luật cờ vua
fastapi          web framework
uvicorn          máy chủ
pydantic         kiểm dữ liệu
websockets       đã là phụ thuộc của uvicorn — dùng cho phòng chơi
```

Quân cờ vẽ bằng SVG của [Colin M.L. Burnett](https://en.wikipedia.org/wiki/User:Colinburnett)
(CC BY-SA 3.0), xem `chessai/web/static/pieces/CREDITS.md`.

## Giới hạn đã biết

Cần nói thẳng trước khi đưa lên Internet:

1. **Mọi thứ nằm trong bộ nhớ máy chủ.** Tắt máy chủ là mất hết phòng và ván.
   Không có cơ sở dữ liệu.
2. **Chỉ chạy được trong MỘT tiến trình.** `uvicorn … --workers 2` sẽ làm hai
   người ở hai phòng khác tiến trình không thấy nhau. Cần khoá dùng chung
   (Redis/Postgres) mới xử lý được.
3. **Không có đăng nhập.** Mã người chơi nằm trong `localStorage` và là thứ duy
   nhất chứng minh bạn là bạn. Nó không nằm trong URL, nhưng nó **có** trong
   query string của WebSocket (`/ws/room/…?p=…`) — tức xuất hiện trong log máy
   chủ và log của reverse proxy. Đừng đặt sau proxy chia sẻ log công khai.
4. **Mã phòng 8 ký tự chỉ che mờ**, không phải bí mật. Ai đoán trúng mã thì vào
   được phòng đang *chờ* (ghế còn trống). Ván đã bắt đầu thì ghế đã đủ hai
   người nên không ai vào thêm được. Muốn phòng kín thật sự thì phải thêm mật
   khẩu phòng, không phải làm dài mã phòng.
5. **Không giới hạn số lần tạo phòng.** Mỗi lần tạo phòng cũng tạo một ván, và
   trần bộ nhớ là 200 phòng / 200 ván thường. Kẻ nào tạo liên tục sẽ đẩy phòng
   người khác ra — phòng bị đẩy ra thì người chơi phải tạo phòng mới.
6. **Ván không được lưu lại.** Tải PGN xong là hết; không có lịch sử lâu dài.

## Nếu muốn mở rộng

`GameStore` và `RoomStore` là hai lớp giữ dữ liệu, được viết để thay thế được:
route HTTP không bao giờ đụng `chessai.Session` trực tiếp. Chuyển sang SQLite
hoặc Postgregres chỉ cần viết lại hai lớp đó, không sửa route.
