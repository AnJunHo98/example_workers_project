# Example Workers Project (Single/Dual rate + unified events + event-driven state machine)

멀티프로세스 워커 기반의 이벤트 드리븐 상태 머신 프레임워크입니다.
모든 워커가 동일한 방식으로 이벤트를 읽고 상태를 전이할 수 있도록 설계되었습니다.


## 🎯 주요 기능

### 1. 통일된 이벤트 시스템
- **Level 이벤트**: `mp.Event` 기반 상태 유지 (ready, start, shutdown)
- 모든 워커가 `EventBus.read_snapshot()`으로 일관된 방식으로 이벤트 읽음
- OS 수준의 안전한 멀티프로세스 동기화

### 2. 워커 타입
- **Single-rate Worker**: 고정 주기(Hz) 루프
- **Dual-rate Worker**: 느린 루프(slow_hz) + 빠른 루프(fast_hz) 조합
- **Keyboard Worker**: 콘솔 입력으로 이벤트 트리거

### 3. 상태 머신
- 모든 워커가 공통 전이 함수 `core.state_machine.step()`를 사용
- 이벤트 기반 상태 전이 (WAIT_CONNECT → WAIT_START → RUN/PAUSE → EXIT)
- 워커 동작은 `step_once()`(single) 또는 `do_slow()`/`do_fast()`(dual)에서 구현

### 4. Qt GUI 컨트롤러
- 실시간 워커 상태 모니터링 (ALIVE/STOPPED)
- 이벤트(ready, start, shutdown) 수동 제어
- EventBus 레벨 스냅샷 표시

### 5. 공유 메모리
- 워커 간 고성능 데이터 공유
- 스키마 기반 구조화된 메모리 관리
- Lock 기반 동시성 제어

### 6. IPC 기반 확장성
- 이벤트/데이터 통신을 IPC로 분리해 설계
- 필요 시 동일 호스트의 서로 다른 Python 실행 환경(가상환경/컨테이너 등)에도 적용 가능하도록 확장 용이

## 🚀 설치 및 실행

### 가상환경 생성 (.init)
```bash
python -m venv .init
source .init/bin/activate
```

### 외부 가상환경 생성 (.external)
```bash
python -m venv .external
```

### 필수 패키지 설치
```bash
pip install PyQt5 logging_mp numpy
# 또는 PyQt6
pip install PyQt6 logging_mp numpy
```

### 프로젝트 실행
```bash
python main.py
```


## 📁 프로젝트 구조

```
example_workers_project/
├── .external/                       # 로컬 venv (자동 생성)
├── .init/                           # 초기화용 venv (자동 생성)
├── main.py                          # 런처(워커 시작, GUI 관리, cleanup)
├── core/
│   ├── __init__.py
│   ├── events.py                    # EventBus, LEVEL_EVENTS 정의
│   ├── rate.py                      # 고정 주기 루프 헬퍼
│   ├── state_machine.py             # 공통 상태 전이(step) 정의
│   └── worker_base.py               # WorkerContext, BaseWorker, DualRateWorker
├── ipc/
│   ├── __init__.py
│   └── manager.py                   # IPC 매니저
├── workers/
│   ├── __init__.py
│   ├── _registry.py                 # 워커 레지스트리
│   ├── _single_example.py           # Single-rate 워커 예제
│   ├── _dual_example.py             # Dual-rate 워커 예제
│   ├── _keyboard_worker.py          # 콘솔 입력 워커
│   └── _run_external.py             # 외부 프로세스 워커 실행
├── ui/
│   ├── gui_controller.py            # Qt GUI 메인 컨트롤러
│   └── gui.ui                       # Qt Designer 레이아웃
├── sharedmemory/
│   ├── __init__.py
│   ├── shmManager.py                # 공유 메모리 관리자
│   ├── shm_schema.py                # 메모리 스키마 정의(CAMERA 등)
│   └── shm_init_clean.py            # 초기화/정리 함수
└── README.md
```



## 동시성 및 안전성

- **Level 이벤트**: `mp.Event` 기반으로 OS 수준 동기화
- **공유 메모리**: Lock 기반 임계 영역 보호
- **Dual-rate Worker**: 상태 전이는 내부 lock으로 보호(사용자 공유 데이터는 별도 lock 권장)
- **GUI**: Qt의 signal/slot 메커니즘으로 스레드 안전성 보장
- **Watchdog**: GUI 타이머가 200ms 주기로 워커 상태 감시

## 🔧 커스터마이징

### 새 워커 추가하기

