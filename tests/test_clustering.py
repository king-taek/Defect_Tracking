"""defect 클러스터링 + layer 간 교차 매칭 단위 테스트(순수 로직)."""

from __future__ import annotations

from pathlib import Path

from app.clustering import (
    CLUSTER_RADIUS,
    Cluster,
    cluster_records,
    cross_layer_groups,
)
from app.models import DefectRecord


def _rec(name: str, layer: str, col: int, row: int, x: float, y: float, wafer: str = "W1") -> DefectRecord:
    return DefectRecord(
        image_path=Path(f"/{name}.jpg"),
        wafer_id=wafer,
        layer=layer,
        layer_folder=layer,
        col=col,
        row=row,
        x=x,
        y=y,
    )


def test_cluster_merges_within_radius():
    # 같은 die 안 거리 30(<50) → 하나로.
    a = _rec("a", "L1", 1, 1, 0.0, 0.0)
    b = _rec("b", "L1", 1, 1, 30.0, 0.0)
    clusters = cluster_records([a, b])
    assert len(clusters) == 1
    assert clusters[0].extra_count == 1
    assert len(clusters[0].members) == 2


def test_cluster_separates_at_boundary():
    # 거리 정확히 50 → 미만이 아니므로 분리.
    a = _rec("a", "L1", 1, 1, 0.0, 0.0)
    b = _rec("b", "L1", 1, 1, 50.0, 0.0)
    clusters = cluster_records([a, b])
    assert len(clusters) == 2
    assert all(c.extra_count == 0 for c in clusters)


def test_cluster_different_die_not_merged():
    a = _rec("a", "L1", 1, 1, 0.0, 0.0)
    b = _rec("b", "L1", 2, 2, 0.0, 0.0)
    assert len(cluster_records([a, b])) == 2


def test_cluster_no_coords_is_singleton():
    bad = DefectRecord(image_path=Path("/x.jpg"), wafer_id="W1", layer="L1", layer_folder="L1")
    good = _rec("g", "L1", 1, 1, 0.0, 0.0)
    clusters = cluster_records([bad, good])
    assert len(clusters) == 2


def test_cluster_representative_is_deterministic():
    # 이름순 첫 항목이 대표.
    a = _rec("zzz", "L1", 1, 1, 0.0, 0.0)
    b = _rec("aaa", "L1", 1, 1, 10.0, 0.0)
    clusters = cluster_records([a, b])
    assert clusters[0].representative.image_path == Path("/aaa.jpg")


def test_cross_layer_matches_between_layers():
    # 기준 layer 없이 L1·L2 가 같은 위치에서 매칭.
    c1 = cluster_records([_rec("a", "L1", 1, 1, 0.0, 0.0)])
    c2 = cluster_records([_rec("b", "L2", 1, 1, 10.0, 0.0)])
    groups = cross_layer_groups({"L1": c1, "L2": c2}, tolerance=100.0)
    assert len(groups) == 1
    assert set(groups[0].keys()) == {"L1", "L2"}


def test_cross_layer_unmatched_is_individual():
    # 거리 초과 → 매칭 안 됨 → 각자 개별 그룹.
    c1 = cluster_records([_rec("a", "L1", 1, 1, 0.0, 0.0)])
    c2 = cluster_records([_rec("b", "L2", 1, 1, 500.0, 0.0)])
    groups = cross_layer_groups({"L1": c1, "L2": c2}, tolerance=100.0)
    assert len(groups) == 2
    assert all(len(g) == 1 for g in groups)


def test_cross_layer_one_cluster_per_layer_in_group():
    # L2 에 두 후보가 모두 L1 과 매칭 가능해도, 한 그룹엔 layer 당 1개만.
    c1 = cluster_records([_rec("a", "L1", 1, 1, 0.0, 0.0)])
    # L2 의 두 defect 은 서로 60 떨어져(>50) 별개 cluster.
    c2 = cluster_records([_rec("b", "L2", 1, 1, 10.0, 0.0), _rec("c", "L2", 1, 1, 70.0, 0.0)])
    assert len(c2) == 2
    groups = cross_layer_groups({"L1": c1, "L2": c2}, tolerance=100.0)
    # L1 은 가장 가까운 L2 하나와만 묶이고, 나머지 L2 는 개별.
    two_layer = [g for g in groups if len(g) == 2]
    assert len(two_layer) == 1
    assert two_layer[0]["L2"].representative.image_path == Path("/b.jpg")
    assert any(len(g) == 1 and "L2" in g for g in groups)


def test_cross_layer_different_wafer_not_matched():
    c1 = cluster_records([_rec("a", "L1", 1, 1, 0.0, 0.0, wafer="W1")])
    c2 = cluster_records([_rec("b", "L2", 1, 1, 0.0, 0.0, wafer="W2")])
    groups = cross_layer_groups({"L1": c1, "L2": c2}, tolerance=100.0)
    assert len(groups) == 2
