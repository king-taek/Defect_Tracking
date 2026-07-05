"""로딩(작업 중) 오버레이 — 부모 위에 반투명 막 + 중앙 카드(스피너·메시지·진행바).

무거운 작업이 진행되는 동안 '멈춘 것'처럼 보이지 않도록, 애니메이션 스피너와 (가능하면)
진행도를 표시한다. 부모의 크기에 맞춰 자동으로 덮는다.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class BusyOverlay(QWidget):
    """부모를 덮는 로딩 오버레이. start/stop/set_progress 로 제어."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._host = parent
        self.setVisible(False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)  # 클릭 삼켜 조작 방지

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        card = QFrame()
        card.setObjectName("panel")
        card.setFixedWidth(340)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(22, 20, 22, 20)
        cl.setSpacing(10)
        cl.setAlignment(Qt.AlignCenter)

        self._spinner = QLabel(_SPINNER[0])
        self._spinner.setAlignment(Qt.AlignCenter)
        self._spinner.setStyleSheet(f"font-size:26px; color:{theme.NEON};")
        cl.addWidget(self._spinner)

        self._msg = QLabel("처리 중…")
        self._msg.setAlignment(Qt.AlignCenter)
        self._msg.setWordWrap(True)
        self._msg.setStyleSheet(f"color:{theme.TEXT}; font-weight:600;")
        cl.addWidget(self._msg)

        self._bar = QProgressBar()
        self._bar.setTextVisible(True)
        self._bar.setVisible(False)
        cl.addWidget(self._bar)

        lay.addWidget(card)

        self._i = 0
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._tick)

        self._host.installEventFilter(self)

    # ---- 표시 제어 ---------------------------------------------------
    def start(self, message: str = "처리 중…", determinate: bool = False) -> None:
        self._msg.setText(message)
        self._bar.setVisible(determinate)
        if determinate:
            self._bar.setRange(0, 100)
            self._bar.setValue(0)
        self._reposition()
        self.setVisible(True)
        self.raise_()
        if not self._timer.isActive():
            self._timer.start()

    def set_message(self, message: str) -> None:
        self._msg.setText(message)

    def set_progress(self, cur: int, total: int) -> None:
        if total <= 0:
            return
        if not self._bar.isVisible():
            self._bar.setVisible(True)
        self._bar.setRange(0, 100)
        self._bar.setValue(int(round(min(cur, total) / total * 100)))

    def stop(self) -> None:
        self._timer.stop()
        self.setVisible(False)

    # ---- 내부 ---------------------------------------------------------
    def _tick(self) -> None:
        self._i = (self._i + 1) % len(_SPINNER)
        self._spinner.setText(_SPINNER[self._i])

    def _reposition(self) -> None:
        self.setGeometry(self._host.rect())

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._host and event.type() == QEvent.Resize and self.isVisible():
            self._reposition()
        return False

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(8, 11, 16, 170))  # 반투명 어두운 막
        painter.end()
