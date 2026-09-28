"""REPL: phân tích lệnh rồi gọi Session."""

from __future__ import annotations

import argparse
import sys

import chess

from . import render
from .position import MoveError
from .session import Session

# Lệnh của #2. Ở #1 phải báo "chưa hỗ trợ" chứ không báo "không tồn tại",
# để không tạo cảm giác lỗi (spec §3.4).
COMING_SOON = frozenset(
    {"/hint", "/best", "/eval", "/analyze", "/puzzle", "/elo", "/style"}
)

_BANNER = (
    "Chess_ai — cờ vua theo luật FIDE. Gõ /help để xem lệnh, /quit để thoát."
)

_HELP = """Lệnh có sẵn:
  /board    Vẽ lại bàn cờ
  /fen      In FEN hiện tại
  /pgn      In chuỗi nước đi
  /undo     Lùi 1 lượt
  /resign   Đầu hàng
  /draw     Kết thúc ván hòa (chưa có đối thủ để đàm phán ở #1)
  /help     Xem danh sách này
  /quit     Thoát
Nước đi gõ kiểu SAN: e4, Nf3, O-O, exd5, e8=Q
Chế độ chơi:
  --both    Tự đi cả hai bên. Phiên bản #1 CHƯA CÓ AI, nên đây là cách
            chơi được duy nhất; mặc định (--side white) sẽ không ai đi hộ
            bạn nước đầu tiên."""


def _startup_note(human_color: chess.Color | None) -> str:
    """Cảnh báo khi ván không thể chơi được vì chưa có đối thủ."""
    if human_color is None:
        return ""
    return (
        "Lưu ý: #1 chưa có AI nên không ai đi hộ phe còn lại. "
        "Muốn chơi được, hãy khởi động lại với: python -m chessai.cli --both"
    )


def _force_utf8_stdout(stream) -> None:
    """Ép stdout ra UTF-8 để bàn cờ vẽ được trên console cp1252/cp437.

    Console Windows mặc định không mã hóa được ♔ và tiếng Việt có dấu.
    """
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError, AttributeError):
        pass


class Quit(Exception):
    """Người dùng yêu cầu thoát."""


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="chessai", description="Cờ vua theo luật FIDE, chơi trên terminal."
    )
    parser.add_argument("--side", choices=["white", "black"], default="white")
    parser.add_argument(
        "--both", action="store_true", help="Đi cả hai bên (chế độ thử nghiệm)"
    )
    parser.add_argument("--elo", type=int, default=1500)
    parser.add_argument("--style", default="karpov")
    parser.add_argument("--mode", default="coach")
    return parser.parse_args(argv)


def _build_session(args: argparse.Namespace) -> Session:
    if args.both:
        human: chess.Color | None = None
    else:
        human = chess.WHITE if args.side == "white" else chess.BLACK
    return Session(human_color=human, elo=args.elo, style=args.style, mode=args.mode)


def _perspective(session: Session) -> chess.Color:
    return session.human_color if session.human_color is not None else chess.WHITE


def _report(session: Session) -> str:
    """Báo cáo chuẩn sau mỗi lượt: bàn cờ, nước vừa đi, chuỗi nước đi, trạng thái."""
    lines = [render.render(session.position.board, _perspective(session))]
    last = session.last_move_label()
    if last:
        lines.append(f"Nước vừa đi: {last}")
    lines.append(f"Nước đi: {session.movetext()}")
    lines.append(session.status_line())
    if session.position.can_claim_fifty_moves() and not session.is_game_over():
        lines.append("Có thể đề nghị hòa theo luật 50 nước.")
    if session.is_game_over():
        lines.append(f"KẾT THÚC: {session.result_text()}")
    return "\n".join(lines)


def _cmd_board(session: Session, arg: str) -> str:
    return render.render(session.position.board, _perspective(session))


def _cmd_fen(session: Session, arg: str) -> str:
    return session.position.fen()


def _cmd_pgn(session: Session, arg: str) -> str:
    return session.movetext()


def _cmd_undo(session: Session, arg: str) -> str:
    if not session.undo_turn():
        return "Không có nước nào để lùi."
    return "Đã lùi 1 lượt."


def _cmd_resign(session: Session, arg: str) -> str:
    loser = session.human_color if session.human_color is not None else chess.WHITE
    session.resign(loser)
    return session.result_text()


def _cmd_draw(session: Session, arg: str) -> str:
    session.agree_draw()
    return session.result_text()


def _cmd_quit(session: Session, arg: str) -> str:
    raise Quit()


COMMANDS = {
    "/board": _cmd_board,
    "/fen": _cmd_fen,
    "/pgn": _cmd_pgn,
    "/undo": _cmd_undo,
    "/resign": _cmd_resign,
    "/draw": _cmd_draw,
    "/help": lambda s, a: _HELP,
    "/quit": _cmd_quit,
}


def _dispatch(session: Session, raw: str) -> str:
    """Xử lý một dòng người dùng gõ. Ném `MoveError` nếu nước đi sai."""
    if not raw.startswith("/"):
        session.apply_san(raw)
        return _report(session)
    name, _, arg = raw.partition(" ")
    if name in COMING_SOON:
        return f"Lệnh '{name}' chưa hỗ trợ ở phiên bản #1 (sẽ có ở #2)."
    handler = COMMANDS.get(name)
    if handler is None:
        return f"Không có lệnh '{name}'. Gõ /help để xem danh sách."
    return handler(session, arg.strip())


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout(sys.stdout)
    session = _build_session(_parse_args(argv))
    print(_BANNER)
    print(f"Chế độ {session.mode} · AI ELO {session.elo} ({session.style})")
    note = _startup_note(session.human_color)
    if note:
        print(f"\n⚠ {note}")
    print()
    print(_report(session))
    while True:
        try:
            raw = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not raw:
            continue
        try:
            print(_dispatch(session, raw))
        except Quit:
            return 0
        except MoveError as exc:
            print(f"Lỗi: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
