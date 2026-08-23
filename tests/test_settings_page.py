"""설정 페이지(단계 8) 계약.

카드 순서(REVIEW-01 A8) · 원본 보호 차단 · 글자 크기 높이표(A9) · 테마 즉시 반영과
첫 실행 안내 1회(A10) · 업데이트 확인 대화를 못 박는다.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402
from qfluentwidgets import MessageBox, Theme, isDarkTheme, setTheme  # noqa: E402

from app.config import AppSettings  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.pages.settings import (  # noqa: E402
    CARD_ORDER,
    GROUP_DISPLAY,
    GROUP_PATHS,
    SettingsPage,
    apply_theme_mode,
    ask_update,
    show_update_notice,
    theme_notice_pending,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def page(app, tmp_path):
    settings = AppSettings(workspace=str(tmp_path / "ws"), auto_update_check=True)
    return SettingsPage(settings, current_lot=None)


@pytest.fixture(autouse=True)
def restore_theme(app):
    """테마·글자 크기는 앱 전역 상태라 테스트가 끝나면 되돌린다."""
    sheet = app.styleSheet()
    scale = theme.FONT_SCALE
    yield
    setTheme(Theme.LIGHT)
    app.setStyleSheet(sheet)
    theme.apply_font_scale(app, scale)


# ---- 카드 순서(A8) -------------------------------------------------------

def test_card_order_matches_a8(page):
    """제품 프로파일과 글자 크기를 포함한 A8 확정 순서 그대로여야 한다."""
    assert page.card_titles() == CARD_ORDER
    paths, display = page.card_titles()
    assert paths[0] == GROUP_PATHS
    assert display[0] == GROUP_DISPLAY
    # A8 이 명시적으로 지적한 누락 두 개.
    assert "제품 프로파일" in paths[1]
    assert "글자 크기" in display[1]
    assert paths[1].index("제품 프로파일") == paths[1].index("디바이스 DB") + 1
    assert display[1].index("글자 크기") == display[1].index("테마") + 1


def test_product_combo_keeps_user_data(page):
    """제품 콤보는 데이터를 키워드로 넣는다(두 번째 위치 인자는 아이콘)."""
    from app import config

    combo = page.card_product.comboBox
    assert combo.count() >= 1
    assert combo.itemText(0) == "자동 인식"
    assert combo.itemData(0) == config.DEFAULT_PRODUCT
    assert page.card_product.current_data() == config.DEFAULT_PRODUCT


# ---- 원본 보호 ------------------------------------------------------------

def test_workspace_inside_lot_is_blocked(app, tmp_path):
    """작업공간이 LOT 폴더 안이면 값을 받지 않고 안내 문구를 남긴다."""
    lot = tmp_path / "LOT_A"
    lot.mkdir()
    safe = str(tmp_path / "ws")
    settings = AppSettings(workspace=safe)
    page = SettingsPage(settings, current_lot=str(lot))

    page.card_workspace.set_path(str(lot / "inside"))

    assert "원본 보호를 위해" in page.last_error()
    assert "작업공간 폴더가 현재 LOT 폴더 내부에 있습니다" in page.last_error()
    assert page.lbl_error.isVisible() or page.lbl_error.text()
    # 값은 그대로 남아야 한다(차단이지 경고가 아니다).
    assert page.card_workspace.path() == safe
    assert page.updated_settings().workspace == safe


def test_output_inside_lot_is_blocked(app, tmp_path):
    lot = tmp_path / "LOT_B"
    lot.mkdir()
    settings = AppSettings(workspace=str(tmp_path / "ws"))
    page = SettingsPage(settings, current_lot=str(lot))

    page.card_output.set_path(str(lot / "out"))

    assert "출력 폴더가 현재 LOT 폴더 내부에 있습니다" in page.last_error()
    assert page.card_output.path() == ""


def test_workspace_outside_lot_is_accepted(app, tmp_path):
    lot = tmp_path / "LOT_C"
    lot.mkdir()
    settings = AppSettings(workspace=str(tmp_path / "ws"))
    page = SettingsPage(settings, current_lot=str(lot))
    changed = []
    page.settings_changed.connect(lambda s: changed.append(s))

    target = str(tmp_path / "ws2")
    page.card_workspace.set_path(target)

    assert page.last_error() == ""
    assert page.updated_settings().workspace == target
    assert changed and changed[-1] is settings


def test_validate_reports_empty_workspace(app, tmp_path):
    settings = AppSettings(workspace="")
    page = SettingsPage(settings, current_lot=None)
    assert page.validate() == "작업공간 폴더를 지정하세요."


# ---- 글자 크기(A9) --------------------------------------------------------

def test_large_font_uses_large_height_token(page):
    """'크게' 는 높이표의 large 값을 쓴다. 곱셈이 아니라 표를 따른다."""
    normal = theme.fluent_height("control")
    large = theme.fluent_height("control", "large")
    assert page.control_height() == normal

    page.card_font.segment.setCurrentItem("large")

    assert page.control_height() == large
    assert page.card_workspace.button.minimumHeight() == large
    # 콤보는 Fluent qss 가 테두리 1px 를 더해 41 이 된다. 하한(large)만 지키면 된다.
    assert page.card_product.comboBox.height() >= large
    assert page.updated_settings().ui_font_size == "large"
    # 카드 높이도 같은 증가분만큼 올라간다(고정 70px 이면 글자가 잘린다).
    assert page.card_workspace.minimumHeight() == 70 + (large - normal)
    # 형태 토큰은 배율과 무관하게 그대로다(게이트).
    assert theme.RADIUS["card"] == 7
    assert theme.SPACING["gapM"] == 12

    page.card_font.segment.setCurrentItem("normal")
    assert page.control_height() == normal


def test_font_size_signal(page):
    seen = []
    page.font_size_changed.connect(seen.append)
    page.card_font.segment.setCurrentItem("large")
    assert seen == ["large"]
    page.card_font.segment.setCurrentItem("normal")


# ---- 테마(A10) ------------------------------------------------------------

def test_theme_switch_saves_and_applies(page):
    """테마를 바꾸면 theme_mode 에 남고 화면에 즉시 반영된다."""
    seen = []
    page.theme_changed.connect(seen.append)

    page.card_theme.segment.setCurrentItem("dark")

    assert page.updated_settings().theme_mode == "dark"
    assert isDarkTheme() is True
    assert seen == ["dark"]

    page.card_theme.segment.setCurrentItem("light")
    assert page.updated_settings().theme_mode == "light"
    assert isDarkTheme() is False


def test_apply_theme_mode_rebuilds_bridge_qss(app):
    """옛 화면이 기대는 브리지 QSS 도 테마와 함께 다시 만든다."""
    assert apply_theme_mode("dark") is True
    assert app.styleSheet() == theme.build_bridge_qss(True)
    assert apply_theme_mode("light") is False
    assert app.styleSheet() == theme.build_bridge_qss(False)


def test_theme_notice_shows_once(app, tmp_path):
    """첫 실행 안내는 1회만. 저장 파일에 theme_mode 가 생기면 다시 뜨지 않는다."""
    settings = AppSettings(workspace=str(tmp_path / "ws"))
    page = SettingsPage(settings, current_lot=None)

    assert theme_notice_pending(settings) is True
    assert page.maybe_show_theme_notice() is True
    assert theme_notice_pending(settings) is False
    assert page.maybe_show_theme_notice() is False

    # 새 페이지를 만들어도(=다음 실행) 다시 뜨지 않는다.
    assert SettingsPage(settings, current_lot=None).maybe_show_theme_notice() is False


# ---- 개발자 모드 ----------------------------------------------------------

def test_dev_toggle_reveals_log_rows(page):
    assert page.sw_dev.isChecked() is False
    assert page._dev_box.isHidden() is True

    page.sw_dev.setChecked(True)

    assert page.sw_dev.text == "켜짐"
    assert page._dev_box.isHidden() is False
    assert page.updated_settings().dev_mode is True
    assert page.card_dev.isExpand is True


def test_dev_expand_uses_motion_tokens(page):
    """펼침 250ms / 접힘 150ms. 기본값 200ms 는 토큰과 다르다."""
    page.card_dev.setExpand(True)
    assert page.card_dev.expandAni.duration() == theme.MOTION["rowExpand"][0]
    assert page.card_dev.card.expandButton.rotateAni.duration() == 250
    page.card_dev.setExpand(False)
    assert page.card_dev.expandAni.duration() == theme.MOTION["rowCollapse"][0]


# ---- 업데이트 ------------------------------------------------------------

def test_update_button_requests_update(page):
    fired = []
    page.update_requested.connect(lambda: fired.append(1))
    assert page.wants_update() is False

    page.btn_update.click()

    assert page.wants_update() is True
    assert fired == [1]


def test_update_available_changes_button(page):
    page.set_update_available(True)
    assert page.btn_update.text() == "지금 업데이트"
    assert page.lbl_update.text() == "새 버전이 있습니다"
    page.set_update_available(False)
    assert page.btn_update.text() == "업데이트 확인"


def test_ask_update_uses_fluent_message_box(app, monkeypatch):
    """순수 Qt QMessageBox 대신 Fluent MessageBox 를 쓴다(버튼은 동사)."""
    seen = {}

    def fake_exec(self):
        seen["box"] = self
        return 1

    monkeypatch.setattr(MessageBox, "exec", fake_exec)
    host = QWidget()

    class _Status:
        remote = "abcdef1234567890"

    assert ask_update(host, _Status()) is True
    box = seen["box"]
    assert box.yesButton.text() == "지금 업데이트"
    assert box.cancelButton.text() == "나중에"
    assert "abcdef1" in box.content
    assert "\u2014" not in box.content  # em-dash 0건


def test_show_update_notice_has_single_button(app, monkeypatch):
    seen = {}
    monkeypatch.setattr(MessageBox, "exec", lambda self: seen.setdefault("box", self))
    host = QWidget()
    show_update_notice(host, "업데이트 완료", "다시 시작해 주세요.")
    box = seen["box"]
    assert box.yesButton.text() == "확인"
    assert box.cancelButton.isHidden()


# ---- 창이 쓰는 계약 --------------------------------------------------------

def test_page_keeps_window_contract(app, tmp_path):
    """MainWindow 가 쓰는 계약(생성자 / updated_settings / wants_update / update_requested)."""
    settings = AppSettings(workspace=str(tmp_path / "ws"))
    page = SettingsPage(settings, str(tmp_path / "lot"), None, update_available=True)

    assert page.wants_update() is False
    assert page.updated_settings() is settings
    fired = []
    page.update_requested.connect(lambda: fired.append(1))
    page._on_update_clicked()
    assert page.wants_update() is True
    assert fired == [1]
