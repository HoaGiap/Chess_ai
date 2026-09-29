"""Phòng chơi: ghế, quyền host, rò rỉ token, và nối sang ván của GameStore.

Token thử dài 22 ký tự như token thật (`secrets.token_urlsafe(16)`) — máy chủ
chặn token ngắn nên token "nguoi-a" sẽ bị 401 ở tầng route.
"""

import threading
import unittest

from chessai.web.games import GameNotFound, GameStore
from chessai.web.rooms import (
    Full,
    GameOver,
    NotEnough,
    NotFound,
    NotHost,
    NotInRoom,
    NotStarted,
    NotYourTurn,
    RoomStore,
)

AL = "nguoichoiAaaaaaaaaaaaaaaaaa"
BL = "nguoichoiBaaaaaaaaaaaaaaaaa"
CC = "nguoichoiCaaaaaaaaaaaaaaaaa"


def bo() -> tuple[RoomStore, GameStore]:
    games = GameStore()
    return RoomStore(games), games


class TestKhongRoToken(unittest.TestCase):
    """Token người chơi là BÍ MẬT. Ra khỏi máy chủ là mất bí mật đó.

    Đặc tả §5.1 nói `white`/`black` là "mã người chơi đã cắt bớt" — nghĩa là
    không gửi token. Gửi token thật thì bất kỳ ai cũng lấy được từ
    `GET /api/rooms` rồi chơi thay người đó.
    """

    def _hai_nguoi(self):
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        return rooms, rid

    def test_dict_phong_khong_chua_token(self) -> None:
        rooms, rid = self._hai_nguoi()
        du = rooms.view(rid, AL).as_dict()
        flat = repr(du)
        self.assertNotIn(AL, flat, "RoomView.as_dict() lộ token người chơi")
        self.assertNotIn(BL, flat, "RoomView.as_dict() lộ token người chơi")

    def test_danh_sach_khong_cha_token(self) -> None:
        """Người ngoài phòng cũng không được thấy token của ai cả."""
        rooms, rid = self._hai_nguoi()
        flat = repr([v.as_dict() for v in rooms.list(CC)])
        self.assertNotIn(AL, flat)
        self.assertNotIn(BL, flat)

    def test_chi_con_co_ghelam_bool(self) -> None:
        rooms, rid = self._hai_nguoi()
        du = rooms.view(rid, AL).as_dict()
        self.assertIs(du["seat_white"], True)
        self.assertIs(du["seat_black"], True)
        self.assertIs(du["host_is_you"], True)
        self.assertIs(du["you_in_room"], True)
        self.assertIs(rooms.view(rid, BL).as_dict()["host_is_you"], False)
        self.assertIs(rooms.view(rid, CC).as_dict()["you_in_room"], False)

    def test_ghelistrong_thi_ghetrong(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        du = rooms.view(rid, AL).as_dict()
        self.assertIs(du["seat_white"], True)
        self.assertIs(du["seat_black"], False)


class TestVanPhongDuocBaoVe(unittest.TestCase):
    """Ván của phòng KHÔNG được `/api/game/...` đụng tới.

    `POST /api/game/{id}/undo` không cần token, nên nếu không chặn thì ai cũng
    lùi được nước của đối thủ (vi phạm C4), và ai cũng đi thay được.
    """

    def test_van_phong_da_bao_ve(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        self.assertTrue(games.is_protected(rooms.game_id_of(rid)))

    def test_van_thuong_khong_bao_ve(self) -> None:
        games = GameStore()
        self.assertFalse(games.is_protected(games.create(None)))

    def test_tran_bo_nho_khong_cuat_van_phong(self) -> None:
        """Trần GameStore KHÔNG được cắt ván của phòng.

        Cắt mất thì mọi lệnh phòng ném `GameNotFound`, mà nó không phải
        `RoomError` — làm hỏng CẢ sảnh phòng, không chỉ phòng đó.
        """
        games = GameStore(capacity=2)
        rooms = RoomStore(games)
        rid = rooms.create(AL)
        game_id = rooms.game_id_of(rid)
        for _ in range(10):                     # dồn bộ nhớ vượt trần
            games.create(None)
        self.assertTrue(games.is_protected(game_id))
        rooms.join(rid, BL)
        rooms.start(rid, AL)
        rooms.move(rid, AL, "e4")                # vẫn chơi được sau khi đầy bộ nhớ
        self.assertEqual(rooms.games.snapshot(game_id).moves, ["e4"])

    def test_phong_bi_cut_thi_van_au(self) -> None:
        """Cắt ván phòng thì phải báo hỏng, không phải lỗi lung tung."""
        games = GameStore()
        rooms = RoomStore(games)
        rid = rooms.create(AL)
        games.forget(rooms.game_id_of(rid))      # ván biến mất
        with self.assertRaises(NotFound):
            rooms.view(rid, AL)

    def test_phong_hong_khong_lam_hong_ca_danh_sach(self) -> None:
        games = GameStore()
        rooms = RoomStore(games)
        tot = [rooms.create(AL) for _ in range(3)]
        games.forget(rooms.game_id_of(tot[1]))  # phòng giữa bị hỏng
        danh = [v.id for v in rooms.list()]
        self.assertNotIn(tot[1], danh)
        self.assertEqual(danh, [tot[0], tot[2]])


class TestGhe(unittest.TestCase):
    def test_tao_phong_thi_nguoi_tao_vao_ghe_trang_luon(self) -> None:
        """Người tạo phòng phải chơi được ngay. Nếu để ghế trống thì họ phải tự
        bấm "Vào", và một người lạ có thể ngồi ghế Trắng trước họ."""
        rooms, games = bo()
        rid = rooms.create(AL)
        view = rooms.view(rid, AL)
        self.assertEqual(view.you, "white")
        self.assertIs(view.seat_black, False)
        self.assertIs(view.host_is_you, True)
        self.assertEqual(rooms._rooms[rid].host, AL)
        self.assertFalse(view.started)
        self.assertEqual(view.status, "Chờ đối thủ")

    def test_nguoi_vao_sau_di_ghe_den(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        view = rooms.join(rid, BL)
        self.assertEqual(view.you, "black")
        self.assertIs(view.seat_white, True)
        self.assertIs(view.seat_black, True)
        # Token nằm trong `_Room`, KHÔNG nằm trong view.
        self.assertEqual(rooms._rooms[rid].black, BL)

    def test_phong_day_thi_ba_nguoi_bi_tu_choi(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        with self.assertRaises(Full):
            rooms.join(rid, CC)

    def test_vao_lai_phong_da_vao_thi_tra_ve_cho_cu(self) -> None:
        """Tải lại trang là việc bình thường, không được coi là lỗi."""
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        self.assertEqual(rooms.join(rid, BL).you, "black")

    def test_roi_phong_thi_ghe_trong_lai(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        self.assertIs(rooms.leave(rid, BL).seat_black, False)

    def test_phong_khong_ton_tai(self) -> None:
        rooms, games = bo()
        with self.assertRaises(NotFound):
            rooms.view("khongco")

    def test_ma_phong_khong_de_ky_tu_nham(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        self.assertEqual(len(rid), 8)
        self.assertFalse(set(rid) & set("loi01"), rid)

    def test_ma_phong_khac_nhau(self) -> None:
        rooms, games = bo()
        rooms.create_quota = 0            # tắt hạn mức: test này về tính duy nhất
        self.assertEqual(len({rooms.create(AL) for _ in range(50)}), 50)

    def test_tran_so_phong_thi_phong_cu_bi_bo(self) -> None:
        games = GameStore()
        rooms = RoomStore(games, capacity=2)
        a = rooms.create(AL)
        rooms.create(AL)
        rooms.create(AL)
        with self.assertRaises(NotFound):
            rooms.view(a)


class TestQuyen(unittest.TestCase):
    def _hai_nguoi(self):
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        return rooms, rid

    def test_khong_phai_host_thi_bam_bat_dau_bi_tu_choi(self) -> None:
        rooms, rid = self._hai_nguoi()
        with self.assertRaises(NotHost):
            rooms.start(rid, BL)

    def test_chua_du_hai_nguoi_thi_khong_bat_dau_duoc(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        with self.assertRaises(NotEnough):
            rooms.start(rid, AL)

    def test_host_bat_dau_duoc_khi_du_hai_nguoi(self) -> None:
        rooms, rid = self._hai_nguoi()
        view = rooms.start(rid, AL)
        self.assertTrue(view.started)
        self.assertEqual(view.status, "Đang đấu")

    def test_chua_bat_dau_thi_di_nuoc_bi_tu_choi(self) -> None:
        rooms, rid = self._hai_nguoi()
        with self.assertRaises(NotStarted):
            rooms.move(rid, AL, "e4")

    def test_dau_hang_luc_chua_bat_dau_thi_bi_tu_choi(self) -> None:
        """Không có chuyện "đầu hàng" với một ván chưa bắt đầu — và nếu cho phép
        thì ván thành xong vĩnh viễn, ai cũng xoá không được."""
        rooms, rid = self._hai_nguoi()
        with self.assertRaises(NotStarted):
            rooms.resign(rid, AL)

    def test_di_nuoc_thay_nguoi_khong_co_ghe_bi_tu_choi(self) -> None:
        rooms, rid = self._hai_nguoi()
        rooms.start(rid, AL)
        with self.assertRaises(NotInRoom):
            rooms.move(rid, CC, "e4")

    def test_di_nuoc_cho_khong_phai_luot_gi(self) -> None:
        rooms, rid = self._hai_nguoi()
        rooms.start(rid, AL)
        rooms.move(rid, AL, "e4")
        with self.assertRaises(NotYourTurn):
            rooms.move(rid, AL, "e5")
        rooms.move(rid, BL, "e5")
        self.assertEqual(
            rooms.games.snapshot(rooms.game_id_of(rid)).moves, ["e4", "e5"]
        )

    def test_host_roi_thi_quyen_chuyen_cho_nguoi_con_lai(self) -> None:
        """Host rời phải nhường quyền cho người còn lại, không thành ma.

        Nếu `host` rơi về chính token người vừa rời thì phòng không ai bấm
        "Bắt đầu" được nữa — treo vĩnh viễn.
        """
        rooms, rid = self._hai_nguoi()
        rooms.leave(rid, AL)                     # host rời, còn BL
        self.assertEqual(rooms._rooms[rid].host, BL)
        rooms.join(rid, AL)                      # AL ngồi lại ghế Trắng
        rooms.start(rid, BL)                     # và BL bấm "Bắt đầu" được

    def test_host_roi_khi_phong_trong_thi_nguoi_vao_se_thanh_host(self) -> None:
        rooms, rid = self._hai_nguoi()
        rooms.leave(rid, AL)
        rooms.leave(rid, BL)                     # phòng trống sạch
        self.assertIsNone(rooms._rooms[rid].host)
        rooms.join(rid, CC)
        self.assertEqual(rooms._rooms[rid].host, CC)
        rooms.join(rid, BL)
        rooms.start(rid, CC)                     # người vào sau thành host


class TestChoiThat(unittest.TestCase):
    def _hai_nguoi(self):
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        rooms.start(rid, AL)
        return rooms, rid

    def test_di_nuoc_hop_le_thi_vao_lich_su(self) -> None:
        rooms, rid = self._hai_nguoi()
        view, state = rooms.move(rid, AL, "e4")
        self.assertEqual(state.moves, ["e4"])
        self.assertEqual(state.turn, "black")

    def test_van_xong_thi_khong_di_duoc(self) -> None:
        rooms, rid = self._hai_nguoi()
        rooms.move(rid, AL, "f3")
        rooms.move(rid, BL, "e5")
        rooms.move(rid, AL, "g4")
        rooms.move(rid, BL, "Qh4#")
        with self.assertRaises(GameOver):
            rooms.move(rid, AL, "Nxf4")

    def test_dau_hang_thi_ket_qua_dung_nguoi(self) -> None:
        rooms, rid = self._hai_nguoi()
        view, state = rooms.resign(rid, BL)
        self.assertTrue(state.over)
        self.assertIn("Trắng thắng", state.result_text)
        self.assertTrue(view.finished)

    def test_phong_hoi_lai_thi_xoa_lich_su_cu(self) -> None:
        rooms, rid = self._hai_nguoi()
        rooms.move(rid, AL, "e4")
        view = rooms.rematch(rid, AL)
        self.assertFalse(view.started)
        self.assertEqual(rooms.games.snapshot(rooms.game_id_of(rid)).moves, [])

    def test_choi_lai_thi_van_van_duoc_bao_ve(self) -> None:
        rooms, rid = self._hai_nguoi()
        rooms.rematch(rid, AL)
        self.assertTrue(rooms.games.is_protected(rooms.game_id_of(rid)))

    def test_choi_lai_khong_phai_host_thi_bi_tu_choi(self) -> None:
        rooms, rid = self._hai_nguoi()
        with self.assertRaises(NotHost):
            rooms.rematch(rid, BL)


class TestMatKetNoi(unittest.TestCase):
    def _hai_nguoi(self):
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        rooms.start(rid, AL)
        return rooms, rid

    def test_connected_la_dang_co_websocket(self) -> None:
        """Vào phòng bằng link mà WebSocket hỏng thì vẫn chơi được, nhưng người
        kia phải thấy cảnh báo — nên cờ này chỉ lớp WebSocket được bật."""
        rooms, rid = self._hai_nguoi()
        self.assertFalse(rooms.view(rid, AL).connected)
        rooms.set_connected(rid, AL, True)
        self.assertTrue(rooms.view(rid, AL).connected)

    def test_biet_doi_thu_mat_ket_noi_khong(self) -> None:
        rooms, rid = self._hai_nguoi()
        rooms.set_connected(rid, AL, True)
        rooms.set_connected(rid, BL, True)
        self.assertTrue(rooms.view(rid, AL).opponent_connected)
        rooms.set_connected(rid, BL, False)
        self.assertFalse(rooms.view(rid, AL).opponent_connected)
        self.assertTrue(rooms.view(rid, BL).opponent_connected)
        self.assertTrue(rooms.view(rid, CC).opponent_connected)

    def test_cap_ket_noi_hoi_nguoi_khong_cua_phong(self) -> None:
        """Sau khi phòng bị cắt khỏi bộ nhớ thì `set_connected` phải im lặng."""
        games = GameStore()
        rooms = RoomStore(games, capacity=1)
        rid = rooms.create(AL)
        rooms.create(AL)                          # đẩy phòng đầu ra khỏi bộ nhớ
        rooms.set_connected(rid, AL, True)        # không được ném

    def test_nguoi_con_lai_duoc_ket_thuan_khi_doi_thu_mat_ket_noi(self) -> None:
        """C6: không để một người treo cả ván chỉ vì đóng tab."""
        rooms, rid = self._hai_nguoi()
        rooms.move(rid, AL, "e4")
        rooms.set_connected(rid, AL, True)
        rooms.set_connected(rid, BL, True)
        rooms.set_connected(rid, BL, False)
        view, state = rooms.forfeit(rid, AL)
        self.assertTrue(state.over)
        self.assertIn("Trắng thắng", state.result_text)

    def test_ket_thuan_khi_doi_thu_van_con_ket_noi_thi_bi_tu_choi(self) -> None:
        rooms, rid = self._hai_nguoi()
        rooms.set_connected(rid, AL, True)
        rooms.set_connected(rid, BL, True)
        with self.assertRaises(Exception):
            rooms.forfeit(rid, AL)

    def test_ket_thuan_khi_van_da_xong_thi_bi_tu_choi(self) -> None:
        rooms, rid = self._hai_nguoi()
        rooms.resign(rid, BL)
        with self.assertRaises(GameOver):
            rooms.forfeit(rid, AL)

    def test_nguoi_khong_co_ghe_thi_khong_ket_thuan_duoc(self) -> None:
        rooms, rid = self._hai_nguoi()
        with self.assertRaises(NotInRoom):
            rooms.forfeit(rid, CC)


class TestDanhSach(unittest.TestCase):
    def test_danh_sach_co_phong_vua_tao(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        danh = rooms.list()
        self.assertEqual([v.id for v in danh], [rid])
        self.assertEqual(danh[0].status, "Sẵn sàng")

    def test_phong_co_se_lap_roi_thi_van_chua_gi(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        rooms.start(rid, AL)
        self.assertFalse(rooms.leave(rid, BL).started)


class TestGioiHanTaoPhong(unittest.TestCase):
    """Không giới hạn tạo phòng thì một đứa tạo đủ số phòng là đẩy sạch
    phòng của người khác — trên máy local vô hại, trên Internet thì không."""

    def test_tao_qua_nhieu_phong_trong_mot_lan_thi_bi_tu_choi(self) -> None:
        rooms = RoomStore(GameStore(), capacity=1000, create_quota=5)
        for _ in range(rooms.create_quota):
            rooms.create(AL)
        with self.assertRaises(Exception):
            rooms.create(AL)

    def test_quota_reset_theo_thoi_gian(self) -> None:
        import time as _t
        rooms, _ = bo()
        rooms.create_quota = 2
        rooms.create_window = 0.3
        rooms.create(AL)
        rooms.create(AL)
        with self.assertRaises(Exception):
            rooms.create(AL)
        _t.sleep(0.35)
        rooms.create(AL)          # qua khoang thoi gian thi cho phep lai

    def test_quota_tinh_theo_nguoi_dung_khac_nhau(self) -> None:
        rooms, _ = bo()
        rooms.create_quota = 2
        rooms.create(AL)
        rooms.create(AL)
        rooms.create(BL)          # nguoi khac thi khong dung quota cua AL

    def test_van_co_dang_choi_khong_bi_day_ra_khi_don_phong(self) -> None:
        """Cấu trúc quan trọng hơn cả giới hạn: cắt phòng ĐANG CHƠI trước
        phòng chờ sẽ làm ván đang đấu biến mất chỉ vì ai đó mở nhiều tab."""
        games = GameStore()
        rooms = RoomStore(games, capacity=3)
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        rooms.start(rid, AL)
        rooms.move(rid, AL, "e4")               # van dang dau
        for _ in range(10):                     # don phong cho
            rooms.create(AL)
        self.assertTrue(rooms.view(rid, AL).you_in_room)
        self.assertEqual(rooms.games.snapshot(rooms.game_id_of(rid)).moves, ["e4"])


class TestKhoa(unittest.TestCase):
    """Hợp đồng khoá: `_notify` phải chạy SAU khi thả khoá phòng.

    `_notify` gọi người nghe, mà người nghe lại đọc trạng thái phòng (lấy
    khoá). Gọi lúc còn khoá là tự khoá lồng — treo cả máy chủ.
    """

    def test_notify_chay_ngoai_khoa(self) -> None:
        games = GameStore()
        rooms = RoomStore(games)
        rid = rooms.create(AL)
        trong_khoa: list[bool] = []

        def nghe() -> None:
            # Nếu đang trong khoa phòng thì `view` sẽ treo; ta kiểm tra bằng
            # cách thử lấy khoá không chặn.
            khoa = rooms._locks.get(rid)
            trong_khoa.append(khoa is not None and khoa.locked())

        rooms.add_listener(rid, nghe)
        rooms.join(rid, BL)
        rooms.start(rid, AL)
        rooms.move(rid, AL, "e4")
        # create() đã chạy trước khi gắn người nghe, nên chỉ 3 thao tác sau.
        self.assertEqual(len(trong_khoa), 3, "mỗi thao tác phải đẩy đúng một lần")
        self.assertFalse(any(trong_khoa), f"_notify gọi khi còn khoá: {trong_khoa}")

    def test_ngoai_phong_thi_nguoi_nghe_bi_go(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        loi = []

        def nghe() -> None:
            loi.append(1)

        rooms.add_listener(rid, nghe)
        rooms.remove_listener(rid, nghe)
        rooms.join(rid, BL)
        self.assertEqual(loi, [])

    def test_van_hong_thi_nguoi_nghe_hong_duoc_go(self) -> None:
        """Người nghe ném lỗi thì phải bị gỡ, không làm hỏng cả lượt đẩy sau."""
        rooms, games = bo()
        rid = rooms.create(AL)

        def hong() -> None:
            raise RuntimeError("socket chết")

        dem = []
        rooms.add_listener(rid, hong)
        rooms.add_listener(rid, lambda: dem.append(1))
        rooms.join(rid, BL)                      # lần 1: hong ném, vẫn phải tới
        self.assertEqual(dem, [1])
        rooms.start(rid, AL)                     # lần 2: hong đã bị gỡ
        self.assertEqual(dem, [1, 1])

    def test_da_du_vao_phong_thi_van_phai_duoc_da_khoa(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        xong = threading.Event()

        def doc() -> None:
            rooms.view(rid, AL)                 # lấy khoá phòng
            xong.set()

        t = threading.Thread(target=doc)
        t.start()
        self.assertTrue(xong.wait(timeout=2.0))


class TestVoiGameStore(unittest.TestCase):
    def test_van_phong_khong_co_ai_di(self) -> None:
        """`human_color=None` nên `AIController` không tự đi."""
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        rooms.start(rid, AL)
        self.assertFalse(games.snapshot(rooms.game_id_of(rid)).over)

    def test_snapshot_phong_hong_thi_nem_dung_loi(self) -> None:
        games = GameStore()
        rooms = RoomStore(games)
        rid = rooms.create(AL)
        games.forget(rooms.game_id_of(rid))
        with self.assertRaises(NotFound):
            rooms.state(rid, AL)


__all__ = ["GameNotFound"]
