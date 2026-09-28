"""Route HTTP. Lớp này không chứa luật cờ vua — chỉ dịch lỗi sang mã HTTP."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..position import MoveError
from .games import GameNotFound, GameStore

# Không khai báo charset thì trình duyệt giải mã file theo locale, và byte
# tiếng Việt vỡ thành ký tự phá vỡ chuỗi -> SyntaxError ngay trong app.js.
# Cần thiết vì toàn bộ giao diện đều là tiếng Việt có dấu.
mimetypes.add_type("text/javascript; charset=utf-8", ".js")
mimetypes.add_type("text/css; charset=utf-8", ".css")
mimetypes.add_type("image/svg+xml; charset=utf-8", ".svg")

STATIC_DIR = Path(__file__).parent / "static"


class MoveRequest(BaseModel):
    san: str


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


def create_app(store: GameStore | None = None) -> FastAPI:
    app = FastAPI(title="Chess_ai web", docs_url=None, redoc_url=None)
    games = store if store is not None else GameStore()

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.post("/api/game")
    def create_game() -> JSONResponse:
        return _guard(games.snapshot, games.create(None))

    @app.get("/api/game/{game_id}")
    def read_game(game_id: str) -> JSONResponse:
        return _guard(games.snapshot, game_id)

    @app.post("/api/game/{game_id}/move")
    def move(game_id: str, payload: MoveRequest) -> JSONResponse:
        return _guard(games.submit, game_id, payload.san)

    @app.post("/api/game/{game_id}/undo")
    def undo(game_id: str) -> JSONResponse:
        return _guard(games.undo, game_id)

    @app.post("/api/game/{game_id}/new")
    def new_game(game_id: str) -> JSONResponse:
        return _guard(games.new_game, game_id)

    @app.get("/api/game/{game_id}/pgn")
    def pgn(game_id: str) -> JSONResponse:
        return _guard(lambda gid: {"pgn": games.pgn_text(gid)}, game_id)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
