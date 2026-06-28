"""미매칭(기준 layer 의 defect 과 어떤 비교 layer 와도 매칭 안 된) 사진 갤러리.

후보에서 제외된 '매칭 없음' 기준 사진들을 한곳에 모아 썸네일 + 사유로 보여준다.
사유는 매칭 엔진이 이미 계산한 MatchResult.reason(NoMatchReason)을 그대로 재사용한다.
썸네일을 클릭하면 본문 탐색을 그 기준으로 이동한다(on_navigate 콜백).
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.models import NoMatchReason
from app.ui import theme
from app.ui.widgets import ClickableThumb

_COLUMNS = 4

# 사유별 (표시명, 색). 트리아지 우선순위는 _dominant 에서 별도로 정한다.
_REASON_META = {
    NoMatchReason.OVER_TOLERANCE: ("허용오차 초과", theme.WARN),
    NoMatchReason.COORD_FAIL: ("좌표 추출 실패", theme.NOMATCH),
    NoMatchReason.NO_DIE_PHOTO: ("같은 die 사진 없음", theme.TEXT_DIM),
}
# 트리아지 우선순위(높을수록 먼저) — 거의 매칭된 것(허용오차 초과)을 가장 눈에 띄게.
_PRIORITY = [
    NoMatchReason.OVER_TOLERANCE,
    NoMatchReason.COORD_FAIL,
    NoMatchReason.NO_DIE_PHOTO,
]


def _layer_diag(mr) -> str:
    """한 비교 layer 의 미매칭 사유 짧은 문구(그리드와 동일 표현 재사용)."""
    from app.ui.compare_grid import CompareGrid

    return CompareGrid._diag_text(mr)[0]


def _dominant(item) -> Optional[NoMatchReason]:
    """기준 1개의 대표 미매칭 사유(우선순위가 가장 높은 것)."""
    present = {r.reason for r in item.results if not r.is_match}
    for reason in _PRIORITY:
        if reason in present:
            return reason
    return None


class NoMatchGalleryDialog(QDialog):
    """미매칭 기준 사진 갤러리(사유 표기 + 사유별 필터 + 클릭 이동)."""

    def __init__(
        self,
        entries: list[tuple[int, object]],
        thumb_cache,
        on_navigate: Callable[[int], None],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._entries = entries  # [(base_index, BaseDefectMatches), ...]
        self._thumb_cache = thumb_cache
        self._on_navigate = on_navigate
        self.setWindowTitle("매칭 없는 기준 사진")
        self.setMinimumSize(560, 460)
        self._build()
        self._populate()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 12)
        outer.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel(f"매칭 없는 기준 사진 — 총 {len(self._entries)}장")
        title.setObjectName("title")
        head.addWidget(title)
        head.addStretch()
        head.addWidget(QLabel("사유:"))
        self.cmb_reason = QComboBox()
        self.cmb_reason.addItem("전체", None)
        for reason in _PRIORITY:
            self.cmb_reason.addItem(_REASON_META[reason][0], reason.value)
        self.cmb_reason.currentIndexChanged.connect(self._populate)
        head.addWidget(self.cmb_reason)
        outer.addLayout(head)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._host = QWidget()
        self._grid = QGridLayout(self._host)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(10)
        self._grid.setAlignment(Qt.AlignTop)
        self._scroll.setWidget(self._host)
        outer.addWidget(self._scroll, 1)

        self._empty = QLabel("해당하는 미매칭 기준 사진이 없습니다.")
        self._empty.setObjectName("dim")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setVisible(False)
        outer.addWidget(self._empty)

        btn = QPushButton("닫기")
        btn.setObjectName("primary")
        btn.clicked.connect(self.accept)
        outer.addWidget(btn, alignment=Qt.AlignRight)

    def _clear_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _populate(self) -> None:
        self._clear_grid()
        want = self.cmb_reason.currentData()
        shown = 0
        for idx, item in self._entries:
            present = {r.reason.value for r in item.results if not r.is_match}
            if want is not None and want not in present:
                continue
            self._grid.addWidget(self._make_cell(idx, item), shown // _COLUMNS, shown % _COLUMNS)
            shown += 1
        self._empty.setVisible(shown == 0)

    def _make_cell(self, idx: int, item) -> QWidget:
        cell = QFrame()
        cell.setFixedWidth(128)
        lay = QVBoxLayout(cell)
        lay.setContentsMargins(2, 2, 2, 6)
        lay.setSpacing(5)

        thumb = ClickableThumb(idx)
        base = item.base
        thumb.set_caption(f"{base.wafer_id}\n({base.col},{base.row})")
        path = self._thumb_cache.get_full_thumbnail(base.image_path, max_size=120)
        thumb.set_image(str(path) if path else None)
        thumb.set_status("none")
        thumb.clicked.connect(self._on_thumb_clicked)
        lay.addWidget(thumb, alignment=Qt.AlignHCenter)

        # 대표 사유 색 태그
        dom = _dominant(item)
        if dom is not None:
            label, color = _REASON_META[dom]
            tag = QLabel(label)
            tag.setAlignment(Qt.AlignCenter)
            tag.setStyleSheet(f"color:{color}; font-size:10px; font-weight:700;")
            lay.addWidget(tag)

        # layer 별 사유 요약(툴팁 + 작은 라벨)
        per_layer = [f"{r.compare_layer}: {_layer_diag(r)}" for r in item.results if not r.is_match]
        summary = QLabel(" · ".join(per_layer))
        summary.setObjectName("dim")
        summary.setStyleSheet("font-size:9px;")
        summary.setWordWrap(True)
        summary.setAlignment(Qt.AlignCenter)
        summary.setFixedWidth(120)
        if per_layer:
            summary.setToolTip("\n".join(per_layer))
        lay.addWidget(summary)
        return cell

    def _on_thumb_clicked(self, index: int) -> None:
        self._on_navigate(index)
