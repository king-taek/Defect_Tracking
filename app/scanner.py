"""LOT 폴더 스캔 및 인덱스 구축 (문서 Section 4, 8.1, 8.2).

구조: LOT 폴더 / layer 폴더 / wafer 폴더 / (defect 이미지 + info/ini 파일)

각 wafer 폴더의 이미지마다 좌표 출처를 판별해 col_row_x_y 위치 정보를 만든다:
  1) Camtek 파일명에 좌표가 있으면 그대로 추출
  2) ColorImageGrabingInfo.ini section 에서 산출
  3) KLA info(.001) 의 TiffFileName/DefectList 로 변환

원본은 read-only 로만 읽으며 어떤 파일도 생성하지 않는다.
"""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app import config, layout
from app.models import DefectRecord, LayerInfo, ParseStatus, Source
from app.parsers import camtek_filename, camtek_ini, kla_info

ProgressCb = Optional[Callable[[str, int, int], None]]
CancelCb = Optional[Callable[[], bool]]  # True 면 스캔을 협조적으로 중단

_INI_HINT = "colorimagegrabinginfo"
_log = logging.getLogger("defect_tracker.scanner")

# wafer 스캔 병렬 워커 수(네트워크 I/O 바운드 → CPU 수보다 넉넉히).
_SCAN_WORKERS = max(4, min(16, (os.cpu_count() or 4) * 2))

# 디렉터리/파일 나열 중 접근 오류를 누적(스캔 1회 단위). 병렬 스캔(Phase 3) 대비 lock 사용.
_scan_errors: list[str] = []
_scan_errors_lock = threading.Lock()


def _record_scan_error(path: Path, exc: OSError) -> None:
    msg = f"{path}: {exc.__class__.__name__}: {exc}"
    with _scan_errors_lock:
        _scan_errors.append(msg)
    _log.warning("접근 실패 — %s", msg)


@dataclass
class LotIndex:
    """스캔 결과. layer/wafer/record 인덱스를 보관."""

    lot_name: str
    lot_path: Path
    layers: list[LayerInfo] = field(default_factory=list)
    records: list[DefectRecord] = field(default_factory=list)
    scan_errors: list[str] = field(default_factory=list)  # 접근 불가 경로(권한/네트워크)

    def layer_canonicals(self) -> list[str]:
        """선택 UI 에 표시할 layer 이름 목록(폴더 순서, 유니크).

        canonical 이 충돌하지 않으면 canonical 그대로, 충돌하면 재리뷰 등으로
        구분된 display 이름을 사용한다(scan_lot 에서 display 산정).
        """
        seen: list[str] = []
        for lyr in self.layers:
            name = lyr.display or lyr.canonical
            if name not in seen:
                seen.append(name)
        return seen

    def records_for_layer(self, canonical: str) -> list[DefectRecord]:
        return [r for r in self.records if r.layer == canonical]

    def records_by_layer(self) -> dict[str, list[DefectRecord]]:
        out: dict[str, list[DefectRecord]] = {}
        for r in self.records:
            out.setdefault(r.layer, []).append(r)
        return out

    def wafers(self) -> list[str]:
        seen: list[str] = []
        for r in self.records:
            if r.wafer_id not in seen:
                seen.append(r.wafer_id)
        return seen


def _list_dirs(path: Path) -> list[Path]:
    try:
        return sorted([p for p in path.iterdir() if p.is_dir()], key=lambda p: p.name)
    except OSError as exc:
        _record_scan_error(path, exc)
        return []


def _list_files(path: Path) -> list[Path]:
    try:
        return sorted([p for p in path.iterdir() if p.is_file()], key=lambda p: p.name)
    except OSError as exc:
        _record_scan_error(path, exc)
        return []


def _is_image(name: str) -> bool:
    return Path(name).suffix.lower() in config.IMAGE_EXTENSIONS


def _dir_has_image(path: Path) -> bool:
    try:
        with os.scandir(path) as it:
            for e in it:
                if e.is_file() and _is_image(e.name):
                    return True
    except OSError:
        return False
    return False


