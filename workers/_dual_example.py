from __future__ import annotations

import time

import logging_mp
from core.events import EventSnapshot
from core.state_machine import ModeState, TransitionResult
from core.worker_base import DualRateWorker, WorkerContext


logger = logging_mp.get_logger(__name__, level=logging_mp.INFO)


class DualExampleWorker(DualRateWorker):
    """Dual-rate 워커 예제:
    - slow: 관측(telemetry) 업데이트
    - fast: 제어(명령) 업데이트
    """

    def __init__(self, ctx: WorkerContext, slow_hz: float = 10.0, fast_hz: float = 10.0) -> None:
        super().__init__(ctx, slow_hz=slow_hz, fast_hz=fast_hz)
        self._obs = 0.0
        self._cmd = 0.0
        self._fast_ticks = 0

    def on_start(self) -> None:
        logger.info(f"[{self.ctx.name}] start (dual-rate slow={self.slow_hz}Hz fast={self.fast_hz}Hz)")

    def do_slow(self, ev: EventSnapshot, tr: TransitionResult) -> None:
        # RUN일 때만 명령 생성/전송
        if self.state == ModeState.RUN:
            pass
    def do_fast(self, ev: EventSnapshot, tr: TransitionResult) -> None:

        # RUN일 때만 명령 생성/전송
        if self.state == ModeState.RUN:
            pass

    def on_stop(self) -> None:
        logger.info(f"[{self.ctx.name}] stop")
