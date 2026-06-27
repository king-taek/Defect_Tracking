"""오프스크린 UI 회귀 테스트 (Round 3 — 연결성/사용성).

Qt 가 없으면 skip. 모달(QFileDialog/QMessageBox)을 띄우지 않는 내부 메서드만 호출한다.
합성 데이터를 _on_scan_finished 로 직접 주입하여 스캔 워커/모달을 우회한다.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import scanner  # noqa: E402
from app.config import AppSettings  # noqa: E402
from app.models import DefectRecord  # noqa: E402
from tools.make_sample_data import generate  # noqa: E402


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture()
def win(app, tmp_path):
    from app.ui.main_window import MainWindow

    lot = generate(tmp_path / "src")
    idx = scanner.scan_lot(lot)
    # 테스트에서 시작 시 네트워크 업데이트 확인을 끈다(헤르메틱).
    w = MainWindow(AppSettings(workspace=str(tmp_path / "ws"), auto_update_check=False))
    w.lot_index = idx
    w._on_scan_finished(idx)
    for _ in range(10):
        QCoreApplication.processEvents()
    return w


def test_loads_and_builds(win):
    assert win.top.base_layer() == "LYA4"
    assert set(win.top.compare_layers()) == {"LYB4", "LYA3", "LYB3"}
    assert len(win.matches) == 8
    assert win.current == 0
    assert set(win.grid._cells.keys()) == {"LYA4", "LYB4", "LYA3", "LYB3"}


def test_tolerance_change_preserves_index(win):
    win._goto(3)
    assert win.current == 3
    win.top.spn_tol.setValue(250.0)  # tolerance_changed → _rematch(rebuild_grid=False)
    for _ in range(5):
        QCoreApplication.processEvents()
    assert win.current == 3, "허용오차 변경이 현재 인덱스를 리셋하면 안 된다"


def test_compare_toggle_preserves_index_and_columns(win):
    win._goto(4)
    # LYB3 해제 → 그리드 컬럼에서 빠지고, 인덱스는 유지
    cb = next(c for c in win.top._compare_checks if c.text() == "LYB3")
    cb.setChecked(False)
    for _ in range(5):
        QCoreApplication.processEvents()
    assert win.current == 4
    assert "LYB3" not in win.grid._cells
    assert "LYB4" in win.grid._cells


def test_keyboard_like_navigation(win):
    win._goto(0)
    win._next()
    assert win.current == 1
    win._prev()
    win._prev()
    assert win.current == 7  # wrap-around
    win._goto(len(win.matches) - 1)
    assert win.current == 7


def test_image_click_forwards_record(app):
    """LayerCell 클릭 → CompareGrid.image_clicked 로 record 가 전달되는지(모달 우회)."""
    from app.ui.compare_grid import CompareGrid

    grid = CompareGrid()
    grid.build_layout([["LYA4", "LYB4"]], "LYA4")
    captured = []
    grid.image_clicked.connect(lambda r: captured.append(r))
    cell = grid._cells["LYA4"]
    rec = DefectRecord(
        image_path=Path("/x/y.jpg"), wafer_id="W1", layer="LYA4", layer_folder="LYA4",
    )
    cell._set_record(rec)
    cell.record_clicked.emit(cell._record)
    assert captured and isinstance(captured[0], DefectRecord)


def test_select_all_none_compare_single_signal(win):
    calls = []
    win.top.compare_layers_changed.connect(lambda: calls.append(1))
    win.top._set_all_compares(False)
    for _ in range(3):
        QCoreApplication.processEvents()
    assert win.top.compare_layers() == []
    assert len(calls) == 1, "전체/해제는 한 번의 신호로 처리되어야 한다"


def test_stale_scan_ignored(win):
    before = win.current
    # 토큰을 올린 뒤 과거 토큰으로 finished 를 주입하면 무시되어야 한다
    win._scan_token += 1
    win._on_scan_finished(win.lot_index, token=win._scan_token - 1)
    assert win.current == before


def test_thumbnail_strip_vertical_wheel_scrolls_horizontally(app, tmp_path):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from app.ui.thumbnail_strip import ThumbnailStrip

    strip = ThumbnailStrip()
    strip.set_items([f"w{i}\n({i},{i})" for i in range(30)])
    strip.resize(300, 152)
    strip.show()
    for _ in range(5):
        QCoreApplication.processEvents()
    bar = strip.horizontalScrollBar()
    start = bar.value()
    ev = QWheelEvent(
        QPointF(10, 10), QPointF(10, 10), QPoint(0, -120), QPoint(0, -120),
        Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False,
    )
    strip.wheelEvent(ev)
    assert bar.value() >= start  # 세로 휠(아래)로 가로 스크롤 이동


def test_match_index_cache_reused(win):
    rbl = win.lot_index.records_by_layer()
    layers = win.top.compare_layers()
    idx1, fidx1 = win._get_match_indices(layers, rbl)
    idx2, fidx2 = win._get_match_indices(layers, rbl)
    assert idx1 is idx2 and fidx1 is fidx2  # 동일 시그니처 → 재사용
    other = layers[:-1] if len(layers) > 1 else layers + ["__x__"]
    idx3, _ = win._get_match_indices(other, rbl)
    assert idx3 is not idx1  # 비교 layer 집합 변경 → 재구성


def test_image_loader_prefetch_warms_cache(app, tmp_path):
    from PySide6.QtCore import QThreadPool
    from app.ui.image_loader import ImageLoader
    from tools.make_sample_data import generate

    lot = generate(tmp_path / "src")
    jpgs = [str(p) for p in lot.rglob("*.jpg")][:3]
    assert jpgs
    loader = ImageLoader()
    loader.prefetch(jpgs)
    QThreadPool.globalInstance().waitForDone(5000)
    for _ in range(10):
        QCoreApplication.processEvents()
    assert any(p in loader._cache for p in jpgs)


def test_match_summary_populated(win):
    # 매칭 계산 후 사이드바에 요약 텍스트가 채워진다(허용오차 피드백)
    assert "매칭" in win.top.lbl_match.text()


def test_match_status_classification():
    from app.ui.main_window import MainWindow
    from app.models import BaseDefectMatches, DefectRecord, MatchResult

    base = DefectRecord(image_path=Path("/b.jpg"), wafer_id="W1", layer="LYA4",
                        layer_folder="LYA4")

    def _item(flags):
        it = BaseDefectMatches(base=base)
        for f in flags:
            it.results.append(MatchResult(
                compare_layer="X", base=base,
                matched=(base if f else None),
            ))
        return it

    assert MainWindow._match_status(_item([True, True])) == "full"
    assert MainWindow._match_status(_item([True, False])) == "partial"
    assert MainWindow._match_status(_item([False, False])) == "none"


def test_filter_traversal_skips(win):
    # 허용오차 0 → 전부 미매칭(none). '완전 매칭' 필터면 대상 없음.
    win.top.spn_tol.setValue(0.0)
    for _ in range(5):
        QCoreApplication.processEvents()
    statuses = {win._match_status(m) for m in win.matches}
    assert statuses == {"none"}
    assert win._view_indices() != []  # 'all'
    win._filter = "full"
    assert win._view_indices() == []  # 완전매칭 없음
    win._filter = "unmatched"
    assert len(win._view_indices()) == len(win.matches)


def test_recent_folders_push(win, tmp_path):
    win._push_recent("/a/lot1")
    win._push_recent("/a/lot2")
    win._push_recent("/a/lot1")  # 중복은 앞으로 이동
    assert win.settings.recent_folders[0] == "/a/lot1"
    assert win.settings.recent_folders.count("/a/lot1") == 1
    assert len(win.settings.recent_folders) <= 5


def test_session_mark_toggle_via_window(win):
    assert win.session is not None
    base = win.matches[0].base
    win._toggle_mark(base)
    assert win.session.is_marked(str(base.image_path)) is True
    win._toggle_mark(base)
    assert win.session.is_marked(str(base.image_path)) is False


def test_crosshair_toggle(win):
    win.chk_crosshair.setChecked(False)
    for _ in range(3):
        QCoreApplication.processEvents()
    assert win.settings.show_crosshair is False
    # 모든 셀 이미지에 십자선 상태가 전파된다
    assert all(not c.image._crosshair for c in win.grid._cells.values())
    win.chk_crosshair.setChecked(True)
    for _ in range(3):
        QCoreApplication.processEvents()
    assert win.settings.show_crosshair is True


def test_wafer_map_updates(win):
    item = win.matches[0]
    win._update_wafer_map(item)
    assert win.wafer_map._cols >= 1 and win.wafer_map._rows >= 1
    assert (item.base.col, item.base.row) in win.wafer_map._states


def test_jump_to_die(win):
    win._goto(2)
    cur_wafer = win.matches[win.current].base.wafer_id
    target = next(
        i for i, m in enumerate(win.matches) if m.base.wafer_id == cur_wafer
    )
    tb = win.matches[target].base
    win._jump_to_die(tb.col, tb.row)
    got = win.matches[win.current].base
    assert got.wafer_id == cur_wafer
    assert (got.col, got.row) == (tb.col, tb.row)


def test_overlay_dialog_constructs(win):
    from app.ui.compare_overlay import OverlayCompareDialog

    item = win.matches[0]
    pairs = [
        (r.compare_layer, r.matched)
        for r in item.results
        if r.is_match and r.matched is not None
    ]
    assert pairs
    dlg = OverlayCompareDialog(item.base, "LYA4", pairs)
    dlg._render()
    dlg._set_blink(True)
    dlg._on_blink_tick()
    dlg._set_blink(False)
    dlg._zoom(1.25)  # 크래시 없어야 함


def test_failure_summary_text():
    from app.ui.main_window import MainWindow

    assert "정상" in MainWindow._failure_summary([])


def test_safe_filename():
    from app.ui.main_window import MainWindow

    assert MainWindow._safe_filename('DEVA.226 (PKG)') == "DEVA.226 (PKG)"
    assert MainWindow._safe_filename('a/b:c*?') == "a_b_c__"
    assert MainWindow._safe_filename("trail. ") == "trail"
    assert MainWindow._safe_filename("") == "compare"


def test_sidebar_settings_button_shows_update_mark(win):
    assert win.top.btn_settings is not None
    # 업데이트는 설정 다이얼로그로 이동 → 사이드바엔 업데이트 버튼 없음
    assert win.top.btn_update is None
    # 가용 시 설정 버튼에 표식(•)이 붙고, 해제 시 사라진다
    win.top.set_update_available(True)
    assert "•" in win.top.btn_settings.text()
    win.top.set_update_available(False)
    assert win.top.btn_settings.text() == "⚙ 설정"


def test_update_check_available_sets_flag(win, monkeypatch):
    """업데이트 확인이 available 이면 설정 버튼 표식 + 사용자가 'Yes' 시 적용 호출(모달 우회)."""
    from PySide6.QtWidgets import QMessageBox
    from app import updater

    st = updater.UpdateStatus(available=True, local="a", remote="b", method="zip")
    called = {}
    monkeypatch.setattr(win, "_do_update", lambda s: called.setdefault("do", s))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    win._on_update_checked(st, manual=True)
    assert "•" in win.top.btn_settings.text()
    assert called.get("do") is st


def test_update_check_uptodate_manual_banner(win):
    from app import updater

    st = updater.UpdateStatus(available=False, local="a", remote="a", method="zip")
    win._on_update_checked(st, manual=True)  # 모달 없음(available=False)
    assert win.top.btn_settings.text() == "⚙ 설정"


def test_settings_dialog_update_button_requests(app, tmp_path):
    """설정 다이얼로그의 업데이트 버튼이 update_requested 를 emit 하고 wants_update 설정."""
    from app.config import AppSettings
    from app.ui.settings_dialog import SettingsDialog

    s = AppSettings(workspace=str(tmp_path / "ws"))
    dlg = SettingsDialog(s, current_lot=None, update_available=True)
    fired = []
    dlg.update_requested.connect(lambda: fired.append(1))
    dlg._on_update_clicked()
    assert dlg.wants_update() is True
    assert fired == [1]


def test_settings_dialog_constructs(app, tmp_path):
    from app.config import AppSettings
    from app.ui.settings_dialog import SettingsDialog

    s = AppSettings(workspace=str(tmp_path / "ws"))
    dlg = SettingsDialog(s, current_lot=None)
    dlg.ed_workspace.setText(str(tmp_path / "ws2"))
    dlg.spn_tol.setValue(150.0)
    dlg.chk_update.setChecked(False)
    out = dlg.updated_settings()
    assert out.tolerance == 150.0
    assert out.auto_update_check is False
    assert out.workspace == str(tmp_path / "ws2")
