"""매칭 엔진 (문서 Section 8.3 + 원본 AOI 도구 Module_Compare 알고리즘).

기준 layer 의 각 defect 에 대해 비교 layer 에서 다음 조건을 만족하는 defect 를 찾는다:
  1. wafer ID 동일
  2. die 위치 (col,row) 가 ±DIE_TOL(기본 1) 이내 — 경계 정렬 차이를 흡수
  3. local x,y 거리(아래 '정합오차 보정' 적용) <= tolerance

원본 AOI 도구의 비교 알고리즘에서 가져온 개선:
  - **die ±1 허용**: 두 layer 의 die index 가 1 칸 어긋나도 매칭.
  - **layer 간 전역 정합오차(median offset) 보정**: 1:1 로 분명히 매칭되는 쌍들로
    두 layer 사이의 계통적 이동량(중앙값 dx,dy)을 추정하고, 그 이동량을 뺀 잔차로
    게이팅·선택한다. 두 스캔 사이에 일정한 위치 오프셋이 있어도 매칭이 성립한다.

대량 이미지에서도 빠르도록 비교 layer record 를 (wafer, col, row) 키로 한 번만
인덱싱한다. 모든 계산은 메모리에서만 수행하며 원본 파일을 수정하지 않는다.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass

from app.models import BaseDefectMatches, DefectRecord, MatchResult

# layer -> {(norm_wafer, col, row): [record, ...]}
DieIndex = dict[str, dict[tuple[str, int, int], list[DefectRecord]]]
# layer -> {norm_wafer: 좌표 추출 실패(not ok) record 수}
FailIndex = dict[str, dict[str, int]]

# die index 허용 오차(±). 0 이면 정확 일치.
DEFAULT_DIE_TOL = 1


@dataclass(frozen=True)
class LayerOffset:
    """비교 layer 의 기준 layer 대비 전역 정합오차(중앙값)와 표본 수."""

    dx: float = 0.0
    dy: float = 0.0
    count: int = 0  # 추정에 쓰인 1:1 매칭 쌍 수


def _norm_wafer(wafer_id: str) -> str:
    """layer 간 wafer 폴더명 표기 차이(대소문자/공백)를 흡수해 매칭을 완화."""
    return wafer_id.strip().lower()


def _gather_candidates(
    base: DefectRecord,
    layer_bucket: dict,
    die_tol: int,
) -> list[DefectRecord]:
    """base 의 die 주변 ±die_tol 범위 비교 후보를 모은다(같은 wafer)."""
    if base.col is None or base.row is None:
        return []
    w = _norm_wafer(base.wafer_id)
    out: list[DefectRecord] = []
    for dc in range(-die_tol, die_tol + 1):
        for dr in range(-die_tol, die_tol + 1):
            out.extend(layer_bucket.get((w, base.col + dc, base.row + dr), []))
    return out


# 정합오차를 신뢰하려면 최소 이만큼의 1:1 표본이 있어야 한다(단일 쌍 오적용 방지).
_MIN_OFFSET_SAMPLES = 3


def _mad(values: list[float], center: float) -> float:
    """median absolute deviation — 표본 일관성(흩어짐) 측정."""
    return statistics.median([abs(v - center) for v in values]) if values else 0.0


def _estimate_offset(
    dxs: list[float], dys: list[float], tolerance: float
) -> LayerOffset:
    """1:1 매칭 쌍의 dx,dy 표본에서 전역 정합오차(중앙값)를 추정한다.

    오적용을 막기 위해 (1) 표본 수 ≥ _MIN_OFFSET_SAMPLES, (2) 표본이 일관(MAD ≤
    tolerance)할 때만 보정값을 만든다. 그 외에는 보정 없음(LayerOffset()).
    """
    if len(dxs) >= _MIN_OFFSET_SAMPLES:
        mdx = statistics.median(dxs)
        mdy = statistics.median(dys)
        if _mad(dxs, mdx) <= tolerance and _mad(dys, mdy) <= tolerance:
            return LayerOffset(mdx, mdy, len(dxs))
    return LayerOffset()


def compute_layer_offsets(
    base_records: list[DefectRecord],
    compare_layers: list[str],
    index: DieIndex,
    tolerance: float,
    die_tol: int = DEFAULT_DIE_TOL,
) -> dict[str, LayerOffset]:
    """비교 layer 별 전역 정합오차(중앙값 dx,dy)를 die-단일 매칭 쌍으로 추정한다.

    die 주변(±die_tol)에 후보가 **정확히 1개**인 경우만 표본으로 사용한다(모호 배제).
    거리 게이트를 두지 않으므로 **허용오차보다 큰 계통적 shift 도 추정**할 수 있다.
    """
    offsets: dict[str, LayerOffset] = {}
    for layer in compare_layers:
        bucket = index.get(layer, {})
        dxs: list[float] = []
        dys: list[float] = []
        for base in base_records:
            if not base.ok:
                continue
            cands = [c for c in _gather_candidates(base, bucket, die_tol) if c.ok]
            if len(cands) == 1:
                dxs.append(base.x - cands[0].x)  # type: ignore[operator]
                dys.append(base.y - cands[0].y)  # type: ignore[operator]
        offsets[layer] = _estimate_offset(dxs, dys, tolerance)
    return offsets


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


# 두 후보의 잔차 차가 이 값 미만이면 "동률(모호)"로 본다(µm).
_AMBIGUOUS_EPSILON = 1.0


def find_nearest(
    base: DefectRecord,
    candidates: list[DefectRecord],
) -> tuple[DefectRecord | None, float | None]:
    """허용오차와 무관하게 후보 중 최근접 record 를 반환(진단용, raw 거리)."""
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


def _select_match(
    base: DefectRecord,
    candidates: list[DefectRecord],
    tolerance: float,
    offset: LayerOffset,
) -> tuple[DefectRecord | None, float | None, bool]:
    """정합오차(offset)를 보정한 잔차 기준으로 최적 후보를 고른다.

    잔차 = hypot(dx-offset.dx, dy-offset.dy) <= tolerance 인 후보 중 잔차 최소.
    반환 distance 는 보정 전 실제 거리(raw)로 보고한다(사용자에게 실제 분리량 표시).
    offset 이 (0,0) 이면 raw 거리 기준 최근접과 동일하게 동작한다.
    """
    if not base.ok:
        return None, None, False
    best: DefectRecord | None = None
    best_resid: float | None = None
    best_raw: float | None = None
    resids: list[float] = []
    for c in candidates:
        if not c.ok:
            continue
        dx = base.x - c.x  # type: ignore[operator]
        dy = base.y - c.y  # type: ignore[operator]
        resid = math.hypot(dx - offset.dx, dy - offset.dy)
        if resid > tolerance:
            continue
        resids.append(resid)
        if best_resid is None or resid < best_resid:
            best_resid = resid
            best = c
            best_raw = math.hypot(dx, dy)
    ambiguous = (
        best is not None
        and sum(1 for r in resids if abs(r - best_resid) < _AMBIGUOUS_EPSILON) >= 2
    )
    return best, best_raw, ambiguous


def _build_result(
    base: DefectRecord,
    layer: str,
    candidates: list[DefectRecord],
    tolerance: float,
    offset: LayerOffset,
    failed_count: int,
) -> MatchResult:
    """미리 수집한 후보(candidates)로 한 layer 의 매칭 결과를 만든다.

    후보 수집을 호출자가 책임지므로(중복 수집 제거) 매칭 로직만 담당한다.
    """
    matched: DefectRecord | None = None
    dist: float | None = None
    nearest: DefectRecord | None = None
    nearest_dist: float | None = None
    failed_in_die = 0
    ambiguous = False
    if base.ok:
        matched, dist, ambiguous = _select_match(base, candidates, tolerance, offset)
        if matched is None:
            nearest, nearest_dist = find_nearest(base, candidates)
            failed_in_die = failed_count
    return MatchResult(
        compare_layer=layer,
        base=base,
        matched=matched,
        distance=dist,
        nearest=nearest,
        nearest_distance=nearest_dist,
        die_candidates=len(candidates),
        failed_in_die=failed_in_die,
        ambiguous=ambiguous,
    )


def match_base_against_layers(
    base: DefectRecord,
    compare_layers: list[str],
    records_by_layer: dict[str, list[DefectRecord]],
    tolerance: float,
    *,
    index: DieIndex | None = None,
    fail_index: FailIndex | None = None,
    offsets: dict[str, LayerOffset] | None = None,
    die_tol: int = DEFAULT_DIE_TOL,
) -> BaseDefectMatches:
    """기준 defect 1개를 모든 비교 layer 와 매칭.

    index/fail_index/offsets 를 미리 만들어 넘기면 재사용한다(match_all 에서 사용).
    넘기지 않으면 이 호출에 한해 즉석에서 만든다(offsets 미지정 시 정합오차 보정 없음).
    """
    idx = index if index is not None else build_die_index(records_by_layer, compare_layers)
    fidx = (
        fail_index
        if fail_index is not None
        else build_fail_index(records_by_layer, compare_layers)
    )
    result = BaseDefectMatches(base=base)
    for layer in compare_layers:
        candidates = (
            _gather_candidates(base, idx.get(layer, {}), die_tol) if base.ok else []
        )
        offset = (offsets or {}).get(layer, LayerOffset())
        failed_count = fidx.get(layer, {}).get(_norm_wafer(base.wafer_id), 0)
        result.results.append(
            _build_result(base, layer, candidates, tolerance, offset, failed_count)
        )
    return result


def match_all_with_offsets(
    base_records: list[DefectRecord],
    compare_layers: list[str],
    records_by_layer: dict[str, list[DefectRecord]],
    tolerance: float,
    *,
    index: DieIndex | None = None,
    fail_index: FailIndex | None = None,
    die_tol: int = DEFAULT_DIE_TOL,
) -> tuple[list[BaseDefectMatches], dict[str, LayerOffset]]:
    """매칭 결과 목록과 비교 layer 별 전역 정합오차를 함께 반환한다.

    각 (base, layer) 후보를 **한 번만** 수집해 정합오차 추정과 매칭에 함께 쓴다
    (이전엔 두 패스에서 각각 수집 → 중복 제거로 대량 이미지에서 빨라진다).
    """
    idx = index if index is not None else build_die_index(records_by_layer, compare_layers)
    fidx = (
        fail_index
        if fail_index is not None
        else build_fail_index(records_by_layer, compare_layers)
    )
    buckets = {layer: idx.get(layer, {}) for layer in compare_layers}

    # 1패스: (base, layer) 후보 수집 + 1:1 쌍에서 정합오차 표본 적립.
    cand_table: list[dict[str, list[DefectRecord]]] = []
    samples: dict[str, tuple[list[float], list[float]]] = {
        layer: ([], []) for layer in compare_layers
    }
    for base in base_records:
        row: dict[str, list[DefectRecord]] = {}
        for layer in compare_layers:
            cands = _gather_candidates(base, buckets[layer], die_tol) if base.ok else []
            row[layer] = cands
            if base.ok:
                ok_cands = [c for c in cands if c.ok]
                if len(ok_cands) == 1:
                    dxs, dys = samples[layer]
                    dxs.append(base.x - ok_cands[0].x)  # type: ignore[operator]
                    dys.append(base.y - ok_cands[0].y)  # type: ignore[operator]
        cand_table.append(row)

    offsets = {
        layer: _estimate_offset(samples[layer][0], samples[layer][1], tolerance)
        for layer in compare_layers
    }

    # 2패스: 수집한 후보 재사용해 매칭 결과 구성.
    matches: list[BaseDefectMatches] = []
    for base, row in zip(base_records, cand_table):
        result = BaseDefectMatches(base=base)
        wafer = _norm_wafer(base.wafer_id)
        for layer in compare_layers:
            failed_count = fidx.get(layer, {}).get(wafer, 0)
            result.results.append(
                _build_result(
                    base, layer, row[layer], tolerance, offsets[layer], failed_count
                )
            )
        matches.append(result)
    return matches, offsets


def match_all(
    base_records: list[DefectRecord],
    compare_layers: list[str],
    records_by_layer: dict[str, list[DefectRecord]],
    tolerance: float,
) -> list[BaseDefectMatches]:
    """기준 layer 의 모든 defect 에 대해 매칭 결과 목록을 만든다(정합오차 보정 포함)."""
    matches, _ = match_all_with_offsets(
        base_records, compare_layers, records_by_layer, tolerance
    )
    return matches
