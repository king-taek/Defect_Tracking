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
    # 기준 layer 는 빈칸으로 시작하므로, 테스트는 사용자가 LYA4 를 고른 상태를 시뮬레이션한다.
    w.top.cmb_base.setCurrentText("LYA4")
    for _ in range(10):
        QCoreApplication.processEvents()
    return w


def test_loads_and_builds(win):
    assert win.top.base_layer() == "LYA4"
    # 기본 비교 선택은 '_재리뷰' layer 우선(샘플의 LYA4/LYB4 가 재리뷰).
    # 기준 LYA4 를 제외하면 비교는 LYB4 하나.
    assert set(win.top.compare_layers()) == {"LYB4"}
    assert len(win.matches) == 8
    assert win.current == 0
    assert set(win.grid._cells.keys()) == {"LYA4", "LYB4"}


def test_tolerance_change_preserves_index(win):
    win._goto(3)
    assert win.current == 3
    win.top.spn_tol.setValue(250.0)  # tolerance_changed → _rematch(rebuild_grid=False)
    for _ in range(5):
        QCoreApplication.processEvents()
    assert win.current == 3, "허용오차 변경이 현재 인덱스를 리셋하면 안 된다"


def test_set_layers_rereview_default(app):
    from app.ui.controls import SideBar

    sb = SideBar()
    # 재리뷰(LYA4,LYB4)만 기본 체크, 기준 LYA3 제외 → 비교 = {LYA4, LYB4}
    sb.set_layers(["LYA4", "LYB4", "LYA3", "LYB3"], base="LYA3", rereview={"LYA4", "LYB4"})
    assert set(sb.compare_layers()) == {"LYA4", "LYB4"}
    # 재리뷰 layer 가 전혀 없으면 막다른 화면 방지를 위해 전체를 기본 체크(폴백).
    sb.set_layers(["A", "B", "C"], base="A", rereview=set())
    assert set(sb.compare_layers()) == {"B", "C"}


def test_rereview_button_selects_deepest(app):
    from app.ui.controls import SideBar

    sb = SideBar()
    # 재리뷰/재재리뷰 혼재 → 선호 집합(재재리뷰 우선)만 버튼이 선택
    layers = ["LYA4", "LYA4_재리뷰", "LYA4_재재리뷰", "LYB4_재리뷰"]
    preferred = {"LYA4_재재리뷰", "LYB4_재리뷰"}
    sb.set_layers(layers, base=None, compares=[], rereview=preferred)
    assert set(sb.compare_layers()) == set()  # compares=[] → 아무것도 선택 안 함
    sb._set_rereview_compares()
    assert set(sb.compare_layers()) == preferred
    assert sb.btn_rereview.isEnabled()


def test_base_layer_checkbox_preserved(win):
    """기준으로 고른 layer 는 비교 목록에서 체크 유지(비활성)되고, 비교에서만 제외된다."""
    top = win.top
    rd = next(c for c in top._compare_checks if c.text() == "LYA4")
    assert rd.isChecked() and not rd.isEnabled()  # 체크 유지 + 비활성
    assert "LYA4" not in top.compare_layers()
    # 기준을 LYB4 로 바꾸면 LYA4 는 활성+체크 → 비교 복귀, LYB4 는 제외
    top.cmb_base.setCurrentText("LYB4")
    for _ in range(3):
        QCoreApplication.processEvents()
    assert rd.isEnabled() and rd.isChecked()
    cmps = top.compare_layers()
    assert "LYA4" in cmps and "LYB4" not in cmps


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

    assert MainWindow._match_status(_item([True, True])) == "matched"
    assert MainWindow._match_status(_item([True, False])) == "matched"
    assert MainWindow._match_status(_item([False, False])) == "none"


def _set_filter(win, mode):
    """필터를 바꾸고 보기 캐시를 무효화(직접 _filter 설정 시)."""
    win._filter = mode
    win._view_cache = None


def test_filter_traversal_skips(win):
    from PySide6.QtTest import QTest
    # 허용오차 0 → 전부 미매칭(none). 매칭은 디바운스(250ms)+백그라운드 → 조건까지 폴링 대기.
    win.top.spn_tol.setValue(0.0)
    for _ in range(30):
        QTest.qWait(100)
        if win.matches and {win._match_status(m) for m in win.matches} == {"none"}:
            break
    statuses = {win._match_status(m) for m in win.matches}
    assert statuses == {"none"}
    # 기본 '매칭만' 필터: 모든 후보가 none 이면 빈 화면 대신 전체를 보인다(혼란 방지).
    _set_filter(win, "matched")
    assert len(win._view_indices()) == len(win.matches)
    _set_filter(win, "all")
    assert win._view_indices() != []


