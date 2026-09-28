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
import re
import unittest

from chessai.web.app import MoveRequest, create_app
from chessai.web.games import GameStore


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


if __name__ == "__main__":
    unittest.main()
