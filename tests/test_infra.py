"""Phase 1 인프라 테스트: 원자적 설정 저장, 손상 복구, 스캔 오류 표면화, 로깅."""

from __future__ import annotations

import json
from pathlib import Path

from app import scanner
from app.config import AppSettings


def test_settings_atomic_save_roundtrip(tmp_path):
    s = AppSettings(workspace=str(tmp_path / "ws"))
    s.tolerance = 137.0
    s.base_layer = "RDL4"
    s.compare_layers = ["PI4", "RDL3"]
    s.save()
    # 임시파일이 남지 않아야 한다(원자적 교체).
    assert not (s.workspace_path / "settings.json.tmp").exists()
    loaded = AppSettings.load(s.workspace_path)
    assert loaded.tolerance == 137.0
    assert loaded.base_layer == "RDL4"
    assert loaded.compare_layers == ["PI4", "RDL3"]


def test_settings_load_corrupted_returns_defaults(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "settings.json").write_text("{ not valid json ", encoding="utf-8")
    loaded = AppSettings.load(ws)
    assert loaded.workspace == str(ws)
    assert loaded.tolerance == AppSettings().tolerance  # 기본값 복구


def test_settings_save_overwrites_atomically(tmp_path):
    s = AppSettings(workspace=str(tmp_path / "ws"))
    s.save()
    s.tolerance = 999.0
    s.save()
    raw = json.loads((s.workspace_path / "settings.json").read_text(encoding="utf-8"))
    assert raw["tolerance"] == 999.0


def test_list_dirs_records_access_error():
    with scanner._scan_errors_lock:
        scanner._scan_errors.clear()
    result = scanner._list_dirs(Path("/this/path/does/not/exist/xyz"))
    assert result == []
    with scanner._scan_errors_lock:
        assert any("xyz" in e for e in scanner._scan_errors)


def test_scan_lot_clean_has_no_errors(tmp_path):
    from tools.make_sample_data import generate

    lot = generate(tmp_path / "src")
    idx = scanner.scan_lot(lot)
    assert idx.scan_errors == []
    assert hasattr(idx, "scan_errors")


def test_parallel_scan_is_deterministic(tmp_path):
    from tools.make_sample_data import generate

    lot = generate(tmp_path / "src")
    a = scanner.scan_lot(lot)
    b = scanner.scan_lot(lot)
    # 병렬 스캔이어도 record 순서/내용이 결정적이어야 한다.
    seq_a = [(r.layer, r.wafer_id, r.image_path.name) for r in a.records]
    seq_b = [(r.layer, r.wafer_id, r.image_path.name) for r in b.records]
    assert seq_a == seq_b
    # layer 는 폴더 순서, 그 안에서 (wafer, 파일명) 정렬이 유지된다.
    for i in range(1, len(seq_a)):
        # 같은 (layer, wafer) 그룹 내에서는 파일명이 비내림차순
        if seq_a[i][:2] == seq_a[i - 1][:2]:
            assert seq_a[i][2] >= seq_a[i - 1][2]


def test_setup_logging_idempotent(tmp_path):
    from app import logging_config

    logger = logging_config.setup_logging(tmp_path / "ws")
    n = len(logger.handlers)
    logging_config.setup_logging(tmp_path / "ws")  # 두 번째 호출
    assert len(logger.handlers) == n  # 핸들러 중복 추가 안 됨
    assert (tmp_path / "ws" / "logs" / "conder.log").exists()
