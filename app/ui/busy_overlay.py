"""로딩(작업 중) 오버레이 — 부모 위 반투명 막 + 중앙 카드(부드러운 스피너·메시지·진행바).

무거운 작업이 진행되는 동안 '멈춘 것'처럼 보이지 않도록, 부드럽게 회전하는 네온 링과
(가능하면) 진행도를 표시한다. 부모의 크기에 맞춰 자동으로 덮는다.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QEventLoop, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme


class _SpinnerRing(QWidget):
    """부드럽게 회전하는 네온 원호(브라유 글리프보다 매끄럽게)."""

    def __init__(self, parent: Optional[QWidget] = None, size: int = 52):
        super().__init__(parent)
        self._angle = 0.0
        self.setFixedSize(size, size)

    def advance(self, deg: float) -> None:
        self._angle = (self._angle + deg) % 360.0
        self.update()

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        m = 7
        rect = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        # 바탕 트랙(희미한 전체 원)
        track = QPen(QColor(theme.NEON_SOFT))
        track.setWidth(5)
        track.setCapStyle(Qt.RoundCap)
        p.setPen(track)
        p.drawArc(rect, 0, 360 * 16)
        # 밝은 회전 호(약 110°)
        arc = QPen(QColor(theme.NEON))
        arc.setWidth(5)
        arc.setCapStyle(Qt.RoundCap)
        p.setPen(arc)
        p.drawArc(rect, int(-self._angle * 16), 110 * 16)
        p.end()


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
        card.setObjectName("busyCard")
        card.setFixedWidth(320)
        # 은은한 네온 테두리 + 살짝 밝은 배경으로 카드를 또렷하게.
        card.setStyleSheet(
            "QFrame#busyCard {"
            f" background:{theme.BG_ELEV};"
            f" border:1px solid {theme.NEON_SOFT};"
            " border-radius:14px; }"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(26, 24, 26, 22)
        cl.setSpacing(14)
        cl.setAlignment(Qt.AlignCenter)

        self._ring = _SpinnerRing()
        cl.addWidget(self._ring, alignment=Qt.AlignHCenter)

        self._base_msg = "처리 중"
        self._msg = QLabel(self._base_msg)
        self._msg.setAlignment(Qt.AlignCenter)
        self._msg.setWordWrap(True)
        self._msg.setStyleSheet(
            f"color:{theme.TEXT}; font-weight:700; font-size:14px; border:none;"
        )
        cl.addWidget(self._msg)

        self._sub = QLabel("잠시만 기다려 주세요")
        self._sub.setAlignment(Qt.AlignCenter)
        self._sub.setStyleSheet(
            f"color:{theme.TEXT_DIM}; font-size:11px; border:none;"
        )
        cl.addWidget(self._sub)

        self._bar = QProgressBar()
        self._bar.setTextVisible(True)
        self._bar.setFixedHeight(14)
        self._bar.setVisible(False)
        cl.addWidget(self._bar)

        lay.addWidget(card)

        self._dot = 0
        self._frame = 0
        self._timer = QTimer(self)
        self._timer.setInterval(40)  # 부드러운 회전(≈25fps)
        self._timer.timeout.connect(self._tick)

        self._host.installEventFilter(self)

    # ---- 표시 제어 ---------------------------------------------------
    def start(self, message: str = "처리 중", determinate: bool = False) -> None:
        self._base_msg = message.rstrip("… .")
        self._msg.setText(self._base_msg)
        self._sub.setVisible(not determinate)
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
        self._base_msg = message.rstrip("… .")
        self._msg.setText(self._base_msg + "." * self._dot)

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

    def pump(self) -> None:
        """무거운 메인 스레드 작업 중에도 스피너가 계속 회전하도록 이벤트 루프를 잠깐 돌린다.

        사용자 입력 이벤트는 제외해 작업 도중 재진입(레이어 재변경 등)을 막고,
        타이머·페인트 이벤트만 처리해 애니메이션 프레임을 갱신한다.
        """
        if not self.isVisible():
            return
        QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

    # ---- 내부 ---------------------------------------------------------
    def _tick(self) -> None:
        self._ring.advance(14)  # 회전
        self._frame += 1
        if self._frame % 9 == 0:  # 메시지 말줄임(…) 애니메이션은 느리게
            self._dot = (self._dot + 1) % 4
            self._msg.setText(self._base_msg + "." * self._dot)

    def _reposition(self) -> None:
        self.setGeometry(self._host.rect())

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._host and event.type() == QEvent.Resize and self.isVisible():
            self._reposition()
        return False

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(8, 11, 16, 185))  # 반투명 어두운 막
        painter.end()