def _image_depth(root: Path, max_depth: int = 4, breadth: int = 24) -> Optional[int]:
    """root 아래에서 이미지 파일을 직접 담은 디렉터리가 처음 나타나는 깊이를 반환.

    레벨별 BFS(레벨당 폴더 수 breadth 로 제한)로 가볍게 탐색한다(네트워크 경로 대비).
    못 찾으면 None.
    """
    level = [root]
    for depth in range(0, max_depth + 1):
        for d in level[:breadth]:
            if _dir_has_image(d):
                return depth
        nxt: list[Path] = []
        for d in level[:breadth]:
            try:
                with os.scandir(d) as it:
                    nxt.extend(Path(e.path) for e in it if e.is_dir())
            except OSError:
                continue
        if not nxt:
            break
        level = nxt
    return None


def classify_selection(path: str | Path) -> tuple[str, Optional[Path]]:
    """선택한 폴더가 자재 구조(자재/layer/wafer/이미지)에서 어느 레벨인지 판별.

    Returns:
        (kind, material_path) — kind 는
          'material'(정상) / 'layer' / 'wafer'(둘 다 자동으로 상위 자재로 보정 가능) /
          'too_high'(device 등 상위, 재선택 필요) / 'unknown'(이미지 못 찾음).
        material_path 는 layer/wafer/material 일 때 추정 자재 폴더, 그 외 None.
    """
    p = Path(path)
    depth = _image_depth(p)
    if depth is None:
        return ("unknown", None)
    if depth == 2:
        return ("material", p)
    if depth == 1:
        return ("layer", p.parent)
    if depth == 0:
        return ("wafer", p.parent.parent)
    return ("too_high", None)  # depth >= 3


def _merge_ini_sections(ini_paths: list[Path]) -> dict[str, dict[str, str]]:
    """폴더 내 모든 ColorImageGrabingInfo.ini section 을 하나로 합친다."""
    merged: dict[str, dict[str, str]] = {}
    for p in ini_paths:
        try:
            merged.update(camtek_ini.load_ini(p))
        except OSError:
            continue
    return merged


def _build_record_for_image(
    image_path: Path,
    wafer_id: str,
    layer: str,
    layer_folder: str,
    ini_sections: dict[str, dict[str, str]],
    kla_parsed,  # Optional[_ParsedInfo]
    wafer_diag: dict,  # 폴더 레벨 진단 컨텍스트
) -> DefectRecord:
    name = image_path.name
    stem = image_path.stem
    # 각 파서 시도의 실패 사유를 모아(시도 트레일) 진단 리포트에 쓴다.
    trail: list[str] = []

    # 1) Camtek 파일명 직접 파싱
    fn = camtek_filename.parse_camtek_filename(name)
    if fn.status == ParseStatus.OK:
        return DefectRecord(
            image_path=image_path,
            wafer_id=wafer_id,
            layer=layer,
            layer_folder=layer_folder,
            source=Source.CAMTEK_FILENAME,
            status=ParseStatus.OK,
            col=fn.col,
            row=fn.row,
            x=fn.x,
            y=fn.y,
            defect_name=fn.defect_name,
            dx_size=fn.dx_size,
            dy_size=fn.dy_size,
            d_area=fn.d_area,
        )
    trail.append(f"파일명: {fn.reason}")

    # 2) ColorImageGrabingInfo.ini
    if ini_sections:
        ini_res = camtek_ini.convert_from_sections(ini_sections, stem)
        if ini_res.status == ParseStatus.OK:
            return DefectRecord(
                image_path=image_path,
                wafer_id=wafer_id,
                layer=layer,
                layer_folder=layer_folder,
                source=Source.CAMTEK_INI,
                status=ParseStatus.OK,
                col=ini_res.col,
                row=ini_res.row,
                x=ini_res.x,
                y=ini_res.y,
            )
        trail.append(f"INI: {ini_res.reason}")
    else:
        trail.append("INI: ColorImageGrabingInfo.ini 없음")

    # 3) KLA info
    if kla_parsed is not None:
        kla_res = kla_info.convert_from_parsed(kla_parsed, name)
        if kla_res.status == ParseStatus.OK:
            return DefectRecord(
                image_path=image_path,
                wafer_id=wafer_id,
                layer=layer,
                layer_folder=layer_folder,
                source=Source.KLA,
                status=ParseStatus.OK,
                col=kla_res.col,
                row=kla_res.row,
                x=kla_res.x,
                y=kla_res.y,
            )
        trail.append(f"KLA: {kla_res.reason}")
        return DefectRecord(
            image_path=image_path,
            wafer_id=wafer_id,
            layer=layer,
            layer_folder=layer_folder,
            source=Source.KLA,
            status=kla_res.status,
            col=kla_res.col,
            row=kla_res.row,
            x=kla_res.x,
            y=kla_res.y,
            note=" | ".join(trail),
            diag=wafer_diag,
        )
    trail.append("KLA: info 파일 없음")

    # 어느 방법으로도 좌표를 찾지 못함
    return DefectRecord(
        image_path=image_path,
        wafer_id=wafer_id,
        layer=layer,
        layer_folder=layer_folder,
        source=Source.UNKNOWN,
        status=ParseStatus.NOT_FOUND,
        note=" | ".join(trail),
        diag=wafer_diag,
    )


