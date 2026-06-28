"""전역 상수 및 사용자 설정 관리.

좌표 변환 상수(pitch, package count)와 매칭 기본값을 한 곳에 모아 두어
TB500 외 제품으로 확장할 때 이 파일만 수정하면 되도록 한다.

사용자 설정(마지막 LOT 경로, tolerance, 출력 폴더 등)은 output workspace 내부의
JSON 파일에 저장한다. 원본 폴더에는 어떤 것도 쓰지 않는다.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# 제품 프로파일 (좌표 변환 상수 묶음) — 제품별 확장은 PRODUCTS 에 추가만 하면 된다.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductConfig:
    """제품별 좌표 변환/패키지 상수 묶음 (문서 Section 13)."""

    key: str
    name: str
    camtek_pitch_x: float
    camtek_pitch_y: float
    kla_package_x_count: int
    kla_package_y_count: int
    camtek_col_offset: int = 2
    camtek_row_base: int = 7
    die_map: frozenset = field(default_factory=frozenset)  # 존재하는 (col,row) (비면 사각 전체)
    source: str = "builtin"  # builtin / db

    def kla_zero_x(self) -> int:
        return self.kla_package_x_count // 2

    def kla_zero_y(self) -> int:
        return self.kla_package_y_count // 2


def register_devices(profiles: dict) -> None:
    """외부 디바이스 DB(DeviceProfile 사전)를 PRODUCTS 에 병합한다.

    DB 가 제공하지 않는 Camtek INI 변환 상수(col_offset/row_base)는 기본값을 쓴다.
    """
    for key, prof in profiles.items():
        PRODUCTS[key] = ProductConfig(
            key=key,
            name=getattr(prof, "name", key),
            camtek_pitch_x=getattr(prof, "pitch_x", 0.0) or _DEFAULT_CFG.camtek_pitch_x,
            camtek_pitch_y=getattr(prof, "pitch_y", 0.0) or _DEFAULT_CFG.camtek_pitch_y,
            kla_package_x_count=prof.x_count,
            kla_package_y_count=prof.y_count,
            die_map=prof.die_map,
            source="db",
        )


PRODUCTS: dict[str, ProductConfig] = {
    "TB500INT": ProductConfig(
        key="TB500INT",
        name="TB500 Live",
        camtek_pitch_x=37247.7,
        camtek_pitch_y=44905.4,
        camtek_col_offset=2,
        camtek_row_base=7,
        kla_package_x_count=7,
        kla_package_y_count=6,
    ),
}
DEFAULT_PRODUCT = "TB500INT"
_active_product = DEFAULT_PRODUCT


def active_product() -> ProductConfig:
    return PRODUCTS.get(_active_product, PRODUCTS[DEFAULT_PRODUCT])


def set_active_product(key: str) -> None:
    """활성 제품 프로파일을 바꾼다(다음 스캔부터 좌표 변환에 적용)."""
    global _active_product
    if key in PRODUCTS:
        _active_product = key


# ---- 하위호환 상수 (기본 제품 값) — 샘플데이터/기존 테스트가 참조 ----
_DEFAULT_CFG = PRODUCTS[DEFAULT_PRODUCT]
CAMTEK_PITCH_X = _DEFAULT_CFG.camtek_pitch_x
CAMTEK_PITCH_Y = _DEFAULT_CFG.camtek_pitch_y
CAMTEK_COL_OFFSET = _DEFAULT_CFG.camtek_col_offset
CAMTEK_ROW_BASE = _DEFAULT_CFG.camtek_row_base
KLA_PACKAGE_X_COUNT = _DEFAULT_CFG.kla_package_x_count
KLA_PACKAGE_Y_COUNT = _DEFAULT_CFG.kla_package_y_count


def kla_zero_x() -> int:
    return active_product().kla_zero_x()


def kla_zero_y() -> int:
    return active_product().kla_zero_y()


# ---------------------------------------------------------------------------
# 애플리케이션 / 자동 업데이트
# ---------------------------------------------------------------------------

APP_NAME = "Defect Layer Tracker"

# 자동 업데이트 대상 저장소(메인 브랜치를 가져와 적용)
UPDATE_OWNER = "king-taek"
UPDATE_REPO = "defect_tracking"
UPDATE_BRANCH = "main"


# ---------------------------------------------------------------------------
# 매칭 / UI 기본값
# ---------------------------------------------------------------------------

# 기본 허용 오차 (Section 8.3) - 좌표 단위는 파일/INI 값 그대로 사용
DEFAULT_TOLERANCE = 100.0

# 상단 썸네일은 사진 중앙 일부 구간만 확대 (Section 8.6) - 중앙 비율
THUMBNAIL_CENTER_RATIO = 0.10
THUMBNAIL_SIZE = 140

# Layer 비교 그리드 기본 배치 (Section 8.4). 2열 그리드, 위에서 아래로.
DEFAULT_LAYER_GRID = [
    ["RDL4", "PI4"],
    ["RDL3", "PI3"],
    ["RDL2", "PI2"],
    ["RDL1", "FS"],
]

# 지원 이미지 확장자
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


# ---------------------------------------------------------------------------
# Output workspace (2차 보호: 결과/캐시는 원본 밖에만 생성 - Section 1.1)
# ---------------------------------------------------------------------------

def default_workspace() -> Path:
    """원본 폴더 밖의 기본 출력 작업공간 경로."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    if not base:
        base = str(Path.home())
    return Path(base) / "ConderCompare"


