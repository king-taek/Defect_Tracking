"""웨이퍼 맵 die 정합(alignment) — 관측 die 와 디바이스 DB die_map 의 원점 맞추기.

배경: 디바이스 DB 의 die_map 은 Map 그리드의 (ci,ri)(좌상단 원점)인데, record 의
(col,row) 는 파서마다 다른 오프셋(KLA `+count//2`, Camtek INI `row_base-row`, 파일명
직접)을 거친다. 따라서 die_map 을 그대로 valid 로 쓰면 실제 모양과 어긋날 수 있다.

해법(translation voting): 관측 die o 와 die_map die d 의 모든 쌍에 대해 평행이동
s = o - d 에 투표하면, 가장 표를 많이 받은 s 가 두 좌표계를 가장 잘 겹치게 하는 이동이다.
그 s 로 die_map 을 관측 좌표계로 옮겨(valid = die_map + s) 그리면 실제 디바이스 모양과
관측 die 가 정렬된다. 겹침 비율(overlap)이 낮으면 정합 실패로 보고 호출 측이 폴백한다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

# 좌표쌍 타입
Die = tuple[int, int]


@dataclass(frozen=True)
class Alignment:
    """관측→die_map 정합 결과."""

    dcol: int  # die_map 을 관측 좌표계로 옮기는 평행이동(col)
    drow: int
    overlap: float  # 관측 die 중 디바이스 모양 위에 놓인 비율(0~1)

    @property
    def ok(self) -> bool:
        return self.overlap > 0.0


def align_observed_to_diemap(
    observed: set[Die],
    die_map: frozenset[Die] | set[Die],
    *,
    max_samples: int = 120,
) -> Alignment:
    """관측 die 집합을 die_map 에 가장 잘 겹치게 하는 평행이동을 찾는다.

    반환 Alignment.(dcol,drow) 는 die_map 을 관측 좌표계로 옮기는 이동이며,
    valid = {(ci+dcol, ri+drow) for (ci,ri) in die_map} 로 쓰면 관측과 정렬된다.
    overlap 은 관측 die 중 옮긴 die_map 위에 놓인 비율이다.
    """
    if not observed or not die_map:
        return Alignment(0, 0, 0.0)

    # 표본으로 평행이동 투표(비용 제한). 정수 die 이므로 단순 차이로 충분.
    sample = list(observed)[:max_samples]
    votes: Counter[Die] = Counter()
    for oc, orow in sample:
        for dc, dr in die_map:
            votes[(oc - dc, orow - dr)] += 1

    # 동점(같은 최다 득표) translation 이 여럿일 수 있다 — 관측 die 가 성기면 작은
    # cluster 가 큰(dense) 디바이스 모양 안 여러 위치에 똑같이 맞아 overlap 이 같아진다.
    # 해시 순서로 임의 선택하면 윤곽이 defect 셀 옆으로 밀려 보이고, 관측 중심으로 맞추면
    # 오히려 이미 제자리인 die 를 밀어버린다(관측이 die_map 부분집합일 때 shift 0 이 정답인데
    # centroid 로 (-1,1) 등을 고름). 두 좌표계는 원점을 공유하도록 설계됐으므로, 최다 득표
    # 후보 중 **이동 크기(|dcol|+|drow|)가 가장 작은**(= 원 좌표를 최대한 보존하는) 것을
    # 결정론적으로 고른다. 이상적(부분집합) 경우 shift 0 을 되찾는다.
    best_votes = max(votes.values())
    candidates = [s for s, c in votes.items() if c == best_votes]
    sdc, sdr = min(candidates, key=lambda s: (abs(s[0]) + abs(s[1]), s))

    # 전체 관측 기준 겹침 비율 산정(표본이 아닌 전체로 신뢰도 측정).
    shifted = {(ci + sdc, ri + sdr) for ci, ri in die_map}
    hit = sum(1 for o in observed if o in shifted)
    return Alignment(sdc, sdr, hit / len(observed))


def shifted_die_map(die_map: frozenset[Die] | set[Die], align: Alignment) -> set[Die]:
    """die_map 을 정합 이동만큼 옮긴 valid 집합(관측 좌표계)."""
    return {(ci + align.dcol, ri + align.drow) for ci, ri in die_map}
