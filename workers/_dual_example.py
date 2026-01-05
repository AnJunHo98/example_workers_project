from __future__ import annotations

import logging_mp
from core.events import EventSnapshot
from core.state_machine import ModeState, TransitionResult
from core.worker_base import DualRateWorker, WorkerContext


logger = logging_mp.get_logger(__name__, level=logging_mp.INFO)


class DualExampleWorker(DualRateWorker):
    """Dual-rate worker example: logs SYSTEM_STATUS in slow/fast loops."""

    def __init__(self, ctx: WorkerContext, slow_hz: float = 100.0, fast_hz: float = 100.0) -> None:
        super().__init__(ctx, slow_hz=slow_hz, fast_hz=fast_hz)
        self._obs = 0.0
        self._cmd = 0.0
        self._fast_ticks = 0
        self._status_shm = None
        self._slow_reads = 0
        self._fast_reads = 0

    def on_start(self) -> None:
        logger.info(f"[{self.ctx.name}] start (dual-rate slow={self.slow_hz}Hz fast={self.fast_hz}Hz)")
        if self.ctx.shared_memory is not None:
            self._status_shm = self.ctx.shared_memory.get("system_status_shm")
        if self._status_shm is None:
            logger.warning("[%s] system_status_shm not available", self.ctx.name)

    def _log_status(self, loop_name: str) -> None:
        if self._status_shm is None:
            return
        data = self._status_shm.read_data()
        counter = data["counter"].item()
        timestamp = data["timestamp"].item()
        logger.info(
            "[%s] %s loop system_status counter=%s timestamp=%.6f",
            self.ctx.name,
            loop_name,
            counter,
            timestamp,
        )

    def do_slow(self, ev: EventSnapshot, tr: TransitionResult) -> None:
        if self.state != ModeState.RUN:
            return
        self._slow_reads += 1
        if self._slow_reads % 100 != 0:
            return
        self._log_status("slow")
    def do_fast(self, ev: EventSnapshot, tr: TransitionResult) -> None:
        if self.state != ModeState.RUN:
            return
        self._fast_reads += 1
        if self._fast_reads % 100 != 0:
            return
        self._log_status("fast")

    def on_stop(self) -> None:
        logger.info(f"[{self.ctx.name}] stop")
