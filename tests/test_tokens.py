"""Fluent 재설계 토큰 회귀 테스트 (Qt 없이 동작).

design_handoff_fluent_redesign/02-design-rules.md 의 게이트를 코드로 못 박는다.
- 게이트 1: 텍스트/배경 대비 5.0 이상
- 게이트 2: accent 3역할 분리(fill / onAccent / text)
- 글자 크기 large 에서 높이는 표 값으로 오르고 radius·gap 은 그대로(REVIEW-01 A9)

라이트 테마 4쌍은 현재 게이트 미달이며 QUESTIONS-02 로 질의 중이다. 답이 오기 전까지
strict xfail 로 남겨 둔다. 토큰을 고쳐 통과시키면 XPASS 로 즉시 드러나므로,
그때 이 표식을 지우면서 QUESTIONS-02 결론을 함께 반영해야 한다.
"""

from __future__ import annotations


import pytest

from app.ui import theme


# QUESTIONS-02 답변 대기 중인 쌍 (라이트 전용, 측정값 기준)
_PENDING = {
    ("light", "onAccent", "accentFill"),
    ("light", "pass", "passBg"),
    ("light", "warn", "warnBg"),
    ("light", "danger", "dangerBg"),
}

# 읽어야 하는 텍스트 조합 전수. txtDeco 는 장식 전용이라 게이트 대상이 아니다.
_PAIRS = [
    ("txt1", "card"), ("txt2", "card"), ("txt3", "card"),
    ("txt1", "layer"), ("txt2", "layer"), ("txt3", "layer"),
    ("txt1", "win"), ("txt2", "win"), ("txt3", "win"),
    ("onAccent", "accentFill"),
    ("accentText", "card"), ("accentText", "layer"), ("accentText", "win"),
    ("pass", "passBg"), ("warn", "warnBg"), ("danger", "dangerBg"),
    ("info", "infoBg"),
]


def _resolved_bg(tokens: dict[str, str], key: str) -> str:
    """배경 토큰을 불투명 색으로 만든다(다크 상태 배경은 카드 위에 깔린다)."""
    value = tokens[key]
    try:
        return theme.flatten(value)
    except ValueError:
        return theme.flatten(value, tokens["card"])


def _case_id(dark: bool, fg: str, bg: str) -> str:
    return f"{'dark' if dark else 'light'}-{fg}-on-{bg}"


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
@pytest.mark.parametrize("fg,bg", _PAIRS, ids=[f"{f}-on-{b}" for f, b in _PAIRS])
def test_contrast_gate(request, dark: bool, fg: str, bg: str) -> None:
    tokens = theme.fluent_tokens(dark)
    key = ("dark" if dark else "light", fg, bg)
    if key in _PENDING:
        request.node.add_marker(
            pytest.mark.xfail(
                strict=True,
                reason="QUESTIONS-02 답변 대기 (라이트 테마 게이트 미달)",
            )
        )
    ratio = theme.contrast(tokens[fg], _resolved_bg(tokens, bg))
    assert ratio >= theme.CONTRAST_GATE, (
        f"{_case_id(dark, fg, bg)} = {ratio:.2f} (게이트 {theme.CONTRAST_GATE})"
    )


