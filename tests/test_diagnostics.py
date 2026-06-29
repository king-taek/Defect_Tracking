"""파서 reason 필드 + 진단 리포트(단일 md) 단위 테스트."""

from __future__ import annotations

from pathlib import Path

from app import diagnostics
from app.models import DefectRecord, ParseStatus, Source
from app.parsers import camtek_filename, kla_info


def _rec(status, note="", layer="1. RDL4", wafer="W1", name="a.jpg"):
    return DefectRecord(
        image_path=Path(f"/{layer}/{wafer}/{name}"),
        wafer_id=wafer, layer="RDL4", layer_folder=layer,
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
    ok = DefectRecord(image_path=Path("/x/c.jpg"), wafer_id="W1", layer="RDL4",
                      layer_folder="1. RDL4", status=ParseStatus.OK, col=1, row=1, x=0.0, y=0.0)
    recs.append(ok)
    out = diagnostics.write_parse_failure_report(tmp_path, "LOT1", recs, ["/net/x: PermissionError"])
    assert out == tmp_path / "logs" / "parse_failures.md"
    text = out.read_text(encoding="utf-8")
    assert "(2개)" in text
    assert "KLA 원본" in text
    assert "PermissionError" in text
    assert "실패: **2개**" in text

    # 두 번째 스캔 — 누적 추가되어 이전 내용도 보존
    out2 = diagnostics.write_parse_failure_report(tmp_path, "LOT1", [ok])
    assert out2 == out
    text2 = out2.read_text(encoding="utf-8")
    assert "실패가 없습니다" in text2
    assert "(2개)" in text2  # 이전 리포트 내용이 남아 있어야 함
    assert "스캔 시각:" in text2


def test_report_no_failures(tmp_path):
    ok = DefectRecord(image_path=Path("/x/c.jpg"), wafer_id="W1", layer="RDL4",
                      layer_folder="1. RDL4", status=ParseStatus.OK, col=1, row=1, x=0.0, y=0.0)
    out = diagnostics.write_parse_failure_report(tmp_path, "LOT", [ok])
    assert "실패가 없습니다" in out.read_text(encoding="utf-8")
