"""로딩(작업 중) 오버레이 - 부모 위 반투명 막 + 중앙 카드(부드러운 스피너·메시지·진행바).

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

from qfluentwidgets import isDarkTheme, qconfig

from app.ui import theme


def _is_dark() -> bool:
    return bool(isDarkTheme())


def _scrim_color() -> QColor:
    """시트 뒤를 덮는 스크림. 두 테마 모두 검정 계열이되 다크에서 조금 더 진하게."""
    return QColor(0, 0, 0, 140 if _is_dark() else 82)


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
        # 색은 그릴 때마다 토큰에서 읽는다. 생성 시점에 굳히면 테마 전환을 따라가지 못한다.
        tokens = theme.fluent_tokens(_is_dark())
        track = QPen(QColor(theme.flatten(tokens["divider"], tokens["card"])))
        track.setWidth(5)
        track.setCapStyle(Qt.RoundCap)
        p.setPen(track)
        p.drawArc(rect, 0, 360 * 16)
        # 밝은 회전 호(약 110°)
        arc = QPen(QColor(tokens["accentFill"]))
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
        self._card = card
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
        cl.addWidget(self._msg)

        self._sub = QLabel("잠시만 기다려 주세요")
        self._sub.setAlignment(Qt.AlignCenter)
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
        self._apply_tokens()
        qconfig.themeChanged.connect(self._apply_tokens)

    def _apply_tokens(self, *_args) -> None:
        """카드·문구 색을 현재 테마 토큰으로 다시 칠한다.

        여기 위젯은 순수 Qt(QFrame/QLabel)라 setStyleSheet 를 써도 된다. Fluent 위젯에
        직접 거는 것만 금지다.
        """
        tokens = theme.fluent_tokens(_is_dark())
        border = theme.flatten(tokens["cardBorder"], tokens["layer"])
        self._card.setStyleSheet(
            "QFrame#busyCard {"
            f" background:{tokens['card']};"
            f" border:1px solid {border};"
            f" border-radius:{theme.RADIUS['card']}px; }}"
        )
        self._msg.setStyleSheet(
            f"color:{theme.flatten(tokens['txt1'], tokens['card'])};"
            " font-weight:600; font-size:14px; border:none;"
        )
        self._sub.setStyleSheet(
            f"color:{theme.flatten(tokens['txt2'], tokens['card'])};"
            " font-size:12px; border:none;"
        )
        self.update()

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
        # 호스트가 파괴된 뒤에도 필터 등록이 남아 shiboken 이 __init__ 없이 재래핑한
        # 인스턴스로 호출될 수 있다(_host 없음) - 그런 경우 조용히 무시한다.
        host = getattr(self, "_host", None)
        if host is not None and obj is host and event.type() == QEvent.Resize and self.isVisible():
            self._reposition()
        return False

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), _scrim_color())  # 반투명 막(과하게 어둡지 않게)
        painter.end()
