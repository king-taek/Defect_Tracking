"""히트맵 순수 로직 — defect 밀도 격자 구성과 die 하위셀(subcell) 분할.

UI(팝업)와 분리해 단위 테스트로 검증한다. 웨이퍼맵에 defect 위치를 표시/클릭하기 위한
집계와, die 개수가 적을 때(50개 미만) 각 die 를 4×5(20) 하위셀로 나눠 die 내부 local
좌표(x,y)로 defect 을 구분 배치하는 매핑을 제공한다(항목 4·5).
"""

from __future__ import annotations

from dataclasses import dataclass

# die 하위셀 격자(항목 5): die 가 클 때 die 내부를 4열×5행(20칸)으로 나눈다.
SUB_COLS = 4
SUB_ROWS = 5
# die 개수가 이 값 미만이면 하위셀 분할을 적용한다.
SUBDIVIDE_THRESHOLD = 50


def should_subdivide(die_count: int) -> bool:
    """die 개수가 임계값 미만이면 하위셀 분할을 적용한다."""
    return 0 < die_count < SUBDIVIDE_THRESHOLD


def _bucket(value: float, lo: float, hi: float, n: int) -> int:
    """value 를 [lo,hi] 범위에서 n 개 구간 중 하나(0..n-1)로 버킷화한다."""
    if hi <= lo:
        return 0
    frac = (value - lo) / (hi - lo)
    b = int(frac * n)
    return max(0, min(n - 1, b))


def local_ranges(records) -> tuple[tuple[float, float], tuple[float, float]]:
    """defect record 들의 die 내부 local 좌표(x,y) 관측 범위((xmin,xmax),(ymin,ymax)).

    좌표가 없는 record 는 건너뛴다. 비어 있으면 ((0,1),(0,1)).
    """
    xs = [r.x for r in records if getattr(r, "x", None) is not None]
    ys = [r.y for r in records if getattr(r, "y", None) is not None]
    if not xs or not ys:
        return (0.0, 1.0), (0.0, 1.0)
    return (min(xs), max(xs)), (min(ys), max(ys))


def subcell_of(
    x: float,
    y: float,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
) -> tuple[int, int]:
    """die 내부 local 좌표(x,y)를 하위셀 좌표(sub_col, sub_row)로 매핑한다.

    y 는 위(작은 값)→아래로 증가하도록 행 인덱스를 매긴다(화면 좌표계).
    """
    sc = _bucket(x, x_range[0], x_range[1], SUB_COLS)
    sr = _bucket(y, y_range[0], y_range[1], SUB_ROWS)
    return sc, sr


@dataclass(frozen=True)
class HeatKey:
    """히트맵 셀 키 — die (col,row) + (하위셀 sub_col/sub_row, 미분할이면 -1)."""

    col: int
    row: int
    sub_col: int = -1
    sub_row: int = -1

    @property
    def subdivided(self) -> bool:
        return self.sub_col >= 0 and self.sub_row >= 0


def group_defects(
    entries: list[tuple[int, object]],
    subdivide: bool,
    x_range: tuple[float, float] | None = None,
    y_range: tuple[float, float] | None = None,
) -> dict[HeatKey, list[int]]:
    """(index, DefectRecord) 목록을 히트맵 셀(HeatKey)별 index 리스트로 집계한다.

    subdivide=True 이면 die 내부를 하위셀로 나눠 키에 (sub_col,sub_row)를 포함한다.
    좌표(col/row) 가 없는 record 는 제외한다.
    """
    out: dict[HeatKey, list[int]] = {}
    for idx, rec in entries:
        col = getattr(rec, "col", None)
        row = getattr(rec, "row", None)
        if col is None or row is None:
            continue
        if subdivide and x_range is not None and y_range is not None \
                and getattr(rec, "x", None) is not None \
                and getattr(rec, "y", None) is not None:
            sc, sr = subcell_of(rec.x, rec.y, x_range, y_range)
            key = HeatKey(int(col), int(row), sc, sr)
        else:
            key = HeatKey(int(col), int(row))
        out.setdefault(key, []).append(idx)
    return out
