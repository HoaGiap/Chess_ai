"""Luồng AI: sau nước của người thì AI nghĩ ở thread nền rồi tự đáp.

Dùng ENGINE GIẢ trong phần lớn test: nó trả nước đã biết và có thể bị khoá
lại bằng Event, nên test chạy nhanh và xác định. Test thật với engine thật chỉ
giữ một cái, để chắc chắn hai bên khớp nhau.
"""

import threading
import unittest

import chess

from chessai.position import MoveError
from chessai.web.ai import AIController
from chessai.web.games import GameStore


class FakeEngine:
    """Engine giả: đi theo kịch bản SAN, không hợp lệ thì đi nước đầu tiên.

    So khớp bằng `board.san(m)` chứ không dùng `board.parse_san(...)`: hàm đó
    NÉM khi SAN không hợp lệ, và kịch bản của test có thể không hợp lệ ở
    đúng thế cờ đó (ví dụ bấm "Ván mới" làm bàn cờ về xuất phát).
    """

    def __init__(self, *moves: str, block: threading.Event | None = None):
        self.moves = list(moves)
        self.block = block
        self.calls = 0
        self.fens: list[str] = []
        self.elos: list[int] = []

    def think(self, board, elo=1500, min_seconds=0.0):
        self.calls += 1
        self.fens.append(board.fen())
        self.elos.append(elo)
        if self.block is not None:
            self.block.wait(timeout=5.0)
        wanted = self.moves.pop(0) if self.moves else None
        if wanted is not None:
            for move in board.legal_moves:
                if board.san(move) == wanted:
                    return move
        return next(iter(board.legal_moves), None)


