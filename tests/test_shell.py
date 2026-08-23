"""FluentWindow 셸 회귀 (단계 1a).

nav 라우팅은 objectName 이 곧 키라 비거나 겹치면 조용히 깨진다. 그 계약과 빈 상태 전환을
코드로 못 박는다.
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config import AppSettings  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.pages.review import ReviewPage  # noqa: E402

_ROUTES = [
    "reviewInterface",
    "nomatchInterface",
    "heatmapInterface",
    "exportInterface",
    "helpInterface",
    "settingsInterface",
]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    w = MainWindow(AppSettings(workspace=tempfile.mkdtemp(), auto_update_check=False))
    yield w
    w.close()


def test_all_six_routes_are_registered(win):
    for route in _ROUTES:
        assert win.navigationInterface.widget(route) is not None, route


def test_route_keys_are_unique_and_non_empty(win):
    pages = [
        win.review_page, win.nomatch_page, win.heatmap_page,
        win.export_page, win.help_page, win.settings_page,
    ]
    names = [p.objectName() for p in pages]
    assert all(names), "objectName 이 비면 addSubInterface 가 ValueError 를 낸다"
    assert len(set(names)) == len(names), "objectName 이 겹치면 라우팅이 깨진다"
    assert set(names) == set(_ROUTES)


def test_starts_on_the_empty_state(win):
    """LOT 을 열기 전에는 다음 행동을 고르는 화면이 보여야 한다."""
    assert win.review_page.is_empty_state()


def test_empty_state_offers_open_and_recent(win):
    empty = win.review_page.empty_state
    assert empty.btn_open.text() == "LOT 폴더 선택"
    assert empty.btn_recent.text() == "최근 폴더"


def test_review_widget_aliases_survive_the_shell_move(win):
    """기존 코드와 테스트가 기대는 이름을 페이지로 옮긴 뒤에도 유지한다."""
    page = win.review_page
    assert win.top is page.sidebar
    assert win.grid is page.grid
    assert win.strip is page.strip
    assert win.nav is page.nav
    assert win.progress is page.progress
    assert win.btn_stop is page.btn_stop
    assert win.splitter is page.splitter


def test_scan_stop_button_is_inherited(win):
    """스캔 중단은 계승 필수 항목이다."""
    assert win.btn_stop.text() == "■ 중단"
    assert not win.btn_stop.isVisible()


def test_nav_badge_appears_and_clears(win):
    win._set_nav_badge("exportInterface", 3)
    assert "exportInterface" in win._nav_badges
    win._set_nav_badge("exportInterface", 0)
    assert "exportInterface" not in win._nav_badges


def test_every_route_is_a_real_page(win):
    """여섯 라우트가 모두 실제 페이지다. 임시 다리는 남지 않았다."""
    routes = {
        win.review_page: "reviewInterface",
        win.nomatch_page: "nomatchInterface",
        win.heatmap_page: "heatmapInterface",
        win.export_page: "exportInterface",
        win.help_page: "helpInterface",
        win.settings_page: "settingsInterface",
    }
    for page, key in routes.items():
        assert page.objectName() == key
        assert win.stackedWidget.indexOf(page) >= 0


def test_review_page_can_be_built_standalone(app):
    """페이지가 창에서 분리돼도 서야 단계 2 에서 갈아끼울 수 있다."""
    page = ReviewPage(None, 240)
    assert page.objectName() == "reviewInterface"
    assert page.is_empty_state()
    page.show_empty_state(False)
    assert not page.is_empty_state()
