#!/usr/bin/env bash
# Đẩy code mới lên máy ảo và khởi động lại máy chủ.
#
#   bash deploy/deploy.sh <user>@<ip>
#   bash deploy/deploy.sh hoa@chess-online-vn.japaneast.cloudapp.azure.com
#
# Chạy trên máy CỦA BẠN. Phải chạy từ trong WSL/Git Bash (cần `rsync`), KHÔNG
# chạy `ssh.exe` của Windows — bản đó không có ControlMaster.
#
# CHỈ hỏi mật khẩu MỘT lần nhờ ControlMaster.
# CHÚ Ý: restart sẽ xoá hết phòng và ván đang chơi, vì mọi thứ nằm trong RAM.
#       Chỉ deploy khi không ai đang đánh.

set -euo pipefail

TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  echo "Dùng: bash deploy/deploy.sh <user>@<ip>" >&2
  echo "Ví dụ: bash deploy/deploy.sh hoa@20.46.112.69" >&2
  exit 1
fi

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE=chessai

# SSH nhân bản kết nối: lần đầu mở "master" và giữ 10 phút, các lần sau dùng
# lại nên không hỏi mật khẩu nữa. Không có `ControlMaster` thì mỗi lệnh
# `ssh`/`rsync` sẽ hỏi lại — đó là lý do script cũ hỏi tới 5 lần.
SSH_OPTS=(
  -o ControlMaster=auto
  -o "ControlPath=/tmp/chessai-cm-%r@%h:%p"
  -o ControlPersist=10m
  -o ConnectTimeout=15
)
RSYNC_SSH="ssh -o ControlMaster=auto -o ControlPath=/tmp/chessai-cm-%r@%h:%p -o ControlPersist=10m -o ConnectTimeout=15"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mXX\033[0m %s\n' "$*" >&2; exit 1; }

remote() { ssh "${SSH_OPTS[@]}" "$TARGET" "$@"; }

cleanup() {
  # Đóng kết nối chính để không để lại socket treo trong /tmp.
  # ControlPath là "/tmp/chessai-cm-%r@%h:%p" nên socket tên đúng là
  # /tmp/chessai-cm-<user>@<host>:<port> — dùng user@host:22 từ $TARGET.
  ssh -S "/tmp/chessai-cm-$TARGET:22" -O exit "$TARGET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

for tool in rsync ssh; do
  command -v "$tool" >/dev/null || die "Thiếu $tool. Hãy chạy script này trong WSL hoặc Git Bash."
done

say "Kết nối tới $TARGET (chỉ hỏi mật khẩu ở lần này)"
remote 'true' || die "Không kết nối được."

say "Tìm xem ứng dụng đang chạy ở đâu"
# KHÔNG hard-code /opt/chessai: máy có thể đã cài ở chỗ khác. Hỏi systemd
# rồi mới đẩy, nếu không sẽ rsync vào thư mục không tồn tại hoặc không có quyền.
APP_DIR="$(remote "systemctl show -p WorkingDirectory --value $SERVICE" 2>/dev/null || true)"
if [[ -z "$APP_DIR" || "$APP_DIR" == "/" ]]; then
  die "Không tìm thấy service '$SERVICE'. Trên máy chủ đang chạy thật sự là:
     systemctl list-units --type=service | grep -iE 'chess|uvicorn|chessai'
     rồi sửa SERVICE= trong deploy.sh cho đúng."
fi
say "Ứng dụng nằm ở: $APP_DIR"

say "Nạp quyền sudo một lần (hỏi mật khẩu ở đây)"
remote "sudo -v" || die "Không nạp được quyền sudo."

remote "systemctl is-active --quiet $SERVICE && echo 'Máy chủ đang chạy — restart sẽ xoá hết phòng.' || echo 'Máy chủ đang dừng.'"

say "Đẩy mã nguồn"
# rsync phải chạy Ở MÁY NÀY, dùng `-e ssh` làm đường truyền tới máy chủ.
# Gọi `ssh ... "rsync ..."` như bản cũ là SAI: khi đó rsync chạy trên máy
# chủ và đi tìm đường dẫn kiểu /mnt/d/... trên máy chủ — không tồn tại ở đó.
# --delete để file đã xoá ở local cũng biến mất ở máy chủ.
# Không đụng .venv: thư viện cài riêng ở dưới.
rsync -a --delete \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
  --exclude '.superpowers' --exclude '*.pyc' \
  -e "$RSYNC_SSH" \
  "$SOURCE_DIR/" "$TARGET:$APP_DIR/" \
  || die "rsync thất bại. Máy chủ có sẵn rsync chưa? Kiểm tra: ssh $TARGET 'which rsync'"

say "Bảo đảm có venv rồi cài lại thư viện"
# Phải hỏi MÁY CHỦ xem venv có sẵn không. Bản cũ kiểm `[[ -x ... ]]` ở máy
# này — đường dẫn /opt/... không tồn tại trên Windows nên nhánh if không bao
# giờ vào, còn nhánh else chỉ chạy được là do may mắn.
if ! remote "test -x '$APP_DIR/.venv/bin/python'"; then
  say "Tạo venv trên máy chủ (lần đầu)"
  remote "python3 -m venv '$APP_DIR/.venv'" || die "Không tạo được venv."
fi
remote "'$APP_DIR/.venv/bin/python' -m pip install --quiet -r '$APP_DIR/requirements.txt'" \
  || die "Cài thư viện thất bại."

say "Chạy toàn bộ test trên chính máy chủ đó"
# Đây là chốt chặn cuối: test đỏ thì KHÔNG restart, để máy chủ cũ còn chạy.
remote "cd '$APP_DIR' && .venv/bin/python -m unittest 2>&1 | tail -3" || true
if ! remote "cd '$APP_DIR' && .venv/bin/python -m unittest >/dev/null 2>&1"; then
  die "Test thất bại trên máy chủ — KHÔNG restart. Code trên máy đã được thay nhưng tiến trình cũ vẫn đang chạy nên người chơi không bị ảnh hưởng."
fi

say "Khởi động lại máy chủ"
remote "chown -R \$USER:\$USER '$APP_DIR' 2>/dev/null || true; sudo systemctl restart $SERVICE"
sleep 3
remote "systemctl is-active --quiet $SERVICE" \
  || { remote "journalctl -u $SERVICE -n 40 --no-pager"; die "Máy chủ không lên. Xem log ở trên."; }

say "Xong."
