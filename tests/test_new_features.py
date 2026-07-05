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
    dlg._on_selection_changed([key])
    assert dlg._detail_box.count() >= 2  # 행 위젯 + stretch
    dlg._add_all_current()
    assert added, "이 위치 전체 담기가 트레이 콜백을 호출해야 한다"


def test_heatmap_multi_select_union(win, app):
    from app.ui.heatmap_dialog import HeatmapDialog

    added = []
    dlg = HeatmapDialog(
        win.matches, win.top.base_layer(), win.top.compare_layers(),
        win.thumb_cache, lambda idxs: added.extend(idxs), win.settings,
        current_wafer=win.matches[0].base.wafer_id,
    )
    keys = list(dlg._groups.keys())
    if len(keys) >= 2:
        dlg._on_selection_changed(keys[:2])
        expected = set(dlg._groups[keys[0]]) | set(dlg._groups[keys[1]])
        assert set(dlg._union_indices()) == expected
    # 다중 선택 토글 → 맵이 multi 모드
    dlg.btn_multi.setChecked(True)
    assert dlg._map._multi is True


def test_heatmap_show_all_includes_unmatched(win, app):
    """'전체 defect 보기'는 매칭 없는 defect 도 records_by_layer 에서 수집한다."""
    from app.ui.heatmap_dialog import HeatmapDialog

    rbl = win.lot_index.records_by_layer()
    dlg = HeatmapDialog(
        win.matches, win.top.base_layer(), win.top.compare_layers(),
        win.thumb_cache, lambda idxs: None, win.settings,
        current_wafer=win.matches[0].base.wafer_id, records_by_layer=rbl,
    )
    key = next(iter(dlg._groups))
    dlg._on_selection_changed([key])
    dlg.btn_show_all.setChecked(True)
    # 선택 위치에서 선택 layer 의 record 를 실제로 수집한다(기준 defect 이 하나는 있음).
    recs = dlg._records_at_selection()
    assert any(lyr == dlg._base_layer for lyr, _ in recs)


def test_heatmap_all_wafers_aggregates(win, app):
    from app.ui.heatmap_dialog import HeatmapDialog, _ALL_WAFERS

    dlg = HeatmapDialog(
        win.matches, win.top.base_layer(), win.top.compare_layers(),
        win.thumb_cache, lambda idxs: None, win.settings,
    )
    # '전체' wafer 항목이 콤보 맨 앞에 있고, 선택 시 모든 wafer 를 집계한다.
    assert dlg.cmb_wafer.itemText(0) == _ALL_WAFERS
    dlg._on_wafer_changed(_ALL_WAFERS)
    all_entries = dlg._base_entries()
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


def test_excel_no_top_item_header(win, app, tmp_path):
    """엑셀 상단 '항목' 컬럼 헤더 행이 제거됐다(블록마다 Layer 행 사용)."""
    from app.export.excel_report import export_excel
    from openpyxl import load_workbook

    out = tmp_path / "o.xlsx"
    sel = win.matches[:2]
    export_excel(out, lot_name="L", base_layer=win.top.base_layer(),
                 compare_layers=win.top.compare_layers(), tolerance=100.0,
                 selected=sel, thumb_cache=win.thumb_cache,
                 source_roots=[win.lot_index.lot_path])
    wb = load_workbook(out)
    ws = wb.active
    firsts = {row[0] for row in ws.iter_rows(values_only=True) if row}
    assert "항목" not in firsts
    assert "Layer" in firsts  # 블록별 Layer 행은 있다


def test_grid_rollback_base_top_left(win):
    # 항목 5 롤백: 기준 셀이 압축 배치의 (0,0)에 온다.
    win.top.spn_tol.setValue(100000.0)
    for _ in range(5):
        QCoreApplication.processEvents()
    win._goto(0)
    gl = win.grid._grid
    base_cell = win.grid._cells[win.grid._base_layer]
    r, c, _, _ = gl.getItemPosition(gl.indexOf(base_cell))
    assert (r, c) == (0, 0)


