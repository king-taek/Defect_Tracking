"""Camtek INI 파일(ColorImageGrabingInfo.ini) 파싱 → DefectCoord (AOI 모드).

`king-taek/coding` ``coords/camtek_ini.py`` 의 이식.  변환식 — 상수가 아니라 폴더에서
읽은 :class:`~.wafer_geometry.CamtekGeometry` 를 쓴다.  **die 인덱스는 좌표에서
유도한다** — INI 의 ``Col``/``Row`` 필드는 레시피마다 원점이 다를 수 있어 변환에 쓰지
않는다::

    x_index = floor(X / geom.pitch_x)       y_index = floor(Y / geom.pitch_y)
    col = x_index - geom.col_origin         # col_origin  = 첫 완전 die 열
    row = geom.row_total - y_index          # row_total   = 마지막 완전 die 행
    x   = floor(X - x_index × pitch_x)      # 장비 표기 = 버림 (반올림 아님)
    y   = floor(Y - y_index × pitch_y)
"""

from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .ini_text import read_ini_text
from .models import CAMTEK_COL_OFFSET, DefectCoord
from .wafer_geometry import FALLBACK_CAMTEK, CamtekGeometry, camtek_geometry

__all__ = ["resolve", "load_folder", "load_abs_folder", "load_raw_folder",
           "load_recipe_folder", "abs_coord", "has_ini"]

# INI 파일 이름 후보 — 대소문자 두 가지
_INI_CANDIDATES = ("ColorImageGrabingInfo.ini", "ColorImageGrabinginfo.ini")

_KEY_PAT = re.compile(r'^(\w+)\s*=\s*(.+)$', re.MULTILINE)
_SECTION_PAT = re.compile(r'\[([^\]]+)\]')


def _find_ini(folder: Path) -> Optional[Path]:
    for name in _INI_CANDIDATES:
        p = folder / name
        if p.exists():
            return p
    return None


def has_ini(folder: Path) -> bool:
    """이 폴더에 Camtek INI 가 **있는가** — 파일 존재만 본다(파싱하지 않는다)."""
    try:
        return _find_ini(Path(folder)) is not None
    except OSError:
        return False


@lru_cache(maxsize=256)
def load_folder(folder: Path) -> dict[str, DefectCoord]:
    """폴더의 INI 파일을 파싱해 {stem(소문자) → DefectCoord} 맵 반환."""
    ini = _find_ini(folder)
    if ini is None:
        return {}
    try:
        geom = camtek_geometry(folder)
        if geom is None:
            # ★ pitch 를 몰라도 **매칭은 된다** — INI 의 절대 X/Y 를 그대로 쓰면 된다.
            return _parse_ini_abs(ini)
        return _parse_ini(ini, geom)
    except Exception:
        return {}


def _parse_ini(path: Path, geom: CamtekGeometry) -> dict[str, DefectCoord]:
    text = read_ini_text(path) or ""
    # 섹션 단위로 분리: [filename.jpeg] → 내용 반복
    parts = _SECTION_PAT.split(text)
    result: dict[str, DefectCoord] = {}
    it = iter(parts[1:])
    for name, content in zip(it, it):
        stem = Path(name.strip()).stem   # "foo.jpeg" → "foo"
        coord = _extract_coord(content, geom)
        if coord is not None:
            result[stem.lower()] = coord
    return result


def _extract_coord(content: str,
                   geom: CamtekGeometry = FALLBACK_CAMTEK) -> Optional[DefectCoord]:
    """INI 섹션 내용 → DefectCoord. 필수 키가 없으면 None."""
    raw = _extract_raw(content)
    if raw is None:
        return None
    X, Y, _col_i, _row_i = raw
    # ★ die 인덱스는 **좌표에서 유도**한다 — INI 의 Col/Row 필드를 쓰지 않는다.
    x_index = math.floor(X / geom.pitch_x)
    y_index = math.floor(Y / geom.pitch_y)
    col = x_index - geom.col_origin
    row = geom.row_total - y_index
    # 버림(floor) — 장비 화면·정답 데이터와 표기를 일치시킨다.
    x = float(math.floor(X - x_index * geom.pitch_x))
    y = float(math.floor(Y - y_index * geom.pitch_y))
    return DefectCoord(col=col, row=row, x=x, y=y, source="camtek_ini")


def abs_coord(X: float, Y: float, col_i: int, row_i: int) -> DefectCoord:
    """원시 ``(X, Y, Col, Row)`` → **절대 wafer 좌표** DefectCoord (순수 함수)."""
    return DefectCoord(col=col_i - CAMTEK_COL_OFFSET, row=-row_i,
                       x=float(math.floor(X)), y=float(math.floor(Y)),
                       source="camtek_abs")


