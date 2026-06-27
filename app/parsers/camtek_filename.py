"""Camtek 파일명에서 직접 좌표 추출 (문서 Section 6 / 13.3.4).

Camtek 스캔 이미지는 파일명에 die 위치(col,row)와 local 좌표(x,y)가 이미 포함되어 있다.
관찰된 두 가지 레이아웃을 모두 처리한다:

  (A) Section 6     : R_..._{wafer}_{col}_{row}_{x}_{y}_{DefectName}.jpg
  (B) Section 13.3.4: R_..._{wafer}_{col}_{row}_{DefectName}_{x}_{y}

핵심: col/row 는 정수 토큰, x/y 는 소수점을 가진 부동소수 토큰이라는 점을 이용해
위치에 의존하지 않고 견고하게 추출한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.models import ParseStatus

_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+\.\d+$")


@dataclass
class CamtekNameResult:
    status: ParseStatus
    col: Optional[int] = None
    row: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None
    defect_name: str = ""


def parse_camtek_filename(filename: str) -> CamtekNameResult:
    """Camtek 파일명에서 col/row/x/y 와 defect 이름을 추출한다.

    좌표를 찾지 못하면 ParseStatus.NOT_FOUND 를 반환한다.
    """
    stem = re.sub(r"\.(jpg|jpeg|png|bmp|tif|tiff)$", "", filename, flags=re.IGNORECASE)
    tokens = stem.split("_")

    # x, y = 소수점을 포함한 부동소수 토큰 (등장 순서대로 앞의 두 개)
    float_tokens = [(i, t) for i, t in enumerate(tokens) if _FLOAT_RE.match(t)]
    if len(float_tokens) < 2:
        return CamtekNameResult(ParseStatus.NOT_FOUND)
    x_idx, x_tok = float_tokens[0]
    y_idx, y_tok = float_tokens[1]

    # col, row = 연속한 두 정수 토큰 중 첫 번째 쌍 (die 위치)
    col = row = None
    col_idx = None
    for i in range(len(tokens) - 1):
        if _INT_RE.match(tokens[i]) and _INT_RE.match(tokens[i + 1]):
            col = int(tokens[i])
            row = int(tokens[i + 1])
            col_idx = i
            break
    if col is None or row is None:
        return CamtekNameResult(ParseStatus.NOT_FOUND)

    # defect 이름: col/row 뒤, 좌표가 아닌 알파벳 포함 토큰들을 모은다.
    used = {col_idx, col_idx + 1, x_idx, y_idx}
    name_tokens = [
        t
        for i, t in enumerate(tokens)
        if i > col_idx + 1 and i not in used and not _FLOAT_RE.match(t)
    ]
    defect_name = " ".join(name_tokens).strip()

    return CamtekNameResult(
        status=ParseStatus.OK,
        col=col,
        row=row,
        x=float(x_tok),
        y=float(y_tok),
        defect_name=defect_name,
    )
