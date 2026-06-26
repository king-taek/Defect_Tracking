"""원본 보호 게이트 (문서 Section 1 — 절대 안전 규칙).

본 프로그램의 최우선 원칙은 원본 데이터 훼손 방지이다. 모든 쓰기/캐시/Excel 경로는
반드시 이 모듈의 게이트를 통과해야 한다.

2중 보호:
  1차(로직) : 소스(LOT) 경로에 대해서는 write/delete/move/rename 을 절대 호출하지 않는다.
              이미지/INI/info 파일은 read_bytes()/open('rb') 읽기 전용으로만 접근한다.
  2차(경로) : 출력 경로가 어떤 소스 루트와 같거나 그 하위면 저장을 차단한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


class OriginalProtectionError(Exception):
    """원본 보호 규칙 위반 시 발생. 저장/쓰기를 차단한다."""


def _resolve(path: str | Path) -> Path:
    """심볼릭 링크/상대경로/대소문자 차이를 흡수해 비교 가능한 절대경로로 변환.

    네트워크 경로(UNC)나 존재하지 않는 출력 경로도 다룰 수 있어야 하므로
    strict=False 로 resolve 한다.
    """
    try:
        return Path(path).resolve(strict=False)
    except (OSError, RuntimeError):
        return Path(path).absolute()


def is_within(child: str | Path, parent: str | Path) -> bool:
    """child 가 parent 와 같거나 그 하위 경로이면 True."""
    c = _resolve(child)
    p = _resolve(parent)
    if c == p:
        return True
    try:
        c.relative_to(p)
        return True
    except ValueError:
        return False


def assert_output_safe(
    output_path: str | Path,
    source_roots: Iterable[str | Path],
) -> Path:
    """출력 경로가 어떤 소스 루트와 같거나 하위이면 차단한다 (2차 보호).

    Section 1.1: "원본 경로와 출력 경로가 같거나, 출력 경로가 원본 경로 하위이면 저장을 차단한다."

    Returns:
        검증을 통과한 절대 출력 경로.

    Raises:
        OriginalProtectionError: 출력 경로가 원본 폴더 내부일 때.
    """
    out = _resolve(output_path)
    for root in source_roots:
        if not str(root):
            continue
        if is_within(out, root):
            raise OriginalProtectionError(
                "출력 경로가 원본(LOT) 폴더 내부이거나 동일합니다. "
                "원본 보호 규칙에 따라 저장을 차단했습니다.\n"
                f"  출력 경로 : {out}\n"
                f"  원본 경로 : {_resolve(root)}\n"
                "원본 폴더 밖의 다른 폴더를 선택하세요."
            )
    return out


def safe_makedirs(target_dir: str | Path, source_roots: Iterable[str | Path]) -> Path:
    """출력 디렉터리를 만들되, 원본 내부면 차단한다."""
    out = assert_output_safe(target_dir, source_roots)
    out.mkdir(parents=True, exist_ok=True)
    return out


def read_only_bytes(path: str | Path) -> bytes:
    """원본 파일을 읽기 전용으로만 읽는다 (1차 보호).

    명시적으로 'rb' 모드만 사용하여 원본 수정 가능성을 원천 차단한다.
    """
    with open(path, "rb") as fh:
        return fh.read()
