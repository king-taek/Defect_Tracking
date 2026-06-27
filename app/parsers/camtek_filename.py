"""Camtek 파일명에서 직접 좌표 추출 (문서 Section 6 / 13.3.4 + 실제 AOI 도구 스키마).

Camtek 스캔 이미지는 파일명에 die 위치(col,row)와 local 좌표(x,y)가 포함된다.
관찰된 레이아웃(원본 자료 Module_KLA 의 파일명 생성 규칙 포함):

  (A) Section 6      : R_..._{wafer}_{col}_{row}_{x}_{y}_{DefectName}.jpg
  (B) Section 13.3.4 : R_..._{wafer}_{col}_{row}_{DefectName}_{x}_{y}
  (C) AOI 변환 결과  : {PREFIX}_{LOT}_{wafer}_{col}_{row}_{DefectName}_{x}_{y}_{DXSize}_{DYSize}_{DArea}.jpg

핵심 규칙(세 레이아웃 공통):
  - col/row 는 die 위치를 나타내는 **연속한 두 정수 토큰**(파일명에서 처음 등장하는 쌍).
  - col/row 뒤에는 **반드시 defect 이름(영문자 포함 토큰)** 이 존재한다.
    (KLA 원본 이름 `wafer_0_1_7_1` 처럼 이름이 없는 건 Camtek 형식이 아님 → NOT_FOUND)
  - x/y 는 col/row 뒤에서 **처음 등장하는 두 수치 토큰**(정수/소수 모두 가능).
    (C) 처럼 그 뒤에 수치가 더 있으면 차례로 DXSize/DYSize/DArea 로 본다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.models import ParseStatus

_INT_RE = re.compile(r"^-?\d+$")
_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")  # 정수 또는 소수
_HAS_LETTER_RE = re.compile(r"[A-Za-z가-힣]")


@dataclass
class CamtekNameResult:
    status: ParseStatus
    col: Optional[int] = None
    row: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None
    defect_name: str = ""
    dx_size: Optional[float] = None
    dy_size: Optional[float] = None
    d_area: Optional[float] = None


def _is_number(tok: str) -> bool:
    return bool(_NUM_RE.match(tok))


def parse_camtek_filename(filename: str) -> CamtekNameResult:
    """Camtek 파일명에서 col/row/x/y(+크기/면적)와 defect 이름을 추출한다.

    좌표 형식이 아니면 ParseStatus.NOT_FOUND 를 반환한다.
    """
    stem = re.sub(r"\.(jpg|jpeg|png|bmp|tif|tiff)$", "", filename, flags=re.IGNORECASE)
    tokens = stem.split("_")

    # col, row = 연속한 두 정수 토큰 중 첫 번째 쌍 (die 위치)
    col = row = col_idx = None
    for i in range(len(tokens) - 1):
        if _INT_RE.match(tokens[i]) and _INT_RE.match(tokens[i + 1]):
            col, row, col_idx = int(tokens[i]), int(tokens[i + 1]), i
            break
    if col is None:
        return CamtekNameResult(ParseStatus.NOT_FOUND)

    after = tokens[col_idx + 2:]
    # col/row 뒤에 defect 이름(영문자 포함)이 없으면 Camtek 형식이 아님(KLA 원본 등).
    if not any(_HAS_LETTER_RE.search(t) for t in after):
        return CamtekNameResult(ParseStatus.NOT_FOUND)

    # x/y = col/row 뒤 처음 등장하는 두 수치 토큰. 그 뒤 수치는 크기/면적.
    nums = [t for t in after if _is_number(t)]
    if len(nums) < 2:
        return CamtekNameResult(ParseStatus.NOT_FOUND)
    x = float(nums[0])
    y = float(nums[1])
    dx_size = float(nums[2]) if len(nums) >= 3 else None
    dy_size = float(nums[3]) if len(nums) >= 4 else None
    d_area = float(nums[4]) if len(nums) >= 5 else None

    defect_name = " ".join(t for t in after if not _is_number(t)).strip()

    return CamtekNameResult(
        status=ParseStatus.OK,
        col=col,
        row=row,
        x=x,
        y=y,
        defect_name=defect_name,
        dx_size=dx_size,
        dy_size=dy_size,
        d_area=d_area,
    )
