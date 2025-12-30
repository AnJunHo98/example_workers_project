from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from core.events import EventSnapshot


class ModeState(IntEnum):
    WAIT_CONNECT = 0
    WAIT_START = 1
    RUN = 2
    PAUSE = 3
    EXIT = 99


@dataclass(frozen=True)
class TransitionResult:
    state: ModeState
    reason: str


def step(state: ModeState, ev: EventSnapshot) -> TransitionResult:
    """공통 상태 전이 로직(순수 함수).

    설계 의도:
    - 모든 워커가 동일한 전이 함수를 사용하면,
      'event 기반 state 변경'이 획일화된다.
    - 레벨 이벤트: shutdown/ready/start
    """
    # 1) 종료는 항상 우선
    if ev.level.get("shutdown", False):
        return TransitionResult(ModeState.EXIT, "shutdown")

    # 상태별 전이
    if state == ModeState.WAIT_CONNECT:
        if ev.level.get("ready", False):
            return TransitionResult(ModeState.WAIT_START, "ready")
        return TransitionResult(state, "Waiting for ready")

    if state == ModeState.WAIT_START:
        if ev.level.get("start", False):
            return TransitionResult(ModeState.RUN, "start_set")
        return TransitionResult(state, "Waiting for start")

    if state == ModeState.RUN:
        # start 레벨을 toggle로 쓰는 패턴: start가 꺼지면 PAUSE
        if not ev.level.get("start", False):
            return TransitionResult(ModeState.PAUSE, "start_cleared")
        return TransitionResult(state, "Running")

    if state == ModeState.PAUSE:
        if ev.level.get("start", False):
            return TransitionResult(ModeState.RUN, "start_set")
        return TransitionResult(state, "Paused")

    if state == ModeState.EXIT:
        return TransitionResult(state, "exit")

    # 방어적 처리
    return TransitionResult(state, "waiting")
