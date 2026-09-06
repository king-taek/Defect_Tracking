"""die 격자 기하(pitch·인덱스 원점)를 **스캔 결과 폴더에서 읽는다**.

`king-taek/coding` ``coords/wafer_geometry.py`` 의 이식.  TB500 상수는 한 대의 값이라
die 크기가 다른 디바이스에서는 좌표·매칭이 통째로 어긋난다.  필요한 값은 결과 폴더
안에 있다:

  · Camtek : ``Params_WaferInfo.ini``  ``[Geometry] DieStep_X/DieStep_Y``
  · KLA    : ``.001`` 헤더 ``DiePitch X Y`` 와 ``SampleCenterLocation``/``SampleTestPlan``

실측 불변식 — **읽은 pitch 의 검산에 쓴다**::

    Col == floor(X / DieStep_X)      Row == floor(Y / DieStep_Y)

즉 Camtek 의 die 격자는 stage 원점(0,0)에 고정돼 있다.  읽은 pitch 로 이 식이 안 맞으면
엉뚱한 키를 읽은 것이므로 채택하지 않는다.  ``Row`` 쪽은 레시피마다 원점이 1 다를 수
있어 X 만 등호를 요구하고 Y 는 '레시피별로 차이가 상수' 만 본다(:func:`_grid_check`).

폴더 단위 ``@lru_cache``, 전 구간 fail-safe(절대 raise 안 함), 합리적 범위 클램프.
"""

from __future__ import annotations

import logging
import math
import re
import struct
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .ini_text import read_ini_text
from .models import (CAMTEK_COL_OFFSET, CAMTEK_PITCH_X, CAMTEK_PITCH_Y,
                     DEFAULT_WAFER_DIAMETER, KLA_ZERO_X, KLA_ZERO_Y)

__all__ = ["CamtekGeometry", "KlaGeometry", "camtek_geometry", "kla_geometry",
           "has_camtek_entries", "peek_die_pitch", "parse_kla_header",
           "FALLBACK_CAMTEK", "FALLBACK_KLA"]

_LOG = logging.getLogger("defect_tracker.aoi.coords")

# 합리적 die pitch 범위(µm) — 엉뚱한 키를 읽었을 때 채택 방지.
_MIN_PITCH, _MAX_PITCH = 100.0, 500000.0
# 합리적 웨이퍼 직경 범위(µm) — 2인치(50 mm) ~ 450 mm.
_MIN_DIAMETER, _MAX_DIAMETER = 50000.0, 450000.0
# die 인덱스 기준의 상식 범위 — 웨이퍼가 stage 원점에서 이보다 멀리 놓일 수 없다.
_MAX_DIE_INDEX = 200

# Diameter 를 담은 파일 후보 — pitch 후보와 같은 폴더 탐색 순서로 찾는다.
_DIAMETER_SOURCES = ("Params_WaferInfo.ini", "ProductInfo.ini")

# 웨이퍼 중심의 **2순위 소스** — `[Geometric] Center_X/Y` 가 0(미기록)일 때 쓴다.
# `Wafer2Table_X/Y = a11 a12 t1` 두 줄이 어파인 변환 `wafer = M·table + t` 를 준다.
_W2T_FILE = "Wafer2Table.ini"
_W2T_PAT = re.compile(
    r"(?im)^\s*Wafer2Table_([XY])\s*=\s*"
    r"([-\d.eE]+)\s+([-\d.eE]+)\s+([-\d.eE]+)\s*$")

# Camtek die pitch 후보 (상대경로, X키, Y키) 우선순위.
# ⚠ **간격(step) 계열만** 넣는다.  die '크기' 는 pitch 가 아니다 — 스크라이브 street 이
# 있는 자재는 둘이 다르다.  그래서 `DieSize_*` `DieSelectedSize_*` `XDieSize/YDieSize`
# 는 후보에서 제외한다.
_CAMTEK_SOURCES = (
    ("Params_WaferInfo.ini", "DieStep_X", "DieStep_Y"),
    ("ProductInfo.ini", "XDieIndex", "YDieIndex"),
    ("ProductInfo.ini", "CustomerDiePitch_X", "CustomerDiePitch_Y"),
)
# 사진 폴더가 웨이퍼 폴더의 하위일 수 있어 부모를 몇 단계까지 올라가 찾는다.
_PARENT_LEVELS = 2
# 파일에서 못 읽었을 때의 마지막 후보(`models.py` 상수)의 출처 표기 — 검산이 '의미
# 있음' 까지 확인해야만 채택된다(`camtek_geometry`).
_CONST_SOURCE = "models.py 상수"

