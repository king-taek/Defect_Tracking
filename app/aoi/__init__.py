"""AOI 엔지니어 전용 모드 — AOI 장비 scanresult 에서 바로 좌표를 뽑는 패키지.

`king-taek/coding` 저장소(``aoi_verification/app/coords``)의 좌표 추출 메커니즘을 그대로
옮긴 것이다.  기존 Conder scan 경로(:mod:`app.parsers`)와는 별개로, 제품 프로파일 상수
없이 **결과 폴더 안의 파일**(Params_WaferInfo.ini / .001 헤더)에서 die 격자를 읽는다.

우선순위:
    1. camtek_live  — LIVE 파일명에서 직접 파싱 (가장 빠름, 항상 정확)
    2. camtek_ini   — ColorImageGrabingInfo.ini 파싱
    3. kla_info     — KLA .001 정보 파일 파싱

원본 폴더는 read-only 로만 읽는다.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional

from . import camtek_ini, camtek_live, kla_info, wafer_geometry
from .models import DefectCoord

__all__ = ["resolve", "resolve_batch", "clear_caches", "DefectCoord"]

_LOG = logging.getLogger("defect_tracker.aoi.coords")


def resolve(image_path: Path) -> Optional[DefectCoord]:
    """이미지 경로 → DefectCoord. 세 소스를 순서대로 시도, 모두 실패하면 None."""
    coord = camtek_live.resolve(image_path)
    if coord is not None:
        return coord
    coord = camtek_ini.resolve(image_path)
    if coord is not None:
        return coord
    return kla_info.resolve(image_path)


def resolve_batch(paths: Iterable[Path]) -> dict[Path, Optional[DefectCoord]]:
    """여러 이미지 경로를 한꺼번에 resolve → {path: DefectCoord | None}.

    INI/KLA 파일은 폴더별로 한 번만 파싱(lru_cache)한다.

    ★ **한 실행 안에서 Camtek 좌표 프레임을 통일한다.**  die pitch 검산은 웨이퍼 폴더마다
    독립이라, 한 layer 는 통과하고 다른 layer 는 실패할 수 있다.  그러면 한쪽은 die-내부
    (``row = row_total − y_index``), 다른 쪽은 절대좌표(``row = −Row``)가 돼 ``(col,row) ±1``
    이웃 게이트가 절대 안 맞는다.  섞이면 통과한 쪽도 절대좌표로 내려 양쪽을 맞춘다.
    """
    result: dict[Path, Optional[DefectCoord]] = {}
    for p in paths:
        result[p] = resolve(p)

    sources = {c.source for c in result.values() if c is not None}

    # die-내부 좌표를 내는 소스 중 **절대좌표로 되돌릴 수 없는** 것들.
    stuck = {"camtek_live", "kla"} & sources
    if stuck and "camtek_abs" in sources:
        _LOG.warning(
            "이 실행에 die-내부 좌표(%s)와 절대 wafer 좌표가 섞여 있습니다. "
            "이 소스들은 절대 좌표를 갖고 있지 않아 통일할 수 없어 그 조합은 "
            "매칭되지 않습니다. Camtek 폴더의 die 기하를 못 찾은 것이 원인입니다.",
            ", ".join(sorted(stuck)))
    if not {"camtek_ini", "camtek_abs"} <= sources:
        return result

    _LOG.warning(
        "이 실행에 die pitch 를 확정한 Camtek 폴더와 못 한 폴더가 섞여 있습니다. "
        "좌표 프레임이 달라 매칭이 전멸하므로 **전부 절대 wafer 좌표로 통일**합니다"
        "(매칭은 정상, die 단위 표기만 불가).")
    for p, c in result.items():
        if c is None or c.source != "camtek_ini":
            continue
        raw = camtek_ini.load_raw_folder(p.parent).get(p.stem.lower())
        result[p] = camtek_ini.abs_coord(*raw) if raw is not None else None
    return result


def clear_caches() -> None:
    """폴더 단위 lru_cache 를 모두 비운다 — 재스캔(F5)이 갱신된 파일을 다시 읽게."""
    for fn in (camtek_ini.load_folder, camtek_ini.load_raw_folder,
               camtek_ini.load_recipe_folder, camtek_ini.load_abs_folder,
               kla_info.load_folder, kla_info.load_folder_raw, kla_info.read_wafer_id,
               wafer_geometry.camtek_geometry, wafer_geometry.kla_geometry):
        fn.cache_clear()
