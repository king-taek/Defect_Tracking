"""AOI 엔지니어 모드 좌표 추출(app.aoi) — 참고 저장소 king-taek/coding 의 메커니즘 고정.

기대값은 참고 저장소가 문서화한 규칙으로 손으로 계산했다:
  Camtek INI : x_index=floor(X/pitch), col=x_index−col_origin, row=row_total−y_index,
               x/y = floor(나머지)  ← 반올림이 아니라 **버림**
  KLA .001   : col=XINDEX+zero_x, row=YINDEX+zero_y, x=round(XREL), y=round(DiePitchY−YREL)
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from app import aoi
from app.aoi import camtek_ini, camtek_live, kla_info, wafer_geometry
from app.aoi.models import CAMTEK_COL_OFFSET

PX, PY = 37247.7, 44905.4
_JPEG = b"\xff\xd8\xff\xd9"


@pytest.fixture(autouse=True)
def _fresh_caches():
    aoi.clear_caches()
    yield
    aoi.clear_caches()


# ---------------------------------------------------------------- LIVE 파일명

@pytest.mark.parametrize("stem, expect", [
    # (A) col_row_x_y_Name
    ("TB500_RDL4 - Multi_FDV-RDL4_W7548304XYG4_5_4_31863.2366998812_26908.4427394723_Irregular Bump",
     (5, 4, 31863.2366998812, 26908.4427394723, ())),
    # (B) col_row_Name_x_y
    ("R_VLP-PDIS3_W6317098XYB5_4_5_Over Sized Bump_30229.803_1987.994",
     (4, 5, 30229.803, 1987.994, ())),
    # (C) col_row_Name_x_y_DX_DY_Area — x/y 는 **처음 두 수치**, 뒤는 extra
    ("P_LOT1_W1_4_5_Over Sized Bump_30229.803_1987.994_12.5_18.3_229.1",
     (4, 5, 30229.803, 1987.994, (12.5, 18.3, 229.1))),
])
def test_live_name_layouts(stem, expect):
    got = camtek_live.parse_live_name(stem)
    assert got is not None
    assert (got.col, got.row, got.x, got.y, got.extra) == expect


@pytest.mark.parametrize("stem", [
    "W6459076XYG1_2_0_23_2",          # KLA: 앞 식별자 1개뿐
    "00MEU018XYG1_-1_4_23_1",         # KLA: 음수 인덱스가 첫 정수 쌍
    "LOT_W1_-2_-2_31_2",              # 규칙 2 통과해도 음수 die 는 거부
    "253715.91797.c.-1104740629.1",   # 점표기 — 정수 쌍 없음
])
def test_live_name_rejects_non_live(stem):
    assert camtek_live.parse_live_name(stem) is None


# ---------------------------------------------------------------- Camtek INI

def _write_ini(folder: Path, entries: list[tuple[str, float, float, int, int]],
               recipe: int | None = None) -> None:
    lines = []
    for name, X, Y, col, row in entries:
        lines += [f"[{name}]", f"X={X}", f"Y={Y}", f"Col={col}", f"Row={row}"]
        if recipe is not None:
            lines.append(f"RecipeNumber={recipe}")
        (folder / name).write_bytes(_JPEG)
    (folder / "ColorImageGrabingInfo.ini").write_text("\n".join(lines), encoding="utf-8")


def _write_params(folder: Path, center: tuple[float, float] | None = None) -> None:
    txt = ["[Geometry]", f"DieStep_X={PX}", f"DieStep_Y={PY}", "[Geometric]", "Diameter=300000"]
    if center:
        txt += [f"Center_X={center[0]}", f"Center_Y={center[1]}"]
    (folder / "Params_WaferInfo.ini").write_text("\n".join(txt), encoding="utf-8")


# 실측 예시 1건: X/Y 로 유도한 die 인덱스 (6, 2), 나머지 30229.80 / 1987.99.
_X, _Y = 253716.003307344, 91798.7938704543


def test_camtek_ini_die_coords_floor_and_center_fallback(tmp_path):
    """Center 미기록 → col_origin=2(상수), row_total=ceil(D/pitch_y)=7. 나머지는 버림."""
    _write_ini(tmp_path, [("a.jpeg", _X, _Y, 6, 2)])
    _write_params(tmp_path)
    c = aoi.resolve(tmp_path / "a.jpeg")
    assert c is not None and c.source == "camtek_ini"
    assert (c.col, c.row) == (6 - CAMTEK_COL_OFFSET, 7 - 2)
    assert (c.x, c.y) == (30229.0, 1987.0)   # round 였다면 30230/1988
    geom = wafer_geometry.camtek_geometry(tmp_path)
    assert geom.source.startswith("Params_WaferInfo.ini")


def test_camtek_ini_origins_derived_from_center(tmp_path):
    """Center_X/Y 가 있으면 col_origin=ceil((Cx−D/2)/px), row_total=floor((Cy+D/2)/py)−1."""
    _write_ini(tmp_path, [("a.jpeg", _X, _Y, 6, 2)])
    _write_params(tmp_path, center=(150000.0, 150000.0))
    c = aoi.resolve(tmp_path / "a.jpeg")
    col_origin = math.ceil((150000 - 150000) / PX)              # 0
    row_total = math.floor((150000 + 150000) / PY) - 1          # 5
    assert (c.col, c.row) == (6 - col_origin, row_total - 2)


def test_camtek_ini_rejects_pitch_that_fails_grid_check(tmp_path):
    """읽은 pitch 로 Col == floor(X/pitch_x) 가 안 맞으면 채택하지 않는다 → 절대좌표 폴백."""
    _write_ini(tmp_path, [("a.jpeg", 10000.0, 20000.0, 5, 3)])   # floor(10000/37247)=0 ≠ 5
    _write_params(tmp_path)
    assert wafer_geometry.camtek_geometry(tmp_path) is None
    c = aoi.resolve(tmp_path / "a.jpeg")
    assert c.source == "camtek_abs"
    assert (c.col, c.row, c.x, c.y) == (5 - CAMTEK_COL_OFFSET, -3, 10000.0, 20000.0)


def test_camtek_ini_index_from_coords_not_ini_fields(tmp_path):
    """Row 필드가 레시피별로 1 어긋나도(검산은 '레시피별 상수') die 는 좌표에서 유도한다."""
    folder = tmp_path
    lines = []
    for name, X, Y, col, row, rc in [("a.jpeg", _X, _Y, 6, 2, 1), ("b.jpeg", _X, _Y, 6, 3, 2)]:
        lines += [f"[{name}]", f"X={X}", f"Y={Y}", f"Col={col}", f"Row={row}", f"RecipeNumber={rc}"]
        (folder / name).write_bytes(_JPEG)
    (folder / "ColorImageGrabingInfo.ini").write_text("\n".join(lines), encoding="utf-8")
    _write_params(folder)
    a, b = aoi.resolve(folder / "a.jpeg"), aoi.resolve(folder / "b.jpeg")
    assert a.source == b.source == "camtek_ini"
    assert (a.col, a.row, a.x, a.y) == (b.col, b.row, b.x, b.y)


def test_ini_utf16_is_readable(tmp_path):
    """UTF-16 INI 도 정규식이 맞아야 한다(인코딩 무시로 0건이 되던 사고 방지)."""
    (tmp_path / "a.jpeg").write_bytes(_JPEG)
    (tmp_path / "ColorImageGrabingInfo.ini").write_text(
        f"[a.jpeg]\nX={_X}\nY={_Y}\nCol=6\nRow=2\n", encoding="utf-16")
    _write_params(tmp_path)
    assert aoi.resolve(tmp_path / "a.jpeg").source == "camtek_ini"


def test_resolve_batch_unifies_frames(tmp_path):
    """한 실행에 die 좌표 폴더와 절대좌표 폴더가 섞이면 전부 절대좌표로 통일한다."""
    good, bad = tmp_path / "good", tmp_path / "bad"
    good.mkdir(); bad.mkdir()
    _write_ini(good, [("a.jpeg", _X, _Y, 6, 2)]); _write_params(good)
    _write_ini(bad, [("b.jpeg", 10000.0, 20000.0, 5, 3)]); _write_params(bad)
    assert aoi.resolve(good / "a.jpeg").source == "camtek_ini"
    got = aoi.resolve_batch([good / "a.jpeg", bad / "b.jpeg"])
    assert got[good / "a.jpeg"].source == "camtek_abs"
    assert got[good / "a.jpeg"].x == math.floor(_X)
    assert got[bad / "b.jpeg"].source == "camtek_abs"


def test_live_name_wins_over_ini(tmp_path):
    """우선순위: LIVE 파일명 → INI → KLA."""
    name = "P_LOT_W1_5_4_Bump_100.5_200.5.jpeg"
    _write_ini(tmp_path, [(name, _X, _Y, 6, 2)]); _write_params(tmp_path)
    c = aoi.resolve(tmp_path / name)
    assert c.source == "camtek_live" and (c.col, c.row, c.x, c.y) == (5, 4, 100.5, 200.5)


# ---------------------------------------------------------------- KLA .001

_KLA_HEAD = (
    "FileVersion 1 2;\n"
    f"DiePitch {PX} {PY};\n"
    "SampleSize 1 300;\n"
    "SampleCenterLocation 100000 100000;\n"
    'WaferID "W123";\n'
)


def test_parse_kla_header_zero_from_center():
    g = wafer_geometry.parse_kla_header(_KLA_HEAD)
    assert g.source == "DiePitch+SampleCenterLocation"
    # zero = −ceil((center − D/2)/pitch) : (100000−150000)/37247.7=−1.34 → ceil −1 → 1
    assert (g.zero_x, g.zero_y) == (1, 1)


def test_parse_kla_header_testplan_fallback():
    txt = f"DiePitch {PX} {PY};\nSampleTestPlan 3\n-3 0\n-1 2\n2 1;\n"
    g = wafer_geometry.parse_kla_header(txt)
    assert g.source == "DiePitch+SampleTestPlan"
    assert g.zero_x == 3 and g.zero_y == wafer_geometry.KLA_ZERO_Y


def test_kla_info_folder(tmp_path):
    (tmp_path / "img1.jpg").write_bytes(_JPEG)
    (tmp_path / "scan.001").write_text(
        _KLA_HEAD + "DefectList\nTiffFileName img1.tif;\n"
        "1 123.4 567.8 1000.4 2000.25 -1 2 1 1;\n", encoding="utf-8")
    c = aoi.resolve(tmp_path / "img1.jpg")
    assert c is not None and c.source == "kla"
    assert (c.col, c.row) == (-1 + 1, 2 + 1)
    assert (c.x, c.y) == (round(1000.4), round(PY - 2000.25))
    assert (c.native_x, c.native_y) == (1000.4, 2000.25)
    assert kla_info.read_wafer_id(tmp_path) == "W123"


def test_unknown_image_returns_none(tmp_path):
    (tmp_path / "x.jpg").write_bytes(_JPEG)
    assert aoi.resolve(tmp_path / "x.jpg") is None
    assert camtek_ini.has_ini(tmp_path) is False
