#!/usr/bin/env bash
# Cài Chess_ai lên máy ảo Ubuntu 24.04. Chạy MỘT LẦN, bằng root.
#
#   sudo bash deploy/install.sh
#
# Script này an toàn chạy lại nhiều lần: mỗi bước đều kiểm tra trước khi làm.
# Nó KHÔNG đụng tới thông tin Azure, không tự đăng ký tên miền, không cần mật
# khẩu nào của bạn.

set -euo pipefail

APP_DIR=/opt/chessai
APP_USER=chessai
SERVICE_FILE=/etc/systemd/system/chessai.service
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

say() { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }

if [[ $EUID -ne 0 ]]; then
  echo "Chạy bằng root: sudo bash $0" >&2
  exit 1
fi

# ---------------------------------------------------------------- swap
# Máy ảo của bạn chỉ có 1 GiB RAM. Ảnh Ubuntu trên cloud mặc định KHÔNG có
# swap, nên một đỗ dốt bộ nhớ là OOM-killer giết luôn máy chủ giữa ván.
# 1 GiB swap là biên an toàn rẻ.
say "Bảo đảm có swap (máy chỉ 1 GiB RAM, mặc định ảnh Ubuntu không có swap)"
if swapon --show=NAME --noheadings | grep -q .; then
  echo "   Đã có swap, bỏ qua."
else
  if [[ ! -f /swapfile ]]; then
    fallocate -l 1G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=1024
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
  fi
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "   Đã tạo và bật /swapfile (1 GiB)."
fi

# ------------------------------------------------------------- gói cài đặt
say "Cài gói cần thiết"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip rsync >/dev/null
echo "   Python: $(python3 --version)"

# ------------------------------------------------------------------ user
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  say "Tạo người dùng $APP_USER (không có quyền ghi, không có shell)"
  useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
else
  echo "   Người dùng $APP_USER đã tồn tại."
fi

# ------------------------------------------------------------------ code
say "Đặt mã nguồn vào $APP_DIR"
mkdir -p "$APP_DIR"
# Không đồng bộ .git, .venv, cache — chỉ cần mã nguồn chạy được.
rsync -a --delete \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
  --exclude '.superpowers' --exclude '*.pyc' \
  "$SOURCE_DIR/" "$APP_DIR/"

# ------------------------------------------------------------------ venv
say "Tạo môi trường ảo và cài thư viện"
# Ubuntu 24.04 chặn `pip install` vào hệ thống (PEP 668), nên BẮT BUỘC dùng venv.
# Nếu bỏ qua bước này thì pip sẽ báo lỗi "externally-managed-environment".
if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
  python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/python" -m pip install --quiet --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install --quiet -r "$APP_DIR/requirements.txt"
echo "   Đã cài: $("$APP_DIR/.venv/bin/python" -m pip list --format=freeze | wc -l) gói"

# -------------------------------------------------------------- systemd
say "Cài systemd service"
install -m 0644 "$SOURCE_DIR/deploy/chessai.service" "$SERVICE_FILE"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

systemctl daemon-reload
systemctl enable chessai >/dev/null
systemctl restart chessai

sleep 3
if systemctl is-active --quiet chessai; then
  echo "   Máy chủ đang chạy (systemctl status chessai)."
else
  warn "Máy chủ KHÔNG chạy. Xem: journalctl -u chessai -n 50"
  exit 1
fi

# ------------------------------------------------------------- kiểm tra
say "Kiểm tra từ trong máy"
LOCAL_IP="$(hostname -I | awk '{print $1}')"
if curl -fsS -o /dev/null "http://127.0.0.1/" 2>/dev/null; then
  echo "   http://127.0.0.1/  -> OK"
else
  warn "Không trả lời ở 127.0.0.1"
fi
if curl -fsS -o /dev/null "http://$LOCAL_IP/" 2>/dev/null; then
  echo "   http://$LOCAL_IP/ -> OK"
else
  warn "Không trả lời ở $LOCAL_IP — kiểm tra NSG của máy ảo (cần mở cổng 80)"
fi

cat <<'EOF'

----------------------------------------------------------------------
  Xong. Còn hai việc tay, làm trong Azure Portal:

  1. Mở cổng trong NSG (Network Security Group):
     Cổng TCP 80 (và 443 nếu muốn), nguồn 0.0.0.0/0.
     Azure ĐÃ có sẵn chứng thư ký cho tên
     chess-online-vn.japaneast.cloudapp.azure.com và tự chuyển
     tiếp cổng 443 của nó xuống cổng 80 của máy ảo — nên không cần
     cài chứng thư, không cần nginx.

  2. Thử:  https://chess-online-vn.japaneast.cloudapp.azure.com

  Lệnh thường dùng:
     sudo systemctl restart chessai      # khởi động lại
     sudo journalctl -u chessai -f        # xem log trực tiếp
     sudo systemctl status chessai

  Nhớ: phòng nằm trong RAM. `sudo systemctl restart chessai` sẽ xoá
  hết phòng và ván đang chơi.
----------------------------------------------------------------------
EOF
