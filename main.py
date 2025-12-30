from __future__ import annotations

import multiprocessing as mp
import subprocess
import sys
import time
from typing import Callable, Dict
from pathlib import Path
import os
import logging_mp
logger = logging_mp.get_logger(__name__)
logging_mp.basic_config(level=logging_mp.INFO)


def _ensure_mp_start_method() -> None:
    """logging_mp는 fork 기반으로 큐를 공유하는 편이 자연스러우므로 가능하면 fork 사용."""
    if "fork" not in mp.get_all_start_methods():
        return
    try:
        mp.set_start_method("fork")
    except (RuntimeError, ValueError):
        # 이미 설정되었거나 지원되지 않는 경우 그대로 둔다.
        pass


_ensure_mp_start_method()


def _configure_qt_plugin_path() -> str | None:
    """PyQt 플러그인 경로를 env에 써넣고 경로를 반환."""
    plugin_path: str | None = None
    try:
        import PyQt5  # type: ignore

        plugin_path = str(Path(PyQt5.__file__).resolve().parent / "Qt5" / "plugins")
    except Exception:  # pragma: no cover
        try:
            import PyQt6  # type: ignore

            plugin_path = str(Path(PyQt6.__file__).resolve().parent / "Qt6" / "plugins")
        except Exception:
            plugin_path = None

    if plugin_path:
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = plugin_path
        os.environ["QT_PLUGIN_PATH"] = plugin_path
    return plugin_path


_configure_qt_plugin_path()

from core.events import EventBus, create_shared_events
from core.worker_base import WorkerContext
from ipc.manager import encode_authkey, start_ipc_server
from workers._registry import (
    WorkerSpec,
    get_external_worker_python,
    get_worker_spec,
    get_worker_specs,
    list_worker_names,
    parse_external_workers_env,
)

from sharedmemory.shmManager import SharedMemoryManager
from sharedmemory.shm_init_clean import _cleanup_shared_memory, _init_shared_memory
from sharedmemory.shm_schema import SHM_SPECS, build_shm_name_map


def _run_worker(worker_ctor: Callable[[WorkerContext], object], ctx: WorkerContext) -> None:
    """프로세스 엔트리포인트."""
    w = worker_ctor(ctx)
    w.run()  # type: ignore[attr-defined]


def _proc_is_alive(proc: object) -> bool:
    if hasattr(proc, "is_alive"):
        return bool(proc.is_alive())
    if hasattr(proc, "poll"):
        return proc.poll() is None
    return False


def _proc_join(proc: object, timeout: float) -> None:
    if hasattr(proc, "join"):
        proc.join(timeout=timeout)
        return
    if hasattr(proc, "wait"):
        try:
            proc.wait(timeout=timeout)
        except Exception:
            pass


def _proc_terminate(proc: object) -> None:
    if hasattr(proc, "terminate"):
        try:
            proc.terminate()
        except Exception:
            pass


def _start_external_worker(
    *,
    name: str,
    python: str,
    ipc_host: str,
    ipc_port: int,
    ipc_auth: str,
    lock_names: list[str],
    shm_name: dict[str, str],
) -> subprocess.Popen | None:
    cmd = [
        python,
        "-m",
        "workers._run_external",
        "--worker",
        name,
        "--ipc-host",
        ipc_host,
        "--ipc-port",
        str(ipc_port),
        "--ipc-auth",
        ipc_auth,
    ]
    for lock_name in lock_names:
        cmd.extend(["--lock", lock_name])
    for key, value in shm_name.items():
        cmd.extend(["--shm", f"{key}={value}"])
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    logger.info("[MAIN] starting external %s: %s", name, " ".join(cmd))
    try:
        return subprocess.Popen(cmd, cwd=Path(__file__).resolve().parent, env=env)
    except FileNotFoundError:
        logger.exception("[MAIN] worker python not found for %s: %s", name, python)
        return None
    except Exception:
        logger.exception("[MAIN] Failed to start external worker %s.", name)
        return None


def _start_workers(
    bus: EventBus,
    *,
    shared_lock: dict[str, object],
    shm_name: dict[str, str],
    shared_memory: dict[str, SharedMemoryManager],
    worker_specs: Dict[str, WorkerSpec],
) -> Dict[str, object]:
    procs: Dict[str, object] = {}

    def ctx(name: str) -> WorkerContext:
        return WorkerContext(
            name=name,
            bus=bus,
            shared_lock=shared_lock,
            shm_name=shm_name,
            shared_memory=shared_memory,
        )

    for name, spec in worker_specs.items():
        if spec.enabled is False:
            continue

        builder = spec.builder
        daemon = bool(spec.daemon)
        procs[name] = mp.Process(
            target=_run_worker,
            args=(builder, ctx(name)),
            daemon=daemon,
        )

    for p in procs.values():
        p.start()

    return procs


def _join_workers(
    procs: Dict[str, object],
    *,
    timeout_s: float = 30.0,
    shm_name: dict[str, str],
    main_shms: dict[str, SharedMemoryManager],
) -> None:
    deadline = time.time() + float(timeout_s)
    for p in procs.values():
        if not _proc_is_alive(p):
            continue
        remain = max(0.0, deadline - time.time())
        _proc_join(p, timeout=remain)

    # best-effort terminate
    for p in procs.values():
        if _proc_is_alive(p):
            _proc_terminate(p)
    for key, mgr in main_shms.items():
        try:
            mgr.main_unlink()
            logger.info("[MAIN] unlinked SHM %s", key)
        except FileNotFoundError:
            pass
        except Exception:
            logger.exception("[MAIN] Failed to unlink SHM %s", key)
    _cleanup_shared_memory(shm_name)


