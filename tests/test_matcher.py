"""매칭 엔진 및 layer 정규화 테스트 (문서 Section 8.3 / 8.2)."""

from pathlib import Path

from app import layout
from app.matcher import match_all_with_offsets, match_base_against_layers
from app.models import DefectRecord, ParseStatus, Source


def _rec(layer, wafer, col, row, x, y, name="img.jpg"):
    return DefectRecord(
        image_path=Path(f"/src/{layer}/{wafer}/{name}"),
        wafer_id=wafer,
        layer=layer,
        layer_folder=layer,
        source=Source.CAMTEK_FILENAME,
        status=ParseStatus.OK,
        col=col,
        row=row,
        x=x,
        y=y,
    )


def test_match_within_tolerance():
    base = _rec("LYA4", "W1", 4, 5, 1000.0, 2000.0)
    cmp = _rec("LYB4", "W1", 4, 5, 1050.0, 2000.0)  # 거리 50
    out = match_base_against_layers(base, ["LYB4"], {"LYB4": [cmp]}, tolerance=100.0)
    mr = out.for_layer("LYB4")
    assert mr.is_match
    assert abs(mr.distance - 50.0) < 1e-6


def test_no_match_outside_tolerance():
    base = _rec("LYA4", "W1", 4, 5, 1000.0, 2000.0)
    cmp = _rec("LYB4", "W1", 4, 5, 1200.0, 2000.0)  # 거리 200 > 100
    out = match_base_against_layers(base, ["LYB4"], {"LYB4": [cmp]}, tolerance=100.0)
    assert not out.for_layer("LYB4").is_match


def test_no_match_different_die():
    base = _rec("LYA4", "W1", 4, 5, 1000.0, 2000.0)
    cmp = _rec("LYB4", "W1", 3, 3, 1000.0, 2000.0)  # die 다름
    out = match_base_against_layers(base, ["LYB4"], {"LYB4": [cmp]}, tolerance=100.0)
    assert not out.for_layer("LYB4").is_match


def test_no_match_different_wafer():
    base = _rec("LYA4", "W1", 4, 5, 1000.0, 2000.0)
    cmp = _rec("LYB4", "W2", 4, 5, 1000.0, 2000.0)  # wafer 다름
    out = match_base_against_layers(base, ["LYB4"], {"LYB4": [cmp]}, tolerance=100.0)
    assert not out.for_layer("LYB4").is_match


def test_picks_nearest_candidate():
    base = _rec("LYA4", "W1", 4, 5, 1000.0, 2000.0)
    far = _rec("LYB4", "W1", 4, 5, 1090.0, 2000.0, name="far.jpg")
    near = _rec("LYB4", "W1", 4, 5, 1010.0, 2000.0, name="near.jpg")
    out = match_base_against_layers(base, ["LYB4"], {"LYB4": [far, near]}, tolerance=100.0)
    mr = out.for_layer("LYB4")
    assert mr.matched.image_path.name == "near.jpg"
    assert mr.ambiguous is False


def test_ambiguous_when_two_candidates_tie():
    base = _rec("LYA4", "W1", 4, 5, 1000.0, 2000.0)
    a = _rec("LYB4", "W1", 4, 5, 1050.0, 2000.0, name="a.jpg")  # 거리 50
    b = _rec("LYB4", "W1", 4, 5, 950.0, 2000.0, name="b.jpg")   # 거리 50 (반대편)
    out = match_base_against_layers(base, ["LYB4"], {"LYB4": [a, b]}, tolerance=100.0)
    mr = out.for_layer("LYB4")
    assert mr.is_match
    assert mr.ambiguous is True


def test_not_ambiguous_with_clear_winner():
    base = _rec("LYA4", "W1", 4, 5, 1000.0, 2000.0)
    near = _rec("LYB4", "W1", 4, 5, 1005.0, 2000.0, name="near.jpg")  # 5
    far = _rec("LYB4", "W1", 4, 5, 1080.0, 2000.0, name="far.jpg")    # 80
    out = match_base_against_layers(base, ["LYB4"], {"LYB4": [near, far]}, tolerance=100.0)
    assert out.for_layer("LYB4").ambiguous is False


