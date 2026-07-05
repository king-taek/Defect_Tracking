"""외부 디바이스 DB(AOIDeviceDB.xlsx) 로더 — 제품 일반화.

원본 자료 구조: 시트 1개 = 디바이스 1개. 각 시트에 다음이 있다.
  Package Info
    X  | <package X die 개수>
    Y  | <package Y die 개수>
    X1 | <die pitch X (mm 근사)>
    Y1 | <die pitch Y (mm 근사)>
  Map
    <Y개 행 × X개 열의 격자. die 가 존재하는 칸에 값(0)이 있고, 없는 칸은 빈칸>

이 정보로 제품별 package count·pitch·die 배치(웨이퍼 모양)를 구성한다.
원본/DB 파일은 read-only 로만 읽는다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

_log = logging.getLogger("defect_tracker.device_db")

_PKG_KEYS = ("X", "Y", "X1", "Y1")


@dataclass(frozen=True)
class DeviceProfile:
    """디바이스 1개의 패키지/배치 정보."""

    key: str
    name: str
    x_count: int
    y_count: int
    pitch_x: float  # die pitch X (단위는 좌표계와 동일하게 ×1000 환산)
    pitch_y: float
    die_map: frozenset = field(default_factory=frozenset)  # 존재하는 (col,row) 집합


def _to_number(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_sheet(title: str, rows: list[tuple]) -> DeviceProfile | None:
    """한 시트(rows: values_only 행 목록)에서 DeviceProfile 을 만든다. 실패 시 None."""
    pkg: dict[str, float] = {}
    map_start: int | None = None
    for i, r in enumerate(rows):
        if not r:
            continue
        c0 = "" if r[0] is None else str(r[0]).strip()
        if c0 in _PKG_KEYS and len(r) > 1:
            num = _to_number(r[1])
            if num is not None:
                pkg[c0] = num
        elif c0.lower() == "map":
            map_start = i + 1

    if "X" not in pkg or "Y" not in pkg:
        return None
    x_count = int(round(pkg["X"]))
    y_count = int(round(pkg["Y"]))
    if x_count <= 0 or y_count <= 0 or x_count > 200 or y_count > 200:
        return None
    pitch_x = pkg.get("X1", 0.0) * 1000.0
    pitch_y = pkg.get("Y1", 0.0) * 1000.0

    die_map: set[tuple[int, int]] = set()
    if map_start is not None:
        for ri in range(y_count):
            idx = map_start + ri
            row = rows[idx] if idx < len(rows) else ()
            for ci in range(x_count):
                v = row[ci] if row and ci < len(row) else None
                if v is not None and str(v).strip() != "":
                    die_map.add((ci, ri))

    return DeviceProfile(
        key=title,
        name=title,
        x_count=x_count,
        y_count=y_count,
        pitch_x=pitch_x,
        pitch_y=pitch_y,
        die_map=frozenset(die_map),
    )


def load_device_db(path: str | Path) -> dict[str, DeviceProfile]:
    """AOIDeviceDB.xlsx 를 읽어 {device_name: DeviceProfile} 를 반환한다.

    Package Info(X/Y) 가 없는 시트는 건너뛴다. 파일/시트 오류는 로깅 후 건너뛴다.
    """
    import openpyxl  # 지연 임포트(시작 비용 절감)

    out: dict[str, DeviceProfile] = {}
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        _log.warning("디바이스 DB 로드 실패(%s): %s", path, exc)
        return out
    try:
        for ws in wb.worksheets:
            try:
                rows = list(ws.iter_rows(values_only=True))
                prof = _parse_sheet(ws.title, rows)
            except Exception as exc:  # noqa: BLE001
                _log.warning("시트 파싱 실패(%s): %s", ws.title, exc)
                prof = None
            if prof is not None:
                out[prof.key] = prof
    finally:
        wb.close()
    _log.info("디바이스 DB 로드: %d개 디바이스 (%s)", len(out), path)
    return out
