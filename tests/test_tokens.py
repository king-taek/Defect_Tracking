"""Fluent 재설계 토큰 회귀 테스트 (Qt 없이 동작).

design_handoff_fluent_redesign/02-design-rules.md 의 게이트를 코드로 못 박는다.
- 게이트 1: 텍스트/배경 대비 5.0 이상
- 게이트 2: accent 3역할 분리(fill / onAccent / text)
- 글자 크기 large 에서 높이는 표 값으로 오르고 radius·gap 은 그대로(REVIEW-01 A9)

REVIEW-02·REVIEW-03 으로 토큰 레이어가 닫혔다. 미해결 표식(xfail)은 남아 있지 않다.
경계선 4쌍은 REVIEW-03 A21 로 게이트 대상에서 아예 빠졌고, 그 대가로 hover 가 경계선 단독
신호가 아님을 검사한다.
"""

from __future__ import annotations


import pytest

from app.ui import theme


# 읽어야 하는 텍스트 조합 전수. txtDeco 는 장식 전용이라 게이트 대상이 아니다.
_PAIRS = [
    ("txt1", "card"), ("txt2", "card"), ("txt3", "card"),
    ("txt1", "layer"), ("txt2", "layer"), ("txt3", "layer"),
    ("txt1", "win"), ("txt2", "win"), ("txt3", "win"),
    ("onAccent", "accentFill"), ("onAccent", "accentHover"), ("onAccent", "accentPressed"),
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
def test_contrast_gate(dark: bool, fg: str, bg: str) -> None:
    tokens = theme.fluent_tokens(dark)
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
    """게이트 2 + REVIEW-02 A15 확정값. 채움과 글자에 같은 색을 쓰지 않는다."""
    light = theme.accent_roles(dark=False)
    dark = theme.accent_roles(dark=True)

    # 구 #0078D4 는 흰 글자와 4.53 이라 게이트 미달이었다
    assert light["fill"] == "#0067B8"
    assert light["hover"] == "#005A9E"
    assert light["pressed"] == "#004C85"
    assert light["onAccent"] == "#FFFFFF"
    assert light["text"] == "#005A9E"

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


@pytest.mark.parametrize("preset", ["#0078D4", "#009FAA", "#8B5CF6"])
@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_accent_preset_states_pass_the_gate(preset: str, dark: bool) -> None:
    """REVIEW-02 A17. 프리셋 3종 x 라이트·다크 = 6조합을 회귀로 고정한다.

    채움뿐 아니라 hover·pressed 에서도 게이트가 유지되어야 한다. 상태에서 채움이 움직이므로
    onAccent 를 흰색으로 쓰는 어두운 채움은 더 어둡게, near-black 을 쓰는 밝은 채움은 더 밝게
    가야 한다.
    """
    roles = theme.accent_roles(dark, preset)
    tokens = theme.fluent_tokens(dark, preset)
    for state in ("fill", "hover", "pressed"):
        ratio = theme.contrast(roles["onAccent"], roles[state])
        assert ratio >= theme.CONTRAST_GATE, f"{preset} {state} = {ratio:.2f}"
    for surface in ("card", "layer", "win"):
        ratio = theme.contrast(roles["text"], theme.flatten(tokens[surface]))
        assert ratio >= theme.CONTRAST_GATE, f"{preset} text on {surface} = {ratio:.2f}"


def test_accent_preset_light_values_match_review_02() -> None:
    """REVIEW-02 A15 가 제시한 라이트 확정 채움."""
    assert theme.accent_roles(False, "#0078D4")["fill"] == "#0067B8"
    assert theme.accent_roles(False, "#009FAA")["fill"] == "#009FAA"
    assert theme.accent_roles(False, "#8B5CF6")["fill"] == "#7B3FE4"
    # 밝은 청록은 라이트에서도 near-black 글자가 맞다(테마가 아니라 밝기로 고른다)
    assert theme.accent_roles(False, "#009FAA")["onAccent"] == theme.ONACCENT_DARK
    assert theme.accent_roles(False, "#0078D4")["onAccent"] == theme.ONACCENT_LIGHT


@pytest.mark.parametrize(
    "base",
    ["#FFFF00", "#00FF00", "#FF00FF", "#000000", "#FFFFFF", "#808080", "#FF6B00", "#123456"],
)
@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_accent_rule_holds_the_gate_for_any_color(base: str, dark: bool) -> None:
    """규칙 안전망. 임의 색을 넣어도 게이트를 넘겨야 한다.

    다크에서 명도가 이미 최대인 고채도 색은 더 밝힐 수 없으므로 채도를 낮춰 이어간다.
    이 확장이 없으면 반복만 소진하고 미달로 빠져나온다.
    """
    roles = theme.resolve_accent(base, dark)
    tokens = theme.fluent_tokens(dark)
    for state in ("fill", "hover", "pressed"):
        ratio = theme.contrast(roles["onAccent"], roles[state])
        assert ratio >= theme.CONTRAST_GATE, f"{base} {state} = {ratio:.2f}"
    # 글자용 accent 는 카드 하나가 아니라 세 면 모두에서 읽혀야 한다
    for surface in ("card", "layer", "win"):
        ratio = theme.contrast(roles["text"], theme.flatten(tokens[surface]))
        assert ratio >= theme.CONTRAST_GATE, f"{base} text on {surface} = {ratio:.2f}"


def test_status_colors_match_review_02() -> None:
    """REVIEW-02 A16. 라이트 글자만 여유값으로 교체하고 배경·다크는 유지."""
    light = theme.STATUS_LIGHT
    assert (light["pass"], light["warn"], light["danger"]) == ("#0B6A0B", "#8A5200", "#B02218")
    assert (light["passBg"], light["warnBg"], light["dangerBg"]) == (
        "#DFF6DD", "#FFF4CE", "#FDE7E9",
    )
    dark = theme.STATUS_DARK
    assert (dark["pass"], dark["warn"], dark["danger"]) == ("#6CCB70", "#FFD68A", "#FF99A4")
    # 판정을 나르는 색이라 최소변경(5.0 언저리)이 아니라 여유가 있어야 한다
    for fg, bg in (("pass", "passBg"), ("warn", "warnBg"), ("danger", "dangerBg")):
        assert theme.contrast(light[fg], light[bg]) >= 5.7


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


# ---- REVIEW-02 A17: 비텍스트 하위 기준 + 게이트 대상 정의 ----

_FOCUS_BACKGROUNDS = ["card", "layer", "win"]


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
@pytest.mark.parametrize("bg", _FOCUS_BACKGROUNDS)
def test_focus_ring_meets_subgate(dark: bool, bg: str) -> None:
    """포커스 링은 조작에 필요한 요소라 하위 기준 3.0 을 넘어야 한다."""
    tokens = theme.fluent_tokens(dark)
    ratio = theme.contrast(tokens["accentFill"], _resolved_bg(tokens, bg))
    assert ratio >= theme.SUBGATE_CONTRAST, f"focus ring on {bg} = {ratio:.2f}"


def test_photo_stage_text_passes_the_gate() -> None:
    """순검정 무대 위 텍스트는 별도 쌍으로 검사한다(A17 대상 목록)."""
    for alpha, label in ((".62", "매치 없음"), (".66", "사유"), (".55", "스케일바 라벨")):
        ratio = theme.contrast(f"rgba(255,255,255,{alpha})", theme.PHOTO_BG)
        assert ratio >= theme.CONTRAST_GATE, f"{label} = {ratio:.2f}"


def test_gate_constants_match_the_reviews() -> None:
    assert theme.SUBGATE_CONTRAST == 3.0
    assert theme.CONTRAST_GATE == 5.0
    # REVIEW-03 A19. 생성 목표와 판정 합격선을 분리한다. 같으면 결과가 늘 경계에 얹힌다.
    assert theme.ACCENT_CLAMP_TARGET == 5.4
    assert theme.ACCENT_CLAMP_TARGET > theme.CONTRAST_GATE


# ---- REVIEW-02 AD6: txtDeco 오용 방지 정적 검사 ----

_TXTDECO_ALLOWED = (
    "app/ui/theme.py",  # 토큰 정의 자체
)


def test_txtdeco_is_only_used_for_separators() -> None:
    """게이트에서 빼는 대가로 사용처를 고정한다(AD6).

    허용: 구분자, 수치 분모, 페이지 경계 라벨. 그 외에서 참조하면 실패한다.
    실제로 분모에 쓴 값이 2.66:1 까지 떨어진 사례가 보고됐다.
    """
    import pathlib

    root = pathlib.Path(theme.__file__).resolve().parents[2]
    offenders = []
    for path in sorted((root / "app" / "ui").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel in _TXTDECO_ALLOWED:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "txtDeco" not in line:
                continue
            if any(hint in line for hint in ("구분자", "분모", "페이지 경계", "separator")):
                continue
            offenders.append(f"{rel}:{number}")
    assert not offenders, (
        "txtDeco 는 구분자·분모·페이지 경계 라벨에만 쓴다. 용도를 주석으로 남기거나 "
        f"txt2/txt3 을 쓰세요: {offenders}"
    )


# ---- REVIEW-03 반영 ----

@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_hover_is_never_a_border_only_signal(dark: bool) -> None:
    """REVIEW-03 A21. 경계선을 게이트에서 빼는 대가로 붙은 조건.

    경계선은 대비 1.13~1.69 라 hover 를 경계선만으로 표현하면 사실상 보이지 않는다.
    hover 에는 반드시 배경 변화가 따라야 한다.
    """
    tokens = theme.fluent_tokens(dark)
    for base, hover in (("card", "cardHover"), ("ctrlBg", "ctrlBgH"), ("subtle", "subtleH")):
        assert tokens[base] != tokens[hover], f"{base} 와 {hover} 가 같으면 hover 가 안 보인다"


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_heatmap_selection_ring_survives_both_ramp_ends(dark: bool) -> None:
    """REVIEW-03 A22. 단색 링은 램프 최고 채움과 같은 색이라 최고 밀도 die 에서 사라진다.

    이중선이라 램프 어느 지점에서도 한 겹이 대비를 만든다.
    """
    tokens = theme.fluent_tokens(dark)
    ramp_min = theme.flatten(tokens["accentTint"], tokens["card"])
    ramp_max = tokens["accentFill"]

    outer = theme.contrast(tokens["accentFill"], ramp_min)
    inner = theme.contrast(tokens["onAccent"], ramp_max)
    assert outer >= theme.SUBGATE_CONTRAST, f"바깥 링 x 램프 최저 = {outer:.2f}"
    assert inner >= theme.SUBGATE_CONTRAST, f"안쪽 링 x 램프 최고 = {inner:.2f}"

    # 단색 링이었다면 최고 밀도에서 완전히 묻힌다(회귀 근거)
    assert theme.contrast(tokens["accentFill"], ramp_max) == pytest.approx(1.0, abs=0.001)


def test_selection_ring_spec_is_a_double_line() -> None:
    assert theme.SELECTION_RING["width_px"] == 2
    assert theme.SELECTION_RING["outer"] == "accentFill"
    assert theme.SELECTION_RING["inner"] == "onAccent"


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_clamp_failure_is_raised_not_swallowed(dark: bool) -> None:
    """REVIEW-03 A18 게이트. 목표에 도달하지 못하면 조용히 넘어가지 않는다."""
    with pytest.raises(ValueError):
        theme.resolve_accent("#0078D4", dark, target=21.5)


def test_clamp_target_leaves_margin_over_the_gate() -> None:
    """생성 목표가 합격선보다 높아야 결과가 경계에 얹히지 않는다."""
    roles = theme.resolve_accent("#0078D4", dark=False)
    ratio = theme.contrast(roles["onAccent"], roles["fill"])
    assert ratio >= theme.ACCENT_CLAMP_TARGET
    assert ratio > theme.CONTRAST_GATE


def test_accent_presets_delegate_dark_to_the_rule() -> None:
    """REVIEW-03 A20. 표에 없는 조합(None)은 규칙이 받는다."""
    assert theme.ACCENT_PRESETS["#009FAA"][True] is None
    assert theme.ACCENT_PRESETS["#8B5CF6"][True] is None
    # 위임 경로도 게이트를 넘는다
    for preset in ("#009FAA", "#8B5CF6"):
        roles = theme.accent_roles(True, preset)
        assert theme.contrast(roles["onAccent"], roles["fill"]) >= theme.CONTRAST_GATE
