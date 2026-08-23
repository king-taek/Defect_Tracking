"""도움말 페이지(단계 8) 계약.

문구는 REVIEW-01 A6 확정본이다. 단축키 4그룹 · 기능 6항목을 유지하고, 화면 이름이 바뀐
"출력 트레이"는 앱 어디에도 남기지 않는다.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui import theme  # noqa: E402
from app.ui.pages.help import FEATURES, SHORTCUT_GROUPS, HelpPage  # noqa: E402

# REVIEW-01 A6 이 준 FEAT#3 교체 문구. 한 글자도 바꾸지 않는다.
_A6_FEATURE_3 = (
    "layer 교차 판독",
    "히트맵에서 위치를 고르면 그 자리의 defect 을 layer 별로 나란히 놓고 봅니다. "
    "선택한 layer 들을 서로 교차 매칭하므로 기준 없이도 비교할 수 있고, "
    "어느 layer 와도 매칭되지 않은 defect 은 따로 표시됩니다.",
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def page(app):
    return HelpPage()


# ---- 문구(A6) -------------------------------------------------------------

def test_shortcut_groups_and_features_kept(page):
    """원본 4그룹 · 6항목 구성을 유지한다."""
    assert len(SHORTCUT_GROUPS) == 4
    assert [name for name, _ in SHORTCUT_GROUPS] == ["탐색", "선택", "출력", "파일 · 도움말"]
    assert len(FEATURES) == 6
    assert len(page._rows) == sum(len(rows) for _, rows in SHORTCUT_GROUPS)
    assert len(page._feature_cards) == 6


def test_feature_three_is_a6_wording():
    """A6 이 준 FEAT#3 교체본이 그대로 들어 있다."""
    assert FEATURES[2] == _A6_FEATURE_3


def test_no_export_tray_wording():
    """화면 이름은 '출력 명세' 하나로 통일한다."""
    blob = "\n".join(
        [key + desc for _, rows in SHORTCUT_GROUPS for key, desc in rows]
        + [name + desc for name, desc in FEATURES]
    )
    assert "출력 트레이" not in blob
    assert "현재 기준 사진을 출력 명세에 담기" in blob
    assert any(name == "출력 명세" for name, _ in FEATURES)


def test_copy_rules(page):
    """이모지 0건 · em-dash 0건(02 §4)."""
    blob = "".join(
        [key + desc for _, rows in SHORTCUT_GROUPS for key, desc in rows]
        + [name + desc for name, desc in FEATURES]
    )
    assert "\u2014" not in blob
    assert not any(0x1F300 <= ord(ch) <= 0x1FAFF for ch in blob)


# ---- 화면 -----------------------------------------------------------------

def test_page_object_name(page):
    """objectName 이 곧 라우트 키다."""
    assert page.objectName() == "helpInterface"


def test_keycap_and_row_use_tokens(page):
    """키캡 폭 214 유지, 행 높이는 높이표를 따른다."""
    assert page._keycaps[0].minimumWidth() == 214
    assert page._rows[0].minimumHeight() == theme.fluent_height("control")
    page.set_font_size("large")
    assert page._rows[0].minimumHeight() == theme.fluent_height("control", "large")
    page.set_font_size("normal")


def test_group_header_passes_contrast_gate():
    """그룹 헤더는 accentText 를 subtle 배경 위에 쓴다. 새 조합이라 실측해 둔다(게이트 5.0)."""
    for dark in (False, True):
        t = theme.fluent_tokens(dark)
        head_bg = theme.flatten(t["subtle"], t["card"])
        assert theme.contrast(t["accentText"], head_bg) >= theme.CONTRAST_GATE


def test_rows_carry_original_shortcuts(page):
    """행 문구가 데이터와 1:1 로 붙어 있다(표시 누락 방지)."""
    keys = [cap.text() for cap in page._keycaps]
    assert keys[0] == "← / → · PageUp / PageDown"
    assert "Ctrl + E" in keys
    descs = [d.text() for d in page._descs]
    assert "현재 기준 사진을 출력 명세에 담기" in descs


def test_help_is_a_route_not_a_dialog(app):
    """도움말은 nav 라우트다. 단축키를 보려고 보던 화면을 덮지 않는다.

    부모 없이 만들면 Qt 는 어떤 위젯이든 창으로 친다(`isWindow()`). 그래서 창인지가 아니라
    모달을 띄우는 종류(QDialog)가 아닌지를 본다.
    """
    from PySide6.QtWidgets import QDialog

    page = HelpPage()
    assert page.objectName() == "helpInterface"
    assert not isinstance(page, QDialog)
