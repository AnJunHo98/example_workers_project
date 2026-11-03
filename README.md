# Example Workers Project (Single/Dual rate + unified events + event-driven state machine)

English | [한국어](README.ko.md)

An event-driven state machine framework built on multi-process workers. Every worker reads events and moves between states in the same way.

## Features

### 1. Unified event system
- **Level events** keep state with `mp.Event` (ready, start, shutdown)
- Every worker reads events the same way, through `EventBus.read_snapshot()`
- Safe multi-process synchronization at the OS level

### 2. Worker types
- **Single-rate worker**: a loop at a fixed rate (Hz)
- **Dual-rate worker**: a slow loop (`slow_hz`) combined with a fast loop (`fast_hz`)
- **Keyboard worker**: triggers events from console input

### 3. State machine
- Every worker uses the shared transition function `core.state_machine.step()`
- Event-driven transitions (WAIT_CONNECT → WAIT_START → RUN/PAUSE → EXIT)
- Worker behaviour goes in `step_once()` (single-rate) or `do_slow()` / `do_fast()` (dual-rate)

### 4. Qt GUI controller
- Live worker status (ALIVE/STOPPED)
- Manual control of the events (ready, start, shutdown)
- Shows the EventBus level snapshot

### 5. Shared memory
- Fast data sharing between workers
- Structured memory defined by schemas
- Lock-based concurrency control

### 6. IPC-based extension
- Event and data communication goes through IPC
- Easy to extend to workers that run in a different Python environment (another venv, a container, ...) on the same host

## Installation and running

### Create the main virtual environment (.init)
```bash
python -m venv .init
source .init/bin/activate
```

### Create the external virtual environment (.external)
```bash
python -m venv .external
```

### Install the required packages
```bash
pip install PyQt5 logging_mp numpy
# or with PyQt6
pip install PyQt6 logging_mp numpy
```

### Run
```bash
python main.py
```

## Repository layout

```
example_workers_project/
├── .external/                       # venv for external workers (create it yourself, git-ignored)
├── .init/                           # venv for the main launcher (create it yourself, git-ignored)
├── main.py                          # launcher (starts workers, manages the GUI, cleanup)
├── core/
│   ├── __init__.py
│   ├── events.py                    # EventBus and LEVEL_EVENTS
│   ├── rate.py                      # fixed-rate loop helper
│   ├── state_machine.py             # shared state transition (step)
│   └── worker_base.py               # WorkerContext, BaseWorker, SingleRateWorker, DualRateWorker
├── ipc/
│   ├── __init__.py
│   └── manager.py                   # IPC manager
├── workers/
│   ├── __init__.py
│   ├── _registry.py                 # worker registry
│   ├── _single_example.py           # single-rate worker example
│   ├── _dual_example.py             # dual-rate worker example
│   ├── _keyboard_worker.py          # console input worker
│   └── _run_external.py             # runs a worker in an external process
├── ui/
│   ├── gui_controller.py            # main Qt GUI controller
│   └── gui.ui                       # Qt Designer layout
├── sharedmemory/
│   ├── __init__.py
│   ├── shmManager.py                # shared memory manager
│   ├── shm_schema.py                # memory schemas (CAMERA, ...)
│   └── shm_init_clean.py            # init/cleanup functions
└── README.md
```

## Concurrency and safety

- **Level events**: OS-level synchronization through `mp.Event`
- **Shared memory**: critical sections protected by locks
- **Dual-rate worker**: state transitions are protected by an internal lock (use a separate lock for your own shared data)
- **GUI**: thread safety through Qt signals and slots
- **Watchdog**: a GUI timer checks worker status every 200 ms

## Customization

### Add a worker

**Step 1: define the worker class**
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
            # main logic
            logger.info("[MyWorker] Running...")
```

**Step 2: register it in `workers/_registry.py`**
```python
# workers/_registry.py
def _build_my_worker(ctx: WorkerContext):
    from workers.my_worker import MyWorker
    return MyWorker(ctx, hz=10.0)

