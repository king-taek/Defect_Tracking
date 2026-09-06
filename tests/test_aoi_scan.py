"""AOI 모드 스캔(scanner.scan_aoi) — 수동 layer 지정 폴더에서 LotIndex 를 만든다."""

from __future__ import annotations

from pathlib import Path

from app import aoi, scanner
from app.models import ParseStatus, Source
from app.scanner import AoiLayer

_JPEG = b"\xff\xd8\xff\xd9"
_LIVE = "TB500_RDL4 - Multi_FDV-RDL4_W7548304XYG4_{col}_{row}_{x}_{y}_Irregular Bump.jpg"


def _slot(root: Path, slot: str, names: list[str]) -> Path:
    d = root / slot
    d.mkdir(parents=True)
    for n in names:
        (d / n).write_bytes(_JPEG)
    return d


def test_scan_aoi_builds_index_from_named_layers(tmp_path):
    a, b = tmp_path / "eq1" / "result", tmp_path / "eq2" / "out"
    _slot(a, "Slot01", [_LIVE.format(col=5, row=4, x="31863.2", y="26908.4")])
    _slot(b, "Slot01", [_LIVE.format(col=5, row=4, x="31870.0", y="26900.0"), "unknown.jpg"])
    _slot(b, "Slot02", [_LIVE.format(col=1, row=1, x="10.0", y="20.0")])

    msgs: list[str] = []
    idx = scanner.scan_aoi(
        [AoiLayer("LYA4", a), AoiLayer("LYB4", b)],
        progress=lambda m, c, t: msgs.append(m),
    )
    assert idx.aoi_mode is True
    assert idx.layer_canonicals() == ["LYA4", "LYB4"]
    assert [lyr.path for lyr in idx.layers] == [a, b]
    assert set(idx.source_roots) == {a, b}
    assert idx.wafers() == ["Slot01", "Slot02"]

    ok = [r for r in idx.records if r.ok]
    assert len(ok) == 3 and all(r.source == Source.AOI_CAMTEK_LIVE for r in ok)
    first = idx.records_for_layer("LYA4")[0]
    assert (first.col, first.row, first.x, first.y) == (5, 4, 31863.2, 26908.4)
    assert first.defect_name == "Irregular Bump"
    assert first.layer_folder == "result"

    failed = [r for r in idx.records if not r.ok]
    assert len(failed) == 1 and failed[0].status == ParseStatus.NOT_FOUND
    assert failed[0].source == Source.UNKNOWN and "AOI" in failed[0].note
    assert msgs[-1] == "스캔 완료" and any("LYB4/Slot02" in m for m in msgs)


def test_scan_aoi_accepts_single_wafer_folder_and_missing_folder(tmp_path):
    single = _slot(tmp_path, "W7548304XYG4", [_LIVE.format(col=2, row=3, x="1.0", y="2.0")])
    idx = scanner.scan_aoi([AoiLayer("A", single), AoiLayer("B", tmp_path / "nope")])
    assert idx.records[0].wafer_id == "W7548304XYG4"
    assert len(idx.records) == 1
    assert idx.scan_errors and "nope" in idx.scan_errors[0]


def test_scan_aoi_cancel_stops_early(tmp_path):
    for i in range(3):
        _slot(tmp_path / "L", f"Slot0{i}", [_LIVE.format(col=1, row=1, x="1", y="2")])
    calls = {"n": 0}

    def cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    idx = scanner.scan_aoi([AoiLayer("L", tmp_path / "L")], cancel_check=cancel)
    assert len(idx.records) < 3


def test_scan_aoi_clears_coord_caches(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(aoi, "clear_caches", lambda: called.append(True))
    scanner.scan_aoi([])
    assert called