# 장비가 쓴 die 맵 — 그 웨이퍼의 die 전체 목록(좌표).  col/row 번호의 기준을 유도하지
# 않고 여기서 **읽는다**(:func:`_die_map_origins`).  레코드 배치는 장비 소프트웨어마다
# 달라서(실측 72 / 128) 옆의 ``.md`` 사이드카가 알려 준다.
_DIE_MAP_FILE = "s_DieLocation.dat"
# 이보다 적으면 die 맵으로 인정하지 않는다 — 웨이퍼 한 장에 die 가 수백~수천 개다.
_MIN_DIE_MAP = 50
_VT_DOUBLE = 5                      # 장비가 쓰는 VARIANT 코드 (VT_R8)
_RECSIZE_PAT = re.compile(r'RecordSize\s+Size="(\d+)"')
_FIELD_PAT = re.compile(r'Name="([^"]+)"[^>]*?Offset="(\d+)"[^>]*?Vartype="(\d+)"')

_DIEPITCH_PAT = re.compile(r'DiePitch\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)', re.IGNORECASE)
# SampleTestPlan <개수> 뒤에 (XINDEX YINDEX) 쌍이 ';' 까지 이어진다.
_TESTPLAN_PAT = re.compile(r'SampleTestPlan\s+\d+(.*?);', re.IGNORECASE | re.DOTALL)
_INDEX_PAIR_PAT = re.compile(r'(-?\d+)\s+(-?\d+)')
# 웨이퍼 중심의 die 격자 좌표(µm) — Camtek `[Geometric] Center_X/Y` 에 대응한다.
_SAMPLE_CENTER_PAT = re.compile(
    r'SampleCenterLocation\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)', re.IGNORECASE)
# `SampleSize 1 300;` → 웨이퍼 직경 300 **mm**.
_SAMPLE_SIZE_PAT = re.compile(r'SampleSize\s+\d+\s+([\d.eE+\-]+)', re.IGNORECASE)


@dataclass(frozen=True)
class CamtekGeometry:
    """Camtek INI 좌표 변환에 필요한 die 격자 기하.

    ``col = x_index − col_origin``,  ``row = row_total − y_index``,
    ``x = floor(X − x_index × pitch_x)``,  ``y = floor(Y − y_index × pitch_y)``

    ``col_origin``·``row_total`` 은 상수가 아니라 **웨이퍼가 stage 위 어디에 놓였는지**
    (``Center_X``/``Center_Y``)에서 유도한다 — 각각 '온전히 들어오는 첫 열' 과
    '온전히 들어오는 마지막 행' 이다.
    """
    pitch_x: float
    pitch_y: float
    col_origin: int
    row_total: int
    source: str      # 진단용 — 어느 파일에서 왔는지("fallback" 이면 TB500 상수)


@dataclass(frozen=True)
class KlaGeometry:
    """KLA .001 좌표 변환에 필요한 die 격자 기하.  ``col = XINDEX + zero_x`` 등."""
    pitch_x: float
    pitch_y: float
    zero_x: int
    zero_y: int
    source: str