def test_die_within_one_matches():
    """die index 가 (±1) 어긋나도 매칭된다(원본 AOI 알고리즘)."""
    base = _rec("LYA4", "W1", 4, 5, 1000.0, 2000.0)
    cmp = _rec("LYB4", "W1", 5, 6, 1010.0, 2000.0)  # die +1,+1, 거리 10
    out = match_base_against_layers(base, ["LYB4"], {"LYB4": [cmp]}, tolerance=100.0)
    assert out.for_layer("LYB4").is_match


def test_die_two_off_still_no_match():
    base = _rec("LYA4", "W1", 4, 5, 1000.0, 2000.0)
    cmp = _rec("LYB4", "W1", 6, 7, 1000.0, 2000.0)  # die +2,+2 → 범위 밖
    out = match_base_against_layers(base, ["LYB4"], {"LYB4": [cmp]}, tolerance=100.0)
    assert not out.for_layer("LYB4").is_match


def test_median_offset_corrects_selection():
    """layer 간 계통적 이동이 있으면, 그 중앙값에 맞는 후보를 선택한다."""
    # die 를 2칸 간격으로 띄워 die±1 이웃이 겹치지 않게 한다.
    bases = [
        _rec("LYA4", "W1", 1, 1, 1000.0, 0.0),
        _rec("LYA4", "W1", 3, 3, 1000.0, 0.0),
        _rec("LYA4", "W1", 5, 5, 1000.0, 0.0),
        _rec("LYA4", "W1", 7, 7, 1000.0, 0.0),  # 같은 die 후보 2개(모호)
    ]
    cmps = [
        _rec("LYB4", "W1", 1, 1, 1040.0, 0.0, name="c1.jpg"),
        _rec("LYB4", "W1", 3, 3, 1040.0, 0.0, name="c2.jpg"),
        _rec("LYB4", "W1", 5, 5, 1040.0, 0.0, name="c3.jpg"),
        _rec("LYB4", "W1", 7, 7, 1045.0, 0.0, name="ca.jpg"),  # raw 45, 보정후 잔차 5
        _rec("LYB4", "W1", 7, 7, 965.0, 0.0, name="cb.jpg"),   # raw 35, 보정후 잔차 75
    ]
    matches, offsets = match_all_with_offsets(bases, ["LYB4"], {"LYB4": cmps}, tolerance=100.0)
    assert round(offsets["LYB4"].dx) == -40 and offsets["LYB4"].count == 3
    mr = matches[3].for_layer("LYB4")
    assert mr.is_match and mr.matched.image_path.name == "ca.jpg"


def test_large_systematic_offset_auto_corrected():
    """허용오차보다 큰 일정 shift(+150)도 4쌍이 일관되면 자동 보정해 매칭한다."""
    bases = [
        _rec("LYA4", "W1", 1, 1, 1000.0, 0.0),
        _rec("LYA4", "W1", 3, 3, 1000.0, 0.0),
        _rec("LYA4", "W1", 5, 5, 1000.0, 0.0),
        _rec("LYA4", "W1", 1, 5, 1000.0, 0.0),
    ]
    cmps = [
        _rec("LYB4", "W1", 1, 1, 1150.0, 0.0, name="a.jpg"),
        _rec("LYB4", "W1", 3, 3, 1150.0, 0.0, name="b.jpg"),
        _rec("LYB4", "W1", 5, 5, 1150.0, 0.0, name="c.jpg"),
        _rec("LYB4", "W1", 1, 5, 1150.0, 0.0, name="d.jpg"),
    ]
    matches, offsets = match_all_with_offsets(bases, ["LYB4"], {"LYB4": cmps}, tolerance=100.0)
    assert offsets["LYB4"].count == 4 and round(offsets["LYB4"].dx) == -150
    assert all(m.for_layer("LYB4").is_match for m in matches)


