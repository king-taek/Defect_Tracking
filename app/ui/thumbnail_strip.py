"""상단 기준 썸네일 스트립 (문서 Section 8.6).

기준 Layer 사진들의 (중앙 10% 확대) 썸네일을 가로로 나열한다.
클릭 시 해당 사진을 기준 defect 로 설정하고, 현재 선택 썸네일을 강조한다.

가로 휠을 쓰지 않도록 **세로 휠 -> 가로 스크롤** 로 매핑한다(사용성).

사진은 화면에 들어온 카드만 읽는다. 599장짜리 LOT 에서 전부 미리 읽으면 스크롤이 시작되기도
전에 메모리와 시간이 다 나간다.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QWidget

from app.ui.widgets import ClickableThumb

# 프로토타입 필름스트립 96 에서 아래 여백 12 를 뺀 값(카드 80 + 상하 여백 4).
_STRIP_H = 84
# 화면 밖으로 이만큼까지는 미리 읽어 둔다. 스크롤을 시작하자마자 빈 칸이 보이지 않게.
_PRELOAD_PX = 320


class ThumbnailStrip(QScrollArea):
    """기준 사진 썸네일 가로 스트립."""

    thumb_clicked = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(_STRIP_H)
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
        self._layout.setContentsMargins(0, 2, 0, 2)
        self._layout.setSpacing(8)
        self._layout.addStretch()
        self.setWidget(self._container)
        self._thumbs: list[ClickableThumb] = []
        self._current = -1
        # 부드러운 가로 스크롤 애니메이션
        self._scroll_anim = QPropertyAnimation(self.horizontalScrollBar(), b"value", self)
        self._scroll_anim.setDuration(220)
        self._scroll_anim.setEasingCurve(QEasingCurve.OutCubic)
        # 스크롤이 멈출 때가 아니라 움직이는 동안 계속 채운다(빈 칸이 스쳐 지나가지 않게).
        self.horizontalScrollBar().valueChanged.connect(lambda _=0: self.load_visible())

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
        self,
        captions: list[str],
        tooltips: Optional[list[str]] = None,
        on_progress=None,
    ) -> None:
        """기준 record 개수만큼 썸네일 placeholder 를 만든다.

        on_progress 가 주어지면 일정 개수마다 호출해(예: 로딩 스피너 pump) 많은
        썸네일을 만드는 동안에도 UI 가 멈춘 것처럼 보이지 않게 한다.
        """
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
            # 썸네일이 많을 때 주기적으로 이벤트 루프에 양보 → 스피너 애니메이션 유지
            if on_progress is not None and (i & 15) == 15:
                on_progress()

    def set_thumbnail(self, index: int, path: str) -> None:
        """사진 경로를 등록한다. 화면에 보이는 카드만 실제로 읽는다."""
        if 0 <= index < len(self._thumbs):
            self._thumbs[index].set_source(path)
            self.load_visible()

    def load_visible(self) -> int:
        """보이는 범위(+여유)의 카드를 읽는다. 실제로 읽은 장수를 돌려준다.

        위치는 위젯 geometry 가 아니라 카드 폭으로 계산한다. 목록을 막 채운 직후에는
        레이아웃이 아직 돌지 않아 모든 카드가 x=0 으로 보이고, 그러면 599장을 한꺼번에
        읽어 버린다.
        """
        if not self._thumbs:
            return 0
        left = self.horizontalScrollBar().value() - _PRELOAD_PX
        right = left + max(self.viewport().width(), 0) + 2 * _PRELOAD_PX
        margins = self._layout.contentsMargins()
        x = margins.left()
        step = ClickableThumb.CARD_W + self._layout.spacing()
        loaded = 0
        for thumb in self._thumbs:
            # isVisible 이 아니라 isHidden 이다. 창을 보이기 전에도 채워야 첫 화면이 빈 칸으로
            # 뜨지 않는다. 후보에서 제외돼 명시적으로 숨긴 카드만 자리를 차지하지 않는다.
            if thumb.isHidden():
                continue
            if x <= right and x + ClickableThumb.CARD_W >= left and thumb.ensure_loaded():
                loaded += 1
            x += step
        return loaded

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self.load_visible()

    def set_status_marks(self, statuses: list[str]) -> None:
        """각 썸네일에 매칭 상태 점을 표시(matched/none)."""
        for i, t in enumerate(self._thumbs):
            t.set_status(statuses[i] if i < len(statuses) else "matched")

    def set_visible_set(self, indices: Optional[list[int]]) -> None:
        """주어진 인덱스의 썸네일만 보이고 나머지는 숨긴다(후보 제외 반영).

        indices 가 None 이면 전부 표시. 인덱스는 기준 record 전체 기준(불변)이라
        클릭 시 emit 되는 index 도 그대로 유효하다.
        """
        if indices is None:
            for t in self._thumbs:
                t.setVisible(True)
            self.load_visible()
            return
        sel = set(indices)
        for i, t in enumerate(self._thumbs):
            t.setVisible(i in sel)
        self.load_visible()

    def set_current(self, index: int) -> None:
        if not (0 <= index < len(self._thumbs)):
            return
        for i, t in enumerate(self._thumbs):
            t.set_selected(i == index)
        self._current = index
        self._ensure_visible(index)
        self.load_visible()

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
