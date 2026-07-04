"""신규 기능 오프스크린 UI 스모크 테스트.

항목 1(출력 트레이), 2(매치 없는 셀 숨김), 4·5(히트맵), 7(썸네일 배율).
모달을 띄우지 않는 내부 메서드/위젯만 직접 호출한다.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import scanner  # noqa: E402
from app.config import AppSettings  # noqa: E402
from tools.make_sample_data import generate  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app, tmp_path):
    from app.ui.main_window import MainWindow

    lot = generate(tmp_path / "src")
    idx = scanner.scan_lot(lot)
    w = MainWindow(AppSettings(workspace=str(tmp_path / "ws"), auto_update_check=False))
    w.lot_index = idx
    w._on_scan_finished(idx)
    w.top.cmb_base.setCurrentText("LYA4")
    for _ in range(10):
        QCoreApplication.processEvents()
    return w


# ---- 항목 9/1: 필터 드롭다운 제거 + 출력 트레이 ----

def test_filter_dropdown_removed(win):
    assert not hasattr(win, "cmb_filter")
    assert win._filter == "matched"


def test_export_tray_add_and_persist(win):
    # 트레이는 BaseDefectMatches 스냅샷을 담고, layer/자재가 바뀌어도 유지된다(항목 1).
    win._goto(0)
    assert win._export_tray == []
    p0 = str(win.matches[0].base.image_path)
    win._add_current_to_export()
    assert [str(m.base.image_path) for m in win._export_tray] == [p0]
    win._add_current_to_export()  # 중복 무시
    assert len(win._export_tray) == 1
    win._goto(1)
    win._add_current_to_export()
    assert len(win._export_tray) == 2
    assert "(2)" in win.btn_add_export.text()
    # 기준 layer 를 바꿔도 담은 것이 유지된다.
    win.top.cmb_base.setCurrentText("LYB4")
    for _ in range(5):
        QCoreApplication.processEvents()
    assert len(win._export_tray) == 2


def test_export_tray_dialog_remove_and_add_all(win, app):
    from app.ui.export_dialog import ExportTrayDialog

    entries = [win.matches[i] for i in range(min(3, len(win.matches)))]
    all_matched = [m for m in win.matches if win._match_status(m) != "none"]
    dlg = ExportTrayDialog(entries, win.thumb_cache, all_matched=all_matched)
    assert {str(m.base.image_path) for m in dlg.selected()} == {
        str(m.base.image_path) for m in entries
    }
    # 개별 제거
    key0 = str(entries[0].base.image_path)
    dlg._remove(key0)
    assert key0 not in {str(m.base.image_path) for m in dlg.selected()}
    # '이번 LOT 전체(매치) 추가' → 매치 있는 것이 모두 담김(중복 제거)
    dlg._add_all_matched()
    assert {str(m.base.image_path) for m in dlg.selected()} == {
        str(m.base.image_path) for m in all_matched
    }
    dlg._clear_all()
    assert dlg.selected() == []


# ---- 항목 2: 매치 없는 셀 숨김(re-pack) ----

def test_grid_hides_unmatched_cells(win):
    # 허용오차 0 → 모든 비교 매칭 실패 → 보이는 셀은 기준 하나뿐.
    win.top.spn_tol.setValue(0.0)
    for _ in range(5):
        QCoreApplication.processEvents()
    win._goto(0)
    grid = win.grid
    # isHidden(): 창을 show 하지 않아도 명시적 숨김 상태를 반영한다.
    visible = [l for l, c in grid._cells.items() if not c.isHidden()]
    assert visible == [grid._base_layer]
    # 큰 허용오차 → 비교도 매칭 → 비교 셀도 보인다.
    win.top.spn_tol.setValue(100000.0)
    for _ in range(5):
        QCoreApplication.processEvents()
    win._goto(0)
    visible2 = {l for l, c in grid._cells.items() if not c.isHidden()}
    assert grid._base_layer in visible2
    assert len(visible2) >= 2


# ---- 썸네일 확대율: 5× 고정, 조절 UI 없음 ----

def test_thumbnail_zoom_fixed_5x_no_button(win):
    # 중앙 20%(≈5×) 고정.
    assert abs(win._thumbnail_center_ratio() - 0.20) < 1e-6
    # 조절 버튼/메서드가 제거됐다.
    assert not hasattr(win, "btn_thumb_zoom")
    assert not hasattr(win, "_adjust_thumbnail_zoom")


# ---- 항목 4·5: 히트맵 다이얼로그 ----

def test_heatmap_dialog_constructs_and_selects(win, app):
    from app.ui.heatmap_dialog import HeatmapDialog

    added = []
    dlg = HeatmapDialog(
        win.matches, win.top.base_layer(), win.top.compare_layers(),
        win.thumb_cache, lambda idxs: added.extend(idxs), win.settings,
        current_wafer=win.matches[0].base.wafer_id,
    )
    # 밀도 그룹이 채워지고 웨이퍼맵 격자가 잡힌다.
    assert dlg._map._cols >= 1 and dlg._map._rows >= 1
    assert dlg._groups, "defect 밀도 그룹이 있어야 한다"
    # 첫 셀 선택 → 상세 목록 구성(행 stretch 외 1개 이상) + 담기 동작
    key = next(iter(dlg._groups))
    dlg._on_cell_clicked(key)
    assert dlg._detail_box.count() >= 2  # 행 위젯 + stretch
    dlg._add_all_current()
    assert added, "이 위치 전체 담기가 트레이 콜백을 호출해야 한다"


def test_heatmap_all_wafers_aggregates(win, app):
    from app.ui.heatmap_dialog import HeatmapDialog, _ALL_WAFERS

    dlg = HeatmapDialog(
        win.matches, win.top.base_layer(), win.top.compare_layers(),
        win.thumb_cache, lambda idxs: None, win.settings,
    )
    # '전체' wafer 항목이 콤보 맨 앞에 있고, 선택 시 모든 wafer 를 집계한다.
    assert dlg.cmb_wafer.itemText(0) == _ALL_WAFERS
    dlg._on_wafer_changed(_ALL_WAFERS)
    all_entries = dlg._current_entries()
    total = sum(1 for m in win.matches
                if m.base.col is not None and m.base.row is not None
                and m.base.col >= 0 and m.base.row >= 0)
    assert len(all_entries) == total


def test_wafer_map_bbox_normalized_no_margin_or_clip(win, app):
    """웨이퍼맵이 좌표 원점과 무관하게 bounding box (0,0) 기준으로 그려진다.

    회귀: 정합 shift 로 내용 min 이 양수면 왼쪽/위 여백(떠 보임), 음수면 좌·상단 잘림이
    생겼다. 이제 origin 정규화로 그려지는 셀이 항상 (0,0)부터 시작하고 잘리지 않아야 한다.
    """
    from app import config
    from app.config import ProductConfig
    from app.models import BaseDefectMatches, DefectRecord, MatchResult
    from pathlib import Path

    dm = {(c, r) for c in range(7) for r in range(6) if 1 <= c <= 5 or 1 <= r <= 4}
    config.PRODUCTS["TESTDISC_NORM"] = ProductConfig(
        key="TESTDISC_NORM", name="Test Disc", camtek_pitch_x=1, camtek_pitch_y=1,
        kla_package_x_count=7, kla_package_y_count=6, die_map=frozenset(dm), source="db",
    )
    prod0 = config.active_product().key

    def mk(col, row):
        b = DefectRecord(image_path=Path("/b.jpg"), wafer_id="W1", layer="LYA4",
                         layer_folder="LYA4", col=col, row=row, x=0.0, y=0.0)
        return BaseDefectMatches(base=b, results=[MatchResult(compare_layer="LYB4", base=b, matched=b)])

    try:
        config.set_active_product("TESTDISC_NORM")
        for off in [(0, 0), (3, 2), (-2, -1), (10, 7)]:
            obs = [(c + off[0], r + off[1]) for c, r in list(dm)[:8]]
            win.matches = [mk(c, r) for c, r in obs]
            win.current = 0
            win._align_cache.clear()
            win._update_wafer_map(win.matches[0])
            wm = win.wafer_map
            oc, orr = wm._origin_col, wm._origin_row
            content = set(wm._valid) if wm._valid else set(wm._states)
            assert content, f"offset {off}: 그릴 내용이 있어야 한다"
            # 그려지는 최소 셀이 (0,0)에 오고(여백 0), 모두 격자 안(잘림 0)이어야 한다.
            assert min(c - oc for c, _ in content) == 0
            assert min(r - orr for _, r in content) == 0
            assert all(0 <= c - oc < wm._cols and 0 <= r - orr < wm._rows for c, r in content)
    finally:
        config.set_active_product(prod0)
        config.PRODUCTS.pop("TESTDISC_NORM", None)
        win._align_cache.clear()


def test_heatmap_subdivide_small_die_count(app):
    """die 개수가 적으면 웨이퍼맵이 하위셀 분할 모드가 된다."""
    from app.ui.heatmap_dialog import HeatmapDialog
    from app.models import BaseDefectMatches, DefectRecord
    from pathlib import Path

    def mk(col, row, x, y):
        base = DefectRecord(image_path=Path("/b.jpg"), wafer_id="W1", layer="LYA4",
                            layer_folder="LYA4", col=col, row=row, x=x, y=y)
        return BaseDefectMatches(base=base)

    # 4개 die(<50) → subdivide
    matches = [mk(0, 0, 0, 0), mk(0, 0, 90, 90), mk(1, 1, 0, 0), mk(2, 2, 0, 0)]
    dlg = HeatmapDialog(matches, "LYA4", [], None, lambda idxs: None, AppSettings())
    assert dlg._map._subdivide is True
