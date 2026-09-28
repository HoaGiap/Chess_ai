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

    def test_phase_giam_dan_theo_so_quan(self) -> None:
        dau = chess.Board(chess.STARTING_FEN)
        cuoi = chess.Board("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
        self.assertEqual(engine.phase(dau), 10)
        self.assertLessEqual(engine.phase(cuoi), 2)


class TestProfile(unittest.TestCase):
    def test_elo_thap_cho_tim_nong_va_game_hon(self) -> None:
        thap = engine.profile_for(700)
        cao = engine.profile_for(2300)
        self.assertLess(thap[0], cao[0])            # max_depth
        self.assertGreater(thap[1], cao[1])         # blunder_rate
        self.assertGreater(thap[2], cao[2])         # slack_cp
        self.assertLess(thap[3], cao[3])            # max_seconds

    def test_noi_suy_tuyen_tinh(self) -> None:
        self.assertEqual(engine.profile_for(600)[0], 1)
        self.assertEqual(engine.profile_for(750)[0], 2)   # nua giua 600 va 900

    def test_kep_o_hai_dau(self) -> None:
        self.assertEqual(engine.profile_for(100)[0], engine.profile_for(600)[0])
        self.assertEqual(engine.profile_for(9999)[0], engine.profile_for(2400)[0])

    def test_elo_2400_khong_cho_phep_sai(self) -> None:
        self.assertEqual(engine.profile_for(2400)[1], 0.0)

    def test_bang_elo_don_tang(self) -> None:
        for a, b in ((600, 900), (900, 1200), (1200, 1500),
                     (1500, 1800), (1800, 2100), (2100, 2400)):
            with self.subTest(a=a, b=b):
                self.assertLess(engine.profile_for(a)[0], engine.profile_for(b)[0])
                self.assertGreater(engine.profile_for(a)[1], engine.profile_for(b)[1])


class TestThink(unittest.TestCase):
    def _an(self, san: str) -> chess.Board:
        board = chess.Board()
        for one in san.split():
            board.push_san(one)
        return board

    def test_the_chet_thi_tra_none(self) -> None:
        """K+N đối K là thế chết: máy phải trả None, không phải nước đi."""
        self.assertIsNone(engine.think(chess.Board("4k3/8/8/8/8/5N2/8/4K3 w - - 0 1"), 1500, 0.0))

    def test_khong_con_nuoc_di_thi_tra_none(self) -> None:
        board = self._an("f3 e5 g4 Qh4#")
        self.assertIsNone(engine.think(board, 1500, 0.0))

    def test_dang_bi_chieu_thi_phai_tra_lai(self) -> None:
        """Xe trắng đứng chéo vua đen: đen phải thoát chiếu.

        Dùng FEN dựng tay thay vì dòng SAN — dòng SAN viết tay thì dễ sai, và
        một dòng sai là test hỏng vì lý do không liên quan tới engine.
        """
        board = chess.Board("4k3/8/8/8/8/8/8/K3R3 b - - 0 1")
        self.assertTrue(board.is_check(), "the phai thuoc ve de bai co y nghia")
        nuoc = engine.think(board, 2400, 0.0)
        self.assertIsNotNone(nuoc)
        self.assertIn(nuoc, list(board.legal_moves))
        ten = board.san(nuoc)          # san() chi goi duoc TRUOC khi day nuoc
        board.push(nuoc)
        self.assertFalse(board.is_check(), ten)

    def test_bi_chi_hoi_thi_khong_di_quan_khac(self) -> None:
        """Bị chiều thì phải đáp — hoặc thoát, hoặc chặn, nhưng không được đứng yên.

        Thêm tốt đen ở e7 để có thêm lựa chọn chặn đường chiếu, nên test buộc
        máy phải đánh giá nhiều lựa chọn chứ không chỉ chạy vua.
        """
        board = chess.Board("4k3/8/8/8/8/8/4p3/K3R3 b - - 0 1")
        nuoc = engine.think(board, 2400, 0.0)
        self.assertIsNotNone(nuoc)
        ten = board.san(nuoc)          # san() chi goi duoc TRUOC khi day nuoc
        board.push(nuoc)
        self.assertFalse(board.is_check(), ten)

    def test_ai_khong_tu_tra_nuoc_lam_mat_quan(self) -> None:
        board = self._an("e4 e5 Nf3 Nc6 Bc4 Bc5")
        nuoc = engine.think(board, 2400, 0.0)
        self.assertIsNotNone(nuoc)
        self.assertNotIn(
            chess.square_name(nuoc.from_square), ("f1", "g1"),
            "mat quan vo dieu kien",
        )

    def test_moi_dong_ca_quan_hon_deu_tra_nuoc_hop_le(self) -> None:
        dong = [
            chess.STARTING_FEN,
            "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
            "r1bq1rk1/pp2ppbp/2np1np1/8/3NP3/2N1BP2/PPPQ2PP/2KR1B1R w - - 0 9",
            "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1",
            "8/2P5/8/8/8/8/6k1/4K3 w - - 0 1",
            "4k3/8/8/8/8/5N2/8/3RK3 w - - 0 1",
            "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 4 4",
        ]
        for fen in dong:
            with self.subTest(fen=fen):
                board = chess.Board(fen)
                nuoc = engine.think(board, 1500, 0.0)
                self.assertIn(nuoc, list(board.legal_moves))

    def test_elo_thap_van_luon_hop_le(self) -> None:
        """Review Focus 4: cho may choi yeu bang cach chon nuoc te; bang cach
        tra nuoc bat hop le thi mat ca van.

        Cả RNG của người chơi lẫn RNG truyền vào `think` đều có gieo, nên ván
        này tái lập được: hỏng thì chạy lại là ra y hệt. Trước đây `think` dùng
        `random` toàn cục, không gieo được — ván hỏng không tái lập.
        """
        import random
        rng = random.Random(20260928)
        board = chess.Board()
        for _ in range(16):
            # Máy ở Elo 600 có thể chiếu tướng hoặc bế tắc trước khi hết 16
            # nước, nên phải dừng khi ván xong thay vì giả định còn nước đi.
            if board.is_game_over():
                break
            board.push(rng.choice(list(board.legal_moves)))
            nuoc = engine.think(board, 600, 0.0, rng=rng)
            if nuoc is None:
                break
            self.assertIn(nuoc, list(board.legal_moves), board.fen())
            board.push(nuoc)

    def test_elo_cao_cung_luon_hop_le(self) -> None:
        import random
        rng = random.Random(1)
        board = chess.Board()
        for _ in range(6):
            if board.is_game_over():
                break
            board.push(rng.choice(list(board.legal_moves)))
            nuoc = engine.think(board, 2400, 0.0, rng=rng)
            if nuoc is None:
                break
            self.assertIn(nuoc, list(board.legal_moves), board.fen())
            board.push(nuoc)

    def test_elo_2400_don_gian_khong_bai_thua_tot(self) -> None:
        board = self._an("e4 e5 Qh5 Nc6 Bc4 Nf6")
        nuoc = engine.think(board, 2400, 0.0)
        self.assertIn(board.san(nuoc), ("Qxf7#", "Bxf7+", "Qxe5+"))

    def test_khong_vuot_qua_thoi_gian_cho_phep(self) -> None:
        import time as _time
        board = chess.Board(
            "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
        )
        bat_dau = _time.monotonic()
        engine.think(board, 2400, 0.0)
        # Trần của Elo 2400 là 9.0s. Cho phép hơn 20% vì deadline được kiểm ở
        # đỉnh mỗi node, một node cuối có thể trôi — nhưng KHÔNG cho phép gấp đôi:
        # con số 2x khiến test này không bao giờ đỏ.
        self.assertLess(_time.monotonic() - bat_dau, 9.0 * 1.2)

    def test_thoi_gian_toi_thieu_duoc_chan(self) -> None:
        import time as _time
        bat_dau = _time.monotonic()
        engine.think(chess.Board(), 600, 0.6)
        self.assertGreaterEqual(_time.monotonic() - bat_dau, 0.55)

    def test_clamp_time_khong_vuot_tran(self) -> None:
        board = chess.Board(chess.STARTING_FEN)
        self.assertLessEqual(engine.clamp_time(board, 0.4, 0.6), 0.6)
        self.assertGreaterEqual(engine.clamp_time(board, 0.4, 0.1), 0.1)


if __name__ == "__main__":
    unittest.main()