def _row_total(center_y: Optional[float], diameter: float, pitch_y: float) -> int:
    """row 번호 기준 = **웨이퍼 안에 온전히 들어오는 마지막 die 행**::

        row_total = floor((Center_Y + Diameter/2) / DieStep_Y) − 1

    ``center_y`` 가 없거나 기록되지 않았으면(``0``) 옛 식 ``ceil(Diameter/pitch_y)`` 로
    폴백한다.  ⚠ **두 식은 보통 1 다르다** — 그래서 KLA 쪽 ``zero_y`` 도 같은 조건에서
    함께 폴백해야 정렬이 유지된다.
    """
    if not center_y:                       # None 또는 0.0 → 미기록
        return math.ceil(diameter / pitch_y)
    total = math.floor((center_y + diameter / 2.0) / pitch_y) - 1
    if not (0 <= total <= _MAX_DIE_INDEX):
        _LOG.warning("Center_Y %.1f 로 계산한 row 기준 %d 이 비상식적이라 "
                     "ceil(Diameter/pitch_y) 로 폴백합니다.", center_y, total)
        return math.ceil(diameter / pitch_y)
    return total


def _col_origin(center_x: Optional[float], diameter: float, pitch_x: float) -> int:
    """col 번호 기준 = **웨이퍼 안에 온전히 들어오는 첫 die 열**::

        col_origin = ceil((Center_X − Diameter/2) / DieStep_X)

    같은 자재라도 웨이퍼 위치가 한 die 달라지면 ``x_index`` 가 통째로 1 밀리므로 상수로
    둘 수 없다.  ``center_x`` 가 없거나 ``0``(정렬 정보 미기록)이면
    :data:`CAMTEK_COL_OFFSET` 로 폴백한다.
    """
    if not center_x:                       # None 또는 0.0 → 미기록
        return CAMTEK_COL_OFFSET
    origin = math.ceil((center_x - diameter / 2.0) / pitch_x)
    if not (0 <= origin <= _MAX_DIE_INDEX):
        _LOG.warning("Center_X %.1f 로 계산한 col 기준 %d 이 비상식적이라 상수 %d 을 씁니다.",
                     center_x, origin, CAMTEK_COL_OFFSET)
        return CAMTEK_COL_OFFSET
    return origin


# 데이터에서 못 읽을 때 쓰는 TB500 폴백 — 값은 models.py 가 보유한다.
FALLBACK_CAMTEK = CamtekGeometry(
    pitch_x=CAMTEK_PITCH_X, pitch_y=CAMTEK_PITCH_Y,
    col_origin=CAMTEK_COL_OFFSET,
    row_total=_row_total(None, DEFAULT_WAFER_DIAMETER, CAMTEK_PITCH_Y),   # = 7
    source="fallback",
)
FALLBACK_KLA = KlaGeometry(
    pitch_x=CAMTEK_PITCH_X, pitch_y=CAMTEK_PITCH_Y,
    zero_x=KLA_ZERO_X, zero_y=KLA_ZERO_Y, source="fallback",
)


def _read_key(path: Path, key: str, lo: float = _MIN_PITCH,
              hi: float = _MAX_PITCH) -> Optional[float]:
    """INI 에서 ``key=값`` 을 읽어 float 로. 없거나 [lo, hi] 밖이면 None.

    값 뒤에 다른 문자가 붙으면(예: 소수점이 ',' 인 로캘) **잘라 읽지 않고 거부**한다."""
    txt = read_ini_text(path)
    if txt is None:
        return None
    m = re.search(r"(?im)^\s*" + re.escape(key) + r"\s*=\s*([-\d.eE]+)\s*$", txt)
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    return v if lo <= v <= hi else None


def _search_dirs(folder: Path) -> list[Path]:
    """폴더 자신 + 부모 ``_PARENT_LEVELS`` 단계."""
    dirs = [folder]
    cur = folder
    for _ in range(_PARENT_LEVELS):
        parent = cur.parent
        if parent == cur:
            break
        dirs.append(parent)
        cur = parent
    return dirs


def _read_diameter(folder: Path) -> float:
    """웨이퍼 직경(µm) — ``[Geometric] Diameter``.  못 찾으면 기본 300 mm."""
    for base in _search_dirs(folder):
        for rel in _DIAMETER_SOURCES:
            v = _read_key(base / rel, "Diameter", _MIN_DIAMETER, _MAX_DIAMETER)
            if v is not None:
                return v
    return DEFAULT_WAFER_DIAMETER


