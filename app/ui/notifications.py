"""비차단 알림 배너(토스트) — 매끄러운 오류/안내 처리 (문서 Section 9 / 사용성).

화면을 막는 모달 팝업 대신, 창 상단에 부드럽게 나타났다 사라지는 인라인 배너를 사용한다.
info/success/warn/error 레벨별 색상, 선택적 액션 버튼, 자동 소멸을 지원한다.
배너는 비차단이므로 작업 흐름이 끊기지 않는다.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from app.ui import theme

_LEVEL_COLORS = {
    "info": (theme.NEON_DIM, "#ffffff"),
    "success": ("#15803d", "#ffffff"),
    "warn": ("#b45309", "#ffffff"),
    "error": ("#b00020", "#ffffff"),
}

_ICONS = {"info": "ℹ", "success": "✓", "warn": "⚠", "error": "✕"}


class NotificationBanner(QFrame):
    """창 상단의 비차단 알림 배너."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("banner")
        self._action_cb: Optional[Callable[[], None]] = None
        self._build()

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)

        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(180)
        self._fade.setEasingCurve(QEasingCurve.InOutCubic)
        self._collapse = QPropertyAnimation(self, b"maximumHeight", self)
        self._collapse.setDuration(200)
        self._collapse.setEasingCurve(QEasingCurve.InOutCubic)
        self._group = QParallelAnimationGroup(self)
        self._group.addAnimation(self._fade)
        self._group.addAnimation(self._collapse)

        self._auto_hide = QTimer(self)
        self._auto_hide.setSingleShot(True)
        self._auto_hide.timeout.connect(self.dismiss)

        self.setMaximumHeight(0)
        self.setVisible(False)

    def _build(self) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 10, 8)
        lay.setSpacing(10)
        self._icon = QLabel("")
        self._icon.setStyleSheet("font-weight:700; color:#ffffff; background:transparent;")
        self._label = QLabel("")
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._label.setStyleSheet("color:#ffffff; background:transparent;")
        self._action = QPushButton("")
        self._action.setCursor(Qt.PointingHandCursor)
        self._action.setVisible(False)
        self._action.clicked.connect(self._on_action)
        self._action.setStyleSheet(
            "QPushButton { color:#ffffff; background:rgba(255,255,255,0.18);"
            " border:1px solid rgba(255,255,255,0.45); border-radius:6px;"
            " padding:3px 10px; }"
            "QPushButton:hover { background:rgba(255,255,255,0.32); }"
        )
        self._close = QPushButton("✕")
        self._close.setCursor(Qt.PointingHandCursor)
        self._close.setFixedSize(22, 22)
        self._close.clicked.connect(self.dismiss)
        self._close.setStyleSheet(
            "QPushButton { color:#ffffff; background:transparent; border:none;"
            " font-size:13px; }"
            "QPushButton:hover { background:rgba(255,255,255,0.22); border-radius:11px; }"
        )

        lay.addWidget(self._icon)
        lay.addWidget(self._label, 1)
        lay.addWidget(self._action)
        lay.addWidget(self._close)

    def _on_action(self) -> None:
        cb = self._action_cb
        self.dismiss()
        if cb is not None:
            cb()

    def show_message(
        self,
        text: str,
        level: str = "info",
        *,
        action_text: Optional[str] = None,
        action: Optional[Callable[[], None]] = None,
        timeout_ms: int = 4500,
    ) -> None:
        """배너를 표시한다. timeout_ms<=0 이면 자동 소멸하지 않는다."""
        bg, _fg = _LEVEL_COLORS.get(level, _LEVEL_COLORS["info"])
        # 프레임 배경만 레벨별로 바꾸고, 자식(라벨/버튼) 스타일은 _build 에서 고정.
        self.setStyleSheet(
            f"QFrame#banner {{ background:{bg}; border:none; border-radius:8px; }}"
        )
        self._icon.setText(_ICONS.get(level, "ℹ"))
        self._label.setText(text)
        self._action_cb = action
        if action_text and action is not None:
            self._action.setText(action_text)
            self._action.setVisible(True)
        else:
            self._action.setVisible(False)

        self.setVisible(True)
        target = max(self.sizeHint().height(), 40)
        self._group.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(1.0)
        self._collapse.setStartValue(self.maximumHeight())
        self._collapse.setEndValue(target)
        self._group.start()
        # 오버레이로 부모 위에 떠서 표시 — 레이아웃을 밀지 않아 화면이 흔들리지 않는다.
        self.reposition()
        self.raise_()

        self._auto_hide.stop()
        if timeout_ms > 0:
            self._auto_hide.start(timeout_ms)

    def reposition(self) -> None:
        """부모 위 상단 중앙에 배너를 배치한다(오버레이). 부모 크기 변화 시 호출."""
        parent = self.parentWidget()
        if parent is None:
            return
        w = min(760, max(320, parent.width() - 40))
        self.setFixedWidth(w)
        self.move((parent.width() - w) // 2, 12)

    def dismiss(self) -> None:
        self._auto_hide.stop()
        if not self.isVisible():
            return
        self._group.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(0.0)
        self._collapse.setStartValue(self.maximumHeight())
        self._collapse.setEndValue(0)
        try:
            self._group.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._group.finished.connect(self._after_hide)
        self._group.start()

    def _after_hide(self) -> None:
        try:
            self._group.finished.disconnect(self._after_hide)
        except (RuntimeError, TypeError):
            pass
        if self._effect.opacity() <= 0.01:
            self.setVisible(False)