@dataclass
class AppSettings:
    """사용자 설정. output workspace 내 settings.json에 저장된다."""

    workspace: str = field(default_factory=lambda: str(default_workspace()))
    last_lot_folder: str = ""
    output_folder: str = ""  # 비어 있으면 workspace/exports 사용
    tolerance: float = DEFAULT_TOLERANCE
    base_layer: str = ""
    compare_layers: list[str] = field(default_factory=list)
    recent_folders: list[str] = field(default_factory=list)  # 최근 연 자재 폴더(최대 5)
    product: str = DEFAULT_PRODUCT  # 활성 제품 프로파일(좌표 변환 상수)
    device_db_path: str = ""  # 외부 AOIDeviceDB.xlsx 경로(있으면 제품 목록 확장)
    window_geometry: str = ""  # "x,y,w,h" — 모니터 환경별 창 크기/위치 기억
    sidebar_width: int = 240  # 좌측 사이드바 폭(스플리터) 기억
    auto_update_check: bool = True  # 시작 시 백그라운드 업데이트 확인
    update_token: str = ""  # (선택) 비공개 저장소용 GitHub 토큰. public 이면 빈값.

    # ---- 경로 헬퍼 -------------------------------------------------------
    @property
    def workspace_path(self) -> Path:
        return Path(self.workspace)

    @property
    def cache_path(self) -> Path:
        return self.workspace_path / "cache"

    @property
    def exports_path(self) -> Path:
        if self.output_folder:
            return Path(self.output_folder)
        return self.workspace_path / "exports"

    def settings_file(self) -> Path:
        return self.workspace_path / "settings.json"

    # ---- 저장/로드 -------------------------------------------------------
    def ensure_workspace(self) -> None:
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        self.cache_path.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        """설정을 원자적으로 저장한다(임시파일 작성 후 교체 → 크래시 시 손상 방지)."""
        self.ensure_workspace()
        data = asdict(self)
        target = self.settings_file()
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, target)  # 같은 디렉터리 내 원자적 교체

    @classmethod
    def load(cls, workspace: Path | None = None) -> "AppSettings":
        ws = workspace or default_workspace()
        settings_file = ws / "settings.json"
        if settings_file.exists():
            try:
                raw: dict[str, Any] = json.loads(settings_file.read_text(encoding="utf-8"))
                known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
                return cls(**{k: v for k, v in raw.items() if k in known})
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                logging.getLogger("conder.config").warning(
                    "settings.json 을 읽지 못해 기본값을 사용합니다: %s", exc
                )
        return cls(workspace=str(ws))
