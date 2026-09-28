"""Chạy máy chủ: python -m chessai.web [--port 8000] [--host 127.0.0.1]"""

from __future__ import annotations

import argparse

import uvicorn

_CANH_BAO = """
LƯU Ý — phòng chơi nằm trong bộ nhớ máy chủ:
  - Tắt máy chủ là mất hết phòng và ván đang chơi.
  - CHỈ chạy được trong MỘT tiến trình. Nếu bạn tự chạy
    `uvicorn chessai.web.app:app --workers 2` thì hai người ở
    hai tiến trình khác nhau sẽ không thấy nhau.
  - Không có đăng nhập: ai có mã người chơi của người khác thì
    vào được phòng của họ. Mã đó nằm trong query string của
    WebSocket nên xuất hiện trong log máy chủ.
Muốn chạy thật sự nhiều người thì cần chuyển sang SQLite hoặc
PostgreSQL — xem README.md.
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="chessai.web", description="Chơi cờ vua trên trình duyệt."
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--host", default="127.0.0.1", help="0.0.0.0 để máy khác cùng mạng vào"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    # In trước khi uvicorn chiếm màn hình, để biết địa chỉ ngay cả khi log bị trộn.
    print(f"Chess_ai: http://{args.host}:{args.port}")
    print(_CANH_BAO)
    uvicorn.run("chessai.web.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