def _run_gui(
    bus: EventBus,
    procs: Dict[str, object],
    shared_memory: dict[str, SharedMemoryManager],
) -> None:
    """Qt 이벤트 루프에서 워커 상태 감시 + UI 표시.

    주의:
      - Qt 초기화 이후에는 fork/spawn을 추가로 하지 않는 것이 안전하다.
      - 따라서 workers는 main()에서 먼저 start 한 뒤, 여기서 GUI를 띄운다.
    """

    # PyQt import 전에 경로를 교체해야 gui_controller import 시에도 적용된다.
    plugin_path = _configure_qt_plugin_path()

    try:
        from PyQt5 import QtCore, QtWidgets  # type: ignore

        _qt = "PyQt5"
    except Exception:  # pragma: no cover
        from PyQt6 import QtCore, QtWidgets  # type: ignore

        _qt = "PyQt6"

    from ui.gui_controller import EventControllerWindow

    # reapply Qt plugin path after PyQt import (cv2 might have reset it again).
    plugin_path = _configure_qt_plugin_path()

    if plugin_path:
        # Qt가 사용할 플러그인 탐색 경로를 명시적으로 지정해 cv2 경로를 배제한다.
        QtCore.QCoreApplication.setLibraryPaths([plugin_path])
    app = QtWidgets.QApplication(sys.argv)
    if plugin_path:
        QtCore.QCoreApplication.setLibraryPaths([plugin_path])
    win = EventControllerWindow(bus, shared_memory)
    win.statusbar.showMessage(f"Qt={_qt} | workers started in main.py")  # type: ignore[attr-defined]
    win.show()

    timer = QtCore.QTimer()
    timer.setInterval(200)

    def watchdog() -> None:
        alive = {k: _proc_is_alive(p) for k, p in procs.items()}
        win.set_worker_status(alive)

        # 워커 하나라도 죽으면 종료
        if alive and (not all(alive.values())):
            bus.set_level("shutdown")

        # shutdown set이면 GUI도 종료
        if bus.is_level_set("shutdown"):
            app.quit()

    timer.timeout.connect(watchdog)
    timer.start()

    watchdog()

    if hasattr(app, "exec"):
        app.exec()
    else:  # pragma: no cover
        app.exec_()  # type: ignore[attr-defined]


def main(argv=None) -> None:
    mp.freeze_support()

    ipc_manager, ipc_host, ipc_port, ipc_authkey = start_ipc_server()
    ipc_auth = encode_authkey(ipc_authkey)
    logger.info("[MAIN] IPC manager started at %s:%s", ipc_host, ipc_port)

    # shared EventBus
    level = create_shared_events(ipc_manager)
    bus = EventBus(level)

    shared_lock = {spec.lock_key: ipc_manager.get_lock(spec.lock_key) for spec in SHM_SPECS}
    shm_name = build_shm_name_map()
    
    main_shms = _init_shared_memory(shm_name, shared_lock)

    external_workers = parse_external_workers_env()
    known_workers = set(list_worker_names())
    unknown_workers = sorted(external_workers - known_workers)
    if unknown_workers:
        logger.warning("[MAIN] Unknown external workers ignored: %s", ", ".join(unknown_workers))
    external_workers = external_workers & known_workers
    worker_specs = get_worker_specs(external_workers)

    # 항상 keyboard + (single, dual) 워커를 먼저 실행
    procs = _start_workers(
        bus,
        shared_lock=shared_lock,
        shm_name=shm_name,
        shared_memory=main_shms,
        worker_specs=worker_specs,
    )

    if external_workers:
        lock_names = list(shared_lock.keys())
        for name in sorted(external_workers):
            spec = get_worker_spec(name)
            if spec.enabled is False:
                logger.info("[MAIN] External worker %s disabled; skipping.", name)
                continue
            python = get_external_worker_python(name)
            if not python:
                logger.warning("[MAIN] External worker %s missing python path.", name)
                continue
            ext_proc = _start_external_worker(
                name=name,
                python=python,
                ipc_host=ipc_host,
                ipc_port=ipc_port,
                ipc_auth=ipc_auth,
                lock_names=lock_names,
                shm_name=shm_name,
            )
            if ext_proc is not None:
                procs[name] = ext_proc
            else:
                logger.warning("[MAIN] External worker %s failed to start.", name)
    
    try:
        # 항상 GUI 실행 (GUI가 이벤트만 제어하고, 워커는 main.py가 관리)
        _run_gui(bus, procs, shared_memory=main_shms)
    finally:
        # GUI 종료(창 닫기) 또는 예외 시 항상 shutdown 후 정리
        try:
            bus.set_level("shutdown")
        except Exception:
            pass

        _join_workers(
            procs,
            timeout_s=30.0,
            shm_name=shm_name,
            main_shms=main_shms,
        )
        logger.info("[main] exit")
        try:
            logging_mp.stop_listener_process()
        except Exception:
            pass
        try:
            ipc_manager.shutdown()
        except Exception:
            pass



if __name__ == "__main__":
    main()
