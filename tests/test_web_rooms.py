"""Route phòng: mã HTTP, thông điệp tiếng Việt, và rào chắn từ `/api/game/*`.

Gọi thẳng handler như các test #3A: máy không có `httpx` nên không dùng
TestClient, và `TestClient` cũng không nâng WebSocket.
"""

import json
import re
import unittest

from chessai.web.app import MoveRequest, create_app
from chessai.web.games import GameStore
from chessai.web.rooms import RoomStore

# Token thật dài 22 ký tự (secrets.token_urlsafe(16)). Máy chủ chặn token quá
# ngắn, nên token thử phải giống hệt thứ thật — dùng chuỗi "nguoi-a" thì 401.
AL = "nguoichoiAaaaaaaaaaaaaaaaaa"
BL = "nguoichoiBaaaaaaaaaaaaaaaaa"
CC = "nguoichoiCaaaaaaaaaaaaaaaaa"


def match_endpoint(application, method: str, path: str):
    """Tìm endpoint bằng cách so mẫu đường dẫn, và trả về tham số trong path."""
    for route in application.routes:
        template = getattr(route, "path", None)
        if template is None or method not in getattr(route, "methods", set()):
            continue
        escaped = re.escape(template)
        names = re.findall(r"\\\{([^}]+)\\\}", escaped)
        found = re.fullmatch(re.sub(r"\\\{[^}]+\\\}", "([^/]+)", escaped), path)
        if found:
            return route.endpoint, dict(zip(names, found.groups()))
    raise AssertionError(f"khong tim thay route {method} {path}")


class _FakeEngine:
    """Engine giả cho test route: trả SAN cố định, chặn được."""

    def __init__(self, *moves: str, blocks=None):
        self.moves = list(moves)
        self.blocks = list(blocks or [])

    def think(self, board, elo=1500, min_seconds=0.0):
        if self.blocks:
            self.blocks.pop(0).wait(timeout=5.0)
        wanted = self.moves.pop(0) if self.moves else None
        for move in board.legal_moves:
            if wanted and board.san(move) == wanted:
                return move
        return next(iter(board.legal_moves), None)