def _read_info_text_safe(path: Path) -> str:
    """진단용: info 파일 텍스트 전문을 읽는다."""
    try:
        from app.safety import read_only_bytes
        raw = read_only_bytes(path)
        for enc in ("utf-8", "cp949", "utf-16-le", "utf-16-be", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except (UnicodeDecodeError, ValueError):
                continue
        else:
            text = raw.decode("latin-1", errors="replace")
        return text
    except OSError:
        return "(읽기 실패)"


def _scan_wafer_folder(
    wafer_dir: Path, layer: str, layer_folder: str
) -> list[DefectRecord]:
    files = _list_files(wafer_dir)
    filenames = [f.name for f in files]

    image_files = [f for f in files if _is_image(f.name)]
    ini_files = [
        f for f in files if _INI_HINT in f.name.lower() and f.suffix.lower() == ".ini"
    ]
    ini_sections = _merge_ini_sections(ini_files)

    # KLA info 파일 선택. Camtek INI 파일(.ini)은 KLA info 후보에서 제외하여
    # 혼재 폴더에서 오인하지 않도록 한다. 이 파싱은 .001/info 가 있는 KLA 폴더에서만 발생.
    kla_parsed = None
    kla_candidates = [n for n in filenames if Path(n).suffix.lower() != ".ini"]
    info_name = kla_info.select_info_file(kla_candidates)
    info_text = ""
    if info_name:
        info_path = wafer_dir / info_name
        info_text = _read_info_text_safe(info_path)
        try:
            kla_parsed = kla_info.load_info(info_path)
        except OSError:
            kla_parsed = None

    # 진단용 폴더 컨텍스트(실패 record 에만 첨부)
    wafer_diag: dict = {
        "wafer_dir": str(wafer_dir),
        "files_in_folder": filenames,
        "image_count": len(image_files),
        "ini_files": [f.name for f in ini_files],
        "has_ini_sections": bool(ini_sections),
        "ini_section_keys": sorted(ini_sections.keys())[:20] if ini_sections else [],
        "kla_info_file": info_name,
        "kla_info_text": info_text,
        "kla_tiff_count": len(kla_parsed.defects) if kla_parsed else 0,
        "kla_all_defect_count": len(kla_parsed.all_defects) if kla_parsed else 0,
        "kla_die_pitch_y": kla_parsed.die_pitch_y if kla_parsed else None,
    }

    wafer_id = wafer_dir.name
    return [
        _build_record_for_image(
            img, wafer_id, layer, layer_folder, ini_sections, kla_parsed,
            wafer_diag,
        )
        for img in image_files
    ]


def _assign_displays(infos: list[LayerInfo]) -> None:
    """canonical 이 충돌하는 경우에만 재리뷰 등으로 구분한 display 이름을 부여한다.

    충돌이 없으면 display = canonical (기존 동작 유지). 충돌 시 재리뷰 깊이에 따라
    "{canonical}_재리뷰"(레벨1) / "{canonical}_재재리뷰"(레벨2) … 로 구분하고, 일반은
    canonical, 그래도 겹치면 " (2)", " (3)" … 로 유일화.
    """
    counts: dict[str, int] = {}
    for inf in infos:
        counts[inf.canonical] = counts.get(inf.canonical, 0) + 1

    used: set[str] = set()
    for inf in infos:
        if counts.get(inf.canonical, 0) <= 1:
            name = inf.canonical
        elif inf.re_review_level >= 1:
            suffix = "재" * inf.re_review_level + "리뷰"
            name = f"{inf.canonical}_{suffix}"
        else:
            name = inf.canonical
        base = name
        k = 2
        while name in used:
            name = f"{base} ({k})"
            k += 1
        used.add(name)
        inf.display = name


def scan_lot(
    lot_path: str | Path,
    progress: ProgressCb = None,
    cancel_check: CancelCb = None,
) -> LotIndex:
    """LOT 폴더를 스캔해 LotIndex 를 만든다. 원본은 읽기 전용으로만 접근.

    cancel_check 가 True 를 반환하면 wafer 처리 루프를 협조적으로 중단한다(부분 결과 반환).
    """
    lot = Path(lot_path)
    index = LotIndex(lot_name=lot.name, lot_path=lot)

    with _scan_errors_lock:
        _scan_errors.clear()
    _log.info("스캔 시작: %s", lot)

    layer_dirs = _list_dirs(lot)
    total = len(layer_dirs) or 1

    # 1차: layer 폴더별 정규화 정보 수집 후 표시 이름(display) 산정(충돌 시에만 구분).
    for layer_dir in layer_dirs:
        canonical, is_rr = layout.normalize_layer(layer_dir.name)
        level = layout.re_review_level(layer_dir.name)
        index.layers.append(
            LayerInfo(
                folder_name=layer_dir.name,
                canonical=canonical,
                path=layer_dir,
                is_re_review=is_rr,
                re_review_level=level,
            )
        )
    _assign_displays(index.layers)

    # 2차: (layer, wafer) 작업 목록을 만들고 wafer 단위로 병렬 스캔한다.
    # 네트워크 경로에서 디렉터리/info 파일 I/O latency 가 지배적이므로 병렬화가 효과적.
    # 결과는 입력 순서(layer 순 → wafer 정렬)대로 모아 직렬 스캔과 동일한 결정적 순서 유지.
    tasks: list[tuple[LayerInfo, Path]] = []
    for info in index.layers:
        for wafer_dir in _list_dirs(info.path):
            tasks.append((info, wafer_dir))
    wafer_total = len(tasks) or 1

    def _scan_task(task: tuple[LayerInfo, Path]) -> list[DefectRecord]:
        if cancel_check and cancel_check():  # 이미 제출된 작업도 빠르게 빠져나간다
            return []
        info, wafer_dir = task
        try:
            return _scan_wafer_folder(wafer_dir, info.display, info.folder_name)
        except Exception as exc:  # noqa: BLE001 - 한 wafer 실패가 전체 스캔을 막지 않게
            _record_scan_error(wafer_dir, exc if isinstance(exc, OSError) else OSError(str(exc)))
            return []

    if tasks:
        workers = min(_SCAN_WORKERS, len(tasks))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for done, recs in enumerate(ex.map(_scan_task, tasks), start=1):
                if cancel_check and cancel_check():
                    _log.info("스캔 중단 요청 — %d/%d wafer 에서 멈춤", done, wafer_total)
                    break
                index.records.extend(recs)
                if progress:
                    info, wafer_dir = tasks[done - 1]
                    progress(
                        f"스캔: {info.folder_name}/{wafer_dir.name}", done, wafer_total
                    )

    with _scan_errors_lock:
        index.scan_errors = list(_scan_errors)
    _log.info(
        "스캔 완료: layer %d · record %d · 접근오류 %d",
        len(index.layers), len(index.records), len(index.scan_errors),
    )
    if progress:
        progress("스캔 완료", total, total)
    return index