def test_matched_filter_excludes_unmatched(win):
    # '매칭만' 필터는 매칭 0(none)인 기준을 후보에서 제외한다(일부는 매칭되게 큰 허용오차).
    win.top.spn_tol.setValue(100000.0)
    for _ in range(5):
        QCoreApplication.processEvents()
    statuses = [win._match_status(m) for m in win.matches]
    _set_filter(win, "matched")
    view = win._view_indices()
    # none 인 기준은 모두 빠지고, 그 외(full/partial)는 모두 포함된다.
    assert all(statuses[i] != "none" for i in view)
    non_none = [i for i, s in enumerate(statuses) if s != "none"]
    if non_none:  # 매칭이 하나라도 있으면 제외 의미 성립
        assert view == non_none


def test_no_nomatch_button(win):
    # '미매칭 n' 버튼은 제거됨(항목 9).
    assert not hasattr(win, "btn_nomatch")


def test_base_change_keeps_exclusion(win):
    # item 7: 기준 layer 를 바꿔도 매칭 0(none)인 후보는 계속 제외된다.
    win.top.spn_tol.setValue(0.0)
    for _ in range(5):
        QCoreApplication.processEvents()
    # 다른 layer 로 기준 변경(샘플에 존재하는 layer 중 현재와 다른 것)
    layers = win.lot_index.layer_canonicals()
    other = next((l for l in layers if l != win.top.base_layer()), None)
    if other is not None:
        win.top.cmb_base.setCurrentText(other)
        for _ in range(5):
            QCoreApplication.processEvents()
    none_idx = {i for i, m in enumerate(win.matches) if win._match_status(m) == "none"}
    # 기본 '매칭만' 필터에서 none 후보는 보기(탐색 후보)에 포함되지 않는다
    # (단, 전부 none 이면 혼란 방지 폴백으로 전체 표시 — 그 경우는 제외 검사를 건너뜀)
    view = set(win._view_indices())
    if len(none_idx) < len(win.matches):
        assert none_idx.isdisjoint(view)


def test_recent_folders_push(win, tmp_path):
    win._push_recent("/a/lot1")
    win._push_recent("/a/lot2")
    win._push_recent("/a/lot1")  # 중복은 앞으로 이동
    assert win.settings.recent_folders[0] == "/a/lot1"
    assert win.settings.recent_folders.count("/a/lot1") == 1
    assert len(win.settings.recent_folders) <= 5


def test_wafer_map_updates(win):
    item = win.matches[0]
    win._update_wafer_map(item)
    assert win.wafer_map._cols >= 1 and win.wafer_map._rows >= 1
    assert (item.base.col, item.base.row) in win.wafer_map._states


def test_wafer_map_paints_observed_die_outside_device_shape(win):
    """DB die_map 밖이어도 실제 관측(매칭)된 die 는 그려져야 한다(회귀).

    device_db 기반 제품의 die_map 이 실제 관측 die 범위를 다 담지 못하면(예:
    zeroX/zeroY 실측 계산으로 col/row 범위가 넓어진 경우), 정합은 성공하되
    관측 die 하나가 die_map 밖에 남을 수 있다 — 이 die 도 지워지지 않고 그려져야 한다.
    """
    from app import config

    item = win.matches[0]
    wafer = item.base.wafer_id
    observed = {
        (m.base.col, m.base.row)
        for m in win.matches
        if m.base.wafer_id == wafer and m.base.col is not None and m.base.row is not None
    }
    assert len(observed) >= 2, "샘플 데이터에 wafer 당 die 가 2개 이상 있어야 테스트 가능"
    missing = sorted(observed)[0]
    partial_die_map = frozenset(observed - {missing})  # 관측 die 중 하나를 뺀 DB 모양

    prod = config.active_product()
    config.PRODUCTS["TESTDEV_PARTIAL"] = config.ProductConfig(
        key="TESTDEV_PARTIAL", name="Test Partial Device",
        camtek_pitch_x=prod.camtek_pitch_x, camtek_pitch_y=prod.camtek_pitch_y,
        kla_package_x_count=prod.kla_package_x_count,
        kla_package_y_count=prod.kla_package_y_count,
        die_map=partial_die_map, source="db",
    )
    try:
        config.set_active_product("TESTDEV_PARTIAL")
        win._align_cache.clear()
        win._update_wafer_map(item)
        # 정합이 성공해 die_map 클리핑이 실제로 적용되는 시나리오인지 확인.
        assert win.wafer_map._valid is not None
        # 수정 전에는 missing die 가 valid 밖이라 그려지지 않았을 것 — 이제는 포함돼야 한다.
        assert missing in win.wafer_map._valid
        assert missing in win.wafer_map._states
    finally:
        config.set_active_product(prod.key)
        config.PRODUCTS.pop("TESTDEV_PARTIAL", None)
        win._align_cache.clear()


