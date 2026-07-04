"""KLA 좌표 변환 테스트 (문서 Section 13.2.8 워크드 예시)."""

from app.models import ParseStatus
from app.parsers import kla_info

# 문서 Section 13.2.8 의 KLA info 발췌
SAMPLE_INFO = """\
FileVersion 1 2;
DiePitch 3.7247898000e+004 4.4905301000e+004;
SampleType WAFER;
TiffFileName W5929249XYD6_0_1_23_2.jpg;
DefectList
 2 -13841.989 84687.370 4629.010 39554.104 0 1 5.200 3.900 20.280000 5.200 23 3 1 0 2 2 0 1449 0 1 1 1 0;
"""


def test_kla_worked_example():
    """문서 정답: W5929249XYD6_0_1_23_2.jpg -> 3_3_4629_5351
    col = XINDEX(0) + zeroX(3) = 3
    row = YINDEX(1) + zeroY(2) = 3   (PackageY=5, zeroY=5÷2=2)
    """
    parsed = kla_info.parse_info_text(SAMPLE_INFO)
    res = kla_info.convert_from_parsed(parsed, "W5929249XYD6_0_1_23_2.jpg")
    assert res.status == ParseStatus.OK
    assert res.col == 3
    assert res.row == 3
    assert round(res.x) == 4629
    assert round(res.y) == 5351


def test_kla_die_pitch_y_parsed():
    parsed = kla_info.parse_info_text(SAMPLE_INFO)
    assert abs(parsed.die_pitch_y - 44905.301) < 1e-3


def test_kla_not_found():
    parsed = kla_info.parse_info_text(SAMPLE_INFO)
    res = kla_info.convert_from_parsed(parsed, "DOES_NOT_EXIST.jpg")
    assert res.status == ParseStatus.NOT_FOUND


def test_kla_invalid_info_missing_pitch():
    text = SAMPLE_INFO.replace(
        "DiePitch 3.7247898000e+004 4.4905301000e+004;\n", ""
    )
    parsed = kla_info.parse_info_text(text)
    res = kla_info.convert_from_parsed(parsed, "W5929249XYD6_0_1_23_2.jpg")
    assert res.status == ParseStatus.INVALID_INFO


def test_kla_negative_die_index_rejected():
    """음수 die 위치(XINDEX/YINDEX 가 음수로 col/row<0)는 잘못 매칭되지 않도록 실패."""
    # XINDEX=-5, YINDEX=-5 → col=-2, row=-3
    text = (
        "FileVersion 1 2;\n"
        "DiePitch 3.7247898000e+004 4.4905301000e+004;\n"
        "TiffFileName NEG_0_1_2_3.jpg;\n"
        "DefectList\n"
        " 1 -1.0 2.0 100.0 200.0 -5 -5 5.2 3.9 20.28 5.2 23 3 1 0 2 2 0 1449 0 1 1 1 0;\n"
    )
    parsed = kla_info.parse_info_text(text)
    res = kla_info.convert_from_parsed(parsed, "NEG_0_1_2_3.jpg")
    assert res.status == ParseStatus.INVALID_INFO


def test_select_info_file_prefers_001():
    files = [
        "00T3UB50XYF5_0_1_7_1.jpg",
        "uuid_DEVA_00T3UB50XYF5.001",
        "uuid_DEVA_00T3UB50XYF5.pass",
    ]
    assert kla_info.select_info_file(files) == "uuid_DEVA_00T3UB50XYF5.001"


def test_select_info_file_ignores_pass_and_jpg():
    files = ["a.jpg", "b.pass"]
    assert kla_info.select_info_file(files) is None


def test_select_info_file_non_jpg_fallback():
    files = ["a.jpg", "b.pass", "info.txt"]
    assert kla_info.select_info_file(files) == "info.txt"


def test_select_info_file_excludes_image_extensions():
    """이미지 확장자(.tif/.bmp/.png) 파일은 KLA info 후보에서 제외."""
    files = ["a.jpg", "b.pass", "c.tif", "d.bmp", "e.png"]
    assert kla_info.select_info_file(files) is None


def test_select_info_file_extensionless():
    """확장자 없는 파일을 KLA info 후보로 선택."""
    files = ["a.jpg", "b.pass", "W8190076XYC2"]
    assert kla_info.select_info_file(files) == "W8190076XYC2"


