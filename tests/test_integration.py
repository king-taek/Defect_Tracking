"""통합 테스트: 합성 데이터로 스캔→매칭→Excel 출력, 그리고 원본 무수정 보장.

Qt 없이 동작하는 핵심 파이프라인만 검증한다(UI 제외).
"""

from pathlib import Path

import pytest

from app import config, matcher, scanner
from app.export.excel_report import export_excel
from app.safety import OriginalProtectionError
from app.thumbnails import ThumbnailCache
from tools.make_sample_data import generate


def _snapshot(root: Path) -> dict[str, int]:
    """원본 트리의 (상대경로 -> 크기) 스냅샷. 무수정 검증용."""
    return {
        str(p.relative_to(root)): p.stat().st_size
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.fixture()
def lot(tmp_path) -> Path:
    src = tmp_path / "source"
    src.mkdir()
    return generate(src)


def test_scan_detects_all_sources(lot):
    idx = scanner.scan_lot(lot)
    assert set(idx.layer_canonicals()) == {"RDL4", "PI4", "RDL3", "PI3"}
    assert len(idx.wafers()) == 2
    sources = {r.source.value for r in idx.records}
    assert "Camtek(파일명)" in sources
    assert "Camtek(INI)" in sources
    assert "KLA" in sources
    # 합성 데이터는 모두 좌표 OK 여야 한다.
    assert all(r.ok for r in idx.records)


def test_matching_finds_cross_layer(lot):
    idx = scanner.scan_lot(lot)
    rbl = idx.records_by_layer()
    base = [r for r in idx.records_for_layer("RDL4") if r.ok]
    compare = ["PI4", "RDL3", "PI3"]
    results = matcher.match_all(base, compare, rbl, config.DEFAULT_TOLERANCE)
    total = len(results) * len(compare)
    hits = sum(1 for m in results for r in m.results if r.is_match)
    # 허용 오차 내 jitter 로 생성했으므로 전부 매칭되어야 한다.
    assert hits == total


def test_export_and_source_untouched(lot, tmp_path):
    before = _snapshot(lot)

    idx = scanner.scan_lot(lot)
    rbl = idx.records_by_layer()
    base = [r for r in idx.records_for_layer("RDL4") if r.ok]
    results = matcher.match_all(base, ["PI4", "RDL3"], rbl, config.DEFAULT_TOLERANCE)

    cache = ThumbnailCache(tmp_path / "ws" / "cache")
    out = export_excel(
        tmp_path / "ws" / "exports" / "r.xlsx",
        lot_name=idx.lot_name,
        base_layer="RDL4",
        compare_layers=["PI4", "RDL3"],
        tolerance=config.DEFAULT_TOLERANCE,
        selected=results[:3],
        thumb_cache=cache,
        source_roots=[lot],
    )
    assert out.exists() and out.stat().st_size > 0

    # 원본 트리는 한 글자도 바뀌면 안 된다.
    assert _snapshot(lot) == before


def test_export_with_notes(lot, tmp_path):
    idx = scanner.scan_lot(lot)
    rbl = idx.records_by_layer()
    base = [r for r in idx.records_for_layer("RDL4") if r.ok]
    results = matcher.match_all(base, ["PI4"], rbl, config.DEFAULT_TOLERANCE)
    cache = ThumbnailCache(tmp_path / "ws" / "cache")
    notes = {str(results[0].base.image_path): "재리뷰 요청"}
    out = export_excel(
        tmp_path / "ws" / "exports" / "n.xlsx",
        lot_name=idx.lot_name,
        base_layer="RDL4",
        compare_layers=["PI4"],
        tolerance=config.DEFAULT_TOLERANCE,
        selected=results[:2],
        thumb_cache=cache,
        source_roots=[lot],
        notes=notes,
    )
    assert out.exists() and out.stat().st_size > 0


def test_export_into_source_blocked(lot, tmp_path):
    idx = scanner.scan_lot(lot)
    rbl = idx.records_by_layer()
    base = [r for r in idx.records_for_layer("RDL4") if r.ok]
    results = matcher.match_all(base, ["PI4"], rbl, config.DEFAULT_TOLERANCE)
    cache = ThumbnailCache(tmp_path / "ws" / "cache")

    with pytest.raises(OriginalProtectionError):
        export_excel(
            lot / "leak.xlsx",  # 원본 내부 → 차단되어야 함
            lot_name=idx.lot_name,
            base_layer="RDL4",
            compare_layers=["PI4"],
            tolerance=config.DEFAULT_TOLERANCE,
            selected=results[:1],
            thumb_cache=cache,
            source_roots=[lot],
        )
    assert not (lot / "leak.xlsx").exists()


def test_rereview_layers_kept_distinct(tmp_path):
    """같은 canonical 의 일반/재리뷰 폴더가 둘 다 별도 layer 로 보여야 한다(충돌 시 구분)."""
    lot = tmp_path / "204. TB500"
    # 같은 canonical(RDL4) 의 일반 + 재리뷰 폴더, 그리고 충돌 없는 PI4
    (lot / "1. RDL4" / "W1").mkdir(parents=True)
    (lot / "2. RDL4_재리뷰" / "W1").mkdir(parents=True)
    (lot / "3. PI4" / "W1").mkdir(parents=True)
    # 각 wafer 폴더에 좌표가 파일명에 있는 Camtek 이미지 1장씩
    for folder in ("1. RDL4", "2. RDL4_재리뷰", "3. PI4"):
        img = lot / folder / "W1" / "R_TB500_LIVE_X_WLW_X_W1_4_5_1000.000000_2000.000000_Defect.jpg"
        img.write_bytes(b"\xff\xd8\xff\xd9")  # 최소 JPEG 바이트(좌표는 파일명에서 추출)

    idx = scanner.scan_lot(lot)
    names = idx.layer_canonicals()
    # 충돌난 RDL4 는 일반/재리뷰로 구분, 충돌 없는 PI4 는 그대로
    assert "RDL4" in names
    assert "RDL4_재리뷰" in names
    assert "PI4" in names
    # records 도 섞이지 않고 각 display 로 분리
    rbl = idx.records_by_layer()
    assert rbl["RDL4"] and all(r.layer == "RDL4" for r in rbl["RDL4"])
    assert rbl["RDL4_재리뷰"] and all(r.layer == "RDL4_재리뷰" for r in rbl["RDL4_재리뷰"])


def test_sample_data_is_deterministic(tmp_path):
    a = generate(tmp_path / "a")
    b = generate(tmp_path / "b")
    names_a = sorted(p.name for p in a.rglob("*.jpg"))
    names_b = sorted(p.name for p in b.rglob("*.jpg"))
    assert names_a == names_b
