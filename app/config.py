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
# 좌표 변환 상수 (문서 Section 13 기준, TB500 Live)
# ---------------------------------------------------------------------------

# Camtek stage 좌표 보정에 쓰는 die pitch (Section 13.3.5)
CAMTEK_PITCH_X = 37247.7
CAMTEK_PITCH_Y = 44905.4

# Camtek die 위치 변환 규칙 (Section 13.3.6): col = Col - COL_OFFSET, row = ROW_BASE - Row
CAMTEK_COL_OFFSET = 2
CAMTEK_ROW_BASE = 7

# KLA package size (Section 13.2.6). zeroX/zeroY는 정수 나눗셈으로 산출.
KLA_PACKAGE_X_COUNT = 7
KLA_PACKAGE_Y_COUNT = 6


def kla_zero_x() -> int:
    return KLA_PACKAGE_X_COUNT // 2


def kla_zero_y() -> int:
    return KLA_PACKAGE_Y_COUNT // 2


# ---------------------------------------------------------------------------
# 애플리케이션 / 자동 업데이트
# ---------------------------------------------------------------------------

APP_NAME = "Conder Scan Compare Viewer"

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
