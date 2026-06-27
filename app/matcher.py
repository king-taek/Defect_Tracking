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

# layer -> {(norm_wafer, col, row): [record, ...]}
DieIndex = dict[str, dict[tuple[str, int, int], list[DefectRecord]]]
# layer -> {norm_wafer: 좌표 추출 실패(not ok) record 수}
FailIndex = dict[str, dict[str, int]]


def _norm_wafer(wafer_id: str) -> str:
    """layer 간 wafer 폴더명 표기 차이(대소문자/공백)를 흡수해 매칭을 완화."""
    return wafer_id.strip().lower()


def build_die_index(
    records_by_layer: dict[str, list[DefectRecord]],
    layers: list[str],
) -> DieIndex:
    """비교 layer 들을 (norm_wafer, col, row) 키로 인덱싱한다(좌표 OK 인 record 만)."""
    index: DieIndex = {}
    for layer in layers:
        bucket: dict[tuple[str, int, int], list[DefectRecord]] = defaultdict(list)
        for rec in records_by_layer.get(layer, []):
            if rec.ok:
                bucket[(_norm_wafer(rec.wafer_id), rec.col, rec.row)].append(  # type: ignore[index]
                    rec
                )
        index[layer] = bucket
    return index


def build_fail_index(
    records_by_layer: dict[str, list[DefectRecord]],
    layers: list[str],
) -> FailIndex:
    """비교 layer·wafer 별 좌표 추출 실패(not ok) record 수를 센다.

    실패 record 는 col/row 가 None 이라 die 단위로 키를 만들 수 없으므로
    (layer, wafer) 단위로 근사 집계한다(진단 표시용).
    """
    index: FailIndex = {}
    for layer in layers:
        bucket: dict[str, int] = defaultdict(int)
        for rec in records_by_layer.get(layer, []):
            if not rec.ok:
                bucket[_norm_wafer(rec.wafer_id)] += 1
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


def find_nearest(
    base: DefectRecord,
    candidates: list[DefectRecord],
) -> tuple[DefectRecord | None, float | None]:
    """허용오차와 무관하게 같은 die 후보 중 최근접 record 를 반환(진단용)."""
    best: DefectRecord | None = None
    best_dist: float | None = None
    for cand in candidates:
        dist = base.distance_to(cand)
        if dist is None:
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
    fail_index: FailIndex | None = None,
) -> BaseDefectMatches:
    """기준 defect 1개를 모든 비교 layer 와 매칭.

    index/fail_index 를 미리 만들어 넘기면 재사용한다(match_all 에서 사용).
    넘기지 않으면 이 호출에 한해 즉석에서 인덱싱한다.
    """
    idx = index if index is not None else build_die_index(records_by_layer, compare_layers)
    fidx = (
        fail_index
        if fail_index is not None
        else build_fail_index(records_by_layer, compare_layers)
    )
    result = BaseDefectMatches(base=base)
    for layer in compare_layers:
        matched: DefectRecord | None = None
        dist: float | None = None
        nearest: DefectRecord | None = None
        nearest_dist: float | None = None
        die_candidates = 0
        failed_in_die = 0
        if base.ok:
            key = (_norm_wafer(base.wafer_id), base.col, base.row)
            candidates = idx.get(layer, {}).get(key, [])  # type: ignore[arg-type]
            die_candidates = len(candidates)
            matched, dist = find_best_match(base, candidates, tolerance)
            if matched is None:
                nearest, nearest_dist = find_nearest(base, candidates)
                failed_in_die = fidx.get(layer, {}).get(_norm_wafer(base.wafer_id), 0)
        result.results.append(
            MatchResult(
                compare_layer=layer,
                base=base,
                matched=matched,
                distance=dist,
                nearest=nearest,
                nearest_distance=nearest_dist,
                die_candidates=die_candidates,
                failed_in_die=failed_in_die,
            )
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
    fail_index = build_fail_index(records_by_layer, compare_layers)
    return [
        match_base_against_layers(
            base,
            compare_layers,
            records_by_layer,
            tolerance,
            index=index,
            fail_index=fail_index,
        )
        for base in base_records
    ]
