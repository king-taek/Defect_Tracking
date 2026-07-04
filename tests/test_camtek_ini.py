"""Camtek INI 좌표 변환 테스트 (문서 Section 13.3.9 ~ 13.3.13 워크드 예시)."""

import pytest

from app import config
from app.models import ParseStatus
from app.parsers import camtek_ini

# 아래 CASES 의 기대값은 문서 Section 13.3.9~13.3.13 이 쓴 pitch/offset 기준으로
# 계산돼 있다 — 실제 DEVA 기본 제품값(AOIDeviceDB "DEVA Live" 실측)과는 별개이므로,
# 이 문서 예시 상수로 고정한 임시 제품을 활성화해 기본값 변경에 영향받지 않게 한다.
_DOC_PRODUCT_KEY = "_DOC_EXAMPLE_DEVA"


@pytest.fixture(autouse=True)
def _doc_example_product():
    prev = config.active_product().key
    config.PRODUCTS[_DOC_PRODUCT_KEY] = config.ProductConfig(
        key=_DOC_PRODUCT_KEY,
        name="문서 예시(Section 13.3)",
        camtek_pitch_x=37247.7,
        camtek_pitch_y=44905.4,
        camtek_col_offset=2,
        camtek_row_base=7,
        kla_package_x_count=7,
        kla_package_y_count=6,
    )
    config.set_active_product(_DOC_PRODUCT_KEY)
    try:
        yield
    finally:
        config.set_active_product(prev)
        config.PRODUCTS.pop(_DOC_PRODUCT_KEY, None)


# (원본이름, X, Y, Col, Row, 기대 col, row, x_int, y_int)
CASES = [
    ("253715.91797.c.-1104740629.1", 253716.003307344, 91798.7938704543, 6, 2, 4, 5, 30230, 1988),
    ("285836.241929.c.1454174356.2", 285837.569021826, 241931.965714178, 7, 5, 5, 2, 25104, 17405),
    ("183425.337590.c.-363586910.1", 183424.006310378, 337589.125854985, 4, 7, 2, 0, 34433, 23251),
    ("182588.149591.c.1625563295.1", 182587.539096461, 149593.522482771, 4, 3, 2, 4, 33597, 14877),
    ("180377.100975.c.-1378927417.1", 180377.576920526, 100976.81821231, 4, 2, 2, 5, 31387, 11166),
]


def _make_sections(name, x, y, col, row):
    return {
        f"{name}.jpeg".lower(): {
            "x": str(x),
            "y": str(y),
            "col": str(col),
            "row": str(row),
        }
    }


@pytest.mark.parametrize("name,x,y,col,row,ec,er,ex,ey", CASES)
def test_camtek_ini_worked_examples(name, x, y, col, row, ec, er, ex, ey):
    sections = _make_sections(name, x, y, col, row)
    res = camtek_ini.convert_from_sections(sections, name)
    assert res.status == ParseStatus.OK
    assert res.col == ec
    assert res.row == er
    assert round(res.x) == ex
    assert round(res.y) == ey


def test_camtek_ini_fault_fallback():
    """X/Y 가 없으면 FaultX/FaultY 를 사용한다."""
    name = "253715.91797.c.-1104740629.1"
    sections = {
        f"{name}.jpeg": {
            "faultx": "253716.003307344",
            "faulty": "91798.7938704543",
            "col": "6",
            "row": "2",
        }
    }
    res = camtek_ini.convert_from_sections(sections, name)
    assert res.status == ParseStatus.OK
    assert (res.col, res.row) == (4, 5)
    assert round(res.x) == 30230
    assert round(res.y) == 1988


def test_camtek_ini_not_found():
    res = camtek_ini.convert_from_sections({}, "missing")
    assert res.status == ParseStatus.NOT_FOUND


def test_camtek_ini_invalid_missing_col():
    name = "abc"
    sections = {f"{name}.jpeg": {"x": "1", "y": "2", "row": "3"}}
    res = camtek_ini.convert_from_sections(sections, name)
    assert res.status == ParseStatus.INVALID_INFO


def test_real_ini_section_parsing(tmp_path):
    """실제 INI 텍스트(여러 키 포함) 파싱 후 변환."""
    ini = tmp_path / "1. ColorImageGrabingInfo.ini"
    ini.write_text(
        "[253715.91797.c.-1104740629.1.jpeg]\n"
        "X=253716.003307344\n"
        "Y=91798.7938704543\n"
        "StageZ=74818.4\n"
        "Col=6\n"
        "Row=2\n",
        encoding="utf-8",
    )
    res = camtek_ini.convert_camtek_ini(ini, "253715.91797.c.-1104740629.1")
    assert res.status == ParseStatus.OK
    assert (res.col, res.row) == (4, 5)
