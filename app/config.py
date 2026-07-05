"""전역 상수 및 사용자 설정 관리.

좌표 변환 상수(pitch, package count)와 매칭 기본값을 한 곳에 모아 두어
DEVA 외 제품으로 확장할 때 이 파일만 수정하면 되도록 한다.

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
    "DEVAINT": ProductConfig(
        key="DEVAINT",
        name="DEVA Live",
        # AOIDeviceDB.xlsx "DEVA Live" 시트 실측값(정답 도구 원본 기준).
        # "DEVA"(다른 시트, Y=5/23-die)과 혼동하지 말 것 — 실제 운영 KLARF
        # SampleTestPlan(YINDEX -3~+2, 30쌍)과 일치하는 건 "DEVA Live"(Y=6/30-die).
        camtek_pitch_x=37170.0,
        camtek_pitch_y=44830.0,
        camtek_col_offset=2,
        camtek_row_base=7,
        kla_package_x_count=7,
        kla_package_y_count=6,
    ),
}
DEFAULT_PRODUCT = "DEVAINT"
_active_product = DEFAULT_PRODUCT


def active_product() -> ProductConfig:
    return PRODUCTS.get(_active_product, PRODUCTS[DEFAULT_PRODUCT])


def set_active_product(key: str) -> None:
    """활성 제품 프로파일을 바꾼다(다음 스캔부터 좌표 변환에 적용)."""
    global _active_product
    if key in PRODUCTS:
        _active_product = key


def ensure_die_map_product() -> None:
    """활성 제품에 die_map 이 없으면(빌트인 폴백) 같은 패키지 크기의 DB 제품으로 승격한다.

    DB 자동 로드 직후 호출한다. 빌트인 제품(die_map 비어 사각 표시)만 있을 때에도, DB 에
    같은 패키지(X×Y) 크기의 die_map 이 있으면 그 DB 제품을 활성화해 웨이퍼맵이 기본적으로
    실제 die 모양으로 뜨게 한다. 사용자가 이미 die_map 있는 제품을 고른 경우엔 건드리지 않는다.
    """
    cur = active_product()
    if cur.die_map:
        return
    for key, prod in PRODUCTS.items():
        if (
            prod.source == "db"
            and prod.die_map
            and prod.kla_package_x_count == cur.kla_package_x_count
            and prod.kla_package_y_count == cur.kla_package_y_count
        ):
            set_active_product(key)
            return


def match_product_for_path(lot_path) -> tuple[str | None, int]:
    """자재(LOT) 경로 구성요소에서 등록 제품을 자동 인식한다.

    자재명·상위(device 등) 폴더명을 영숫자 소문자 토큰으로 정규화하고, 등록 제품의
    key/name 토큰이 그 안에 부분 문자열로 나타나면 매칭으로 본다. 가장 긴(구체적인)
    제품 토큰을 우선한다. 반환은 (제품 key 또는 None, 점수=매칭 토큰 길이).
    """
    from pathlib import Path

    from app.layout import _canon_token

    p = Path(lot_path)
    parts = [p.name] + [par.name for par in list(p.parents)[:3]]
    path_tokens = [_canon_token(s) for s in parts if s]
    path_tokens = [t for t in path_tokens if t]

    best_key: str | None = None
    best_score = 0
    for key, prod in PRODUCTS.items():
        for cand in (key, prod.name):
            ct = _canon_token(cand)
            if len(ct) < 4:  # 너무 짧은 토큰은 오매칭 위험 → 제외
                continue
            if any(ct in t for t in path_tokens):
                if len(ct) > best_score:
                    best_key, best_score = key, len(ct)
    return best_key, best_score


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

APP_NAME = "Defect Tracker"

# 제작 크레딧(UI 곳곳 표기용 단일 출처)
CREDITS = "Designed by JinHan Kim, Developed by HyunTaek Lim"


def dev_mode(settings=None) -> bool:
    """개발자 모드 여부. 환경변수 DEFECT_TRACKER_DEV 또는 설정(AppSettings.dev_mode)로 켠다.

    - 환경변수가 참(1/true/on/yes/y)이면 **설정보다 우선**해 항상 켜진다(배포/디버그용).
    - 환경변수가 없으면 전달된 ``settings.dev_mode`` 값을 따른다(설정 창 토글로 저장).
    켜지면 파일 로그 생성·진단 리포트·설정의 로그 경로 노출이 활성화된다.
    """
    val = os.environ.get("DEFECT_TRACKER_DEV", "").strip().lower()
    if val in ("1", "true", "on", "yes", "y"):
        return True
    if settings is not None:
        return bool(getattr(settings, "dev_mode", False))
    return False

# 자동 업데이트 대상 저장소(메인 브랜치를 가져와 적용)
UPDATE_OWNER = "king-taek"
UPDATE_REPO = "defect_tracking"
UPDATE_BRANCH = "main"


# ---------------------------------------------------------------------------
# 매칭 / UI 기본값
# ---------------------------------------------------------------------------

# 기본 허용 오차 (Section 8.3) - 좌표 단위는 파일/INI 값 그대로 사용
DEFAULT_TOLERANCE = 100.0

# defect 근접 클러스터링 거리(같은 die 안에서 이 값 미만이면 하나로 묶음). 설정에서 조절.
DEFAULT_CLUSTER_RADIUS = 50.0

# 상단 썸네일은 사진 중앙 일부 구간만 확대 (Section 8.6) - 중앙 비율
# 0.20 = 중앙 20% 를 잘라 ≈5× 확대(고정).
THUMBNAIL_CENTER_RATIO = 0.20
THUMBNAIL_SIZE = 140

# Layer 비교 그리드 기본 배치 (Section 8.4). 2열 그리드, 위에서 아래로.
DEFAULT_LAYER_GRID = [
    ["LYA4", "LYB4"],
    ["LYA3", "LYB3"],
    ["LYA2", "LYB2"],
    ["LYA1", "FS"],
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
    return Path(base) / "DefectTracker"


def bundled_device_db_path() -> Path | None:
    """앱과 함께 배포되는 기본 디바이스 DB(data/AOIDeviceDB.xlsx) 경로.

    사용자가 별도 DB 경로를 지정하지 않았을 때 자동 로드용으로 쓴다(원본은 read-only).
    - 소스 실행: 리포지토리 루트의 data/AOIDeviceDB.xlsx
    - PyInstaller onefile: sys._MEIPASS/data/AOIDeviceDB.xlsx
    찾지 못하면 None.
    """
    import sys

    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "data" / "AOIDeviceDB.xlsx")
    # config.py -> app/ -> repo root
    repo_root = Path(__file__).resolve().parent.parent
    candidates.append(repo_root / "data" / "AOIDeviceDB.xlsx")
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def default_log_dir() -> str:
    """로그 전용 기본 경로(비어 있으면 workspace/logs 를 씀).

    Windows 배포 환경에서만 지정된 고정 경로를 쓰고, 그 외(테스트/CI 등)에서는
    빈 문자열로 두어 기존 workspace/logs 폴백을 그대로 따른다.
    """
    if os.name == "nt":
        return r"C:\Users\304236\Desktop\Defect_Tracking-main\log"
    return ""


@dataclass
class AppSettings:
    """사용자 설정. output workspace 내 settings.json에 저장된다."""

    workspace: str = field(default_factory=lambda: str(default_workspace()))
    last_lot_folder: str = ""
    output_folder: str = ""  # 비어 있으면 workspace/exports 사용
    tolerance: float = DEFAULT_TOLERANCE
    cluster_radius: float = DEFAULT_CLUSTER_RADIUS  # defect 근접 클러스터링 거리(설정에서 조절)
    base_layer: str = ""
    compare_layers: list[str] = field(default_factory=list)
    recent_folders: list[str] = field(default_factory=list)  # 최근 연 자재 폴더(최대 5)
    favorite_folders: list[str] = field(default_factory=list)  # 즐겨찾기(고정) 상위 폴더
    scan_root_name: str = "Conder Scan"  # 폴더 트리 최상위 고정: 이 이름의 폴더가 있는 드라이브
    scan_root_path: str = ""  # 명시 지정한 스캔 데이터 폴더(있으면 최상위 📌 고정, 비면 이름 탐지)
    product: str = DEFAULT_PRODUCT  # 활성 제품 프로파일(좌표 변환 상수)
    device_db_path: str = ""  # 외부 AOIDeviceDB.xlsx 경로(비면 번들 DB 자동 로드)
    thumbnail_center_ratio: float = THUMBNAIL_CENTER_RATIO  # 상단 썸네일 중앙 crop 비율(확대율)
    heatmap_layout: int = 0  # 히트맵 팝업 레이아웃 프리셋 인덱스(마지막 선택 기억)
    log_dir: str = field(default_factory=default_log_dir)  # 비어 있으면 workspace/logs 사용
    window_geometry: str = ""  # "x,y,w,h" — 모니터 환경별 창 크기/위치 기억(최대화 해제 시 복원)
    window_maximized: bool = True  # 시작 시 최대화(기본). 사용자가 해제하면 False 로 저장
    sidebar_width: int = 240  # 좌측 사이드바 폭(스플리터) 기억
    auto_update_check: bool = True  # 시작 시 백그라운드 업데이트 확인
    update_token: str = ""  # (선택) 비공개 저장소용 GitHub 토큰. public 이면 빈값.
    dev_mode: bool = False  # 개발자 모드(파일 로그·진단·로그 경로 UI). 설정 창에서 토글.

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

    @property
    def log_dir_path(self) -> Path:
        if self.log_dir:
            return Path(self.log_dir)
        return self.workspace_path / "logs"

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
                logging.getLogger("defect_tracker.config").warning(
                    "settings.json 을 읽지 못해 기본값을 사용합니다: %s", exc
                )
        return cls(workspace=str(ws))
