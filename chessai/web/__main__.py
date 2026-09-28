"""Chạy máy chủ: python -m chessai.web [--port 8000] [--host 127.0.0.1]"""

from __future__ import annotations

import argparse

import uvicorn


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
    uvicorn.run("chessai.web.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
