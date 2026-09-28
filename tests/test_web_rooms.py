"""Route phòng: mã HTTP và thông điệp tiếng Việt.

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
        response = self.call("POST", "/api/rooms", "ngan")
        self.assertEqual(response.status_code, 401)

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
        response = self.call("POST", f"/api/rooms/{rid}/start", BL)
        self.assertEqual(response.status_code, 403)

    def test_bat_dau_thieu_nguoi_thi_400(self) -> None:
        rid = self.tao_phong()
        self.call("POST", f"/api/rooms/{rid}/leave", AL)   # bỏ ghế host
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
        self.assertEqual(
            self.games.snapshot(self.rooms.game_id_of(rid)).fen, truoc
        )

    def test_nguoi_la_thi_di_nuoc_bi_403(self) -> None:
        """Review Focus 1: token lạ không được đi nước thay người đã vào."""
        rid = self.hai_nguoi()
        response = self.di(rid, CC, "e4")
        self.assertEqual(response.status_code, 403)

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
        self.assertIsNone(self.body(response)["black"])

    def test_nguoi_nao_roi_thi_phai_co_ghe(self) -> None:
        rid = self.hai_nguoi()
        self.call("POST", f"/api/rooms/{rid}/leave", CC)
        self.assertEqual(self.body(self.call("GET", f"/api/rooms/{rid}", AL))["black"], BL)


if __name__ == "__main__":
    unittest.main()