def _read_center(folder: Path, key: str) -> Optional[float]:
    """웨이퍼 중심의 stage 좌표(µm) — ``Center_X``/``Center_Y``.  미기록이면 None.

    ``0.000000`` 은 **값이 아니라 '기록 안 됨'** 이다.  :func:`_read_key` 의 하한이 걸러 준다."""
    for base in _search_dirs(folder):
        for rel in _DIAMETER_SOURCES:
            v = _read_key(base / rel, key, _MIN_PITCH, _MAX_DIAMETER)
            if v is not None:
                return v
    return None


def _read_wafer2table(folder: Path) -> Optional[tuple[float, float]]:
    """``Wafer2Table.ini`` 의 정렬 변환에서 **웨이퍼 중심의 stage 좌표**를 푼다.

    파일이 담은 것은 어파인 변환 ``wafer = M·table + t`` 다.  웨이퍼 중심은
    ``wafer = (0,0)`` 인 지점이므로 ``중심(stage) = M⁻¹ · (−t)``.
    """
    for base in _search_dirs(folder):
        txt = read_ini_text(base / _W2T_FILE)
        if txt is None:
            continue
        rows: dict[str, tuple[float, float, float]] = {}
        for m in _W2T_PAT.finditer(txt):
            try:
                rows[m.group(1).upper()] = (float(m.group(2)), float(m.group(3)),
                                            float(m.group(4)))
            except ValueError:
                return None
        if {"X", "Y"} - rows.keys():
            continue
        (a11, a12, t1), (a21, a22, t2) = rows["X"], rows["Y"]
        det = a11 * a22 - a12 * a21
        if abs(det) < 1e-9:            # 특이행렬 — 못 푼다
            return None
        cx = (a22 * -t1 - a12 * -t2) / det
        cy = (-a21 * -t1 + a11 * -t2) / det
        if not all(_MIN_PITCH <= v <= _MAX_DIAMETER for v in (cx, cy)):
            _LOG.warning("%s 로 푼 웨이퍼 중심 (%.1f, %.1f) 이 비상식적이라 무시합니다: %s",
                         _W2T_FILE, cx, cy, base)
            return None
        return (cx, cy)
    return None


def _wafer_center(folder: Path) -> tuple[Optional[float], Optional[float]]:
    """웨이퍼 중심의 stage 좌표 ``(X, Y)`` — 축마다 없으면 ``None``.

    1순위 ``Params_WaferInfo.ini [Geometric] Center_X/Y``, 2순위 ``Wafer2Table.ini``."""
    cx = _read_center(folder, "Center_X")
    cy = _read_center(folder, "Center_Y")
    if cx is not None and cy is not None:
        return (cx, cy)
    w2t = _read_wafer2table(folder)
    if w2t is None:
        return (cx, cy)
    return (cx if cx is not None else w2t[0], cy if cy is not None else w2t[1])


def _pitch_candidates(folder: Path):
    """(pitch_x, pitch_y, 출처) 후보를 우선순위대로 내놓는다.

    마지막 후보는 :mod:`.models` 의 상수다 — **다른 후보와 똑같이 검산을 받는다**."""
    for base in _search_dirs(folder):
        for rel, kx, ky in _CAMTEK_SOURCES:
            px = _read_key(base / rel, kx)
            py = _read_key(base / rel, ky)
            if px is not None and py is not None:
                yield (px, py, f"{rel}:{kx}/{ky}")
    yield (CAMTEK_PITCH_X, CAMTEK_PITCH_Y, _CONST_SOURCE)


def peek_die_pitch(folder: Path) -> Optional[tuple[float, float, str]]:
    """안내용 — **파일에 적힌** die pitch 를 검산 없이 읽는다(무거운 파일은 열지 않음).

    상수 후보는 내지 않는다 — 파일에 없는 값을 '감지됨' 이라 말하지 않는다."""
    try:
        for px, py, src in _pitch_candidates(folder):
            if src == _CONST_SOURCE:
                break
            return (px, py, src)
    except Exception:
        pass
    return None


def has_camtek_entries(folder: Path) -> bool:
    """이 폴더가 **Camtek INI 좌표를 가진 폴더**인가(변환 대상이 있는가)."""
    from . import camtek_ini

    try:
        return bool(camtek_ini.load_raw_folder(folder))
    except Exception:
        return False


