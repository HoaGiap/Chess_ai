"""Ván đấu: lịch sử nước đi, PGN, lùi lượt, kết quả.

Ở #1 chưa có AI. `human_color=None` nghĩa là người chơi đi cả hai bên —
chế độ thử nghiệm để tự lái một ván trọn vẹn nhằm kiểm chứng luật.
#2 sẽ thay bằng người chơi thật, cắm vào `on_move`.
"""

from __future__ import annotations

from typing import Callable

import chess
import chess.pgn

from .position import MoveError, Position

Color = chess.Color


class Session:
    def __init__(
        self,
        human_color: Color | None,
        elo: int = 1500,
        style: str = "karpov",
        mode: str = "coach",
    ) -> None:
        self.position = Position()
        self.human_color = human_color
        self.elo = elo
        self.style = style
        self.mode = mode
        # Điểm móc cho #2: gán callback sau mỗi nước đi, nhận (SAN chuẩn, phe đã đi).
        # Ở #1 là None.
        self.on_move: Callable[[str, Color], None] | None = None
        # #3B: máy đang suy nghĩ. Cờ hiển thị, KHÔNG phải luật — nên đọc/ghi
        # không cần khoá ván.
        self.thinking = False
        # (người thắng hoặc None, lý do bằng tiếng Việt) khi kết thúc bằng tuyên bố.
        self._declared: tuple[Color | None, str] | None = None

    def restart(self) -> None:
        """Bắt đầu ván mới nhưng GIỮ nguyên `human_color`, `elo`, `style`,
        `mode` và `on_move`.

        Không được tạo `Session` mới thay chỗ: `on_move` là chỗ #3B cắm engine
        vào, mất nó thì bấm "Ván mới" sẽ âm thầm tắt AI.
        """
        self.position = Position()
        self._declared = None
        self.thinking = False

    def is_human_turn(self) -> bool:
        if self.human_color is None:
            return True
        if self.is_game_over():
            return False
        return self.position.side_to_move == self.human_color

    def is_game_over(self) -> bool:
        return self._declared is not None or self.position.is_game_over()

    def result_text(self) -> str:
        if self._declared is not None:
            return self._declared[1]
        return self.position.termination_text()

    def apply_san(self, san: str) -> None:
        if self.is_game_over():
            raise MoveError(f"Ván đã kết thúc: {self.result_text()}")
        if not self.is_human_turn():
            side = "Trắng" if self.position.side_to_move else "Đen"
            raise MoveError(
                f"Chưa đến lượt bạn — đang là lượt của {side}. "
                f"Muốn tự đi cả hai bên thì chạy với --both."
            )
        mover = self.position.side_to_move
        canonical = self.position.apply_san(san)
        if self.on_move is not None:
            try:
                self.on_move(canonical, mover)
            except Exception as exc:  # hook của #2 không được làm sập ván
                raise MoveError(f"Lỗi khi xử lý nước đi: {exc}") from exc

    def undo_turn(self) -> bool:
        """Lùi đúng một lượt. False nếu không đủ nước để lùi."""
        plies = 1 if self.human_color is None else 2
        if self.position.ply_count() < plies:
            return False
        for _ in range(plies):
            self.position.undo()
        self._declared = None
        return True

    def resign(self, by: Color) -> None:
        if self.is_game_over():
            return
        winner: Color = chess.WHITE if by == chess.BLACK else chess.BLACK
        loser = "Trắng" if by == chess.WHITE else "Đen"
        self._declared = (
            winner,
            f"{'Trắng' if winner else 'Đen'} thắng — {loser} đầu hàng",
        )

    def agree_draw(self) -> None:
        if self.is_game_over():
            return
        self._declared = (None, "HÒA: hai bên đồng ý hòa")

    def last_move_label(self) -> str | None:
        history = self.position.san_history()
        return history[-1] if history else None

    def pgn(self) -> str:
        """PGN đầy đủ kèm header và kết quả, dùng để lưu file."""
        game = chess.pgn.Game()
        game.headers["Result"] = self._pgn_result()
        node: chess.pgn.GameNode = game
        replay = chess.Board(self.position.root_fen)
        for san in self.position.san_history():
            move = replay.parse_san(san)
            replay.push(move)
            node = node.add_variation(move)
        return str(game)

    def _pgn_result(self) -> str:
        """Kết quả theo chuẩn PGN: '1-0', '0-1', '1/2-1/2' hoặc '*' nếu còn đi."""
        if self._declared is not None:
            winner = self._declared[0]
            if winner is None:
                return "1/2-1/2"
            return "1-0" if winner else "0-1"
        outcome = self.position.outcome()
        return "*" if outcome is None else outcome.result()

    def movetext(self) -> str:
        """Chỉ phần nước đi, bỏ header PGN và dấu `*` — dùng để in trong REPL."""
        text = self.pgn().partition("\n\n")[2].strip()
        if text.endswith("*"):
            text = text[:-1].strip()
        return text or "*"

    def status_line(self) -> str:
        return (
            f"Chế độ: {self.mode} | AI: ELO {self.elo} · {self.style} | "
            f"Bạn: {self._side_label()} | Đến lượt: {self._turn_label()}"
        )

    def _side_label(self) -> str:
        if self.human_color is None:
            return "cả hai bên"
        return "Trắng" if self.human_color else "Đen"

    def _turn_label(self) -> str:
        if self.is_game_over():
            return "ván đã xong"
        if self.human_color is None:
            who = "Trắng" if self.position.side_to_move else "Đen"
            return f"{who} (chế độ hai bên)"
        side = "Trắng" if self.position.side_to_move else "Đen"
        who = "bạn" if self.position.side_to_move == self.human_color else "AI"
        return f"{side} ({who})"
