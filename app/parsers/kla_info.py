"""KLA info(.001) 기반 좌표 변환 (문서 Section 13.2 및 KLA 변환 보고서).

같은 wafer 폴더의 KLA info 파일에서 jpg 파일명과 동일한 TiffFileName 을 찾고,
그 아래 DefectList line 의 XREL/YREL/XINDEX/YINDEX 와 header 의 DiePitchY 로 변환한다.

  col = XINDEX + zeroX(=3)
  row = YINDEX + zeroY(=3)
  x   = Round(XREL, 0)
  y   = Round(DiePitchY - YREL, 0)   # Y 방향은 DiePitchY 기준으로 반전

원본 info/이미지 파일은 read-only 로만 읽는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app import config
from app.models import ParseStatus
from app.safety import read_only_bytes

# DefectList 필드 순서(문서 Section 13.2.5.2):
# DEFECTID X Y XREL YREL XINDEX YINDEX XSIZE YSIZE ...
_XREL_IDX = 3
_YREL_IDX = 4
_XINDEX_IDX = 5
_YINDEX_IDX = 6
_MIN_FIELDS = 7


@dataclass
class KlaResult:
    status: ParseStatus
    col: Optional[int] = None
    row: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None


def select_info_file(filenames: list[str]) -> Optional[str]:
    """wafer 폴더 파일 목록에서 KLA info 파일을 고른다 (문서 Section 13.2.3).

    1) 확장자 .001 우선
    2) 없으면 .pass 가 아닌 비-jpg 파일
    3) .pass / .jpg(.jpeg) 는 info 로 사용하지 않음
    """
    def ext(name: str) -> str:
        return Path(name).suffix.lower()

    dot001 = [f for f in filenames if ext(f) == ".001"]
    if dot001:
        return sorted(dot001)[0]

    candidates = [
        f
        for f in filenames
        if ext(f) not in (".pass", ".jpg", ".jpeg")
    ]
    return sorted(candidates)[0] if candidates else None


def _read_text(path: Path) -> str:
    data = read_only_bytes(path)
    for encoding in ("utf-8", "cp949", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def _parse_die_pitch_y(lines: list[str]) -> Optional[float]:
    for line in lines:
        s = line.strip()
        if s.lower().startswith("diepitch"):
            nums = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
            if len(nums) >= 2:
                try:
                    return float(nums[1])
                except ValueError:
                    return None
    return None


def _parse_defect_fields(data_line: str) -> Optional[list[float]]:
    cleaned = data_line.strip().rstrip(";").strip()
    parts = cleaned.split()
    if len(parts) < _MIN_FIELDS:
        return None
    try:
        return [float(p) for p in parts[:_MIN_FIELDS]]
    except ValueError:
        return None


@dataclass
class _ParsedInfo:
    die_pitch_y: Optional[float]
    # jpg 파일명(소문자) -> DefectList 필드
    defects: dict[str, list[float]]


def parse_info_text(text: str) -> _ParsedInfo:
    """KLA info 텍스트를 파싱해 DiePitchY 와 TiffFileName->DefectList 매핑을 만든다."""
    lines = text.splitlines()
    die_pitch_y = _parse_die_pitch_y(lines)
    defects: dict[str, list[float]] = {}

    i = 0
    n = len(lines)
    while i < n:
        s = lines[i].strip()
        m = re.match(r"(?i)^TiffFileName\s+(.+?);?\s*$", s)
        if m:
            tiff_name = m.group(1).strip().strip(";").strip().lower()
            # 바로 아래에서 DefectList 데이터 line 을 찾는다.
            fields = None
            j = i + 1
            while j < n and j <= i + 4:  # 바로 아래 몇 줄 이내
                nxt = lines[j].strip()
                if not nxt:
                    j += 1
                    continue
                if nxt.lower().startswith("defectlist"):
                    # 키워드 뒤에 데이터가 같은 줄에 있을 수도, 다음 줄일 수도 있음
                    rest = nxt[len("defectlist"):].strip()
                    if rest:
                        fields = _parse_defect_fields(rest)
                        break
                    j += 1
                    continue
                fields = _parse_defect_fields(nxt)
                break
            if fields is not None and tiff_name:
                defects[tiff_name] = fields
        i += 1

    return _ParsedInfo(die_pitch_y=die_pitch_y, defects=defects)


def load_info(info_path: str | Path) -> _ParsedInfo:
    return parse_info_text(_read_text(Path(info_path)))


def convert_from_parsed(parsed: _ParsedInfo, jpg_filename: str) -> KlaResult:
    """미리 파싱한 info 에서 jpg 파일명에 해당하는 좌표를 계산."""
    key = Path(jpg_filename).name.lower()
    fields = parsed.defects.get(key)
    if fields is None:
        return KlaResult(ParseStatus.NOT_FOUND)
    if parsed.die_pitch_y is None:
        return KlaResult(ParseStatus.INVALID_INFO)

    xrel = fields[_XREL_IDX]
    yrel = fields[_YREL_IDX]
    xindex = int(round(fields[_XINDEX_IDX]))
    yindex = int(round(fields[_YINDEX_IDX]))

    col = xindex + config.kla_zero_x()
    row = yindex + config.kla_zero_y()
    x = round(xrel)
    y = round(parsed.die_pitch_y - yrel)
    return KlaResult(status=ParseStatus.OK, col=col, row=row, x=float(x), y=float(y))


def convert_kla(info_path: str | Path, jpg_filename: str) -> KlaResult:
    """KLA info 파일을 읽어 jpg 에 해당하는 col_row_x_y 위치 정보를 계산."""
    try:
        parsed = load_info(info_path)
    except OSError:
        return KlaResult(ParseStatus.INFO_FILE_NOT_FOUND)
    return convert_from_parsed(parsed, jpg_filename)
