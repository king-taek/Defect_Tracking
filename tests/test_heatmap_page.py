"""히트맵 페이지(단계 6) 계약.

자동 LOD 임계 · 한 화면 게이트 · 누적합 영역 합산 · row 0 아래 · 드래그 선택 · 이중선 링을
못 박는다. 지도는 die 수가 늘어도 스크롤이 아니라 표현 단계를 낮춰서 대응한다.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QAbstractScrollArea, QApplication  # noqa: E402

from app import heatmap  # noqa: E402
from app.config import AppSettings  # noqa: E402
from app.heatmap import HeatKey  # noqa: E402
from app.models import BaseDefectMatches, DefectRecord, MatchResult  # noqa: E402
from app.ui import theme  # noqa: E402


@pytest.fixture(scope="module")
def app():
    from qfluentwidgets import Theme, setTheme, setThemeColor

    instance = QApplication.instance() or QApplication([])
    setTheme(Theme.LIGHT)
    setThemeColor(theme.ACCENT_BASE)
    return instance


def _rec(col: int, row: int, layer: str = "LYA4", x: float = 10.0, y: float = 10.0):
    return DefectRecord(
        image_path=Path(f"/{layer}_{col}_{row}_{x}_{y}.jpg"),
        wafer_id="W1", layer=layer, layer_folder=layer,
        col=col, row=row, x=x, y=y,
    )


def _dataset(side: int, layers=("LYA4", "LYB4"), per_die: int = 1):
    """side x side die 격자에 defect 을 깐 (matches, records_by_layer)."""
    rbl: dict[str, list] = {lyr: [] for lyr in layers}
    for col in range(side):
        for row in range(side):
            count = 1 + (col * 3 + row * 5) % 7
            for i in range(count * per_die):
                for lyr in layers:
                    rbl[lyr].append(_rec(col, row, lyr, x=100.0 * i, y=100.0 * i))
    base = layers[0]
    matches = []
    for rec in rbl[base]:
        results = [
            MatchResult(compare_layer=lyr, base=rec, matched=rec)
            for lyr in layers[1:]
        ]
        matches.append(BaseDefectMatches(base=rec, results=results))
    return matches, rbl


def _page(app, side: int, size=(1264, 940)):
    from app.ui.pages.heatmap import HeatmapPage

    matches, rbl = _dataset(side)
    page = HeatmapPage()
    page.resize(*size)
    page.show()
    page.set_data(
        matches, "LYA4", ["LYB4"], None, lambda idxs: None, AppSettings(),
        records_by_layer=rbl,
    )
    for _ in range(6):
        QCoreApplication.processEvents()
    return page


# ---------------------------------------------------------------- 자동 LOD
def test_lod_mode_per_cell_size():
    """A7 임계: 20px 이상은 하위분할, 6~19px 는 중간, 6px 미만은 래스터."""
    assert heatmap.plan_lod(45).mode == heatmap.MODE_DETAIL
    assert heatmap.plan_lod(20).mode == heatmap.MODE_DETAIL
    assert heatmap.plan_lod(19.9).mode == heatmap.MODE_PLAIN
    assert heatmap.plan_lod(6).mode == heatmap.MODE_PLAIN
    assert heatmap.plan_lod(5.9).mode == heatmap.MODE_RASTER
    assert heatmap.plan_lod(1).mode == heatmap.MODE_RASTER


def test_lod_drops_features_in_order():
    """하위분할 -> 간격 -> 테두리 순서로만 사라진다."""
    detail = heatmap.plan_lod(24)
    assert (detail.subdivide, detail.gap, detail.border) == (True, True, True)
    # 하위분할만 해제
    mid = heatmap.plan_lod(14)
    assert (mid.subdivide, mid.gap, mid.border) == (False, True, True)
    # 간격까지 해제
    tight = heatmap.plan_lod(10)
    assert (tight.subdivide, tight.gap, tight.border) == (False, False, True)
    # 테두리까지 해제
    bare = heatmap.plan_lod(7)
    assert (bare.subdivide, bare.gap, bare.border) == (False, False, False)
    # 단계가 역전되지 않는다(작아질수록 켜진 것이 늘지 않는다).
    prev = (True, True, True)
    for px in range(45, 0, -1):
        plan = heatmap.plan_lod(px)
        cur = (plan.subdivide, plan.gap, plan.border)
        assert all(c <= p for c, p in zip(cur, prev)), px
        prev = cur


def test_layout_never_exceeds_available():
    """어떤 규모에서도 격자 전체가 주어진 상자 안에 들어간다(게이트)."""
    for side in (7, 16, 32, 64, 128):
        cell, gap, _plan = heatmap.layout_for(side, side, 394, 500)
        assert side * (cell + gap) + gap <= 394 + 1e-6
        assert side * (cell + gap) + gap <= 500 + 1e-6


# ------------------------------------------------------- 한 화면 게이트
def test_map_fits_container_at_4096_die(app):
    """4,096 die 에서도 지도가 카드 안에 통째로 들어오고 스크롤이 없다."""
    page = _page(app, 64)
    view = page.map
    assert view.plan().mode == heatmap.MODE_RASTER
    content = view.content_rect()
    assert view.rect().contains(content), (view.rect(), content)
    card = view.parentWidget()
    assert view.width() <= card.width() and view.height() <= card.height()
    # 지도 위로 스크롤 영역을 두지 않는다(스크롤 금지).
    node = view.parentWidget()
    while node is not None and node is not page:
        assert not isinstance(node, QAbstractScrollArea), node
        node = node.parentWidget()


def test_map_fits_container_at_every_scale(app):
    for side in (7, 32, 64):
        page = _page(app, side)
        assert page.map.rect().contains(page.map.content_rect()), side


# ---------------------------------------------------------- 2D 누적합
def test_region_sum_matches_naive():
    """무작위 영역 여러 개에서 누적합과 단순 합이 같다."""
    rng = random.Random(20260823)
    counts = {
        (c, r): rng.randint(0, 9) for c in range(40) for r in range(30)
    }
    grid = heatmap.DensityGrid(counts, 40, 30)
    for _ in range(200):
        c0, c1 = sorted((rng.randint(0, 39), rng.randint(0, 39)))
        r0, r1 = sorted((rng.randint(0, 29), rng.randint(0, 29)))
        naive = sum(
            counts[(c, r)]
            for c in range(c0, c1 + 1)
            for r in range(r0, r1 + 1)
        )
        assert grid.region_sum(c0, r0, c1, r1) == naive


def test_region_sum_honours_origin_and_clamps():
    counts = {(10, 5): 3, (11, 6): 4}
    grid = heatmap.DensityGrid(counts, 2, 2, origin=(10, 5))
    assert grid.total == 7
    assert grid.region_sum(10, 5, 11, 6) == 7
    assert grid.region_sum(10, 5, 10, 5) == 3
    # 격자 밖으로 나가도 잘라서 센다(드래그가 지도 밖으로 나갈 수 있다).
    assert grid.region_sum(-100, -100, 100, 100) == 7
    assert grid.region_sum(50, 50, 60, 60) == 0


def test_map_region_sum_uses_grid(app):
    """지도 위 드래그 사각의 합이 같은 범위의 단순 합과 같다."""
    page = _page(app, 8)
    view = page.map
    rect = view.content_rect()
    dies, total = view.region_sum(rect)
    assert total == sum(view._die_counts.values())
    assert dies == 8 * 8


# ------------------------------------------------------------ 웨이퍼 좌표계
def test_row0_is_at_screen_bottom(app):
    page = _page(app, 8)
    view = page.map
    bottom = view._die_rect(0, 0)
    top = view._die_rect(0, 7)
    assert bottom.y() > top.y(), "row 0 이 화면 맨 아래여야 한다"


def test_click_roundtrip_restores_die(app):
    """각 die 중심을 클릭하면 그 (col,row) 가 그대로 돌아온다."""
    page = _page(app, 8)
    view = page.map
    for col, row in [(0, 0), (0, 7), (7, 0), (3, 5)]:
        rect = view._die_rect(col, row)
        key = view._key_at(rect.center())
        assert key is not None and (key.col, key.row) == (col, row)


# ------------------------------------------------------------ 드래그 선택
def _drag(view, start, end):
    for kind, pos, btn in (
        (QEvent.MouseButtonPress, start, Qt.LeftButton),
        (QEvent.MouseMove, QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2), Qt.NoButton),
        (QEvent.MouseMove, end, Qt.NoButton),
        (QEvent.MouseButtonRelease, end, Qt.LeftButton),
    ):
        event = QMouseEvent(kind, QPointF(pos), Qt.LeftButton, btn, Qt.NoModifier)
        if kind == QEvent.MouseButtonPress:
            view.mousePressEvent(event)
        elif kind == QEvent.MouseMove:
            view.mouseMoveEvent(event)
        else:
            view.mouseReleaseEvent(event)


@pytest.mark.parametrize("side", [8, 32, 64])
def test_drag_rectangle_selects_in_every_mode(app, side):
    """드래그 사각 선택은 표현 단계(하위분할/중간/래스터)와 무관하게 항상 된다."""
    page = _page(app, side)
    view = page.map
    seen = []
    view.selection_changed.connect(lambda keys: seen.append(list(keys)))
    a = view._die_rect(1, 1).center()
    b = view._die_rect(3, 3).center()
    _drag(view, a, b)
    assert seen and seen[-1], f"{side}: 드래그로 선택이 생겨야 한다"
    got = {(k.col, k.row) for k in seen[-1]}
    assert {(1, 1), (2, 2), (3, 3)} <= got


def test_drag_works_without_multi_mode(app):
    """여러 다이 선택 모드는 클릭 동작만 바꾼다. 드래그는 모드와 무관하다."""
    page = _page(app, 8)
    view = page.map
    assert view._multi is False
    _drag(view, view._die_rect(0, 0).center(), view._die_rect(2, 2).center())
    without = set(view.selected_keys())
    assert len(without) >= 9
    view.set_multi(True)
    _drag(view, view._die_rect(0, 0).center(), view._die_rect(2, 2).center())
    assert set(view.selected_keys()) == without


def test_multi_mode_click_accumulates(app):
    page = _page(app, 8)
    view = page.map
    view.set_multi(True)
    for col, row in [(1, 1), (4, 4)]:
        pos = view._die_rect(col, row).center()
        for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            event = QMouseEvent(kind, QPointF(pos), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            if kind == QEvent.MouseButtonPress:
                view.mousePressEvent(event)
            else:
                view.mouseReleaseEvent(event)
    assert {(k.col, k.row) for k in view.selected_keys()} == {(1, 1), (4, 4)}


def test_drag_emits_region_sum(app):
    page = _page(app, 32)
    view = page.map
    sums = []
    view.region_summed.connect(lambda dies, total: sums.append((dies, total)))
    _drag(view, view._die_rect(0, 0).center(), view._die_rect(5, 5).center())
    assert sums, "드래그 중 영역 합계를 알려야 한다"
    dies, total = sums[-1]
    naive = sum(
        view._die_counts.get((c, r), 0)
        for c in range(0, 6) for r in range(0, 6)
    )
    assert (dies, total) == (36, naive)


# ------------------------------------------------------------ 선택 링 (A22)
def test_selection_ring_uses_both_theme_colors(app):
    """링 두 겹의 색이 theme.SELECTION_RING 이 지정한 토큰 그대로다."""
    from app.ui.pages.heatmap import DensityMapView

    view = DensityMapView()
    tokens = theme.fluent_tokens(False)
    outer, inner = view._ring_pens(tokens, False)
    spec = theme.SELECTION_RING
    assert outer.color().name().lower() == theme.flatten(
        tokens[spec["outer"]], tokens["card"]
    ).lower()
    assert inner.color().name().lower() == theme.flatten(
        tokens[spec["inner"]], tokens["card"]
    ).lower()
    assert outer.color() != inner.color()
    dashed_outer, dashed_inner = view._ring_pens(tokens, True)
    assert dashed_outer.style() == Qt.DashLine and dashed_inner.style() == Qt.DashLine


@pytest.mark.parametrize("dark", [False, True])
def test_selection_ring_visible_at_min_and_max_density(app, dark):
    """최고 밀도 칸에서도 링이 보인다(A22). 단색 링은 램프 상한과 같은 색이라 사라졌다."""
    from qfluentwidgets import Theme, setTheme

    from app.ui.pages.heatmap import DensityMapView

    setTheme(Theme.DARK if dark else Theme.LIGHT)
    try:
        view = DensityMapView()
        view.resize(240, 120)
        # 왼쪽 칸은 램프 최저(1개), 오른쪽 칸은 램프 최고(9개).
        view.set_data(2, 1, None, False, {HeatKey(0, 0): 1, HeatKey(1, 0): 9})
        view.set_selection([HeatKey(0, 0), HeatKey(1, 0)])
        image = view.grab().toImage()
        tokens = theme.fluent_tokens(dark)
        spec = theme.SELECTION_RING
        outer = theme.flatten(tokens[spec["outer"]], tokens["card"]).lower()
        inner = theme.flatten(tokens[spec["inner"]], tokens["card"]).lower()

        def colors_in(rect) -> set[str]:
            found = set()
            for x in range(rect.left(), rect.right() + 1):
                for y in range(rect.top(), rect.bottom() + 1):
                    found.add(image.pixelColor(x, y).name().lower())
            return found

        low = colors_in(view.key_rect(HeatKey(0, 0)).toAlignedRect())
        high = colors_in(view.key_rect(HeatKey(1, 0)).toAlignedRect())
        # 연한 칸은 바깥 링이, 진한 칸은 안쪽 링이 대비를 만든다.
        assert outer in low, (outer, sorted(low))
        assert inner in high, (inner, sorted(high))
        # 두 겹 다 그린다.
        assert inner in low and outer in high
    finally:
        setTheme(Theme.DARK if dark else Theme.LIGHT)
        setTheme(Theme.LIGHT)


# ------------------------------------------------------------ 단일 잉크 램프
def test_single_ink_ramp_alpha_range():
    assert heatmap.ramp_alpha(0, 9) == 0.0
    assert heatmap.ramp_alpha(1, 9) == pytest.approx(heatmap.RAMP_MIN_ALPHA)
    assert heatmap.ramp_alpha(9, 9) == pytest.approx(heatmap.RAMP_MAX_ALPHA)
    assert heatmap.ramp_alpha(5, 9) == pytest.approx(0.12 + 0.88 * 0.5)
    # 단조 증가
    values = [heatmap.ramp_alpha(n, 9) for n in range(1, 10)]
    assert values == sorted(values)


def test_ramp_is_one_hue_from_accent_fill(app):
    """램프 색은 accentFill 하나에서만 나온다(파랑->코랄 2색 램프 제거)."""
    from app.ui.pages.heatmap import _InkRamp

    tokens = theme.fluent_tokens(False)
    ramp = _InkRamp(tokens, 9)
    fill = ramp.color(9).name().lower()
    assert fill == tokens["accentFill"].lower()
    source = Path("app/ui/pages/heatmap.py").read_text(encoding="utf-8")
    assert "#39ff14" not in source.lower(), "네온 그린 선택색은 제거 대상이다"
    assert "6fb0e0" not in source.lower() and "ff8a5c" not in source.lower()


# ------------------------------------------------------------ 페이지 계약
def test_page_object_name_is_route_key(app):
    from app.ui.pages.heatmap import HeatmapPage

    page = HeatmapPage()
    assert page.objectName() == "heatmapInterface"
    assert page.is_empty_state(), "데이터가 오기 전에는 빈 상태다"


def test_set_data_fills_map_and_totals(app):
    page = _page(app, 8)
    assert not page.is_empty_state()
    assert page.map.total > 0
    assert "die" in page.lbl_total.text() and "defect" in page.lbl_total.text()
    assert page.lbl_legend_hi.text().startswith("최대")


def test_select_die_opens_that_position(app):
    """판독 화면에서 넘어온 die 를 고른 상태로 연다(A12 점프 경로)."""
    from app.ui.pages.heatmap import HeatmapPage

    matches, rbl = _dataset(8)
    page = HeatmapPage()
    page.resize(1264, 940)
    page.show()
    page.set_data(
        matches, "LYA4", ["LYB4"], None, lambda idxs: None, AppSettings(),
        records_by_layer=rbl, select_die=(3, 4),
    )
    for _ in range(6):
        QCoreApplication.processEvents()
    keys = page.map.selected_keys()
    assert keys and all((k.col, k.row) == (3, 4) for k in keys)
    assert "die (3,4)" in page.lbl_read_title.text()


def test_double_click_asks_for_die_jump(app):
    """die 점프 경로는 이 페이지가 흡수한다(wafer_map.py 삭제, A12)."""
    page = _page(app, 8)
    seen = []
    page.die_activated.connect(lambda c, r: seen.append((c, r)))
    pos = page.map._die_rect(2, 3).center()
    event = QMouseEvent(
        QEvent.MouseButtonDblClick, QPointF(pos), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier
    )
    page.map.mouseDoubleClickEvent(event)
    assert seen == [(2, 3)]


def test_only_unmatched_gets_a_tag(app):
    """교차매치 초록 태그는 없앤다. 태그는 '매치 없음' 하나뿐이다."""
    source = Path("app/ui/pages/heatmap.py").read_text(encoding="utf-8")
    assert "교차매치" not in source
    assert "매치 없음" in source
    page = _page(app, 8)
    page.map.set_selection([HeatKey(1, 1)])
    for _ in range(4):
        QCoreApplication.processEvents()
    labels = [w.text() for w in page._read_host.findChildren(type(page.lbl_hint))]
    assert not any("교차매치" in t for t in labels)


def test_layer_chips_drive_the_map(app):
    """조사 layer 칩을 끄면 그 layer 의 defect 이 지도에서 빠진다."""
    page = _page(app, 8)
    before = page.map.total
    page._on_layer_toggled("LYB4", False)
    for _ in range(4):
        QCoreApplication.processEvents()
    assert page.selected_layers() == ["LYA4"]
    assert page.map.total < before


def test_slot_rail_filters(app):
    from app.ui.pages.heatmap import _ALL_SLOTS

    page = _page(app, 8)
    assert page.slots.currentRouteKey() == _ALL_SLOTS
    page._on_slot("W1")
    for _ in range(4):
        QCoreApplication.processEvents()
    assert page.map.total > 0


def test_no_emoji_or_em_dash_in_source():
    """카피 규칙: 이모지 0건, em-dash 0건. 글자를 코드포인트로 만들어 이 파일도 검사 대상에 둔다."""
    em_dash = chr(0x2014)
    for name in ("app/ui/pages/heatmap.py", "app/heatmap.py", "tests/test_heatmap_page.py"):
        text = Path(name).read_text(encoding="utf-8")
        assert em_dash not in text, name
        assert not any(ord(ch) >= 0x1F300 for ch in text), name