def _grid_check(folder: Path, pitch_x: float, pitch_y: float) -> tuple[bool, bool]:
    """INI 의 ``Col``/``Row`` 필드를 참조값 삼아 pitch 를 검산한다.

        X : Col == floor(X/pitch_x)                       전 항목 **등호**
        Y : {floor(Y/pitch_y) − Row} 가 **레시피별로 상수**  (0 일 필요 없음)

    **X 는 절대 완화하지 않는다** — 항목이 1건뿐인 폴더에서 '상수' 조건은 공허하게 참이
    돼 격자가 다른 자재에 TB500 상수가 채택되는 길이 열린다.

    반환 ``(통과, 의미있음)``.  '의미있음' 은 검산이 실제로 pitch 를 제약했는지다 —
    모든 항목이 ``Col=0`` 이면 어떤 pitch 든 통과하므로 검산이 아무 말도 못 한 것이다.
    파일에서 읽은 값은 '통과' 만으로 채택하지만, 상수 후보는 '의미있음' 까지 요구한다.
    """
    from . import camtek_ini      # 순환 import 회피 — 검산 시점에만 필요

    try:
        raw = camtek_ini.load_raw_folder(folder)
        recipes = camtek_ini.load_recipe_folder(folder)
    except Exception:
        return (False, False)
    if not raw:
        return (False, False)

    # X: 등호 그대로.
    if not all(math.floor(X / pitch_x) == col_i for X, _, col_i, _ in raw.values()):
        return (False, False)

    # Y: 레시피별로 차이가 일정하기만 하면 된다.
    by_recipe: dict[int, set[int]] = {}
    for stem, (_X, Y, _col_i, row_i) in raw.items():
        by_recipe.setdefault(recipes.get(stem, 0), set()).add(
            math.floor(Y / pitch_y) - row_i)
    if any(len(diffs) != 1 for diffs in by_recipe.values()):
        return (False, False)

    off = {r: next(iter(d)) for r, d in by_recipe.items() if next(iter(d)) != 0}
    if off:
        _LOG.info("INI Row 가 die 인덱스와 어긋난다(레시피별 상수라 채택). "
                  "좌표 산출은 좌표에서 유도하므로 영향 없음 — recipe별 차이 %s: %s",
                  off, folder)

    meaningful = (any(col_i >= 1 for _, _, col_i, _ in raw.values())
                  and any(row_i >= 1 for *_, row_i in raw.values()))
    return (True, meaningful)


