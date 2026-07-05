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

from collections import defaultdict
from typing import Callable, Optional

from PySide6.QtCore import QRect, Qt, QThreadPool, Signal
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
from app.clustering import Cluster, cluster_records, cross_layer_groups
from app.heatmap import HeatKey
from app.models import BaseDefectMatches, DefectRecord
from app.thumbnails import ThumbnailCache
from app.ui import theme

_ALIGN_MIN_OVERLAP = 0.6
_ALL_WAFERS = "전체"
_THUMB_PX = 150  # 상세 목록 썸네일 크기(고정)


# 히트맵 die 색(배경 theme.BG 위에서 잘 보이도록 밝게). 배경/빈 die 와 구분된다.
_HEAT_LO = QColor("#6fb0e0")   # 낮은 밀도(밝은 슬레이트블루)
_HEAT_HI = QColor("#ff8a5c")   # 높은 밀도(밝은 코랄)


def _heat_color(count: int, max_count: int) -> QColor:
    """defect 개수를 밀도 색으로 변환(0=빈 die 톤, 많을수록 밝은 코랄)."""
    if count <= 0:
        return QColor(theme.BG_ELEV)  # 빈 die: 배경(BG)보다 밝은 중간 톤
    lo = _HEAT_LO
    hi = _HEAT_HI
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

    selection_changed = Signal(object)  # list[HeatKey]

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
        self._selected_keys: set[HeatKey] = set()
        # 여러 die 선택 모드 + 러버밴드 상태. 드래그 사각 선택은 _multi 와 무관하게 항상 가능;
        # _multi 는 '클릭=토글/박스=합집합'(on) vs '클릭·박스=교체'(off) 만 좌우한다.
        self._multi = False
        self._rubber_origin = None
        self._rubber_cur = None
        self._dragging = False
        # 그리기 원점(실좌표) — 내용 bounding box 좌상단을 (0,0) 픽셀에 맞춘다(맵 떠보임/잘림 방지).
        self._origin_col = 0
        self._origin_row = 0
        self.setToolTip("defect 밀도 — 색이 진할수록 defect 이 많음. 위치를 클릭하세요.")

    def set_multi(self, on: bool) -> None:
        self._multi = on
        self._selected_keys = set()
        self._rubber_origin = None
        self._rubber_cur = None
        self.update()
        self.selection_changed.emit([])

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
        self._selected_keys = set()
        self._rubber_origin = None
        self._rubber_cur = None
        self._origin_col, self._origin_row = origin
        dw, dh = self._die_w(), self._die_h()
        self.setFixedSize(
            max(40, self._cols * (dw + self._GAP) + self._GAP),
            max(40, self._rows * (dh + self._GAP) + self._GAP),
        )
        self.update()

    def _die_origin(self, col: int, row: int) -> tuple[int, int]:
        dw, dh = self._die_w(), self._die_h()
        return (self._GAP + (col - self._origin_col) * (dw + self._GAP),
                self._GAP + (row - self._origin_row) * (dh + self._GAP))

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        # 위젯 전체를 UI 어두운 배경으로 채운다(흰 배경 제거, die 색과 구분).
        painter.fillRect(self.rect(), QColor(theme.BG))
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

    def _key_rect(self, key: HeatKey) -> QRect:
        ox, oy = self._die_origin(key.col, key.row)
        if self._subdivide and key.subdivided:
            return QRect(ox + key.sub_col * self._SUBCELL_PX,
                         oy + key.sub_row * self._SUBCELL_PX,
                         self._SUBCELL_PX, self._SUBCELL_PX)
        return QRect(ox, oy, self._die_w(), self._die_h())

    def _paint_selection(self, painter) -> None:
        # 선택 die: 얇은(1px) 네온 녹색 외곽선만(채움 없음).
        green = QColor("#39ff14")
        painter.setPen(QPen(green, 1))
        for key in self._selected_keys:
            if not (self._origin_col <= key.col < self._origin_col + self._cols
                    and self._origin_row <= key.row < self._origin_row + self._rows):
                continue
            painter.drawRect(self._key_rect(key).adjusted(0, 0, -1, -1))
        # 드래그 러버밴드
        if self._rubber_origin is not None and self._rubber_cur is not None:
            rb = QRect(self._rubber_origin, self._rubber_cur).normalized()
            painter.setPen(QPen(green, 1, Qt.DashLine))
            painter.drawRect(rb)

    def _key_at(self, pos) -> Optional[HeatKey]:
        dw, dh = self._die_w(), self._die_h()
        dc = (pos.x() - self._GAP) // (dw + self._GAP)
        dr = (pos.y() - self._GAP) // (dh + self._GAP)
        if not (0 <= dc < self._cols and 0 <= dr < self._rows):
            return None
        col = int(dc) + self._origin_col
        row = int(dr) + self._origin_row
        if self._subdivide:
            ox, oy = self._die_origin(col, row)
            sc = min(heatmap.SUB_COLS - 1, max(0, (pos.x() - ox) // self._SUBCELL_PX))
            sr = min(heatmap.SUB_ROWS - 1, max(0, (pos.y() - oy) // self._SUBCELL_PX))
            key = HeatKey(col, row, int(sc), int(sr))
        else:
            key = HeatKey(col, row)
        return key if self._density.get(key, 0) > 0 else None

    def _keys_in_rect(self, rect: QRect) -> list[HeatKey]:
        out = []
        for key, cnt in self._density.items():
            if cnt > 0 and self._key_rect(key).intersects(rect):
                out.append(key)
        return out

    def _emit_selection(self) -> None:
        keys = sorted(self._selected_keys,
                      key=lambda k: (k.row, k.col, k.sub_row, k.sub_col))
        self.selection_changed.emit(keys)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() != Qt.LeftButton:
            return
        # 드래그 사각 선택은 항상 시작 가능(멀티 모드 여부와 무관).
        pos = event.position().toPoint()
        self._rubber_origin = pos
        self._rubber_cur = pos
        self._dragging = False

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._rubber_origin is None:
            return
        pos = event.position().toPoint()
        if (pos - self._rubber_origin).manhattanLength() > 4:
            self._dragging = True
        self._rubber_cur = pos
        if self._dragging:
            self.update()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() != Qt.LeftButton or self._rubber_origin is None:
            return
        origin = self._rubber_origin
        cur = self._rubber_cur or origin
        if self._dragging:
            # 사각 드래그: 사각 내 die 선택. 멀티면 합집합, 아니면 교체.
            keys = set(self._keys_in_rect(QRect(origin, cur).normalized()))
            self._selected_keys = (self._selected_keys | keys) if self._multi else keys
        else:
            # 클릭: 멀티면 토글, 아니면 단일 교체.
            key = self._key_at(origin)
            if self._multi:
                if key is not None:
                    self._selected_keys.discard(key) if key in self._selected_keys \
                        else self._selected_keys.add(key)
            else:
                self._selected_keys = {key} if key is not None else set()
        self._rubber_origin = None
        self._rubber_cur = None
        self._dragging = False
        self.update()
        self._emit_selection()


# 클러스터 표시 위젯은 공유 모듈로 이동(메인 매치와 공용). 하위 호환 별칭 유지.
from app.ui.cluster_view import (  # noqa: E402
    ClusteredThumb as _ClusteredThumb,
    ClusterMembersPopup as _ClusterMembersPopup,
    ClickThumb as _ClickThumb,
    load_thumb_holder as _load_thumb_holder,
)


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
        records_by_layer: Optional[dict] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.matches = matches
        self._base_layer = base_layer
        self._compare_layers = list(compare_layers)
        self._thumb_cache = thumb_cache
        self._on_add = on_add_to_export
        self._settings = settings
        self._records_by_layer = records_by_layer or {}
        # 교차 매칭(전체 defect 모드)·매칭 판정용 허용오차.
        self._tolerance = getattr(settings, "tolerance", None) or config.DEFAULT_TOLERANCE
        self.setWindowTitle("Defect 히트맵")
        self.setMinimumSize(900, 600)

        self._groups: dict[HeatKey, list[int]] = {}
        self._selected_keys: list[HeatKey] = []  # 현재 선택된 위치(단일/다중)
        self._add_targets: list[int] = []  # '이 위치 출력에 넣기' 대상(매칭된 기준)
        self._pending_thumbs: list = []  # 상세 지연 로딩 썸네일 위젯
        self._thumb_token = 0            # stale 썸네일 로딩 무시
        self._active_thumb_workers: set = set()  # 실행 중 워커 참조 유지(GC 방지)
        self._hm_align_cache: dict = {}  # observed→alignment 캐시(매 refresh 재계산 방지)
        self._xr = (0.0, 1.0)   # die 내부 local 좌표 범위(subcell 판정용)
        self._yr = (0.0, 1.0)
        self._subdivide = False

        # 기본은 '전체' wafer(사용자 요청). current_wafer 는 무시하고 전체로 시작.
        self._current_wafer = _ALL_WAFERS

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

    def _all_layers(self) -> list[str]:
        """조사 대상 전체 layer — 메인 기준 + 비교 layer(중복 제거, 순서 유지)."""
        out: list[str] = []
        for lyr in [self._base_layer, *self._available_layers()]:
            if lyr and lyr not in out:
                out.append(lyr)
        return out

    def _selected_layers(self) -> list[str]:
        """조사할(체크된) layer 목록. 기준 특별취급 없음."""
        return [lyr for lyr, cb in self._col_checks.items() if cb.isChecked()]

    def _wafer_ok(self, rec) -> bool:
        return self._current_wafer == _ALL_WAFERS or rec.wafer_id == self._current_wafer

    def _base_entries(self) -> list[tuple[int, object]]:
        """기준 defect 전체를 (base_index, base_record) 로. wafer 필터 적용.

        매치만 모드의 맵 density·선택→index 매핑(_groups) 공통. (미매칭 숨김은 상세 목록에서만.)
        """
        out: list[tuple[int, object]] = []
        for i, m in enumerate(self.matches):
            b = m.base
            if b.col is None or b.row is None or b.col < 0 or b.row < 0:
                continue
            if not self._wafer_ok(b):
                continue
            out.append((i, b))
        return out

    def _is_matched(self, bi: int) -> bool:
        """메인 비교 layer 중 하나 이상에서 매치되면 True('출력에 넣기' 대상 판정)."""
        m = self.matches[bi]
        return any((r := m.for_layer(lyr)) and r.is_match for lyr in self._compare_layers)

    def _all_defect_entries(self) -> list[tuple[int, object]]:
        """체크된 layer 의 모든 좌표 OK defect(맵 density 용). 기준 특별취급 없음."""
        out: list[tuple[int, object]] = []
        k = 0
        for lyr in self._selected_layers():
            for rec in self._records_by_layer.get(lyr, []):
                if not getattr(rec, "ok", False) or not self._wafer_ok(rec):
                    continue
                out.append((k, rec))
                k += 1
        return out

    def _map_entries(self) -> list[tuple[int, object]]:
        """맵 density 계산용 entries — 상시 조사 모드(체크된 layer 전체 defect)."""
        return self._all_defect_entries()

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

        # 조사할 layer(기준 개념 없음): 모든 layer 를 체크박스로, 체크된 것들의 defect 을 교차 조사.
        col_row = QHBoxLayout()
        col_row.setSpacing(8)
        col_row.addWidget(QLabel("조사할 layer:"))
        self._col_checks: dict[str, QCheckBox] = {}
        for lyr in self._all_layers():
            cb = QCheckBox(lyr)
            cb.setChecked(True)  # 기본 전체 체크
            cb.stateChanged.connect(lambda _=0: self._on_layers_changed())
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
        self._map.selection_changed.connect(self._on_selection_changed)
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
        # 여러 다이 선택 토글(드래그 사각 선택은 이 토글과 무관하게 항상 가능).
        self.btn_multi = QPushButton("여러 다이 선택: OFF")
        self.btn_multi.setObjectName("mini")
        self.btn_multi.setCheckable(True)
        self.btn_multi.setToolTip(
            "켜면 클릭이 여러 die 를 누적 토글합니다.\n"
            "(끄면 클릭=한 개 선택. 드래그 사각 다중 선택은 항상 가능합니다.)"
        )
        self.btn_multi.toggled.connect(self._on_multi_toggled)
        head.addWidget(self.btn_multi, 0)
        self.btn_add_all = QPushButton("이 위치 출력에 넣기")
        self.btn_add_all.setObjectName("mini")
        self.btn_add_all.setToolTip("선택 위치의 매칭된 기준 defect 을 출력 트레이에 담습니다.")
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
        self._selected_keys = []
        self._refresh_map()
        self._rebuild_detail()

    def _on_multi_toggled(self, on: bool) -> None:
        self.btn_multi.setText(f"여러 다이 선택: {'ON' if on else 'OFF'}")
        self._map.set_multi(on)  # set_multi 가 selection_changed([]) 를 emit → 상세 초기화

    def _on_layers_changed(self) -> None:
        # layer 체크 변경 → 맵(선택 layer 반영)·상세 실시간 갱신, 선택 위치 유지.
        self._refresh_map(preserve_selection=True)
        self._rebuild_detail()

    def _refresh_map(self, preserve_selection: bool = False) -> None:
        keep = list(self._selected_keys) if preserve_selection else []
        entries = self._map_entries()
        observed = {(r.col, r.row) for _, r in entries}
        die_count = len(observed)
        subdivide = heatmap.should_subdivide(die_count)
        xr, yr = heatmap.local_ranges([r for _, r in entries])
        self._xr, self._yr, self._subdivide = xr, yr, subdivide
        density_groups = heatmap.group_defects(entries, subdivide, xr, yr)
        density = {k: len(v) for k, v in density_groups.items()}
        # 매치만 상세용 그룹(base index)은 항상 기준 defect 전체로, 동일 subdivide/range 로 키 정합.
        self._groups = heatmap.group_defects(self._base_entries(), subdivide, xr, yr)
        self._selected_keys = [k for k in keep if k in density]

        prod = config.active_product()
        valid = None
        caption = prod.name if prod.source == "db" else ""  # 제품명만(‘모양 정합’ 미표기)
        if prod.die_map and observed:
            # 정합은 관측 die 집합·제품이 같으면 재계산 불필요 → 캐시(매 refresh 비용 절감).
            ckey = (prod.name, frozenset(observed))
            align = self._hm_align_cache.get(ckey)
            if align is None:
                align = wafermap_align.align_observed_to_diemap(observed, prod.die_map)
                self._hm_align_cache[ckey] = align
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
        # set_data 가 선택을 비우므로, 그 뒤에 유지할 선택을 복원한다.
        if self._selected_keys:
            self._map._selected_keys = set(self._selected_keys)
            self._map.update()

        sub_txt = " · die 4×5 분할" if subdivide else ""
        n_def = sum(density.values())
        wafer_txt = "전체 wafer" if self._current_wafer == _ALL_WAFERS else f"wafer {self._current_wafer}"
        self.lbl_map.setText(
            f"{wafer_txt} · die {die_count}개 · defect {n_def}개{sub_txt}"
            + (f"\n{caption}" if caption else "")
        )

    def _clear_detail(self) -> None:
        # 마지막 stretch 를 제외한 위젯 제거
        while self._detail_box.count() > 1:
            item = self._detail_box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _on_selection_changed(self, keys) -> None:
        self._selected_keys = list(keys)
        self._rebuild_detail()

    def _union_indices(self) -> list[int]:
        """선택된 위치(단일/다중)의 base defect index 합집합(순서 유지, 중복 제거)."""
        seen: set[int] = set()
        out: list[int] = []
        for k in self._selected_keys:
            for bi in self._groups.get(k, []):
                if bi not in seen:
                    seen.add(bi)
                    out.append(bi)
        return out

    def _key_for_record(self, rec) -> HeatKey:
        if self._subdivide and rec.x is not None and rec.y is not None:
            sc, sr = heatmap.subcell_of(rec.x, rec.y, self._xr, self._yr)
            return HeatKey(int(rec.col), int(rec.row), sc, sr)
        return HeatKey(int(rec.col), int(rec.row))

    def _records_at_selection(self) -> list[tuple[str, object]]:
        """선택 위치의 체크된 layer 모든 defect record — (layer, record)."""
        layers = self._selected_layers()
        wafer = self._current_wafer
        key_set = set(self._selected_keys)
        out: list[tuple[str, object]] = []
        for lyr in layers:
            for rec in self._records_by_layer.get(lyr, []):
                if not getattr(rec, "ok", False):
                    continue
                if wafer != _ALL_WAFERS and rec.wafer_id != wafer:
                    continue
                if rec.col is None or rec.row is None:
                    continue
                if self._key_for_record(rec) in key_set:
                    out.append((lyr, rec))
        return out

    def _open_viewer(self, record) -> None:
        from app.ui.image_viewer import ImageViewerDialog
        if isinstance(record, DefectRecord):
            ImageViewerDialog(record, self).exec()

    def _rebuild_detail(self) -> None:
        self._clear_detail()
        self._pending_thumbs = []  # 이번 상세의 지연 썸네일 모음(비동기 로딩)
        # 상시 조사 모드: 체크된 layer 를 교차 매칭해 표시. '출력에 넣기' 대상은 선택 위치의
        # 매칭된 메인 기준 defect(출력은 기준 layer 기반).
        self._add_targets = [bi for bi in self._union_indices() if self._is_matched(bi)]
        self.btn_add_all.setEnabled(bool(self._add_targets))
        if not self._selected_keys:
            self.lbl_detail.setText("위치를 클릭하면 그 자리의 defect 이 여기에 나열됩니다.")
            return
        n_loc = len(self._selected_keys)
        loc = (self._key_label(self._selected_keys[0]) if n_loc == 1 else f"{n_loc}개 위치")
        self._build_all_detail(loc)
        # 썸네일은 백그라운드로 캐시를 구운 뒤 채워, 클릭 즉시 목록이 뜨고 멈추지 않게 한다.
        self._start_detail_thumbs()

    def _build_all_detail(self, loc: str) -> None:
        """조사 모드 — 체크된 layer 를 layer 간 교차 매칭(기준 종속 아님)해 그룹으로.

        교차매치 그룹(≥2 layer)은 전폭 행으로, 개별(미매칭, 1 layer)은 한 섹션에 가로(FlowLayout)
        나열해 빈칸을 줄인다.
        """
        by_layer: dict[str, list] = defaultdict(list)
        for lyr, rec in self._records_at_selection():
            by_layer[lyr].append(rec)
        layer_to_clusters = {lyr: cluster_records(recs) for lyr, recs in by_layer.items()}
        groups = cross_layer_groups(layer_to_clusters, self._tolerance)
        matched = [g for g in groups if len(g) >= 2]
        individual = [g for g in groups if len(g) == 1]
        for g in matched:
            self._detail_box.insertWidget(
                self._detail_box.count() - 1, self._make_group_row(g)
            )
        if individual:
            self._detail_box.insertWidget(
                self._detail_box.count() - 1, self._make_individual_section(individual)
            )
        self.lbl_detail.setText(
            f"{loc} — 교차매치 {len(matched)}그룹 · 개별(미매칭) {len(individual)}개"
        )

    def _make_individual_section(self, groups: list[dict]) -> QWidget:
        """개별(미매칭) 단일-layer 그룹들을 layer 배지+대표(+n) 컴팩트 카드로 가로 나열."""
        from app.ui.flow_layout import FlowLayout

        box = QFrame()
        box.setObjectName("cell")
        box.setStyleSheet(
            f"QFrame#cell {{ background:{theme.BG_ELEV};"
            f" border:1px solid {theme.NEON_SOFT}; border-radius:8px; }}"
        )
        outer = QVBoxLayout(box)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(4)
        cap = QLabel(f"개별(미매칭) — {len(groups)}개")
        cap.setStyleSheet(f"font-size:10px; font-weight:700; color:{theme.NOMATCH};")
        outer.addWidget(cap)
        host = QWidget()
        flow = FlowLayout(host, margin=0, h_spacing=8, v_spacing=8)
        for g in groups:
            (layer, cluster), = g.items()
            flow.addWidget(self._clustered_thumb(cluster, layer, layer == self._base_layer))
        outer.addWidget(host)
        return box

    @staticmethod
    def _key_label(key: HeatKey) -> str:
        return (f"die({key.col},{key.row})"
                + (f" · 하위셀({key.sub_col},{key.sub_row})" if key.subdivided else ""))

    def _row_frame(self):
        row = QFrame()
        row.setObjectName("cell")
        row.setStyleSheet(
            f"QFrame#cell {{ background:{theme.BG_ELEV};"
            f" border:1px solid {theme.NEON_SOFT}; border-radius:8px; }}"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)
        return row, lay

    def _clustered_thumb(self, cluster: Cluster, layer: str, is_base: bool) -> QWidget:
        # 지연 로딩: 위젯은 즉시 만들고, 썸네일은 백그라운드로 캐시를 구운 뒤 채운다.
        w = _ClusteredThumb(cluster, layer, is_base, self._thumb_cache,
                            self._open_viewer, _THUMB_PX, defer=True)
        self._pending_thumbs.append(w)
        return w

    def _start_detail_thumbs(self) -> None:
        """상세에 만든 지연 썸네일들을 백그라운드로 캐시 굽고 준비되는 대로 채운다."""
        from app.workers import FullThumbWorker
        pending = self._pending_thumbs
        if not pending:
            return
        self._thumb_token += 1
        token = self._thumb_token
        items = [(i, str(w.rep_path), w._px) for i, w in enumerate(pending)]
        worker = FullThumbWorker(self._thumb_cache, items)

        def _fill(i, t=token, snap=pending):
            if t == self._thumb_token and 0 <= i < len(snap):
                snap[i].fill()

        worker.signals.ready.connect(_fill)
        # 워커가 끝날 때까지 참조를 유지한다(안 그러면 GC 로 signals 가 사라져 ready 가
        # 도착 안 해 썸네일이 '로딩…'에 멈춘다 — 이 버그의 근본 원인).
        self._active_thumb_workers.add(worker)
        worker.signals.done.connect(
            lambda w=worker: self._active_thumb_workers.discard(w)
        )
        QThreadPool.globalInstance().start(worker)

    def _make_group_row(self, group: dict) -> QWidget:
        """조사 행 — 그룹의 layer 별 대표(+n). 단독이면 개별(미매칭)."""
        row, lay = self._row_frame()
        is_matched = len(group) >= 2
        rep0 = next(iter(group.values())).representative
        head = QVBoxLayout()
        head.setSpacing(4)
        tag = QLabel("교차매치" if is_matched else "개별(미매칭)")
        tag.setStyleSheet(
            f"font-size:10px; font-weight:700;"
            f" color:{theme.MATCH if is_matched else theme.NOMATCH};"
        )
        head.addWidget(tag)
        info = QLabel(f"wafer {rep0.wafer_id}\ndie({rep0.col},{rep0.row})")
        info.setObjectName("dim")
        info.setStyleSheet("font-size:10px;")
        head.addWidget(info)
        head.addStretch()
        head_host = QWidget()
        head_host.setFixedWidth(120)
        head_host.setLayout(head)
        lay.addWidget(head_host)

        for lyr in self._selected_layers():
            if lyr in group:
                lay.addWidget(self._clustered_thumb(group[lyr], lyr, lyr == self._base_layer))
        lay.addStretch()
        return row

    # ---- 출력 트레이 담기 -------------------------------------------
    def _add_all_current(self) -> None:
        if self._add_targets:
            self._on_add(list(self._add_targets))