class TestPhong(unittest.TestCase):
    def setUp(self) -> None:
        self.games = GameStore()
        self.rooms = RoomStore(self.games)
        self.app = create_app(self.games, rooms=self.rooms)

    def call(self, method: str, path: str, token: str | None = None, **kw):
        endpoint, params = match_endpoint(self.app, method, path)
        if token is not None:
            kw["x_player"] = token
        return endpoint(**params, **kw)

    def body(self, response) -> dict:
        return json.loads(response.body)

    def di(self, room_id: str, token: str, san: str):
        """Endpoint nhận tham số `payload: MoveRequest`, không phải `san`."""
        return self.call(
            "POST", f"/api/rooms/{room_id}/move", token,
            payload=MoveRequest(san=san),
        )

    def tao_phong(self, host: str = AL) -> str:
        return self.body(self.call("POST", "/api/rooms", host))["room_id"]

    def hai_nguoi(self) -> str:
        rid = self.tao_phong()
        self.call("POST", f"/api/rooms/{rid}/join", BL)
        self.call("POST", f"/api/rooms/{rid}/start", AL)
        return rid

    # ---- danh tính ---------------------------------------------------

    def test_me_cap_ma_nguoi_hoi_dai(self) -> None:
        a = self.body(self.call("GET", "/api/me"))["player"]
        b = self.body(self.call("GET", "/api/me"))["player"]
        self.assertNotEqual(a, b)
        self.assertGreaterEqual(len(a), 20)

    def test_thieu_ma_nguoi_hoi_thi_401(self) -> None:
        response = self.call("POST", "/api/rooms")
        self.assertEqual(response.status_code, 401)
        self.assertIn("tải lại trang", self.body(response)["error"])

    def test_ma_nguoi_hoi_qua_ngan_bi_tu_choi(self) -> None:
        self.assertEqual(self.call("POST", "/api/rooms", "ngan").status_code, 401)

    # ---- vòng đời phòng ----------------------------------------------

    def test_tao_phong_thi_201_va_co_ma_dai_8(self) -> None:
        response = self.call("POST", "/api/rooms", AL)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(self.body(response)["room_id"]), 8)

    def test_danh_sach_phong(self) -> None:
        rid = self.tao_phong()
        self.call("POST", f"/api/rooms/{rid}/join", BL)
        danh = self.body(self.call("GET", "/api/rooms", AL))
        self.assertEqual([r["id"] for r in danh["rooms"]], [rid])
        self.assertEqual(danh["rooms"][0]["status"], "Sẵn sàng")

    def test_danh_sach_khong_ro_token(self) -> None:
        """Lỗi nghiêm trọng: API phát tán chính token người chơi thì mọi phân
        quyền sau đó đều vô nghĩa — lấy token từ danh sách là chơi thay được."""
        rid = self.tao_phong()
        self.call("POST", f"/api/rooms/{rid}/join", BL)
        cho_nguoi_la = json.dumps(self.body(self.call("GET", "/api/rooms", CC)))
        self.assertNotIn(AL, cho_nguoi_la)
        self.assertNotIn(BL, cho_nguoi_la)

    def test_view_phong_khong_ro_token(self) -> None:
        rid = self.hai_nguoi()
        du = json.dumps(self.body(self.call("GET", f"/api/rooms/{rid}", CC)))
        self.assertNotIn(AL, du)
        self.assertNotIn(BL, du)

    def test_phong_khong_ton_tai_thi_404(self) -> None:
        response = self.call("POST", "/api/rooms/khongco/join", BL)
        self.assertEqual(response.status_code, 404)
        self.assertIn("Phòng", self.body(response)["error"])

    def test_phong_day_thi_409(self) -> None:
        rid = self.tao_phong()
        self.call("POST", f"/api/rooms/{rid}/join", BL)
        response = self.call("POST", f"/api/rooms/{rid}/join", CC)
        self.assertEqual(response.status_code, 409)
        self.assertIn("đủ hai người", self.body(response)["error"])

    def test_bat_dau_khong_phai_host_thi_403(self) -> None:
        rid = self.tao_phong()
        self.call("POST", f"/api/rooms/{rid}/join", BL)
        self.assertEqual(
            self.call("POST", f"/api/rooms/{rid}/start", BL).status_code, 403
        )

    def test_bat_dau_thieu_nguoi_thi_400(self) -> None:
        rid = self.tao_phong()                # mới có mình host
        response = self.call("POST", f"/api/rooms/{rid}/start", AL)
        self.assertEqual(response.status_code, 400)
        self.assertIn("hai người", self.body(response)["error"])

    def test_view_phong_co_you_la_mau_cua_nguoi_goi(self) -> None:
        rid = self.hai_nguoi()
        self.assertEqual(
            self.body(self.call("GET", f"/api/rooms/{rid}", AL))["you"], "white"
        )
        self.assertEqual(
            self.body(self.call("GET", f"/api/rooms/{rid}", BL))["you"], "black"
        )

    def test_view_cho_nguoi_ngoai_phong_thi_khong_loi(self) -> None:
        rid = self.hai_nguoi()
        response = self.call("GET", f"/api/rooms/{rid}", CC)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.body(response)["you"])
        self.assertIs(self.body(response)["you_in_room"], False)

    # ---- chơi thật ---------------------------------------------------

    def test_di_nuoc_hop_le_thi_200(self) -> None:
        rid = self.hai_nguoi()
        response = self.di(rid, AL, "e4")
        self.assertEqual(response.status_code, 200)
        body = self.body(response)
        self.assertEqual(body["game"]["moves"], ["e4"])
        self.assertEqual(body["game"]["turn"], "black")
        self.assertEqual(body["room"]["id"], rid)

    def test_di_nuoc_sai_luot_thi_400_va_ban_khong_doi(self) -> None:
        rid = self.hai_nguoi()
        self.di(rid, AL, "e4")
        truoc = self.games.snapshot(self.rooms.game_id_of(rid)).fen
        response = self.di(rid, AL, "e5")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Chưa đến lượt bạn", self.body(response)["error"])
        self.assertEqual(self.games.snapshot(self.rooms.game_id_of(rid)).fen, truoc)

    def test_nguoi_la_thi_di_nuoc_bi_403(self) -> None:
        rid = self.hai_nguoi()
        self.assertEqual(self.di(rid, CC, "e4").status_code, 403)

    def test_di_nuoc_khi_chua_bat_dau_thi_400(self) -> None:
        rid = self.tao_phong()
        self.call("POST", f"/api/rooms/{rid}/join", BL)
        response = self.di(rid, AL, "e4")
        self.assertEqual(response.status_code, 400)
        self.assertIn("chưa bắt đầu", self.body(response)["error"])

    def test_phong_khong_cho_lui(self) -> None:
        """C4: trong phòng không có nút lùi nước."""
        rid = self.hai_nguoi()
        self.di(rid, AL, "e4")
        response = self.call("POST", f"/api/rooms/{rid}/undo", AL)
        self.assertEqual(response.status_code, 400)
        self.assertIn("không có nút lùi", self.body(response)["error"])

    def test_dau_hang_thi_ket_qua_dung(self) -> None:
        rid = self.hai_nguoi()
        self.di(rid, AL, "e4")
        response = self.call("POST", f"/api/rooms/{rid}/resign", AL)
        self.assertEqual(response.status_code, 200)
        body = self.body(response)
        self.assertTrue(body["game"]["over"])
        self.assertIn("Đen thắng", body["game"]["result_text"])
        self.assertTrue(body["room"]["finished"])

    def test_nguoi_la_thi_dau_hang_bi_403(self) -> None:
        rid = self.hai_nguoi()
        self.assertEqual(
            self.call("POST", f"/api/rooms/{rid}/resign", CC).status_code, 403
        )

    def test_di_nuoc_khi_van_xong_thi_400(self) -> None:
        rid = self.hai_nguoi()
        self.call("POST", f"/api/rooms/{rid}/resign", AL)
        response = self.di(rid, BL, "e5")
        self.assertEqual(response.status_code, 400)
        self.assertIn("đã kết thúc", self.body(response)["error"])

    def test_choi_lai_thi_xoa_lich_su(self) -> None:
        rid = self.hai_nguoi()
        self.di(rid, AL, "e4")
        response = self.call("POST", f"/api/rooms/{rid}/rematch", AL)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.body(response)["started"])
        self.assertEqual(
            self.games.snapshot(self.rooms.game_id_of(rid)).moves, []
        )

    def test_choi_lai_khong_phai_host_thi_403(self) -> None:
        rid = self.hai_nguoi()
        self.assertEqual(
            self.call("POST", f"/api/rooms/{rid}/rematch", BL).status_code, 403
        )

    def test_roi_phong_thi_ghe_trong(self) -> None:
        rid = self.hai_nguoi()
        response = self.call("POST", f"/api/rooms/{rid}/leave", BL)
        self.assertEqual(response.status_code, 200)
        self.assertIs(self.body(response)["seat_black"], False)

    def test_nguoi_nao_roi_thi_phai_co_ghe(self) -> None:
        rid = self.hai_nguoi()
        self.call("POST", f"/api/rooms/{rid}/leave", CC)
        view = self.body(self.call("GET", f"/api/rooms/{rid}", AL))
        self.assertIs(view["seat_black"], True)

    def test_dung_phong_khong_bi_tach(self) -> None:
        rid = self.hai_nguoi()
        self.assertIs(self.body(self.call("GET", f"/api/rooms/{rid}", AL))["you_in_room"],
                      True)

    # ---- rào chắn: /api/game/* không được đụng ván của phòng ----------

    def test_van_phong_bi_khoa_khoi_api_game(self) -> None:
        """`POST /api/game/{id}/*` không cần token, nên nếu ván phòng đi qua
        đó được thì ai cũng lùi/đi thay được — gọi `/api/game/{id}/state` để
        lấy `game_id` rồi thử từng lệnh."""
        rid = self.hai_nguoi()
        game_id = self.rooms.game_id_of(rid)
        self.di(rid, AL, "e4")
        truoc = self.games.snapshot(game_id).moves

        for duong in ("undo", "new"):
            with self.subTest(duong=duong):
                response = self.call("POST", f"/api/game/{game_id}/{duong}")
                self.assertNotEqual(
                    response.status_code, 200,
                    f"/api/game/{game_id}/{duong} van xoay được van phong",
                )
        response = self.call(
            "POST", f"/api/game/{game_id}/move", payload=MoveRequest(san="e5")
        )
        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(self.games.snapshot(game_id).moves, truoc)

    def test_api_game_ban_thuong_van_dung_duoc(self) -> None:
        """Rào chắn phải đủ hẹp: ván bình thường vẫn chơi như cũ."""
        game_id = self.body(self.call("POST", "/api/game"))["game_id"]
        response = self.call(
            "POST", f"/api/game/{game_id}/move", payload=MoveRequest(san="e4")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.body(response)["moves"], ["e4"])
        self.assertEqual(
            self.call("POST", f"/api/game/{game_id}/undo").status_code, 200
        )


