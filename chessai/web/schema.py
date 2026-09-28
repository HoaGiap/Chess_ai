"""Khung dữ liệu gửi cho trình duyệt.

Đây là DTO, KHÔNG phải luật cờ vua. `MoveOption` mang sẵn ô nguồn và ô đích
để trình duyệt khớp với cú bấm chuột mà không phải tự phân tích SAN.
"""

from __future__ import annotations

from pydantic import BaseModel


class MoveOption(BaseModel):
    from_sq: str
    to_sq: str
    san: str
    capture: bool
    # "Q" | "R" | "B" | "N" | None — KHÔNG phải bool. Trình duyệt cần biết
    # phong cấp thành quân nào; đoán từ ký tự cuối của SAN sẽ hỏng vì SAN
    # phong cấp kèm chiếu có đuôi `+` (g8=Q+).
    promotion: str | None


class GameState(BaseModel):
    game_id: str
    fen: str
    turn: str
    legal: list[MoveOption]
    last_move: str | None
    last_from: str | None
    last_to: str | None
    check: bool
    # Ô vua đang bị chiếu, máy chủ tính sẵn — trình duyệt không tự suy ra,
    # vì "vua nào bị chiếu" là luật cờ vua chứ không phải trình bày.
    check_square: str | None
    over: bool
    result_text: str
    moves: list[str]
    captured_by_white: list[str]
    captured_by_black: list[str]
    can_undo: bool
