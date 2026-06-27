"""매칭 엔진 및 layer 정규화 테스트 (문서 Section 8.3 / 8.2)."""

from pathlib import Path

from app import layout
from app.matcher import match_base_against_layers
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


def test_normalize_layer_order_prefix_and_rereview():
    assert layout.normalize_layer("1. LYA4") == ("LYA4", False)
    assert layout.normalize_layer("2. LYC3_재리뷰") == ("LYC3", True)
    assert layout.normalize_layer("1. LYA4_재리뷰") == ("LYA4", True)


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
