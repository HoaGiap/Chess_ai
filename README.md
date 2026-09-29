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
python-chess==1.999    luật cờ vua
fastapi==0.138.0       web framework
uvicorn==0.40.0        máy chủ
pydantic==2.12.5       kiểm dữ liệu
websockets==15.0.1     WebSocket cho phòng chơi (extra của uvicorn, phải ghim riêng)
```

`starlette` và `anyio` là phụ thuộc của fastapi. Không có gói nào khác.

Quân cờ vẽ bằng SVG của [Colin M.L. Burnett](https://en.wikipedia.org/wiki/User:Colinburnett)
(CC BY-SA 3.0), xem `chessai/web/static/pieces/CREDITS.md`.

## Đưa lên Internet (Azure)

Máy ảo Ubuntu 24.04, mã nguồn đặt ở `/opt/chessai`, chạy bằng systemd, nghe
cổng 80. **Không cần nginx và không cần cài chứng thư**: Azure đã có sẵn
chứng thư cho tên `*.cloudapp.azure.com` và tự chuyển tiếp cổng 443 xuống
cổng 80 của máy ảo.

Lần đầu, trên máy ảo:

```bash
git clone <repo> /tmp/chessai-src      # hoặc chép thư mục lên
cd /tmp/chessai-src
sudo bash deploy/install.sh
```

`install.sh` tạo swap, cài thư viện vào venv riêng, và cài systemd service.
Chạy lại nhiều lần cũng được.

Sau đó, trong **Azure Portal**:

1. Mở NSG của máy ảo → thêm quy tắc cho phép **TCP 80** (và 443) từ
   `0.0.0.0/0`. Mặc định Azure chỉ mở cổng 22.
2. Thử `https://chess-online-vn.japaneast.cloudapp.azure.com`

Đẩy code mới lên (chạy trên máy của bạn, cần `ssh` và `rsync`):

```bash
bash deploy/deploy.sh <user>@<ip-cua-may-ao>
```

Script này chạy toàn bộ test trên chính máy chủ đó rồi mới khởi động lại.

Lệnh thường dùng trên máy ảo:

```bash
sudo systemctl restart chessai     # khởi động lại (xoá hết phòng!)
sudo journalctl -u chessai -f       # xem log trực tiếp
sudo systemctl status chessai
```

### Vì sao nghe cổng 80 chứ không cấu hình HTTPS

`deploy/chessai.service` cấp cho người dùng `chessai` đúng **một** quyền:
`CAP_NET_BIND_SERVICE`, đủ để bind cổng 80 mà không cần chạy bằng root, và
không cần thêm nginx để làm trung gian. Khi sau này bạn gắn tên miền riêng và
muốn kiểm soát nhiều hơn (bộ nhớ đệm, gzip, header bảo mật, log riêng) thì
đặt nginx trước và đổi cổng — phần còn lại không phải sửa gì.

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
5. **Không giới hạn số lần tạo phòng.** Đã có hạn mức: mỗi mã người chơi được
   tạo tối đa **20 phòng / 1 giờ**, hết hạn thì trả về 429. Ngoài ra khi bộ
   nhớ phòng đầy, hệ thống cắt **phòng đang chờ trước phòng đang chơi** — nên
   với vài người quen biết, người mới mở nhiều tab cũng không xoá được ván
   đang đấu của người khác. Hạn mức tính theo mã người chơi, mà mã đó lấy từ
   `/api/me` chỉ cần một lệnh GET, nên đây là rào hờm chứ không phải rào
   chống tấn công thật sự. Muốn chống thật thì phải giới hạn theo IP ở tầng
   nginx.
6. **Ván không được lưu lại.** Tải PGN xong là hết; không có lịch sử lâu dài.
7. **Sao chép link cần HTTPS.** `navigator.clipboard` chỉ chạy trong ngữ cảnh
   an toàn. Trên `http://` nút "Sao chép link" sẽ tự chọn ô link và bảo bạn
   tự copy. Trên tên `*.cloudapp.azure.com` của Azure thì có HTTPS nên không
   gặp vấn đề này.

## Nếu muốn mở rộng

`GameStore` và `RoomStore` là hai lớp giữ dữ liệu, được viết để thay thế được:
route HTTP không bao giờ đụng `chessai.Session` trực tiếp. Chuyển sang SQLite
hoặc Postgregres chỉ cần viết lại hai lớp đó, không sửa route.
