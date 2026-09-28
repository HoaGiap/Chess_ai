"""Engine tự viết: bảng điểm vị trí + hàm đánh giá thế cờ."""

import unittest

import chess

from chessai import engine


class TestMaterial(unittest.TestCase):
    def test_trang_them_mot_tot_thi_diem_duong(self) -> None:
        board = chess.Board("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")   # Q vs trống, trắng đi
        self.assertGreater(engine.evaluate(board), 0)

    def test_quan_hon_luon_duoc_diem_duong(self) -> None:
        for fen in (
            "4k3/8/8/8/8/8/8/P3K3 w - - 0 1",
            "4k3/8/8/8/8/8/8/N3K3 w - - 0 1",
            "4k3/8/8/8/8/8/8/B3K3 w - - 0 1",
            "4k3/8/8/8/8/8/8/R3K3 w - - 0 1",
            "4k3/8/8/8/8/8/8/Q3K3 w - - 0 1",
        ):
            with self.subTest(fen=fen):
                self.assertGreater(engine.evaluate(chess.Board(fen)), 0)

    def test_quan_hon_hon_thi_diem_am(self) -> None:
        board = chess.Board("4k3/8/8/8/8/8/8/3qK3 w - - 0 1")   # hậu đen, trắng đi
        self.assertLess(engine.evaluate(board), 0)

    def test_gia_tri_dung_thu_tu(self) -> None:
        self.assertLess(engine.VALUES[chess.PAWN], engine.VALUES[chess.KNIGHT])
        self.assertLess(engine.VALUES[chess.KNIGHT], engine.VALUES[chess.BISHOP])
        self.assertLess(engine.VALUES[chess.BISHOP], engine.VALUES[chess.ROOK])
        self.assertLess(engine.VALUES[chess.ROOK], engine.VALUES[chess.QUEEN])


class TestSymmetry(unittest.TestCase):
    def test_doi_phe_thi_diem_doi_dau(self) -> None:
        """Bảng điểm lệch phe sẽ hỏng im lặng và engine sẽ chơi yếu ở một màu."""
        for fen in (
            chess.STARTING_FEN,
            "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
            "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2",
        ):
            with self.subTest(fen=fen):
                white = chess.Board(fen)
                black = chess.Board(fen)
                black.turn = chess.BLACK
                self.assertEqual(
                    engine.evaluate(white), -engine.evaluate(black), fen
                )


class TestPositionTables(unittest.TestCase):
    def test_bang_vi_tri_dung_64_o(self) -> None:
        for ten, bang in engine.PST.items():
            with self.subTest(bang=ten):
                self.assertEqual(len(bang), 64, ten)
                self.assertTrue(all(isinstance(x, int) for x in bang))

    def test_quan_di_dung_o_dich_duoc_thuong(self) -> None:
        """Đưa xe từ h1 lên h8 phải tăng điểm — bảng vị trí có thật sự được dùng."""
        board = chess.Board()
        board.set_piece_at(chess.H1, chess.Piece(chess.ROOK, chess.WHITE))
        thuong = engine.evaluate(board)

        moved = chess.Board()
        moved.set_piece_at(chess.H8, chess.Piece(chess.ROOK, chess.WHITE))
        self.assertGreater(engine.evaluate(moved), thuong)

    def test_tot_tien_len_ban_duoc_thuong(self) -> None:
        o_ha = chess.Board("4k3/8/8/8/8/8/2P5/4K3 w - - 0 1")
        giua = chess.Board("4k3/8/2P5/8/8/8/8/4K3 w - - 0 1")
        self.assertGreater(engine.evaluate(giua), engine.evaluate(o_ha))

    def test_vua_nguy_hiem_khi_di_xa(self) -> None:
        """Vua ở giữa bàn lộ trộn hơn vua trong góc — nếu bảng bị đảo dấu thì hỏng."""
        o_goc = engine.piece_square(chess.KING, chess.WHITE, chess.E1)
        o_giua = engine.piece_square(chess.KING, chess.WHITE, chess.E4)
        self.assertGreater(o_goc, o_giua)

    def test_dao_chieu_lay_cho_phe_den(self) -> None:
        """Quân đen ở ô S phải đọc bảng như quân trắng ở ô đối xứng (lật hàng).

        Đây là bất biến đúng, kiểm trên CẢ 64 ô. Nếu đảo chiều bảng sai, máy
        sẽ nghĩ tốt đen ở hàng 1 là tốt trắng ở hàng 8 — tức là chưa qua sông.
        """
        for square in chess.SQUARES:
            doi = chess.square(
                chess.square_file(square), 7 - chess.square_rank(square)
            )
            with self.subTest(o=chess.square_name(square)):
                self.assertEqual(
                    engine.piece_square(chess.PAWN, chess.BLACK, square),
                    engine.piece_square(chess.PAWN, chess.WHITE, doi),
                )

    def test_dao_chieu_that_su_co_tac_dung(self) -> None:
        """Bảng phải phân biệt được hai phe, nếu không bước đảo là vô nghĩa."""
        khac = [
            o for o in chess.SQUARES
            if engine.piece_square(chess.PAWN, chess.BLACK, o)
            != engine.piece_square(chess.PAWN, chess.WHITE, o)
        ]
        self.assertTrue(khac, "mọi ô đều cho cùng điểm — đảo chiều là mã chết")

    def test_chi_so_bang_dung_chieu(self) -> None:
        """Bảng phải là hàng trước, cột sau — đọc nằm ngang là bảng sai."""
        self.assertEqual(engine._table_index(chess.A8), 0)
        self.assertEqual(engine._table_index(chess.H8), 7)
        self.assertEqual(engine._table_index(chess.A1), 56)
        self.assertEqual(engine._table_index(chess.H1), 63)
        # Ô lệch cả hàng lẫn cột: đây mới làm lộ lỗi hoán đổi.
        self.assertEqual(engine._table_index(chess.B2), 49)
        self.assertEqual(engine._table_index(chess.H6), 23)
        self.assertEqual(engine._table_index(chess.D4), 35)

    def test_dao_chieu_chi_lap_hang(self) -> None:
        self.assertEqual(
            engine._mirror(engine._table_index(chess.A8)),
            engine._table_index(chess.A1),
        )
        self.assertEqual(
            engine._mirror(engine._table_index(chess.D4)),
            engine._table_index(chess.D5),
        )

    def test_hau_giua_ban_diem_phai_cao(self) -> None:
        giua = chess.Board("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")
        goc = chess.Board("4k3/8/8/8/8/8/8/Q3K3 w - - 0 1")
        self.assertGreater(engine.evaluate(giua), engine.evaluate(goc))

    def test_min_material_tinh_dung_phe(self) -> None:
        """Hai phe bất đồng lượng quân: lấy số của phe ít hơn, vua không tính."""
        board = chess.Board("4k3/8/8/8/8/8/4R3/p3K3 w - - 0 1")   # trắng R, đen P
        self.assertEqual(
            engine.min_material(board),
            min(engine.VALUES[chess.PAWN], engine.VALUES[chess.ROOK]),
        )

    def test_min_material_bang_khong_khi_mot_phe_trong(self) -> None:
        board = chess.Board("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")
        self.assertEqual(engine.min_material(board), 0)

    def test_phase_giam_dan_theo_so_quan(self) -> None:
        dau = chess.Board(chess.STARTING_FEN)
        cuoi = chess.Board("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
        self.assertEqual(engine.phase(dau), 10)
        self.assertLessEqual(engine.phase(cuoi), 2)


if __name__ == "__main__":
    unittest.main()
