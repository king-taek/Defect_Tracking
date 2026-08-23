"""시작 스플래시. 무거운 MainWindow 임포트/구성 전에 즉시 피드백을 준다.

PySide6 임포트(가장 큰 비용) 직후, QApplication 이 만들어지자마자 표시한다.

REVIEW-01 A5 는 B안(독립 스플래시 리스킨)을 확정했다. qfluentwidgets 의 SplashScreen 은 창이
먼저 있어야 하므로 셸 생성 시간만큼 첫 프레임이 늦는데, 실측(import 166ms + 생성 35ms = 201ms)이
A안 조건(150ms 미만)을 넘겼다. 05-verified-source-facts 의 "임포트 직후 즉시 피드백"이 계승
필수 항목이라 독립 창을 유지하고 Fluent 토큰으로만 다시 칠한다.

스피너는 등속 900ms 무한(가감속 금지 - 게이트), 단계 문구는 고정 높이라 교체 시 흔들리지 않는다.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

from app import __version__, config
from app.ui import theme

_W, _H = 400, 220
_ICON = 64
_SPINNER = 26
_SPINNER_PEN = 2.5
_STATUS_H = 16          # 문구가 바뀌어도 흔들리지 않도록 고정
_FADE_MS = 300          # 퇴장
_FRAME_MS = 16
_SPIN_MS = theme.MOTION["spinner"][0]   # 900ms 등속


class FluentSplash(QWidget):
    """Fluent 토큰으로 칠한 독립 스플래시 창."""

    def __init__(self, dark: bool = False) -> None:
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint |
                         Qt.WindowStaysOnTopHint)
        self.setObjectName("fluentSplash")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(_W, _H)

        self._dark = bool(dark)
        self._tokens = theme.fluent_tokens(self._dark)
        self._accent = theme.accent_roles(self._dark)
        self._status = ""
        self._angle = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._advance)
        self._timer.start()

        self._center_on_screen()

    # ---- 위치 ----
    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.center().x() - _W // 2, area.center().y() - _H // 2)

    # ---- 상태 ----
    def set_status(self, text: str) -> None:
        self._status = text or ""
        self.update()

    def _advance(self) -> None:
        # 등속: 한 바퀴 900ms. 가감속을 넣지 않는다(게이트).
        self._angle = (self._angle + 360.0 * _FRAME_MS / _SPIN_MS) % 360.0
        self.update()

    def finish(self, window: QWidget | None = None) -> None:
        """300ms 로 사라진다. window 인자는 QSplashScreen 과의 호환용."""
        self._timer.stop()
        steps = max(1, _FADE_MS // _FRAME_MS)
        self._fade_left = steps
        fade = QTimer(self)

        def step() -> None:
            self._fade_left -= 1
            self.setWindowOpacity(max(0.0, self._fade_left / steps))
            if self._fade_left <= 0:
                fade.stop()
                self.close()

        fade.timeout.connect(step)
        fade.start(_FRAME_MS)

    # ---- 그리기 ----
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 규약
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        radius = theme.RADIUS["sheet"]
        body = QPainterPath()
        body.addRoundedRect(0.5, 0.5, _W - 1, _H - 1, radius, radius)
        p.fillPath(body, QColor(self._tokens["win"]))
        p.setPen(QPen(QColor(theme.flatten(self._tokens["cardBorder"],
                                           self._tokens["win"])), 1))
        p.drawPath(body)

        # 220px 안에 아이콘 64 + 제목 24 + 버전 16 + 스피너 26 + 문구 16 이 들어가도록
        # 여백을 배분한다(합계 209, 하단 11 여유).
        top = 22
        self._paint_icon(p, top)
        top += _ICON + 14
        top = self._paint_titles(p, top)
        top += 14
        self._paint_spinner(p, top)
        top += _SPINNER + 10
        self._paint_status(p, top)
        p.end()

    def _paint_icon(self, p: QPainter, top: int) -> None:
        x = (_W - _ICON) // 2
        icon = QPainterPath()
        icon.addRoundedRect(x, top, _ICON, _ICON, 14, 14)
        p.fillPath(icon, QColor(self._accent["fill"]))
        dot = 22
        p.setBrush(QColor(self._accent["onAccent"]))
        p.setPen(Qt.NoPen)
        p.drawEllipse(x + (_ICON - dot) // 2, top + (_ICON - dot) // 2, dot, dot)

    def _paint_titles(self, p: QPainter, top: int) -> int:
        title = QFont(_family(), 12)
        title.setWeight(QFont.DemiBold)
        title.setPixelSize(19)
        p.setFont(title)
        p.setPen(QColor(theme.flatten(self._tokens["txt1"], self._tokens["win"])))
        p.drawText(0, top, _W, 24, Qt.AlignHCenter | Qt.AlignVCenter, config.APP_NAME)
        top += 24 + 3

        ver = QFont(_family(), 9)
        ver.setPixelSize(12)
        p.setFont(ver)
        p.setPen(QColor(theme.flatten(self._tokens["txt3"], self._tokens["win"])))
        p.drawText(0, top, _W, 16, Qt.AlignHCenter | Qt.AlignVCenter, f"v{__version__}")
        return top + 16

    def _paint_spinner(self, p: QPainter, top: int) -> None:
        x = (_W - _SPINNER) // 2
        rect = (x + _SPINNER_PEN, top + _SPINNER_PEN,
                _SPINNER - 2 * _SPINNER_PEN, _SPINNER - 2 * _SPINNER_PEN)
        track = QPen(QColor(theme.flatten(self._tokens["divider"], self._tokens["win"])),
                     _SPINNER_PEN)
        track.setCapStyle(Qt.FlatCap)
        p.setBrush(Qt.NoBrush)
        p.setPen(track)
        p.drawEllipse(*rect)

        arc = QPen(QColor(self._accent["fill"]), _SPINNER_PEN)
        arc.setCapStyle(Qt.RoundCap)
        p.setPen(arc)
        # Qt 각도 단위는 1/16도. 시계 방향으로 돌도록 부호를 뒤집는다.
        p.drawArc(int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]),
                  int(-self._angle * 16), int(-100 * 16))

    def _paint_status(self, p: QPainter, top: int) -> None:
        font = QFont(_family(), 9)
        font.setPixelSize(12)
        p.setFont(font)
        p.setPen(QColor(theme.flatten(self._tokens["txt2"], self._tokens["win"])))
        p.drawText(0, top, _W, _STATUS_H, Qt.AlignHCenter | Qt.AlignVCenter, self._status)


def _family() -> str:
    """프로덕션은 Segoe UI Variable, 없으면 시스템 기본으로 떨어진다."""
    return "Segoe UI Variable Text"


def make_splash(dark: bool = False) -> FluentSplash:
    """앱 이름/버전과 진행 문구를 담은 스플래시 창을 만든다."""
    return FluentSplash(dark)


def show_status(splash: FluentSplash, text: str) -> None:
    """스플래시 하단 단계 문구를 갱신한다."""
    splash.set_status(text)