def test_contrast_helper_known_values() -> None:
    assert theme.contrast("#FFFFFF", "#000000") == pytest.approx(21.0, abs=0.01)
    assert theme.contrast("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.01)
    assert theme.contrast("#777777", "#777777") == pytest.approx(1.0, abs=0.001)


def test_flatten_composites_alpha_over_base() -> None:
    # 검정 50% 를 흰 바탕에 깔면 정확히 중간 회색
    assert theme.flatten("rgba(0,0,0,.5)", "#FFFFFF") == "#808080"
    # 완전 투명은 바탕 그대로
    assert theme.flatten("rgba(0,0,0,0)", "#123456") == "#123456"
    # 여러 층도 위에서 아래로 합성: 흰 50% 위 + 검정 50% 아래 + 흰 바탕
    assert theme.flatten("rgba(255,255,255,.5)", "rgba(0,0,0,.5)", "#FFFFFF") == "#BFBFBF"


def test_flatten_requires_opaque_bottom() -> None:
    with pytest.raises(ValueError):
        theme.flatten("rgba(0,0,0,.5)", "rgba(0,0,0,.5)")


def test_parse_rgba_formats() -> None:
    assert theme.parse_rgba("#FFF") == (255.0, 255.0, 255.0, 1.0)
    assert theme.parse_rgba("#0078D4") == (0.0, 120.0, 212.0, 1.0)
    assert theme.parse_rgba("rgb(1,2,3)") == (1.0, 2.0, 3.0, 1.0)
    assert theme.parse_rgba("rgba(0,0,0,.62)") == (0.0, 0.0, 0.0, 0.62)
    with pytest.raises(ValueError):
        theme.parse_rgba("nope")


def test_accent_three_roles_exact_values() -> None:
    """게이트 2. 채움과 글자에 같은 색을 쓰지 않는다."""
    light = theme.accent_roles(dark=False)
    dark = theme.accent_roles(dark=True)

    assert light["fill"] == "#0078D4"
    assert light["onAccent"] == "#FFFFFF"
    assert light["text"] == "#005A9E"
    assert light["pressed"] == "#005A9E"

    assert dark["fill"] == "#4CC2FF"
    # 다크에서 채움 위 흰 글자는 2.01:1 이라 near-black 을 쓴다
    assert dark["onAccent"] == "#16140F"
    assert dark["text"] == "#4CC2FF"

    for roles in (light, dark):
        assert roles["fill"] != roles["onAccent"]
    # 라이트는 채움과 글자용 accent 가 서로 다른 색이어야 한다
    assert light["fill"] != light["text"]


def test_dark_accent_fill_with_white_text_is_the_trap_we_avoid() -> None:
    dark = theme.accent_roles(dark=True)
    assert theme.contrast("#FFFFFF", dark["fill"]) < 2.5
    assert theme.contrast(dark["onAccent"], dark["fill"]) >= theme.CONTRAST_GATE


def test_accent_roles_derive_for_custom_base() -> None:
    light = theme.accent_roles(dark=False, base="#8B5CF6")
    dark = theme.accent_roles(dark=True, base="#8B5CF6")

    assert light["fill"] == "#8B5CF6"
    assert light["onAccent"] == "#FFFFFF"
    assert dark["onAccent"] == "#16140F"
    # 글자용 accent 는 채움보다 어둡고(라이트), 채움은 다크에서 더 밝다
    assert theme.relative_luminance(light["text"]) < theme.relative_luminance(light["fill"])
    assert theme.relative_luminance(dark["fill"]) > theme.relative_luminance("#8B5CF6")
    assert light["tint"].startswith("rgba(139,92,246,")


def test_light_and_dark_expose_the_same_token_keys() -> None:
    assert set(theme.FLUENT_LIGHT) == set(theme.FLUENT_DARK)
    assert set(theme.STATUS_LIGHT) == set(theme.STATUS_DARK)
    assert set(theme.fluent_tokens(False)) == set(theme.fluent_tokens(True))


def test_photo_background_is_pure_black_in_both_themes() -> None:
    assert theme.PHOTO_BG == "#000000"
    assert theme.fluent_tokens(False)["photo"] == "#000000"
    assert theme.fluent_tokens(True)["photo"] == "#000000"


def test_heights_scale_by_table_not_multiplication() -> None:
    """REVIEW-01 A9. 높이는 하한이고 large 는 표 값으로 오른다."""
    assert theme.fluent_height("control") == 32
    assert theme.fluent_height("control", "large") == 40
    assert theme.fluent_height("primary", "large") == 44
    assert theme.fluent_height("navItem", "large") == 48
    assert theme.fluent_height("tableRow", "large") == 27
    assert theme.fluent_height("specRow", "large") == 72
    assert theme.fluent_height("icon", "large") == 20
    # 타이틀바는 두 배율에서 같다
    assert theme.fluent_height("titleBar", "large") == theme.fluent_height("titleBar")


def test_shape_tokens_do_not_scale_with_font_size() -> None:
    """게이트: radius·gap·패딩은 글자 크기 배율과 무관하게 고정."""
    before = (dict(theme.RADIUS), dict(theme.SPACING))
    assert theme.fluent_font_px("body", "large") == pytest.approx(13.0 * 1.3)
    assert (dict(theme.RADIUS), dict(theme.SPACING)) == before
    assert theme.RADIUS == {"control": 5, "card": 7, "sheet": 8, "chip": 13}


def test_font_scale_applies_to_typography_roles() -> None:
    assert theme.fluent_font_px("title") == 26.0
    assert theme.fluent_font_px("title", "large") == pytest.approx(26.0 * 1.3)
    assert theme.fluent_font_px("caption", "large") == pytest.approx(12.0 * 1.3)
    assert theme.FONT_SCALES == {"normal": 1.0, "large": 1.3}


def test_well_minimum_keeps_twelve_layers_readable() -> None:
    """게이트 4. 판독대 한 칸의 최소 높이."""
    assert theme.WELL_MIN_PX == 224


def test_motion_durations_match_the_spec() -> None:
    assert theme.MOTION["control"] == (120, "Linear")
    assert theme.MOTION["enter"] == (250, "OutQuint")
    assert theme.MOTION["exit"] == (150, "InQuart")
    assert theme.MOTION["navPill"] == (300, "OutQuart")
    assert theme.MOTION["photoSwap"][0] == 220
    # 스피너는 등속(가감속 금지)
    assert theme.MOTION["spinner"] == (900, "Linear")
    assert theme.INFOBAR_DURATION_MS == 3400


def test_touched_files_have_no_em_dash() -> None:
    """카피 규칙: em-dash 금지. 주석·docstring 에도 적용(REVIEW-01 AD5).

    문자를 코드 리터럴로 적으면 이 파일 자신이 걸리므로 코드포인트로 만든다.
    """
    import pathlib

    em_dash = chr(0x2014)
    for path in (pathlib.Path(theme.__file__), pathlib.Path(__file__)):
        assert em_dash not in path.read_text(encoding="utf-8"), path.name


def test_token_values_are_parseable_colors() -> None:
    for dark in (False, True):
        for key, value in theme.fluent_tokens(dark).items():
            assert isinstance(key, str) and key
            theme.parse_rgba(value)  # 형식 오류면 여기서 실패