def test_kla_filename_fallback_by_xindex_yindex():
    """TiffFileName 없는 DefectList 블록에서 KLA 파일명 기반 폴백 검색."""
    text = (
        "FileVersion 1 2;\n"
        "DiePitch 3.7247898000e+004 4.4905301000e+004;\n"
        "DefectRecordSpec 22 DEFECTID X Y XREL YREL XINDEX YINDEX;\n"
        "DefectList\n"
        " 1 -84303.118 5810.550 8652.739 5587.609 -2 0 10.41 7.81 81.32 5.2 23 3 1 0;\n"
        " 2 -50000.000 3000.000 4000.000 3000.000 0 -1 5.0 5.0 25.0 5.0 7 3 1 0;\n"
        "EndOfFile;\n"
    )
    parsed = kla_info.parse_info_text(text)
    # TiffFileName 매칭은 실패, all_defects 기반 폴백으로 찾는다
    assert len(parsed.defects) == 0
    assert len(parsed.all_defects) == 2

    res = kla_info.convert_from_parsed(parsed, "W6460170XYB4_-2_0_23_1.jpg")
    assert res.status == ParseStatus.OK
    assert res.col == 1   # -2 + 3 (zeroX)
    assert res.row == 2   # 0 + 2 (zeroY)
    assert round(res.x) == 8653
    assert round(res.y) == 39318  # round(44905.301 - 5587.609)


def test_all_defects_collected_with_tifffilename():
    """TiffFileName 이 있는 구조에서도 all_defects 가 수집됨."""
    parsed = kla_info.parse_info_text(SAMPLE_INFO)
    assert len(parsed.defects) == 1
    assert len(parsed.all_defects) == 1


SAMPLE_TEST_PLAN_INFO = """\
FileVersion 1 2;
DiePitch 3.7247898000e+004 4.4905301000e+004;
SampleTestPlan 3
  -3 -1
  -1 -3
  3 0 ;
TiffFileName W1_-1_-3_23_1.jpg;
DefectList
 1 -1.0 2.0 4629.010 39554.104 -1 -3 5.2 3.9 20.28 5.2 23 3 1 0 2 2 0 1449 0 1 1 1 0;
"""


def test_sample_test_plan_derives_zero_offsets():
    """실측 SampleTestPlan(XINDEX -3~3, YINDEX -3~0)으로 zeroX=3, zeroY=3 계산.

    제품 설정값(zeroY=2)을 썼다면 YINDEX=-3 은 row=-1(음수)로 실패했을 die.
    """
    parsed = kla_info.parse_info_text(SAMPLE_TEST_PLAN_INFO)
    assert parsed.sample_zero == (3, 3)
    res = kla_info.convert_from_parsed(parsed, "W1_-1_-3_23_1.jpg")
    assert res.status == ParseStatus.OK
    assert res.col == 2   # -1 + 3
    assert res.row == 0   # -3 + 3


def test_sample_test_plan_absent_falls_back_to_config():
    """SampleTestPlan 이 없는 info 는 제품 설정값(zeroX=3, zeroY=2)으로 폴백."""
    parsed = kla_info.parse_info_text(SAMPLE_INFO)
    assert parsed.sample_zero is None
    res = kla_info.convert_from_parsed(parsed, "W5929249XYD6_0_1_23_2.jpg")
    assert res.status == ParseStatus.OK
    assert res.col == 3
    assert res.row == 3


def test_kla_class_zero_filename_reports_as_unclassified_candidate():
    """class=0(Unclassified) 파일명이 매칭 실패하면 파일명 없는 고정 사유를 반환.

    실측 확인: KLARF DefectList 에 등록되지 않은 미분류 후보 이미지가 흔함(정상).
    """
    text = (
        "FileVersion 1 2;\n"
        "DiePitch 3.7247898000e+004 4.4905301000e+004;\n"
        "TiffFileName W1_-2_0_14_1.jpg;\n"
        "DefectList\n"
        " 1 -1.0 2.0 100.0 200.0 -2 0 5.2 3.9 20.28 5.2 14 3 1 0 2 2 0 1449 0 1 1 1 0;\n"
    )
    parsed = kla_info.parse_info_text(text)
    res = kla_info.convert_from_parsed(parsed, "w1_2_1_0_10.jpg")
    assert res.status == ParseStatus.NOT_FOUND
    assert "미분류(class 0)" in res.reason
    assert "w1_2_1_0_10" not in res.reason


def test_multi_defect_block_without_tifffilename():
    """TiffFileName 없는 DefectList 블록에서 여러 결함이 all_defects 에 수집됨."""
    text = (
        "DiePitch 3.7247898000e+004 4.4905301000e+004;\n"
        "DefectList\n"
        " 1 -84303.0 5810.5 8652.7 5587.6 -2 0 10.4 7.8 81.3 5.2 23;\n"
        " 2 -50000.0 3000.0 4000.0 3000.0 0 -1 5.0 5.0 25.0 5.0 7;\n"
        " 3 -30000.0 2000.0 2000.0 1000.0 1 1 3.0 3.0 9.0 3.0 31;\n"
        "EndOfFile;\n"
    )
    parsed = kla_info.parse_info_text(text)
    assert len(parsed.defects) == 0
    assert len(parsed.all_defects) == 3
