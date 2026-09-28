"""Cho máy đi nước ở thread nền.

Một `Session.on_move` chạy **bên trong** khoá ván (`GameStore.submit` giữ khoá
rồi mới gọi `apply_san`). Nên `on_move` chỉ được làm một việc rẻ: đặt cờ và
đẩy việc tìm nước ra thread. Tìm nước tuyệt đối không được chạm vào khoá —
nếu giữ, mỗi lần bấm nút "Lùi" trong lúc máy đang nghĩ sẽ treo cả trang.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from functools import partial

import chess

from .. import engine
from .games import GameStore

# Engine mặc định. Test truyền engine giả vào để chạy nhanh và xác định.
_MODULE_ENGINE = engine

# Người chơi cấp hình; máy luôn chờ tối thiểu bấy nhiêu giây trước khi đáp,
# nếu không thì ở Elo thấp máy đi tức thì và cảm giác như đang đấu máy in.
_MIN_THINK_SECONDS = 0.6


class AIController:
    def __init__(
        self,
        store: GameStore,
        executor: ThreadPoolExecutor | None = None,
        engine=None,
    ) -> None:
        self.store = store
        self.engine = engine if engine is not None else _MODULE_ENGINE
        self._pool = executor or ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="ai"
        )
        self._owns_pool = executor is None
        self._flags: dict[str, bool] = {}
        self._tasks: dict[str, Future] = {}
        self._guard = threading.Lock()

    # ---- vòng đời ---------------------------------------------------

    def attach(self, game_id: str) -> None:
        """Gắn `on_move` cho một ván, và bật AI nếu đã tới lượt máy.

        `partial` vì `on_move` chỉ nhận (san, phe) — không biết ván nào, nên
        phải buộc `game_id` vào trước.
        """
        session = self.store.session(game_id)
        session.on_move = partial(self._on_move, game_id)
        if self._machine_to_move(game_id):
            self._start(game_id, self.store.fen_of(game_id))

    def shutdown(self) -> None:
        if self._owns_pool:
            self._pool.shutdown(wait=False, cancel_futures=True)

    # ---- cờ huỷ ---------------------------------------------------

    def cancel(self, game_id: str) -> None:
        """Báo thread đang tìm là kết quả của nó đã lỗi thời.

        Thread vẫn chạy hết thời gian rồi tự kết thúc — Python không huỷ được
        thread, nhưng nó không giữ tài nguyên nào nên để vậy là được.
        """
        with self._guard:
            self._flags[game_id] = True
        self.store.set_thinking(game_id, False)

    def thinking(self, game_id: str) -> bool:
        return bool(self.store.snapshot(game_id).thinking)

    def wait_idle(self, game_id: str, timeout: float = 10.0) -> None:
        """Chờ thread của một ván xong. Chỉ dùng trong test."""
        with self._guard:
            task = self._tasks.get(game_id)
        if task is not None:
            task.result(timeout=timeout)

    # ---- phần cốt lõi -----------------------------------------------

    def _machine_to_move(self, game_id: str) -> bool:
        session = self.store.session(game_id)
        return (
            session.human_color is not None
            and not session.is_game_over()
            and session.position.side_to_move != session.human_color
        )

    def _on_move(self, game_id: str, san: str, color: chess.Color) -> None:
        if self._machine_to_move(game_id):
            # Đang ở trong khoá ván (do submit gọi), nên đọc FEN bằng bản
            # không khoá — đọc bản có khoá ở đây sẽ tự khoá và treo.
            self._start(game_id, self.store.fen_now(game_id))

    def _start(self, game_id: str, fen: str) -> None:
        with self._guard:
            if self._flags.get(game_id):
                return
            self._flags[game_id] = False
        self.store.set_thinking(game_id, True)
        task = self._pool.submit(self._run, game_id, fen)
        with self._guard:
            self._tasks[game_id] = task

    def _run(self, game_id: str, fen: str) -> None:
        with self._guard:
            if self._flags.get(game_id):
                return
        try:
            self._move(game_id, fen)
        finally:
            self.store.set_thinking(game_id, False)

    def _move(self, game_id: str, fen: str) -> None:
        elo = self.store.session(game_id).elo
        board = chess.Board(fen)
        move = self.engine.think(board, elo=elo, min_seconds=_MIN_THINK_SECONDS)
        if move is None:
            return

        with self._guard:
            if self._flags.get(game_id):
                return

        self.store.commit_ai_move(game_id, fen, move)
