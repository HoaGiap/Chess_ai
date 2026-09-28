"""Phòng chơi: ghế, quyền host, và nối sang ván của GameStore."""

import unittest

import chess

from chessai.web.games import GameStore
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

AL = "nguoi-a"
BL = "nguoi-b"
CC = "nguoi-c"


def bo() -> tuple[RoomStore, GameStore]:
    games = GameStore()
    return RoomStore(games), games


class TestGhe(unittest.TestCase):
    def test_tao_phong_thi_nguoi_tao_vao_ghe_trang_luon(self) -> None:
        """Người tạo phòng phải chơi được ngay. Nếu để ghế trống thì họ phải tự
        bấm "Vào", và một người lạ có thể ngồi ghế Trắng trước họ."""
        rooms, games = bo()
        rid = rooms.create(AL)
        view = rooms.view(rid, AL)
        self.assertEqual(view.white, AL)
        self.assertIsNone(view.black)
        self.assertEqual(view.host, AL)
        self.assertFalse(view.started)
        self.assertEqual(view.you, "white")
        self.assertEqual(view.status, "Chờ đối thủ")

    def test_nguoi_vao_sau_di_ghe_den(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        view = rooms.join(rid, BL)
        self.assertEqual(view.white, AL)
        self.assertEqual(view.black, BL)
        self.assertEqual(view.you, "black")

    def test_phong_day_hai_nguoi_thi_ba_nguoi_bi_tu_choi(self) -> None:
        """Review Focus 1: người thứ ba không được chen vào phòng."""
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
        view = rooms.join(rid, BL)
        self.assertEqual(view.white, AL)
        self.assertEqual(view.black, BL)
        self.assertEqual(view.you, "black")

    def test_roi_phong_thi_ghe_trong_lai(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        view = rooms.leave(rid, BL)
        self.assertIsNone(view.black)
        self.assertEqual(view.host, AL)

    def test_phong_khong_ton_tai(self) -> None:
        rooms, games = bo()
        with self.assertRaises(NotFound):
            rooms.view("khongco")

    def test_ma_phong_khong_de_ky_tu_nham(self) -> None:
        """Đọc to ra cho người khác thì dễ nhầm l/o/i/0/1."""
        rooms, games = bo()
        rid = rooms.create(AL)
        self.assertEqual(len(rid), 8)
        self.assertFalse(set(rid) & set("loi01"), rid)

    def test_ma_phong_khac_nhau(self) -> None:
        rooms, games = bo()
        self.assertEqual(len({rooms.create(AL) for _ in range(50)}), 50)


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
        """Review Focus 5: một mình bấm "Bắt đầu" thì vào ván với ghế trống."""
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

    def test_di_nuoc_thay_nguoi_khong_co_ghe_bi_tu_choi(self) -> None:
        """Review Focus 1: token lạ không được đi nước thay người đã vào."""
        rooms, rid = self._hai_nguoi()
        rooms.start(rid, AL)
        with self.assertRaises(NotInRoom):
            rooms.move(rid, CC, "e4")

    def test_di_nuoc_cho_khong_phai_luot_gi(self) -> None:
        """Review Focus 2: phải chặn theo GHẾ, không chỉ theo lượt."""
        rooms, rid = self._hai_nguoi()
        rooms.start(rid, AL)
        rooms.move(rid, AL, "e4")
        with self.assertRaises(NotYourTurn):
            rooms.move(rid, AL, "e5")
        rooms.move(rid, BL, "e5")
        self.assertEqual(
            rooms.games.snapshot(rooms.game_id_of(rid)).moves, ["e4", "e5"]
        )


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

    def test_phong_hoi_lai_thi_giu_dung_lich_su_cu(self) -> None:
        rooms, rid = self._hai_nguoi()
        rooms.move(rid, AL, "e4")
        view = rooms.rematch(rid, AL)
        self.assertFalse(view.started)
        self.assertEqual(
            rooms.games.snapshot(rooms.game_id_of(rid)).moves, []
        )

    def test_trang_thai_ket_noi(self) -> None:
        """`connected` = ĐANG CÓ WebSocket sống, không phải "đã vào phòng".

        Vào phòng bằng link mà WebSocket hỏng thì vẫn chơi được, nhưng người
        kia phải thấy cảnh báo mất kết nối — nên cờ này chỉ lớp WebSocket được
        bật.
        """
        rooms, rid = self._hai_nguoi()
        self.assertFalse(rooms.view(rid, AL).connected)   # chưa có WebSocket
        rooms.set_connected(rid, AL, True)
        self.assertTrue(rooms.view(rid, AL).connected)
        rooms.set_connected(rid, AL, False)
        self.assertFalse(rooms.view(rid, AL).connected)

    def test_biet_doi_thu_co_ngon_tai_khong(self) -> None:
        """`connected` là của chính người gọi; `opponent_connected` mới là của
        đối thủ — nhầm hai cái thì mất kết nối của nhau sẽ không bao giờ hiện."""
        rooms, rid = self._hai_nguoi()
        rooms.set_connected(rid, AL, True)
        rooms.set_connected(rid, BL, True)
        self.assertTrue(rooms.view(rid, AL).opponent_connected)
        rooms.set_connected(rid, BL, False)
        self.assertFalse(rooms.view(rid, AL).opponent_connected)
        # Người bị mất kết nối thì vẫn thấy đối thủ đang nối
        self.assertTrue(rooms.view(rid, BL).opponent_connected)
        # Người ngoài phòng thì không có ý kiến gì
        self.assertTrue(rooms.view(rid, CC).opponent_connected)


class TestDanhSach(unittest.TestCase):
    def test_danh_sach_co_phong_vua_tao(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        danh = rooms.list()
        self.assertEqual([v.id for v in danh], [rid])
        self.assertEqual(danh[0].status, "Sẵn sàng")

    def test_phong_day_hai_nguoi_thi_van_hien(self) -> None:
        """Phòng đã đủ hai người vẫn nên hiện — để biết đang bận."""
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        self.assertEqual(rooms.list()[0].status, "Sẵn sàng")

    def test_tran_so_phong_thi_phong_cu_bi_bo(self) -> None:
        games = GameStore()
        rooms = RoomStore(games, capacity=2)
        a = rooms.create(AL)
        b = rooms.create(AL)
        c = rooms.create(AL)
        with self.assertRaises(NotFound):
            rooms.view(a)
        rooms.view(c)

    def test_phong_co_se_lap_roi_van_chua_gi(self) -> None:
        rooms, games = bo()
        rid = rooms.create(AL)
        rooms.join(rid, BL)
        rooms.start(rid, AL)
        rooms.leave(rid, BL)
        self.assertFalse(rooms.view(rid, AL).started)
        self.assertEqual(rooms.view(rid, AL).status, "Chờ đối thủ")


if __name__ == "__main__":
    unittest.main()
