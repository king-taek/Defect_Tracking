"""상단 기준 썸네일 스트립 (문서 Section 8.6).

기준 Layer 사진들의 (중앙 10% 확대) 썸네일을 가로로 나열한다.
클릭 시 해당 사진을 기준 defect 로 설정하고, 현재 선택 썸네일을 강조한다.

가로 휠을 쓰지 않도록 **세로 휠 → 가로 스크롤** 로 매핑한다(사용성).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QWidget

from app.ui.widgets import ClickableThumb


class ThumbnailStrip(QScrollArea):
    """기준 사진 썸네일 가로 스트립."""

    thumb_clicked = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(120)
        self.setToolTip("세로 휠로 좌우 스크롤 · 클릭하면 기준 사진 변경")
        # viewport 기본 흰색 제거 → 뒤의 패널(BG_PANEL)이 비치게
        self.setFrameShape(QScrollArea.NoFrame)
        self.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.viewport().setAutoFillBackground(False)
        self._container = QWidget()
        self._container.setObjectName("stripHost")
        self._container.setAutoFillBackground(False)
        self._container.setStyleSheet("#stripHost { background: transparent; }")
        self._layout = QHBoxLayout(self._container)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(8)
        self._layout.addStretch()
        self.setWidget(self._container)
        self._thumbs: list[ClickableThumb] = []
        self._current = -1
        # 부드러운 가로 스크롤 애니메이션
        self._scroll_anim = QPropertyAnimation(self.horizontalScrollBar(), b"value", self)
        self._scroll_anim.setDuration(220)
        self._scroll_anim.setEasingCurve(QEasingCurve.OutCubic)

    def _animate_scroll_to(self, target: int) -> None:
        """수평 스크롤바를 target 값으로 부드럽게 이동."""
        bar = self.horizontalScrollBar()
        target = max(bar.minimum(), min(bar.maximum(), target))
        if target == bar.value():
            return
        self._scroll_anim.stop()
        self._scroll_anim.setStartValue(bar.value())
        self._scroll_anim.setEndValue(target)
        self._scroll_anim.start()

    def clear(self) -> None:
        for t in self._thumbs:
            t.setParent(None)
            t.deleteLater()
        self._thumbs.clear()
        self._current = -1

    def set_items(
        self, captions: list[str], tooltips: Optional[list[str]] = None
    ) -> None:
        """기준 record 개수만큼 썸네일 placeholder 를 만든다."""
        self.clear()
        for i, cap in enumerate(captions):
            thumb = ClickableThumb(i)
            thumb.set_caption(cap)
            if tooltips and i < len(tooltips):
                thumb.set_tooltip(tooltips[i])
            thumb.clicked.connect(self.thumb_clicked)
            # stretch 앞에 삽입
            self._layout.insertWidget(self._layout.count() - 1, thumb)
            self._thumbs.append(thumb)

    def set_thumbnail(self, index: int, path: str) -> None:
        if 0 <= index < len(self._thumbs):
            self._thumbs[index].set_image(path)

    def set_status_marks(self, statuses: list[str]) -> None:
        """각 썸네일에 매칭 상태 점을 표시(full/partial/none)."""
        for i, t in enumerate(self._thumbs):
            t.set_status(statuses[i] if i < len(statuses) else "full")

    def set_marked(self, index: int, marked: bool) -> None:
        if 0 <= index < len(self._thumbs):
            self._thumbs[index].set_marked(marked)

    def set_current(self, index: int) -> None:
        if not (0 <= index < len(self._thumbs)):
            return
        for i, t in enumerate(self._thumbs):
            t.set_selected(i == index)
        self._current = index
        self._ensure_visible(index)

    def _ensure_visible(self, index: int) -> None:
        """선택 썸네일이 보이도록 부드럽게 가로 스크롤."""
        if not (0 <= index < len(self._thumbs)):
            return
        thumb = self._thumbs[index]
        bar = self.horizontalScrollBar()
        left = thumb.x()
        right = left + thumb.width()
        view_w = self.viewport().width()
        margin = 60
        cur = bar.value()
        if left - margin < cur:
            self._animate_scroll_to(left - margin)
        elif right + margin > cur + view_w:
            self._animate_scroll_to(right + margin - view_w)

    def wheelEvent(self, event):  # noqa: N802
        """세로 휠을 가로 스크롤로 변환 (가로 휠 불필요), 부드럽게 이동."""
        bar = self.horizontalScrollBar()
        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.angleDelta().x()
        if delta != 0 and bar.maximum() > 0:
            # 진행 중 애니메이션의 목표값을 기준으로 누적 → 휠 연타도 매끄럽게
            anim_running = self._scroll_anim.state() == QPropertyAnimation.Running
            base = self._scroll_anim.endValue() if anim_running else bar.value()
            self._animate_scroll_to(int(base) - delta)
            event.accept()
        else:
            super().wheelEvent(event)
