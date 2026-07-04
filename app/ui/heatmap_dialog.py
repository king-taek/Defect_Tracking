"""Defect 히트맵 팝업 (항목 4·5).

좌측 웨이퍼맵에 defect 밀도를 색으로 표시하고, 위치(die/하위셀)를 클릭하면 우측에 그
위치의 defect 들을 세로로 나열한다. 각 defect 행에는 기준 사진과 **매칭된 비교 layer
사진만** 가로로 나열하며(매칭 없는 칸은 표시하지 않음), 각 썸네일 좌상단에 layer 배지를
붙인다. 각 행은 '담기'로 공유 출력 트레이에 담을 수 있다.

die 개수가 50개 미만이면 각 die 를 4×5(20) 하위셀로 나눠 die 내부 위치를 구분한다.
wafer 선택에서 '전체'를 고르면 모든 wafer 의 defect 을 한 장에 밀도 합산해 보여준다.

순수 집계/분할 로직은 app.heatmap 에 있고 여기서는 시각화/상호작용만 담당한다.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app import config, heatmap, wafermap_align
from app.heatmap import HeatKey
from app.models import BaseDefectMatches
from app.thumbnails import ThumbnailCache
from app.ui import theme

_ALIGN_MIN_OVERLAP = 0.6
_ALL_WAFERS = "전체"
_THUMB_PX = 150  # 상세 목록 썸네일 크기(고정)


def _heat_color(count: int, max_count: int) -> QColor:
    """defect 개수를 밀도 색으로 변환(0=빈칸, 많을수록 진한 경고색)."""
    if count <= 0:
        return QColor(theme.BG_ELEV)
    lo = QColor(theme.NEON_DIM)   # 낮은 밀도(차분한 블루)
    hi = QColor(theme.NOMATCH)    # 높은 밀도(경고 레드)
    if max_count <= 1:
        t = 1.0
    else:
        t = (count - 1) / (max_count - 1)
    t = max(0.0, min(1.0, t))
    r = int(lo.red() + (hi.red() - lo.red()) * t)
    g = int(lo.green() + (hi.green() - lo.green()) * t)
    b = int(lo.blue() + (hi.blue() - lo.blue()) * t)
    return QColor(r, g, b)


class HeatmapWaferMap(QWidget):
    """웨이퍼맵에 defect 밀도를 색으로 그리고 위치 클릭을 알린다.

    die 개수가 적으면(subdivide=True) 각 die 를 4×5 하위셀로 나눠 그린다.
    """

    cell_clicked = Signal(object)  # HeatKey

    _DIE_PX = 20          # 미분할 die 한 변
    _SUBCELL_PX = 9       # 하위셀 한 변
    _GAP = 3              # die 간 간격

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._cols = 0
        self._rows = 0
        self._valid: Optional[frozenset] = None
        self._subdivide = False
        self._density: dict[HeatKey, int] = {}
        self._max_count = 1
        self._selected: Optional[HeatKey] = None
        # 그리기 원점(실좌표) — 내용 bounding box 좌상단을 (0,0) 픽셀에 맞춘다(맵 떠보임/잘림 방지).
        self._origin_col = 0
        self._origin_row = 0
        self.setToolTip("defect 밀도 — 색이 진할수록 defect 이 많음. 위치를 클릭하세요.")

    def _die_w(self) -> int:
        return heatmap.SUB_COLS * self._SUBCELL_PX if self._subdivide else self._DIE_PX

    def _die_h(self) -> int:
        return heatmap.SUB_ROWS * self._SUBCELL_PX if self._subdivide else self._DIE_PX

    def set_data(
        self,
        cols: int,
        rows: int,
        valid: Optional[frozenset],
        subdivide: bool,
        density: dict[HeatKey, int],
        origin: tuple[int, int] = (0, 0),
    ) -> None:
        self._cols = max(0, cols)
        self._rows = max(0, rows)
        self._valid = frozenset(valid) if valid else None
        self._subdivide = subdivide
        self._density = density
        self._max_count = max(density.values(), default=1)
        self._selected = None
        self._origin_col, self._origin_row = origin
        dw, dh = self._die_w(), self._die_h()
        self.setFixedSize(
            max(40, self._cols * (dw + self._GAP) + self._GAP),
            max(40, self._rows * (dh + self._GAP) + self._GAP),
        )
        self.update()

    def set_selected(self, key: Optional[HeatKey]) -> None:
        self._selected = key
        self.update()

    def _die_origin(self, col: int, row: int) -> tuple[int, int]:
        dw, dh = self._die_w(), self._die_h()
        return (self._GAP + (col - self._origin_col) * (dw + self._GAP),
                self._GAP + (row - self._origin_row) * (dh + self._GAP))

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        border = QColor(theme.NEON_SOFT)
        die_border = QColor(theme.BASE_GLOW)
        for dr in range(self._rows):
            row = dr + self._origin_row
            for dc in range(self._cols):
                col = dc + self._origin_col
                if self._valid is not None and (col, row) not in self._valid:
                    continue
                ox, oy = self._die_origin(col, row)
                if self._subdivide:
                    self._paint_die_sub(painter, col, row, ox, oy, border)
                    # die 경계선(하위셀 위에 굵게) — die 구분 유지
                    painter.setPen(QPen(die_border, 1))
                    painter.drawRect(QRect(ox, oy, self._die_w(), self._die_h()))
                else:
                    count = self._density.get(HeatKey(col, row), 0)
                    rect = QRect(ox, oy, self._DIE_PX, self._DIE_PX)
                    painter.fillRect(rect, _heat_color(count, self._max_count))
                    painter.setPen(QPen(border, 1))
                    painter.drawRect(rect)
        self._paint_selection(painter)
        painter.end()

    def _paint_die_sub(self, painter, col, row, ox, oy, border) -> None:
        for sr in range(heatmap.SUB_ROWS):
            for sc in range(heatmap.SUB_COLS):
                count = self._density.get(HeatKey(col, row, sc, sr), 0)
                x = ox + sc * self._SUBCELL_PX
                y = oy + sr * self._SUBCELL_PX
                rect = QRect(x, y, self._SUBCELL_PX, self._SUBCELL_PX)
                painter.fillRect(rect, _heat_color(count, self._max_count))
                painter.setPen(QPen(border, 1))
                painter.drawRect(rect)

    def _paint_selection(self, painter) -> None:
        if self._selected is None:
            return
        key = self._selected
        if not (self._origin_col <= key.col < self._origin_col + self._cols
                and self._origin_row <= key.row < self._origin_row + self._rows):
            return
        ox, oy = self._die_origin(key.col, key.row)
        painter.setPen(QPen(QColor(theme.NEON), 2))
        if self._subdivide and key.subdivided:
            x = ox + key.sub_col * self._SUBCELL_PX
            y = oy + key.sub_row * self._SUBCELL_PX
            painter.drawRect(QRect(x, y, self._SUBCELL_PX, self._SUBCELL_PX).adjusted(0, 0, -1, -1))
        else:
            painter.drawRect(QRect(ox, oy, self._die_w(), self._die_h()).adjusted(0, 0, -1, -1))

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() != Qt.LeftButton:
            return
        pos = event.position().toPoint()
        dw, dh = self._die_w(), self._die_h()
        dc = (pos.x() - self._GAP) // (dw + self._GAP)
        dr = (pos.y() - self._GAP) // (dh + self._GAP)
        if not (0 <= dc < self._cols and 0 <= dr < self._rows):
            return
        col = int(dc) + self._origin_col
        row = int(dr) + self._origin_row
        ox, oy = self._die_origin(int(col), int(row))
        if self._subdivide:
            sc = min(heatmap.SUB_COLS - 1, max(0, (pos.x() - ox) // self._SUBCELL_PX))
            sr = min(heatmap.SUB_ROWS - 1, max(0, (pos.y() - oy) // self._SUBCELL_PX))
            key = HeatKey(int(col), int(row), int(sc), int(sr))
        else:
            key = HeatKey(int(col), int(row))
        if self._density.get(key, 0) > 0:
            self.set_selected(key)
            self.cell_clicked.emit(key)


class HeatmapDialog(QDialog):
    """defect 히트맵 팝업(좌 웨이퍼맵 · 우 defect 목록)."""

    def __init__(
        self,
        matches: list[BaseDefectMatches],
        base_layer: str,
        compare_layers: list[str],
        thumb_cache: ThumbnailCache,
        on_add_to_export: Callable[[list[int]], None],
        settings,
        current_wafer: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.matches = matches
        self._base_layer = base_layer
        self._compare_layers = list(compare_layers)
        self._thumb_cache = thumb_cache
        self._on_add = on_add_to_export
        self._settings = settings
        self.setWindowTitle("Defect 히트맵")
        self.setMinimumSize(900, 600)

        self._groups: dict[HeatKey, list[int]] = {}
        self._selected_key: Optional[HeatKey] = None

        wafers = self._wafers()
        self._current_wafer = current_wafer if current_wafer in wafers else (
            wafers[0] if wafers else ""
        )

        self._build()
        # 시작 시 전체화면(최대화). exec 모달에서도 유지된다.
        self.setWindowState(Qt.WindowMaximized)
        self._refresh_map()

    # ---- 데이터 헬퍼 -------------------------------------------------
    def _wafers(self) -> list[str]:
        seen: list[str] = []
        for m in self.matches:
            w = m.base.wafer_id
            if w not in seen:
                seen.append(w)
        return seen

    def _available_layers(self) -> list[str]:
        """표시(필터) 가능한 비교 layer: matches 에 등장하는 모든 비교 layer(순서 유지)."""
        layers: list[str] = []
        for m in self.matches:
            for r in m.results:
                if r.compare_layer not in layers:
                    layers.append(r.compare_layer)
        return layers

    def _selected_compare_layers(self) -> list[str]:
        """상세 목록에 표시할 비교 layer(체크된 것). 기준은 항상 별도로 맨 앞에 표시."""
        return [lyr for lyr, cb in self._col_checks.items() if cb.isChecked()]

    def _current_entries(self) -> list[tuple[int, object]]:
        """현재 wafer 선택(또는 '전체')에 해당하는 (base_index, base_record) 목록."""
        out: list[tuple[int, object]] = []
        wafer = self._current_wafer
        for i, m in enumerate(self.matches):
            b = m.base
            if b.col is None or b.row is None or b.col < 0 or b.row < 0:
                continue
            if wafer != _ALL_WAFERS and b.wafer_id != wafer:
                continue
            out.append((i, b))
        return out

    # ---- UI 구성 -----------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)

        # 상단 컨트롤 바: 제목 / wafer 선택
        bar = QHBoxLayout()
        title = QLabel("Defect 히트맵")
        title.setObjectName("title")
        bar.addWidget(title)
        bar.addStretch()
        bar.addWidget(QLabel("Wafer"))
        self.cmb_wafer = QComboBox()
        self.cmb_wafer.addItem(_ALL_WAFERS)  # '전체' 맨 앞
        self.cmb_wafer.addItems(self._wafers())
        if self._current_wafer:
            self.cmb_wafer.setCurrentText(self._current_wafer)
        self.cmb_wafer.currentTextChanged.connect(self._on_wafer_changed)
        bar.addWidget(self.cmb_wafer)
        outer.addLayout(bar)

        # 표시 layer 필터(기준은 항상 표시, 비교 layer 는 체크로 on/off)
        col_row = QHBoxLayout()
        col_row.setSpacing(8)
        col_row.addWidget(QLabel("표시 layer:"))
        base_tag = QLabel(f"★ {self._base_layer}")
        base_tag.setStyleSheet(f"color:{theme.BASE_GLOW}; font-weight:700;")
        col_row.addWidget(base_tag)
        self._col_checks: dict[str, QCheckBox] = {}
        default_cols = set(self._compare_layers)
        for lyr in self._available_layers():
            cb = QCheckBox(lyr)
            cb.setChecked(lyr in default_cols or not default_cols)
            cb.stateChanged.connect(lambda _=0: self._rebuild_detail())
            self._col_checks[lyr] = cb
            col_row.addWidget(cb)
        col_row.addStretch()
        outer.addLayout(col_row)

        # 본문 스플리터: 좌 맵 | 우 목록 (고정 배치)
        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.addWidget(self._build_map_panel())
        self._splitter.addWidget(self._build_list_panel())
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([360, 900])
        outer.addWidget(self._splitter, 1)

        btn_close = QPushButton("닫기")
        btn_close.setObjectName("primary")
        btn_close.clicked.connect(self.accept)
        outer.addWidget(btn_close, alignment=Qt.AlignRight)

    def _transparent_scroll(self) -> QScrollArea:
        """테마 배경이 비치는(흰 배경 없는) 스크롤 영역."""
        sc = QScrollArea()
        sc.setFrameShape(QFrame.NoFrame)
        sc.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        sc.viewport().setAutoFillBackground(False)
        return sc

    def _build_map_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        cap = QLabel("defect 밀도 (색이 진할수록 많음)")
        cap.setObjectName("dim")
        lay.addWidget(cap)
        self._map = HeatmapWaferMap()
        map_scroll = self._transparent_scroll()
        map_scroll.setWidgetResizable(False)
        map_scroll.setAlignment(Qt.AlignCenter)
        map_scroll.setWidget(self._map)
        self._map.cell_clicked.connect(self._on_cell_clicked)
        lay.addWidget(map_scroll, 1)
        self.lbl_map = QLabel("")
        self.lbl_map.setObjectName("dim")
        self.lbl_map.setStyleSheet("font-size:10px;")
        self.lbl_map.setWordWrap(True)
        lay.addWidget(self.lbl_map)
        return panel

    def _build_list_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        head = QHBoxLayout()
        self.lbl_detail = QLabel("위치를 클릭하면 그 자리의 defect 이 여기에 나열됩니다.")
        self.lbl_detail.setObjectName("dim")
        head.addWidget(self.lbl_detail, 1)
        self.btn_add_all = QPushButton("이 위치 전체 담기")
        self.btn_add_all.setObjectName("mini")
        self.btn_add_all.setToolTip("이 위치의 defect 을 모두 출력 트레이에 담습니다.")
        self.btn_add_all.clicked.connect(self._add_all_current)
        self.btn_add_all.setEnabled(False)
        head.addWidget(self.btn_add_all, 0)
        lay.addLayout(head)

        self._detail_scroll = self._transparent_scroll()
        self._detail_scroll.setWidgetResizable(True)
        self._detail_host = QWidget()
        self._detail_host.setStyleSheet("background: transparent;")
        self._detail_box = QVBoxLayout(self._detail_host)
        self._detail_box.setContentsMargins(2, 2, 2, 2)
        self._detail_box.setSpacing(8)
        self._detail_box.addStretch()
        self._detail_scroll.setWidget(self._detail_host)
        lay.addWidget(self._detail_scroll, 1)
        return panel

    # ---- 웨이퍼맵 / 상호작용 ----------------------------------------
    def _on_wafer_changed(self, wafer: str) -> None:
        self._current_wafer = wafer
        self._selected_key = None
        self._refresh_map()
        self._rebuild_detail()

    def _refresh_map(self) -> None:
        entries = self._current_entries()
        observed = {(r.col, r.row) for _, r in entries}
        die_count = len(observed)
        subdivide = heatmap.should_subdivide(die_count)
        xr, yr = heatmap.local_ranges([r for _, r in entries])
        self._groups = heatmap.group_defects(entries, subdivide, xr, yr)
        density = {k: len(v) for k, v in self._groups.items()}

        prod = config.active_product()
        valid = None
        caption = prod.name if prod.source == "db" else ""  # 제품명만(‘모양 정합’ 미표기)
        if prod.die_map and observed:
            align = wafermap_align.align_observed_to_diemap(observed, prod.die_map)
            if align.overlap >= _ALIGN_MIN_OVERLAP:
                valid = wafermap_align.shifted_die_map(prod.die_map, align)
        paint_valid = (valid | observed) if valid else None
        if paint_valid is not None:
            # 내용 bounding box 로 정규화(맵이 여백에 떠 보이거나 잘리지 않게).
            content = set(paint_valid) | observed
            min_col = min(c for c, _ in content)
            min_row = min(r for _, r in content)
            cols = max(c for c, _ in content) - min_col + 1
            rows = max(r for _, r in content) - min_row + 1
            origin = (min_col, min_row)
        else:
            max_col = max((c for c, _ in observed), default=0)
            max_row = max((r for _, r in observed), default=0)
            cols = max(prod.kla_package_x_count, max_col + 1)
            rows = max(prod.kla_package_y_count, max_row + 1)
            origin = (0, 0)
        self._map.set_data(cols, rows, paint_valid, subdivide, density, origin=origin)

        sub_txt = " · die 4×5 분할" if subdivide else ""
        n_def = sum(density.values())
        wafer_txt = "전체 wafer" if self._current_wafer == _ALL_WAFERS else f"wafer {self._current_wafer}"
        self.lbl_map.setText(
            f"{wafer_txt} · die {die_count}개 · defect {n_def}개{sub_txt}"
            + (f"\n{caption}" if caption else "")
        )

    def _on_cell_clicked(self, key: HeatKey) -> None:
        self._selected_key = key
        self._rebuild_detail()

    def _clear_detail(self) -> None:
        # 마지막 stretch 를 제외한 위젯 제거
        while self._detail_box.count() > 1:
            item = self._detail_box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _rebuild_detail(self) -> None:
        self._clear_detail()
        key = self._selected_key
        indices = self._groups.get(key, []) if key else []
        self.btn_add_all.setEnabled(bool(indices))
        if not key:
            self.lbl_detail.setText("위치를 클릭하면 그 자리의 defect 이 여기에 나열됩니다.")
            return
        loc = (f"die({key.col},{key.row})"
               + (f" · 하위셀({key.sub_col},{key.sub_row})" if key.subdivided else ""))
        self.lbl_detail.setText(f"{loc} — defect {len(indices)}개")
        show_compares = self._selected_compare_layers()
        for bi in indices:
            self._detail_box.insertWidget(
                self._detail_box.count() - 1, self._make_row(bi, show_compares)
            )

    def _make_row(self, bi: int, show_compares: list[str]) -> QWidget:
        """한 defect 행 — 기준 + 매칭된 비교 layer 사진만 가로로 나열."""
        item = self.matches[bi]
        base = item.base
        row = QFrame()
        row.setObjectName("cell")
        row.setStyleSheet(
            f"QFrame#cell {{ background:{theme.BG_ELEV};"
            f" border:1px solid {theme.NEON_SOFT}; border-radius:8px; }}"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)

        # 행 헤더(위치/ wafer + 담기)
        head = QVBoxLayout()
        head.setSpacing(4)
        info = QLabel(f"wafer {base.wafer_id}\ndie({base.col},{base.row})\npos {base.position_key}")
        info.setObjectName("dim")
        info.setStyleSheet("font-size:10px;")
        head.addWidget(info)
        btn = QPushButton("＋ 담기")
        btn.setObjectName("mini")
        btn.setToolTip("이 defect 을 출력 트레이에 담습니다.")
        btn.clicked.connect(lambda _=0, i=bi: self._on_add([i]))
        head.addWidget(btn)
        head.addStretch()
        head_host = QWidget()
        head_host.setFixedWidth(120)
        head_host.setLayout(head)
        lay.addWidget(head_host)

        # 기준 사진(항상 맨 앞)
        lay.addWidget(self._thumb_with_badge(base.image_path, self._base_layer, is_base=True))
        # 매칭된 비교 layer 사진만
        for lyr in show_compares:
            mr = item.for_layer(lyr)
            if mr and mr.is_match and mr.matched is not None:
                lay.addWidget(self._thumb_with_badge(mr.matched.image_path, lyr))
        lay.addStretch()
        return row

    def _thumb_with_badge(self, image_path, layer: str, *, is_base: bool = False) -> QWidget:
        """썸네일 + 좌상단 layer 배지."""
        px = _THUMB_PX
        holder = QLabel()
        holder.setAlignment(Qt.AlignCenter)
        holder.setFixedSize(px, int(px * 0.78))
        holder.setStyleSheet(
            f"background:{theme.BG}; border:1px solid {theme.NEON_SOFT};"
            f" border-radius:6px; color:{theme.TEXT_DIM}; font-size:10px;"
        )
        path = self._thumb_cache.get_full_thumbnail(image_path, max_size=px) \
            if self._thumb_cache is not None else None
        if path is not None:
            pix = QPixmap(str(path))
            if not pix.isNull():
                holder.setPixmap(
                    pix.scaled(px, int(px * 0.78), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                holder.setToolTip(str(image_path))
            else:
                holder.setText("이미지 없음")
        else:
            holder.setText("이미지 없음")
        badge = QLabel(("★ " + layer) if is_base else layer, holder)
        badge.setObjectName("layerBadgeBase" if is_base else "layerBadge")
        badge.adjustSize()
        badge.move(5, 5)
        badge.show()
        return holder

    # ---- 출력 트레이 담기 -------------------------------------------
    def _add_all_current(self) -> None:
        key = self._selected_key
        indices = self._groups.get(key, []) if key else []
        if indices:
            self._on_add(list(indices))
