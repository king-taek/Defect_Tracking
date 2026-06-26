"""매칭 엔진 (문서 Section 8.3).

기준 layer 의 각 defect 에 대해 비교 layer 에서 다음 조건을 만족하는 defect 를 찾는다:
  1. wafer ID 동일
  2. die 위치 (col,row) 동일
  3. local x,y 좌표 거리 <= tolerance (기본 100, 사용자 조정)

여러 후보가 있으면 가장 가까운 것을 선택한다. 모든 계산은 메모리에서만 수행하며
원본 파일을 수정하지 않는다.
"""

from __future__ import annotations

from collections import defaultdict

from app.models import BaseDefectMatches, DefectRecord, MatchResult


def _index_by_wafer_die(
    records: list[DefectRecord],
) -> dict[tuple[str, int, int], list[DefectRecord]]:
    """(wafer_id, col, row) -> 정상 파싱된 record 목록. 빠른 후보 조회용."""
    index: dict[tuple[str, int, int], list[DefectRecord]] = defaultdict(list)
    for rec in records:
        if rec.ok:
            index[(rec.wafer_id, rec.col, rec.row)].append(rec)  # type: ignore[index]
    return index


def find_best_match(
    base: DefectRecord,
    candidates: list[DefectRecord],
    tolerance: float,
) -> tuple[DefectRecord | None, float | None]:
    """후보들 중 base 와 같은 die 이고 거리 <= tolerance 인 최근접 record 를 반환."""
    best: DefectRecord | None = None
    best_dist: float | None = None
    for cand in candidates:
        dist = base.distance_to(cand)
        if dist is None or dist > tolerance:
            continue
        if best_dist is None or dist < best_dist:
            best = cand
            best_dist = dist
    return best, best_dist


def match_base_against_layers(
    base: DefectRecord,
    compare_layers: list[str],
    records_by_layer: dict[str, list[DefectRecord]],
    tolerance: float,
) -> BaseDefectMatches:
    """기준 defect 1개를 모든 비교 layer 와 매칭."""
    result = BaseDefectMatches(base=base)
    for layer in compare_layers:
        layer_records = records_by_layer.get(layer, [])
        if base.ok:
            same_die = [
                r
                for r in layer_records
                if r.ok and r.wafer_id == base.wafer_id and r.die_key == base.die_key
            ]
            matched, dist = find_best_match(base, same_die, tolerance)
        else:
            matched, dist = None, None
        result.results.append(
            MatchResult(compare_layer=layer, base=base, matched=matched, distance=dist)
        )
    return result


def match_all(
    base_records: list[DefectRecord],
    compare_layers: list[str],
    records_by_layer: dict[str, list[DefectRecord]],
    tolerance: float,
) -> list[BaseDefectMatches]:
    """기준 layer 의 모든 defect 에 대해 매칭 결과 목록을 만든다."""
    return [
        match_base_against_layers(base, compare_layers, records_by_layer, tolerance)
        for base in base_records
    ]
