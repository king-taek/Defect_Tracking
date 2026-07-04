"""Phase 1 인프라 테스트: 원자적 설정 저장, 손상 복구, 스캔 오류 표면화, 로깅."""

from __future__ import annotations

import json
from pathlib import Path

from app import scanner
from app.config import AppSettings


def test_settings_atomic_save_roundtrip(tmp_path):
    s = AppSettings(workspace=str(tmp_path / "ws"))
    s.tolerance = 137.0
    s.base_layer = "LYA4"
    s.compare_layers = ["LYB4", "LYA3"]
    s.save()
    # 임시파일이 남지 않아야 한다(원자적 교체).
    assert not (s.workspace_path / "settings.json.tmp").exists()
    loaded = AppSettings.load(s.workspace_path)
    assert loaded.tolerance == 137.0
    assert loaded.base_layer == "LYA4"
    assert loaded.compare_layers == ["LYB4", "LYA3"]


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


def test_session_store_roundtrip(tmp_path):
    from app.session import SessionStore

    s = SessionStore.load(tmp_path / "ws", "204. DEVA (PKG)")
    key = "/src/LYA4/W1/img.jpg"
    assert s.is_marked(key) is False
    assert s.toggle_mark(key) is True
    s.set_note(key, "재확인 필요")
    s.save()

    again = SessionStore.load(tmp_path / "ws", "204. DEVA (PKG)")
    assert again.is_marked(key) is True
    assert again.note(key) == "재확인 필요"
    assert again.notes_map() == {key: "재확인 필요"}
    # 마킹 해제 + 메모 삭제 시 항목이 정리된다
    again.toggle_mark(key)
    again.set_note(key, "")
    assert key not in again.marks


def test_classify_selection_levels(tmp_path):
    # DEVICE/MAT/LAYER/WAFER/a.jpg  — 각 레벨 선택 시 분류
    img = tmp_path / "DEVICE" / "MAT" / "LAYER" / "WAFER" / "a.jpg"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"\xff\xd8\xff\xd9")
    mat = tmp_path / "DEVICE" / "MAT"

    assert scanner.classify_selection(mat) == ("material", mat)
    assert scanner.classify_selection(mat / "LAYER") == ("layer", mat)
    assert scanner.classify_selection(mat / "LAYER" / "WAFER") == ("wafer", mat)
    kind, _ = scanner.classify_selection(tmp_path / "DEVICE")
    assert kind == "too_high"
    (tmp_path / "EMPTY").mkdir()
    assert scanner.classify_selection(tmp_path / "EMPTY") == ("unknown", None)


def test_product_profiles_default_and_switch():
    from app import config
    from app.config import ProductConfig

    assert config.active_product().key == config.DEFAULT_PRODUCT
    assert config.kla_zero_x() == config.active_product().kla_package_x_count // 2
    # 하위호환 상수는 기본 제품 값과 일치해야 한다(샘플데이터/기존 테스트).
    assert config.CAMTEK_COL_OFFSET == config.active_product().camtek_col_offset

    config.PRODUCTS["TESTPROD"] = ProductConfig(
        key="TESTPROD", name="Test", camtek_pitch_x=1.0, camtek_pitch_y=2.0,
        camtek_col_offset=0, camtek_row_base=5, kla_package_x_count=9,
        kla_package_y_count=9,
    )
    try:
        config.set_active_product("TESTPROD")
        assert config.active_product().name == "Test"
        assert config.kla_zero_x() == 4
    finally:
        config.set_active_product(config.DEFAULT_PRODUCT)
        config.PRODUCTS.pop("TESTPROD", None)


def test_setup_logging_idempotent(tmp_path):
    from app import logging_config

    log_dir = tmp_path / "ws" / "logs"
    logger = logging_config.setup_logging(log_dir)
    n = len(logger.handlers)
    logging_config.setup_logging(log_dir)  # 두 번째 호출
    assert len(logger.handlers) == n  # 핸들러 중복 추가 안 됨
    assert (log_dir / "conder.log").exists()


def test_log_dir_path_falls_back_to_workspace_logs(tmp_path):
    s = AppSettings(workspace=str(tmp_path / "ws"), log_dir="")
    assert s.log_dir_path == tmp_path / "ws" / "logs"


def test_log_dir_path_uses_explicit_setting(tmp_path):
    custom = tmp_path / "custom-log"
    s = AppSettings(workspace=str(tmp_path / "ws"), log_dir=str(custom))
    assert s.log_dir_path == custom


def test_default_log_dir_empty_on_non_windows():
    from app import config

    if config.os.name != "nt":
        assert config.default_log_dir() == ""
