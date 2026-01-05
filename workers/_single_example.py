from __future__ import annotations

import time

import logging_mp
from core.events import EventSnapshot
from core.state_machine import ModeState, TransitionResult
from core.worker_base import SingleRateWorker, WorkerContext


logger = logging_mp.get_logger(__name__, level=logging_mp.INFO)


class SingleExampleWorker(SingleRateWorker):
    """Single-rate worker example: updates SYSTEM_STATUS counter/timestamp each tick."""

    def __init__(self, ctx: WorkerContext, hz: float = 100.0) -> None:
        super().__init__(ctx, hz=hz)
        self._counter = 0
        self._status_shm = None

    def on_start(self) -> None:
        logger.info(f"[{self.ctx.name}] start (single-rate {self.hz} Hz)")
        if self.ctx.shared_memory is not None:
            self._status_shm = self.ctx.shared_memory.get("system_status_shm")
        if self._status_shm is None:
            logger.warning("[%s] system_status_shm not available", self.ctx.name)

    def step_once(self, ev: EventSnapshot, tr: TransitionResult) -> None:
        if self.state != ModeState.RUN:
            return
        if self._status_shm is None:
            return

        self._counter += 1
        now = time.time()
        self._status_shm.write_data(counter=self._counter, timestamp=now)

    def on_stop(self) -> None:
        logger.info(f"[{self.ctx.name}] stop")
