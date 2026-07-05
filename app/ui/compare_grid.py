"""Layer 비교 그리드 (문서 Section 8.4).

layer별 이미지를 LYA4/LYB4 ... 형태로 배치한다. 기준 Layer 이미지는 강조 + "기준" 표기.
기준 사진 변경 시 비교 Layer 이미지들은 빠른 Fade 로 갱신된다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pathlib import Path as _Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.models import BaseDefectMatches, DefectRecord, NoMatchReason
from app.ui import theme
from app.ui.image_loader import ImageLoader
from app.ui.widgets import FadeImageLabel


class LayerCell(QFrame):
    """단일 layer 이미지 셀 (제목 + 매칭 정보 + 이미지).

    이미지가 있을 때 클릭하면 record_clicked 로 현재 DefectRecord 를 알린다(원본 확대 보기).
    """

    record_clicked = Signal(object)  # DefectRecord
    cluster_clicked = Signal(object)  # 근접중복 '+n' 클릭 → 묶인 base 목록(list[DefectRecord])

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
        self._record: Optional[DefectRecord] = None
        self.setObjectName("cell")
        self._build()
        if loader is not None:
            self.image.set_loader(loader)
        self._apply_style(active=is_base)

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 기준은 부드럽게(긴 fade), 비교는 빠른 fade
        self.image = FadeImageLabel(duration=320 if self.is_base else 180)
        self.image.setMinimumHeight(280)
        self.image.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Layer 이름 배지: 이미지 위에 floating (요구사항 4 — 사진 위 Layer명 표시)
        self.badge = QLabel(self.image)
        self.badge.setObjectName("layerBadgeBase" if self.is_base else "layerBadge")
        self.badge.setText(f"★ {self.layer} (기준)" if self.is_base else self.layer)
        self.badge.adjustSize()
        self.badge.move(10, 10)

        # 근접중복 '+n' 배지(기준 셀에서만) — 클릭 시 묶인 defect 전체 보기.
        self._cluster_members: list = []
        self.more_badge = QPushButton("", self.image)
        self.more_badge.setObjectName("mini")
        self.more_badge.setCursor(Qt.PointingHandCursor)
        self.more_badge.setToolTip("이 자리에 근접(<50)해 하나로 묶인 defect 을 모두 봅니다.")
        self.more_badge.clicked.connect(self._emit_cluster)
        self.more_badge.hide()

        # 이미지 아래 작은 진단/부가정보 줄(wafer명 노출 X — 상세는 tooltip)
        self.info = QLabel("")
        self.info.setObjectName("diag")
        self.info.setAlignment(Qt.AlignCenter)

        lay.addWidget(self.image, 1)
        lay.addWidget(self.info)

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

    def _set_info(self, text: str, *, warn: bool = False) -> None:
        """진단/부가정보 줄을 갱신하고 QSS objectName 을 다시 적용한다."""
        self.info.setText(text)
        self.info.setObjectName("diagWarn" if warn else "diag")
        self.info.style().unpolish(self.info)
        self.info.style().polish(self.info)

    def show_record(
        self, rec: Optional[DefectRecord], info: str, matched: bool, *, warn: bool = False
    ) -> None:
        self._set_record(rec)
        if rec is not None:
            self.image.show_path(rec.image_path, animated=not self.is_base)
        else:
            self.image.show_message("")
        self._set_info(info, warn=warn)
        self.badge.raise_()
        if not self.is_base:
            self._apply_style(active=matched)

    def show_base(self, rec: DefectRecord, extra: int = 0, members: Optional[list] = None) -> None:
        self._set_record(rec)
        self.image.show_path(rec.image_path, animated=True)
        # wafer명은 노출하지 않고 die 위치만 간단히(상세는 tooltip)
        info = f"die ({rec.col}, {rec.row})"
        if extra:
            info += f" · 근접중복 +{extra}"
        self._set_info(info)
        self.badge.raise_()
        # 근접중복 '+n' 배지 갱신(좌하단).
        self._cluster_members = list(members or [])
        if extra > 0:
            self.more_badge.setText(f"+{extra}")
            self.more_badge.adjustSize()
            self.more_badge.move(10, self.image.height() - self.more_badge.height() - 10)
            self.more_badge.show()
            self.more_badge.raise_()
        else:
            self.more_badge.hide()

    def _emit_cluster(self) -> None:
        if self._cluster_members:
            self.cluster_clicked.emit(self._cluster_members)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        # 이미지 크기 변화에 맞춰 '+n' 배지를 좌하단에 유지.
        if self.more_badge.isVisible():
            self.more_badge.move(10, self.image.height() - self.more_badge.height() - 10)

    def _set_record(self, rec: Optional[DefectRecord]) -> None:
        self._record = rec
        if rec is not None:
            self.setCursor(Qt.PointingHandCursor)
            tip = (
                f"{self.layer} · wafer {rec.wafer_id} · die({rec.col},{rec.row})\n"
                f"pos {rec.position_key}"
            )
            if rec.defect_name:
                tip += f" · {rec.defect_name}"
            tip += f"\n{rec.image_path}\n\n클릭하면 원본을 크게 봅니다"
            self.setToolTip(tip)
            self.image.setToolTip(tip)
        else:
            self.setCursor(Qt.ArrowCursor)
            self.setToolTip("")
            self.image.setToolTip("")

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and self._record is not None:
            self.record_clicked.emit(self._record)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):  # noqa: N802
        if self._record is None:
            return
        rec = self._record
        path = str(rec.image_path)
        menu = QMenu(self)
        menu.addAction("경로 복사", lambda: QGuiApplication.clipboard().setText(path))
        menu.addAction(
            "파일 열기",
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)),
        )
        menu.addAction(
            "폴더 열기",
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(_Path(path).parent))
            ),
        )
        menu.exec(event.globalPos())


class CompareGrid(QWidget):
    """layer 배치 그리드 컨테이너."""

    image_clicked = Signal(object)  # DefectRecord
    base_cluster_clicked = Signal(object)  # 근접중복 '+n' → 묶인 base 목록

    def __init__(
        self, loader: Optional[ImageLoader] = None, parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(10)
        self._cells: dict[str, LayerCell] = {}
        self._layer_order: list[str] = []  # 셀 배치 순서(기준 우선, 이후 grid 순서)
        self._base_layer: str = ""
        self._loader = loader

    def build_layout(
        self, grid: list[list[Optional[str]]], base_layer: str
    ) -> None:
        """layer 배치(grid)에 따라 셀을 재구성하고 부드럽게 페이드 인한다."""
        # 기존 제거
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._cells.clear()
        self._layer_order = []
        self._base_layer = base_layer

        for r, row in enumerate(grid):
            for c, layer in enumerate(row):
                if not layer:
                    continue
                cell = LayerCell(
                    layer, is_base=(layer == base_layer), loader=self._loader
                )
                cell.record_clicked.connect(self.image_clicked)
                cell.cluster_clicked.connect(self.base_cluster_clicked)
                self._cells[layer] = cell
                self._layer_order.append(layer)
                self._grid.addWidget(cell, r, c)

    def _repack(self, visible_layers: list[str]) -> None:
        """보이는 layer 셀만 2열 그리드에 빈칸 없이 다시 배치하고 나머지는 숨긴다.

        위젯은 삭제하지 않고 재사용(위치만 이동)하므로 탐색 중 깜빡임이 적다.
        """
        while self._grid.count():
            self._grid.takeAt(0)
        visible_set = set(visible_layers)
        for layer, cell in self._cells.items():
            if layer not in visible_set:
                cell.setVisible(False)
        for i, layer in enumerate(visible_layers):
            cell = self._cells.get(layer)
            if cell is None:
                continue
            cell.setVisible(True)
            self._grid.addWidget(cell, i // 2, i % 2)

    def update_for_base(
        self, item: BaseDefectMatches, compare_layers: list[str]
    ) -> None:
        """기준 defect 변경 시 셀 갱신 — 기준 + 매칭된 비교 layer 셀만 압축 배치.

        매칭 없는 비교 layer 셀은 숨겨 빈칸을 없애고, 보이는 셀을 좌상단부터 2열로 채운다.
        """
        base = item.base
        visible: list[str] = []
        if self._base_layer in self._cells:
            cluster = getattr(item, "base_cluster", None)
            extra = getattr(cluster, "extra_count", 0) or 0
            members = list(getattr(cluster, "members", []) or [])
            self._cells[self._base_layer].show_base(base, extra=extra, members=members)
            visible.append(self._base_layer)

        ordered_compares = [l for l in self._layer_order if l != self._base_layer]
        for layer in ordered_compares:
            if layer not in compare_layers:
                continue
            cell = self._cells.get(layer)
            if cell is None:
                continue
            mr = item.for_layer(layer)
            if mr and mr.is_match and mr.matched is not None:
                info = f"매칭 O · 거리 {mr.distance:.1f} µm"
                if mr.ambiguous:
                    info += " · ⚠동률 후보"
                cell.show_record(mr.matched, info, matched=True, warn=mr.ambiguous)
                visible.append(layer)

        self._repack(visible)

    @staticmethod
    def _diag_text(mr) -> tuple[str, bool]:
        """매칭 실패 사유를 사용자 문구로 변환 (text, warn)."""
        reason = mr.reason
        if reason == NoMatchReason.COORD_FAIL:
            return f"좌표 추출 실패({mr.failed_in_die}장)", True
        if reason == NoMatchReason.OVER_TOLERANCE and mr.nearest_distance is not None:
            return f"허용오차 초과 · 최근접 {mr.nearest_distance:.1f}", True
        return "이 layer에 같은 die 사진 없음", False

    def show_empty(self, message: str) -> None:
        # 모든 셀을 다시 보이게 배치한 뒤 안내 메시지를 표시한다.
        self._repack(list(self._layer_order))
        for cell in self._cells.values():
            cell.image.show_message(message)
            cell.info.setText("")
