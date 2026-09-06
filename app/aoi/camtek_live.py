"""Camtek LIVE 파일명에서 좌표 추출 (AOI 모드).

`king-taek/coding` ``coords/camtek_live.py`` 의 이식.  정규식으로 위치를 맞추지 않고
**``_`` 로 토큰을 쪼개서** 해석한다.  관찰된 배치가 셋이고 정규식으로는 서로 잡아먹기
때문이다:

  A) ..._col_row_x_y[_DefectName]                 x/y 뒤에 이름(선택)
  B) ..._col_row_DefectName_x_y                   x/y 앞에 이름
  C) ..._col_row_DefectName_x_y_DXSize_DYSize_DArea    ★ x/y 뒤에 크기·면적이 더 붙는다

규칙 세 개로 셋을 다 덮는다:

1. ``col``/``row`` = 파일명에서 **처음 등장하는 '연속한 두 정수 토큰'**.
2. 그 앞에 식별자 토큰이 **2개 이상** 있어야 한다 — KLA 파일명 배제용.
3. ``x``/``y`` = ``col``/``row`` **뒤에서 처음 등장하는 두 수치 토큰**.
   그 뒤에 수치가 더 있으면 (C) 의 크기·면적이며 **좌표로 쓰지 않는다.**

★ **col/row 토큰은 보정하지 않는다.** :mod:`.camtek_ini` 가 내는
``row = row_total − y_index`` 와 같은 규약이다.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple, Optional

from .models import DefectCoord

__all__ = ["resolve", "parse_live_name", "LiveName"]

# 정수 토큰.  **음수를 포함시키는 게 중요하다** — KLA 파일명 ``00MEU018XYG1_-1_4_23_1``
# 에서 `-1` 을 정수로 보지 않으면 '처음 연속한 정수 쌍' 이 `4`,`23` 으로 밀려
# col=4,row=23 으로 오인한다.
_INT = re.compile(r'^-?\d+$')
_NUM = re.compile(r'^-?\d+(?:\.\d+)?$')

# col/row 앞에 있어야 하는 최소 식별자 토큰 수.
# KLA 이미지 파일명은 `{WaferID}_{...}` 로 앞이 **1개**(웨이퍼 ID)뿐이고,
# LIVE 는 레시피·로트·웨이퍼가 앞에 붙어 2개 이상이다.
_MIN_PREFIX_TOKENS = 2


class LiveName(NamedTuple):
    """파일명 토큰 해석 결과.  ``extra`` 는 x/y 뒤에 남은 수치(=(C) 의 크기·면적)."""
    col: int
    row: int
    x: float
    y: float
    extra: tuple[float, ...]


def parse_live_name(stem: str) -> Optional[LiveName]:
    """LIVE 파일명 stem → :class:`LiveName`.  형식이 아니면 ``None``.  순수 함수."""
    toks = stem.split('_')

    # 규칙 1 — 처음 등장하는 '연속한 두 정수 토큰'
    at = next((i for i in range(len(toks) - 1)
               if _INT.match(toks[i]) and _INT.match(toks[i + 1])), None)
    if at is None:
        return None

    # 규칙 2 — 앞에 식별자 토큰이 2개 이상 (KLA 파일명 배제)
    if at < _MIN_PREFIX_TOKENS:
        return None

    col, row = int(toks[at]), int(toks[at + 1])
    # 0-based 웨이퍼 맵에 음수 die 는 존재할 수 없다.  규칙 2 를 우연히 통과한
    # KLA 계열 이름(`LOT_W1_-2_-2_31_2` 같은 것)을 여기서 한 번 더 거른다.
    if col < 0 or row < 0:
        return None

    # 규칙 3 — col/row 뒤에서 **처음** 두 수치.
    nums = [float(t) for t in toks[at + 2:] if _NUM.match(t)]
    if len(nums) < 2:
        return None

    return LiveName(col=col, row=row, x=nums[0], y=nums[1],
                    extra=tuple(nums[2:]))


def resolve(image_path: Path) -> Optional[DefectCoord]:
    """LIVE 형식 파일명에서 DefectCoord 추출. 형식이 맞지 않으면 None."""
    got = parse_live_name(image_path.stem)
    if got is None:
        return None
    return DefectCoord(col=got.col, row=got.row, x=got.x, y=got.y,
                       source="camtek_live")