WORKER_SPECS: Dict[str, WorkerSpec] = {
    # ... existing workers
    "my_worker": WorkerSpec(name="my_worker", builder=_build_my_worker, enabled=True, daemon=True),
}
```
- `main.py` reads `WORKER_SPECS` from `workers/_registry.py` and starts the workers.

### Run a worker in an external process

An external worker runs in another Python environment (for example the `.external` venv) and connects to the same EventBus, locks and shared memory through IPC.

**Step 1: mark the worker as external**
```python
# workers/_registry.py
WORKER_SPECS = {
    "external": WorkerSpec(
        name="external",
        builder=_build_external,
        enabled=True,
        daemon=True,
        external=True,                # run in an external process
        python=".external/bin/python" # Python interpreter to use
    ),
}
```

**Step 2: install its dependencies in the external environment**
- Install the packages it needs (PyQt, numpy, ...) into `.external/`

**Step 3: run**
- `python main.py` starts the IPC manager and launches the external worker with `python -m workers._run_external ...`.
- A worker marked as external does not run inside the main process.

### Extend the shared memory schema

```python
# sharedmemory/shm_schema.py
import numpy as np

MY_DATA = [
    ("value", (1,), np.float32),
    ("counter", (1,), np.int32),
    ("timestamp", (1,), np.float64),
]

# Entries in SHM_SPECS are picked up automatically by main.py and shm_init_clean.py
SHM_SPECS = (
    # ... existing specs ...
    ShmSpec(key="my_data_shm", schema=MY_DATA, lock_key="my_data_lock"),
)
```

### Extend the GUI

Open `gui.ui` in Qt Designer to add buttons, labels and so on, then connect the signals in `gui_controller.py`:

```python
# ui/gui_controller.py
class EventControllerWindow(QtWidgets.QMainWindow):
    def __init__(self, bus, shared_memory):
        super().__init__()
        # ... existing code ...
        self.myButton.clicked.connect(self._on_my_button_clicked)

    def _on_my_button_clicked(self) -> None:
        # handle the new event
        self.bus.set_level("my_event")
```

## Configuration

### Enable or disable workers

```python
# workers/_registry.py
WORKER_SPECS: Dict[str, WorkerSpec] = {
    "single": WorkerSpec(name="single", builder=_build_single, enabled=True, daemon=True),
    "dual": WorkerSpec(name="dual", builder=_build_dual, enabled=False, daemon=True),  # disabled
}
```

### Change the rate (Hz)

```python
# workers/_registry.py
def _build_single(ctx: WorkerContext):
    from workers._single_example import SingleExampleWorker
    return SingleExampleWorker(ctx, hz=20.0)  # 20 Hz

def _build_dual(ctx: WorkerContext):
    from workers._dual_example import DualExampleWorker
    return DualExampleWorker(ctx, slow_hz=5.0, fast_hz=50.0)  # dual rate
```

## Design principles

1. **Single responsibility**: each worker does one job
2. **Event-driven**: state changes are driven by events, not polling
3. **Snapshots**: each cycle reads a snapshot of the current event state
4. **Process isolation**: workers run as separate processes for stability
5. **Memory safety**: shared memory is protected by locks
6. **GUI/worker separation**: workers run in their own processes; the GUI controls the EventBus from the main process
7. **Simplicity**: only level events, to keep the structure simple

The same `core/`, `ipc/`, `sharedmemory/` and `workers/` skeleton is also used in some of the author's other (private) research projects.

## References

- [Python multiprocessing documentation](https://docs.python.org/3/library/multiprocessing.html)
- [PyQt5 documentation](https://www.riverbankcomputing.com/static/Docs/PyQt5/)
- [Finite-state machine](https://en.wikipedia.org/wiki/Finite-state_machine)

## Status

An example/template framework written between December 2025 and January 2026. There have been no commits since 2026-01-05.

## License

MIT License — see [LICENSE](LICENSE).
