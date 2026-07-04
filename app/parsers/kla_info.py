"""KLA info(.001) 기반 좌표 변환 (문서 Section 13.2 및 KLA 변환 보고서).

같은 wafer 폴더의 KLA info 파일에서 jpg 파일명과 동일한 TiffFileName 을 찾고,
그 아래 DefectList line 의 XREL/YREL/XINDEX/YINDEX 와 header 의 DiePitchY 로 변환한다.

  col = XINDEX + zeroX
  row = YINDEX + zeroY
  x   = Round(XREL, 0)
  y   = Round(DiePitchY - YREL, 0)   # Y 방향은 DiePitchY 기준으로 반전

zeroX/zeroY 는 info 파일의 `SampleTestPlan` 블록(그 lot/step 에서 실제 관측된
XINDEX/YINDEX 최소값)에서 우선 계산한다 — 제품 설정(PackageX/Y÷2)은 이 블록이
없을 때만 쓰는 폴백이다. 제품 설정값은 디바이스 DB 시트를 잘못 참조하는 등으로
실측과 어긋날 수 있어(정답 VBA 도구/AOIDeviceDB.xlsx 로 확인한 DEVA 사례 —
"DEVA"과 "DEVA Live" 두 시트가 있는데 후자가 실제 운영 값(PackageY=6, zeroY=3)),
info 파일 자신의 실측값이 더 신뢰할 수 있다.

원본 info/이미지 파일은 read-only 로만 읽는다.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app import config
from app.models import ParseStatus
from app.safety import read_only_bytes

_log = logging.getLogger("conder.parsers.kla")

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
    reason: str = ""  # 진단용: 실패 사유(성공이면 빈 문자열)


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

    _skip = frozenset((".pass", ".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"))
    candidates = [
        f
        for f in filenames
        if ext(f) not in _skip
    ]
    return sorted(candidates)[0] if candidates else None


def _read_text(path: Path) -> str:
    data = read_only_bytes(path)
    for encoding in ("utf-8", "cp949", "utf-16-le", "utf-16-be", "latin-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, ValueError):
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


def _parse_sample_test_plan(lines: list[str]) -> Optional[tuple[int, int]]:
    """`SampleTestPlan N` 블록에서 실측 XINDEX/YINDEX 최소값 기준 zeroX/zeroY 를 구한다.

    블록은 `SampleTestPlan <개수>` 라인 다음에 `XINDEX YINDEX` 쌍이 이어지고,
    선언된 개수만큼 읽거나 `;`로 끝나는 라인을 만나면 끝난다.
    """
    n = len(lines)
    i = 0
    while i < n:
        m = re.match(r"(?i)^\s*SampleTestPlan\s+(\d+)\s*$", lines[i])
        if not m:
            i += 1
            continue
        count = int(m.group(1))
        xs: list[int] = []
        ys: list[int] = []
        i += 1
        while i < n and len(xs) < count:
            entry = lines[i].strip()
            i += 1
            if not entry:
                continue
            terminated = entry.endswith(";")
            nums = re.findall(r"-?\d+", entry.rstrip(";").strip())
            if len(nums) >= 2:
                xs.append(int(nums[0]))
                ys.append(int(nums[1]))
            if terminated:
                break
        if xs and ys:
            return (-min(xs), -min(ys))
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


_KLA_FNAME_RE = re.compile(
    r"^.+?_(-?\d+)_(-?\d+)_(\d+)_(\d+)\.[a-zA-Z]+$"
)


@dataclass
class _ParsedInfo:
    die_pitch_y: Optional[float]
    # jpg 파일명(소문자) -> DefectList 필드
    defects: dict[str, list[float]]
    all_defects: list[list[float]] = field(default_factory=list)
    # SampleTestPlan 실측 기반 (zeroX, zeroY). 블록이 없으면 None(제품 설정값 폴백).
    sample_zero: Optional[tuple[int, int]] = None


def parse_info_text(text: str) -> _ParsedInfo:
    """KLA info 텍스트를 파싱해 DiePitchY 와 TiffFileName->DefectList 매핑을 만든다.

    TiffFileName 이 없는 DefectList 엔트리도 all_defects 에 수집하여,
    TiffFileName 매칭 실패 시 XINDEX/YINDEX 기반 폴백 검색에 쓴다.
    """
    lines = text.splitlines()
    die_pitch_y = _parse_die_pitch_y(lines)
    sample_zero = _parse_sample_test_plan(lines)
    defects: dict[str, list[float]] = {}
    all_defects: list[list[float]] = []

    i = 0
    n = len(lines)
    pending_tiff: Optional[str] = None
    in_defect_block = False
    while i < n:
        s = lines[i].strip()
        m = re.match(r"(?i)^TiffFileName\s+(.+?);?\s*$", s)
        if m:
            pending_tiff = m.group(1).strip().strip(";").strip().lower()
            in_defect_block = False
            i += 1
            continue
        if s.lower().startswith("defectlist"):
            rest = s[len("defectlist"):].strip()
            if rest:
                fields = _parse_defect_fields(rest)
                if fields is not None:
                    all_defects.append(fields)
                    if pending_tiff:
                        defects[pending_tiff] = fields
                        pending_tiff = None
            else:
                in_defect_block = True
            i += 1
            continue
        if (in_defect_block or pending_tiff) and s:
            fields = _parse_defect_fields(s)
            if fields is not None:
                all_defects.append(fields)
                if pending_tiff:
                    defects[pending_tiff] = fields
                    pending_tiff = None
            else:
                in_defect_block = False
                pending_tiff = None
        i += 1

    return _ParsedInfo(die_pitch_y=die_pitch_y, defects=defects,
                       all_defects=all_defects, sample_zero=sample_zero)


def load_info(info_path: str | Path) -> _ParsedInfo:
    return parse_info_text(_read_text(Path(info_path)))


def convert_from_parsed(parsed: _ParsedInfo, jpg_filename: str) -> KlaResult:
    """미리 파싱한 info 에서 jpg 파일명에 해당하는 좌표를 계산."""
    key = Path(jpg_filename).name.lower()
    fields = parsed.defects.get(key)
    if fields is None:
        # 정확 파일명 실패 시 stem(확장자 제외) 일치로 한 번 더 시도.
        # 예) 이미지 foo.jpg ↔ TiffFileName foo.tif 처럼 확장자만 다른 경우.
        stem = Path(jpg_filename).stem.lower()
        for k, v in parsed.defects.items():
            if Path(k).stem == stem:
                fields = v
                break
    fname_match = _KLA_FNAME_RE.match(key)
    if fields is None and parsed.all_defects and fname_match:
        want_xi = int(fname_match.group(1))
        want_yi = int(fname_match.group(2))
        want_id = int(fname_match.group(4))
        for entry in parsed.all_defects:
            if (len(entry) >= _MIN_FIELDS
                    and int(round(entry[_XINDEX_IDX])) == want_xi
                    and int(round(entry[_YINDEX_IDX])) == want_yi
                    and int(round(entry[0])) == want_id):
                fields = entry
                break
    if fields is None:
        # class(그룹 3)==0(Unclassified) 파일명은 KLARF 에 정식 결함으로 등록된 적
        # 없는 미분류 후보 이미지일 가능성이 높다(정상) — 파일명을 사유에 넣지 않는
        # 고정 문구로 반환해 진단 리포트에서 파일마다 따로 클러스터링되지 않게 한다.
        if fname_match and fname_match.group(3) == "0":
            return KlaResult(
                ParseStatus.NOT_FOUND,
                reason=(
                    "KLA: 미분류(class 0) 후보 이미지 — info DefectList 에 정식 결함으로 "
                    "등록되지 않음(정상, 무시 가능)"
                ),
            )
        sample = ", ".join(list(parsed.defects)[:3])
        return KlaResult(
            ParseStatus.NOT_FOUND,
            reason=(
                f"info 에 TiffFileName '{key}' 매칭 실패"
                f"(보유 {len(parsed.defects)}개{', 예: ' + sample if sample else ''}, "
                f"DefectList {len(parsed.all_defects)}건)"
            ),
        )
    if parsed.die_pitch_y is None:
        return KlaResult(
            ParseStatus.INVALID_INFO, reason="info header 에 DiePitchY 없음"
        )

    xrel = fields[_XREL_IDX]
    yrel = fields[_YREL_IDX]
    xindex = int(round(fields[_XINDEX_IDX]))
    yindex = int(round(fields[_YINDEX_IDX]))

    zero_x, zero_y = parsed.sample_zero or (config.kla_zero_x(), config.kla_zero_y())
    col = xindex + zero_x
    row = yindex + zero_y
    # 음수 die 위치는 비정상(잘못된 XINDEX/YINDEX) — 잘못 매칭되지 않도록 실패 처리.
    if col < 0 or row < 0:
        _log.warning(
            "KLA die 위치가 음수입니다(col=%s,row=%s) — %s", col, row, jpg_filename
        )
        return KlaResult(
            ParseStatus.INVALID_INFO,
            reason=f"die 위치 음수(col={col},row={row}) — XINDEX/YINDEX 비정상",
        )
    x = round(xrel)
    y = round(parsed.die_pitch_y - yrel)
    return KlaResult(status=ParseStatus.OK, col=col, row=row, x=float(x), y=float(y))


def convert_kla(info_path: str | Path, jpg_filename: str) -> KlaResult:
    """KLA info 파일을 읽어 jpg 에 해당하는 col_row_x_y 위치 정보를 계산."""
    try:
        parsed = load_info(info_path)
    except OSError as exc:
        return KlaResult(
            ParseStatus.INFO_FILE_NOT_FOUND, reason=f"info 파일 열기 실패: {exc}"
        )
    return convert_from_parsed(parsed, jpg_filename)
