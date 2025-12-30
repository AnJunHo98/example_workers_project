from __future__ import annotations

import time


class Rate:
    """고정 주기 루프 헬퍼(원 프로젝트의 Rate와 유사한 형태)."""

    def __init__(self, hz: float) -> None:
        if hz <= 0:
            raise ValueError("hz must be > 0")
        self.hz = float(hz)
        self.dt = 1.0 / self.hz
        self.next_t = time.perf_counter() + self.dt

    def sleep(self) -> None:
        now = time.perf_counter()
        remaining = self.next_t - now
        if remaining > 0:
            # 대부분은 sleep으로 처리
            if remaining > 0.001:
                time.sleep(remaining - 0.0005)
            # 마지막 0~1ms는 바쁜 대기(정밀도)
            while time.perf_counter() < self.next_t:
                pass
        self.next_t += self.dt