@lru_cache(maxsize=256)
def camtek_geometry(folder: Path) -> Optional[CamtekGeometry]:
    """폴더의 Camtek die 격자 기하.

    후보를 우선순위대로 돌며 **검산을 통과한 첫 값**을 채택한다.  통과한 후보가 하나도
    없으면 ``None`` — 호출부는 die 좌표를 만들지 않는다(절대좌표로 폴백).
    **틀린 좌표를 내느니 안 내는 편이 낫다.**  전 구간 fail-safe.
    """
    try:
        for px, py, src in _pitch_candidates(folder):
            ok, meaningful = _grid_check(folder, px, py)
            if not ok:
                continue
            if src == _CONST_SOURCE and not meaningful:
                continue      # 검산이 pitch 를 제약하지 못했다 — 상수를 추정으로 쓰지 않는다
            # col·row 기준은 **장비가 쓴 die 맵이 1순위**다 — 맵이 없으면 중심 유도로
            # 폴백한다: 중심은 Params 의 Center_X/Y → Wafer2Table.ini 순으로 찾고,
            # 그래도 없으면 각각 상수/옛 식으로 폴백한다.
            dia = _read_diameter(folder)
            cx, cy = _wafer_center(folder)
            d_origin = _col_origin(cx, dia, px)
            d_total = _row_total(cy, dia, py)
            mapped = _die_map_origins(folder, px, py)
            if mapped is not None:
                m_origin, m_total = mapped
                # ⚠ 맵은 유도값과 **±1 이내일 때만** 믿는다(부분 맵 방어).
                if abs(m_origin - d_origin) <= 1 and abs(m_total - d_total) <= 1:
                    if (m_origin, m_total) != (d_origin, d_total):
                        _LOG.info(
                            "die 맵과 중심 유도가 다르다 — 맵을 쓴다(맵이 장비 "
                            "표시값이다). col_origin %d→%d · row_total %d→%d: %s",
                            d_origin, m_origin, d_total, m_total, folder)
                    return CamtekGeometry(pitch_x=px, pitch_y=py,
                                          col_origin=m_origin, row_total=m_total,
                                          source=f"{src}+{_DIE_MAP_FILE}")
                _LOG.warning(
                    "%s 의 die 기준 (%d, %d) 이 유도값 (%d, %d) 과 1 넘게 달라 "
                    "무시합니다(부분 맵 의심): %s",
                    _DIE_MAP_FILE, m_origin, m_total, d_origin, d_total, folder)
            return CamtekGeometry(pitch_x=px, pitch_y=py,
                                  col_origin=d_origin, row_total=d_total,
                                  source=src)
        # Camtek INI 자체가 없는 폴더(KLA 슬롯·LIVE 파일명 슬롯)는 **조용히** None.
        if has_camtek_entries(folder):
            _LOG.warning(
                "die pitch 를 확정하지 못해 **절대 wafer 좌표**로 매칭합니다(매칭은 정상). "
                "die 내부 좌표·row 표기를 보려면 Params_WaferInfo.ini `DieStep_X/Y` 또는 "
                "ProductInfo.ini `XDieIndex/YDieIndex` 가 필요합니다: %s", folder)
        return None
    except Exception:
        return None


def _die_map_origins(folder: Path, px: float, py: float
                     ) -> Optional[tuple[int, int]]:
    """**장비가 쓴 die 맵**(``s_DieLocation.dat``)에서 ``(col_origin, row_total)`` 을 읽는다.

    ``x_index`` 최솟값이 col 기준, ``y_index`` 최댓값이 row 기준이다.  레코드 배치는
    옆의 ``.dat.md`` 사이드카를 따른다.  ``.md`` 가 없거나, 레코드 수가 안 맞거나, die 가
    :data:`_MIN_DIE_MAP` 개 미만이거나, 인덱스가 상식 범위를 벗어나면 ``None``.
    """
    for base in _search_dirs(folder):
        dat = base / _DIE_MAP_FILE
        layout = _dat_layout(dat)
        if layout is None:
            continue
        rec, fields = layout
        try:
            off_x, vt_x = fields["x"]
            off_y, vt_y = fields["y"]
        except KeyError:
            continue
        if vt_x != _VT_DOUBLE or vt_y != _VT_DOUBLE:
            continue
        try:
            from app.safety import read_only_bytes
            data = read_only_bytes(dat)
        except OSError:
            continue
        if rec <= 0 or not data or len(data) % rec:
            continue
        count = len(data) // rec
        if count < _MIN_DIE_MAP:
            continue
        xs: set[int] = set()
        ys: set[int] = set()
        for i in range(count):
            b = i * rec
            x = struct.unpack_from("<d", data, b + off_x)[0]
            y = struct.unpack_from("<d", data, b + off_y)[0]
            xs.add(math.floor(x / px))
            ys.add(math.floor(y / py))
        col_origin, row_total = min(xs), max(ys)
        if not (0 <= col_origin <= _MAX_DIE_INDEX
                and 0 <= row_total <= _MAX_DIE_INDEX):
            continue
        return col_origin, row_total
    return None


def _dat_layout(dat: Path) -> Optional[tuple[int, dict[str, tuple[int, int]]]]:
    """``<이름>.dat.md`` 가 알려 주는 ``(레코드크기, {필드: (오프셋, vartype)})``."""
    txt = read_ini_text(Path(str(dat) + ".md"))
    if not txt:
        return None
    m = _RECSIZE_PAT.search(txt)
    if not m:
        return None
    fields = {name: (int(off), int(vt))
              for name, off, vt in _FIELD_PAT.findall(txt)}
    return (int(m.group(1)), fields) if fields else None


