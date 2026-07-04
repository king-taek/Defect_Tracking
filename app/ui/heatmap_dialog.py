"""Defect 히트맵 팝업 (항목 4·5).

웨이퍼맵에 defect 밀도를 색으로 표시하고, 위치(die/하위셀)를 클릭하면 그 위치의 defect
들을 세로로 나열한다. 컬럼은 layer 이며(기준+선택 비교 layer 기본), 사용자가 바꿀 수 있다.
각 행은 '출력에 추가'로 공유 출력 트레이에 담을 수 있다.

레이아웃은 프리셋(≈10종)을 콤보로 전환해 사용자가 실행 후 선호를 고르도록 한다.
die 개수가 50개 미만이면 각 die 를 4×5(20) 하위셀로 나눠 die 내부 위치를 구분한다.

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
    QGridLayout,
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

# 레이아웃 프리셋(≈10종) — 사용자가 실행 후 선호를 고른다.
# orient: 스플리터 방향, map_first: 맵을 앞(좌/상)에 둘지, map/list: 스트레치 비중,
# thumb: 상세 목록 썸네일 픽셀.
_PRESETS = [
    {"name": "좌 맵 · 우 목록", "orient": "H", "map_first": True, "map": 1, "list": 2, "thumb": 120},
    {"name": "우 맵 · 좌 목록", "orient": "H", "map_first": False, "map": 1, "list": 2, "thumb": 120},
    {"name": "상 맵 · 하 목록", "orient": "V", "map_first": True, "map": 1, "list": 2, "thumb": 120},
    {"name": "하 맵 · 상 목록", "orient": "V", "map_first": False, "map": 1, "list": 2, "thumb": 120},
    {"name": "좌 맵(크게) · 우 목록", "orient": "H", "map_first": True, "map": 2, "list": 1, "thumb": 110},
    {"name": "좌 맵(작게) · 우 목록(넓게)", "orient": "H", "map_first": True, "map": 1, "list": 3, "thumb": 130},
    {"name": "우 목록 조밀(썸네일 소)", "orient": "H", "map_first": True, "map": 1, "list": 2, "thumb": 80},
    {"name": "우 목록 크게(썸네일 대)", "orient": "H", "map_first": True, "map": 1, "list": 2, "thumb": 180},
    {"name": "상 맵 대형 · 하 목록", "orient": "V", "map_first": True, "map": 2, "list": 2, "thumb": 120},
    {"name": "하 맵 · 상 목록 조밀", "orient": "V", "map_first": False, "map": 1, "list": 2, "thumb": 90},
]


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
    ) -> None:
        self._cols = max(0, cols)
        self._rows = max(0, rows)
        self._valid = frozenset(valid) if valid else None
        self._subdivide = subdivide
        self._density = density
        self._max_count = max(density.values(), default=1)
        self._selected = None
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
        return self._GAP + col * (dw + self._GAP), self._GAP + row * (dh + self._GAP)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        border = QColor(theme.NEON_SOFT)
        die_border = QColor(theme.BASE_GLOW)
        for row in range(self._rows):
            for col in range(self._cols):
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
        if not (0 <= key.col < self._cols and 0 <= key.row < self._rows):
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
        col = (pos.x() - self._GAP) // (dw + self._GAP)
        row = (pos.y() - self._GAP) // (dh + self._GAP)
        if not (0 <= col < self._cols and 0 <= row < self._rows):
            return
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
    """defect 히트맵 팝업(웨이퍼맵 + layer 컬럼별 defect 목록)."""

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
        self.setMinimumSize(920, 640)

        self._groups: dict[HeatKey, list[int]] = {}
        self._selected_key: Optional[HeatKey] = None
        preset_idx = int(getattr(settings, "heatmap_layout", 0) or 0)
        self._preset_idx = max(0, min(len(_PRESETS) - 1, preset_idx))
        self._thumb_px = _PRESETS[self._preset_idx]["thumb"]

        wafers = self._wafers()
        self._current_wafer = current_wafer if current_wafer in wafers else (
            wafers[0] if wafers else ""
        )

        self._build()
        self._apply_preset(self._preset_idx)
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
        """컬럼으로 선택 가능한 layer: 기준 + matches 에 등장하는 모든 비교 layer(순서 유지)."""
        layers = [self._base_layer]
        for m in self.matches:
            for r in m.results:
                if r.compare_layer not in layers:
                    layers.append(r.compare_layer)
        return layers

    def _selected_columns(self) -> list[str]:
        cols = [self._base_layer]  # 기준은 항상 포함(첫 컬럼)
        for lyr, cb in self._col_checks.items():
            if lyr != self._base_layer and cb.isChecked():
                cols.append(lyr)
        return cols

    # ---- UI 구성 -----------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)

        # 상단 컨트롤 바: 제목 / wafer 선택 / 레이아웃 프리셋
        bar = QHBoxLayout()
        title = QLabel("Defect 히트맵")
        title.setObjectName("title")
        bar.addWidget(title)
        bar.addStretch()
        bar.addWidget(QLabel("Wafer"))
        self.cmb_wafer = QComboBox()
        self.cmb_wafer.addItems(self._wafers())
        if self._current_wafer:
            self.cmb_wafer.setCurrentText(self._current_wafer)
        self.cmb_wafer.currentTextChanged.connect(self._on_wafer_changed)
        bar.addWidget(self.cmb_wafer)
        bar.addSpacing(12)
        bar.addWidget(QLabel("레이아웃"))
        self.cmb_preset = QComboBox()
        self.cmb_preset.addItems([p["name"] for p in _PRESETS])
        self.cmb_preset.setCurrentIndex(self._preset_idx)
        self.cmb_preset.currentIndexChanged.connect(self._on_preset_changed)
        bar.addWidget(self.cmb_preset)
        outer.addLayout(bar)

        # 컬럼(layer) 선택 체크박스 행
        col_row = QHBoxLayout()
        col_row.setSpacing(8)
        col_row.addWidget(QLabel("컬럼 layer:"))
        self._col_checks: dict[str, QCheckBox] = {}
        default_cols = set([self._base_layer] + self._compare_layers)
        for lyr in self._available_layers():
            cb = QCheckBox(lyr)
            cb.setChecked(lyr in default_cols)
            if lyr == self._base_layer:
                cb.setChecked(True)
                cb.setEnabled(False)  # 기준은 항상 첫 컬럼
                cb.setToolTip("기준 layer 는 항상 표시됩니다.")
            cb.stateChanged.connect(lambda _=0: self._rebuild_detail())
            self._col_checks[lyr] = cb
            col_row.addWidget(cb)
        col_row.addStretch()
        outer.addLayout(col_row)

        # 본문 스플리터: 맵 패널 | 목록 패널
        self._splitter = QSplitter(Qt.Horizontal)
        self._map_panel = self._build_map_panel()
        self._list_panel = self._build_list_panel()
        self._splitter.addWidget(self._map_panel)
        self._splitter.addWidget(self._list_panel)
        outer.addWidget(self._splitter, 1)

        btn_close = QPushButton("닫기")
        btn_close.setObjectName("primary")
        btn_close.clicked.connect(self.accept)
        outer.addWidget(btn_close, alignment=Qt.AlignRight)

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
        self._map.cell_clicked.connect(self._on_cell_clicked)
        map_scroll = QScrollArea()
        map_scroll.setWidgetResizable(False)
        map_scroll.setAlignment(Qt.AlignCenter)
        map_scroll.setFrameShape(QFrame.NoFrame)
        map_scroll.setWidget(self._map)
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

        self._detail_scroll = QScrollArea()
        self._detail_scroll.setWidgetResizable(True)
        self._detail_scroll.setFrameShape(QFrame.NoFrame)
        self._detail_host = QWidget()
        self._detail_grid = QGridLayout(self._detail_host)
        self._detail_grid.setContentsMargins(4, 4, 4, 4)
        self._detail_grid.setHorizontalSpacing(8)
        self._detail_grid.setVerticalSpacing(8)
        self._detail_grid.setAlignment(Qt.AlignTop)
        self._detail_scroll.setWidget(self._detail_host)
        lay.addWidget(self._detail_scroll, 1)
        return panel

    # ---- 레이아웃 프리셋 --------------------------------------------
    def _apply_preset(self, idx: int) -> None:
        p = _PRESETS[idx]
        self._thumb_px = p["thumb"]
        self._splitter.setOrientation(
            Qt.Horizontal if p["orient"] == "H" else Qt.Vertical
        )
        # 순서 재배치: 맵을 앞/뒤로.
        self._map_panel.setParent(None)
        self._list_panel.setParent(None)
        if p["map_first"]:
            self._splitter.addWidget(self._map_panel)
            self._splitter.addWidget(self._list_panel)
            self._splitter.setSizes([p["map"] * 300, p["list"] * 300])
        else:
            self._splitter.addWidget(self._list_panel)
            self._splitter.addWidget(self._map_panel)
            self._splitter.setSizes([p["list"] * 300, p["map"] * 300])

    def _on_preset_changed(self, idx: int) -> None:
        self._preset_idx = idx
        self._apply_preset(idx)
        self._rebuild_detail()
        try:
            self._settings.heatmap_layout = idx
            self._settings.save()
        except OSError:
            pass

    # ---- 웨이퍼맵 / 상호작용 ----------------------------------------
    def _on_wafer_changed(self, wafer: str) -> None:
        self._current_wafer = wafer
        self._selected_key = None
        self._refresh_map()
        self._rebuild_detail()

    def _refresh_map(self) -> None:
        wafer = self._current_wafer
        entries = [
            (i, m.base) for i, m in enumerate(self.matches)
            if m.base.wafer_id == wafer
            and m.base.col is not None and m.base.row is not None
            and m.base.col >= 0 and m.base.row >= 0
        ]
        observed = {(r.col, r.row) for _, r in entries}
        die_count = len(observed)
        subdivide = heatmap.should_subdivide(die_count)
        xr, yr = heatmap.local_ranges([r for _, r in entries])
        self._groups = heatmap.group_defects(entries, subdivide, xr, yr)
        density = {k: len(v) for k, v in self._groups.items()}

        prod = config.active_product()
        valid = None
        caption = prod.name if prod.source == "db" else ""
        if prod.die_map and observed:
            align = wafermap_align.align_observed_to_diemap(observed, prod.die_map)
            if align.overlap >= _ALIGN_MIN_OVERLAP:
                valid = wafermap_align.shifted_die_map(prod.die_map, align)
                caption = f"{prod.name} · 모양 정합 {align.overlap * 100:.0f}%"
        all_dies = set(observed) | (valid or set())
        max_col = max((c for c, _ in all_dies), default=0)
        max_row = max((r for _, r in all_dies), default=0)
        cols = max(prod.kla_package_x_count, max_col + 1)
        rows = max(prod.kla_package_y_count, max_row + 1)
        paint_valid = (valid | observed) if valid else None
        self._map.set_data(cols, rows, paint_valid, subdivide, density)

        sub_txt = " · die 4×5 분할" if subdivide else ""
        n_def = sum(density.values())
        self.lbl_map.setText(
            f"wafer {wafer} · die {die_count}개 · defect {n_def}개{sub_txt}"
            + (f"\n{caption}" if caption else "")
        )

    def _on_cell_clicked(self, key: HeatKey) -> None:
        self._selected_key = key
        self._rebuild_detail()

    def _clear_detail(self) -> None:
        while self._detail_grid.count():
            item = self._detail_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _rebuild_detail(self) -> None:
        self._clear_detail()
        key = self._selected_key
        indices = self._groups.get(key, []) if key else []
        columns = self._selected_columns()
        self.btn_add_all.setEnabled(bool(indices))
        if not key:
            self.lbl_detail.setText("위치를 클릭하면 그 자리의 defect 이 여기에 나열됩니다.")
            return
        loc = (f"die({key.col},{key.row})"
               + (f" · 하위셀({key.sub_col},{key.sub_row})" if key.subdivided else ""))
        self.lbl_detail.setText(f"{loc} — defect {len(indices)}개")

        # 헤더(컬럼 layer 이름)
        self._detail_grid.addWidget(self._col_header("위치 / 담기"), 0, 0)
        for ci, lyr in enumerate(columns):
            self._detail_grid.addWidget(
                self._col_header(("★ " + lyr) if lyr == self._base_layer else lyr),
                0, ci + 1,
            )
        # 각 defect 행
        for ri, bi in enumerate(indices, start=1):
            item = self.matches[bi]
            self._detail_grid.addWidget(self._row_head(bi, item), ri, 0)
            for ci, lyr in enumerate(columns):
                self._detail_grid.addWidget(
                    self._layer_thumb(item, lyr), ri, ci + 1
                )

    def _col_header(self, text: str) -> QWidget:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"background:{theme.BG_ELEV}; color:{theme.TEXT}; font-weight:700;"
            f" font-size:11px; padding:4px 6px; border-radius:6px;"
        )
        lbl.setAlignment(Qt.AlignCenter)
        return lbl

    def _row_head(self, bi: int, item: BaseDefectMatches) -> QWidget:
        base = item.base
        w = QFrame()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(4)
        info = QLabel(f"die({base.col},{base.row})\npos {base.position_key}")
        info.setObjectName("dim")
        info.setStyleSheet("font-size:10px;")
        info.setAlignment(Qt.AlignCenter)
        lay.addWidget(info)
        btn = QPushButton("＋ 담기")
        btn.setObjectName("mini")
        btn.setToolTip("이 defect 을 출력 트레이에 담습니다.")
        btn.clicked.connect(lambda _=0, i=bi: self._add_one(i))
        lay.addWidget(btn)
        return w

    def _layer_thumb(self, item: BaseDefectMatches, layer: str) -> QWidget:
        """한 defect 의 특정 layer 이미지를 썸네일로 표시(매칭 없으면 표식)."""
        px = self._thumb_px
        holder = QLabel()
        holder.setAlignment(Qt.AlignCenter)
        holder.setFixedSize(px, int(px * 0.78))
        holder.setStyleSheet(
            f"background:{theme.BG}; border:1px solid {theme.NEON_SOFT};"
            f" border-radius:6px; color:{theme.TEXT_DIM}; font-size:10px;"
        )
        if layer == self._base_layer:
            rec = item.base
        else:
            mr = item.for_layer(layer)
            rec = mr.matched if (mr and mr.is_match and mr.matched is not None) else None
        if rec is None:
            holder.setText("매칭 없음")
            return holder
        path = self._thumb_cache.get_full_thumbnail(rec.image_path, max_size=px) \
            if self._thumb_cache is not None else None
        if path is not None:
            pix = QPixmap(str(path))
            if not pix.isNull():
                holder.setPixmap(
                    pix.scaled(px, int(px * 0.78), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                holder.setToolTip(str(rec.image_path))
                return holder
        holder.setText("이미지 없음")
        return holder

    # ---- 출력 트레이 담기 -------------------------------------------
    def _add_one(self, bi: int) -> None:
        self._on_add([bi])

    def _add_all_current(self) -> None:
        key = self._selected_key
        indices = self._groups.get(key, []) if key else []
        if indices:
            self._on_add(list(indices))
