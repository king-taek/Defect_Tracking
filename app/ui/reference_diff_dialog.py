"""현재 매칭 모드 vs '정답 도구(reference_gate)' 모드 결과가 다른 기준 사진 모아보기.

정답 도구(원본 AOI Data Viewer VBA)를 그대로 재현한 reference_gate 매칭과 현재
매칭이 갈리는 기준 사진만 모아, layer 별로 두 모드의 결과를 나란히 보여준다.
썸네일을 클릭하면 본문 탐색을 그 기준으로 이동한다(on_navigate 콜백).
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.models import BaseDefectMatches, MatchResult
from app.ui.widgets import ClickableThumb

_COLUMNS = 4


def _fmt_result(r: Optional[MatchResult]) -> str:
    if r is None:
        return "?"
    if r.is_match:
        return f"매치(raw {r.distance:.0f})" if r.distance is not None else "매치"
    return "미매칭"


def layer_diff_lines(cur: BaseDefectMatches, ref: BaseDefectMatches) -> list[str]:
    """두 모드의 결과가 다른 layer 만 골라 비교 문구를 만든다."""
    lines = []
    for cur_r in cur.results:
        ref_r = ref.for_layer(cur_r.compare_layer)
        cur_matched = cur_r.matched.image_path if cur_r.is_match else None
        ref_matched = ref_r.matched.image_path if ref_r and ref_r.is_match else None
        if cur_matched == ref_matched:
            continue
        lines.append(
            f"{cur_r.compare_layer} — 현재:{_fmt_result(cur_r)} / 정답:{_fmt_result(ref_r)}"
        )
    return lines


class ReferenceDiffDialog(QDialog):
    """현재 모드 vs 정답 도구(reference_gate) 모드 매칭 결과가 다른 기준 사진 갤러리."""

    def __init__(
        self,
        entries: list[tuple[int, BaseDefectMatches, BaseDefectMatches]],
        thumb_cache,
        on_navigate: Callable[[int], None],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._entries = entries  # [(base_index, current, reference), ...]
        self._thumb_cache = thumb_cache
        self._on_navigate = on_navigate
        self.setWindowTitle("정답 도구와 결과가 다른 기준 사진")
        self.setMinimumSize(560, 460)
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 12)
        outer.setSpacing(10)

        title = QLabel(
            f"현재 모드 vs 정답 도구 모드 결과가 다른 기준 사진 — 총 {len(self._entries)}장"
        )
        title.setObjectName("title")
        title.setWordWrap(True)
        outer.addWidget(title)

        note = QLabel(
            "현재 모드: 정합오차(offset)로 tolerance 를 넘는 거리도 자동 보정해 매칭.\n"
            "정답 도구 모드: raw 거리가 이미 tolerance 이내인 후보끼리만 offset 으로 tie-break."
        )
        note.setObjectName("dim")
        note.setWordWrap(True)
        outer.addWidget(note)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        host = QWidget()
        self._grid = QGridLayout(host)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(10)
        self._grid.setAlignment(Qt.AlignTop)
        for i, (idx, cur, ref) in enumerate(self._entries):
            self._grid.addWidget(
                self._make_cell(idx, cur, ref), i // _COLUMNS, i % _COLUMNS
            )
        scroll.setWidget(host)
        outer.addWidget(scroll, 1)

        btn = QPushButton("닫기")
        btn.setObjectName("primary")
        btn.clicked.connect(self.accept)
        outer.addWidget(btn, alignment=Qt.AlignRight)

    def _make_cell(self, idx: int, cur: BaseDefectMatches, ref: BaseDefectMatches) -> QWidget:
        cell = QFrame()
        cell.setFixedWidth(148)
        lay = QVBoxLayout(cell)
        lay.setContentsMargins(2, 2, 2, 6)
        lay.setSpacing(5)

        thumb = ClickableThumb(idx)
        base = cur.base
        thumb.set_caption(f"{base.wafer_id}\n({base.col},{base.row})")
        path = self._thumb_cache.get_full_thumbnail(base.image_path, max_size=120)
        thumb.set_image(str(path) if path else None)
        thumb.set_status("none")
        thumb.clicked.connect(self._on_thumb_clicked)
        lay.addWidget(thumb, alignment=Qt.AlignHCenter)

        lines = layer_diff_lines(cur, ref)
        summary = QLabel("\n".join(lines))
        summary.setObjectName("dim")
        summary.setStyleSheet("font-size:9px;")
        summary.setWordWrap(True)
        summary.setAlignment(Qt.AlignCenter)
        summary.setFixedWidth(140)
        if lines:
            summary.setToolTip("\n".join(lines))
        lay.addWidget(summary)
        return cell

    def _on_thumb_clicked(self, index: int) -> None:
        self._on_navigate(index)
