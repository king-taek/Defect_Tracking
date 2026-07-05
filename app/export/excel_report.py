"""Excel 결과 출력 (문서 Section 8.7).

선택된 기준 사진들에 대해 기준 layer 사진과 비교 layer 매칭 결과를 깔끔한 Excel 로 출력한다.
포함 정보: LOT명, wafer ID, 기준/비교 layer, col_row_x_y 위치, 허용 오차, 매칭 여부,
이미지 썸네일, 원본 경로(추적용, 무수정).

저장 경로는 반드시 assert_output_safe 게이트를 통과해야 하며, 원본 폴더 내부면 차단된다.
원본 이미지는 read-only 로만 읽는다(썸네일 캐시를 통해).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.models import BaseDefectMatches
from app.safety import assert_output_safe
from app.thumbnails import ThumbnailCache

# 다크/네온 느낌과 어울리는 보고서 색 (Excel 은 밝은 배경이 가독성 좋아 절제해 사용)
_NAVY = "FF1B2A4A"
_NEON = "FF1E90FF"
_LIGHT = "FFF2F6FF"
_MATCH = "FF1F7A1F"
_NOMATCH = "FFB00020"
_GREY = "FF6B7280"

_THIN = Side(style="thin", color="FFB8C4DE")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_IMG_COL_WIDTH = 30  # Excel 폭 단위
_IMG_PX = 190  # 썸네일 픽셀
_IMG_ROW_HEIGHT = 150  # 포인트


def _set_cell(ws, row, col, value, *, bold=False, color=None, fill=None,
              size=10, align="left", wrap=False):
    cell = ws.cell(row=row, column=col, value=value)
    cell.font = Font(bold=bold, color=color or "FF1B2A4A", size=size)
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    cell.alignment = Alignment(
        horizontal=align, vertical="center", wrap_text=wrap
    )
    cell.border = _BORDER
    return cell


def export_excel(
    output_path: str | Path,
    *,
    lot_name: str,
    base_layer: str,
    compare_layers: list[str],
    tolerance: float,
    selected: list[BaseDefectMatches],
    thumb_cache: ThumbnailCache,
    source_roots: Iterable[str | Path],
    notes: dict[str, str] | None = None,
) -> Path:
    """선택된 기준 defect 들의 비교 결과를 Excel 로 저장한다.

    Returns:
        저장된 파일의 절대 경로.

    Raises:
        OriginalProtectionError: 출력 경로가 원본 폴더 내부일 때.
    """
    out = assert_output_safe(output_path, source_roots)
    out.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "비교 결과"
    ws.sheet_view.showGridLines = False

    # 열: A=라벨, B=기준, C..=비교 layer
    columns = ["기준: " + base_layer] + compare_layers
    n_cols = len(columns) + 1  # +1 라벨열

    ws.column_dimensions["A"].width = 16
    for ci in range(len(columns)):
        ws.column_dimensions[get_column_letter(2 + ci)].width = _IMG_COL_WIDTH

    # ---- 보고서 헤더 ----
    r = 1
    title = ws.cell(row=r, column=1, value="Defect Layer Tracker 비교 결과 보고서")
    title.font = Font(bold=True, color="FFFFFFFF", size=14)
    title.fill = PatternFill("solid", fgColor=_NAVY)
    title.alignment = Alignment(horizontal="left", vertical="center")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=n_cols)
    ws.row_dimensions[r].height = 26
    r += 1

    meta = (
        f"LOT: {lot_name}    기준 Layer: {base_layer}    "
        f"비교 Layer: {', '.join(compare_layers) or '-'}    "
        f"허용 오차: {tolerance:g}    생성: {datetime.now():%Y-%m-%d %H:%M}"
    )
    mc = ws.cell(row=r, column=1, value=meta)
    mc.font = Font(color="FFFFFFFF", size=10)
    mc.fill = PatternFill("solid", fgColor=_NEON)
    mc.alignment = Alignment(horizontal="left", vertical="center")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=n_cols)
    ws.row_dimensions[r].height = 20
    r += 2

    # 상단 컬럼 헤더 행은 두지 않는다 — 블록마다 'Layer' 행으로 이미 표기하므로 중복이다(항목 1).

    # ---- 각 기준 defect 블록 ----
    for idx, item in enumerate(selected, start=1):
        base = item.base

        # 블록 제목
        _set_cell(
            ws, r, 1,
            f"#{idx}", bold=True, color="FFFFFFFF", fill=_GREY, align="center",
        )
        head = (
            f"wafer {base.wafer_id}   "
            f"die ({base.col},{base.row})   pos {base.position_key}   "
            f"[{base.source.value}]"
        )
        _set_cell(ws, r, 2, head, bold=True, fill=_LIGHT, wrap=True)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=n_cols)
        ws.row_dimensions[r].height = 18
        r += 1

        # Layer 이름 행 — 각 사진마다 어떤 layer 인지 블록마다 반복 표기(항목 8).
        layer_names = [base_layer] + compare_layers
        _set_cell(ws, r, 1, "Layer", bold=True, align="center", fill=_LIGHT)
        for ci, name in enumerate(layer_names):
            is_base = ci == 0
            _set_cell(
                ws, r, 2 + ci,
                ("★ " + name + " (기준)") if is_base else name,
                bold=True,
                color="FFFFFFFF",
                fill=_NEON if is_base else _NAVY,
                align="center",
            )
        ws.row_dimensions[r].height = 18
        r += 1

        # 이미지 행
        _set_cell(ws, r, 1, "이미지", bold=True, align="center", fill=_LIGHT)
        ws.row_dimensions[r].height = _IMG_ROW_HEIGHT
        for ci in range(len(columns)):
            col_letter = get_column_letter(2 + ci)
            cell = ws.cell(row=r, column=1 + 1 + ci)
            cell.border = _BORDER
            if ci == 0:
                rec = base
            else:
                mr = item.for_layer(compare_layers[ci - 1])
                rec = mr.matched if mr and mr.matched else None
            if rec is not None:
                thumb = thumb_cache.get_full_thumbnail(rec.image_path, max_size=_IMG_PX)
                if thumb is not None:
                    try:
                        xl = XLImage(str(thumb))
                        xl.anchor = f"{col_letter}{r}"
                        ws.add_image(xl)
                    except (OSError, ValueError):
                        cell.value = "(이미지 로드 실패)"
                else:
                    cell.value = "(이미지 없음)"
            else:
                _set_cell(ws, r, 2 + ci, "매칭 없음", color=_NOMATCH, align="center")
        r += 1

        # 상세 정보 행
        _set_cell(ws, r, 1, "정보", bold=True, align="center", fill=_LIGHT)
        for ci in range(len(columns)):
            if ci == 0:
                rec = base
                matched = True
                dist = None
            else:
                mr = item.for_layer(compare_layers[ci - 1])
                rec = mr.matched if mr else None
                matched = bool(mr and mr.is_match)
                dist = mr.distance if mr else None
            lines = []
            if ci == 0:
                lines.append("기준 ★")
                lines.append(f"위치 {base.position_key}")
                lines.append(Path(base.image_path).name)
                extra = getattr(getattr(item, "base_cluster", None), "extra_count", 0) or 0
                if extra:
                    lines.append(f"+{extra} 근접중복")
            elif rec is not None:
                lines.append(f"매칭 O (거리 {dist:.1f})" if dist is not None else "매칭 O")
                lines.append(f"위치 {rec.position_key}")
                lines.append(Path(rec.image_path).name)
            else:
                lines.append("매칭 X")
            color = _NEON if ci == 0 else (_MATCH if matched else _NOMATCH)
            _set_cell(ws, r, 2 + ci, "\n".join(lines), color=color, wrap=True, size=9)
        ws.row_dimensions[r].height = 48
        r += 1

        # 원본 경로 행 (추적용)
        _set_cell(ws, r, 1, "원본경로", bold=True, align="center", fill=_LIGHT)
        _set_cell(ws, r, 2, str(base.image_path), color=_GREY, wrap=True, size=8)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=n_cols)
        ws.row_dimensions[r].height = 24
        r += 1

        # 메모 행(세션 마킹/메모가 있을 때만)
        note = (notes or {}).get(str(base.image_path), "")
        if note:
            _set_cell(ws, r, 1, "메모", bold=True, align="center", fill=_LIGHT)
            _set_cell(ws, r, 2, note, color=_NAVY, wrap=True, size=9)
            ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=n_cols)
            ws.row_dimensions[r].height = 28
            r += 1
        r += 1  # 블록 간 간격

    wb.save(out)
    return out
