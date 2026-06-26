"""LOT 폴더 스캔 및 인덱스 구축 (문서 Section 4, 8.1, 8.2).

구조: LOT 폴더 / layer 폴더 / wafer 폴더 / (defect 이미지 + info/ini 파일)

각 wafer 폴더의 이미지마다 좌표 출처를 판별해 col_row_x_y 위치 정보를 만든다:
  1) Camtek 파일명에 좌표가 있으면 그대로 추출
  2) ColorImageGrabingInfo.ini section 에서 산출
  3) KLA info(.001) 의 TiffFileName/DefectList 로 변환

원본은 read-only 로만 읽으며 어떤 파일도 생성하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app import config, layout
from app.models import DefectRecord, LayerInfo, ParseStatus, Source
from app.parsers import camtek_filename, camtek_ini, kla_info

ProgressCb = Optional[Callable[[str, int, int], None]]

_INI_HINT = "colorimagegrabinginfo"


@dataclass
class LotIndex:
    """스캔 결과. layer/wafer/record 인덱스를 보관."""

    lot_name: str
    lot_path: Path
    layers: list[LayerInfo] = field(default_factory=list)
    records: list[DefectRecord] = field(default_factory=list)

    def layer_canonicals(self) -> list[str]:
        seen: list[str] = []
        for lyr in self.layers:
            if lyr.canonical not in seen:
                seen.append(lyr.canonical)
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
    except OSError:
        return []


def _list_files(path: Path) -> list[Path]:
    try:
        return sorted([p for p in path.iterdir() if p.is_file()], key=lambda p: p.name)
    except OSError:
        return []


def _is_image(name: str) -> bool:
    return Path(name).suffix.lower() in config.IMAGE_EXTENSIONS


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
) -> DefectRecord:
    name = image_path.name
    stem = image_path.stem

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
        )

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

    # 3) KLA info
    if kla_parsed is not None:
        kla_res = kla_info.convert_from_parsed(kla_parsed, name)
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
        )

    # 어느 방법으로도 좌표를 찾지 못함
    return DefectRecord(
        image_path=image_path,
        wafer_id=wafer_id,
        layer=layer,
        layer_folder=layer_folder,
        source=Source.UNKNOWN,
        status=ParseStatus.NOT_FOUND,
        note="좌표 정보를 찾을 수 없습니다.",
    )


def _scan_wafer_folder(
    wafer_dir: Path, layer: str, layer_folder: str
) -> list[DefectRecord]:
    files = _list_files(wafer_dir)
    filenames = [f.name for f in files]

    image_files = [f for f in files if _is_image(f.name)]
    ini_files = [f for f in files if _INI_HINT in f.name.lower() and f.suffix.lower() == ".ini"]
    ini_sections = _merge_ini_sections(ini_files)

    # KLA info 파일 (이미지가 Camtek 으로 해석 안 될 때만 의미가 있지만 미리 파싱)
    kla_parsed = None
    info_name = kla_info.select_info_file(filenames)
    if info_name:
        try:
            kla_parsed = kla_info.load_info(wafer_dir / info_name)
        except OSError:
            kla_parsed = None

    wafer_id = wafer_dir.name
    return [
        _build_record_for_image(
            img, wafer_id, layer, layer_folder, ini_sections, kla_parsed
        )
        for img in image_files
    ]


def scan_lot(lot_path: str | Path, progress: ProgressCb = None) -> LotIndex:
    """LOT 폴더를 스캔해 LotIndex 를 만든다. 원본은 읽기 전용으로만 접근."""
    lot = Path(lot_path)
    index = LotIndex(lot_name=lot.name, lot_path=lot)

    layer_dirs = _list_dirs(lot)
    total = len(layer_dirs) or 1
    for li, layer_dir in enumerate(layer_dirs):
        canonical, is_rr = layout.normalize_layer(layer_dir.name)
        index.layers.append(
            LayerInfo(
                folder_name=layer_dir.name,
                canonical=canonical,
                path=layer_dir,
                is_re_review=is_rr,
            )
        )
        if progress:
            progress(f"layer 스캔: {layer_dir.name}", li, total)

        for wafer_dir in _list_dirs(layer_dir):
            index.records.extend(
                _scan_wafer_folder(wafer_dir, canonical, layer_dir.name)
            )

    if progress:
        progress("스캔 완료", total, total)
    return index