class TestHook(unittest.TestCase):
    def _bo(self, engine, human=chess.WHITE, elo=1500):
        store = GameStore()
        ai = AIController(store, engine=engine)
        game_id = store.create(human, elo=elo)
        ai.attach(game_id)
        return store, ai, game_id

    def test_hai_ben_thi_khong_bao_ngh(self) -> None:
        store, ai, game_id = self._bo(FakeEngine(), human=None)
        store.submit(game_id, "e4")
        ai.wait_idle(game_id)
        self.assertFalse(store.snapshot(game_id).thinking)
        self.assertEqual(ai.engine.calls, 0)

    def test_nguoi_di_thi_ai_ngh(self) -> None:
        store, ai, game_id = self._bo(FakeEngine("e5"))
        store.submit(game_id, "e4")
        ai.wait_idle(game_id)
        self.assertEqual(store.snapshot(game_id).moves, ["e4", "e5"])

    def test_nguoi_di_nham_phe_thi_bi_tu_trai(self) -> None:
        """Sau 1.e4, lượt là của đen — trắng bấm tiếp phải bị chặn."""
        store, ai, game_id = self._bo(FakeEngine("e5"))
        store.submit(game_id, "e4")
        ai.wait_idle(game_id)
        with self.assertRaises(MoveError):
            store.submit(game_id, "e4")

    def test_thinking_bat_dung_roi_tat(self) -> None:
        chan = threading.Event()
        store, ai, game_id = self._bo(FakeEngine("e5", block=chan))
        store.submit(game_id, "e4")
        self.assertTrue(store.snapshot(game_id).thinking)
        chan.set()
        ai.wait_idle(game_id)
        self.assertFalse(store.snapshot(game_id).thinking)

    def test_nguoi_chon_phe_den_thi_ai_ngh_ngay(self) -> None:
        """Review Focus 1: trắng đi trước, nên AI phải đi ngay khi ván tạo."""
        store, ai, game_id = self._bo(FakeEngine("e4"), human=chess.BLACK)
        ai.wait_idle(game_id)
        self.assertEqual(store.snapshot(game_id).moves, ["e4"])
        self.assertFalse(store.snapshot(game_id).thinking)

    def test_van_moi_giữ_cau_hinh(self) -> None:
        store, ai, game_id = self._bo(
            FakeEngine("e5"), human=chess.WHITE, elo=1900
        )
        store.submit(game_id, "e4")
        ai.wait_idle(game_id)
        state = store.new_game(game_id)
        self.assertEqual(state.elo, 1900)
        self.assertIsNotNone(store.session(game_id).on_move)

    def test_luu_cha_gi_nuoc_dang_cho(self) -> None:
        """Review Focus 2: bấm Ván mới khi AI đang nghĩ thì nước AI phải bị bỏ.

        `cancel` là việc route làm, không phải `GameStore.new_game` — nên test
        gọi `ai.cancel` đúng như route gọi.
        """
        chan = threading.Event()
        store, ai, game_id = self._bo(FakeEngine("e5", block=chan))
        store.submit(game_id, "e4")
        ai.cancel(game_id)
        store.new_game(game_id)
        chan.set()
        ai.wait_idle(game_id)
        self.assertEqual(store.snapshot(game_id).moves, [])

    def test_huy_thi_tat_thong_bao_nghi(self) -> None:
        chan = threading.Event()
        store, ai, game_id = self._bo(FakeEngine("e5", block=chan))
        store.submit(game_id, "e4")
        self.assertTrue(store.snapshot(game_id).thinking)
        ai.cancel(game_id)
        self.assertFalse(store.snapshot(game_id).thinking)
        chan.set()
        ai.wait_idle(game_id)

    def test_fen_doi_thi_khong_ap_du_khong_can_huy(self) -> None:
        """Lớp bảo vệ thứ hai: kể cả lỡ quên gọi cancel, FEN khác thì bỏ nước."""
        chan = threading.Event()
        store, ai, game_id = self._bo(FakeEngine("e5", block=chan))
        store.submit(game_id, "e4")
        store.new_game(game_id)            # KHÔNG huy, chỉ đổi bàn cờ
        chan.set()
        ai.wait_idle(game_id)
        self.assertEqual(store.snapshot(game_id).moves, [])

    def test_get_tra_loi_duc_khi_ai_dang_tim(self) -> None:
        """Review Focus 3: GET phải trả lời được khi AI đang tìm."""
        chan = threading.Event()
        store, ai, game_id = self._bo(FakeEngine("e5", block=chan))
        store.submit(game_id, "e4")
        xong = threading.Event()

        def hoi():
            store.snapshot(game_id)
            xong.set()

        t = threading.Thread(target=hoi)
        t.start()
        self.assertTrue(xong.wait(timeout=1.0), "snapshot bị khoá quá lâu")
        chan.set()
        ai.wait_idle(game_id)

    def test_engine_nhan_dung_elo(self) -> None:
        """Elo trong DTO phải tới được engine, nếu không thanh trượt vô nghĩa."""
        store, ai, game_id = self._bo(FakeEngine("e5"), elo=2200)
        store.submit(game_id, "e4")
        ai.wait_idle(game_id)
        self.assertEqual(ai.engine.elos, [2200])
        self.assertEqual(store.snapshot(game_id).elo, 2200)

    def test_het_van_thi_khong_bao_ngh(self) -> None:
        """Trắng f3, đen e5, trắng g4, đen Qh4# — máy tự đóng ván."""
        store, ai, game_id = self._bo(FakeEngine("e5", "Qh4#"), human=chess.WHITE)
        for nuoc_nguoi in ("f3", "g4"):
            store.submit(game_id, nuoc_nguoi)
            ai.wait_idle(game_id)
        state = store.snapshot(game_id)
        self.assertTrue(state.over, state.moves)
        self.assertFalse(state.thinking)


class TestRealEngine(unittest.TestCase):
    def test_engine_that_roi_van_dung(self) -> None:
        from chessai import engine as that
        store = GameStore()
        ai = AIController(store, engine=that)
        game_id = store.create(chess.WHITE, elo=600)
        ai.attach(game_id)
        store.submit(game_id, "e4")
        ai.wait_idle(game_id, timeout=30.0)
        moves = store.snapshot(game_id).moves
        # KHÔNG khẳng định máy đi e5: ở Elo 600 máy cố tình chơi yếu, nên trả lời
        # nào cũng hợp lệ. Cái cần kiểm là: có đúng MỘT nước, và hợp lệ.
        self.assertEqual(len(moves), 2, moves)
        self.assertEqual(moves[0], "e4")


if __name__ == "__main__":
    unittest.main()
