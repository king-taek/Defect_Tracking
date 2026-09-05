"""Defect Tracker - 진입점.

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
    # Fluent 화면 구성요소(PySide6-Fluent-Widgets). 자동 업데이트는 코드만 덮어쓰고 pip 를
    # 돌리지 않으므로, 여기 없으면 기존 설치본이 원시 트레이스백으로 죽는다.
    "qfluentwidgets": "PySide6-Fluent-Widgets",
    "PIL": "Pillow",
    "openpyxl": "openpyxl",
}

# Qt 는 있는데 Fluent 구성요소만 없는 경우(=자동 업데이트 직후)에 띄우는 안내.
# qfluentwidgets 를 못 불러오는 상황이므로 순수 Qt QMessageBox 를 쓴다.
_SETUP_TITLE = "추가 구성이 필요합니다"
_SETUP_BODY = (
    "이 버전은 새 화면 구성요소를 사용합니다.\n"
    "bootstrap.py 를 한 번 실행하면 설치가 끝납니다."
)
_SETUP_HOWTO = (
    "설치 방법\n\n"
    "    python bootstrap.py\n\n"
    "또는\n\n"
    "    pip install -r requirements.txt"
)


def _show_setup_notice(missing: list[str]) -> bool:
    """Fluent 구성요소 누락을 GUI 로 안내한다. Qt 조차 없으면 False.

    트레이스백을 그대로 보여주면 사용자가 할 수 있는 일이 없다(게이트).
    """
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        return False
    app = QApplication.instance() or QApplication(sys.argv)
    box = QMessageBox()
    box.setIcon(QMessageBox.Information)
    box.setWindowTitle(_SETUP_TITLE)
    box.setText(_SETUP_BODY)
    box.setDetailedText(_SETUP_HOWTO + "\n\n누락: " + ", ".join(missing))
    box.setStandardButtons(QMessageBox.Ok)
    box.exec()
    del app
    return True


def _check_dependencies() -> list[str]:
    return [name for name in _REQUIRED if importlib.util.find_spec(name) is None]


def _load_device_db(settings) -> None:
    """디바이스 DB 를 읽어 제품 목록에 병합한다(실패 무시).

    설정에 경로가 있으면 그 경로를, 없으면 앱과 함께 배포되는 번들 DB
    (data/AOIDeviceDB.xlsx)를 자동으로 읽는다. DB 를 하드코딩하지 않고 항상 파일에서
    읽어 와 웨이퍼맵 die 위치가 DB 기준으로 표시되도록 한다.
    """
    from pathlib import Path

    from app import config

    path = getattr(settings, "device_db_path", "")
    db_path = Path(path) if path else None
    if db_path is None or not db_path.exists():
        db_path = config.bundled_device_db_path()  # 번들 DB 자동 로드
    if db_path is None:
        return
    try:
        from app.device_db import load_device_db

        config.register_devices(load_device_db(db_path))
    except Exception:  # noqa: BLE001 - DB 로드 실패는 치명적이지 않음
        from app import logging_config

        logging_config.get_logger().exception("디바이스 DB 로드 실패: %s", db_path)


def main() -> int:
    missing = _check_dependencies()
    if missing:
        names = ", ".join(_REQUIRED[m] for m in missing)
        # Qt 는 있는데 Fluent 만 빠진 경우(자동 업데이트 직후)에는 GUI 로 안내한다.
        if missing == ["qfluentwidgets"]:
            _show_setup_notice([_REQUIRED[m] for m in missing])
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
            print("Defect Tracker 시작 중... (라이브러리 로딩, 잠시만 기다려 주세요)",
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
    app.setApplicationName("Defect Tracker")
    # 설정을 먼저 읽어 글자 크기(보통/크게)를 테마에 반영한 뒤 스플래시를 띄운다.
    settings = AppSettings.load()
    # setTheme 은 위젯 생성 전에 부른다. 나중에 부르면 첫 프레임이 반대 테마로 그려졌다가
    # 다시 칠해진다(qfluentwidgets 필수 규칙).
    dark = (settings.theme_mode or "light").lower() == "dark"
    from qfluentwidgets import Theme, setTheme, setThemeColor

    setTheme(Theme.DARK if dark else Theme.LIGHT)
    setThemeColor(theme.ACCENT_BASE)
    # 다크 네온 전역 QSS 는 여기서 끊는다. Fluent 위젯을 덮어써 테마가 반만 적용되기 때문이다.
    # 아직 옮기지 않은 화면(단계 4~8)은 토큰으로 만든 브리지 QSS 로 읽히게 한다.
    theme.FONT_SCALE = theme.scale_for(settings.ui_font_size)
    # 본문 서체(시안). 없는 글꼴은 다음 후보로 내려가므로 아무 환경에서도 깨지지 않는다.
    base_font = app.font()
    base_font.setFamilies(theme.FONT_FAMILIES)
    app.setFont(base_font)
    app.setStyleSheet(theme.build_bridge_qss(dark))

    # Qt 준비 직후 즉시 스플래시 표시. 무거운 구성 동안 "로딩 중" 피드백을 보여준다.
    from app.ui.splash import make_splash, show_status

    splash = make_splash(dark)
    splash.show()
    show_status(splash, "로딩 중...")
    app.processEvents()

    _load_device_db(settings)
    config.set_active_product(settings.product)
    # 빌트인 폴백(die_map 없음) 대신 같은 패키지 크기의 DB die_map 제품으로 승격 →
    # 웨이퍼맵이 기본적으로 실제 die 모양으로 표시되도록.
    config.ensure_die_map_product()
    # 개발자 모드(환경변수 또는 설정)일 때만 파일 로그를 남긴다. 일반 사용자에겐 로그를 만들지 않음.
    if config.dev_mode(settings):
        logging_config.setup_logging(settings.log_dir_path)
        logging_config.get_logger().info("애플리케이션 시작 (제품=%s)", settings.product)

    show_status(splash, "화면 구성 중...")
    app.processEvents()

    from app.ui.main_window import MainWindow

    window = MainWindow(settings)
    window.show_initial()  # 기본 최대화(설정), 해제 이력이 있으면 저장된 창 크기
    splash.finish(window)
    # 창이 뜬 뒤(이벤트 루프 진입 후) 디바이스 DB 미설정 안내 팝업을 띄운다.
    from PySide6.QtCore import QTimer

    QTimer.singleShot(0, window.maybe_prompt_device_db)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
