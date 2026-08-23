"""PyInstaller onefile 빌드 스크립트 (Windows 대상).

대상 환경이 Windows 네트워크 경로이므로 Windows 에서 실행하는 것을 권장한다.

사용 (Windows):
    pip install -r requirements.txt pyinstaller
    python build_exe.py

산출물: dist/Defect Tracker.exe

주의: 이 빌드는 GUI 동작에 PySide6 런타임을 포함한다. 좌표 변환/매칭/원본 보호 로직은
빌드와 무관하게 동일하게 동작한다.
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    # 번들 디바이스 DB 를 함께 포함(런타임에 config.bundled_device_db_path 가 찾음).
    # Windows 는 add-data 구분자로 ';', 그 외는 ':' 를 쓴다.
    sep = ";" if os.name == "nt" else ":"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "Defect Tracker",
        "--add-data",
        f"data{os.sep}AOIDeviceDB.xlsx{sep}data",
        # qfluentwidgets 는 스타일시트·아이콘·폰트를 Qt 리소스가 아니라 패키지 안의 데이터
        # 파일로 들고 있다. 자동 분석은 그것들을 못 찾아서, 빌드는 되고 실행하면 스타일이
        # 전부 빠진 채 뜬다. 프레임리스 창 껍데기(qframelesswindow)도 같은 이유다.
        "--collect-all",
        "qfluentwidgets",
        "--collect-all",
        "qframelesswindow",
        "main.py",
    ]
    print("실행:", " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