def test_die_pitch_scale_offset_not_applied():
    """die pitch 급(예: +37247)으로 '일관된' 오프셋은 실제 정합오차가 아니라 die
    라벨링 불일치로 보고 보정을 적용하지 않는다(회귀 — 먼 die 오매칭 방지)."""
    bases = [
        _rec("LYA4", "W1", 1, 1, 1000.0, 0.0),
        _rec("LYA4", "W1", 3, 3, 1000.0, 0.0),
        _rec("LYA4", "W1", 5, 5, 1000.0, 0.0),
        _rec("LYA4", "W1", 1, 5, 1000.0, 0.0),
    ]
    cmps = [
        _rec("LYB4", "W1", 1, 1, 1000.0 + 37247.7, 0.0, name="a.jpg"),
        _rec("LYB4", "W1", 3, 3, 1000.0 + 37247.7, 0.0, name="b.jpg"),
        _rec("LYB4", "W1", 5, 5, 1000.0 + 37247.7, 0.0, name="c.jpg"),
        _rec("LYB4", "W1", 1, 5, 1000.0 + 37247.7, 0.0, name="d.jpg"),
    ]
    matches, offsets = match_all_with_offsets(bases, ["LYB4"], {"LYB4": cmps}, tolerance=100.0)
    assert offsets["LYB4"].count == 0  # 상한 초과로 보정 미적용
    assert not any(m.for_layer("LYB4").is_match for m in matches)


def test_inconsistent_offsets_not_applied():
    """표본이 흩어지면(MAD>tolerance) 보정하지 않아 큰 거리는 매칭되지 않는다."""
    bases = [
        _rec("LYA4", "W1", 1, 1, 1000.0, 0.0),
        _rec("LYA4", "W1", 3, 3, 1000.0, 0.0),
        _rec("LYA4", "W1", 5, 5, 1000.0, 0.0),
    ]
    cmps = [
        _rec("LYB4", "W1", 1, 1, 1150.0, 0.0),
        _rec("LYB4", "W1", 3, 3, 1600.0, 0.0),
        _rec("LYB4", "W1", 5, 5, 800.0, 0.0),
    ]
    matches, offsets = match_all_with_offsets(bases, ["LYB4"], {"LYB4": cmps}, tolerance=100.0)
    assert offsets["LYB4"].count == 0
    assert not any(m.for_layer("LYB4").is_match for m in matches)


def test_normalize_layer_order_prefix_and_rereview():
    assert layout.normalize_layer("1. LYA4") == ("LYA4", False)
    assert layout.normalize_layer("2. LYC3_재리뷰") == ("LYC3", True)
    assert layout.normalize_layer("1. LYA4_재리뷰") == ("LYA4", True)
    # 재재리뷰(반복 재)도 같은 canonical 로 정규화
    assert layout.normalize_layer("3. LYA4_재재리뷰") == ("LYA4", True)


def test_re_review_level():
    assert layout.re_review_level("1. LYA4") == 0
    assert layout.re_review_level("1. LYA4_재리뷰") == 1
    assert layout.re_review_level("2. LYA4_재재리뷰") == 2
    assert layout.re_review_level("3. LYA4_재재재리뷰") == 3
    assert layout.re_review_level("LYA4_rereview") == 1
    assert layout.re_review_level("LYA4_re-re-review") == 2


def test_build_grid_places_known_layers():
    grid = layout.build_grid(["LYA4", "LYB4", "LYA3"])
    assert grid[0][0] == "LYA4"
    assert grid[0][1] == "LYB4"
    # LYA3 는 두 번째 행 첫 칸
    assert grid[1][0] == "LYA3"


def test_build_grid_unknown_layers_appended():
    grid = layout.build_grid(["LYC3", "LYA4"])
    flat = [c for row in grid for c in row if c]
    assert "LYC3" in flat and "LYA4" in flat
