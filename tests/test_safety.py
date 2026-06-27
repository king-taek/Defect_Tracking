"""원본 보호 게이트 테스트 (문서 Section 1)."""

import pytest

from app.safety import OriginalProtectionError, assert_output_safe, is_within


def test_is_within_same_path(tmp_path):
    assert is_within(tmp_path, tmp_path)


def test_is_within_child(tmp_path):
    child = tmp_path / "sub" / "deep"
    assert is_within(child, tmp_path)


def test_is_within_sibling(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    assert not is_within(a, b)


def test_blocks_output_inside_source(tmp_path):
    source = tmp_path / "LOT"
    output = source / "exports" / "result.xlsx"
    with pytest.raises(OriginalProtectionError):
        assert_output_safe(output, [source])


def test_blocks_output_equal_source(tmp_path):
    source = tmp_path / "LOT"
    with pytest.raises(OriginalProtectionError):
        assert_output_safe(source, [source])


def test_allows_output_outside_source(tmp_path):
    source = tmp_path / "LOT"
    output = tmp_path / "workspace" / "result.xlsx"
    # 예외 없이 절대경로 반환
    result = assert_output_safe(output, [source])
    assert str(result).endswith("result.xlsx")


def test_allows_when_no_source_roots(tmp_path):
    output = tmp_path / "result.xlsx"
    assert assert_output_safe(output, []) is not None
