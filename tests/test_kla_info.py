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
    """문서 정답: W5929249XYD6_0_1_23_2.jpg -> 3_4_4629_5351"""
    parsed = kla_info.parse_info_text(SAMPLE_INFO)
    res = kla_info.convert_from_parsed(parsed, "W5929249XYD6_0_1_23_2.jpg")
    assert res.status == ParseStatus.OK
    assert res.col == 3
    assert res.row == 4
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


def test_select_info_file_prefers_001():
    files = [
        "00T3UB50XYF5_0_1_7_1.jpg",
        "uuid_TB500_00T3UB50XYF5.001",
        "uuid_TB500_00T3UB50XYF5.pass",
    ]
    assert kla_info.select_info_file(files) == "uuid_TB500_00T3UB50XYF5.001"


def test_select_info_file_ignores_pass_and_jpg():
    files = ["a.jpg", "b.pass"]
    assert kla_info.select_info_file(files) is None


def test_select_info_file_non_jpg_fallback():
    files = ["a.jpg", "b.pass", "info.txt"]
    assert kla_info.select_info_file(files) == "info.txt"
