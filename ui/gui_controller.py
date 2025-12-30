"""PyQt 기반 이벤트 컨트롤러(UI는 이벤트만 관리).

- 워커 프로세스 생성/시작/종료는 main.py(런처)가 담당
- 본 UI는 EventBus(level)에 대해 set/clear만 수행

실행 예시:
  python -m example_workers.main

의존성:
  pip install PyQt5 logging_mp
  (또는 PyQt6)
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from core.events import LEVEL_EVENTS, EventBus
from sharedmemory.shmManager import SharedMemoryManager


# ---- Qt binding (PyQt5 우선, 없으면 PyQt6) ---------------------------------

_QT_API: str
try:
    from PyQt5 import QtCore, QtWidgets, uic  # type: ignore

    _QT_API = "PyQt5"
except Exception:  # pragma: no cover
    from PyQt6 import QtCore, QtWidgets, uic  # type: ignore

    _QT_API = "PyQt6"


class EventControllerWindow(QtWidgets.QMainWindow):
    """EventBus를 버튼으로 제어하는 윈도우."""

    def __init__(self, bus: EventBus, shared_memory: Mapping[str, SharedMemoryManager]) -> None:
        super().__init__()

        ui_path = Path(__file__).with_name("gui.ui")
        uic.loadUi(str(ui_path), self)

        self.bus = bus

        # --- UI: 워커 제어 버튼은 main.py가 담당하므로 비활성화(표시만 유지) ---
        # (기존 ui 파일을 재사용하되, 오동작 방지)
        if hasattr(self, "startWorkersButton"):
            self.startWorkersButton.setEnabled(False)
        if hasattr(self, "singleWorkerStatus"):
            self.singleWorkerStatus.setText("managed by main")
        if hasattr(self, "dualWorkerStatus"):
            self.dualWorkerStatus.setText("managed by main")

        # --- level events ---
        self.readyButton.toggled.connect(self._on_ready_toggled)  # type: ignore[attr-defined]
        self.startButton.toggled.connect(self._on_start_toggled)  # type: ignore[attr-defined]

        # shutdown은 '워커 제어'가 아니라 level event set이므로 허용
        self.shutdownAllButton.clicked.connect(self._on_shutdown_clicked)  # type: ignore[attr-defined]

        # clear level(ready/start)
        self.clearLevelButton.clicked.connect(self._on_clear_level)  # type: ignore[attr-defined]

        # periodic refresh
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

        self.statusbar.showMessage(f"Qt={_QT_API} | controlling shared EventBus")  # type: ignore[attr-defined]
        self.refresh()

    # ---- main.py가 호출해 워커 상태를 표시(선택 기능) ------------------------
    def set_worker_status(self, alive: Mapping[str, bool]) -> None:
        """main.py에서 워커 alive 상태를 UI에 반영(표시만)."""
        if hasattr(self, "singleWorkerStatus") and "single" in alive:
            self.singleWorkerStatus.setText("ALIVE" if alive["single"] else "STOPPED")
        if hasattr(self, "dualWorkerStatus") and "dual" in alive:
            self.dualWorkerStatus.setText("ALIVE" if alive["dual"] else "STOPPED")
        if hasattr(self, "keyboardWorkerStatus") and "keyboard" in alive:
            self.keyboardWorkerStatus.setText("ALIVE" if alive["keyboard"] else "STOPPED")

    # ---- level handlers ---------------------------------------------------
    def _on_ready_toggled(self, checked: bool) -> None:
        if checked:
            self.bus.set_level("ready")
        else:
            self.bus.clear_level("ready")

    def _on_start_toggled(self, checked: bool) -> None:
        if checked:
            self.bus.set_level("start")
        else:
            self.bus.clear_level("start")

    def _on_shutdown_clicked(self) -> None:
        self.bus.set_level("shutdown")
        self.refresh()

    def _on_clear_level(self) -> None:
        # shutdown은 일반적으로 exit 플로우이므로 여기서는 건드리지 않음
        self.bus.clear_level("ready")
        self.bus.clear_level("start")
        self.refresh()

    # ---- refresh ----------------------------------------------------------
    def refresh(self) -> None:
        # level state
        levels = {k: self.bus.is_level_set(k) for k in LEVEL_EVENTS}

        # update checkboxes without re-trigger
        try:
            self.readyButton.blockSignals(True)  # type: ignore[attr-defined]
            self.startButton.blockSignals(True)  # type: ignore[attr-defined]
            self.readyButton.setChecked(levels.get("ready", False))  # type: ignore[attr-defined]
            self.startButton.setChecked(levels.get("start", False))  # type: ignore[attr-defined]
        finally:
            self.readyButton.blockSignals(False)  # type: ignore[attr-defined]
            self.startButton.blockSignals(False)  # type: ignore[attr-defined]

        # shutdown label
        self.shutdownStateLabel.setText("SET" if levels.get("shutdown", False) else "CLEAR")  # type: ignore[attr-defined]

        # snapshot text
        lines = []
        lines.append("[level]")
        for k in LEVEL_EVENTS:
            lines.append(f"  {k:12s}: {levels.get(k)}")

        self.snapshotPlainText.setPlainText("\n".join(lines))  # type: ignore[attr-defined]

    def closeEvent(self, event) -> None:  # type: ignore[override]
        # UI 종료 시 기본 동작: shutdown set (main.py가 join/cleanup 수행)
        try:
            self.bus.set_level("shutdown")
        except Exception:
            pass
        event.accept()