class TestTrangThaiPhong(unittest.TestCase):
    def setUp(self) -> None:
        self.games = GameStore()
        self.rooms = RoomStore(self.games)
        self.app = create_app(self.games, rooms=self.rooms)

    def call(self, method: str, path: str, token: str | None = None, **kw):
        endpoint, params = match_endpoint(self.app, method, path)
        if token is not None:
            kw["x_player"] = token
        return endpoint(**params, **kw)

    def body(self, response) -> dict:
        return json.loads(response.body)

    def test_route_state_tra_va_ban_cho_du_phong_cho(self) -> None:
        """Dự phòng poll (C3) cần lấy được cả bàn cờ, không chỉ ghế.

        Không có route này thì WebSocket hỏng là bàn đứng yên vĩnh viễn.
        """
        rid = self.body(self.call("POST", "/api/rooms", AL))["room_id"]
        self.call("POST", f"/api/rooms/{rid}/join", BL)
        body = self.body(self.call("GET", f"/api/rooms/{rid}/state", AL))
        self.assertEqual(body["room"]["id"], rid)
        self.assertEqual(len(body["game"]["legal"]) > 0, True)
        self.assertEqual(body["game"]["moves"], [])

    def test_route_state_khong_ro_token(self) -> None:
        rid = self.body(self.call("POST", "/api/rooms", AL))["room_id"]
        self.call("POST", f"/api/rooms/{rid}/join", BL)
        self.assertNotIn(BL, json.dumps(
            self.body(self.call("GET", f"/api/rooms/{rid}/state", CC))
        ))

    def test_route_state_phong_hong_thi_404(self) -> None:
        rid = self.body(self.call("POST", "/api/rooms", AL))["room_id"]
        self.games.forget(self.rooms.game_id_of(rid))
        response = self.call("GET", f"/api/rooms/{rid}/state", AL)
        self.assertEqual(response.status_code, 404)


