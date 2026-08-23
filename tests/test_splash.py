"""스플래시 회귀 (REVIEW-01 A5 스펙).

독립 창을 유지하는 이유와 등속 스피너·고정 높이 문구가 게이트라 코드로 못 박는다.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import __version__, config  # noqa: E402
from app.ui import splash as splash_mod  # noqa: E402
from app.ui import theme  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_splash_size_matches_the_spec(app):
    s = splash_mod.make_splash()
    assert (s.width(), s.height()) == (400, 220)
    s.close()


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_splash_paints_without_error_in_both_themes(app, dark):
    s = splash_mod.make_splash(dark)
    splash_mod.show_status(s, "화면 구성")
    s.show()
    for _ in range(3):
        app.processEvents()
    shot = s.grab()
    assert not shot.isNull()
    assert (shot.width(), shot.height()) == (400, 220)
    s.close()


def test_spinner_is_constant_speed(app):
    """가감속 금지(게이트). 같은 시간 간격이면 같은 각도만큼 돈다."""
    s = splash_mod.make_splash()
    steps = []
    for _ in range(3):
        before = s._angle
        s._advance()
        steps.append((s._angle - before) % 360.0)
    assert steps[0] == pytest.approx(steps[1]) == pytest.approx(steps[2])
    # 한 바퀴 900ms
    assert theme.MOTION["spinner"] == (900, "Linear")
    s.close()


def test_status_area_has_a_fixed_height(app):
    """문구가 바뀌어도 레이아웃이 흔들리지 않아야 한다."""
    assert splash_mod._STATUS_H == 16
    s = splash_mod.make_splash()
    splash_mod.show_status(s, "짧게")
    first = s.grab().size()
    splash_mod.show_status(s, "아주 긴 단계 문구로 바꿔도 창 크기는 그대로여야 한다")
    assert s.grab().size() == first
    s.close()


def test_splash_still_shows_version_and_credits_source(app):
    """버전 표기는 계승 필수 항목이다."""
    s = splash_mod.make_splash()
    assert config.APP_NAME
    assert __version__
    s.close()


def test_finish_accepts_a_window_argument(app):
    """QSplashScreen 과 호출 형태가 같아야 main.py 가 그대로 돈다."""
    s = splash_mod.make_splash()
    s.show()
    app.processEvents()
    s.finish(None)
    app.processEvents()