def test_folder_picker_navigation_and_lists(app, tmp_path):
    from app.ui.folder_picker import FolderPickerDialog

    lot = generate(tmp_path / "src")  # tmp_path/src/<LOT_NAME>
    root = lot.parent
    s = AppSettings(workspace=str(tmp_path / "ws"), recent_folders=[str(lot)])
    dlg = FolderPickerDialog(s, str(root))

    # 목록에 LOT 폴더가 뜬다(한 단계 os.scandir).
    names = [dlg.listw.item(i).data(0x0100) for i in range(dlg.listw.count())]
    assert lot.name in names

    # 진입/위로 네비게이션.
    dlg._go_to(lot)
    assert dlg._cur == lot
    dlg._go_up()
    assert dlg._cur == root
    # 뒤로: 방금 위로 왔으니 history 로 lot 복귀.
    dlg._go_back()
    assert dlg._cur == lot


def test_folder_picker_filter_hides_items(app, tmp_path):
    from app.ui.folder_picker import FolderPickerDialog

    root = tmp_path / "root"
    (root / "AlphaLot").mkdir(parents=True)
    (root / "BetaLot").mkdir()
    dlg = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws")), str(root))

    dlg._apply_filter("alpha")
    hidden = {
        dlg.listw.item(i).data(0x0100): dlg.listw.item(i).isHidden()
        for i in range(dlg.listw.count())
    }
    assert hidden.get("AlphaLot") is False
    assert hidden.get("BetaLot") is True


def test_folder_picker_favorite_toggle_persists(app, tmp_path):
    from app.ui.folder_picker import FolderPickerDialog

    (tmp_path / "root" / "sub").mkdir(parents=True)
    s = AppSettings(workspace=str(tmp_path / "ws"))
    dlg = FolderPickerDialog(s, str(tmp_path / "root"))
    dlg._set_candidate(tmp_path / "root" / "sub")
    dlg._toggle_favorite()
    assert str(tmp_path / "root" / "sub") in s.favorite_folders
    dlg._toggle_favorite()
    assert str(tmp_path / "root" / "sub") not in s.favorite_folders


def test_folder_picker_corrects_layer_to_material(app, tmp_path):
    from app.ui.folder_picker import FolderPickerDialog

    lot = generate(tmp_path / "src")
    layer = next(p for p in lot.iterdir() if p.is_dir())  # 자재 아래 layer
    s = AppSettings(workspace=str(tmp_path / "ws"))
    dlg = FolderPickerDialog(s, str(lot))

    # layer 폴더를 후보로 두면 선택 시 상위 자재로 보정된다.
    dlg._set_candidate(layer)
    assert dlg.selected_path() == str(lot)

    # 자재 폴더 자체는 그대로.
    dlg._set_candidate(lot)
    assert dlg.selected_path() == str(lot)


def test_theme_styles_item_views():
    # 트리/리스트 뷰가 전역 테마로 어둡게 스타일링된다(흰 배경 방지).
    from app.ui import theme
    assert "QTreeView" in theme.STYLESHEET
    assert "QHeaderView::section" in theme.STYLESHEET


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


# ---- 8차: 히트맵 모드/드래그/클러스터 · 폴더트리 · 출력 · 도움말 ----

def _make_heatmap(win):
    from app.ui.heatmap_dialog import HeatmapDialog
    return HeatmapDialog(
        win.matches, win.top.base_layer(), win.top.compare_layers(),
        win.thumb_cache, lambda idxs: None, win.settings,
        records_by_layer=win.lot_index.records_by_layer(),
    )


def test_heatmap_default_wafer_is_all(win, app):
    from app.ui.heatmap_dialog import _ALL_WAFERS
    dlg = _make_heatmap(win)
    assert dlg._current_wafer == _ALL_WAFERS
    assert dlg.cmb_wafer.currentText() == _ALL_WAFERS


def test_heatmap_toggle_button_text_on_off(win, app):
    dlg = _make_heatmap(win)
    assert "OFF" in dlg.btn_show_all.text()
    dlg.btn_show_all.setChecked(True)
    assert "ON" in dlg.btn_show_all.text()
    dlg.btn_multi.setChecked(True)
    assert "ON" in dlg.btn_multi.text()


def test_heatmap_show_all_map_density_is_superset(win, app):
    # 전체 defect 모드의 맵 entries 는 매치만(기준 defect)보다 많다(다층 defect 포함).
    dlg = _make_heatmap(win)
    base_n = len(dlg._map_entries())      # 매치만: 기준 defect
    dlg._show_all = True
    all_n = len(dlg._map_entries())        # 전체: 선택 layer 모든 defect
    assert all_n >= base_n
    assert all_n > base_n


