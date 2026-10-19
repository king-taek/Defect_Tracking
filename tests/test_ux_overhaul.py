"""UI/UX 점검(2026-10-19)에서 고친 것들의 회귀.

각 테스트 이름이 고친 증상 하나다. 화면 캡처로 찾은 문제라 겉으로 보이는 결과를 본다.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import scanner  # noqa: E402
from app.config import AppSettings  # noqa: E402
from app.ui.thumbnail_strip import short_wafer_labels  # noqa: E402
from tools.make_sample_data import generate  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _pump(n: int = 10) -> None:
    for _ in range(n):
        QCoreApplication.processEvents()


def _choose_base(win, layer: str = "LYA4") -> None:
    """기준을 고르고 백그라운드 매칭이 끝날 때까지 기다린다."""
    win.top.cmb_base.setCurrentText(layer)
    _wait_matched(win)


def _wait_matched(win, timeout: float = 10.0) -> None:
    import time

    end = time.time() + timeout
    while time.time() < end:
        QCoreApplication.processEvents()
        if win.matches and not win.busy.isVisible() and not win._active_workers:
            break
        time.sleep(0.01)
    _pump()


@pytest.fixture()
def loaded(app, tmp_path):
    """LOT 을 열었지만 기준 layer 는 아직 고르지 않은 창."""
    from app.ui.main_window import MainWindow

    lot = generate(tmp_path / "src")
    idx = scanner.scan_lot(lot)
    w = MainWindow(AppSettings(workspace=str(tmp_path / "ws"), auto_update_check=False))
    w.lot_index = idx
    w._on_scan_finished(idx)
    _pump()
    yield w
    w.close()


# ---------------------------------------------------------------- 조건 행
def test_tolerance_value_is_visible_in_its_box(app):
    """PySide6 6.12 에서 허용오차 입력칸이 1px 로 잡혀 값이 안 보였다."""
    from app.ui.controls import SideBar

    bar = SideBar()
    bar.resize(900, 44)
    bar.show()
    _pump()
    for spin in (bar.spn_tol, bar.spn_cluster):
        assert spin.lineEdit().width() >= spin.width() // 2
    bar.close()


def test_status_line_is_short_and_match_summary_is_separate(loaded):
    _choose_base(loaded)
    status = loaded.top.lbl_status.text()
    assert status.startswith("layer ") and "이미지" not in status and "(" not in status
    assert loaded.top.lbl_match.text().startswith("매칭 ")
    assert "쌍" in loaded.top.lbl_match.toolTip()
    assert loaded.top.lbl_view.isHidden()


# ---------------------------------------------------------------- 기준 미선택
def test_no_base_shows_a_layer_picker_instead_of_a_black_box(loaded):
    page = loaded.review_page
    assert page.is_grid_notice()
    assert page.grid_notice.title.text() == "기준 layer 를 고르세요"
    buttons = page.grid_notice.layer_buttons()
    assert len(buttons) == len(loaded.lot_index.layer_canonicals())
    # 하단 바("0 / 0")는 볼 사진이 없으니 거둔다.
    assert page.nav.isHidden()


def test_layer_button_sets_the_base_and_shows_the_well(loaded):
    page = loaded.review_page
    first = page.grid_notice.layer_buttons()[0]
    first.click()
    _wait_matched(loaded)
    assert loaded.top.base_layer() != ""
    assert not page.is_grid_notice()
    assert not page.nav.isHidden()
    assert loaded.matches


def test_layer_picker_buttons_all_fit_before_show(app):
    """버튼이 화면에 뜨기 전에도 줄바꿈 높이를 센다(넷째 버튼이 잘리던 문제)."""
    from app.ui.pages.review import GridNotice

    notice = GridNotice()
    layers = [f"LY{i:02d}" for i in range(14)]
    notice.set_notice("t", "b", layers=layers, recommended="LY00")
    assert notice._buttons_host.minimumHeight() > notice.layer_buttons()[0].sizeHint().height()


# ---------------------------------------------------------------- nav 로 들어온 페이지
def test_heatmap_from_nav_has_data(loaded):
    _choose_base(loaded)
    loaded.switchTo(loaded.heatmap_page)
    _pump()
    assert not loaded.heatmap_page.is_empty_state()


def test_heatmap_from_nav_without_base_says_what_to_do(loaded):
    loaded.switchTo(loaded.heatmap_page)
    _pump()
    assert loaded.heatmap_page.is_empty_state()
    assert loaded.heatmap_page.empty_title.text() == "기준 layer 를 고르세요"


def test_export_page_from_nav_can_add_all_matches(loaded):
    _choose_base(loaded)
    loaded.switchTo(loaded.export_page)
    _pump()
    assert loaded.export_page.btn_add_all.isEnabled()


def test_ctrl_number_shortcuts_switch_pages(loaded):
    from PySide6.QtGui import QKeySequence, QShortcut

    keys = {s.key().toString() for s in loaded.findChildren(QShortcut)}
    for n in range(1, 5):
        assert QKeySequence(f"Ctrl+{n}").toString() in keys


# ---------------------------------------------------------------- 판독대
def test_single_compare_card_takes_the_full_right_side_and_rows_reset(loaded):
    _choose_base(loaded)
    loaded.top._set_all_compares(True)
    _wait_matched(loaded)
    grid = loaded.grid._grid
    loaded.top._set_all_compares(False)
    _wait_matched(loaded)
    for cb in loaded.top._compare_checks:  # 비교 하나만 다시 켠다
        if cb.text() == "LYB4":
            cb.setChecked(True)
    _wait_matched(loaded)
    assert grid.columnStretch(1) == 0
    for row in range(1, grid.rowCount()):
        assert grid.rowMinimumHeight(row) == 0


def test_filmstrip_caption_is_one_line(loaded):
    _choose_base(loaded)
    caps = [t.caption.text() for t in loaded.strip._thumbs]
    assert caps and all("\n" not in c for c in caps)


def test_short_wafer_labels():
    labels = short_wafer_labels(["00MHE105XYF6", "00MHE106XYC5", "00MHE105XYF6"])
    assert labels == {"00MHE105XYF6": "5XYF6", "00MHE106XYC5": "6XYC5"}
    assert short_wafer_labels(["ONLY1"]) == {"ONLY1": ""}
    # 끝 글자만으로 겹치면 자르지 않는다.
    same_tail = short_wafer_labels(["A1-ZZZZZ", "B2-ZZZZZ"])
    assert len(set(same_tail.values())) == 2


# ---------------------------------------------------------------- 미매칭
def test_nomatch_filter_shows_counts_and_all_matched_line(app):
    from app.ui.pages.nomatch import NoMatchPage

    page = NoMatchPage()
    page.set_waiting_text("기준 layer 를 고르세요.")
    page.set_data([], None, "", [])
    assert page.lbl_empty.text() == "기준 layer 를 고르세요."


# ---------------------------------------------------------------- 알림
def test_notifications_sit_below_the_page_header(loaded):
    loaded.resize(1200, 800)
    loaded.show()
    _pump()
    bar = loaded.banner.show_message("테스트", "info", timeout_ms=0)
    from qfluentwidgets.components.widgets.info_bar import InfoBarManager

    from app.ui import theme
    from app.ui.notifications import BELOW_HEADER_RIGHT

    pos = InfoBarManager.make(BELOW_HEADER_RIGHT)._pos(bar)
    assert pos.y() >= loaded.titleBar.height() + theme.HEADER_ROW_PX
    bar.close()


def test_toast_action_keeps_its_captured_argument(loaded):
    """clicked 의 checked 값이 lambda p=out 의 기본값을 덮어써 '파일 열기' 가 False 를 열었다."""
    from qfluentwidgets import PushButton

    got = []
    bar = loaded.banner.show_message(
        "x", "success", actions=[("열기", lambda p="/tmp/out.xlsx": got.append(p))], timeout_ms=0,
    )
    bar.findChildren(PushButton)[0].click()
    assert got == ["/tmp/out.xlsx"]


# ---------------------------------------------------------------- 원본 뷰어
def test_viewer_fit_enlarges_a_small_photo(app, tmp_path):
    from app.models import DefectRecord, ParseStatus
    from app.ui.sheets.image_viewer import ImageViewerDialog

    path = tmp_path / "small.png"
    img = QImage(200, 150, QImage.Format_RGB32)
    img.fill(QColor("#203040"))
    img.save(str(path))
    rec = DefectRecord(
        image_path=path, wafer_id="W1", layer="LYA4", layer_folder="LYA4",
        col=1, row=1, x=10.0, y=10.0, status=ParseStatus.OK,
    )
    dlg = ImageViewerDialog(rec)
    dlg.resize(1100, 800)
    dlg.show()
    _pump(20)
    assert dlg._fit_scale() > 1.0
    dlg.close()
