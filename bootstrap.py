"""의존성 점검·설치 스크립트.

프로그램 실행에 필요한 라이브러리가 설치되어 있는지 확인하고, 없으면 자동으로 설치한다.
표준 라이브러리만 사용하므로 별도 설치 없이 바로 실행할 수 있다.

사용:
    python bootstrap.py            # 누락된 의존성 설치
    python bootstrap.py --check    # 점검만 하고 설치하지 않음

설치 후:
    python main.py
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

# import 이름 -> requirements 표기(설치 이름/버전)
REQUIRED: dict[str, str] = {
    "PySide6": "PySide6>=6.6",
    "PIL": "Pillow>=10.0",
    "openpyxl": "openpyxl>=3.1",
}

ROOT = Path(__file__).resolve().parent
REQUIREMENTS_FILE = ROOT / "requirements.txt"


def missing_modules() -> list[str]:
    """설치되지 않은 import 이름 목록을 반환."""
    missing = []
    for import_name in REQUIRED:
        if importlib.util.find_spec(import_name) is None:
            missing.append(import_name)
    return missing


def _pip_install(args: list[str]) -> int:
    cmd = [sys.executable, "-m", "pip", "install", *args]
    print("실행:", " ".join(cmd))
    return subprocess.call(cmd)


def install_missing(missing: list[str]) -> int:
    """누락 패키지를 설치. requirements.txt 가 있으면 그것을 우선 사용."""
    if not missing:
        return 0
    if REQUIREMENTS_FILE.exists():
        rc = _pip_install(["-r", str(REQUIREMENTS_FILE)])
    else:
        rc = _pip_install([REQUIRED[m] for m in missing])
    return rc


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    check_only = "--check" in argv

    print(f"Python: {sys.version.split()[0]}  ({sys.executable})")
    missing = missing_modules()

    if not missing:
        print("✓ 모든 의존성이 충족되었습니다. `python main.py` 로 실행하세요.")
        return 0

    print("누락된 라이브러리:", ", ".join(REQUIRED[m] for m in missing))
    if check_only:
        print("`python bootstrap.py` 를 실행하면 자동 설치합니다.")
        return 1

    rc = install_missing(missing)
    if rc != 0:
        print("✗ 설치 중 오류가 발생했습니다. 네트워크/권한을 확인하세요.")
        return rc

    still = missing_modules()
    if still:
        print("✗ 다음 라이브러리가 여전히 누락되었습니다:", ", ".join(still))
        return 1

    print("✓ 설치 완료. `python main.py` 로 실행하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
