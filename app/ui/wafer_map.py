"""웨이퍼 맵 네비게이터 — 현재 wafer 의 die 격자를 매칭 상태로 색칠하고,

die 클릭 시 해당 기준 사진으로 점프한다. 리뷰 현황을 한눈에 본다.

상태 색:
  full(전부 매칭)=초록, partial(일부)=주황, none(전무)=빨강, 기준없음=빈칸.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from app.ui import theme

_CELL = 16
_GAP = 2

_STATE_COLORS = {
    "full": theme.MATCH,
    "partial": theme.WARN,
    "none": theme.NOMATCH,
}


class WaferMapWidget(QWidget):
    """현재 wafer 의 die 상태 격자."""

    die_clicked = Signal(int, int)  # (col, row)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._cols = 0
        self._rows = 0
        self._states: dict[tuple[int, int], str] = {}
        self._current: Optional[tuple[int, int]] = None
        self._valid: Optional[frozenset] = None  # 존재하는 die (None 이면 전체 사각)
        self.setToolTip("웨이퍼 맵 — die 클릭 시 해당 기준 사진으로 이동")
        self.setMinimumSize(40, 40)

    def set_data(
        self,
        cols: int,
        rows: int,
        states: dict[tuple[int, int], str],
        current: Optional[tuple[int, int]] = None,
        valid: Optional[frozenset] = None,
    ) -> None:
        self._cols = max(0, cols)
        self._rows = max(0, rows)
        self._states = states
        self._current = current
        self._valid = valid if valid else None
        self.setFixedSize(
            max(40, self._cols * (_CELL + _GAP) + _GAP),
            max(40, self._rows * (_CELL + _GAP) + _GAP),
        )
        self.update()

    def clear(self) -> None:
        self._states = {}
        self._current = None
        self.update()

    def _cell_rect(self, col: int, row: int) -> QRect:
        x = _GAP + col * (_CELL + _GAP)
        y = _GAP + row * (_CELL + _GAP)
        return QRect(x, y, _CELL, _CELL)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        empty = QColor(theme.BG_ELEV)
        border = QColor(theme.NEON_SOFT)
        for row in range(self._rows):
            for col in range(self._cols):
                # 디바이스 die 배치(valid)가 주어지면 존재하는 die 만 그린다(실제 모양).
                if self._valid is not None and (col, row) not in self._valid:
                    continue
                rect = self._cell_rect(col, row)
                status = self._states.get((col, row))
                color = QColor(_STATE_COLORS.get(status, "")) if status else empty
                painter.fillRect(rect, color)
                painter.setPen(QPen(border, 1))
                painter.drawRect(rect)
        if self._current is not None:
            cc, cr = self._current
            if 0 <= cc < self._cols and 0 <= cr < self._rows:
                painter.setPen(QPen(QColor(theme.BASE_GLOW), 2))
                painter.drawRect(self._cell_rect(cc, cr).adjusted(0, 0, -1, -1))
        painter.end()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() != Qt.LeftButton:
            return
        pos = event.position().toPoint()
        col = (pos.x() - _GAP) // (_CELL + _GAP)
        row = (pos.y() - _GAP) // (_CELL + _GAP)
        if 0 <= col < self._cols and 0 <= row < self._rows:
            if (col, row) in self._states:
                self.die_clicked.emit(int(col), int(row))
