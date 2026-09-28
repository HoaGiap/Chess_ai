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
    promotion: bool


class GameState(BaseModel):
    game_id: str
    fen: str
    turn: str
    legal: list[MoveOption]
    last_move: str | None
    last_from: str | None
    last_to: str | None
    check: bool
    over: bool
    result_text: str
    moves: list[str]
    captured_by_white: list[str]
    captured_by_black: list[str]
    can_undo: bool
