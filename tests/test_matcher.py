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
    base = _rec("RDL4", "W1", 4, 5, 1000.0, 2000.0)
    cmp = _rec("PI4", "W1", 4, 5, 1050.0, 2000.0)  # 거리 50
    out = match_base_against_layers(base, ["PI4"], {"PI4": [cmp]}, tolerance=100.0)
    mr = out.for_layer("PI4")
    assert mr.is_match
    assert abs(mr.distance - 50.0) < 1e-6


def test_no_match_outside_tolerance():
    base = _rec("RDL4", "W1", 4, 5, 1000.0, 2000.0)
    cmp = _rec("PI4", "W1", 4, 5, 1200.0, 2000.0)  # 거리 200 > 100
    out = match_base_against_layers(base, ["PI4"], {"PI4": [cmp]}, tolerance=100.0)
    assert not out.for_layer("PI4").is_match


def test_no_match_different_die():
    base = _rec("RDL4", "W1", 4, 5, 1000.0, 2000.0)
    cmp = _rec("PI4", "W1", 3, 3, 1000.0, 2000.0)  # die 다름
    out = match_base_against_layers(base, ["PI4"], {"PI4": [cmp]}, tolerance=100.0)
    assert not out.for_layer("PI4").is_match


def test_no_match_different_wafer():
    base = _rec("RDL4", "W1", 4, 5, 1000.0, 2000.0)
    cmp = _rec("PI4", "W2", 4, 5, 1000.0, 2000.0)  # wafer 다름
    out = match_base_against_layers(base, ["PI4"], {"PI4": [cmp]}, tolerance=100.0)
    assert not out.for_layer("PI4").is_match


def test_picks_nearest_candidate():
    base = _rec("RDL4", "W1", 4, 5, 1000.0, 2000.0)
    far = _rec("PI4", "W1", 4, 5, 1090.0, 2000.0, name="far.jpg")
    near = _rec("PI4", "W1", 4, 5, 1010.0, 2000.0, name="near.jpg")
    out = match_base_against_layers(base, ["PI4"], {"PI4": [far, near]}, tolerance=100.0)
    mr = out.for_layer("PI4")
    assert mr.matched.image_path.name == "near.jpg"
    assert mr.ambiguous is False


def test_ambiguous_when_two_candidates_tie():
    base = _rec("RDL4", "W1", 4, 5, 1000.0, 2000.0)
    a = _rec("PI4", "W1", 4, 5, 1050.0, 2000.0, name="a.jpg")  # 거리 50
    b = _rec("PI4", "W1", 4, 5, 950.0, 2000.0, name="b.jpg")   # 거리 50 (반대편)
    out = match_base_against_layers(base, ["PI4"], {"PI4": [a, b]}, tolerance=100.0)
    mr = out.for_layer("PI4")
    assert mr.is_match
    assert mr.ambiguous is True


def test_not_ambiguous_with_clear_winner():
    base = _rec("RDL4", "W1", 4, 5, 1000.0, 2000.0)
    near = _rec("PI4", "W1", 4, 5, 1005.0, 2000.0, name="near.jpg")  # 5
    far = _rec("PI4", "W1", 4, 5, 1080.0, 2000.0, name="far.jpg")    # 80
    out = match_base_against_layers(base, ["PI4"], {"PI4": [near, far]}, tolerance=100.0)
    assert out.for_layer("PI4").ambiguous is False


def test_die_within_one_matches():
    """die index 가 (±1) 어긋나도 매칭된다(원본 AOI 알고리즘)."""
    base = _rec("RDL4", "W1", 4, 5, 1000.0, 2000.0)
    cmp = _rec("PI4", "W1", 5, 6, 1010.0, 2000.0)  # die +1,+1, 거리 10
    out = match_base_against_layers(base, ["PI4"], {"PI4": [cmp]}, tolerance=100.0)
    assert out.for_layer("PI4").is_match


def test_die_two_off_still_no_match():
    base = _rec("RDL4", "W1", 4, 5, 1000.0, 2000.0)
    cmp = _rec("PI4", "W1", 6, 7, 1000.0, 2000.0)  # die +2,+2 → 범위 밖
    out = match_base_against_layers(base, ["PI4"], {"PI4": [cmp]}, tolerance=100.0)
    assert not out.for_layer("PI4").is_match


def test_median_offset_corrects_selection():
    """layer 간 계통적 이동이 있으면, 그 중앙값에 맞는 후보를 선택한다."""
    # die 를 2칸 간격으로 띄워 die±1 이웃이 겹치지 않게 한다.
    bases = [
        _rec("RDL4", "W1", 1, 1, 1000.0, 0.0),
        _rec("RDL4", "W1", 3, 3, 1000.0, 0.0),
        _rec("RDL4", "W1", 5, 5, 1000.0, 0.0),
        _rec("RDL4", "W1", 7, 7, 1000.0, 0.0),  # 같은 die 후보 2개(모호)
    ]
    cmps = [
        _rec("PI4", "W1", 1, 1, 1040.0, 0.0, name="c1.jpg"),
        _rec("PI4", "W1", 3, 3, 1040.0, 0.0, name="c2.jpg"),
        _rec("PI4", "W1", 5, 5, 1040.0, 0.0, name="c3.jpg"),
        _rec("PI4", "W1", 7, 7, 1045.0, 0.0, name="ca.jpg"),  # raw 45, 보정후 잔차 5
        _rec("PI4", "W1", 7, 7, 965.0, 0.0, name="cb.jpg"),   # raw 35, 보정후 잔차 75
    ]
    matches, offsets = match_all_with_offsets(bases, ["PI4"], {"PI4": cmps}, tolerance=100.0)
    assert round(offsets["PI4"].dx) == -40 and offsets["PI4"].count == 3
    mr = matches[3].for_layer("PI4")
    assert mr.is_match and mr.matched.image_path.name == "ca.jpg"


def test_normalize_layer_order_prefix_and_rereview():
    assert layout.normalize_layer("1. RDL4") == ("RDL4", False)
    assert layout.normalize_layer("2. PIDS3_재리뷰") == ("PIDS3", True)
    assert layout.normalize_layer("1. RDL4_재리뷰") == ("RDL4", True)


def test_build_grid_places_known_layers():
    grid = layout.build_grid(["RDL4", "PI4", "RDL3"])
    assert grid[0][0] == "RDL4"
    assert grid[0][1] == "PI4"
    # RDL3 는 두 번째 행 첫 칸
    assert grid[1][0] == "RDL3"


def test_build_grid_unknown_layers_appended():
    grid = layout.build_grid(["PIDS3", "RDL4"])
    flat = [c for row in grid for c in row if c]
    assert "PIDS3" in flat and "RDL4" in flat
