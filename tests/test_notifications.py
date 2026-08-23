"""알림 회귀 (단계 1b).

원본 배너는 다음 메시지가 앞 메시지를 덮어썼다. InfoBar 스택은 서로를 지우지 않아야 한다.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QWidget  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui import theme  # noqa: E402
from app.ui.notifications import NotificationBanner  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def host(app):
    w = QWidget()
    w.resize(900, 600)
    w.show()
    yield w
    w.close()


def test_messages_stack_instead_of_replacing(host):
    banner = NotificationBanner(host)
    first = banner.show_message("스캔 완료", "success")
    second = banner.show_message("매칭 완료", "success")
    assert first is not second
    assert len(banner._bars) == 2


def test_default_duration_matches_the_spec(host):
    """자동 소멸 3.4초. qfluentwidgets 기본값 1초는 너무 짧다."""
    banner = NotificationBanner(host)
    bar = banner.show_message("확인", "info")
    assert bar.duration == theme.INFOBAR_DURATION_MS


def test_zero_timeout_keeps_the_message_until_closed(host):
    """조치가 필요한 오류는 사용자가 닫을 때까지 남아야 한다."""
    banner = NotificationBanner(host)
    bar = banner.show_message("폴더 스캔 중 오류", "error", timeout_ms=0)
    assert bar.duration == -1


@pytest.mark.parametrize("level", ["info", "success", "warn", "warning", "error"])
def test_all_levels_are_accepted(host, level):
    banner = NotificationBanner(host)
    assert banner.show_message("메시지", level) is not None


def test_action_button_is_attached(host):
    """'폴더 열기' 같은 후속 동작을 알림에서 바로 실행할 수 있어야 한다."""
    from qfluentwidgets import PushButton

    calls = []
    banner = NotificationBanner(host)
    bar = banner.show_message(
        "Excel 출력 완료", "success", action_text="폴더 열기", action=lambda: calls.append(1)
    )
    buttons = bar.findChildren(PushButton)
    assert any(b.text() == "폴더 열기" for b in buttons)
    for b in buttons:
        if b.text() == "폴더 열기":
            b.click()
    assert calls == [1]


def test_title_and_body_split(host):
    """제목만 주면 본문 없이, 둘 다 주면 두 줄로 뜬다."""
    banner = NotificationBanner(host)
    single = banner.show_message("스캔을 중단했습니다.", "info")
    assert single.title == "스캔을 중단했습니다."
    assert single.content == ""
    paired = banner.show_message("layer 24 · wafer 25", "success", title="스캔 완료")
    assert paired.title == "스캔 완료"
    assert paired.content == "layer 24 · wafer 25"


def test_reposition_is_a_noop_but_still_callable(host):
    """창 크기 변경 훅이 호출부에 남아 있다."""
    banner = NotificationBanner(host)
    banner.reposition()


def test_tone_bar_is_attached_per_level(host):
    """레벨을 아이콘 하나로만 나르면 흑백 인쇄·저시력에서 약하다(03-screens §9)."""
    from qfluentwidgets import CustomStyleSheet

    banner = NotificationBanner(host)
    bar = banner.show_message("확인", "error")
    sheet = CustomStyleSheet(bar)
    light, dark = sheet.lightStyleSheet(), sheet.darkStyleSheet()
    assert "border-left: 4px solid" in light
    assert "border-left: 4px solid" in dark
    assert theme.fluent_tokens(False)["danger"] in light
    assert theme.fluent_tokens(True)["danger"] in dark


def test_tone_bar_colours_differ_by_level(host):
    from qfluentwidgets import CustomStyleSheet

    banner = NotificationBanner(host)
    tones = {}
    for level in ("success", "warn", "error", "info"):
        bar = banner.show_message("메시지", level)
        tones[level] = CustomStyleSheet(bar).lightStyleSheet()
    assert len(set(tones.values())) == 4, "레벨마다 톤이 달라야 구분된다"
