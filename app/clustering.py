"""defect 근접 클러스터링 + layer 간 교차 매칭 (순수 로직, UI 무관).

- `cluster_records`: 같은 wafer·같은 die 안에서 local 좌표 거리가 `CLUSTER_RADIUS` 미만인
  defect 들을 하나로 묶는다(대표 1개 + 나머지). 히트맵에서 근접 중복 defect 을 대표 1장 +
  "+n" 으로 접어 보여주기 위한 것.
- `cross_layer_groups`: 여러 layer 의 cluster 대표들을 layer 간에 매칭(그리디)해, 한 위치의
  defect 들을 "어느 layer 끼리 같은 defect 인지" 그룹으로 묶는다. 특정 기준 layer 에 종속되지
  않는다("전체 defect 보기"용).

매칭/거리 기준은 `matcher` 와 동일한 개념(같은 wafer·die ±1·local 좌표 거리)이며,
거리 계산은 `DefectRecord.distance_to`(app/models.py)를 재사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from app.models import BaseDefectMatches, DefectRecord, MatchResult

# 같은 defect 으로 볼 local 좌표 거리 임계값(미만이면 하나로 묶음).
CLUSTER_RADIUS = 50.0
# 교차 매칭 시 die 이웃 탐색 범위(±DIE_TOL). matcher.DEFAULT_DIE_TOL 과 동일 개념.
_DIE_TOL = 1


def _norm_wafer(wafer_id: str) -> str:
    return (wafer_id or "").strip().lower()


@dataclass
class Cluster:
    """근접 defect 묶음 — 대표 1개 + 전체 members(대표 포함)."""

    representative: DefectRecord
    members: list[DefectRecord] = field(default_factory=list)

    @property
    def extra_count(self) -> int:
        """대표 외 추가 defect 수('+n' 표기용)."""
        return max(0, len(self.members) - 1)


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, a: int) -> int:
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _rep_of(members: list[DefectRecord]) -> DefectRecord:
    """대표 선택 — image_path 이름순 첫 항목(결정론)."""
    return min(members, key=lambda r: str(r.image_path))


def cluster_records(
    records: Iterable[DefectRecord], radius: float = CLUSTER_RADIUS
) -> list[Cluster]:
    """같은 wafer·die 안에서 거리 < radius 인 record 를 union-find 로 묶는다.

    좌표가 없는(ok=False) record 는 각자 단독 cluster. 반환은 대표 image_path 이름순 정렬.
    """
    recs = list(records)
    clusters: list[Cluster] = []

    # 좌표 없는 record 는 단독.
    ok = [r for r in recs if r.ok]
    for r in recs:
        if not r.ok:
            clusters.append(Cluster(representative=r, members=[r]))

    if ok:
        uf = _UnionFind(len(ok))
        # 같은 (wafer, die) 버킷 안에서만 쌍 비교.
        buckets: dict[tuple[str, int, int], list[int]] = {}
        for i, r in enumerate(ok):
            buckets.setdefault((_norm_wafer(r.wafer_id), int(r.col), int(r.row)), []).append(i)
        for idxs in buckets.values():
            for a in range(len(idxs)):
                for b in range(a + 1, len(idxs)):
                    ia, ib = idxs[a], idxs[b]
                    d = ok[ia].distance_to(ok[ib])
                    if d is not None and d < radius:
                        uf.union(ia, ib)
        comps: dict[int, list[DefectRecord]] = {}
        for i, r in enumerate(ok):
            comps.setdefault(uf.find(i), []).append(r)
        for members in comps.values():
            clusters.append(Cluster(representative=_rep_of(members), members=members))

    clusters.sort(key=lambda c: str(c.representative.image_path))
    return clusters


def _clusters_match(a: Cluster, b: Cluster, tolerance: float) -> Optional[float]:
    """두 cluster 대표가 매칭되면 거리, 아니면 None. 같은 wafer·die ±DIE_TOL·거리<=tol."""
    ra, rb = a.representative, b.representative
    if not ra.ok or not rb.ok:
        return None
    if _norm_wafer(ra.wafer_id) != _norm_wafer(rb.wafer_id):
        return None
    if abs(int(ra.col) - int(rb.col)) > _DIE_TOL or abs(int(ra.row) - int(rb.row)) > _DIE_TOL:
        return None
    d = ra.distance_to(rb)
    if d is None or d > tolerance:
        return None
    return d


def cross_layer_groups(
    layer_to_clusters: dict[str, list[Cluster]], tolerance: float
) -> list[dict[str, Cluster]]:
    """layer 별 cluster 들을 layer 간에 매칭해 그룹으로 묶는다(기준 layer 없음).

    거리 오름차순 그리디 union: 서로 다른 layer 의 cluster 두 개가 매칭되고, 두 그룹에
    겹치는 layer 가 없을 때만 합친다(그룹당 layer 최대 1개). 매칭 안 된 cluster 는 원소
    1개짜리 그룹으로 개별 반환. 반환 순서는 결정론(각 그룹 대표 image_path 이름순).
    """
    # 평탄화: (layer, cluster) 노드 목록.
    nodes: list[tuple[str, Cluster]] = []
    for layer, clusters in layer_to_clusters.items():
        for c in clusters:
            nodes.append((layer, c))
    n = len(nodes)
    if n == 0:
        return []

    uf = _UnionFind(n)
    group_layers: dict[int, set[str]] = {i: {nodes[i][0]} for i in range(n)}

    # 후보 간선(서로 다른 layer, 매칭) 을 거리 오름차순으로.
    edges: list[tuple[float, int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            if nodes[i][0] == nodes[j][0]:
                continue
            d = _clusters_match(nodes[i][1], nodes[j][1], tolerance)
            if d is not None:
                edges.append((d, i, j))
    edges.sort(key=lambda e: (e[0], e[1], e[2]))

    for _d, i, j in edges:
        ri, rj = uf.find(i), uf.find(j)
        if ri == rj:
            continue
        if group_layers[ri] & group_layers[rj]:
            continue  # 같은 layer 중복 → 합치지 않음(그룹당 layer 1개 유지)
        uf.union(ri, rj)
        root = uf.find(ri)
        merged = group_layers[ri] | group_layers[rj]
        group_layers[root] = merged

    comps: dict[int, dict[str, Cluster]] = {}
    for i, (layer, cluster) in enumerate(nodes):
        comps.setdefault(uf.find(i), {})[layer] = cluster

    groups = list(comps.values())
    groups.sort(
        key=lambda g: min(str(c.representative.image_path) for c in g.values())
    )
    return groups


def _merge_member_results(members: list[BaseDefectMatches]) -> list[MatchResult]:
    """클러스터 멤버들의 비교 결과를 layer 별 best 매치로 병합한다.

    각 layer 에 대해 매칭된 것(is_match) 중 거리 최소를 우선, 없으면 첫 후보를 쓴다.
    → 대표가 개별로는 미매칭이어도 멤버가 매치했으면 그 매치가 반영된다.
    """
    order: list[str] = []
    by_layer: dict[str, list[MatchResult]] = {}
    for m in members:
        for r in m.results:
            if r.compare_layer not in by_layer:
                by_layer[r.compare_layer] = []
                order.append(r.compare_layer)
            by_layer[r.compare_layer].append(r)
    merged: list[MatchResult] = []
    for layer in order:
        cands = by_layer[layer]
        matched = [c for c in cands if c.is_match]
        if matched:
            best = min(matched, key=lambda c: (c.distance if c.distance is not None else 1e18))
        else:
            best = cands[0]
        merged.append(best)
    return merged


def collapse_matches(
    matches: list[BaseDefectMatches], radius: float = CLUSTER_RADIUS
) -> list[BaseDefectMatches]:
    """근접(같은 wafer·die·거리<radius) 기준 defect 을 대표 1개로 접는다.

    각 클러스터마다: 대표 base = `cluster.representative`(image_path 이름순, 결정론),
    결과는 멤버들의 layer 별 best 매치로 병합, `base_cluster` 에 전체 멤버를 담는다.
    반환 순서는 원래 등장 순서(클러스터 내 최소 index) 기준으로 안정 정렬.
    """
    if not matches:
        return []
    by_base = {id(m.base): m for m in matches}
    index_of = {id(m.base): i for i, m in enumerate(matches)}
    clusters = cluster_records([m.base for m in matches], radius)
    collapsed: list[tuple[int, BaseDefectMatches]] = []
    for cl in clusters:
        member_matches = [by_base[id(b)] for b in cl.members]
        results = _merge_member_results(member_matches)
        bdm = BaseDefectMatches(
            base=cl.representative,
            results=results,
            base_cluster=cl,
        )
        order_idx = min(index_of[id(b)] for b in cl.members)
        collapsed.append((order_idx, bdm))
    collapsed.sort(key=lambda t: t[0])
    return [bdm for _, bdm in collapsed]
