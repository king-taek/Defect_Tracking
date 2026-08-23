"""사진 대조 리포트 출력 (설계 문서 design_handoff_fluent_redesign/04-excel-report.md).

담은(선택한) 기준 defect 만 "사진 대조" 시트 한 장에 블록으로 출력한다. 요약/매칭 표/미매칭
시트는 만들지 않는다. 판정에 쓰지 않는 거리(µm) 표기는 넣지 않고 매칭 / 미매칭 두 상태만
남기며, 미매칭은 회색 1단(회색 채움 + "미매칭" 한 단어)으로 조용히 둔다.

열은 LOT layer 순서로 고정한다. 기준 layer 를 맨 왼쪽으로 끌어오지 않고 자기 자리에서
"★ 기준" 표시로만 구분한다. 담은 항목의 기준 layer 가 둘 이상 섞여 있으면(기준 없음 모드)
★ 를 아예 쓰지 않고 모든 열을 동등한 layer 로 그린다.

저장 경로는 반드시 assert_output_safe 게이트를 통과해야 하며, 원본 폴더 내부면 차단된다.
원본 이미지는 read-only 로만 읽는다(썸네일 캐시를 통해).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.pagebreak import Break
from openpyxl.worksheet.properties import PageSetupProperties

from app.models import BaseDefectMatches
from app.safety import assert_output_safe
from app.thumbnails import ThumbnailCache

# 시트는 이 한 장뿐이다.
SHEET_TITLE = "사진 대조"

# 담은 건이 이 값을 넘으면 출력 전에 확인을 받는다(REVIEW-01 A13).
# export_excel 자체는 묻지 않는다 - 워커 스레드에서 호출되므로 대화상자를 띄울 수 없다.
# UI 가 출력 버튼을 누른 시점에 len(selected) 를 이 상수와 비교해 확인 대화상자를 띄운다.
EXPORT_WARN_BLOCKS = 200

# ---- 색 팔레트 (04-excel-report.md) ----
_HEAD = "FF20303F"     # 머리 채움 (흰 글자와 12.6:1)
_SUBHEAD = "FFF1F5F9"  # 규칙 행
_LYHEAD = "FFE8EEF4"   # layer 머리
_BLOCK = "FFEEF3F8"    # 블록 머리
_GREY_BG = "FFF6F7F8"  # 미매칭 채움
_GREY_FG = "FF8A949E"  # 미매칭 글자
_PASS = "FF1F7A1F"     # "매칭"
_PASS_BG = "FFEEF7EE"
_LINK = "FF0F6CBD"
_LINE = "FFDCE3EA"
# 위 표에 없는 보조색 두 가지: 미매칭 상태 칸의 옅은 글자와, 사진 칸 바탕(검정)이다.
_DIM = "FFA8B0B8"
_PHOTO_BG = "FF000000"
_WHITE = "FFFFFFFF"
# 미매칭 layer 머리 칸은 일반 layer 머리보다 한 단 낮은 회색을 쓴다.
_LY_MISS = "FFEFF1F3"

_THIN = Side(style="thin", color=_LINE)
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

# ---- 치수 (글자 배율 1.0 기준) ----
# 열 폭은 Excel 문자 단위, 행 높이는 포인트. 글자 크기를 "크게"(theme.FONT_SCALES["large"]
# = 1.3)로 쓰면 font_scale 인자로 같은 비율을 넘겨받아 폭/높이/사진 크기가 함께 커진다.
_COL_WIDTH_CHARS = 16.5   # 약 115 px (프로토타입 116 px)
_PX_PER_CHAR = 7.0        # 열 폭 1 문자 ≈ 7 px
_PT_TO_PX = 96.0 / 72.0   # 행 높이 1 pt ≈ 1.333 px

_RH_HEAD = 24.0
_RH_RULE = 18.0
_RH_BLOCK = 20.0
_RH_LAYER = 17.0
_RH_PHOTO = 72.0   # 96 px 상당
_RH_STATE = 16.0
_RH_FILE = 16.0

_FS_TITLE = 13.0
_FS_META = 9.5
_FS_RULE = 9.0
_FS_BLOCK = 10.0
_FS_LAYER = 9.5
_FS_STATE = 9.5
_FS_FILE = 8.5

# 썸네일은 셀 상자보다 크게 구워 두고 셀에 맞춰 줄인다(인쇄 해상도 확보).
_THUMB_SUPERSAMPLE = 2

# 블록 한 개는 5행이다: 머리 / layer / 사진 / 상태 / 파일명.
# 04-excel-report.md 는 "4행"이라 적었지만 같은 문서가 상태 행과 파일명 행을 따로 명세한다.
# 파일명 행을 상태와 한 칸에 합치면 하이퍼링크 표시 글자가 "매칭 + 파일명"이 되어
# "링크 글자는 실제 파일명" 규칙을 지킬 수 없으므로 두 행으로 나눴다.
BLOCK_ROWS = 5


def _font(scale: float, size: float, **kwargs) -> Font:
    return Font(size=round(size * scale, 1), **kwargs)


def _split_layer(name: str) -> tuple[str, str]:
    """layer 표시 이름을 (토큰, 재리뷰 깊이) 로 나눈다.

    scanner 는 canonical 이 충돌할 때만 "LYA4_재리뷰" / "LYA4_재재리뷰" 형태의 display
    이름을 만든다(app/scanner.py). 리포트 layer 칸은 토큰과 깊이를 나눠 적는다.
    """
    token = (name or "").strip()
    for level in (3, 2, 1):
        suffix = "_" + "재" * level + "리뷰"
        if token.endswith(suffix):
            return token[: -len(suffix)], "재" * level
    return token, ""


def _layer_label(name: str) -> str:
    token, depth = _split_layer(name)
    return f"{token} {depth}".strip()


def _extra_count(holder: object) -> int:
    """근접 중복 묶음의 '대표 외' 개수. cluster 정보가 없으면 0."""
    for attr in ("base_cluster", "matched_cluster", "cluster"):
        cluster = getattr(holder, attr, None)
        if cluster is not None:
            return max(0, int(getattr(cluster, "extra_count", 0) or 0))
    return max(0, int(getattr(holder, "extra_count", 0) or 0))


def _sort_token(name: str) -> tuple[str, str]:
    token, depth = _split_layer(name)
    return (token.upper(), depth)


def _column_layers(
    selected: list[BaseDefectMatches],
    base_layer: str,
    compare_layers: list[str],
    layer_order: Optional[list[str]],
) -> list[str]:
    """시트 전체가 함께 쓰는 열(layer) 목록을 LOT 순서로 만든다.

    담은 블록들에 실제로 등장한 layer 만 열로 만든다(조사하지 않은 layer 를 미매칭처럼
    보이게 하지 않는다). layer_order 를 주면 그 순서를 그대로 따르고, 없으면 호출자가 준
    compare_layers 순서를 쓰되 기준 layer 는 이름 순서상 제자리에 끼워 넣는다.
    기준 layer 를 맨 앞으로 끌어오는 예전 동작은 쓰지 않는다.
    """
    seen: list[str] = []
    for item in selected:
        names = [item.base.layer or base_layer]
        names += [mr.compare_layer for mr in item.results]
        for name in names:
            if name and name not in seen:
                seen.append(name)
    if not seen:
        for name in [base_layer, *compare_layers]:
            if name and name not in seen:
                seen.append(name)

    if layer_order:
        pos = {name: i for i, name in enumerate(layer_order)}
        tail = len(layer_order)
        return sorted(seen, key=lambda n: (pos.get(n, tail), seen.index(n)))

    ordered = [name for name in compare_layers if name in seen]
    for name in seen:
        if name in ordered:
            continue
        key = _sort_token(name)
        spot = next(
            (i for i, other in enumerate(ordered) if _sort_token(other) > key),
            len(ordered),
        )
        ordered.insert(spot, name)
    return ordered


def _paint(ws, row: int, n_cols: int, fill: Optional[str]) -> None:
    """행 전체에 채움과 테두리를 깔아 둔다(병합 전에 호출)."""
    for col in range(1, n_cols + 1):
        cell = ws.cell(row=row, column=col)
        if fill:
            cell.fill = PatternFill("solid", fgColor=fill)
        cell.border = _BORDER


def _span(ws, row: int, first: int, last: int, value: str, font: Font,
          *, align: str = "left") -> None:
    """first..last 열을 병합해 한 줄 글을 넣는다."""
    cell = ws.cell(row=row, column=first, value=value)
    cell.font = font
    cell.alignment = Alignment(horizontal=align, vertical="center")
    if last > first:
        ws.merge_cells(start_row=row, start_column=first, end_row=row, end_column=last)


def _cell(ws, row: int, col: int, value, *, font: Font, fill: Optional[str] = None,
          align: str = "center", vertical: str = "center"):
    cell = ws.cell(row=row, column=col, value=value)
    cell.font = font
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    cell.alignment = Alignment(horizontal=align, vertical=vertical)
    cell.border = _BORDER
    return cell


def photo_box_px(font_scale: float = 1.0) -> tuple[int, int]:
    """사진 칸의 픽셀 상자 크기. 열 폭과 행 높이에서 계산한다(04 문서 규격).

    글자 배율이 커지면 열 폭(문자)과 행 높이(pt)가 같은 비율로 커지므로 사진도 따라 커진다.
    """
    col_width_chars = _COL_WIDTH_CHARS * font_scale
    row_height_pt = _RH_PHOTO * font_scale
    return int(col_width_chars * _PX_PER_CHAR), int(row_height_pt * _PT_TO_PX)


def _place_photo(ws, thumb_cache: ThumbnailCache, rec, row: int, col: int,
                 box: tuple[int, int], extra: int, scale: float) -> None:
    """(row,col) 칸에 사진을 셀 크기에 맞춰 줄여 넣는다. 우하단에 ＋n 묶음 배지."""
    target_w_px, target_h_px = box
    badge = f"＋{extra}" if extra > 0 else None
    cell = _cell(
        ws, row, col, badge,
        font=_font(scale, _FS_FILE, bold=True, color=_WHITE),
        fill=_PHOTO_BG, align="right", vertical="bottom",
    )
    source = None
    if rec is not None:
        source = thumb_cache.get_full_thumbnail(
            rec.image_path, max_size=int(max(target_w_px, target_h_px) * _THUMB_SUPERSAMPLE)
        )
    if source is None:
        cell.value = "사진 없음"
        cell.font = _font(scale, _FS_STATE, color=_GREY_FG)
        cell.fill = PatternFill("solid", fgColor=_GREY_BG)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        return
    try:
        xl = XLImage(str(source))
        ratio = min(target_w_px / xl.width, target_h_px / xl.height, 1.0)
        xl.width, xl.height = int(xl.width * ratio), int(xl.height * ratio)
        xl.anchor = f"{get_column_letter(col)}{row}"
        ws.add_image(xl)
    except (OSError, ValueError):
        cell.value = "사진 없음"
        cell.font = _font(scale, _FS_STATE, color=_GREY_FG)
        cell.fill = PatternFill("solid", fgColor=_GREY_BG)
        cell.alignment = Alignment(horizontal="center", vertical="center")


def _place_file_link(ws, row: int, col: int, image_path, scale: float) -> None:
    """파일명을 그대로 보여 주는 하이퍼링크. 원본을 심지 않고 링크로만 연결한다."""
    path = Path(image_path)
    cell = _cell(
        ws, row, col, path.name,
        font=_font(scale, _FS_FILE, color=_LINK, underline="single"),
        align="center",
    )
    try:
        cell.hyperlink = path.resolve().as_uri()
    except (OSError, ValueError):
        pass  # 링크를 못 걸어도 파일명 글자는 남는다


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
    progress: Optional[Callable[[int, int], None]] = None,
    layer_order: Optional[list[str]] = None,
    font_scale: float = 1.0,
) -> Path:
    """담은 기준 defect 들을 "사진 대조" 시트 한 장으로 저장한다.

    Args:
        selected: 담은 항목만. 전량을 넣지 않는다.
        layer_order: LOT 의 원래 layer 순서(폴더 스캔 순서). 항상 넘기는 것이 규칙이다.
            없으면 compare_layers 순서를 쓰고 기준 layer 는 이름 순서상 제자리에 둔다.
        font_scale: 글자 크기 배율(1.0 보통 / 1.3 크게). 열 폭·행 높이·사진 크기가
            같은 비율로 커진다.

    Returns:
        저장된 파일의 절대 경로.

    Raises:
        OriginalProtectionError: 출력 경로가 원본 폴더 내부일 때.
    """
    out = assert_output_safe(output_path, source_roots)
    out.parent.mkdir(parents=True, exist_ok=True)

    scale = float(font_scale) if font_scale else 1.0
    selected = list(selected)

    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_TITLE
    ws.sheet_view.showGridLines = False

    columns = _column_layers(selected, base_layer, compare_layers, layer_order)
    if not columns:
        columns = [base_layer or ""]
    n_cols = len(columns)
    col_of = {name: i + 1 for i, name in enumerate(columns)}

    # 머리 2행은 제목 / 메타 / 집계 세 구역으로 나눈다. 열이 3개보다 적은 작은 리포트에서도
    # 제목 칸(A1)이 흔들리지 않도록 머리 폭만 최소 3열로 잡는다.
    head_cols = max(n_cols, 3)
    for col in range(1, head_cols + 1):
        ws.column_dimensions[get_column_letter(col)].width = _COL_WIDTH_CHARS * scale

    # 담은 항목들의 실제 기준 layer. 둘 이상이면 "기준 없음" 모드로 그린다(REVIEW-01 A4).
    base_layers_present: list[str] = []
    for item in selected:
        name = item.base.layer or base_layer
        if name and name not in base_layers_present:
            base_layers_present.append(name)
    mixed = len(base_layers_present) > 1
    base_desc = base_layers_present[0] if base_layers_present else base_layer

    # ---- 행 1: 머리 ----
    _paint(ws, 1, head_cols, _HEAD)
    ws.row_dimensions[1].height = _RH_HEAD * scale
    if mixed:
        meta = (
            f"{lot_name} · 기준 없음 · 조사 layer {n_cols}개 · "
            f"허용 오차 {tolerance:g} µm"
        )
    else:
        meta = (
            f"{lot_name} · 기준 {_layer_label(base_desc)} · "
            f"허용 오차 {tolerance:g} µm"
        )
    counts = (
        f"담은 {len(selected)}건 · layer {n_cols}개 · {datetime.now():%Y-%m-%d %H:%M}"
    )
    title_font = _font(scale, _FS_TITLE, bold=True, color=_WHITE)
    meta_font = _font(scale, _FS_META, color=_WHITE)
    split = max(2, head_cols // 2)
    _span(ws, 1, 1, 1, SHEET_TITLE, title_font)
    _span(ws, 1, 2, split, meta, meta_font)
    _span(ws, 1, split + 1, head_cols, counts, meta_font, align="right")

    # ---- 행 2: 규칙 ----
    _paint(ws, 2, head_cols, _SUBHEAD)
    ws.row_dimensions[2].height = _RH_RULE * scale
    if mixed:
        rule_left = "열 = LOT layer 순서 고정 · 기준 없음 · 창 고정 · 블록당 1페이지"
    else:
        rule_left = (
            "열 = LOT layer 순서 고정 · 기준은 ★ 표시로만 구분 · 창 고정 · 블록당 1페이지"
        )
    rule_right = "미매칭 = 회색 처리 · 거리 표기 없음"
    rule_font = _font(scale, _FS_RULE, color=_HEAD)
    _span(ws, 2, 1, split, rule_left, rule_font)
    _span(ws, 2, split + 1, head_cols, rule_right, rule_font, align="right")

    ws.freeze_panes = "A3"

    # ---- 행 3~: 블록 반복 (블록 1개 = 5행) ----
    box = photo_box_px(scale)
    row = 3
    total = len(selected)
    for idx, item in enumerate(selected, start=1):
        if progress is not None:
            progress(idx, total)
        base = item.base
        item_base_layer = base.layer or base_layer

        # 이 블록이 실제로 채우는 열: 기준 + 매칭 시도한 비교 layer.
        entries: dict[int, object] = {}
        base_col = col_of.get(item_base_layer)
        if base_col is not None:
            entries[base_col] = None  # None 이면 기준 사진 칸
        for mr in item.results:
            col = col_of.get(mr.compare_layer)
            if col is not None and col not in entries:
                entries[col] = mr

        matched = sum(
            1 for mr in entries.values() if mr is not None and mr.matched is not None
        )
        if mixed:
            # 기준 열이 없으므로 그 블록의 사진이 있는 칸 전부가 분자, 열 수가 분모다.
            hit = matched + (1 if base_col is not None else 0)
            denominator = len(entries)
        else:
            hit = matched
            denominator = max(0, len(entries) - (1 if base_col is not None else 0))

        # 블록 머리
        _paint(ws, row, n_cols, _BLOCK)
        ws.row_dimensions[row].height = _RH_BLOCK * scale
        die = f"({base.col}, {base.row})" if base.ok else "(좌표 없음)"
        parts = [
            f"#{idx}",
            f"wafer {base.wafer_id}",
            f"die {die}",
            f"pos {base.position_key}",
        ]
        if base.defect_name:
            parts.append(base.defect_name)
        parts.append("교차매치" if mixed else f"기준 {_layer_label(item_base_layer)}")
        head_font = _font(scale, _FS_BLOCK, bold=True, color=_HEAD)
        count_text = f"매칭 {hit} / {denominator}"
        if n_cols >= 2:
            _span(ws, row, 1, n_cols - 1, " · ".join(parts), head_font)
            _span(ws, row, n_cols, n_cols, count_text, head_font, align="right")
        else:
            _span(ws, row, 1, 1, f"{' · '.join(parts)} · {count_text}", head_font)
        row += 1

        layer_row, photo_row, state_row, file_row = row, row + 1, row + 2, row + 3
        ws.row_dimensions[layer_row].height = _RH_LAYER * scale
        ws.row_dimensions[photo_row].height = _RH_PHOTO * scale
        ws.row_dimensions[state_row].height = _RH_STATE * scale
        ws.row_dimensions[file_row].height = _RH_FILE * scale

        for col in range(1, n_cols + 1):
            if col not in entries:
                # 이 블록이 조사하지 않은 layer. 빈 칸으로 둔다(미매칭이 아니다).
                for rr in (layer_row, photo_row, state_row, file_row):
                    ws.cell(row=rr, column=col).border = _BORDER
                continue

            mr = entries[col]
            is_base_cell = mr is None
            rec = base if is_base_cell else mr.matched
            hit_cell = rec is not None
            # 기준 없음 모드에서는 ★ 를 쓰지 않고 모든 칸을 동등한 layer 로 그린다.
            star = is_base_cell and not mixed

            # layer 행
            label = _layer_label(columns[col - 1])
            if star:
                _cell(ws, layer_row, col, f"{label} ★ 기준",
                      font=_font(scale, _FS_LAYER, bold=True, color=_WHITE), fill=_HEAD)
            elif hit_cell:
                _cell(ws, layer_row, col, label,
                      font=_font(scale, _FS_LAYER, bold=True, color=_HEAD), fill=_LYHEAD)
            else:
                _cell(ws, layer_row, col, label,
                      font=_font(scale, _FS_LAYER, color=_GREY_FG), fill=_LY_MISS)

            # 사진 행
            if hit_cell:
                _place_photo(
                    ws, thumb_cache, rec, photo_row, col, box,
                    _extra_count(item if is_base_cell else mr), scale,
                )
            else:
                _cell(ws, photo_row, col, "미매칭",
                      font=_font(scale, _FS_STATE, bold=True, color=_GREY_FG),
                      fill=_GREY_BG)

            # 상태 행
            if star:
                _cell(ws, state_row, col, "기준",
                      font=_font(scale, _FS_STATE, bold=True, color=_HEAD), fill=_LYHEAD)
            elif hit_cell:
                _cell(ws, state_row, col, "매칭",
                      font=_font(scale, _FS_STATE, bold=True, color=_PASS), fill=_PASS_BG)
            else:
                _cell(ws, state_row, col, "-",
                      font=_font(scale, _FS_STATE, color=_DIM), fill=_GREY_BG)

            # 파일명 행
            if hit_cell:
                _place_file_link(ws, file_row, col, rec.image_path, scale)
            else:
                _cell(ws, file_row, col, None, font=_font(scale, _FS_FILE), fill=_GREY_BG)

        row = file_row + 1
        # 블록마다 페이지를 나눈다(1건 = 1페이지).
        ws.row_breaks.append(Break(id=file_row))

    # ---- 인쇄 설정 ----
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_title_rows = "1:2"

    wb.save(out)
    return out
