"""git 이력에서 앱 버전을 결정적으로 계산한다(커밋 횟수·크기 반영).

규칙: 버전 = ``1.{MINOR}.{PATCH}``
  - MAJOR = 1 (수동 마일스톤)
  - MINOR = "큰 커밋" 수 = diff 변경 라인(추가+삭제)이 ``_BIG_COMMIT_LINES`` 이상인 커밋 수
            → 커밋 *크기* 를 반영(기능 단위 누적)
  - PATCH = 전체 커밋 수. 워킹트리에 커밋되지 않은 변경이 있으면 +1
            (지금 만들려는 커밋을 미리 반영 → 커밋 후 실제 커밋 수와 일치)

런타임이 아니라 **커밋 직전**에 실행해 ``app/__init__.py`` 의 ``__version__`` 을 갱신한다
(시작 속도에 영향 없음). CLAUDE.md 규칙으로 세션이 바뀌어도 매번 자동 반영된다.

사용:
  python tools/compute_version.py            # 계산된 버전 출력
  python tools/compute_version.py --write     # app/__init__.py 의 __version__ 갱신
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_INIT = _REPO / "app" / "__init__.py"
_BIG_COMMIT_LINES = 200  # 이 이상 변경된 커밋을 "큰 커밋"(MINOR 증가)으로 본다
_VERSION_RE = re.compile(r'^__version__\s*=\s*["\'][^"\']*["\']', re.MULTILINE)


def _git(*args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(_REPO), *args],
        capture_output=True, text=True, check=True, timeout=20,
    )
    return out.stdout


def _commit_count() -> int:
    try:
        return int(_git("rev-list", "--count", "HEAD").strip() or "0")
    except (subprocess.CalledProcessError, ValueError):
        return 0


def _working_tree_dirty() -> bool:
    try:
        return bool(_git("status", "--porcelain").strip())
    except subprocess.CalledProcessError:
        return False


def _big_commit_count() -> int:
    """diff 변경 라인이 임계 이상인 커밋 수를 센다(커밋 크기 반영)."""
    try:
        # 커밋 경계(--) + numstat. 바이너리는 '-'\t'-' 로 표기 → 0 으로 처리.
        text = _git("log", "--no-merges", "--numstat", "--format=%x00")
    except subprocess.CalledProcessError:
        return 0
    big = 0
    cur = 0
    started = False
    for line in text.splitlines():
        if line.startswith("\x00"):
            if started and cur >= _BIG_COMMIT_LINES:
                big += 1
            cur = 0
            started = True
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            add = parts[0].strip()
            rem = parts[1].strip()
            cur += (int(add) if add.isdigit() else 0) + (int(rem) if rem.isdigit() else 0)
    if started and cur >= _BIG_COMMIT_LINES:  # 마지막 커밋
        big += 1
    return big


def compute_parts() -> tuple[int, int, int]:
    """(major, minor, patch) 를 git 에서 계산한다."""
    patch = _commit_count() + (1 if _working_tree_dirty() else 0)
    minor = _big_commit_count()
    return 1, minor, patch


def compute_version() -> str:
    major, minor, patch = compute_parts()
    return f"{major}.{minor}.{patch}"


def write_version(version: str) -> bool:
    """app/__init__.py 의 __version__ 을 version 으로 치환한다(변경 시 True)."""
    text = _INIT.read_text(encoding="utf-8")
    new = _VERSION_RE.sub(f'__version__ = "{version}"', text, count=1)
    if new != text:
        _INIT.write_text(new, encoding="utf-8")
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="git 이력 기반 버전 계산")
    ap.add_argument("--write", action="store_true", help="app/__init__.py 의 __version__ 갱신")
    args = ap.parse_args(argv)
    version = compute_version()
    if args.write:
        changed = write_version(version)
        print(f"{version} ({'updated' if changed else 'unchanged'})")
    else:
        print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