class TestKetThuan(unittest.TestCase):
    def setUp(self) -> None:
        self.games = GameStore()
        self.rooms = RoomStore(self.games)
        self.app = create_app(self.games, rooms=self.rooms)

    def call(self, method: str, path: str, token: str | None = None, **kw):
        endpoint, params = match_endpoint(self.app, method, path)
        if token is not None:
            kw["x_player"] = token
        return endpoint(**params, **kw)

    def body(self, response) -> dict:
        return json.loads(response.body)

    def test_ket_thuan_thi_van_ket_thuc(self) -> None:
        rid = self.body(self.call("POST", "/api/rooms", AL))["room_id"]
        self.call("POST", f"/api/rooms/{rid}/join", BL)
        self.call("POST", f"/api/rooms/{rid}/start", AL)
        self.call(
            "POST", f"/api/rooms/{rid}/move", AL, payload=MoveRequest(san="e4")
        )
        self.rooms.set_connected(rid, AL, True)
        self.rooms.set_connected(rid, BL, False)
        response = self.call("POST", f"/api/rooms/{rid}/forfeit", AL)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.body(response)["game"]["over"])

    def test_doi_thu_con_ket_noi_thi_khong_duoc_ket_thuan(self) -> None:
        rid = self.body(self.call("POST", "/api/rooms", AL))["room_id"]
        self.call("POST", f"/api/rooms/{rid}/join", BL)
        self.call("POST", f"/api/rooms/{rid}/start", AL)
        self.rooms.set_connected(rid, AL, True)
        self.rooms.set_connected(rid, BL, True)
        self.assertEqual(
            self.call("POST", f"/api/rooms/{rid}/forfeit", AL).status_code, 400
        )


class TestVanMoiBamAI(unittest.TestCase):
    """Phải `attach` (bật AI) TRƯỚC rồi mới chụp trạng thái.

    Chụp trước thì response mang `thinking: false`, trình duyệt thấy là ngừng
    hỏi lại — máy vẫn đi nước nhưng người chơi không bao giờ thấy, và bàn kẹt
    khoá.
    """

    def setUp(self) -> None:
        self.store = GameStore()
        self.chan = __import__("threading").Event()
        self.eng = _FakeEngine("e4", "e4", blocks=[self.chan, self.chan])
        from chessai.web.ai import AIController

        self.ai = AIController(self.store, engine=self.eng)
        self.app = create_app(self.store, self.ai, RoomStore(self.store))

    def _call(self, method: str, path: str, **kw):
        endpoint, params = match_endpoint(self.app, method, path)
        return endpoint(**params, **kw)

    def test_van_moi_ma_may_di_truoc_thi_phai_bao_nghi(self) -> None:
        gid = self.store.create(False)          # người chơi phe Đen
        self.ai.attach(gid)
        self.chan.set()
        self.chan.clear()
        state = json.loads(self._call("POST", f"/api/game/{gid}/new").body)
        self.assertTrue(
            state["thinking"],
            "response van bao thinking=false -> trinh duyet dung hoi lai",
        )
        self.assertEqual(state["moves"], [])

    def test_van_moi_ma_nguoi_di_truoc_thi_khong_bat_nghi(self) -> None:
        gid = self.store.create(True)           # người chơi phe Trắng
        self.ai.attach(gid)
        state = json.loads(self._call("POST", f"/api/game/{gid}/new").body)
        self.assertFalse(state["thinking"])


if __name__ == "__main__":
    unittest.main()