def _kla_zero(center: float, diameter: float, pitch: float) -> Optional[int]:
    """die 인덱스 원점 = **−(웨이퍼에 온전히 들어오는 첫 인덱스)**.  비상식적이면 None.

    Camtek :func:`_col_origin` 과 **같은 규칙**이고, KLA 는 Y 가 위로 커져서 두 축 모두
    '첫' 을 쓴다."""
    zero = -math.ceil((center - diameter / 2.0) / pitch)
    return zero if 0 <= zero <= _MAX_DIE_INDEX else None


def _kla_zeros_from_center(text: str, px: float, py: float
                           ) -> Optional[tuple[int, int]]:
    """``SampleCenterLocation`` + ``SampleSize`` 로 ``(zero_x, zero_y)`` 산출."""
    cm = _SAMPLE_CENTER_PAT.search(text)
    sm = _SAMPLE_SIZE_PAT.search(text)
    if cm is None or sm is None:
        return None
    try:
        cx, cy = float(cm.group(1)), float(cm.group(2))
        dia = float(sm.group(1)) * 1000.0        # SampleSize 는 mm 단위
    except ValueError:
        return None
    if not (_MIN_DIAMETER <= dia <= _MAX_DIAMETER):
        return None
    zx, zy = _kla_zero(cx, dia, px), _kla_zero(cy, dia, py)
    return None if zx is None or zy is None else (zx, zy)


def parse_kla_header(text: str) -> Optional[KlaGeometry]:
    """KLA ``.001`` 헤더 텍스트 → KlaGeometry.  DiePitch 가 없으면 None.

    ``zero_x``/``zero_y`` 는 **``SampleCenterLocation`` 기하**로 구한다 — Camtek 의
    ``col_origin``/``row_total`` 과 같은 규칙이라 두 장비가 자동으로 정렬된다.
    그게 없을 때만 옛 경로로 폴백한다: ``zero_x`` 는 ``SampleTestPlan`` 의 XINDEX
    최솟값, ``zero_y`` 는 상수.  순수 함수.
    """
    pm = _DIEPITCH_PAT.search(text)
    if pm is None:
        return None
    try:
        px, py = float(pm.group(1)), float(pm.group(2))
    except ValueError:
        return None
    if not (_MIN_PITCH <= px <= _MAX_PITCH and _MIN_PITCH <= py <= _MAX_PITCH):
        return None

    zeros = _kla_zeros_from_center(text, px, py)
    if zeros is not None:
        return KlaGeometry(pitch_x=px, pitch_y=py, zero_x=zeros[0], zero_y=zeros[1],
                           source="DiePitch+SampleCenterLocation")

    zero_x, src = KLA_ZERO_X, "DiePitch"
    tm = _TESTPLAN_PAT.search(text)
    if tm:
        pairs = _INDEX_PAIR_PAT.findall(tm.group(1))
        if pairs:
            zero_x = -min(int(a) for a, _ in pairs)
            src = "DiePitch+SampleTestPlan"
    return KlaGeometry(pitch_x=px, pitch_y=py, zero_x=zero_x, zero_y=KLA_ZERO_Y,
                       source=src)


@lru_cache(maxsize=256)
def kla_geometry(folder: Path) -> KlaGeometry:
    """폴더의 KLA die 격자 기하.  못 읽으면 TB500 폴백(+경고).  fail-safe."""
    from . import kla_info        # 순환 import 회피

    try:
        info = kla_info._find_info_file(folder)
        if info is not None:
            with open(info, "rb") as fh:
                head = fh.read(kla_info._HEAD_BYTES)
            geom = parse_kla_header(head.decode("utf-8", errors="replace"))
            if geom is not None:
                if geom.source == "DiePitch":
                    _LOG.warning(
                        "KLA %s 에 SampleTestPlan 이 없어 die 인덱스 원점 X 도 "
                        "기본값(%d)을 씁니다.", info.name, KLA_ZERO_X)
                return geom
        _LOG.warning(
            "KLA die 격자 정보를 찾지 못해 기본값을 씁니다: %s", folder)
        return FALLBACK_KLA
    except Exception:
        return FALLBACK_KLA
