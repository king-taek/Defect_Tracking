"""Camtek 파일명 파싱 테스트 (문서 Section 6 / 13.3.4 두 레이아웃)."""

from app.models import ParseStatus
from app.parsers.camtek_filename import parse_camtek_filename


def test_layout_a_section6_example1():
    """Section 6 예시1: 좌표가 끝의 defect 이름 앞에 위치."""
    name = (
        "R_TB500_LIVE_PI4_WLW_PIDS3_00MHE105XYF6_4_5_"
        "15055.344483842_15721.8090212471_Over Sized Bump.jpg"
    )
    res = parse_camtek_filename(name)
    assert res.status == ParseStatus.OK
    assert (res.col, res.row) == (4, 5)
    assert round(res.x) == 15055
    assert round(res.y) == 15722
    assert "Over Sized Bump" in res.defect_name


def test_layout_a_section6_example2():
    name = (
        "R_TB500_LIVE_PI4_WLW_PIDS3_00MHE106XYC5_3_3_"
        "24270.2139160645_16328.045444993_Over Sized Bump.jpg"
    )
    res = parse_camtek_filename(name)
    assert res.status == ParseStatus.OK
    assert (res.col, res.row) == (3, 3)
    assert round(res.x) == 24270
    assert round(res.y) == 16328


def test_layout_b_section1334_example():
    """Section 13.3.4 예시: defect 이름이 좌표 앞(중간)에 위치."""
    name = (
        "R_TB500_LIVE_PI4_VLP-PDIS3_W6317098XYB5_4_5_"
        "Over Sized Bump_30229.8033073437_1987.99387045427"
    )
    res = parse_camtek_filename(name)
    assert res.status == ParseStatus.OK
    assert (res.col, res.row) == (4, 5)
    assert round(res.x) == 30230
    assert round(res.y) == 1988


def test_layout_c_aoi_tool_schema_integer_xy_with_sizes():
    """실제 AOI 변환 스키마: col_row_Name_x_y_DXSize_DYSize_DArea (x/y 정수)."""
    name = (
        "KLA_204_00S6T133XYD1_3_4_Over Sized Bump_4629_5351_5.2_3.9_20.28.jpg"
    )
    res = parse_camtek_filename(name)
    assert res.status == ParseStatus.OK
    assert (res.col, res.row) == (3, 4)
    assert round(res.x) == 4629 and round(res.y) == 5351  # 크기값(5.2,3.9)을 오인하지 않음
    assert res.defect_name == "Over Sized Bump"
    assert res.dx_size == 5.2 and res.dy_size == 3.9 and res.d_area == 20.28


def test_no_coordinates_returns_not_found():
    """KLA 스타일 파일명(좌표 없음)은 NOT_FOUND -> 다른 경로로 처리."""
    res = parse_camtek_filename("00T3UB50XYF5_0_1_7_1.jpg")
    assert res.status == ParseStatus.NOT_FOUND


def test_original_name_style_returns_not_found():
    """Camtek 원본 section-key 이름은 파일명 파싱 대상이 아님."""
    res = parse_camtek_filename("253715.91797.c.-1104740629.1.jpg")
    assert res.status == ParseStatus.NOT_FOUND
