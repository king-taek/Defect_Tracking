"""Conder Scan Review Image Compare Viewer — 진입점.

원본 데이터를 절대 훼손하지 않는(read-only) defect 이미지 비교 뷰어.
실행: python main.py
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app.config import AppSettings
from app.ui import theme
from app.ui.main_window import MainWindow


def main() -> int:
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
