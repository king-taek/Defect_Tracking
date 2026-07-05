"""ColorImageGrabingInfo.ini 기반 Camtek 좌표 산출 (문서 Section 13.3).

원본 이미지 이름(예: 253715.91797.c.-1104740629.1)에 ".jpeg" 를 붙여 INI section 을 찾고,
해당 section 의 X/Y(없으면 FaultX/FaultY)와 Col/Row 로 위치 정보를 계산한다.

  col = Col - camtek_col_offset
  row = camtek_row_base - Row
  x   = X - Col * camtek_pitch_x
  y   = Y - Row * camtek_pitch_y

(상수는 활성 제품 프로파일(`config.active_product()`)에서 온다 — 기본 DEVA 은
col_offset=2, row_base=7, pitch_x=37170.0, pitch_y=44830.0.)

원본 INI 는 read-only 로만 읽는다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app import config
from app.models import ParseStatus
from app.safety import read_only_bytes

_log = logging.getLogger("defect_tracker.parsers.ini")


@dataclass
class CamtekIniResult:
    status: ParseStatus
    col: Optional[int] = None
    row: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None
    reason: str = ""  # 진단용: 실패 사유(성공이면 빈 문자열)


def _parse_ini_sections(text: str) -> dict[str, dict[str, str]]:
    """INI 텍스트를 {section_name(소문자): {key(소문자): value}} 로 파싱.

    configparser 대신 직접 파싱: section 이름에 '.'/'-' 등 특수문자가 많고
    중복/비표준 라인이 있을 수 있으므로 관대하게 처리한다.
    """
    sections: dict[str, dict[str, str]] = {}
    current: Optional[str] = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip().lower()
            sections.setdefault(current, {})
        elif "=" in line and current is not None:
            key, _, value = line.partition("=")
            sections[current][key.strip().lower()] = value.strip()
    return sections


def _read_text(ini_path: Path) -> str:
    data = read_only_bytes(ini_path)
    for encoding in ("utf-8-sig", "utf-8", "cp949", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def load_ini(ini_path: str | Path) -> dict[str, dict[str, str]]:
    """INI 파일을 파싱해 section 사전을 반환 (캐싱은 호출 측 책임)."""
    return _parse_ini_sections(_read_text(Path(ini_path)))


def _to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_int(value: Optional[str]) -> Optional[int]:
    f = _to_float(value)
    if f is None:
        return None
    i = int(round(f))
    if abs(f - i) > 0.01:
        # Col/Row 는 정수여야 한다. 비정수면 데이터 이상 가능성 → 경고(반올림은 진행).
        _log.warning("INI Col/Row 비정수 값 %s → %d 로 반올림", value, i)
    return i


def convert_from_sections(
    sections: dict[str, dict[str, str]], original_name: str
) -> CamtekIniResult:
    """미리 파싱한 section 사전에서 원본 이름에 해당하는 좌표를 계산."""
    # INI section 키는 원본 이미지 파일명(확장자 포함)인데 저장된 확장자가
    # 제각각일 수 있으므로 후보를 순서대로 시도한다(.jpeg 우선으로 기존 동작 보존).
    section = None
    for ext in (".jpeg", ".jpg", ".png", ".bmp", ".tif", ".tiff", ""):
        section = sections.get(f"{original_name}{ext}".lower())
        if section is not None:
            break
    if section is None:
        return CamtekIniResult(
            ParseStatus.NOT_FOUND,
            reason=f"INI 에 이미지 '{original_name}' section 없음(section {len(sections)}개)",
        )

    # X/Y 우선, 없으면 FaultX/FaultY (Section 13.3.3)
    x_raw = _to_float(section.get("x"))
    if x_raw is None:
        x_raw = _to_float(section.get("faultx"))
    y_raw = _to_float(section.get("y"))
    if y_raw is None:
        y_raw = _to_float(section.get("faulty"))
    col_ini = _to_int(section.get("col"))
    row_ini = _to_int(section.get("row"))

    if x_raw is None or y_raw is None or col_ini is None or row_ini is None:
        missing = [
            n for n, v in (("x/faultx", x_raw), ("y/faulty", y_raw),
                           ("col", col_ini), ("row", row_ini)) if v is None
        ]
        return CamtekIniResult(
            ParseStatus.INVALID_INFO,
            reason=f"INI section 필드 누락: {', '.join(missing)}",
        )

    prod = config.active_product()
    col = col_ini - prod.camtek_col_offset
    row = prod.camtek_row_base - row_ini
    x = x_raw - col_ini * prod.camtek_pitch_x
    y = y_raw - row_ini * prod.camtek_pitch_y

    return CamtekIniResult(status=ParseStatus.OK, col=col, row=row, x=x, y=y)


def convert_camtek_ini(ini_path: str | Path, original_name: str) -> CamtekIniResult:
    """INI 파일을 읽어 원본 이름에 해당하는 col_row_x_y 위치 정보를 계산."""
    try:
        sections = load_ini(ini_path)
    except OSError as exc:
        return CamtekIniResult(
            ParseStatus.INFO_FILE_NOT_FOUND, reason=f"INI 파일 열기 실패: {exc}"
        )
    return convert_from_sections(sections, original_name)
