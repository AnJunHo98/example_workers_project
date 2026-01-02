from __future__ import annotations

import os
import sys
import termios
import tty
import select

import logging_mp
from core.worker_base import SingleRateWorker, WorkerContext
from core.events import EventSnapshot
from core.state_machine import TransitionResult


logger = logging_mp.get_logger(__name__, level=logging_mp.INFO)


class KeyboardWorker(SingleRateWorker):
    """단일 키 입력으로 이벤트를 발생시키는 워커.

    - Linux/Unix 환경에서 /dev/tty를 사용해 raw 모드로 1글자 입력을 읽는다.
    - mp.Event(level) 기반 EventBus에 이벤트를 기록한다.

    키 매핑(기본):
      q      -> shutdown (level set)
      r      -> ready (level set)
      s      -> start toggle (level)
      p      -> pause (start level clear)
    """

    def __init__(self, ctx: WorkerContext, hz: float = 60.0) -> None:
        super().__init__(ctx, hz=hz)
        self._fd = None
        self._old_attr = None

    def on_start(self) -> None:
        # controlling terminal을 직접 연다(표준입력이 리다이렉트된 경우도 대비)
        try:
            self._fd = os.open("/dev/tty", os.O_RDONLY)
        except OSError:
            # fallback: stdin
            self._fd = sys.stdin.fileno()

        self._old_attr = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)

        logger.info(
            "\n[keyboard] keys: r(ready) s(start toggle) p(pause) q(quit)\n"
            "          (ready -> start 순으로 입력하면 RUN 진입)\n"
        )

    def step_once(self, ev: EventSnapshot, tr: TransitionResult) -> None:
        if self._fd is None:
            return

        r, _, _ = select.select([self._fd], [], [], 0.0)
        if not r:
            return

        ch = os.read(self._fd, 1)
        if not ch:
            return

        c = ch.decode(errors="ignore")

        # level events
        if c == "q":
            self.ctx.bus.set_level("shutdown")
            return

        if c == "r":
            self.ctx.bus.set_level("ready")
            return

        if c == "s":
            # toggle start
            if self.ctx.bus.is_level_set("start"):
                self.ctx.bus.clear_level("start")
            else:
                self.ctx.bus.set_level("start")
            return

        if c == "p":
            self.ctx.bus.clear_level("start")
            return

    def on_stop(self) -> None:
        if self._fd is not None and self._old_attr is not None:
            try:
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_attr)
            except Exception:
                pass
            try:
                # /dev/tty로 연 fd만 닫는다(표준입력 fileno일 수도 있음)
                if self._fd != sys.stdin.fileno():
                    os.close(self._fd)
            except Exception:
                pass
        logger.info("[keyboard] stop")
