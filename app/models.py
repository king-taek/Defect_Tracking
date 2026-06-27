"""도메인 데이터 모델.

좌표 변환 결과는 col_row_x_y 형식(문서 Section 13)으로 정규화되어 DefectRecord 에 담긴다.
모든 모델은 원본 파일 경로만 보관하고 원본을 수정하지 않는다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class Source(str, Enum):
    """defect 이미지의 좌표 출처."""

    CAMTEK_FILENAME = "Camtek(파일명)"
    CAMTEK_INI = "Camtek(INI)"
    KLA = "KLA"
    UNKNOWN = "Unknown"


class ParseStatus(str, Enum):
    """좌표 파싱 상태 (문서 Section 13의 예외 표기와 대응)."""

    OK = "OK"
    NOT_FOUND = "NOT_FOUND"
    INFO_FILE_NOT_FOUND = "INFO_FILE_NOT_FOUND"
    INVALID_INFO = "INVALID_INFO"


@dataclass
class DefectRecord:
    """단일 defect 이미지와 그 위치 정보.

    col/row 는 die 위치, x/y 는 die 내부 local 좌표(문서 Section 13.1).
    파싱 실패 시 status 로 사유를 보관하고 col/row/x/y 는 None 이다.
    """

    image_path: Path
    wafer_id: str
    layer: str  # 정규화된 layer 토큰 (예: LYA4, LYC3)
    layer_folder: str  # 원본 폴더명 (예: "2. LYC3_재리뷰")
    source: Source = Source.UNKNOWN
    status: ParseStatus = ParseStatus.OK
    col: Optional[int] = None
    row: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None
    defect_name: str = ""
    note: str = ""  # 파싱 관련 부가 정보
    dx_size: Optional[float] = None  # defect 크기 X (파일명에 있을 때)
    dy_size: Optional[float] = None  # defect 크기 Y
    d_area: Optional[float] = None  # defect 면적

    @property
    def ok(self) -> bool:
        return (
            self.status == ParseStatus.OK
            and self.col is not None
            and self.row is not None
            and self.x is not None
            and self.y is not None
        )

    @property
    def position_key(self) -> str:
        """col_row_x_y 형식의 정수 위치 키 (문서 최종 출력 형식)."""
        if not self.ok:
            return self.status.value
        return f"{self.col}_{self.row}_{round(self.x)}_{round(self.y)}"

    @property
    def die_key(self) -> tuple[int, int]:
        return (int(self.col), int(self.row))  # type: ignore[arg-type]

    @property
    def die_key_full(self) -> tuple[str, int, int]:
        """매칭 인덱스 키: (wafer_id, col, row)."""
        return (self.wafer_id, int(self.col), int(self.row))  # type: ignore[arg-type]

    def distance_to(self, other: "DefectRecord") -> Optional[float]:
        """같은 die 내 local 좌표 유클리드 거리. 둘 중 하나라도 좌표 없으면 None."""
        if not self.ok or not other.ok:
            return None
        return math.hypot(self.x - other.x, self.y - other.y)  # type: ignore[operator]


@dataclass
class LayerInfo:
    """LOT 하위 layer 폴더 하나."""

    folder_name: str  # 원본 폴더명 (예: "1. LYA4_재리뷰")
    canonical: str  # 정규화 토큰 (예: LYA4)
    path: Path
    is_re_review: bool = False  # _재리뷰 여부
    display: str = ""  # 선택 UI/매칭에 쓰는 표시 이름(충돌 시에만 canonical 과 다름)


class NoMatchReason(str, Enum):
    """비교 매칭 실패 사유(화면 진단 문구의 단일 출처)."""

    NONE = "NONE"  # 매칭 성공
    NO_DIE_PHOTO = "NO_DIE_PHOTO"  # 같은 die 의 비교 사진 자체가 없음
    COORD_FAIL = "COORD_FAIL"  # 비교 사진은 있으나 좌표 추출 실패로 제외됨
    OVER_TOLERANCE = "OVER_TOLERANCE"  # 같은 die 후보는 있으나 허용오차 초과


@dataclass
class MatchResult:
    """기준 defect 1개에 대한 특정 비교 layer 의 매칭 결과."""

    compare_layer: str
    base: DefectRecord
    matched: Optional[DefectRecord] = None
    distance: Optional[float] = None
    # ---- 진단용(매칭 실패 사유 파악) ----
    nearest: Optional[DefectRecord] = None  # 허용오차 무시한 같은 die 최근접 후보
    nearest_distance: Optional[float] = None  # 그 거리
    die_candidates: int = 0  # 같은 (wafer,die) 의 좌표 OK 비교 record 수
    failed_in_die: int = 0  # 이 비교 layer·같은 wafer 의 좌표 추출 실패 수(근사)
    ambiguous: bool = False  # 허용오차 내 거의 동률 후보가 둘 이상(어느 것이 맞는지 모호)

    @property
    def is_match(self) -> bool:
        return self.matched is not None

    @property
    def reason(self) -> NoMatchReason:
        """매칭 실패 사유 분류."""
        if self.is_match:
            return NoMatchReason.NONE
        if self.die_candidates > 0:
            return NoMatchReason.OVER_TOLERANCE
        if self.failed_in_die > 0:
            return NoMatchReason.COORD_FAIL
        return NoMatchReason.NO_DIE_PHOTO


@dataclass
class BaseDefectMatches:
    """기준 defect 1개 + 모든 비교 layer 매칭 결과 묶음."""

    base: DefectRecord
    results: list[MatchResult] = field(default_factory=list)

    def for_layer(self, layer: str) -> Optional[MatchResult]:
        for r in self.results:
            if r.compare_layer == layer:
                return r
        return None
