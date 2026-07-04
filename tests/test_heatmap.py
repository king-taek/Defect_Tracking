"""히트맵 순수 로직 테스트 (항목 4·5) — die 밀도 집계와 하위셀 분할."""

from __future__ import annotations

from pathlib import Path

from app import heatmap
from app.heatmap import HeatKey
from app.models import DefectRecord


def _rec(col, row, x, y):
    return DefectRecord(
        image_path=Path("/x.jpg"), wafer_id="W1", layer="LYA4", layer_folder="LYA4",
        col=col, row=row, x=x, y=y,
    )


def test_should_subdivide_threshold():
    assert heatmap.should_subdivide(1)
    assert heatmap.should_subdivide(49)
    assert not heatmap.should_subdivide(50)
    assert not heatmap.should_subdivide(100)
    assert not heatmap.should_subdivide(0)


def test_local_ranges():
    recs = [_rec(0, 0, -10.0, 5.0), _rec(0, 0, 30.0, -5.0)]
    xr, yr = heatmap.local_ranges(recs)
    assert xr == (-10.0, 30.0)
    assert yr == (-5.0, 5.0)


def test_local_ranges_empty():
    assert heatmap.local_ranges([]) == ((0.0, 1.0), (0.0, 1.0))


def test_subcell_of_corners():
    xr, yr = (0.0, 100.0), (0.0, 100.0)
    assert heatmap.subcell_of(0.0, 0.0, xr, yr) == (0, 0)
    # 우하단 끝값은 마지막 버킷(3,4)으로 clamp
    assert heatmap.subcell_of(100.0, 100.0, xr, yr) == (heatmap.SUB_COLS - 1, heatmap.SUB_ROWS - 1)
    # 중앙
    sc, sr = heatmap.subcell_of(50.0, 50.0, xr, yr)
    assert 0 <= sc < heatmap.SUB_COLS and 0 <= sr < heatmap.SUB_ROWS


def test_group_defects_die_level():
    entries = [(0, _rec(1, 2, 0, 0)), (1, _rec(1, 2, 5, 5)), (2, _rec(3, 4, 0, 0))]
    groups = heatmap.group_defects(entries, subdivide=False)
    assert groups[HeatKey(1, 2)] == [0, 1]
    assert groups[HeatKey(3, 4)] == [2]
    # 미분할이면 하위셀 정보 없음
    assert all(not k.subdivided for k in groups)


def test_group_defects_subdivided_splits_within_die():
    # 같은 die(1,2) 안에서 local 좌표가 크게 다른 두 defect → 다른 하위셀로 분리.
    entries = [(0, _rec(1, 2, 0.0, 0.0)), (1, _rec(1, 2, 100.0, 100.0))]
    xr, yr = (0.0, 100.0), (0.0, 100.0)
    groups = heatmap.group_defects(entries, subdivide=True, x_range=xr, y_range=yr)
    keys = list(groups.keys())
    assert len(keys) == 2, "다른 위치의 defect 은 다른 하위셀로 나뉘어야 한다"
    assert all(k.col == 1 and k.row == 2 and k.subdivided for k in keys)


def test_group_defects_skips_missing_coords():
    r = DefectRecord(image_path=Path("/x.jpg"), wafer_id="W1", layer="LYA4",
                     layer_folder="LYA4", col=None, row=None)
    groups = heatmap.group_defects([(0, r)], subdivide=False)
    assert groups == {}
