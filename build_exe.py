"""PyInstaller onefile 빌드 스크립트 (Windows 대상).

대상 환경이 Windows 네트워크 경로이므로 Windows 에서 실행하는 것을 권장한다.

사용 (Windows):
    pip install -r requirements.txt pyinstaller
    python build_exe.py

산출물: dist/ConderCompare.exe

주의: 이 빌드는 GUI 동작에 PySide6 런타임을 포함한다. 좌표 변환/매칭/원본 보호 로직은
빌드와 무관하게 동일하게 동작한다.
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "ConderCompare",
        "main.py",
    ]
    print("실행:", " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
