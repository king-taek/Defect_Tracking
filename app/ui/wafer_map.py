"""웨이퍼 맵 네비게이터 — 현재 wafer 의 die 격자를 매칭 상태로 색칠하고,

die 클릭 시 해당 기준 사진으로 점프한다. 리뷰 현황을 한눈에 본다.

상태 색:
  matched(매칭)=초록. 미매칭·기준없음은 빈칸(무시).
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
    "matched": theme.MATCH,
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
        # 그리기 원점(실좌표) — 내용 bounding box 의 좌상단을 (0,0) 픽셀에 맞춘다.
        # states/valid/current 는 실좌표 그대로 두고 그리기·클릭만 이 오프셋을 적용해,
        # 좌표계 원점이 wafer 마다 달라도 맵이 떠 보이거나 잘리지 않게 한다.
        self._origin_col = 0
        self._origin_row = 0
        self.setToolTip("웨이퍼 맵 — die 클릭 시 해당 기준 사진으로 이동")
        self.setMinimumSize(40, 40)

    def set_data(
        self,
        cols: int,
        rows: int,
        states: dict[tuple[int, int], str],
        current: Optional[tuple[int, int]] = None,
        valid: Optional[frozenset] = None,
        origin: tuple[int, int] = (0, 0),
    ) -> None:
        self._cols = max(0, cols)
        self._rows = max(0, rows)
        self._states = states
        self._current = current
        self._valid = valid if valid else None
        self._origin_col, self._origin_row = origin
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
        """실좌표(col,row)를 원점 오프셋을 적용한 픽셀 사각형으로.

        die row 0 을 화면 맨 아래에 그린다(왼쪽아래 0,0 표준, 위로 갈수록 row 증가).
        """
        x = _GAP + (col - self._origin_col) * (_CELL + _GAP)
        dr_from_bottom = (self._rows - 1) - (row - self._origin_row)
        y = _GAP + dr_from_bottom * (_CELL + _GAP)
        return QRect(x, y, _CELL, _CELL)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        empty = QColor(theme.BG_ELEV)
        border = QColor(theme.NEON_SOFT)
        for dr in range(self._rows):
            row = dr + self._origin_row
            for dc in range(self._cols):
                col = dc + self._origin_col
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
            if (self._origin_col <= cc < self._origin_col + self._cols
                    and self._origin_row <= cr < self._origin_row + self._rows):
                painter.setPen(QPen(QColor(theme.BASE_GLOW), 2))
                painter.drawRect(self._cell_rect(cc, cr).adjusted(0, 0, -1, -1))
        painter.end()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() != Qt.LeftButton:
            return
        pos = event.position().toPoint()
        dc = (pos.x() - _GAP) // (_CELL + _GAP)
        dr = (pos.y() - _GAP) // (_CELL + _GAP)
        if 0 <= dc < self._cols and 0 <= dr < self._rows:
            col = int(dc) + self._origin_col
            # row 0 이 화면 맨 아래이므로(_cell_rect 와 대칭) 세로 인덱스를 반전 복원한다.
            row = self._origin_row + (self._rows - 1 - int(dr))
            if (col, row) in self._states:
                self.die_clicked.emit(col, row)