**1단계: 워커 클래스 정의**
```python
# workers/my_worker.py
from core.worker_base import SingleRateWorker
from core.state_machine import ModeState
from logging_mp import get_logger

logger = get_logger(__name__)

class MyWorker(SingleRateWorker):
    def __init__(self, ctx, hz=10.0):
        super().__init__(ctx, hz=hz)
    
    def step_once(self, ev, tr):
        if self.state == ModeState.RUN:
            # 메인 로직 구현
            logger.info("[MyWorker] Running...")
```

**2단계: main.py에 등록**
```python
# main.py
from workers.my_worker import MyWorker

def build_my_worker(ctx: WorkerContext) -> MyWorker:
    return MyWorker(ctx, hz=10.0)

WORKER_SPECS: Dict[str, Dict[str, Any]] = {
    "my_worker": {"builder": build_my_worker, "enabled": True, "daemon": True},
    # ... 기존 워커들
}
```

### 외부 프로세스 워커 사용

외부 프로세스 워커는 다른 Python 실행 환경(예: `.external` venv)에서 실행되며,
IPC를 통해 동일한 EventBus/Lock/SharedMemory에 연결됩니다.

**1단계: 워커를 외부 프로세스로 지정**
```python
# workers/_registry.py
WORKER_SPECS = {
    "external": WorkerSpec(
        name="external",
        builder=_build_external,
        enabled=True,
        daemon=True,
        external=True,                # 외부 프로세스로 실행
        python=".external/bin/python" # 실행할 파이썬 경로
    ),
}
```

**2단계: 외부 Python 환경에 의존성 설치**
- `.external/` 환경에 필요한 패키지(PyQt, numpy 등) 설치

**3단계: 실행**
- `python main.py` 실행 시 IPC 매니저가 시작되고
  `python -m workers._run_external ...` 방식으로 외부 워커가 자동 실행됩니다.
- 외부로 지정된 워커는 main 프로세스에서는 실행되지 않습니다.

### 공유 메모리 스키마 확장

```python
# sharedmemory/shm_schema.py
from dataclasses import dataclass
import numpy as np

@dataclass
class MY_DATA:
    value: np.float32 = 0.0
    counter: np.int32 = 0
    timestamp: np.float64 = 0.0

# main.py에서 사용
shm_name = {
    "camera_shm": "camera_shm",
    "my_data_shm": "my_data_shm",
}

main_shms = _init_shared_memory(shm_name, shared_lock)
```

### GUI 확장

gui.ui를 Qt Designer로 열어 버튼, 레이블 등을 추가하고, `gui_controller.py`에서 신호 연결:

```python
# ui/gui_controller.py
class EventControllerWindow(QtWidgets.QMainWindow):
    def __init__(self, bus, shared_memory):
        super().__init__()
        # ... 기존 코드 ...
        self.myButton.clicked.connect(self._on_my_button_clicked)
    
    def _on_my_button_clicked(self) -> None:
        # 새로운 이벤트 처리
        self.bus.set_level("my_event")
```

## ⚙️ 설정 옵션

### Worker 활성화/비활성화

```python
WORKER_SPECS: Dict[str, Dict[str, Any]] = {
    "single": {"builder": build_single, "enabled": True, "daemon": True},
    "dual": {"builder": build_dual, "enabled": False, "daemon": True},  # 비활성
}
```

### Hz(주기) 조정

```python
def build_single(ctx: WorkerContext) -> SingleExampleWorker:
    return SingleExampleWorker(ctx, hz=20.0)  # 20Hz로 변경

def build_dual(ctx: WorkerContext) -> DualExampleWorker:
    return DualExampleWorker(ctx, slow_hz=5.0, fast_hz=50.0)  # 듀얼 레이트
```

## 📝 주요 설계 원칙

1. **단일 책임**: 각 워커는 하나의 책임만 수행
2. **이벤트 기반**: 폴링이 아닌 이벤트 기반 상태 전이
3. **스냅샷 기반**: 각 주기마다 현재 이벤트 상태의 스냅샷을 읽음
4. **프로세스 격리**: 워커는 독립 프로세스로 실행되어 안정성 증대
5. **메모리 안전**: 공유 메모리는 Lock으로 보호
6. **GUI/워커 분리**: 워커는 별도 프로세스, GUI는 main 프로세스에서 EventBus 제어
7. **간단함**: Level 이벤트만 사용하여 구조를 단순하게 유지

## 📚 참고 문서

- [Python multiprocessing 공식 문서](https://docs.python.org/3/library/multiprocessing.html)
- [PyQt5 공식 문서](https://www.riverbankcomputing.com/static/Docs/PyQt5/)
- [상태 머신 패턴](https://en.wikipedia.org/wiki/Finite-state_machine)
