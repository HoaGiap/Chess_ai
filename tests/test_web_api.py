"""Route được gọi trực tiếp: máy không có httpx nên không dùng TestClient.

Hai điều cần biết khi test kiểu này:

1. Handler là hàm `def` đồng bộ, không phải coroutine. FastAPI chạy chúng trong
   threadpool — cần vậy để #3B thêm search chặn mà không treo event loop. Vì
   vậy test gọi thẳng, KHÔNG bọc `asyncio.run`.
2. `match_endpoint` tìm endpoint bằng cách so mẫu đường dẫn — `app.routes`
   lưu đường dẫn CÓ template (`/api/game/{game_id}/move`) còn test gọi bằng
   id thật, nên không thể tra cứu bằng tên thuộc tính. Hàm còn phải trả về
   các tham số trong đường dẫn để truyền vào handler.
"""

import json
import mimetypes
import re
import unittest

from chessai.web.app import STATIC_DIR, MoveRequest, NewGameRequest, create_app
from chessai.web.games import GameStore
from chessai.web.schema import GameState, MoveOption


def match_endpoint(application, method: str, path: str):
    for route in application.routes:
        template = getattr(route, "path", None)
        if template is None or method not in getattr(route, "methods", set()):
            continue
        escaped = re.escape(template)
        names = re.findall(r"\\\{([^}]+)\\}", escaped)
        pattern = re.sub(r"\\\{[^}]+\\\}", "([^/]+)", escaped)
        found = re.fullmatch(pattern, path)
        if found:
            return route.endpoint, dict(zip(names, found.groups()))
    raise AssertionError(f"không tìm thấy route {method} {path}")


class ApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(GameStore())

    def call(self, method: str, path: str, **kwargs):
        endpoint, params = match_endpoint(self.app, method, path)
        return endpoint(**params, **kwargs)

    def move_san(self, game_id: str, san: str):
        return self.post(f"/api/game/{game_id}/move", payload=MoveRequest(san=san))

    def get(self, path: str, **kwargs):
        return self.call("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self.call("POST", path, **kwargs)

    def body(self, response) -> dict:
        return json.loads(response.body)

    def new_game(self) -> str:
        return self.body(self.post("/api/game"))["game_id"]


class TestCreateGame(ApiTestCase):
    def test_create_returns_200_and_starting_state(self) -> None:
        response = self.post("/api/game")
        self.assertEqual(response.status_code, 200)
        state = self.body(response)
        self.assertEqual(
            state["fen"], "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        )
        self.assertEqual(len(state["legal"]), 20)
        self.assertEqual(len(state["game_id"]), 12)

    def test_two_games_get_different_ids(self) -> None:
        self.assertNotEqual(self.new_game(), self.new_game())


class TestMove(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.gid = self.new_game()

    def test_valid_move_returns_200(self) -> None:
        response = self.move_san(self.gid, "e4")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.body(response)["moves"], ["e4"])

    def test_illegal_move_returns_400_with_vietnamese_text(self) -> None:
        response = self.move_san(self.gid, "e5")
        self.assertEqual(response.status_code, 400)
        message = self.body(response)["error"]
        self.assertIn("không hợp lệ", message)
        self.assertNotIn("illegal san", message)
        self.assertNotIn("/", message)

    def test_illegal_move_does_not_change_position(self) -> None:
        before = self.body(self.get(f"/api/game/{self.gid}"))["fen"]
        self.move_san(self.gid, "e5")
        self.assertEqual(self.body(self.get(f"/api/game/{self.gid}"))["fen"], before)

    def test_state_is_stable_across_reads(self) -> None:
        self.move_san(self.gid, "e4")
        self.assertEqual(
            self.body(self.get(f"/api/game/{self.gid}")),
            self.body(self.get(f"/api/game/{self.gid}")),
        )

    def test_unknown_id_move_returns_404(self) -> None:
        self.assertEqual(
            self.move_san("khongco", "e4").status_code, 404
        )


class TestUndoAndNew(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.gid = self.new_game()

    def test_undo_returns_200_and_reverts(self) -> None:
        start = self.body(self.get(f"/api/game/{self.gid}"))["fen"]
        self.move_san(self.gid, "e4")
        response = self.post(f"/api/game/{self.gid}/undo")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.body(response)["fen"], start)

    def test_undo_on_new_game_returns_400(self) -> None:
        self.assertEqual(self.post(f"/api/game/{self.gid}/undo").status_code, 400)

    def test_new_game_keeps_id(self) -> None:
        self.move_san(self.gid, "e4")
        state = self.body(self.post(f"/api/game/{self.gid}/new"))
        self.assertEqual(state["game_id"], self.gid)
        self.assertEqual(state["moves"], [])


class TestMissingGame(ApiTestCase):
    def test_unknown_id_returns_404(self) -> None:
        self.assertEqual(self.get("/api/game/khongco").status_code, 404)

    def test_404_message_is_actionable(self) -> None:
        message = self.body(self.get("/api/game/khongco"))["error"]
        self.assertIn("Ván", message)
        self.assertIn("Ván mới", message)


class TestPgn(ApiTestCase):
    def test_pgn_after_move_contains_movetext(self) -> None:
        gid = self.new_game()
        self.move_san(gid, "e4")
        text = self.body(self.get(f"/api/game/{gid}/pgn"))["pgn"]
        self.assertIn("1. e4", text)

    def test_pgn_of_unknown_id_returns_404(self) -> None:
        self.assertEqual(self.get("/api/game/khongco/pgn").status_code, 404)


class TestStaticContentType(unittest.TestCase):
    """Thiếu charset thì trình duyệt giải mã sai và app.js chết vì SyntaxError."""

    def test_javascript_declares_utf8(self) -> None:
        self.assertIn("charset=utf-8", mimetypes.guess_type("app.js")[0])

    def test_css_declares_utf8(self) -> None:
        self.assertIn("charset=utf-8", mimetypes.guess_type("style.css")[0])

    def test_svg_declares_utf8(self) -> None:
        self.assertIn("charset=utf-8", mimetypes.guess_type("wK.svg")[0])

    def test_index_html_declares_utf8(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn('<meta charset="utf-8">', html)

    def test_app_js_is_loaded_as_a_module(self) -> None:
        """app.js dùng top-level await nên phải nạp bằng type="module",
        nếu không trình duyệt ném SyntaxError và trang trắng."""
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn('type="module"', html)
        self.assertNotIn('<script src="/static/app.js">', html)

    def test_app_js_really_uses_top_level_await(self) -> None:
        """Nếu sau này bỏ top-level await thì xoá luôn type="module" ở test trên."""
        script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        # assertRegex nhận (text, regex, msg) — cờ phải nằm trong chính regex,
        # truyền re.MULTILINE vào tham số thứ ba chỉ là đổi thông điệp.
        self.assertRegex(script, re.compile(r"^\s*apply\(await ", re.MULTILINE))


class TestOpenApiContract(unittest.TestCase):
    """Review: `match_endpoint` gọi thẳng handler, bỏ qua định tuyến và parse
    body — nên đổi đường dẫn hay đổi tên field trong pydantic thì 20 test vẫn
    xanh còn app thật thì hỏng. Ở đây khoá đúng bằng hợp đồng OpenAPI.
    """

    def setUp(self) -> None:
        self.paths = create_app(GameStore()).openapi()["paths"]

    def _operations(self, path: str) -> set[str]:
        return set(self.paths[path])

    def test_every_route_the_client_uses_exists(self) -> None:
        for path in (
            "/",
            "/api/game",
            "/api/game/{game_id}",
            "/api/game/{game_id}/move",
            "/api/game/{game_id}/undo",
            "/api/game/{game_id}/new",
            "/api/game/{game_id}/pgn",
        ):
            with self.subTest(path=path):
                self.assertIn(path, self.paths)

    def test_create_and_read_use_the_right_methods(self) -> None:
        self.assertEqual(self._operations("/api/game"), {"post"})
        self.assertEqual(self._operations("/api/game/{game_id}"), {"get"})
        self.assertEqual(self._operations("/api/game/{game_id}/pgn"), {"get"})

    def test_actions_use_post(self) -> None:
        for path in ("move", "undo", "new"):
            with self.subTest(path=path):
                self.assertEqual(
                    self._operations(f"/api/game/{{game_id}}/{path}"), {"post"}
                )

    def test_move_body_is_validated_from_a_plain_dict(self) -> None:
        """Không dựng MoveRequest trong test — để nó phải đi qua pydantic thật."""
        request = MoveRequest.model_validate({"san": "e4"})
        self.assertEqual(request.san, "e4")
        with self.assertRaises(Exception):
            MoveRequest.model_validate({"buoc_di": "e4"})

    def test_promotion_and_check_square_reach_the_wire(self) -> None:
        """Tên field phải khớp thứ app.js đọc."""
        for name in ("check_square", "legal", "check", "over", "last_from", "last_to"):
            with self.subTest(model="GameState", field=name):
                self.assertIn(name, GameState.model_fields)
        for name in ("from_sq", "to_sq", "san", "capture", "promotion"):
            with self.subTest(model="MoveOption", field=name):
                self.assertIn(name, MoveOption.model_fields)


if __name__ == "__main__":
    unittest.main()
