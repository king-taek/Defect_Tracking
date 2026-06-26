"""매칭 엔진 (문서 Section 8.3).

기준 layer 의 각 defect 에 대해 비교 layer 에서 다음 조건을 만족하는 defect 를 찾는다:
  1. wafer ID 동일
  2. die 위치 (col,row) 동일
  3. local x,y 좌표 거리 <= tolerance (기본 100, 사용자 조정)

여러 후보가 있으면 가장 가까운 것을 선택한다. 대량 이미지에서도 빠르도록(Section 10)
비교 layer 의 record 를 (wafer, col, row) 키로 한 번만 인덱싱한 뒤 조회한다.
모든 계산은 메모리에서만 수행하며 원본 파일을 수정하지 않는다.
"""

from __future__ import annotations

from collections import defaultdict

from app.models import BaseDefectMatches, DefectRecord, MatchResult

# layer -> {(wafer_id, col, row): [record, ...]}
DieIndex = dict[str, dict[tuple[str, int, int], list[DefectRecord]]]


def build_die_index(
    records_by_layer: dict[str, list[DefectRecord]],
    layers: list[str],
) -> DieIndex:
    """비교 layer 들을 (wafer, col, row) 키로 인덱싱한다(좌표 OK 인 record 만)."""
    index: DieIndex = {}
    for layer in layers:
        bucket: dict[tuple[str, int, int], list[DefectRecord]] = defaultdict(list)
        for rec in records_by_layer.get(layer, []):
            if rec.ok:
                bucket[(rec.wafer_id, rec.col, rec.row)].append(rec)  # type: ignore[index]
        index[layer] = bucket
    return index


def find_best_match(
    base: DefectRecord,
    candidates: list[DefectRecord],
    tolerance: float,
) -> tuple[DefectRecord | None, float | None]:
    """후보들 중 base 와 거리 <= tolerance 인 최근접 record 를 반환."""
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
    *,
    index: DieIndex | None = None,
) -> BaseDefectMatches:
    """기준 defect 1개를 모든 비교 layer 와 매칭.

    index 를 미리 만들어 넘기면 재사용한다(match_all 에서 사용). 넘기지 않으면
    이 호출에 한해 즉석에서 인덱싱한다.
    """
    idx = index if index is not None else build_die_index(records_by_layer, compare_layers)
    result = BaseDefectMatches(base=base)
    for layer in compare_layers:
        matched: DefectRecord | None = None
        dist: float | None = None
        if base.ok:
            candidates = idx.get(layer, {}).get(base.die_key_full, [])
            matched, dist = find_best_match(base, candidates, tolerance)
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
    """기준 layer 의 모든 defect 에 대해 매칭 결과 목록을 만든다.

    비교 layer 인덱스를 한 번만 만들어 전체 기준 record 에 재사용한다.
    """
    index = build_die_index(records_by_layer, compare_layers)
    return [
        match_base_against_layers(
            base, compare_layers, records_by_layer, tolerance, index=index
        )
        for base in base_records
    ]