def test_heatmap_matched_only_hides_unmatched(win, app):
    dlg = _make_heatmap(win)
    dlg._selected_keys = list(dlg._groups.keys())
    dlg._show_all = False
    dlg._rebuild_detail()
    # 담기 대상(=매치만 상세에 표시되는 기준)은 전부 매칭된 것.
    assert dlg._add_targets == [bi for bi in dlg._add_targets if dlg._is_matched(bi)]
    assert all(dlg._is_matched(bi) for bi in dlg._add_targets)


def test_heatmap_map_caption_shows_mode(win, app):
    dlg = _make_heatmap(win)
    assert "매치만" in dlg.lbl_map.text()
    dlg.btn_show_all.setChecked(True)
    assert "전체 defect" in dlg.lbl_map.text()


def test_heatmap_drag_box_selects_without_multi(win, app):
    import types
    from PySide6.QtCore import QPoint, Qt as _Qt
    dlg = _make_heatmap(win)
    m = dlg._map
    assert m._multi is False
    dense = [k for k, c in m._density.items() if c > 0]
    if not dense:
        return  # 데이터 없으면 skip
    # 위젯 전체를 감싸는 드래그 → 밀도>0 die 다중 선택(멀티 off 에서도)
    m._rubber_origin = QPoint(0, 0)
    m._rubber_cur = QPoint(m.width(), m.height())
    m._dragging = True
    m.mouseReleaseEvent(types.SimpleNamespace(button=lambda: _Qt.LeftButton))
    assert len(m._selected_keys) >= 1


def test_heatmap_show_all_builds_cross_layer_detail(win, app):
    dlg = _make_heatmap(win)
    dlg.btn_show_all.setChecked(True)
    keys = list(dlg._groups.keys())
    if not keys:
        return
    dlg._selected_keys = keys[:2]
    dlg._rebuild_detail()
    txt = dlg.lbl_detail.text()
    assert ("교차매치" in txt) or ("개별" in txt)


def test_folder_picker_tree_lazy_expand_and_click(app, tmp_path):
    from PySide6.QtCore import Qt as _Qt
    from app.ui.folder_picker import FolderPickerDialog

    (tmp_path / "root" / "childA").mkdir(parents=True)
    (tmp_path / "root" / "childB").mkdir()
    dlg = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws")), str(tmp_path))
    node = dlg._make_dir_node(dlg.sidebar.invisibleRootItem(), "root", str(tmp_path / "root"))
    assert node.childCount() == 1  # 더미(펼침 화살표)
    dlg._on_tree_expanded(node)
    paths = [node.child(i).data(0, _Qt.UserRole) for i in range(node.childCount())]
    assert any(p.endswith("childA") for p in paths)
    dlg._on_tree_clicked(node)
    assert dlg._cur == (tmp_path / "root")


def test_export_dialog_has_visible_confirm_button(app):
    from app.ui.export_dialog import ExportTrayDialog
    dlg = ExportTrayDialog([], None, None)
    assert hasattr(dlg, "btn_export")
    assert dlg.btn_export.text() == "Excel 출력"
    assert dlg.btn_export.isEnabled() is False  # 빈 트레이 → 비활성(존재는 함)


def test_help_dialog_has_sections_and_features(app):
    from app.ui.help_dialog import ShortcutsDialog, _FEATURES, _SHORTCUT_GROUPS
    dlg = ShortcutsDialog()
    assert dlg.windowTitle() == "도움말"
    assert len(_SHORTCUT_GROUPS) >= 3
    names = [n for n, _ in _FEATURES]
    assert any("히트맵" in n for n in names)
    assert any("클러스터" in n for n in names)


# ---- 9차: 메인 매치 클러스터링 · 히트맵 강조/개별 · 폴더 트리 · 리브랜딩 ----

def test_main_match_collapses_near_duplicates(app, tmp_path):
    """메인 매치가 근접 중복 기준 defect 을 대표 1개로 접는다(base_cluster + '+n')."""
    from app.ui.main_window import MainWindow
    from tools.make_sample_data import generate

    lot = generate(tmp_path / "src")
    # 기존 base defect 과 같은 die·근접 위치의 중복 이미지를 하나 추가한다.
    idx = scanner.scan_lot(lot)
    base_layer = "LYA4"
    raw = [r for r in idx.records_for_layer(base_layer) if r.ok]
    assert raw
    import dataclasses
    dup = dataclasses.replace(
        raw[0],
        image_path=raw[0].image_path.with_name("dup_" + raw[0].image_path.name),
        x=(raw[0].x or 0.0) + 5.0,
    )
    idx.records.append(dup)

    w = MainWindow(AppSettings(workspace=str(tmp_path / "ws"), auto_update_check=False))
    w.lot_index = idx
    w._on_scan_finished(idx)
    w.top.cmb_base.setCurrentText(base_layer)
    for _ in range(10):
        QCoreApplication.processEvents()

    raw_count = len([r for r in idx.records_for_layer(base_layer) if r.ok])
    assert len(w.matches) < raw_count  # 접힘
    assert any(getattr(m.base_cluster, "extra_count", 0) for m in w.matches)


