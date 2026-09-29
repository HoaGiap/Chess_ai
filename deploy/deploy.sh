#!/usr/bin/env bash
# Đẩy code mới lên máy ảo và khởi động lại máy chủ.
#
#   bash deploy/deploy.sh <user>@<ip>
#   bash deploy/deploy.sh hoa@chess-online-vn.japaneast.cloudapp.azure.com
#
# Chạy trên máy CỦA BẠN (Windows/macOS/Linux đều được, cần có ssh/scp).
# Nếu tài khoản ssh của bạn dùng khoá, không cần nhập mật khẩu.
#
# CHÚ Ý: restart sẽ xoá hết phòng và ván đang chơi, vì mọi thứ nằm trong RAM.
# Chỉ deploy khi không ai đang đánh.

set -euo pipefail

TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  echo "Dùng: bash deploy/deploy.sh <user>@<ip>" >&2
  echo "Ví dụ: bash deploy/deploy.sh hoa@20.46.112.69" >&2
  exit 1
fi

APP_DIR=/opt/chessai
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

say "Kiểm tra kết nối tới $TARGET"
ssh -o ConnectTimeout=10 "$TARGET" 'true'

say "Chờ ai đang chơi hết rồi mới deploy"
# Không chặn người chơi, chỉ nhắc. Deploy giữa ván là việc của bạn quyết định.
ssh "$TARGET" "systemctl is-active --quiet chessai && echo 'Máy chủ đang chạy — restart sẽ xoá phòng.' || echo 'Máy chủ đang dừng.'"

say "Đẩy mã nguồn (rsync, chỉ file chạy được)"
# --delete để file đã xoá ở local cũng biến mất ở máy chủ.
# Không đụng .venv: cài thư viện riêng ở dưới.
ssh "$TARGET" "rsync -a --delete \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
  --exclude '.superpowers' --exclude '*.pyc' \
  '$SOURCE_DIR/' '$APP_DIR/'"

say "Cài lại thư viện nếu requirements.txt đổi"
ssh "$TARGET" "'$APP_DIR/.venv/bin/python' -m pip install --quiet -r '$APP_DIR/requirements.txt'"

say "Chạy thử toàn bộ test trên chính máy chủ đó"
ssh "$TARGET" "cd '$APP_DIR' && .venv/bin/python -m unittest 2>&1 | tail -3"

say "Khởi động lại máy chủ"
ssh "$TARGET" "chown -R chessai:chessai '$APP_DIR' && sudo systemctl restart chessai"
sleep 3
ssh "$TARGET" 'systemctl is-active --quiet chessai || { journalctl -u chessai -n 40; exit 1; }'

say "Xong. Thử:  https://chess-online-vn.japaneast.cloudapp.azure.com"
