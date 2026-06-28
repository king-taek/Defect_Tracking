"""중단(취소)·버전 계산·최대화 설정 단위 테스트."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import compute_version


def test_scan_lot_cancel_check_stops_early(tmp_path):
    from app import scanner

    # layer/wafer/이미지 트리를 여러 개 만든다.
    for li in range(3):
        for wi in range(3):
            d = tmp_path / f"{li}. LAYER{li}" / f"W{wi}"
            d.mkdir(parents=True)
            (d / "img.jpg").write_bytes(b"\xff\xd8\xff\xd9")

    # 즉시 취소 → 레코드 누적이 멈춘다(부분/0 결과).
    idx = scanner.scan_lot(tmp_path, cancel_check=lambda: True)
    assert len(idx.records) == 0
    # 취소 없이는 모든 이미지가 스캔된다(대조).
    idx2 = scanner.scan_lot(tmp_path, cancel_check=lambda: False)
    assert len(idx2.records) == 9


def test_compute_version_format():
    major, minor, patch = compute_version.compute_parts()
    assert major == 1
    assert minor >= 0 and patch >= 1
    v = compute_version.compute_version()
    assert v == f"1.{minor}.{patch}"
    # 정규식 치환이 가능한 형식인지(따옴표 포함) 간단 확인
    assert v.count(".") == 2


def test_compute_version_write(tmp_path, monkeypatch):
    # 임시 __init__.py 에 대해 write_version 이 __version__ 줄만 바꾸는지 확인
    fake = tmp_path / "__init__.py"
    fake.write_text('"""doc."""\n\n__version__ = "0.0.0"\n', encoding="utf-8")
    monkeypatch.setattr(compute_version, "_INIT", fake)
    assert compute_version.write_version("1.2.3") is True
    assert '__version__ = "1.2.3"' in fake.read_text(encoding="utf-8")
    # 동일 값으로 다시 쓰면 변경 없음
    assert compute_version.write_version("1.2.3") is False


def test_window_maximized_default():
    from app.config import AppSettings

    s = AppSettings(workspace="/tmp/x")
    assert s.window_maximized is True  # 기본 최대화