def test_wafer_map_refreshes_immediately_on_product_switch(win, monkeypatch):
    """설정에서 제품을 바꾸면 다음 네비게이션을 기다리지 않고 바로 다시 그려야 한다."""
    from app import config
    from app.config import ProductConfig
    from app.ui.settings_dialog import SettingsDialog

    prod = config.active_product()
    other_key = "TESTDEV_SWITCH"
    config.PRODUCTS[other_key] = ProductConfig(
        key=other_key, name="Test Switch Device",
        camtek_pitch_x=prod.camtek_pitch_x, camtek_pitch_y=prod.camtek_pitch_y,
        kla_package_x_count=prod.kla_package_x_count + 3,
        kla_package_y_count=prod.kla_package_y_count + 3,
    )
    try:
        before_cols = win.wafer_map._cols
        # 다이얼로그가 새 제품으로 초기화되도록 미리 설정한 뒤, 모달을 띄우지 않고
        # 바로 accept 된 것처럼 흉내 낸다(exec() monkeypatch — 실제 _open_settings() 호출).
        win.settings.product = other_key
        monkeypatch.setattr(SettingsDialog, "exec", lambda self: True)
        win._open_settings()
        assert config.active_product().key == other_key
        # 더 큰 package 크기를 쓰는 제품으로 바꿨으니 격자가 즉시(다음 네비게이션 전에) 커져야 한다.
        assert win.wafer_map._cols >= before_cols + 3
    finally:
        config.set_active_product(prod.key)
        config.PRODUCTS.pop(other_key, None)
        win._align_cache.clear()
        win._goto(win.current)


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


def test_help_dialog_constructs(app):
    from app.ui.help_dialog import ShortcutsDialog

    dlg = ShortcutsDialog()
    assert dlg.windowTitle() == "도움말"


def test_open_folder_classifies(win, tmp_path, monkeypatch):
    # layer 폴더를 고르면 자재 폴더로 자동 보정해 load_lot 호출
    img = tmp_path / "MAT" / "LAYER" / "WAFER" / "a.jpg"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"\xff\xd8\xff\xd9")
    called = {}
    monkeypatch.setattr(win, "load_lot", lambda f: called.setdefault("folder", f))
    win._open_folder(str(tmp_path / "MAT" / "LAYER"))
    assert called.get("folder") == str(tmp_path / "MAT")


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
    dlg.chk_update.setChecked(False)
    out = dlg.updated_settings()
    # 기준 오차는 설정에서 제거됨(사이드바에서만 조절).
    assert not hasattr(dlg, "spn_tol")
    assert out.auto_update_check is False
    assert out.workspace == str(tmp_path / "ws2")


def test_settings_dialog_dev_mode_toggle(app, tmp_path):
    """개발자 모드 토글(작은 버튼)이 dev 섹션을 표시/숨기고 설정에 저장된다."""
    from app import config
    from app.config import AppSettings
    from app.ui.settings_dialog import SettingsDialog

    s = AppSettings(workspace=str(tmp_path / "ws"), dev_mode=False)
    dlg = SettingsDialog(s, current_lot=None)
    # 기본 꺼짐: 버튼 라벨 '꺼짐', dev 섹션(로그 경로·로그 폴더) 숨김.
    assert dlg.btn_dev.text() == "꺼짐"
    assert dlg.btn_dev.isChecked() is False
    assert dlg._dev_box.isHidden()
    # 켜면 섹션이 보이고 라벨이 '켜짐'.
    dlg.btn_dev.setChecked(True)
    assert dlg.btn_dev.text() == "켜짐"
    assert not dlg._dev_box.isHidden()
    # 저장 시 settings.dev_mode 반영 → config.dev_mode 가 True.
    out = dlg.updated_settings()
    assert out.dev_mode is True
    assert config.dev_mode(out) is True
    # 다시 끄면 False 로 저장.
    dlg.btn_dev.setChecked(False)
    assert dlg.updated_settings().dev_mode is False


def test_settings_dialog_cluster_radius(app, tmp_path):
    """defect 클러스터 거리 스핀박스가 설정을 읽고/쓴다."""
    from app.config import AppSettings
    from app.ui.settings_dialog import SettingsDialog

    s = AppSettings(workspace=str(tmp_path / "ws"), cluster_radius=42.0)
    dlg = SettingsDialog(s, current_lot=None)
    assert dlg.spn_cluster.value() == 42.0
    dlg.spn_cluster.setValue(75.0)
    assert dlg.updated_settings().cluster_radius == 75.0


def test_stop_scan_hides_progress(win):
    # 스캔 진행 상태를 흉내내고 _stop_scan 이 진행바/버튼을 숨기고 토큰을 올리는지
    win.progress.setVisible(True)
    win.btn_stop.setVisible(True)
    tok = win._scan_token
    win._stop_scan()
    assert not win.btn_stop.isVisible()
    assert not win.progress.isVisible()
    assert win._scan_token == tok + 1
    assert win._scan_worker is None


def test_show_initial_maximizes(app, tmp_path):
    from app.ui.main_window import MainWindow

    w = MainWindow(AppSettings(workspace=str(tmp_path / "ws"), auto_update_check=False,
                               window_maximized=True))
    w.show_initial()
    for _ in range(5):
        QCoreApplication.processEvents()
    assert w.isMaximized()
    # closeEvent 가 최대화 상태를 저장한다
    from PySide6.QtGui import QCloseEvent
    w.closeEvent(QCloseEvent())
    assert w.settings.window_maximized is True
    w.close()
