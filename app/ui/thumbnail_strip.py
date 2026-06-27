"""상단 기준 썸네일 스트립 (문서 Section 8.6).

기준 Layer 사진들의 (중앙 10% 확대) 썸네일을 가로로 나열한다.
클릭 시 해당 사진을 기준 defect 로 설정하고, 현재 선택 썸네일을 강조한다.

가로 휠을 쓰지 않도록 **세로 휠 → 가로 스크롤** 로 매핑한다(사용성).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
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
        self.setFixedHeight(152)
        self.setToolTip("세로 휠로 좌우 스크롤 · 클릭하면 기준 사진 변경")
        self._container = QWidget()
        self._layout = QHBoxLayout(self._container)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(8)
        self._layout.addStretch()
        self.setWidget(self._container)
        self._thumbs: list[ClickableThumb] = []
        self._current = -1

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

    def set_current(self, index: int) -> None:
        if not (0 <= index < len(self._thumbs)):
            return
        for i, t in enumerate(self._thumbs):
            t.set_selected(i == index)
        self._current = index
        self._ensure_visible(index)

    def _ensure_visible(self, index: int) -> None:
        if 0 <= index < len(self._thumbs):
            self.ensureWidgetVisible(self._thumbs[index], 60, 0)

    def wheelEvent(self, event):  # noqa: N802
        """세로 휠을 가로 스크롤로 변환 (가로 휠 불필요)."""
        bar = self.horizontalScrollBar()
        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.angleDelta().x()
        if delta != 0 and bar.maximum() > 0:
            bar.setValue(bar.value() - delta)
            event.accept()
        else:
            super().wheelEvent(event)
