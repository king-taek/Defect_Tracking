"""히트맵 페이지.

defect 밀도 지도에서 위치를 고르면 그 자리의 defect 을 layer 별로 나란히 놓고 본다
(03-screens 3절). 원본은 최대화 모달 다이얼로그였다. 판독과 히트맵은 같은 LOT 을 다른
각도로 보는 두 화면이라 왕복이 잦은데, 모달은 그 왕복을 매번 열고 닫게 만들었다.

색상축을 하나로 줄이는 것이 이 화면 재설계의 요점이다. 원본은 파랑->코랄 2색 램프 +
네온그린 선택 + 초록/빨강 태그로 색이 네 축이었고, 어느 칸에 defect 이 많은지를 색상(hue)과
명도로 동시에 읽어야 했다. 여기서는 잉크 한 색의 농도만 밀도를 뜻하고, 선택은 링이,
예외는 태그가 맡는다.

die 가 수천 개가 되면 낱개 칸을 그리는 것 자체가 의미를 잃는다. 셀 크기에 따라 표현을
단계적으로 덜어내고(A7), 6px 미만에서는 래스터 한 장으로 떨어뜨린 뒤 드래그 영역 합산을
기본 상호작용으로 삼는다. 지도는 어떤 규모에서도 스크롤 없이 한 화면에 들어온다(게이트).
"""

from __future__ import annotations

import array
from collections import defaultdict
from typing import Any, Callable, Optional

from PySide6.QtCore import QRect, QRectF, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    PillPushButton,
    PrimaryPushButton,
    RoundMenu,
    SegmentedWidget,
    SimpleCardWidget,
    Slider,
    SmoothScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
    TitleLabel,
    ToolTipFilter,
    TogglePushButton,
    isDarkTheme,
    qconfig,
    setCustomStyleSheet,
)

from app import config, heatmap, wafermap_align
from app.clustering import Cluster, cluster_records, cross_layer_groups
from app.heatmap import HeatKey
from app.ui import theme
from app.ui.sheets.cluster_view import ClusteredThumb
from app.ui.flow_layout import FlowLayout
from app.ui.notifications import NotificationBanner

_PAGE_TITLE = "히트맵"
_PAGE_SUB = "defect 밀도 지도 · 위치를 고르면 그 자리의 layer 교차 판독을 봅니다"
_EMPTY_TITLE = "LOT 폴더를 선택하세요"
_EMPTY_BODY = (
    "LOT 을 열고 기준 layer 를 고르면 defect 밀도 지도를 그립니다. "
    "지도에서 위치를 고르면 그 자리의 사진이 layer 별로 나열됩니다."
)
_HINT_EMPTY = "지도에서 위치를 고르면 그 자리의 defect 이 여기에 나열됩니다."

_ALL_SLOTS = "전체"

# 지도 카드 폭(03-screens 3절). 지도는 이 안에서 크기를 맞춘다.
_MAP_CARD_W = 430
# 컨트롤 행 높이와 칩 높이(A14 · 02 2절 pill).
_ROW_H = 40
_CHIP_H = 26
# 한 줄에 세우는 조사 layer 칩 상한. 넘으면 나머지는 '＋n' 하나로 접는다 - 컨트롤 행이
# 두 줄이 되면 지도 높이를 그만큼 빼앗기고, 지도가 한 화면에 들어오는 게이트가 위태로워진다.
_MAX_CHIPS = 6
# 판독 목록 사진 크기(100% 기준). 슬라이더 기본 30% 가 원본 고정 크기와 같다.
_THUMB_PX = 500
_MONO = ("Cascadia Mono", "Consolas", "Menlo", "monospace")
# 선택 칸이 이보다 많으면 링을 낱개로 그리지 않고 테두리 사각 하나로 묶는다.
# 4,096 die 를 통째로 드래그하면 링만 4,096개가 되어 paint 예산을 혼자 다 쓴다.
_RING_BULK_LIMIT = 256


def _font(px: float, *, bold: bool = False, mono: bool = False) -> QFont:
    """글자 크기를 QFont 로 지정한다(스타일시트 font-size 는 QFont 에 남지 않는다)."""
    f = QFont()
    if mono:
        f.setFamilies(list(_MONO))
    f.setPixelSize(max(1, int(round(px))))
    f.setWeight(QFont.DemiBold if bold else QFont.Normal)
    return f


def _num(value: int) -> str:
    """수치는 천단위 구분 + 단위를 붙여 쓴다(02 2절)."""
    return f"{value:,}"


class _InkRamp:
    """단일 잉크 램프 - accentFill 알파 0.12 -> 1.0 을 카드 면과 합성해 불투명색으로.

    칸마다 문자열을 다시 파싱하면 4,096 die 에서 paint 예산을 넘긴다. 개수는 작은 정수라
    값별로 한 번만 만들어 두고 재사용한다.
    """

    def __init__(self, tokens: dict[str, str], max_count: int) -> None:
        self._card = tokens["card"]
        r, g, b, _a = theme.parse_rgba(tokens["accentFill"])
        self._rgb = (int(r), int(g), int(b))
        self._max = max(1, int(max_count))
        self._empty = QColor(theme.flatten(tokens["subtle"], self._card))
        self._cache: dict[int, QColor] = {}

    @property
    def empty(self) -> QColor:
        return self._empty

    def color(self, count: int) -> QColor:
        if count <= 0:
            return self._empty
        hit = self._cache.get(count)
        if hit is None:
            alpha = heatmap.ramp_alpha(count, self._max)
            r, g, b = self._rgb
            hit = QColor(theme.flatten(f"rgba({r},{g},{b},{alpha})", self._card))
            self._cache[count] = hit
        return hit


class _LayerChip(PillPushButton):
    """조사 layer 칩. 켜짐을 accent 채움이 아니라 틴트로 그린다.

    Fluent 기본 pill 은 켜지면 accent 로 꽉 찬다. 칩 여섯 개가 다 차면 화면의 강조를 칩이
    가져가고 주요 액션(이 위치 담기)이 묻힌다. 강조는 한 화면에 하나다(02 4절).
    배경을 QSS 가 아니라 paintEvent 로 그리는 위젯이라 색도 paintEvent 에서 바꾼다.
    """

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setFixedHeight(_CHIP_H)
        self.setFont(_font(theme.TYPO["captionSm"]["size"]))
        self._apply_text_color()
        qconfig.themeChanged.connect(self._apply_text_color)

    def _apply_text_color(self, *_args) -> None:
        # 채움을 틴트로 바꿨으므로 켜짐 글자색도 onAccent 가 아니라 accentText 여야 읽힌다.
        rule = "PillPushButton:checked {{ color: {0}; background: transparent; }}"
        setCustomStyleSheet(
            self,
            rule.format(theme.fluent_tokens(False)["accentText"]),
            rule.format(theme.fluent_tokens(True)["accentText"]),
        )

    def paintEvent(self, e):  # noqa: N802 - Qt 규약
        tok = theme.fluent_tokens(isDarkTheme())
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.isChecked():
            bg = QColor(theme.flatten(tok["accentTint"], tok["layer"]))
            border = QColor(tok["accentFill"])
        else:
            bg = QColor(theme.flatten(tok["subtle"], tok["layer"]))
            border = QColor(theme.flatten(tok["ctrlBd"], tok["layer"]))
        painter.setPen(QPen(border, 1))
        painter.setBrush(bg)
        radius = rect.height() / 2
        painter.drawRoundedRect(rect, radius, radius)
        painter.end()
        TogglePushButton.paintEvent(self, e)


