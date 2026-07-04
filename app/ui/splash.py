"""시작 스플래시 — 무거운 MainWindow 임포트/구성 전에 즉시 피드백을 준다.

PySide6 임포트(가장 큰 비용) 직후, QApplication 이 만들어지자마자 표시한다.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QSplashScreen

from app import __version__, config
from app.ui import theme

_W, _H = 460, 240


def make_splash() -> QSplashScreen:
    """앱 이름/버전과 '로딩 중...' 을 담은 스플래시 화면을 만든다."""
    pm = QPixmap(_W, _H)
    pm.fill(QColor(theme.BG_PANEL))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(QColor(theme.NEON_SOFT))
    p.drawRoundedRect(0, 0, _W - 1, _H - 1, 14, 14)

    p.setPen(QColor(theme.BASE_GLOW))
    title = QFont("Segoe UI", 17)
    title.setBold(True)
    p.setFont(title)
    p.drawText(pm.rect().adjusted(0, -34, 0, -34), Qt.AlignCenter, config.APP_NAME)

    p.setPen(QColor(theme.TEXT_DIM))
    sub = QFont("Segoe UI", 10)
    p.setFont(sub)
    p.drawText(
        pm.rect().adjusted(0, 36, 0, 36),
        Qt.AlignCenter,
        f"v{__version__}",
    )
    # 제작 크레딧(시작 화면)
    credit = QFont("Segoe UI", 9)
    p.setFont(credit)
    p.drawText(
        pm.rect().adjusted(0, 58, 0, 58),
        Qt.AlignCenter,
        config.CREDITS,
    )
    p.end()

    splash = QSplashScreen(pm)
    splash.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    return splash


def show_status(splash: QSplashScreen, text: str) -> None:
    """스플래시 하단에 진행 상태 문구를 표시한다."""
    splash.showMessage(
        text,
        Qt.AlignHCenter | Qt.AlignBottom,
        QColor(theme.TEXT),
    )
