"""AOI 모드 layer 지정 시트·설정 토글·메인 창 분기(오프스크린 스모크)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
pytest.importorskip("qfluentwidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config import AppSettings  # noqa: E402
from app.scanner import AoiLayer  # noqa: E402
from app.ui.pages.settings import SettingsPage  # noqa: E402
from app.ui.sheets.aoi_layers import AoiLayersDialog, validate_layers  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_validate_layers(tmp_path):
    assert validate_layers([]) is not None
    assert "비어" in validate_layers([AoiLayer("", tmp_path)])
    assert "중복" in validate_layers([AoiLayer("A", tmp_path), AoiLayer("A", tmp_path)])
    assert "찾을 수" in validate_layers([AoiLayer("A", tmp_path / "x")])
    assert validate_layers([AoiLayer("A", tmp_path), AoiLayer("B", tmp_path)]) is None


def test_dialog_prefills_and_roundtrips(app, tmp_path):
    settings = AppSettings(workspace=str(tmp_path / "ws"))
    settings.aoi_layers = [{"name": "LYA4", "folder": str(tmp_path)}]
    dlg = AoiLayersDialog(settings)
    assert dlg.layers() == [AoiLayer("LYA4", tmp_path)]

    dlg._add_row("LYB4", str(tmp_path))
    assert [lyr.name for lyr in dlg.layers()] == ["LYA4", "LYB4"]
    dlg._remove_row()
    assert [lyr.name for lyr in dlg.layers()] == ["LYA4"]

    # 빈 줄은 무시하고, 잘못된 줄은 accept 를 막는다.
    dlg._add_row()
    dlg._add_row("BAD", str(tmp_path / "missing"))
    dlg.accept()
    assert dlg.result() == 0 and "BAD" in dlg.lbl_error.text()
    dlg._remove_row()
    dlg.accept()
    assert dlg.result() == 1 and dlg.lbl_error.text() == ""


def test_settings_toggle_sets_aoi_mode(app, tmp_path):
    settings = AppSettings(workspace=str(tmp_path / "ws"))
    page = SettingsPage(settings, current_lot=None)
    assert page.sw_aoi.isChecked() is False
    page.sw_aoi.setChecked(True)
    assert settings.aoi_mode is True
    assert page.updated_settings().aoi_mode is True
    assert "AOI 엔지니어 전용 모드" in page.card_titles()[0][1]


def test_main_window_routes_open_to_aoi_dialog(app, tmp_path, monkeypatch):
    from app.ui import main_window as mw

    settings = AppSettings(workspace=str(tmp_path / "ws"), auto_update_check=False)
    settings.aoi_mode = True
    settings.window_maximized = False
    win = mw.MainWindow(settings)
    try:
        assert win.review_page.empty_state.btn_open.text() == "AOI layer 폴더 지정"
        opened = []
        monkeypatch.setattr(win, "_choose_aoi_layers", lambda: opened.append(True))
        win._choose_folder()
        assert opened

        launched = []
        monkeypatch.setattr(win, "_launch_scan", lambda title, worker: launched.append(title))
        layers = [AoiLayer("A", tmp_path / "a"), AoiLayer("B", tmp_path / "b")]
        win.load_aoi(layers)
        assert launched == ["AOI 모드"]
        assert settings.aoi_layers == [lyr.to_dict() for lyr in layers]
        assert win._aoi_layers == layers
    finally:
        win.close()
