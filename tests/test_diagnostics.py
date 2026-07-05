"""파서 reason 필드 + 진단 리포트(단일 md) 단위 테스트."""

from __future__ import annotations

from pathlib import Path

from app import diagnostics
from app.models import DefectRecord, ParseStatus, Source
from app.parsers import camtek_filename, kla_info


def _rec(status, note="", layer="1. LYA4", wafer="W1", name="a.jpg"):
    return DefectRecord(
        image_path=Path(f"/{layer}/{wafer}/{name}"),
        wafer_id=wafer, layer="LYA4", layer_folder=layer,
        source=Source.UNKNOWN, status=status, note=note,
    )


def test_parser_reason_filled():
    # KLA 원본형 파일명(이름 토큰 없음) → reason 에 KLA 원본 언급
    r = camtek_filename.parse_camtek_filename("wafer_0_1_7_1.jpg")
    assert r.status == ParseStatus.NOT_FOUND
    assert "KLA" in r.reason or "정수" in r.reason


def test_report_append_accumulates(tmp_path):
    recs = [
        _rec(ParseStatus.NOT_FOUND, note="파일명: col/row 뒤 defect 이름(영문자) 토큰 없음 → KLA 원본"),
        _rec(ParseStatus.NOT_FOUND, note="파일명: col/row 뒤 defect 이름(영문자) 토큰 없음 → KLA 원본", name="b.jpg"),
    ]
    ok = DefectRecord(image_path=Path("/x/c.jpg"), wafer_id="W1", layer="LYA4",
                      layer_folder="1. LYA4", status=ParseStatus.OK, col=1, row=1, x=0.0, y=0.0)
    recs.append(ok)
    log_dir = tmp_path / "logs"
    out = diagnostics.write_parse_failure_report(log_dir, "LOT1", recs, ["/net/x: PermissionError"])
    assert out == log_dir / "parse_failures.md"
    text = out.read_text(encoding="utf-8")
    assert "(2개)" in text
    assert "KLA 원본" in text
    assert "PermissionError" in text
    assert "실패: **2개**" in text

    # 두 번째 스캔 — 누적 추가되어 이전 내용도 보존
    out2 = diagnostics.write_parse_failure_report(log_dir, "LOT1", [ok])
    assert out2 == out
    text2 = out2.read_text(encoding="utf-8")
    assert "실패가 없습니다" in text2
    assert "(2개)" in text2  # 이전 리포트 내용이 남아 있어야 함
    assert "스캔 시각:" in text2


def test_report_no_failures(tmp_path):
    ok = DefectRecord(image_path=Path("/x/c.jpg"), wafer_id="W1", layer="LYA4",
                      layer_folder="1. LYA4", status=ParseStatus.OK, col=1, row=1, x=0.0, y=0.0)
    out = diagnostics.write_parse_failure_report(tmp_path / "logs", "LOT", [ok])
    assert "실패가 없습니다" in out.read_text(encoding="utf-8")


def test_report_separates_unclassified(tmp_path):
    """미분류(class 0) 후보는 '실패' 카운트/원인 클러스터에서 빠지고 별도 섹션으로 표기."""
    unclassified = [
        _rec(ParseStatus.NOT_FOUND,
             note="KLA: 미분류(class 0) 후보 이미지 — info DefectList 에 정식 결함으로 등록되지 않음(정상, 무시 가능)",
             name="w_-2_0_0_26.jpg"),
        _rec(ParseStatus.NOT_FOUND,
             note="KLA: 미분류(class 0) 후보 이미지 — info DefectList 에 정식 결함으로 등록되지 않음(정상, 무시 가능)",
             name="w_0_0_0_21.jpg"),
    ]
    real = _rec(ParseStatus.NOT_FOUND,
                note="info 에 TiffFileName 'x.jpg' 매칭 실패(보유 6개)", name="w_0_-2_23_82.jpg")
    ok = DefectRecord(image_path=Path("/x/c.jpg"), wafer_id="W1", layer="LYA4",
                      layer_folder="1. LYA4", status=ParseStatus.OK, col=1, row=1, x=0.0, y=0.0)
    text = diagnostics.build_failure_report("LOT", unclassified + [real, ok])
    # 미분류는 별도 섹션 + '무시 가능' 카운트, 실패는 real 1개만.
    assert "미분류(class 0) 후보: **2개**" in text
    assert "미분류(class 0) 후보 — 무시 가능 (2개)" in text
    assert "- 실패: **1개**" in text
    # 실패 원인 클러스터엔 미분류가 안 들어가고 진짜 실패만.
    assert "TiffFileName" in text
    assert "미분류(class 0) 후보 이미지 — info DefectList" not in text.split("## 실패 원인 클러스터")[1]


def test_report_only_unclassified_is_not_failure(tmp_path):
    """미분류만 있으면 '확인 필요 실패 없음'으로 안내한다."""
    recs = [_rec(ParseStatus.NOT_FOUND,
                 note="KLA: 미분류(class 0) 후보 이미지 — info DefectList 에 정식 결함으로 등록되지 않음(정상)",
                 name="w_1_0_0_5.jpg")]
    text = diagnostics.build_failure_report("LOT", recs)
    assert "- 실패: **0개**" in text
    assert "확인이 필요한 실패는 없습니다" in text


def test_report_rotates_at_25mb(tmp_path):
    """로그 파일이 25MB를 넘으면 다음 번호 파일로 이어 쓴다."""
    logs = tmp_path / "logs"
    logs.mkdir()
    base = logs / "parse_failures.md"
    base.write_bytes(b"x" * (26 * 1024 * 1024))  # 26MB 더미

    ok = DefectRecord(image_path=Path("/x/c.jpg"), wafer_id="W1", layer="LYA4",
                      layer_folder="1. LYA4", status=ParseStatus.OK, col=1, row=1, x=0.0, y=0.0)
    out = diagnostics.write_parse_failure_report(logs, "LOT", [ok])
    assert out == logs / "parse_failures_2.md"
    assert "실패가 없습니다" in out.read_text(encoding="utf-8")
