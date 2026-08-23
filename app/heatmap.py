"""히트맵 순수 로직 - defect 밀도 격자 구성, die 하위셀(subcell) 분할, 자동 LOD, 누적합.

UI 와 분리해 단위 테스트로 검증한다. 웨이퍼맵에 defect 위치를 표시/클릭하기 위한
집계와, die 개수가 적을 때(50개 미만) 각 die 를 5x5(25) 하위셀로 나눠 die 내부 local
좌표(x,y)로 defect 을 구분 배치하는 매핑을 제공한다.

여기에 그리기 판단(LOD)과 영역 합산(적분 이미지)까지 둔 이유는, 둘 다 Qt 없이 값만으로
결정되는 계산이라 화면 없이 못 박을 수 있기 때문이다. 그리기 자체만 페이지가 맡는다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

# die 하위셀 격자(항목 5): die 가 클 때 die 내부를 5열×5행(25칸)으로 나눈다.
SUB_COLS = 5
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
    """히트맵 셀 키 - die (col,row) + (하위셀 sub_col/sub_row, 미분할이면 -1)."""

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


# ---- 자동 LOD (REVIEW-01 A7) --------------------------------------------
# die 한 변이 몇 px 인지에 따라 표현을 단계적으로 덜어낸다. 사용자가 배율을 고르는 컨트롤을
# 두지 않는 이유는 die 수를 LOT 이 정하기 때문이다(A7). 지도는 언제나 한 화면에 들어와야
# 하므로(게이트) 셀 크기는 패널 크기에서 역산하고, 그 결과가 곧 표현 단계가 된다.
LOD_DETAIL_PX = 20   # 이상: die 안 5x5 하위셀까지 그린다
LOD_GAP_PX = 12      # 미만: die 간격을 해제한다
LOD_BORDER_PX = 9    # 미만: die 테두리를 해제한다
LOD_RASTER_PX = 6    # 미만: QImage 픽셀 채움 1장(래스터)

# die 간격과 셀 상한. 상한이 없으면 die 가 적을 때 지도가 카드를 가득 채워 커지기만 한다
# (03-screens 3절: 42 die 기준 45x45 셀 gap 3).
DIE_GAP_PX = 3
MAX_CELL_PX = 45

MODE_DETAIL = "detail"
MODE_PLAIN = "plain"
MODE_RASTER = "raster"


@dataclass(frozen=True)
class LodPlan:
    """셀 크기 한 개에서 결정되는 그리기 단계."""

    mode: str
    subdivide: bool
    gap: bool
    border: bool


def plan_lod(cell_px: float) -> LodPlan:
    """die 한 변(px)으로 그리기 단계를 고른다.

    해제 순서는 하위분할 -> 간격 -> 테두리 다(A7). 정보가 가장 적은 것부터 버려야 마지막까지
    남는 단서(칸의 밝기)가 유지된다.
    """
    if cell_px >= LOD_DETAIL_PX:
        return LodPlan(MODE_DETAIL, True, True, True)
    if cell_px < LOD_RASTER_PX:
        return LodPlan(MODE_RASTER, False, False, False)
    return LodPlan(
        MODE_PLAIN,
        False,
        cell_px >= LOD_GAP_PX,
        cell_px >= LOD_BORDER_PX,
    )


def fit_cell_px(
    cols: int, rows: int, avail_w: float, avail_h: float, gap: float = DIE_GAP_PX
) -> float:
    """cols x rows 격자가 (avail_w, avail_h) 안에 통째로 들어가는 die 한 변(px)."""
    if cols <= 0 or rows <= 0:
        return 0.0
    wide = (avail_w - gap) / cols - gap
    high = (avail_h - gap) / rows - gap
    return max(0.0, min(wide, high, float(MAX_CELL_PX)))


def layout_for(
    cols: int, rows: int, avail_w: float, avail_h: float
) -> tuple[float, int, LodPlan]:
    """(die 한 변 px, die 간격 px, LodPlan) - 항상 한 화면에 들어가는 조합.

    간격을 먼저 넣고 재 본 뒤, 그 크기가 간격을 감당하지 못하면 간격을 빼고 다시 잰다.
    단계 판정은 첫 측정값으로 고정한다(간격을 뺀 값으로 다시 판정하면 두 상태를 오간다).
    """
    cell = fit_cell_px(cols, rows, avail_w, avail_h, DIE_GAP_PX)
    plan = plan_lod(cell)
    gap = DIE_GAP_PX if plan.gap else 0
    if gap != DIE_GAP_PX:
        cell = fit_cell_px(cols, rows, avail_w, avail_h, gap)
    return cell, gap, plan


# ---- 단일 잉크 램프 ------------------------------------------------------
# 색상축을 하나로 줄이는 것이 이 화면 재설계의 요점이다. 원본의 파랑->코랄 2색 램프는
# 밀도와 색상(hue)을 동시에 읽게 만들어, 어느 칸이 더 많은지 즉답이 안 됐다.
RAMP_MIN_ALPHA = 0.12
RAMP_MAX_ALPHA = 1.0


def ramp_alpha(count: int, max_count: int) -> float:
    """defect 개수를 잉크 농도(accentFill 알파)로. 0 개는 0.0(빈 die)."""
    if count <= 0:
        return 0.0
    if max_count <= 1:
        return RAMP_MAX_ALPHA
    frac = (count - 1) / (max_count - 1)
    frac = max(0.0, min(1.0, frac))
    return RAMP_MIN_ALPHA + (RAMP_MAX_ALPHA - RAMP_MIN_ALPHA) * frac


# ---- 2D 누적합(적분 이미지) ---------------------------------------------
class DensityGrid:
    """die 격자 밀도의 2D 누적합. 어떤 사각 영역이든 네 점 조회로 합을 낸다.

    드래그 사각 선택은 프레임마다 영역 합을 새로 보여 준다. 매번 영역 안을 다시 더하면
    4,096 die 에서 드래그가 끊기므로, 격자가 바뀔 때 한 번만 누적합을 만들어 둔다.
    좌표는 실 die 좌표(col,row)를 그대로 받고 내부에서 origin 을 뺀다.
    """

    def __init__(
        self,
        counts: Mapping[tuple[int, int], int],
        cols: int,
        rows: int,
        origin: tuple[int, int] = (0, 0),
    ):
        self.cols = max(0, int(cols))
        self.rows = max(0, int(rows))
        self.origin = (int(origin[0]), int(origin[1]))
        self.max_count = 0
        stride = self.cols + 1
        table = [0] * (stride * (self.rows + 1))
        oc, orr = self.origin
        for (col, row), value in counts.items():
            n = int(value)
            if n > self.max_count:
                self.max_count = n
            c = int(col) - oc
            r = int(row) - orr
            if 0 <= c < self.cols and 0 <= r < self.rows:
                table[(r + 1) * stride + (c + 1)] = n
        for r in range(1, self.rows + 1):
            base = r * stride
            above = base - stride
            run = 0
            for c in range(1, stride):
                run += table[base + c]
                table[base + c] = run + table[above + c]
        self._table = table
        self._stride = stride

    @property
    def total(self) -> int:
        """격자 안 defect 총합."""
        return self._table[-1] if self._table else 0

    def count_at(self, col: int, row: int) -> int:
        return self.region_sum(col, row, col, row)

    def region_sum(self, col0: int, row0: int, col1: int, row1: int) -> int:
        """실 die 좌표 사각 영역(양끝 포함)의 defect 합. O(1)."""
        if self.cols <= 0 or self.rows <= 0:
            return 0
        oc, orr = self.origin
        c0, c1 = sorted((int(col0) - oc, int(col1) - oc))
        r0, r1 = sorted((int(row0) - orr, int(row1) - orr))
        c0 = max(0, c0)
        r0 = max(0, r0)
        c1 = min(self.cols - 1, c1)
        r1 = min(self.rows - 1, r1)
        if c0 > c1 or r0 > r1:
            return 0
        stride = self._stride
        t = self._table
        return (
            t[(r1 + 1) * stride + (c1 + 1)]
            - t[r0 * stride + (c1 + 1)]
            - t[(r1 + 1) * stride + c0]
            + t[r0 * stride + c0]
        )


def die_counts(density: Mapping[HeatKey, int]) -> dict[tuple[int, int], int]:
    """하위셀까지 나뉜 밀도를 die 단위로 합친다(누적합·저해상 렌더의 입력)."""
    out: dict[tuple[int, int], int] = {}
    for key, value in density.items():
        pos = (key.col, key.row)
        out[pos] = out.get(pos, 0) + int(value)
    return out
