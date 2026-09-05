"""판독 페이지(단계 2) 계약.

컨트롤 행 · 비교 layer Flyout · 판독대 칸 수/최소 높이 · 필름스트립 지연 로드를 못 박는다.
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
from app.ui import theme  # noqa: E402
from app.ui.compare_grid import columns_for  # noqa: E402
from app.ui.controls import SideBar, split_depth  # noqa: E402
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


# ---------------------------------------------------------------- 컨트롤 행
def test_control_row_is_one_fixed_height_row(win):
    """시안: 조건 행 44, 안의 브레드크럼 항목 28. 판독 중에 조건이 화면을 차지하지 않아야 한다."""
    top = win.top
    assert top.height() == theme.HEADER_ROW_PX == 44
    for widget in (top.btn_open, top.cmb_base, top.spn_tol, top.btn_compare, top.btn_nomatch):
        assert widget.height() == 28


def test_settings_and_export_buttons_left_the_control_row(win):
    """설정·업데이트·Excel 출력은 nav 라우트로 옮겼다. 행에는 남지 않는다."""
    assert win.top.btn_settings is None
    assert win.top.btn_update is None
    assert win.top.btn_export is None


def test_add_export_button_lives_in_the_bottom_bar(win):
    """＋ 출력에 담기는 하단 바(112) 오른쪽 끝의 주요 액션이다(시안)."""
    assert win.btn_add_export is win.nav.btn_add_export
    assert "담기" in win.btn_add_export.text()
    assert win.nav.height() == theme.BOTTOM_BAR_PX == 112


def test_lot_name_is_the_open_button(win):
    """LOT 이름 자체가 버튼이다. 누르면 다른 LOT 을 고른다."""
    win.top.set_lot_name("204. DEVAINT.226 (PKG)")
    assert win.top.btn_open.text() == "204. DEVAINT.226 (PKG)"
    win.top.set_lot_name("")
    assert win.top.btn_open.text() == "LOT 폴더"


def test_status_text_moved_into_the_control_row(win):
    """스캔·업데이트 상태 문구는 조건 행 오른쪽에 있다(옛 탐색 바에서 이동)."""
    win.top.set_status("스캔 중...")
    assert win.top.lbl_status.text() == "스캔 중..."


def test_nomatch_jump_button_reaches_the_same_handler(win):
    """미매칭 점프는 U 단축키와 같은 자리로 간다."""
    win._goto(0)
    seen = []
    win.top.nomatch_requested.connect(lambda: seen.append(True))
    win.top.btn_nomatch.click()
    for _ in range(3):
        QCoreApplication.processEvents()
    assert seen


# ---------------------------------------------------------------- 비교 layer
def test_depth_split_groups_by_canonical():
    """표시 이름의 재리뷰 깊이는 이름이 아니라 칩으로 뗀다."""
    assert split_depth("LYA4") == ("LYA4", "")
    assert split_depth("LYA4_재리뷰") == ("LYA4", "재리뷰")
    assert split_depth("LYA4_재재리뷰") == ("LYA4", "재재리뷰")


def test_compare_checks_keep_the_layer_name_contract(app):
    """행 라벨은 canonical 이지만 text() 는 계속 layer 이름이다(배선 계약)."""
    sb = SideBar()
    sb.set_layers(["LYA4", "LYA4_재리뷰"], base=None, compares=[], rereview=None)
    names = [c.text() for c in sb._compare_checks]
    assert names == ["LYA4", "LYA4_재리뷰"]


def test_compare_button_shows_the_selected_count(app):
    sb = SideBar()
    assert sb.btn_compare.text() == "layer"
    assert not sb.btn_compare.isEnabled()
    sb.set_layers(["LYA4", "LYB4", "LYB3"], base="LYA4", compares=["LYB4", "LYB3"])
    assert sb.btn_compare.text() == "2 layer"
    assert sb.btn_compare.isEnabled()
    sb._set_all_compares(False)
    assert sb.btn_compare.text() == "0 layer"


def test_compare_flyout_view_is_hidden_until_opened(app):
    """Flyout 뷰가 그냥 보이면 컨트롤 행 위에 겹쳐 그려진다."""
    sb = SideBar()
    assert not sb.compare_view.isVisible()


def test_cluster_radius_moved_into_the_flyout(app):
    """클러스터 길이는 판독 중 만지는 값이 아니라 비교 조건이다."""
    sb = SideBar()
    assert sb.spn_cluster is sb.compare_view.spn_cluster
    sb.set_cluster_radius(42.0)
    assert sb.cluster_radius() == 42.0


# ---------------------------------------------------------------- 판독대
@pytest.mark.parametrize("cells", [1, 4, 5, 9, 10, 12])
def test_reading_well_column_rule(cells):
    """시안: 기준이 왼쪽 절반을 쓰므로 비교 카드는 칸 수와 무관하게 2열이다."""
    assert columns_for(cells) == 2


def test_twelve_cells_keep_the_minimum_reading_height(win):
    """게이트: 12칸이어도 칸 높이가 224px 밑으로 내려가지 않는다."""
    from app import layout

    layers = ["LYA4", "LYB4", "LYA3", "LYB3", "LYA2", "LYB2",
              "LYA1", "LYB1", "LYC1", "LYC2", "LYD1", "FS"]
    win.resize(1464, 940)
    win.grid.build_layout(layout.build_grid(layers), "LYA4")
    for _ in range(5):
        QCoreApplication.processEvents()
    assert len(win.grid._cells) == 12
    assert min(c.height() for c in win.grid._cells.values()) >= theme.WELL_MIN_PX


def test_base_card_is_one_persistent_widget(win):
    """기준 칸은 하나를 계속 쓴다. 기준 layer 가 바뀌어도 SLOT·die 링크 객체가 같다."""
    from app import layout

    link = win.grid.base_cell.die_link
    win.grid.build_layout(layout.build_grid(["LYA4", "LYB4"]), "LYB4")
    assert win.grid.base_cell.die_link is link
    assert win.grid._cells["LYB4"] is win.grid.base_cell
    assert win.grid.base_cell.title.text() == "LYB4"


def test_unmatched_cells_stay_with_a_reason(win):
    """AD1: 앱 판독대는 사유를 남긴다(회색 1단은 Excel 전용)."""
    win.top.spn_tol.setValue(1.0)
    win._rematch(rebuild_grid=True)
    for _ in range(20):
        QCoreApplication.processEvents()
    win._goto(0)
    for _ in range(10):
        QCoreApplication.processEvents()
    unmatched = [c for name, c in win.grid._cells.items() if name != "LYA4"]
    assert unmatched
    assert any("매치 없음" in c.image.text() for c in unmatched)
    assert any("허용오차" in c.image.text() for c in unmatched)


# ---------------------------------------------------------------- 필름스트립
def test_filmstrip_loads_only_what_is_on_screen(win):
    """599장짜리 LOT 을 스크롤 전에 전부 읽으면 안 된다."""
    strip = win.strip
    strip.set_items([f"{i}" for i in range(200)])
    for _ in range(5):
        QCoreApplication.processEvents()
    for i in range(200):
        strip.set_thumbnail(i, "")  # 경로만 등록(빈 경로는 물음표로 그려진다)
    strip.resize(600, 84)
    for _ in range(5):
        QCoreApplication.processEvents()
    strip.load_visible()
    loaded = [t for t in strip._thumbs if t.is_loaded()]
    assert 0 < len(loaded) < 200


def test_filmstrip_keeps_vertical_wheel_to_horizontal_scroll(win):
    """세로휠 -> 가로 스크롤은 계승 필수 항목이다."""
    assert hasattr(win.strip, "wheelEvent")
    assert win.strip.verticalScrollBarPolicy().name.startswith("ScrollBarAlwaysOff")


def test_filmstrip_marks_photos_that_are_in_the_tray(win):
    """시안: 출력 명세에 담긴 사진은 필름스트립 카드 좌상단에 '담김' 표식이 붙는다."""
    win._goto(0)
    win._add_current_to_export()
    for _ in range(3):
        QCoreApplication.processEvents()
    assert not win.strip._thumbs[0].tray_mark.isHidden()
    assert win.strip._thumbs[1].tray_mark.isHidden()
    assert win.btn_add_export.text().startswith("✓ 담김")
    win._goto(1)
    assert win.btn_add_export.text().startswith("＋ 출력에 담기")


# ---------------------------------------------------------------- 기준 카드 머리
def test_die_link_is_the_way_back_to_the_heatmap(app):
    """A12: 기준 카드 머리의 SLOT·die 를 누르면 히트맵으로 간다.

    창 배선(모달 히트맵)을 타지 않도록 판독대만 세워 신호를 확인한다.
    """
    from app.ui.compare_grid import CompareGrid

    grid = CompareGrid()
    link = grid.base_cell.die_link
    grid.set_die("")
    assert link.isHidden() or link.text() == ""
    grid.set_die("wafer 03 · die (3, 3)")
    assert link.text() == "wafer 03 · die (3, 3)"
    seen = []
    grid.die_clicked.connect(lambda: seen.append(True))
    link.click()
    for _ in range(3):
        QCoreApplication.processEvents()
    assert seen


def test_empty_state_lists_recent_lots(win, tmp_path):
    """빈 상태는 최근 LOT 을 목록으로 보여 준다(버튼 하나가 아니라)."""
    lot = tmp_path / "src"
    win._push_recent(str(lot))
    empty = win.review_page.empty_state
    assert empty.recent_folders()[0] == str(lot)
    seen = []
    empty.recent_chosen.connect(seen.append)
    empty._rows[0].click()
    for _ in range(3):
        QCoreApplication.processEvents()
    assert seen == [str(lot)]
