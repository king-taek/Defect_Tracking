"""AOI 엔지니어 모드 좌표 데이터 모델 + die 격자 변환 **폴백** 상수.

`king-taek/coding` 의 ``aoi_verification/app/coords/models.py`` 를 그대로 옮긴 것이다
(Surface.flt geometry 부분은 이 앱에서 쓰지 않아 제외).

아래 상수들은 TB500 한 대의 실측값이다.  **평상시에는 쓰이지 않는다** —
:mod:`~.wafer_geometry` 가 결과 폴더의 ``Params_WaferInfo.ini`` / KLA ``.001`` 에서
읽은 값을 쓰고, 그게 없을 때만 여기로 떨어진다(그때 경고를 남긴다)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

__all__ = ["DefectCoord", "CAMTEK_PITCH_X", "CAMTEK_PITCH_Y",
           "CAMTEK_COL_OFFSET", "DEFAULT_WAFER_DIAMETER",
           "KLA_ZERO_X", "KLA_ZERO_Y"]


@dataclass(frozen=True)
class DefectCoord:
    """변환 완료된 defect 좌표 — 세 소스(Camtek INI / LIVE 파일명 / KLA .001) 공통 표현."""
    col: int       # 0-based 표준 die column (Camtek/KLA 통일)
    row: int       # 0-based 표준 die row (아래에서 위, Camtek/KLA·현물 웨이퍼 맵 정렬)
    x: float       # die 내부 local X (µm)
    y: float       # die 내부 local Y (µm)
    source: str    # "camtek_ini" | "camtek_live" | "camtek_abs" | "kla"
    # KLA 원본 die-내부 좌표(XREL/YREL, µm) — source="kla" 일 때만 채운다.
    native_x: Optional[float] = None
    native_y: Optional[float] = None


# ── Camtek INI 변환 폴백 상수 ────────────────────────────────────────────
# 변환식 (장비 화면 정답 4-device 실측으로 확정):
#   col = x_index - col_origin      col_origin = ceil((Center_X − D/2) / pitch_x)
#   row = row_total - y_index       row_total  = floor((Center_Y + D/2) / pitch_y) − 1
#   x   = floor(X - x_index × pitch_x)            ← 장비 표기는 반올림이 아니라 버림
#   y   = floor(Y - y_index × pitch_y)
# col·row 기준은 상수가 아니라 **웨이퍼의 stage 위치**에서 나온 유도값이다.  아래
# CAMTEK_COL_OFFSET / DEFAULT_WAFER_DIAMETER 는 Center_* 가 미기록일 때의 폴백 재료다.
# pitch 는 평상시 Params_WaferInfo.ini `[Geometry] DieStep_X/Y` 에서 읽는다.
CAMTEK_PITCH_X: float = 37247.7   # µm/die (TB500 폴백)
CAMTEK_PITCH_Y: float = 44905.4   # µm/die (TB500 폴백)
# col 오프셋 2 는 pitch 가 전혀 다른 3개 device 에서 모두 성립 — 고정 시스템 오프셋.
CAMTEK_COL_OFFSET: int = 2
# 웨이퍼 직경(µm) — die 격자 원점 계산용.  평상시에는 Params_WaferInfo.ini
# `[Geometric] Diameter` 에서 읽고, 없을 때만 이 값을 쓴다.
DEFAULT_WAFER_DIAMETER: float = 300000.0
# ⚠ row 기준을 상수로 박지 말 것 — `Center_Y` 에서 유도하고, 미기록일 때만
#   ceil(Diameter/pitch_y) 로 폴백한다.

# ── KLA .001 변환 폴백 상수 (TB500 실측) ──────────────────────────────────
# col = XINDEX + zero_x ,  row = YINDEX + zero_y ,  x = round(XREL) ,
# y = round(DiePitchY - YREL)
# 평상시에는 `.001` 헤더의 SampleCenterLocation 으로 유도한다
# (wafer_geometry._kla_zeros_from_center).  ⚠ KLA_ZERO_Y 는 device 마다 다르다.
KLA_ZERO_X: int = 3   # 폴백 — SampleTestPlan 의 −min(XINDEX) 도 못 구할 때
KLA_ZERO_Y: int = 4   # 폴백 — SampleCenterLocation 이 없을 때(TB500 실측 상수)
