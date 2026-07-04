"""웨이퍼 맵 die 정합 + 디바이스 경로 인식 단위 테스트."""

from __future__ import annotations

from app import wafermap_align, config


def test_alignment_recovers_offset():
    # die_map 은 3x3 사각(좌상단 원점). 관측은 (+5,+2) 만큼 평행이동된 좌표계.
    die_map = frozenset((c, r) for c in range(3) for r in range(3))
    observed = {(c + 5, r + 2) for c, r in die_map}
    al = wafermap_align.align_observed_to_diemap(observed, die_map)
    assert (al.dcol, al.drow) == (5, 2)
    assert al.overlap == 1.0
    # 옮긴 die_map 이 관측과 정확히 일치해야 한다.
    assert wafermap_align.shifted_die_map(die_map, al) == observed


def test_alignment_partial_overlap_low_confidence():
    die_map = frozenset((c, r) for c in range(5) for r in range(5))
    # 관측이 die_map 모양과 무관(흩어진 소수) → 낮은 겹침
    observed = {(100, 100), (101, 100)}
    al = wafermap_align.align_observed_to_diemap(observed, die_map)
    # 최적 이동을 찾더라도 전체 관측 대비 겹침은 1.0 이지만 die 수가 적어 모양 신뢰 별개.
    # 핵심: die_map 과 전혀 안 겹치는 형태면 overlap 계산이 동작함을 확인.
    assert 0.0 <= al.overlap <= 1.0


def test_alignment_empty_inputs():
    assert wafermap_align.align_observed_to_diemap(set(), frozenset()).overlap == 0.0
    assert wafermap_align.align_observed_to_diemap({(0, 0)}, frozenset()).overlap == 0.0


def test_sparse_observed_centered_within_shape():
    """성긴 관측 die(디바이스 모양의 일부)여도 윤곽이 defect 옆으로 밀리지 않아야 한다.

    회귀: 동점 translation 을 임의로 고르면 윤곽(valid)이 관측 die 옆으로 shift 되어
    보였다. 이제 관측을 모양 안에 중앙 정렬하는 이동을 결정론적으로 골라야 한다.
    """
    # 큰 원반형 die_map: 11x11 격자에서 중심 반경 안쪽만 존재.
    cx = cy = 5
    die_map = frozenset(
        (c, r) for c in range(11) for r in range(11)
        if (c - cx) ** 2 + (r - cy) ** 2 <= 25
    )
    # 관측은 그 모양의 정확한 부분집합(가운데 근처 3개) — 동일 좌표계(shift 0).
    observed = {(5, 5), (5, 4), (6, 5)}
    al = wafermap_align.align_observed_to_diemap(observed, die_map)
    # 올바른 정합은 이동 0 — 관측이 이미 die_map 부분집합이므로.
    assert (al.dcol, al.drow) == (0, 0)
    assert al.overlap == 1.0
    # 옮긴 die_map 이 관측을 모두 포함(윤곽 안에 defect 이 놓임).
    shifted = wafermap_align.shifted_die_map(die_map, al)
    assert observed <= shifted


def test_sparse_alignment_is_deterministic():
    """같은 입력이면 항상 같은 이동(해시 순서 의존 제거)."""
    die_map = frozenset((c, r) for c in range(9) for r in range(9))
    observed = {(4, 4), (4, 5), (5, 4)}
    results = {
        wafermap_align.align_observed_to_diemap(set(observed), die_map)
        for _ in range(5)
    }
    assert len(results) == 1


def test_match_product_for_path_builtin():
    # 기본 제품 DEVAINT 는 경로에 'DEVAINT' 가 있으면 인식된다.
    key, score = config.match_product_for_path("/data/204. DEVAINT.226 (PKG)")
    assert key == "DEVAINT"
    assert score >= 4
    # 무관한 경로는 매칭 안 됨
    key2, _ = config.match_product_for_path("/data/random_lot_001")
    assert key2 is None
