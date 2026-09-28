"""Route HTTP. Lớp này không chứa luật cờ vua — chỉ dịch lỗi sang mã HTTP."""

from __future__ import annotations

import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Literal

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..position import MoveError
from .ai import AIController
from .games import GameNotFound, GameStore

# Ghi charset UTF-8 tường minh cho file tĩnh. `mimetypes` mặc định trả
# "application/javascript" không charset; dù module script theo HTML spec vẫn
# luôn là UTF-8, nói rõ ra thì không còn phụ thuộc trình duyệt đoán, và file .css
# (không phải module) thì cần.
mimetypes.add_type("text/javascript; charset=utf-8", ".js")
mimetypes.add_type("text/css; charset=utf-8", ".css")
mimetypes.add_type("image/svg+xml; charset=utf-8", ".svg")

STATIC_DIR = Path(__file__).parent / "static"


class MoveRequest(BaseModel):
    san: str


class NewGameRequest(BaseModel):
    human_color: Literal["white", "black", None] = None
    elo: int = 1500


def _guard(action, *args) -> JSONResponse:
    """Chạy một thao tác GameStore rồi dịch lỗi thành mã HTTP.

    Cố ý bắt lỗi trong thân handler thay vì dùng `exception_handler` của
    FastAPI: handler chỉ chạy qua ASGI stack, còn test gọi thẳng hàm. Dùng
    `exception_handler` sẽ khiến test im lặng bỏ qua mọi nhánh lỗi.
    """
    try:
        # jsonable_encoder: GameState là model pydantic, JSONResponse tự nó
        # không khoá được.
        return JSONResponse(jsonable_encoder(action(*args)))
    except GameNotFound as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except MoveError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


def create_app(store: GameStore | None = None, ai: AIController | None = None) -> FastAPI:
    games = store if store is not None else GameStore()
    controller = ai if ai is not None else AIController(games)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        controller.shutdown()

    app = FastAPI(
        title="Chess_ai web", docs_url=None, redoc_url=None, lifespan=lifespan
    )

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.post("/api/game")
    def create_game(payload: NewGameRequest | None = None) -> JSONResponse:
        data = payload if payload is not None else NewGameRequest()
        color = None if data.human_color is None else (data.human_color == "white")
        game_id = games.create(color, elo=max(600, min(2400, data.elo)))
        controller.attach(game_id)
        return _guard(games.snapshot, game_id)

    @app.get("/api/game/{game_id}")
    def read_game(game_id: str) -> JSONResponse:
        return _guard(games.snapshot, game_id)

    @app.post("/api/game/{game_id}/move")
    def move(game_id: str, payload: MoveRequest) -> JSONResponse:
        return _guard(games.submit, game_id, payload.san)

    @app.post("/api/game/{game_id}/undo")
    def undo(game_id: str) -> JSONResponse:
        # Hủy trước: nếu AI đang nghĩ, kết quả của nó đã lỗi thời.
        controller.cancel(game_id)
        return _guard(games.undo, game_id)

    @app.post("/api/game/{game_id}/new")
    def new_game(game_id: str) -> JSONResponse:
        controller.cancel(game_id)
        return _guard(_van_moi_va_bat_dau_ai, games, controller, game_id)

    @app.get("/api/game/{game_id}/pgn")
    def pgn(game_id: str) -> JSONResponse:
        return _guard(lambda gid: {"pgn": games.pgn_text(gid)}, game_id)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _van_moi_va_bat_dau_ai(games: GameStore, ai: AIController, game_id: str) -> dict:
    """Bắt đầu ván mới, rồi bảo máy đi nếu đã tới lượt nó.

    `Session.restart()` không bắn `on_move`, nên không ai bảo máy đi nếu ván mới
    mà máy đi trước (người chơi chọn phe Đen) — bàn sẽ khoá vĩnh viễn.

    Thứ tự rất quan trọng: phải `attach` TRƯỚC rồi mới chụp trạng thái. Chụp
    trước thì response mang `thinking: false`, trình duyệt thấy vậy là ngừng
    hỏi lại — máy vẫn đi nước nhưng người chơi không bao giờ thấy.
    """
    games.new_game(game_id)
    ai.attach(game_id)
    return games.snapshot(game_id).model_dump()


app = create_app()
