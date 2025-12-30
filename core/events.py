from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping

import multiprocessing as mp


# ---- Event definitions ----------------------------------------------------

LEVEL_EVENTS = (
    "shutdown",   # 전체 종료(레벨)
    "ready",      # 연결/초기화 완료(레벨)
    "start",      # 동작 시작/일시정지(레벨; toggle로 사용 가능)
)


@dataclass(frozen=True)
class EventSnapshot:
    """워커 루프 한 틱에서 사용하는 이벤트 스냅샷."""
    level: Dict[str, bool]


class EventBus:
    """멀티프로세스에서 level 이벤트만 제공하는 버스."""

    def __init__(
        self,
        level_events: Mapping[str, mp.Event],
    ) -> None:
        self._level = dict(level_events)

    # ----- level API -------------------------------------------------------
    def set_level(self, name: str) -> None:
        self._level[name].set()

    def clear_level(self, name: str) -> None:
        self._level[name].clear()

    def is_level_set(self, name: str) -> bool:
        return self._level[name].is_set()

    def read_snapshot(
        self,
        *,
        level_names: Iterable[str] = LEVEL_EVENTS,
    ) -> EventSnapshot:
        """현재 레벨 이벤트 상태를 스냅샷으로 읽는다."""
        level = {k: self._level[k].is_set() for k in level_names}
        return EventSnapshot(level=level)


def create_shared_events(manager: Any | None = None) -> Dict[str, mp.Event]:
    """main 프로세스에서 호출하여 공유 이벤트를 생성."""
    if manager is None:
        return {k: mp.Event() for k in LEVEL_EVENTS}
    return {k: manager.get_event(k) for k in LEVEL_EVENTS}
