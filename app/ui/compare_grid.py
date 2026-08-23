"""판독대. 기준 사진과 비교 layer 사진을 나란히 놓는다.

원본은 매칭 없는 layer 셀을 숨기고 남은 셀을 2열로 압축했다. 왜 없는지가 화면에서 사라져
사용자가 "이 layer 는 원래 없나, 매칭에 실패했나"를 알 수 없었다. 재설계는 칸을 고정하고
빈 판에 사유를 남긴다(03-screens §1).

열 수는 칸 수에 따라 2/3/4 로 늘리고 한 칸의 최소 높이를 보장한다. layer 12개를 켜도 사진이
읽혀야 한다(게이트 4).

미매칭 표기 범위: 여기(앱 화면)는 사유를 남긴다. 회색 한 단어로 줄이는 것은 Excel 리포트에만
적용되는 규칙이다(REVIEW-01 AD1).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import isDarkTheme, qconfig

from app.models import BaseDefectMatches, DefectRecord, NoMatchReason
from app.ui import theme
from app.ui.image_loader import ImageLoader
from app.ui.widgets import FadeImageLabel

_HEADER_H = 34          # 카드 머리(레이어명 + 배지 + 수치)
_PHOTO_INSET = 8        # 사진 영역 좌우/아래 여백
_NO_MATCH_TITLE = "매치 없음"


def columns_for(cell_count: int) -> int:
    """칸 수에 따른 열 수. 4칸 이하 2열, 9칸 이하 3열, 그 이상 4열(03-screens §1)."""
    if cell_count <= 4:
        return 2
    if cell_count <= 9:
        return 3
    return 4


class LayerCell(QFrame):
    """판독대 한 칸.

    머리(레이어명·배지·수치)와 순검정 사진 무대를 분리한다. 원본은 배지를 사진 위에 겹쳐
    사진을 가렸다.
    """

    record_clicked = Signal(object)   # DefectRecord
    cluster_clicked = Signal(object)  # 근접 묶음 members(list[DefectRecord])

    def __init__(
        self,
        layer: str,
        is_base: bool,
        loader: Optional[ImageLoader] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.layer = layer
        self.is_base = is_base
        self._record: Optional[DefectRecord] = None
        self._cluster_members: list = []
        self.setObjectName("readingCard")
        self.setMinimumHeight(theme.WELL_MIN_PX)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._build(loader)
        self._apply_tokens()
        qconfig.themeChanged.connect(self._apply_tokens)

    # ------------------------------------------------------------ 구성
    def _build(self, loader: Optional[ImageLoader]) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        head = QWidget(self)
        head.setFixedHeight(_HEADER_H)
        head_row = QHBoxLayout(head)
        head_row.setContentsMargins(12, 0, 12, 0)
        head_row.setSpacing(theme.SPACING["gapS"])

        self.title = QLabel(self.layer, head)
        self.title.setObjectName("cardLayerName")
        head_row.addWidget(self.title)

        self.tag = QLabel("", head)
        self.tag.setObjectName("cardTag")
        self.tag.hide()
        head_row.addWidget(self.tag)
        head_row.addStretch(1)

        # 수치는 등폭 + 단위. 거리는 판독 근거라 카드 머리에 남긴다.
        self.chip = QLabel("", head)
        self.chip.setObjectName("cardChip")
        head_row.addWidget(self.chip)
        outer.addWidget(head)

        stage = QFrame(self)
        stage.setObjectName("photoStage")
        stage_layout = QVBoxLayout(stage)
        stage_layout.setContentsMargins(0, 0, 0, 0)
        self.image = FadeImageLabel(duration=theme.MOTION["photoSwap"][0])
        self.image.setMinimumHeight(120)
        self.image.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image.setTextFormat(Qt.RichText)
        self.image.setWordWrap(True)
        if loader is not None:
            self.image.set_loader(loader)
        stage_layout.addWidget(self.image)
        outer.addWidget(stage, 1)
        self._stage = stage

        wrap = QWidget(self)
        wrap.setFixedHeight(0)
        wrap.hide()

        # 기준 칸 좌하단: die 좌표. µm 스케일바는 픽셀 대 µm 실비율 근거가 코드에 없어
        # 만들지 않는다(REVIEW-01 P1). 비율 획득 경로가 생기면 그때 넣는다.
        self.die_label = QLabel("", stage)
        self.die_label.setObjectName("stageDie")
        self.die_label.hide()

        # 우하단 근접 묶음 버튼.
        self.more_badge = QPushButton("", stage)
        self.more_badge.setObjectName("stageMore")
        self.more_badge.setCursor(Qt.PointingHandCursor)
        self.more_badge.setToolTip("근접해 하나로 묶인 defect 을 모두 봅니다.")
        self.more_badge.clicked.connect(self._emit_cluster)
        self.more_badge.hide()

    def _apply_tokens(self, *_args) -> None:
        """카드·머리·무대 색을 현재 테마 토큰으로 칠한다.

        순수 Qt 위젯이라 setStyleSheet 를 쓴다. Fluent 위젯에 직접 거는 것만 금지다.
        """
        t = theme.fluent_tokens(isDarkTheme())
        card = t["card"]
        border = theme.flatten(t["cardBorder"], t["layer"])
        border_hover = theme.flatten(t["cardBorderH"], t["layer"])
        radius = theme.RADIUS["card"]
        self.setStyleSheet(
            f"QFrame#readingCard {{ background:{card}; border:1px solid {border};"
            f" border-radius:{radius}px; }}"
            f"QFrame#readingCard:hover {{ border-color:{border_hover}; }}"
        )
        self._stage.setStyleSheet(
            f"QFrame#photoStage {{ background:{theme.PHOTO_BG};"
            f" border-radius:4px; margin:0 {_PHOTO_INSET}px {_PHOTO_INSET}px"
            f" {_PHOTO_INSET}px; }}"
        )
        self.title.setStyleSheet(
            f"color:{theme.flatten(t['txt1'], card)}; font-size:13px; font-weight:600;"
        )
        self.chip.setStyleSheet(
            f"color:{t['pass']}; font-size:12px; font-weight:600;"
            " font-family:'Cascadia Mono','Consolas',monospace;"
        )
        self.die_label.setStyleSheet(
            "color:rgba(255,255,255,0.62); font-size:11px;"
            " font-family:'Cascadia Mono','Consolas',monospace; background:transparent;"
        )
        self.more_badge.setStyleSheet(
            "QPushButton#stageMore { color:rgba(255,255,255,0.90);"
            " background:rgba(255,255,255,0.08);"
            " border:1px solid rgba(255,255,255,0.30); border-radius:4px;"
            " padding:2px 9px; font-size:11px; }"
            "QPushButton#stageMore:hover { background:rgba(255,255,255,0.18); }"
        )
        self._style_tag()

    def _style_tag(self) -> None:
        t = theme.fluent_tokens(isDarkTheme())
        if self.is_base:
            fg, bg = t["accentText"], t["accentTint"]
        else:
            fg, bg = t["warn"], t["warnBg"]
        self.tag.setStyleSheet(
            f"color:{fg}; background:{bg}; border-radius:4px;"
            " padding:1px 6px; font-size:11px; font-weight:600;"
        )

    # ------------------------------------------------------------ 내용
    def show_base(self, rec: DefectRecord, extra: int = 0, members: Optional[list] = None) -> None:
        """기준 칸. 배지와 die 좌표, 근접 묶음 버튼을 함께 보인다."""
        self._set_record(rec)
        self.tag.setText("기준")
        self.tag.show()
        self._style_tag()
        self.chip.setText("")
        self.image.show_path(rec.image_path if rec else None)
        self.die_label.setText(f"die ({rec.col}, {rec.row})" if rec else "")
        self.die_label.setVisible(rec is not None)
        self._cluster_members = list(members or [])
        if extra > 0:
            self.more_badge.setText(f"＋{extra} 근접")
            self.more_badge.show()
        else:
            self.more_badge.hide()
        self._reposition_overlays()

    def show_match(self, rec: DefectRecord, distance: float, ambiguous: bool = False) -> None:
        """매칭된 비교 칸. 거리는 등폭 + 단위로 머리에 둔다."""
        self._set_record(rec)
        self.chip.setText(f"Δ {distance:.1f} µm")
        if ambiguous:
            self.tag.setText("동률 후보")
            self.tag.show()
        else:
            self.tag.hide()
        self._style_tag()
        self.die_label.hide()
        self.more_badge.hide()
        self.image.show_path(rec.image_path if rec else None)

    def show_no_match(self, reason: str) -> None:
        """빈 판 + 사유. 칸을 숨기지 않는 것이 이 화면의 요점이다."""
        self._set_record(None)
        self.chip.setText("")
        self.tag.hide()
        self.die_label.hide()
        self.more_badge.hide()
        body = (
            f"<div style='color:rgba(255,255,255,0.62); font-size:13px;"
            f" font-weight:600'>{_NO_MATCH_TITLE}</div>"
        )
        if reason:
            body += (
                f"<div style='color:rgba(255,255,255,0.66); font-size:12px;"
                f" margin-top:6px'>{reason}</div>"
            )
        self.image.show_message(body)

    def show_record(
        self, rec: Optional[DefectRecord], info: str, matched: bool, *, warn: bool = False
    ) -> None:
        """호환용 진입점. matched 면 매칭 칸, 아니면 빈 판 + 사유."""
        if matched and rec is not None:
            self._set_record(rec)
            self.chip.setText(info)
            self.tag.setVisible(bool(warn))
            if warn:
                self.tag.setText("동률 후보")
            self.image.show_path(rec.image_path)
        else:
            self.show_no_match(info)

    def _set_record(self, rec: Optional[DefectRecord]) -> None:
        self._record = rec
        self.setCursor(Qt.PointingHandCursor if rec else Qt.ArrowCursor)
        if rec is None:
            self.setToolTip("")
            return
        lines = [
            f"Layer: {self.layer}",
            f"wafer: {rec.wafer_id} · die ({rec.col}, {rec.row})",
            f"경로: {rec.image_path}",
        ]
        if getattr(rec, "defect_name", ""):
            lines.insert(1, f"결함: {rec.defect_name}")
        self.setToolTip("\n".join(lines))

    def _emit_cluster(self) -> None:
        if self._cluster_members:
            self.cluster_clicked.emit(self._cluster_members)

    # ------------------------------------------------------------ 상호작용
    def resizeEvent(self, event):  # noqa: N802 - Qt 규약
        super().resizeEvent(event)
        self._reposition_overlays()

    def _reposition_overlays(self) -> None:
        """무대 위 좌하단 die 라벨과 우하단 근접 버튼 위치."""
        stage = self._stage
        margin = 9
        if self.die_label.isVisible():
            self.die_label.adjustSize()
            self.die_label.move(margin + _PHOTO_INSET,
                                stage.height() - self.die_label.height() - margin)
        if self.more_badge.isVisible():
            self.more_badge.adjustSize()
            self.more_badge.move(
                stage.width() - self.more_badge.width() - margin - _PHOTO_INSET,
                stage.height() - self.more_badge.height() - margin,
            )
            self.more_badge.raise_()

    def mousePressEvent(self, event):  # noqa: N802 - Qt 규약
        if event.button() == Qt.LeftButton and self._record is not None:
            self.record_clicked.emit(self._record)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):  # noqa: N802 - Qt 규약
        if self._record is None:
            return
        path = str(self._record.image_path)
        menu = QMenu(self)
        act_copy = menu.addAction("경로 복사")
        act_open = menu.addAction("파일 열기")
        act_dir = menu.addAction("폴더 열기")
        chosen = menu.exec(event.globalPos())
        if chosen is act_copy:
            QApplication.clipboard().setText(path)
        elif chosen is act_open:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        elif chosen is act_dir:
            from pathlib import Path as _Path

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(_Path(path).parent)))


class CompareGrid(QWidget):
    """판독 카드 격자."""

    image_clicked = Signal(object)
    base_cluster_clicked = Signal(object)

    def __init__(self, loader: Optional[ImageLoader] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._loader = loader
        self._cells: dict[str, LayerCell] = {}
        self._layer_order: list[str] = []
        self._base_layer = ""
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(theme.SPACING["gapM"])

    # ------------------------------------------------------------ 구성
    def build_layout(self, grid: list[list[str]], base_layer: str) -> None:
        """layer 목록으로 카드를 새로 만든다. grid 는 행 단위 layer 이름."""
        for cell in self._cells.values():
            cell.setParent(None)
            cell.deleteLater()
        self._cells.clear()
        self._base_layer = base_layer

        order: list[str] = []
        for row in grid:
            for layer in row:
                if layer and layer not in order:
                    order.append(layer)
        self._layer_order = order

        for layer in order:
            cell = LayerCell(layer, layer == base_layer, self._loader, self)
            cell.record_clicked.connect(self.image_clicked)
            cell.cluster_clicked.connect(self.base_cluster_clicked)
            self._cells[layer] = cell
        self._repack(order)

    def _repack(self, visible_layers: list[str]) -> None:
        """보이는 칸을 칸 수에 맞는 열 수로 배치한다.

        위젯은 지우지 않고 자리만 옮긴다. 탐색 중 깜빡임이 적다.
        """
        while self._grid.count():
            self._grid.takeAt(0)
        visible = [l for l in visible_layers if l in self._cells]
        visible_set = set(visible)
        for layer, cell in self._cells.items():
            cell.setVisible(layer in visible_set)

        cols = columns_for(len(visible))
        for index, layer in enumerate(visible):
            self._grid.addWidget(self._cells[layer], index // cols, index % cols)
        for column in range(cols):
            self._grid.setColumnStretch(column, 1)
        rows = (len(visible) + cols - 1) // cols if visible else 0
        for row in range(max(rows, 1)):
            self._grid.setRowStretch(row, 1)
            self._grid.setRowMinimumHeight(row, theme.WELL_MIN_PX)

    # ------------------------------------------------------------ 내용
    def update_for_base(self, item: BaseDefectMatches, compare_layers: list[str]) -> None:
        """기준 defect 이 바뀔 때 카드를 갱신한다.

        선택된 비교 layer 는 매칭 여부와 무관하게 모두 남긴다. 매칭이 없으면 그 자리에 사유를
        적는다. 칸이 사라지면 왜 없는지가 화면에서 사라진다.
        """
        base = item.base
        visible: list[str] = []
        if self._base_layer in self._cells:
            cluster = getattr(item, "base_cluster", None)
            extra = getattr(cluster, "extra_count", 0) or 0
            members = list(getattr(cluster, "members", []) or [])
            self._cells[self._base_layer].show_base(base, extra=extra, members=members)
            visible.append(self._base_layer)

        for layer in self._layer_order:
            if layer == self._base_layer or layer not in compare_layers:
                continue
            cell = self._cells.get(layer)
            if cell is None:
                continue
            mr = item.for_layer(layer)
            if mr and mr.is_match and mr.matched is not None:
                cell.show_match(mr.matched, mr.distance, ambiguous=bool(mr.ambiguous))
            elif mr is not None:
                cell.show_no_match(self._diag_text(mr)[0])
            else:
                cell.show_no_match("이 layer 에 같은 die 사진 없음")
            visible.append(layer)

        self._repack(visible)

    @staticmethod
    def _diag_text(mr) -> tuple[str, bool]:
        """매칭 실패 사유를 조치 가능한 문장으로. (text, warn)"""
        reason = mr.reason
        if reason == NoMatchReason.COORD_FAIL:
            return f"좌표 추출 실패 ({mr.failed_in_die}장)", True
        if reason == NoMatchReason.OVER_TOLERANCE and mr.nearest_distance is not None:
            return f"허용오차 초과 · 최근접 {mr.nearest_distance:.1f} µm", True
        return "이 layer 에 같은 die 사진 없음", False

    def show_empty(self, message: str) -> None:
        self._repack(list(self._layer_order))
        for cell in self._cells.values():
            cell.show_no_match(message)