def _parse_ini_abs(path: Path) -> dict[str, DefectCoord]:
    """die pitch 를 모를 때의 폴백 — **절대 wafer 좌표**로 DefectCoord 를 만든다.

    · ``col`` 은 pitch 없이도 정확하다(``Col − CAMTEK_COL_OFFSET``).
    · ``row`` 은 기준을 모르므로 추측하지 않고 ``−Row`` 를 버킷 키로만 쓴다
      (음수 → 장비 값이 아님이 드러난다).  ref/val 이 같은 규칙이라 ``(col,row) ±1``
      이웃 게이트는 정상 동작한다.
    · ``x/y`` 는 절대 좌표.  실제 물리 거리로 재므로 die-내부 비교보다 오히려 엄격하다.
    """
    text = read_ini_text(path) or ""
    parts = _SECTION_PAT.split(text)
    result: dict[str, DefectCoord] = {}
    it = iter(parts[1:])
    for name, content in zip(it, it):
        raw = _extract_raw(content)
        if raw is None:
            continue
        X, Y, col_i, row_i = raw
        result[Path(name.strip()).stem.lower()] = abs_coord(X, Y, col_i, row_i)
    return result


def _extract_raw(content: str) -> Optional[tuple[float, float, int, int]]:
    """INI 섹션 내용 → 원시 ``(X, Y, Col, Row)``. 필수 키가 없으면 None."""
    kv: dict[str, str] = {}
    for m in _KEY_PAT.finditer(content):
        kv[m.group(1).upper()] = m.group(2).strip()

    def fget(key: str) -> Optional[float]:
        v = kv.get(key)
        try:
            return float(v) if v is not None else None
        except ValueError:
            return None

    X = fget("X") if fget("X") is not None else fget("FAULTX")
    Y = fget("Y") if fget("Y") is not None else fget("FAULTY")
    Col = fget("COL")
    Row = fget("ROW")

    if None in (X, Y, Col, Row):
        return None
    return (X, Y, int(Col), int(Row))   # type: ignore[arg-type]


@lru_cache(maxsize=256)
def load_raw_folder(folder: Path) -> dict[str, tuple[float, float, int, int]]:
    """폴더의 INI → ``{stem(소문자) → (X, Y, Col, Row)}`` 원시값(pitch 검산용)."""
    ini = _find_ini(folder)
    if ini is None:
        return {}
    try:
        text = read_ini_text(ini) or ""
        parts = _SECTION_PAT.split(text)
        result: dict[str, tuple[float, float, int, int]] = {}
        it = iter(parts[1:])
        for name, content in zip(it, it):
            raw = _extract_raw(content)
            if raw is not None:
                result[Path(name.strip()).stem.lower()] = raw
        return result
    except Exception:
        return {}


@lru_cache(maxsize=256)
def load_recipe_folder(folder: Path) -> dict[str, int]:
    """폴더의 INI → ``{stem(소문자) → RecipeNumber}``.  키가 없으면 ``0``.

    검산을 **레시피별로 묶을 때** 쓴다 — 레시피마다 ``Row`` 필드의 원점이 1 다를 수 있다."""
    ini = _find_ini(folder)
    if ini is None:
        return {}
    try:
        text = read_ini_text(ini) or ""
        parts = _SECTION_PAT.split(text)
        result: dict[str, int] = {}
        it = iter(parts[1:])
        for name, content in zip(it, it):
            m = re.search(r"(?im)^\s*RecipeNumber\s*=\s*(-?\d+)\s*$", content)
            result[Path(name.strip()).stem.lower()] = int(m.group(1)) if m else 0
        return result
    except Exception:
        return {}


def resolve(image_path: Path) -> Optional[DefectCoord]:
    """이미지 1장 → DefectCoord. INI 가 없거나 섹션이 없으면 None."""
    coords = load_folder(image_path.parent)
    return coords.get(image_path.stem.lower())


@lru_cache(maxsize=256)
def load_abs_folder(folder: Path) -> dict[str, tuple[float, float]]:
    """폴더의 INI → {stem(소문자) → (절대 X, 절대 Y)}.  없으면 빈 dict."""
    ini = _find_ini(folder)
    if ini is None:
        return {}
    try:
        text = read_ini_text(ini) or ""
        parts = _SECTION_PAT.split(text)
        result: dict[str, tuple[float, float]] = {}
        it = iter(parts[1:])
        for name, content in zip(it, it):
            xy = _extract_abs(content)
            if xy is not None:
                result[Path(name.strip()).stem.lower()] = xy
        return result
    except Exception:
        return {}


def _extract_abs(content: str) -> Optional[tuple[float, float]]:
    """INI 섹션 내용 → (절대 X, 절대 Y).  X/Y(또는 FaultX/FaultY) 없으면 None."""
    kv: dict[str, str] = {}
    for m in _KEY_PAT.finditer(content):
        kv[m.group(1).upper()] = m.group(2).strip()

    def fget(key: str) -> Optional[float]:
        v = kv.get(key)
        try:
            return float(v) if v is not None else None
        except ValueError:
            return None

    X = fget("X") if fget("X") is not None else fget("FAULTX")
    Y = fget("Y") if fget("Y") is not None else fget("FAULTY")
    if X is None or Y is None:
        return None
    return (X, Y)
