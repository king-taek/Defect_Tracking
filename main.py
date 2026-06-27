"""Conder Scan Review Image Compare Viewer — 진입점.

원본 데이터를 절대 훼손하지 않는(read-only) defect 이미지 비교 뷰어.
실행: python main.py

필요 라이브러리가 없으면 GUI 를 띄우는 대신 친절한 안내를 출력한다.
의존성 자동 설치: python bootstrap.py
"""

from __future__ import annotations

import importlib.util
import sys

# import 이름 -> 안내용 표기
_REQUIRED = {
    "PySide6": "PySide6",
    "PIL": "Pillow",
    "openpyxl": "openpyxl",
}


def _check_dependencies() -> list[str]:
    return [name for name in _REQUIRED if importlib.util.find_spec(name) is None]


def main() -> int:
    missing = _check_dependencies()
    if missing:
        names = ", ".join(_REQUIRED[m] for m in missing)
        print(
            "필요한 라이브러리가 설치되어 있지 않습니다: " + names + "\n"
            "다음 명령으로 설치하세요:\n"
            "    python bootstrap.py\n"
            "또는:\n"
            "    pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    # 의존성 확인 후에 import (누락 시 깔끔한 메시지를 위해 함수 내부에서 import)
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from app.config import AppSettings
    from app.ui import theme
    from app.ui.main_window import MainWindow

    # 고DPI: 분수 배율을 그대로 통과시켜 다양한 모니터에서 또렷하게(반올림 깨짐 방지).
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("ConderCompare")
    theme.apply_theme(app)

    settings = AppSettings.load()
    window = MainWindow(settings)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