class _LegendBar(QWidget):
    """0 -> 최대 그라디언트 바. 램프가 무엇을 뜻하는지 지도 옆에 늘 붙여 둔다."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, event):  # noqa: N802 - Qt 규약
        tokens = theme.fluent_tokens(isDarkTheme())
        ramp = _InkRamp(tokens, 9)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, ramp.color(1))
        grad.setColorAt(1.0, ramp.color(9))
        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        painter.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 3, 3)
        painter.end()


class DensityMapView(QWidget):
    """defect 밀도 지도. 셀 크기에 따라 표현 단계를 자동으로 고른다(A7).

    row 0 을 화면 맨 아래에 그린다(웨이퍼 좌표계: 왼쪽아래 0,0). 드래그 사각 선택은 모드와
    무관하게 항상 가능하고, 여러 다이 선택 모드는 '클릭 = 누적 토글'만 좌우한다.
    """

    selection_changed = Signal(object)   # list[HeatKey]
    region_summed = Signal(int, int)     # (die 수, defect 합) - 드래그 중 실시간
    die_activated = Signal(int, int)     # (col, row) - 더블클릭. 판독 화면으로 점프

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("heatmapDensityMap")
        self._cols = 0
        self._rows = 0
        self._origin = (0, 0)
        self._valid: Optional[frozenset] = None
        self._data_subdivide = False
        self._density: dict[HeatKey, int] = {}
        self._die_counts: dict[tuple[int, int], int] = {}
        self._grid = heatmap.DensityGrid({}, 0, 0)
        self._max_sub = 1
        self._max_die = 1
        self._selected: set[HeatKey] = set()
        self._multi = False
        self._rubber_origin = None
        self._rubber_cur = None
        self._dragging = False
        self._geom_cache: Optional[tuple] = None
        self._raster_cache: Optional[tuple[QSize, QPixmap]] = None
        self.setMinimumSize(160, 160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setToolTip(
            "색이 진할수록 defect 이 많습니다. 클릭으로 한 칸, 드래그로 영역을 고릅니다."
        )
        self.installEventFilter(ToolTipFilter(self, theme.TOOLTIP_DELAY_MS))
        qconfig.themeChanged.connect(self._on_theme_changed)

    # ------------------------------------------------------------ 데이터
    def set_data(
        self,
        cols: int,
        rows: int,
        valid: Optional[frozenset],
        subdivide: bool,
        density: dict[HeatKey, int],
        origin: tuple[int, int] = (0, 0),
    ) -> None:
        self._cols = max(0, int(cols))
        self._rows = max(0, int(rows))
        self._valid = frozenset(valid) if valid else None
        self._data_subdivide = bool(subdivide)
        self._density = dict(density)
        self._die_counts = heatmap.die_counts(self._density)
        self._origin = (int(origin[0]), int(origin[1]))
        self._grid = heatmap.DensityGrid(
            self._die_counts, self._cols, self._rows, self._origin
        )
        self._max_sub = max(self._density.values(), default=1)
        self._max_die = max(self._die_counts.values(), default=1)
        self._selected = set()
        self._rubber_origin = None
        self._rubber_cur = None
        self._dragging = False
        self._invalidate()
        self.update()

    def clear(self) -> None:
        self.set_data(0, 0, None, False, {})

    def set_multi(self, on: bool) -> None:
        """여러 다이 선택 모드. 드래그 사각 선택은 이 값과 무관하게 늘 동작한다."""
        self._multi = bool(on)
        self._selected = set()
        self._rubber_origin = None
        self._rubber_cur = None
        self.update()
        self.selection_changed.emit([])

    def set_selection(self, keys) -> None:
        """바깥(판독 화면 die 점프 등)에서 선택을 지정한다."""
        self._selected = {k for k in keys if self._known(k)}
        self.update()
        self._emit_selection()

    def selected_keys(self) -> list[HeatKey]:
        return self._sorted_selection()

    @property
    def grid(self) -> heatmap.DensityGrid:
        """die 격자 누적합. 영역 합산을 O(1) 로 하는 근거다."""
        return self._grid

    @property
    def total(self) -> int:
        return self._grid.total

    def max_count(self) -> int:
        """현재 표현 단계에서 램프 상한이 되는 개수."""
        return self._max_sub if self._subdivided() else self._max_die

    # ------------------------------------------------------------ 배치
    def _invalidate(self) -> None:
        self._geom_cache = None
        self._raster_cache = None

    def resizeEvent(self, event):  # noqa: N802 - Qt 규약
        self._invalidate()
        super().resizeEvent(event)

    def _geom(self) -> tuple[float, int, heatmap.LodPlan, float, float]:
        """(die 한 변, 간격, LodPlan, x0, y0). 위젯 크기에서 역산하므로 늘 한 화면이다."""
        if self._geom_cache is not None:
            return self._geom_cache
        cell, gap, plan = heatmap.layout_for(
            self._cols, self._rows, self.width(), self.height()
        )
        if plan.mode != heatmap.MODE_RASTER:
            # 벡터로 그리는 동안은 정수 픽셀에 맞춘다(반 픽셀 경계가 칸마다 어긋나 보인다).
            cell = float(int(cell))
            if plan.subdivide and self._data_subdivide:
                cell = float(int(cell) // heatmap.SUB_COLS * heatmap.SUB_COLS)
        grid_w = self._cols * (cell + gap) + gap if self._cols else 0.0
        grid_h = self._rows * (cell + gap) + gap if self._rows else 0.0
        x0 = (self.width() - grid_w) / 2.0
        y0 = (self.height() - grid_h) / 2.0
        self._geom_cache = (cell, gap, plan, x0, y0)
        return self._geom_cache

    def plan(self) -> heatmap.LodPlan:
        return self._geom()[2]

    def cell_px(self) -> float:
        return self._geom()[0]

    def content_rect(self) -> QRect:
        """실제로 그려지는 격자 사각. 컨테이너 안에 들어가는지 검사하는 근거다."""
        cell, gap, _plan, x0, y0 = self._geom()
        grid_w = self._cols * (cell + gap) + gap if self._cols else 0.0
        grid_h = self._rows * (cell + gap) + gap if self._rows else 0.0
        return QRectF(x0, y0, grid_w, grid_h).toAlignedRect()

    def _subdivided(self) -> bool:
        """die 안 5x5 하위셀까지 그리는가. 데이터(die 50개 미만)와 셀 크기 둘 다 만족해야 한다."""
        return bool(self._data_subdivide and self._geom()[2].subdivide)

    def _die_rect(self, col: int, row: int) -> QRectF:
        cell, gap, _plan, x0, y0 = self._geom()
        dc = col - self._origin[0]
        # row 0 이 화면 맨 아래다(웨이퍼 좌표계). 하위셀은 die 안에서 위->아래를 유지한다.
        dr = (self._rows - 1) - (row - self._origin[1])
        return QRectF(
            x0 + gap + dc * (cell + gap), y0 + gap + dr * (cell + gap), cell, cell
        )

    def key_rect(self, key: HeatKey) -> QRectF:
        rect = self._die_rect(key.col, key.row)
        if self._subdivided() and key.subdivided:
            sw = rect.width() / heatmap.SUB_COLS
            sh = rect.height() / heatmap.SUB_ROWS
            return QRectF(
                rect.x() + key.sub_col * sw, rect.y() + key.sub_row * sh, sw, sh
            )
        return rect

    def _known(self, key: HeatKey) -> bool:
        if key in self._density:
            return True
        return not key.subdivided and (key.col, key.row) in self._die_counts

    # ------------------------------------------------------------ 그리기
    def _on_theme_changed(self, *_args) -> None:
        self._raster_cache = None
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt 규약
        if self._cols <= 0 or self._rows <= 0:
            return
        tokens = theme.fluent_tokens(isDarkTheme())
        cell, gap, plan, _x0, _y0 = self._geom()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        if plan.mode == heatmap.MODE_RASTER:
            self._paint_raster(painter, tokens)
        else:
            self._paint_cells(painter, tokens, cell, gap, plan)
        self._paint_selection(painter, tokens)
        painter.end()

    def _paint_cells(self, painter, tokens, cell, gap, plan) -> None:
        """칸을 색깔별로 묶어 한 번에 그린다.

        칸마다 fillRect 를 부르면 1,024 die 에서 그리기 호출 수가 그대로 프레임 시간이 된다.
        같은 개수(=같은 색)끼리 모아 색당 한 번만 넘기면 호출이 색 가짓수로 줄어든다.
        """
        ramp = _InkRamp(tokens, self.max_count())
        subdivided = self._subdivided()
        by_count: dict[int, list[QRect]] = {}
        borders: list[QRect] = []
        for dr in range(self._rows):
            row = dr + self._origin[1]
            for dc in range(self._cols):
                col = dc + self._origin[0]
                if self._valid is not None and (col, row) not in self._valid:
                    continue
                rect = self._die_rect(col, row).toAlignedRect()
                if subdivided:
                    self._collect_subcells(by_count, col, row, rect)
                else:
                    by_count.setdefault(
                        self._die_counts.get((col, row), 0), []
                    ).append(rect)
                if plan.border:
                    borders.append(rect.adjusted(0, 0, -1, -1))
        painter.setPen(Qt.NoPen)
        for count, rects in by_count.items():
            painter.setBrush(ramp.color(count))
            painter.drawRects(rects)
        if borders:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(
                QPen(QColor(theme.flatten(tokens["cardBorder"], tokens["card"])), 1)
            )
            painter.drawRects(borders)

    def _collect_subcells(self, by_count: dict, col: int, row: int, rect: QRect) -> None:
        sw = rect.width() // heatmap.SUB_COLS
        sh = rect.height() // heatmap.SUB_ROWS
        for sr in range(heatmap.SUB_ROWS):
            for sc in range(heatmap.SUB_COLS):
                count = self._density.get(HeatKey(col, row, sc, sr), 0)
                by_count.setdefault(count, []).append(
                    QRect(rect.x() + sc * sw, rect.y() + sr * sh, sw, sh)
                )

    def _paint_raster(self, painter, tokens) -> None:
        rect = self.content_rect()
        cached = self._raster_cache
        if cached is None or cached[0] != rect.size():
            self._raster_cache = (rect.size(), self._build_raster(tokens, rect.size()))
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        painter.drawPixmap(rect.topLeft(), self._raster_cache[1])

    def _build_raster(self, tokens: dict[str, str], size: QSize) -> QPixmap:
        """die 한 개 = 픽셀 한 개인 QImage 를 채우고 한 번에 확대한다.

        수천 칸을 낱개 사각으로 그리면 그리기 호출 수가 그대로 프레임 시간이 된다. 픽셀
        버퍼를 통째로 만들어 한 장으로 올리면 die 수와 무관하게 draw 는 한 번이다.
        """
        ramp = _InkRamp(tokens, self._max_die)
        card = QColor(tokens["card"])

        def rgb(color: QColor) -> int:
            return 0xFF000000 | (color.red() << 16) | (color.green() << 8) | color.blue()

        cols, rows = self._cols, self._rows
        empty = rgb(ramp.empty)
        oc, orr = self._origin
        if self._valid is None:
            buf = array.array("I", [empty]) * (cols * rows)
        else:
            # 디바이스 모양 밖은 카드 면 그대로 둔다(웨이퍼 윤곽이 보이게).
            buf = array.array("I", [rgb(card)]) * (cols * rows)
            for col, row in self._valid:
                x = col - oc
                y = (rows - 1) - (row - orr)
                if 0 <= x < cols and 0 <= y < rows:
                    buf[y * cols + x] = empty
        for (col, row), count in self._die_counts.items():
            x = col - oc
            y = (rows - 1) - (row - orr)
            if 0 <= x < cols and 0 <= y < rows:
                buf[y * cols + x] = rgb(ramp.color(count))
        data = buf.tobytes()
        image = QImage(data, cols, rows, cols * 4, QImage.Format_RGB32)
        scaled = image.scaled(
            size.width(), size.height(), Qt.IgnoreAspectRatio, Qt.FastTransformation
        )
        return QPixmap.fromImage(scaled)

    def _ring_pens(self, tokens: dict[str, str], dashed: bool) -> tuple[QPen, QPen]:
        """이중선 링(REVIEW-03 A22). theme.SELECTION_RING 의 두 색을 그대로 읽는다.

        단색 링은 램프 최고 채움과 같은 색이라 가장 진한 칸에서 사라진다. 바깥은 연한 칸,
        안쪽은 진한 칸에서 각각 대비를 담당하므로 램프 어디에서도 한 겹은 반드시 보인다.
        """
        spec = theme.SELECTION_RING
        outer = QColor(theme.flatten(tokens[spec["outer"]], tokens["card"]))
        inner = QColor(theme.flatten(tokens[spec["inner"]], tokens["card"]))
        style = Qt.DashLine if dashed else Qt.SolidLine
        return QPen(outer, 1, style), QPen(inner, 1, style)

    def _draw_rings(self, painter, rects: list[QRect], tokens, dashed: bool = False) -> None:
        """링도 겹별로 묶어 두 번에 그린다(칸 채움과 같은 이유)."""
        if not rects:
            return
        outer_pen, inner_pen = self._ring_pens(tokens, dashed)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(outer_pen)
        painter.drawRects([r.adjusted(0, 0, -1, -1) for r in rects])
        painter.setPen(inner_pen)
        painter.drawRects([r.adjusted(1, 1, -2, -2) for r in rects])

    def _paint_selection(self, painter, tokens) -> None:
        keys = [k for k in self._selected if self._known(k)]
        if keys:
            if len(keys) > _RING_BULK_LIMIT:
                # 영역 하나를 통째로 고른 것이므로 낱개 윤곽보다 테두리 하나가 읽기 쉽다.
                # 사각을 수천 개 만들어 합치면 그리기보다 계산이 더 든다. 양 끝 die 두 개로
                # 경계를 잡는다(row 0 이 아래라 세로는 뒤집어 짝을 짓는다).
                cols = [k.col for k in keys]
                rows = [k.row for k in keys]
                rects = [
                    self._die_rect(min(cols), max(rows)).toAlignedRect().united(
                        self._die_rect(max(cols), min(rows)).toAlignedRect()
                    )
                ]
            else:
                rects = [self.key_rect(k).toAlignedRect() for k in keys]
            self._draw_rings(painter, rects, tokens)
        if self._rubber_origin is not None and self._rubber_cur is not None and self._dragging:
            band = QRect(self._rubber_origin, self._rubber_cur).normalized()
            self._draw_rings(painter, [band], tokens, dashed=True)

    # ------------------------------------------------------------ 상호작용
    def _key_at(self, pos) -> Optional[HeatKey]:
        cell, gap, _plan, x0, y0 = self._geom()
        step = cell + gap
        if step <= 0:
            return None
        dc = int((pos.x() - x0 - gap) // step)
        dr = int((pos.y() - y0 - gap) // step)
        if not (0 <= dc < self._cols and 0 <= dr < self._rows):
            return None
        col = dc + self._origin[0]
        # row 0 이 화면 맨 아래이므로(_die_rect 와 대칭) 세로 인덱스를 반전 복원한다.
        row = self._origin[1] + (self._rows - 1 - dr)
        if self._subdivided():
            rect = self._die_rect(col, row)
            sw = rect.width() / heatmap.SUB_COLS
            sh = rect.height() / heatmap.SUB_ROWS
            sc = min(heatmap.SUB_COLS - 1, max(0, int((pos.x() - rect.x()) // sw)))
            sr = min(heatmap.SUB_ROWS - 1, max(0, int((pos.y() - rect.y()) // sh)))
            key = HeatKey(col, row, sc, sr)
            return key if self._density.get(key, 0) > 0 else None
        key = HeatKey(col, row)
        return key if self._die_counts.get((col, row), 0) > 0 else None

    def _die_span(self, rect: QRect) -> Optional[tuple[int, int, int, int]]:
        """픽셀 사각을 실 die 좌표 범위(col0,row0,col1,row1)로. 누적합 조회용."""
        cell, gap, _plan, x0, y0 = self._geom()
        step = cell + gap
        if step <= 0 or self._cols <= 0 or self._rows <= 0:
            return None
        dc0 = int((rect.left() - x0 - gap) // step)
        dc1 = int((rect.right() - x0 - gap) // step)
        dr0 = int((rect.top() - y0 - gap) // step)
        dr1 = int((rect.bottom() - y0 - gap) // step)
        dc0 = max(0, dc0)
        dr0 = max(0, dr0)
        dc1 = min(self._cols - 1, dc1)
        dr1 = min(self._rows - 1, dr1)
        if dc0 > dc1 or dr0 > dr1:
            return None
        col0 = dc0 + self._origin[0]
        col1 = dc1 + self._origin[0]
        row0 = self._origin[1] + (self._rows - 1 - dr1)
        row1 = self._origin[1] + (self._rows - 1 - dr0)
        return col0, row0, col1, row1

    def region_sum(self, rect: QRect) -> tuple[int, int]:
        """드래그 사각 안의 (die 수, defect 합). 누적합이라 영역 크기와 무관하게 O(1)."""
        span = self._die_span(rect)
        if span is None:
            return 0, 0
        col0, row0, col1, row1 = span
        dies = (col1 - col0 + 1) * (row1 - row0 + 1)
        return dies, self._grid.region_sum(col0, row0, col1, row1)

    def _keys_in_rect(self, rect: QRect) -> set[HeatKey]:
        span = self._die_span(rect)
        if span is None:
            return set()
        col0, row0, col1, row1 = span
        out: set[HeatKey] = set()
        if self._subdivided():
            for key, count in self._density.items():
                if count > 0 and col0 <= key.col <= col1 and row0 <= key.row <= row1:
                    if self.key_rect(key).toAlignedRect().intersects(rect):
                        out.add(key)
            return out
        for row in range(row0, row1 + 1):
            for col in range(col0, col1 + 1):
                if self._die_counts.get((col, row), 0) > 0:
                    out.add(HeatKey(col, row))
        return out

    def _sorted_selection(self) -> list[HeatKey]:
        return sorted(
            self._selected, key=lambda k: (k.row, k.col, k.sub_row, k.sub_col)
        )

    def _emit_selection(self) -> None:
        self.selection_changed.emit(self._sorted_selection())

    def mousePressEvent(self, event):  # noqa: N802 - Qt 규약
        if event.button() != Qt.LeftButton:
            return
        pos = event.position().toPoint()
        self._rubber_origin = pos
        self._rubber_cur = pos
        self._dragging = False

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt 규약
        if self._rubber_origin is None:
            return
        pos = event.position().toPoint()
        if (pos - self._rubber_origin).manhattanLength() > 4:
            self._dragging = True
        self._rubber_cur = pos
        if self._dragging:
            band = QRect(self._rubber_origin, self._rubber_cur).normalized()
            dies, total = self.region_sum(band)
            self.region_summed.emit(dies, total)
            self.update()

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt 규약
        if event.button() != Qt.LeftButton or self._rubber_origin is None:
            return
        origin = self._rubber_origin
        cur = self._rubber_cur or origin
        if self._dragging:
            keys = self._keys_in_rect(QRect(origin, cur).normalized())
            self._selected = (self._selected | keys) if self._multi else keys
        else:
            key = self._key_at(origin)
            if self._multi:
                if key is not None:
                    if key in self._selected:
                        self._selected.discard(key)
                    else:
                        self._selected.add(key)
            else:
                self._selected = {key} if key is not None else set()
        self._rubber_origin = None
        self._rubber_cur = None
        self._dragging = False
        self.update()
        self._emit_selection()

    def mouseDoubleClickEvent(self, event):  # noqa: N802 - Qt 규약
        """더블클릭 = 그 die 의 사진으로 간다. wafer_map 이 하던 점프를 여기서 잇는다(A12)."""
        if event.button() != Qt.LeftButton:
            return
        key = self._key_at(event.position().toPoint())
        if key is not None:
            self.die_activated.emit(key.col, key.row)


class HeatmapPage(QWidget):
    """히트맵 라우트. 창이 set_data 로 데이터를 넘기면 그때 지도를 그린다."""

    die_activated = Signal(int, int)   # (col, row). 창이 판독 화면 점프에 쓴다.

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # objectName 은 라우트 키다. 비면 ValueError, 겹치면 라우팅이 깨진다.
        self.setObjectName("heatmapInterface")

        self.matches: list[Any] = []
        self._base_layer = ""
        self._thumb_cache: Any = None
        self._on_add: Optional[Callable[[list[int]], None]] = None
        self._settings: Any = None
        self._records_by_layer: dict[str, list] = {}
        self._tolerance = config.DEFAULT_TOLERANCE
        self._cluster_radius = config.DEFAULT_CLUSTER_RADIUS
        self._current_slot = _ALL_SLOTS
        self._layer_on: dict[str, bool] = {}
        self._groups: dict[HeatKey, list[int]] = {}
        self._die_groups: dict[tuple[int, int], list[int]] = {}
        self._selected_keys: list[HeatKey] = []
        self._add_targets: list[int] = []
        self._pending_thumbs: list = []
        self._thumb_token = 0
        self._active_thumb_workers: set = set()
        self._notice: Optional[NotificationBanner] = None
        self._align_cache: dict = {}
        self._xr = (0.0, 1.0)
        self._yr = (0.0, 1.0)
        self._subdivide = False
        self._map_caption = ""
        self._thumb_percent = 30
        self._thumb_px = int(_THUMB_PX * self._thumb_percent / 100)
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.setInterval(300)
        self._thumb_timer.timeout.connect(self._rebuild_detail)

        self._build()
        qconfig.themeChanged.connect(self._apply_tokens)
        self._apply_tokens()

    # ------------------------------------------------------------ 구성
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.stack = QStackedWidget(self)
        outer.addWidget(self.stack)

        self.empty_state = self._build_empty_state()
        self.content = QWidget(self)
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.content)

        main = QVBoxLayout(self.content)
        main.setContentsMargins(
            theme.SPACING["pageH"], theme.SPACING["pageV"], theme.SPACING["pageH"], 0
        )
        main.setSpacing(theme.SPACING["gapM"])
        main.addLayout(self._build_header())
        main.addWidget(self._build_control_row())
        main.addLayout(self._build_body(), 1)
        self.show_empty_state(True)

    def _build_empty_state(self) -> QWidget:
        host = QWidget(self)
        host.setObjectName("heatmapEmptyState")
        outer = QVBoxLayout(host)
        outer.setAlignment(Qt.AlignCenter)
        outer.setSpacing(0)
        box = QWidget(host)
        box.setMaximumWidth(460)
        col = QVBoxLayout(box)
        col.setAlignment(Qt.AlignHCenter)
        col.setSpacing(0)
        title = SubtitleLabel(_EMPTY_TITLE, box)
        title.setAlignment(Qt.AlignCenter)
        col.addWidget(title)
        col.addSpacing(theme.SPACING["gapS"])
        body = BodyLabel(_EMPTY_BODY, box)
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignCenter)
        col.addWidget(body)
        outer.addWidget(box)
        return host

    def _build_header(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACING["gapS"])
        row.addWidget(TitleLabel(_PAGE_TITLE, self.content))
        row.addStretch(1)
        col.addLayout(row)
        self.lbl_sub = CaptionLabel(_PAGE_SUB, self.content)
        self.lbl_sub.setObjectName("dim")
        col.addWidget(self.lbl_sub)
        return col

    def _build_control_row(self) -> QWidget:
        row = QWidget(self.content)
        row.setFixedHeight(_ROW_H)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.SPACING["gapXs"])

        # 슬롯 레일. 원본은 wafer 드롭다운이라 지금 무엇을 보는 중인지 접혀 있었다.
        self.slots = SegmentedWidget(row)
        self.slots.addItem(_ALL_SLOTS, _ALL_SLOTS, lambda: self._on_slot(_ALL_SLOTS))
        self.slots.setCurrentItem(_ALL_SLOTS)
        lay.addWidget(self.slots, 0)

        self._divider = QFrame(row)
        self._divider.setObjectName("heatmapDivider")
        self._divider.setFixedSize(1, 20)
        lay.addSpacing(theme.SPACING["gapXs"])
        lay.addWidget(self._divider, 0)
        lay.addSpacing(theme.SPACING["gapXs"])

        self.lbl_chip_head = CaptionLabel("조사 layer", row)
        self.lbl_chip_head.setObjectName("dim")
        lay.addWidget(self.lbl_chip_head, 0)

        self._chip_host = QWidget(row)
        self._chip_lay = QHBoxLayout(self._chip_host)
        self._chip_lay.setContentsMargins(0, 0, 0, 0)
        self._chip_lay.setSpacing(theme.SPACING["gapXs"])
        lay.addWidget(self._chip_host, 0)
        self._chips: dict[str, _LayerChip] = {}
        self._chip_more: Optional[_LayerChip] = None

        lay.addStretch(1)
        self.lbl_total = CaptionLabel("", row)
        self.lbl_total.setObjectName("dim")
        self.lbl_total.setFont(_font(theme.TYPO["caption"]["size"], mono=True))
        lay.addWidget(self.lbl_total, 0)
        return row

    def _build_body(self) -> QHBoxLayout:
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, theme.SPACING["pageV"])
        body.setSpacing(theme.SPACING["gapL"])
        body.addWidget(self._build_map_card(), 0)
        body.addWidget(self._build_read_card(), 1)
        return body

    def _build_map_card(self) -> QWidget:
        card = SimpleCardWidget(self.content)
        card.setObjectName("heatmapMapCard")
        card.setFixedWidth(_MAP_CARD_W)
        lay = QVBoxLayout(card)
        pad = theme.SPACING["cardMax"]
        lay.setContentsMargins(pad, pad, pad, pad)
        lay.setSpacing(theme.SPACING["gapS"])

        self.lbl_map_title = StrongBodyLabel(f"밀도 지도 · SLOT {_ALL_SLOTS}", card)
        lay.addWidget(self.lbl_map_title)

        self.map = DensityMapView(card)
        self.map.selection_changed.connect(self._on_selection_changed)
        self.map.region_summed.connect(self._on_region_summed)
        self.map.die_activated.connect(self.die_activated)
        lay.addWidget(self.map, 1)

        legend = QHBoxLayout()
        legend.setContentsMargins(0, 0, 0, 0)
        legend.setSpacing(theme.SPACING["gapS"])
        self.lbl_legend_lo = CaptionLabel("0", card)
        self.lbl_legend_lo.setFont(_font(theme.TYPO["label"]["size"], mono=True))
        legend.addWidget(self.lbl_legend_lo, 0)
        legend.addWidget(_LegendBar(card), 1)
        self.lbl_legend_hi = CaptionLabel("최대 9", card)
        self.lbl_legend_hi.setFont(_font(theme.TYPO["label"]["size"], mono=True))
        legend.addWidget(self.lbl_legend_hi, 0)
        lay.addLayout(legend)

        self.lbl_map_caption = CaptionLabel("", card)
        self.lbl_map_caption.setObjectName("dim")
        self.lbl_map_caption.setWordWrap(True)
        lay.addWidget(self.lbl_map_caption)

        self.chk_multi = _LayerChip("여러 다이 선택", card)
        self.chk_multi.setToolTip(
            "켜면 클릭이 여러 die 를 누적 토글합니다. 드래그 사각 선택은 항상 됩니다."
        )
        self.chk_multi.installEventFilter(ToolTipFilter(self.chk_multi, theme.TOOLTIP_DELAY_MS))
        self.chk_multi.toggled.connect(self._on_multi_toggled)
        multi_row = QHBoxLayout()
        multi_row.setContentsMargins(0, 0, 0, 0)
        multi_row.addWidget(self.chk_multi, 0)
        multi_row.addStretch(1)
        lay.addLayout(multi_row)
        return card

    def _build_read_card(self) -> QWidget:
        card = SimpleCardWidget(self.content)
        card.setObjectName("heatmapReadCard")
        lay = QVBoxLayout(card)
        pad = theme.SPACING["cardMax"]
        lay.setContentsMargins(pad, pad, pad, pad)
        lay.setSpacing(theme.SPACING["gapM"])

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(theme.SPACING["gapS"])
        self.lbl_read_title = StrongBodyLabel("선택 위치 판독", card)
        head.addWidget(self.lbl_read_title, 1)

        self.lbl_thumb = CaptionLabel("사진 크기", card)
        self.lbl_thumb.setObjectName("dim")
        head.addWidget(self.lbl_thumb, 0)
        self.sld_thumb = Slider(Qt.Horizontal, card)
        self.sld_thumb.setRange(10, 100)
        self.sld_thumb.setValue(self._thumb_percent)
        self.sld_thumb.setFixedWidth(110)
        self.sld_thumb.setToolTip("판독 목록 사진 크기를 조절합니다.")
        self.sld_thumb.valueChanged.connect(self._on_thumb_size)
        head.addWidget(self.sld_thumb, 0)
        self.lbl_thumb_pct = CaptionLabel(f"{self._thumb_percent}%", card)
        self.lbl_thumb_pct.setObjectName("dim")
        self.lbl_thumb_pct.setFont(_font(theme.TYPO["caption"]["size"], mono=True))
        self.lbl_thumb_pct.setFixedWidth(38)
        head.addWidget(self.lbl_thumb_pct, 0)

        self.btn_add = PrimaryPushButton("이 위치 담기", card)
        self.btn_add.setMinimumHeight(theme.fluent_height("control"))
        self.btn_add.setToolTip("고른 위치에서 기준 layer 와 매칭된 사진을 출력 명세에 담습니다.")
        self.btn_add.clicked.connect(self._add_current)
        self.btn_add.setEnabled(False)
        head.addWidget(self.btn_add, 0)
        lay.addLayout(head)

        self.scroll = SmoothScrollArea(card)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        # 가로 스크롤은 두지 않는다. 사진은 줄바꿈으로 흐르고 세로로만 훑는다.
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.viewport().setStyleSheet("background: transparent;")
        host = QWidget(self.scroll)
        host.setObjectName("heatmapReadHost")
        self._rows = QVBoxLayout(host)
        self._rows.setContentsMargins(0, 0, theme.SPACING["gapM"], 0)
        self._rows.setSpacing(0)
        self._rows.addStretch(1)
        self.scroll.setWidget(host)
        self._read_host = host
        lay.addWidget(self.scroll, 1)

        # 안내와 목록은 한 번에 하나만 보인다. 둘을 같이 세우면 빈 카드에서 안내가 바닥에
        # 눌려 붙어 어디를 봐야 할지 알 수 없다.
        self.lbl_hint = BodyLabel(_HINT_EMPTY, card)
        self.lbl_hint.setObjectName("dim")
        self.lbl_hint.setAlignment(Qt.AlignCenter)
        self.lbl_hint.setWordWrap(True)
        lay.addWidget(self.lbl_hint, 1)
        self._show_hint(True)
        return card

    def _show_hint(self, on: bool, text: str = "") -> None:
        if text:
            self.lbl_hint.setText(text)
        self.lbl_hint.setVisible(on)
        self.scroll.setVisible(not on)

    def _apply_tokens(self, *_args) -> None:
        """순수 Qt 위젯(구분선·스크롤 면)만 토큰으로 칠한다. Fluent 위젯은 스스로 칠한다."""
        tok = theme.fluent_tokens(isDarkTheme())
        self._divider.setStyleSheet(
            f"QFrame#heatmapDivider {{ background: {tok['divider']}; border: none; }}"
        )
        self._read_host.setStyleSheet(
            "QWidget#heatmapReadHost { background: transparent; }"
        )
        self.scroll.viewport().setStyleSheet("background: transparent;")

    # ------------------------------------------------------------ 데이터
    def set_data(
        self,
        matches: Optional[list] = None,
        base_layer: str = "",
        compare_layers: Optional[list[str]] = None,
        thumb_cache: Any = None,
        on_add_to_export: Optional[Callable[[list[int]], None]] = None,
        settings: Any = None,
        current_wafer: Optional[str] = None,
        records_by_layer: Optional[dict] = None,
        select_die: Optional[tuple[int, int]] = None,
    ) -> None:
        """창이 가진 것을 그대로 받는다(옛 HeatmapDialog 생성자와 같은 것들).

        select_die 는 판독 화면에서 넘어올 때 미리 골라 둘 die 다(A12 die 점프).
        current_wafer 는 받기만 하고 쓰지 않는다. 이 화면은 늘 전체 슬롯으로 열어야 밀도가
        비교되기 때문이다(원본 동작 계승). 슬롯을 좁히는 것은 슬롯 레일이 한다.
        """
        self.matches = list(matches or [])
        self._base_layer = base_layer or ""
        self._thumb_cache = thumb_cache
        self._on_add = on_add_to_export
        self._settings = settings
        self._records_by_layer = records_by_layer or {}
        self._tolerance = getattr(settings, "tolerance", None) or config.DEFAULT_TOLERANCE
        self._cluster_radius = (
            getattr(settings, "cluster_radius", None) or config.DEFAULT_CLUSTER_RADIUS
        )
        self._selected_keys = []
        self._align_cache.clear()
        if not self.matches:
            self.map.clear()
            self._clear_rows()
            self.show_empty_state(True)
            return
        self.show_empty_state(False)
        self._rebuild_slots()
        self._rebuild_chips(compare_layers)
        self._refresh_map()
        if select_die is not None:
            self.select_die(*select_die)
        else:
            self._rebuild_detail()

    def show_empty_state(self, empty: bool) -> None:
        self.stack.setCurrentWidget(self.empty_state if empty else self.content)

    def is_empty_state(self) -> bool:
        return self.stack.currentWidget() is self.empty_state

    def set_enabled(self, enabled: bool) -> None:
        """LOT 이 없으면 빈 상태로 둔다(옛 LauncherPage 계약)."""
        if not enabled:
            self.show_empty_state(True)

    def select_die(self, col: int, row: int) -> None:
        """지도에서 그 die 를 고른 상태로 만든다(판독 -> 히트맵 점프)."""
        keys = [
            k for k in self._groups
            if k.col == col and k.row == row
        ] or [HeatKey(col, row)]
        self.map.set_selection(keys)

    # ---- 슬롯 · 칩 ---------------------------------------------------
    def _wafers(self) -> list[str]:
        seen: list[str] = []
        for m in self.matches:
            w = m.base.wafer_id
            if w and w not in seen:
                seen.append(w)
        return seen

    def _rebuild_slots(self) -> None:
        self.slots.clear()
        self.slots.addItem(_ALL_SLOTS, _ALL_SLOTS, lambda: self._on_slot(_ALL_SLOTS))
        for wafer in self._wafers():
            self.slots.addItem(wafer, wafer, lambda w=wafer: self._on_slot(w))
        if self._current_slot not in [_ALL_SLOTS, *self._wafers()]:
            self._current_slot = _ALL_SLOTS
        self.slots.setCurrentItem(self._current_slot)

    def _all_layers(self, compare_layers: Optional[list[str]] = None) -> list[str]:
        """조사 대상 layer - 기준 + 창이 고른 비교 layer + matches 에 남은 layer(순서 유지).

        판독 화면에서 끈 layer 까지 여기 세우지 않는다. 비교 조건은 한 곳에서 정하고, 이
        화면은 그 조건 안에서 교차 판독만 한다.
        """
        out: list[str] = []
        for layer in [self._base_layer, *(compare_layers or [])]:
            if layer and layer not in out:
                out.append(layer)
        for m in self.matches:
            for r in m.results:
                if r.compare_layer not in out:
                    out.append(r.compare_layer)
        if not out:
            out = [lyr for lyr in self._records_by_layer]
        return out

    def _rebuild_chips(self, compare_layers: Optional[list[str]]) -> None:
        layers = self._all_layers(compare_layers)
        # 기본은 전부 조사. 기준 특별취급은 없다(교차 매칭이라 기준 개념이 필요 없다).
        self._layer_on = {lyr: self._layer_on.get(lyr, True) for lyr in layers}
        while self._chip_lay.count():
            item = self._chip_lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._chips = {}
        self._chip_more = None
        for layer in layers[:_MAX_CHIPS]:
            chip = _LayerChip(layer, self._chip_host)
            chip.setChecked(self._layer_on[layer])
            chip.toggled.connect(lambda on, lyr=layer: self._on_layer_toggled(lyr, on))
            self._chips[layer] = chip
            self._chip_lay.addWidget(chip)
        rest = layers[_MAX_CHIPS:]
        if rest:
            more = _LayerChip(f"＋{len(rest)}", self._chip_host)
            more.setCheckable(False)
            more.setToolTip("나머지 layer 를 켜고 끕니다.")
            more.clicked.connect(lambda: self._show_rest_menu(rest, more))
            self._chip_more = more
            self._chip_lay.addWidget(more)

    def _show_rest_menu(self, layers: list[str], anchor: QWidget) -> None:
        menu = RoundMenu(parent=self)
        for layer in layers:
            action = QAction(layer, menu)
            action.setCheckable(True)
            action.setChecked(self._layer_on.get(layer, True))
            action.toggled.connect(lambda on, lyr=layer: self._on_layer_toggled(lyr, on))
            menu.addAction(action)
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def selected_layers(self) -> list[str]:
        """조사할(켜진) layer. 기준 특별취급 없음."""
        return [lyr for lyr, on in self._layer_on.items() if on]

    def _on_layer_toggled(self, layer: str, on: bool) -> None:
        self._layer_on[layer] = bool(on)
        chip = self._chips.get(layer)
        if chip is not None and chip.isChecked() != bool(on):
            chip.setChecked(bool(on))
        self._refresh_map(preserve_selection=True)
        self._rebuild_detail()

    def _on_slot(self, slot: str) -> None:
        self._current_slot = slot
        self._selected_keys = []
        self.lbl_map_title.setText(f"밀도 지도 · SLOT {slot}")
        self._refresh_map()
        self._rebuild_detail()

    def _on_multi_toggled(self, on: bool) -> None:
        self.map.set_multi(on)

    def _on_thumb_size(self, value: int) -> None:
        self._thumb_percent = value
        self._thumb_px = int(_THUMB_PX * value / 100)
        self.lbl_thumb_pct.setText(f"{value}%")
        if len(self._pending_thumbs) <= 20:
            self._rebuild_detail()
        else:
            # 사진이 많으면 슬라이더가 멈춘 뒤에만 다시 그린다(드래그 중 재렌더 방지).
            self._thumb_timer.start()

    # ---- 밀도 계산 ---------------------------------------------------
    def _slot_ok(self, rec) -> bool:
        return self._current_slot == _ALL_SLOTS or rec.wafer_id == self._current_slot

    def _base_entries(self) -> list[tuple[int, object]]:
        """기준 defect 전체를 (base_index, base_record) 로. 슬롯 필터 적용."""
        out: list[tuple[int, object]] = []
        for i, m in enumerate(self.matches):
            b = m.base
            if b.col is None or b.row is None or b.col < 0 or b.row < 0:
                continue
            if not self._slot_ok(b):
                continue
            out.append((i, b))
        return out

    def _map_entries(self) -> list[tuple[int, object]]:
        """지도 밀도용 - 켜진 layer 의 좌표 OK defect. 근접 중복은 클러스터 1개로 센다."""
        out: list[tuple[int, object]] = []
        k = 0
        for lyr in self.selected_layers():
            recs = [
                rec for rec in self._records_by_layer.get(lyr, [])
                if getattr(rec, "ok", False) and self._slot_ok(rec)
            ]
            for cl in cluster_records(recs, self._cluster_radius):
                out.append((k, cl.representative))
                k += 1
        return out

    def _refresh_map(self, preserve_selection: bool = False) -> None:
        keep = list(self._selected_keys) if preserve_selection else []
        entries = self._map_entries()
        observed = {
            (r.col, r.row) for _, r in entries
            if r.col is not None and r.row is not None
        }
        die_count = len(observed)
        self._subdivide = heatmap.should_subdivide(die_count)
        prod = config.active_product()
        # 하위셀은 die pitch 절대 프레임([0,pitch))으로 버킷팅한다. 그래야 layer 선택이 바뀌어도
        # 같은 defect 이 늘 같은 칸에 온다(관측 분포 상대 위치가 아니라 die 내부 실제 위치).
        self._xr = (0.0, float(prod.camtek_pitch_x))
        self._yr = (0.0, float(prod.camtek_pitch_y))

        # 웨이퍼 모양과 defect 정합을 분리한다. 모양(die_map)만 정합 이동만큼 관측 좌표계로
        # 옮기고, 밀도와 die 라벨은 관측 좌표 그대로 둔다(라벨이 실제 die 로 나오게).
        valid = None
        caption = prod.name if prod.source == "db" else ""
        if prod.die_map and observed:
            ckey = (prod.name, frozenset(observed))
            align = self._align_cache.get(ckey)
            if align is None:
                align = wafermap_align.align_observed_to_diemap(observed, prod.die_map)
                self._align_cache[ckey] = align
            valid = wafermap_align.shifted_die_map(prod.die_map, align)

        density_groups = heatmap.group_defects(entries, self._subdivide, self._xr, self._yr)
        density = {k: len(v) for k, v in density_groups.items()}
        base_groups = heatmap.group_defects(
            self._base_entries(), self._subdivide, self._xr, self._yr
        )
        self._groups = dict(base_groups)
        self._die_groups = defaultdict(list)
        for key, indices in self._groups.items():
            self._die_groups[(key.col, key.row)].extend(indices)
        self._selected_keys = [k for k in keep if k in density]

        paint_valid = (valid | observed) if valid else None
        if paint_valid is not None:
            # 그려지는 셀의 bounding box 로 정규화한다(맵이 여백에 떠 보이거나 잘리지 않게).
            min_col = min(c for c, _ in paint_valid)
            min_row = min(r for _, r in paint_valid)
            cols = max(c for c, _ in paint_valid) - min_col + 1
            rows = max(r for _, r in paint_valid) - min_row + 1
            origin = (min_col, min_row)
        else:
            max_col = max((c for c, _ in observed), default=0)
            max_row = max((r for _, r in observed), default=0)
            cols = max(prod.kla_package_x_count, max_col + 1)
            rows = max(prod.kla_package_y_count, max_row + 1)
            origin = (0, 0)
        self.map.set_data(cols, rows, paint_valid, self._subdivide, density, origin=origin)
        if self._selected_keys:
            self.map.set_selection(self._selected_keys)

        total = sum(density.values())
        self.lbl_total.setText(f"defect {_num(total)}개 · die {_num(die_count)}개")
        self.lbl_legend_hi.setText(f"최대 {_num(self.map.max_count())}")
        mode = {
            heatmap.MODE_DETAIL: "die 5x5 분할",
            heatmap.MODE_PLAIN: "die 단위",
            heatmap.MODE_RASTER: "래스터 · 드래그로 영역 합산",
        }[self.map.plan().mode]
        if self.map.plan().mode == heatmap.MODE_DETAIL and not self._subdivide:
            mode = "die 단위"
        self._map_caption = (
            f"{mode} · 칸 {int(self.map.cell_px())}px" + (f" · {caption}" if caption else "")
        )
        self.lbl_map_caption.setText(self._map_caption)

    def _on_region_summed(self, dies: int, total: int) -> None:
        """드래그 중에는 캡션 자리에 영역 합계를 띄운다.

        래스터 단계에서는 낱개 칸을 짚을 수 없으므로 이 숫자가 곧 지도를 읽는 방법이다.
        놓으면 다시 표현 단계 캡션으로 돌아간다(_on_selection_changed).
        """
        self.lbl_map_caption.setText(f"영역 Σ defect {_num(total)}개 · die {_num(dies)}개")

    # ---- 선택 -> 판독 -------------------------------------------------
    def _on_selection_changed(self, keys) -> None:
        self._selected_keys = list(keys)
        self.lbl_map_caption.setText(self._map_caption)
        self._rebuild_detail()

    def _key_for_record(self, rec) -> HeatKey:
        col, row = int(rec.col), int(rec.row)
        if self._subdivide and rec.x is not None and rec.y is not None:
            sc, sr = heatmap.subcell_of(rec.x, rec.y, self._xr, self._yr)
            return HeatKey(col, row, sc, sr)
        return HeatKey(col, row)

    def _selected_match(self, key: HeatKey) -> bool:
        """선택 키 하나가 이 record 키를 포함하는가.

        지도가 하위셀까지 그리지 않는 크기로 줄면 선택이 die 단위로 온다. 그때도 그 die 의
        하위셀 record 를 전부 집어야 판독이 비지 않는다.
        """
        for sel in self._selected_keys:
            if sel == key:
                return True
            if not sel.subdivided and sel.col == key.col and sel.row == key.row:
                return True
        return False

    def _union_indices(self) -> list[int]:
        """고른 위치의 기준 defect index 합집합(순서 유지, 중복 제거)."""
        seen: set[int] = set()
        out: list[int] = []
        for sel in self._selected_keys:
            source = (
                self._groups.get(sel, [])
                if sel.subdivided
                else self._die_groups.get((sel.col, sel.row), [])
            )
            for bi in source:
                if bi not in seen:
                    seen.add(bi)
                    out.append(bi)
        return out

    def records_at_selection(self) -> list[tuple[str, object]]:
        """고른 위치에서 켜진 layer 의 모든 defect record - (layer, record)."""
        out: list[tuple[str, object]] = []
        for lyr in self.selected_layers():
            for rec in self._records_by_layer.get(lyr, []):
                if not getattr(rec, "ok", False):
                    continue
                if not self._slot_ok(rec):
                    continue
                if rec.col is None or rec.row is None:
                    continue
                if self._selected_match(self._key_for_record(rec)):
                    out.append((lyr, rec))
        return out

    @staticmethod
    def _key_label(key: HeatKey) -> str:
        label = f"({key.col},{key.row})"
        if key.subdivided:
            label += f" · 하위셀 ({key.sub_col},{key.sub_row})"
        return label

    def _clear_rows(self) -> None:
        while self._rows.count() > 1:
            item = self._rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _rebuild_detail(self) -> None:
        self._clear_rows()
        self._pending_thumbs = []
        self._add_targets = []
        if not self._selected_keys:
            self.btn_add.setEnabled(False)
            self.lbl_read_title.setText("선택 위치 판독")
            self._show_hint(True, _HINT_EMPTY)
            return
        count = len(self._selected_keys)
        where = (
            f"die {self._key_label(self._selected_keys[0])}"
            if count == 1 else f"{_num(count)}개 위치"
        )
        by_layer: dict[str, list] = defaultdict(list)
        for lyr, rec in self.records_at_selection():
            by_layer[lyr].append(rec)
        layer_to_clusters = {
            lyr: cluster_records(recs, self._cluster_radius)
            for lyr, recs in by_layer.items()
        }
        groups = cross_layer_groups(layer_to_clusters, self._tolerance)
        matched = [g for g in groups if len(g) >= 2]
        alone = [g for g in groups if len(g) == 1]
        for group in matched:
            self._rows.insertWidget(self._rows.count() - 1, self._make_group_row(group))
        if alone:
            self._rows.insertWidget(self._rows.count() - 1, self._make_alone_row(alone))
        self.lbl_read_title.setText(f"선택 위치 판독 · {where}")
        self._show_hint(not groups, "이 위치에는 켜 둔 layer 의 defect 이 없습니다.")

        # 담기 대상 = 화면에 실제로 그린 교차 그룹 중 기준 layer 를 포함한 것.
        base_by_path = {str(m.base.image_path): i for i, m in enumerate(self.matches)}
        for group in matched:
            cluster = group.get(self._base_layer)
            if cluster is None:
                continue
            bi = base_by_path.get(str(cluster.representative.image_path))
            if bi is not None:
                self._add_targets.append(bi)
        self.btn_add.setEnabled(True)
        self._start_thumbs()

    def _row_frame(self) -> tuple[QWidget, QHBoxLayout]:
        row = QFrame(self._read_host)
        row.setObjectName("heatmapReadRow")
        tok = theme.fluent_tokens(isDarkTheme())
        row.setStyleSheet(
            f"QFrame#heatmapReadRow {{ background: transparent; border: none;"
            f" border-bottom: 1px solid {tok['divider']}; }}"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, theme.SPACING["gapM"], 0, theme.SPACING["gapM"])
        lay.setSpacing(theme.SPACING["gapM"])
        return row, lay

    def _head_column(self, rec, tag: str = "") -> QWidget:
        """행 왼쪽 96px - die 와 SLOT. 정상은 무표기, 예외(매치 없음)만 태그를 단다."""
        tok = theme.fluent_tokens(isDarkTheme())
        host = QWidget()
        host.setFixedWidth(96)
        col = QVBoxLayout(host)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        if tag:
            chip = QLabel(tag, host)
            chip.setFont(_font(theme.TYPO["captionSm"]["size"], bold=True))
            chip.setStyleSheet(
                f"color: {tok['danger']}; background: {tok['dangerBg']};"
                f" border-radius: 4px; padding: 2px 7px;"
            )
            chip.setAlignment(Qt.AlignCenter)
            col.addWidget(chip, 0, Qt.AlignLeft)
        if rec is not None:
            die = QLabel(f"die ({rec.col},{rec.row})", host)
            die.setFont(_font(theme.TYPO["captionSm"]["size"], bold=True, mono=True))
            die.setStyleSheet(f"color: {theme.flatten(tok['txt1'], tok['card'])};")
            col.addWidget(die)
            slot = QLabel(host)
            slot.setFont(_font(theme.TYPO["label"]["size"], mono=True))
            slot.setStyleSheet(f"color: {theme.flatten(tok['txt3'], tok['card'])};")
            # SLOT id 는 96px 를 넘기기 쉽다. 잘린 채로 두면 어느 슬롯인지 알 수 없으므로
            # 말줄임으로 줄이고 전체 id 는 툴팁에 둔다.
            full = f"SLOT {rec.wafer_id}"
            slot.setText(
                QFontMetrics(slot.font()).elidedText(full, Qt.ElideRight, 96)
            )
            slot.setToolTip(full)
            slot.installEventFilter(ToolTipFilter(slot, theme.TOOLTIP_DELAY_MS))
            col.addWidget(slot)
        col.addStretch(1)
        return host

    def _make_group_row(self, group: dict) -> QWidget:
        """교차 그룹 한 행. 정상이므로 태그를 달지 않는다(02 4절: 예외만 표기)."""
        row, lay = self._row_frame()
        rep = next(iter(group.values())).representative
        lay.addWidget(self._head_column(rep), 0)
        thumbs = [
            (lyr, group[lyr]) for lyr in self.selected_layers() if lyr in group
        ]
        lay.addWidget(self._thumb_flow(row, thumbs), 1)
        return row

    def _make_alone_row(self, groups: list[dict]) -> QWidget:
        """어느 layer 와도 짝이 없는 defect 들. 이 화면에서 유일한 태그다."""
        row, lay = self._row_frame()
        rep = next(iter(groups[0].values())).representative
        lay.addWidget(self._head_column(rep, tag="매치 없음"), 0)
        thumbs = []
        for group in groups:
            (layer, cluster), = group.items()
            thumbs.append((layer, cluster))
        lay.addWidget(self._thumb_flow(row, thumbs), 1)
        return row

    def _thumb_flow(self, row: QWidget, thumbs: list[tuple[str, Cluster]]) -> QWidget:
        """사진을 줄바꿈으로 흘린다. 가로로만 밀면 layer 가 많을 때 마지막 칸이 잘린다."""
        host = QWidget(row)
        flow = FlowLayout(host, margin=0, h_spacing=theme.SPACING["gapM"],
                          v_spacing=theme.SPACING["gapM"])
        for layer, cluster in thumbs:
            flow.addWidget(self._thumb(cluster, layer))
        return host

    def _thumb(self, cluster: Cluster, layer: str) -> QWidget:
        widget = ClusteredThumb(
            cluster, layer, False, self._thumb_cache, self._open_viewer,
            self._thumb_px, defer=True,
        )
        self._pending_thumbs.append(widget)
        return widget

    def _open_viewer(self, record) -> None:
        from app.ui.sheets.image_viewer import ImageViewerDialog

        ImageViewerDialog(record, self).exec()

    def _start_thumbs(self) -> None:
        """썸네일은 백그라운드로 캐시를 구운 뒤 채운다(고르는 즉시 목록이 뜨게)."""
        from app.workers import FullThumbWorker

        pending = self._pending_thumbs
        if not pending or self._thumb_cache is None:
            return
        self._thumb_token += 1
        token = self._thumb_token
        items = [(i, str(w.rep_path), w._px) for i, w in enumerate(pending)]
        worker = FullThumbWorker(self._thumb_cache, items)

        def _fill(i, t=token, snap=pending):
            if t == self._thumb_token and 0 <= i < len(snap):
                snap[i].fill()

        worker.signals.ready.connect(_fill)
        # 워커 참조를 잡아 둔다. 놓으면 GC 가 signals 를 먼저 걷어가 썸네일이 로딩에 멈춘다.
        self._active_thumb_workers.add(worker)
        worker.signals.done.connect(
            lambda w=worker: self._active_thumb_workers.discard(w)
        )
        QThreadPool.globalInstance().start(worker)

    def _add_current(self) -> None:
        if self._on_add is None:
            return
        if self._add_targets:
            self._on_add(list(self._add_targets))
            return
        # 버튼을 비활성으로 두면 왜 안 되는지 알 수 없다. 눌러 보고 사유를 알려 준다.
        self._banner().show_message(
            "고른 위치에는 기준 layer 와 매칭된 defect 이 없습니다.",
            "info",
            title="담을 사진 없음",
        )

    def _banner(self) -> NotificationBanner:
        """알림은 창 우상단 InfoBar 스택으로 나간다(03-screens 9절)."""
        if self._notice is None:
            self._notice = NotificationBanner(self)
        return self._notice
