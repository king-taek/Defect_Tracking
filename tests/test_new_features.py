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


def test_export_tray_add_and_clear(win):
    win._goto(0)
    assert win._export_tray == []
    win._add_current_to_export()
    assert win._export_tray == [0]
    # 중복 담기는 무시
    win._add_current_to_export()
    assert win._export_tray == [0]
    win._goto(1)
    win._add_current_to_export()
    assert win._export_tray == [0, 1]
    assert "(2)" in win.btn_add_export.text()
    # 기준 layer 변경 시 트레이 초기화
    win.top.cmb_base.setCurrentText("LYB4")
    for _ in range(5):
        QCoreApplication.processEvents()
    assert win._export_tray == []


def test_export_tray_dialog_remove(win, app):
    from app.ui.export_dialog import ExportTrayDialog

    entries = [(i, win.matches[i]) for i in range(min(3, len(win.matches)))]
    dlg = ExportTrayDialog(entries, win.thumb_cache)
    assert set(dlg.selected_indices()) == {e[0] for e in entries}
    remove_idx = entries[0][0]
    dlg._remove(remove_idx)
    assert remove_idx not in dlg.selected_indices()
    dlg._clear_all()
    assert dlg.selected_indices() == []


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
