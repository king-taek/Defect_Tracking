"""단일 파일 생성기(`tools/build_single_file.py`)의 최신성·동등성 회귀 테스트.

- 생성 산출물이 컴파일되고 importlib 로 로드되는지(이벤트 루프는 돌지 않음).
- 모듈식 소스와 동작이 일치하는지(버전·PRODUCTS·matcher·충돌 리네임 보존).
- 오프스크린 MainWindow 스모크(평문화된 UI 트리 전체가 구성되는지).
- 커밋된 산출물이 재생성 결과와 바이트 동일한지(표류 방지 게이트).
"""

import dataclasses
import importlib.util
import os
import py_compile
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tools import build_single_file as bsf  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _load_single_file(tmp_path) -> object:
    """생성 → 임시 파일 기록 → importlib 로 로드(main() 은 __main__ 이 아니라 미실행)."""
    text = bsf.build()
    out = tmp_path / "defect_tracker.py"
    out.write_text(text, encoding="utf-8")
    py_compile.compile(str(out), doraise=True)
    spec = importlib.util.spec_from_file_location("defect_tracker_single", out)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass 가 자기 모듈을 sys.modules 에서 찾음
    spec.loader.exec_module(mod)
    return mod


def test_generated_compiles_and_imports(tmp_path):
    mod = _load_single_file(tmp_path)
    import app

    assert mod.__version__ == app.__version__


def test_config_parity(tmp_path):
    mod = _load_single_file(tmp_path)
    from app import config

    def norm(products):
        return {k: dataclasses.asdict(v) for k, v in products.items()}

    # 서로 다른 클래스라 == 는 못 쓰고 값으로 비교(네임스페이스 elision 정확성 확인)
    assert set(mod.PRODUCTS) == set(config.PRODUCTS)
    assert norm(mod.PRODUCTS) == norm(config.PRODUCTS)


def test_collision_rename_preserved(tmp_path):
    mod = _load_single_file(tmp_path)

    # 6개 모듈의 _log 로거 이름이 각각 보존됐는지(충돌로 사라지지 않았는지)
    assert mod.scanner__log.name == "defect_tracker.scanner"
    assert mod.workers__log.name == "defect_tracker.workers"
    assert mod.device_db__log.name == "defect_tracker.device_db"
    assert mod.session__log.name == "defect_tracker.session"
    assert mod.camtek_ini__log.name == "defect_tracker.parsers.ini"
    assert mod.kla_info__log.name == "defect_tracker.parsers.kla"

    # 값이 서로 다른 충돌 상수들이 각기 보존됐는지
    assert (mod.export_dialog__COLUMNS, mod.nomatch_gallery__COLUMNS) == (3, 4)
    assert (mod.export_dialog__THUMB_PX, mod.heatmap_dialog__THUMB_PX) == (180, 150)
    assert mod.folder_picker__NUM_RE.pattern != mod.camtek_filename__NUM_RE.pattern


def test_matcher_behavior_parity(tmp_path):
    """단일 파일의 matcher 가 모듈식과 동일한 매칭 결과를 내는지(elision + 병합 무결성)."""
    mod = _load_single_file(tmp_path)
    from app.matcher import match_base_against_layers as ref
    from app.models import DefectRecord, ParseStatus, Source

    def rec(layer, x, y):
        return DefectRecord(
            image_path=Path(f"/src/{layer}/W1/img.jpg"),
            wafer_id="W1", layer=layer, layer_folder=layer,
            source=Source.CAMTEK_FILENAME, status=ParseStatus.OK,
            col=4, row=5, x=x, y=y,
        )

    base = rec("LYA4", 1000.0, 2000.0)
    cmp = rec("LYB4", 1050.0, 2000.0)  # 거리 50 (matcher 는 duck-typing 이라 app 레코드 그대로 사용)
    ours = mod.match_base_against_layers(base, ["LYB4"], {"LYB4": [cmp]}, tolerance=100.0).for_layer("LYB4")
    theirs = ref(base, ["LYB4"], {"LYB4": [cmp]}, tolerance=100.0).for_layer("LYB4")
    assert ours.is_match == theirs.is_match is True
    assert abs(ours.distance - theirs.distance) < 1e-9


def test_mainwindow_smoke(tmp_path):
    """평문화된 UI 트리 전체가 import·구성되는지(오프스크린)."""
    mod = _load_single_file(tmp_path)
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    settings = mod.AppSettings()
    win = mod.MainWindow(settings)
    win.show_initial()
    win.close()
    win.deleteLater()
    app.processEvents()


def test_committed_artifact_not_stale():
    """커밋된 단일 파일이 재생성 결과와 바이트 동일해야 함(표류 방지)."""
    committed = bsf.DEFAULT_OUT
    assert committed.exists(), "산출물 미존재 — `python tools/build_single_file.py` 실행 후 커밋"
    fresh = bsf.build()
    assert committed.read_text(encoding="utf-8") == fresh, (
        "단일 파일이 stale 함 — `python tools/build_single_file.py` 재생성 후 커밋하세요."
    )
