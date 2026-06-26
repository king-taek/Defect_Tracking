"""Layer 비교 그리드 (문서 Section 8.4).

layer별 이미지를 RDL4/PI4 ... 형태로 배치한다. 기준 Layer 이미지는 강조 + "기준" 표기.
기준 사진 변경 시 비교 Layer 이미지들은 빠른 Fade 로 갱신된다.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.models import BaseDefectMatches, DefectRecord
from app.ui import theme
from app.ui.image_loader import ImageLoader
from app.ui.widgets import FadeImageLabel


class LayerCell(QFrame):
    """단일 layer 이미지 셀 (제목 + 매칭 정보 + 이미지)."""

    def __init__(
        self,
        layer: str,
        is_base: bool,
        loader: Optional[ImageLoader] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.layer = layer
        self.is_base = is_base
        self.setObjectName("cell")
        self._build()
        if loader is not None:
            self.image.set_loader(loader)
        self._apply_style(active=is_base)

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(4)

        header = QLabel()
        header.setAlignment(Qt.AlignCenter)
        label = f"★ {self.layer} (기준)" if self.is_base else self.layer
        header.setText(label)
        header.setStyleSheet(
            f"font-weight:700; color:{'#ffffff' if self.is_base else theme.TEXT};"
        )
        self.header = header

        self.info = QLabel("")
        self.info.setObjectName("dim")
        self.info.setAlignment(Qt.AlignCenter)
        self.info.setStyleSheet("font-size:10px;")

        # 기준은 부드럽게(긴 fade), 비교는 빠른 fade
        self.image = FadeImageLabel(duration=320 if self.is_base else 180)
        self.image.setMinimumHeight(160)

        lay.addWidget(header)
        lay.addWidget(self.info)
        lay.addWidget(self.image, 1)

    def _apply_style(self, active: bool) -> None:
        if self.is_base:
            self.setStyleSheet(
                f"QFrame#cell {{ background:{theme.BG_ELEV};"
                f" border:2px solid {theme.BASE_GLOW}; border-radius:10px; }}"
            )
        elif active:
            self.setStyleSheet(
                f"QFrame#cell {{ background:{theme.BG_PANEL};"
                f" border:1px solid {theme.MATCH}; border-radius:10px; }}"
            )
        else:
            self.setStyleSheet(
                f"QFrame#cell {{ background:{theme.BG_PANEL};"
                f" border:1px solid {theme.NEON_SOFT}; border-radius:10px; }}"
            )

    def show_record(self, rec: Optional[DefectRecord], info: str, matched: bool) -> None:
        if rec is not None:
            self.image.show_path(rec.image_path, animated=not self.is_base)
            self.info.setText(info)
        else:
            self.image.show_message("매칭 없음")
            self.info.setText(info)
        if not self.is_base:
            self._apply_style(active=matched)

    def show_base(self, rec: DefectRecord) -> None:
        self.image.show_path(rec.image_path, animated=True)
        self.info.setText(
            f"wafer {rec.wafer_id}  die({rec.col},{rec.row})  {rec.position_key}"
        )


class CompareGrid(QWidget):
    """layer 배치 그리드 컨테이너."""

    def __init__(
        self, loader: Optional[ImageLoader] = None, parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(10)
        self._cells: dict[str, LayerCell] = {}
        self._base_layer: str = ""
        self._loader = loader

    def build_layout(
        self, grid: list[list[Optional[str]]], base_layer: str
    ) -> None:
        """layer 배치(grid)에 따라 셀을 재구성한다."""
        # 기존 제거
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._cells.clear()
        self._base_layer = base_layer

        for r, row in enumerate(grid):
            for c, layer in enumerate(row):
                if not layer:
                    continue
                cell = LayerCell(
                    layer, is_base=(layer == base_layer), loader=self._loader
                )
                self._cells[layer] = cell
                self._grid.addWidget(cell, r, c)

    def update_for_base(
        self, item: BaseDefectMatches, compare_layers: list[str]
    ) -> None:
        """기준 defect 변경 시 모든 셀 갱신."""
        base = item.base
        if self._base_layer in self._cells:
            self._cells[self._base_layer].show_base(base)

        for layer in compare_layers:
            cell = self._cells.get(layer)
            if cell is None:
                continue
            mr = item.for_layer(layer)
            if mr and mr.is_match and mr.matched is not None:
                info = (
                    f"매칭 O  거리 {mr.distance:.1f}  "
                    f"{mr.matched.position_key}"
                )
                cell.show_record(mr.matched, info, matched=True)
            else:
                cell.show_record(None, "매칭 없음", matched=False)

    def show_empty(self, message: str) -> None:
        for cell in self._cells.values():
            cell.image.show_message(message)
            cell.info.setText("")
