from __future__ import annotations

import logging_mp
from core.events import EventSnapshot
from core.state_machine import ModeState, TransitionResult
from core.worker_base import SingleRateWorker, WorkerContext


logger = logging_mp.get_logger(__name__, level=logging_mp.INFO)


class SingleExampleWorker(SingleRateWorker):
    """Single-rate 워커 예제: 상태에 따라 카운터를 업데이트."""

    def __init__(self, ctx: WorkerContext, hz: float = 10.0) -> None:
        super().__init__(ctx, hz=hz)
        self._counter = 0

    def on_start(self) -> None:
        logger.info(f"[{self.ctx.name}] start (single-rate {self.hz} Hz)")

    def step_once(self, ev: EventSnapshot, tr: TransitionResult) -> None:
        st = self.state

        # 예시: RUN 상태에서만 카운터 증가
        if st == ModeState.RUN:
            pass

    def on_stop(self) -> None:
        logger.info(f"[{self.ctx.name}] stop")
