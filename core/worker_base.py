from __future__ import annotations

import multiprocessing as mp
import threading
import time
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from core.events import EventBus, EventSnapshot
from core.rate import Rate
from core.state_machine import ModeState, TransitionResult, step

if TYPE_CHECKING:
    from ..sharedmemory.shmManager import SharedMemoryManager


@dataclass
class WorkerContext:
    name: str
    bus: EventBus
    shared_lock: Optional[dict[str, mp.Lock]] = None
    shm_name: Optional[dict[str, str]] = None
    shared_memory: Optional[dict[str, "SharedMemoryManager"]] = None


class BaseWorker:
    """모든 워커의 공통 베이스: 이벤트 읽기 + 상태 전이를 획일화."""

    def __init__(self, ctx: WorkerContext) -> None:
        self.ctx = ctx
        self._state_lock = threading.Lock()
        self._state: ModeState = ModeState.WAIT_CONNECT

    @property
    def state(self) -> ModeState:
        with self._state_lock:
            return self._state

    def _set_state(self, new_state: ModeState) -> None:
        with self._state_lock:
            self._state = new_state

    def poll(self) -> tuple[EventSnapshot, TransitionResult]:
        """모든 워커에서 동일하게 호출하는 poll 함수.

        1) 이벤트 스냅샷 읽기
        2) 상태 전이 수행
        """
        ev = self.ctx.bus.read_snapshot()
        with self._state_lock:
            tr = step(self._state, ev)
            self._state = tr.state
        return ev, tr

    # ---- Lifecycle hooks --------------------------------------------------
    def on_start(self) -> None:
        pass

    def on_stop(self) -> None:
        pass


class SingleRateWorker(BaseWorker):
    """단일 루프(단일 주기) 워커 템플릿."""

    def __init__(self, ctx: WorkerContext, hz: float) -> None:
        super().__init__(ctx)
        self.hz = float(hz)

    def step_once(self, ev: EventSnapshot, tr: TransitionResult) -> None:
        """사용자가 구현: 틱마다 수행할 작업."""
        raise NotImplementedError

    def run(self) -> None:
        self.on_start()
        rate = Rate(self.hz)
        try:
            while True:
                ev, tr = self.poll()
                if self.state == ModeState.EXIT:
                    break
                self.step_once(ev, tr)
                rate.sleep()
        finally:
            self.on_stop()


class DualRateWorker(BaseWorker):
    """느린 루프+빠른 루프(2 스레드) 워커 템플릿."""

    def __init__(self, ctx: WorkerContext, slow_hz: float, fast_hz: float) -> None:
        super().__init__(ctx)
        self.slow_hz = float(slow_hz)
        self.fast_hz = float(fast_hz)

        self._stop_threads = threading.Event()
        self._t_slow: Optional[threading.Thread] = None
        self._t_fast: Optional[threading.Thread] = None

    def do_slow(self, ev: EventSnapshot, tr: TransitionResult) -> None:
        raise NotImplementedError

    def do_fast(self, ev: EventSnapshot, tr: TransitionResult) -> None:
        raise NotImplementedError

    def _slow_loop(self) -> None:
        rate = Rate(self.slow_hz)
        while not self._stop_threads.is_set():
            ev, tr = self.poll()
            if self.state == ModeState.EXIT:
                self._stop_threads.set()
                break
            self.do_slow(ev, tr)
            rate.sleep()

    def _fast_loop(self) -> None:
        rate = Rate(self.fast_hz)
        while not self._stop_threads.is_set():
            ev, tr = self.poll()
            if self.state == ModeState.EXIT:
                self._stop_threads.set()
                break
            self.do_fast(ev, tr)
            rate.sleep()

    def run(self) -> None:
        self.on_start()
        try:
            self._t_slow = threading.Thread(target=self._slow_loop, name=f"{self.ctx.name}-slow", daemon=True)
            self._t_fast = threading.Thread(target=self._fast_loop, name=f"{self.ctx.name}-fast", daemon=True)
            self._t_slow.start()
            self._t_fast.start()

            # 메인 스레드는 join만 수행
            while not self._stop_threads.is_set():
                time.sleep(0.1)
        finally:
            self._stop_threads.set()
            if self._t_slow is not None:
                self._t_slow.join(timeout=1.0)
            if self._t_fast is not None:
                self._t_fast.join(timeout=1.0)
            self.on_stop()
