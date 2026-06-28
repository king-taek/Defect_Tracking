"""Defect Layer Tracker — 진입점.

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


def _load_device_db(settings) -> None:
    """설정에 디바이스 DB 경로가 있으면 읽어 제품 목록에 병합한다(실패 무시)."""
    from pathlib import Path

    path = getattr(settings, "device_db_path", "")
    if not path or not Path(path).exists():
        return
    try:
        from app import config
        from app.device_db import load_device_db

        config.register_devices(load_device_db(path))
    except Exception:  # noqa: BLE001 - DB 로드 실패는 치명적이지 않음
        from app import logging_config

        logging_config.get_logger().exception("디바이스 DB 로드 실패: %s", path)


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

    # 터미널 실행 시: 무거운 라이브러리(PySide6) 로딩 동안 즉시 안내(콘솔).
    # windowed(.exe) 모드에서는 stderr 가 없을 수 있으므로 안전하게 처리.
    if sys.stderr is not None:
        try:
            print("Defect Layer Tracker 시작 중... (라이브러리 로딩, 잠시만 기다려 주세요)",
                  file=sys.stderr, flush=True)
        except (OSError, ValueError):
            pass

    # 의존성 확인 후에 import (누락 시 깔끔한 메시지를 위해 함수 내부에서 import).
    # 무거운 모듈(MainWindow 트리: openpyxl/PIL 등)은 스플래시를 띄운 뒤 임포트한다.
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from app import config, logging_config
    from app.config import AppSettings
    from app.ui import theme

    # 고DPI: 분수 배율을 그대로 통과시켜 다양한 모니터에서 또렷하게(반올림 깨짐 방지).
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("ConderCompare")
    theme.apply_theme(app)

    # Qt 준비 직후 즉시 스플래시 표시 → 무거운 구성 동안 "로딩 중" 피드백을 보여준다.
    from app.ui.splash import make_splash, show_status

    splash = make_splash()
    splash.show()
    show_status(splash, "로딩 중...")
    app.processEvents()

    settings = AppSettings.load()
    _load_device_db(settings)
    config.set_active_product(settings.product)
    logging_config.setup_logging(settings.workspace_path)
    logging_config.get_logger().info("애플리케이션 시작 (제품=%s)", settings.product)

    show_status(splash, "화면 구성 중...")
    app.processEvents()

    from app.ui.main_window import MainWindow

    window = MainWindow(settings)
    window.show()
    splash.finish(window)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