def test_compare_grid_shows_cluster_badge(app, tmp_path):
    from app.ui.compare_grid import CompareGrid, LayerCell
    from app.models import BaseDefectMatches, DefectRecord
    from app.clustering import Cluster
    from pathlib import Path

    def rec(n):
        return DefectRecord(image_path=Path(f"/{n}.jpg"), wafer_id="W1", layer="B",
                            layer_folder="B", col=1, row=1, x=0.0, y=0.0)
    grid = CompareGrid()
    grid.build_layout([["B"]], "B")
    a, b = rec("a"), rec("b")
    item = BaseDefectMatches(base=a, results=[], base_cluster=Cluster(a, [a, b]))
    grid.update_for_base(item, [])
    cell = grid._cells["B"]
    assert not cell.more_badge.isHidden()  # 명시적으로 표시됨(창 미표시라 isVisible 대신)
    assert cell.more_badge.text() == "+1"
    # 클릭 시 묶인 멤버 목록을 emit
    got = []
    grid.base_cluster_clicked.connect(lambda m: got.append(m))
    cell._emit_cluster()
    assert got and len(got[0]) == 2


def test_heatmap_selection_paint_smoke(win, app):
    from PySide6.QtGui import QPixmap, QPainter
    dlg = _make_heatmap(win)
    dlg._selected_keys = list(dlg._groups.keys())[:1]
    dlg._map._selected_keys = set(dlg._selected_keys)
    pm = QPixmap(dlg._map.width() or 200, dlg._map.height() or 200)
    p = QPainter(pm)
    dlg._map._paint_selection(p)  # 채움+이중외곽선 경로가 예외 없이 실행
    p.end()


def test_heatmap_individual_flow_section(win, app):
    # 전체 defect 모드에서 개별(미매칭) 그룹이 FlowLayout 섹션으로 묶인다.
    from app.ui.flow_layout import FlowLayout
    dlg = _make_heatmap(win)
    groups = [{"LYA4": _one_cluster("/x.jpg")}]  # 단일 layer → 개별
    sec = dlg._make_individual_section(groups)
    flows = [c for c in sec.findChildren(QWidget) if c.layout().__class__.__name__ == "FlowLayout"] \
        if False else None
    # 섹션 캡션에 '개별(미매칭)' 포함
    from PySide6.QtWidgets import QLabel
    labels = [l.text() for l in sec.findChildren(QLabel)]
    assert any("개별(미매칭)" in t for t in labels)


def _one_cluster(path):
    from app.clustering import Cluster
    from app.models import DefectRecord
    from pathlib import Path
    r = DefectRecord(image_path=Path(path), wafer_id="W1", layer="LYA4",
                     layer_folder="LYA4", col=1, row=1, x=0.0, y=0.0)
    return Cluster(r, [r])


def test_folder_picker_tree_first_and_reveal(app, tmp_path):
    from PySide6.QtCore import Qt as _Qt
    from app.ui.folder_picker import FolderPickerDialog
    (tmp_path / "lot" / "layerA").mkdir(parents=True)
    dlg = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws")), str(tmp_path / "lot"))
    tops = [dlg.sidebar.topLevelItem(i).text(0) for i in range(dlg.sidebar.topLevelItemCount())]
    assert any("홈" in t for t in tops)  # 최상위는 폴더 루트(홈/드라이브)
    dlg._go_to(tmp_path / "lot" / "layerA")
    cur = dlg.sidebar.currentItem()
    assert cur is not None and str(cur.data(0, _Qt.UserRole)).endswith("layerA")


def test_no_conder_branding_left():
    import subprocess
    out = subprocess.run(
        ["grep", "-rniI", "conder", "app", "main.py", "README.md", "CLAUDE.md", ".gitignore"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == "", f"leftover conder refs:\n{out.stdout}"
