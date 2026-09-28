"""Route HTTP. Lớp này không chứa luật cờ vua — chỉ dịch lỗi sang mã HTTP."""

from __future__ import annotations

import mimetypes
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Literal

from fastapi import FastAPI, Header, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..position import MoveError
from .ai import AIController
from .games import GameNotFound, GameStore
from .rooms import NoUndo, RoomError, RoomStore, Unauthorized

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
        result = action(*args)
        # Response đã dựng sẵn thì trả nguyên: jsonable_encoder trên một
        # JSONResponse sẽ khoá chính nó thành JSON lồng JSON.
        if isinstance(result, Response):
            return result
        # jsonable_encoder: GameState là model pydantic, JSONResponse tự nó
        # không khoá được.
        return JSONResponse(jsonable_encoder(result))
    except GameNotFound as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except RoomError as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status_code)
    except MoveError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


def create_app(
    store: GameStore | None = None,
    ai: AIController | None = None,
    rooms: RoomStore | None = None,
) -> FastAPI:
    games = store if store is not None else GameStore()
    controller = ai if ai is not None else AIController(games)
    phong = rooms if rooms is not None else RoomStore(games)

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


    # ---- #3C: phòng chơi người thật -------------------------------------

    def _token(x_player: str | None) -> str:
        return _token_of(x_player)

    @app.get("/api/me")
    def me() -> JSONResponse:
        return JSONResponse({"player": secrets.token_urlsafe(16)})

    @app.get("/api/rooms")
    def list_rooms(x_player: str | None = Header(default=None)) -> JSONResponse:
        return _guard(lambda: {"rooms": [v.as_dict() for v in phong.list(_token(x_player))]})

    @app.post("/api/rooms")
    def create_room(x_player: str | None = Header(default=None)) -> JSONResponse:
        # 201 đặt thẳng trong response chứ không đặt trên decorator: decorator
        # chỉ có tác dụng qua ASGI, còn test gọi thẳng hàm thì không thấy.
        return _guard(_tao_phong, phong, x_player)

    @app.get("/api/rooms/{room_id}")
    def read_room(
        room_id: str, x_player: str | None = Header(default=None)
    ) -> JSONResponse:
        return _guard(lambda: phong.view(room_id, _token(x_player)).as_dict())

    @app.post("/api/rooms/{room_id}/join")
    def join_room(
        room_id: str, x_player: str | None = Header(default=None)
    ) -> JSONResponse:
        return _guard(lambda: phong.join(room_id, _token(x_player)).as_dict())

    @app.post("/api/rooms/{room_id}/leave")
    def leave_room(
        room_id: str, x_player: str | None = Header(default=None)
    ) -> JSONResponse:
        return _guard(lambda: phong.leave(room_id, _token(x_player)).as_dict())

    @app.post("/api/rooms/{room_id}/start")
    def start_room(
        room_id: str, x_player: str | None = Header(default=None)
    ) -> JSONResponse:
        return _guard(lambda: phong.start(room_id, _token(x_player)).as_dict())

    @app.post("/api/rooms/{room_id}/rematch")
    def rematch_room(
        room_id: str, x_player: str | None = Header(default=None)
    ) -> JSONResponse:
        return _guard(lambda: phong.rematch(room_id, _token(x_player)).as_dict())

    @app.post("/api/rooms/{room_id}/move")
    def room_move(
        room_id: str,
        payload: MoveRequest,
        x_player: str | None = Header(default=None),
    ) -> JSONResponse:
        return _guard(_phong_move, phong, room_id, x_player, payload.san)

    @app.post("/api/rooms/{room_id}/resign")
    def room_resign(
        room_id: str, x_player: str | None = Header(default=None)
    ) -> JSONResponse:
        return _guard(_phong_resign, phong, room_id, x_player)

    @app.post("/api/rooms/{room_id}/undo")
    def room_undo(
        room_id: str, x_player: str | None = Header(default=None)
    ) -> JSONResponse:
        # C4: trong phòng không có nút lùi nước — lùi nước của đối thủ không
        # công bằng. Route vẫn tồn tại để nếu ai đó gọi thì trả lỗi rõ ràng
        # thay vì 404 khó hiểu.
        return _guard(_khong_cho_lui, x_player)

    @app.websocket("/ws/room/{room_id}")
    async def ws_room(websocket: WebSocket, room_id: str) -> None:
        """Chỉ ĐẨY trạng thái. Lệnh đi qua HTTP POST để luật cờ vua chỉ nằm ở
        một chỗ — mở đường ghi qua WebSocket là mở thêm một chỗ phải bảo vệ."""
        token = websocket.query_params.get("p") or ""
        if len(token) < 16:
            await websocket.close(code=1008)
            return
        try:
            phong.view(room_id, token)
        except RoomError:
            await websocket.close(code=1008)
            return

        await websocket.accept()
        phong.set_connected(room_id, token, True)

        async def day() -> None:
            await websocket.send_json(
                {"type": "state", "data": _room_state(phong, room_id, token)}
            )

        phong.add_listener(room_id, day)
        try:
            await day()
            while True:
                # Máy chủ KHÔNG nhận lệnh qua đây. Vòng lặp này chỉ để giữ
                # kết nối mở và phát hiện client đã đóng.
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            phong.remove_listener(room_id, day)
            phong.set_connected(room_id, token, False)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _khong_cho_lui(x_player: str | None) -> None:
    _token_of(x_player)
    raise NoUndo()


def _tao_phong(phong: RoomStore, x_player: str | None) -> JSONResponse:
    return JSONResponse({"room_id": phong.create(_token_of(x_player))}, status_code=201)


def _phong_move(phong, room_id: str, x_player: str | None, san: str) -> dict:
    view, state = phong.move(room_id, _token_of(x_player), san)
    return {"room": view.as_dict(), "game": state.model_dump()}


def _phong_resign(phong, room_id: str, x_player: str | None) -> dict:
    view, state = phong.resign(room_id, _token_of(x_player))
    return {"room": view.as_dict(), "game": state.model_dump()}


def _token_of(x_player) -> str:
    """Kiểm mã người chơi ở tầng module, để hàm ngoài `create_app` dùng được.

    `isinstance` là bắt buộc: test gọi thẳng hàm (không qua ASGI) thì mặc định
    `Header(default=None)` là MỘT ĐỐI TƯỢNG `Header`, không phải None.
    """
    if not isinstance(x_player, str) or len(x_player) < 16:
        raise Unauthorized()
    return x_player


def _room_state(phong: RoomStore, room_id: str, token: str) -> dict:
    room = phong.view(room_id, token)
    out = {"room": room.as_dict(), "game": None}
    if room.started:
        out["game"] = phong.games.snapshot(phong.game_id_of(room_id)).model_dump()
    return out


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
