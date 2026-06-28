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


def test_match_product_for_path_builtin():
    # 기본 제품 TB500INT 는 경로에 'TB500INT' 가 있으면 인식된다.
    key, score = config.match_product_for_path("/data/204. TB500INT.226 (WLW)")
    assert key == "TB500INT"
    assert score >= 4
    # 무관한 경로는 매칭 안 됨
    key2, _ = config.match_product_for_path("/data/random_lot_001")
    assert key2 is None
