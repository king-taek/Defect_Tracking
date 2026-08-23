"""알림. 작업 흐름을 끊지 않는 비차단 안내.

원본은 창 상단 중앙에 배너 하나를 띄우고 다음 메시지가 그것을 덮어썼다. 재설계는 우상단
InfoBar 스택이라 연속으로 오는 알림이 서로를 지우지 않는다(03-screens §9).

`NotificationBanner` 라는 이름과 `show_message(...)` 시그니처를 유지한다. 호출부가 20곳이 넘어
한꺼번에 바꾸면 회귀 원인을 분리할 수 없기 때문이다. 화면을 옮기는 단계마다 호출부를 제목+본문
두 조각으로 다듬는다.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from qfluentwidgets import InfoBar, InfoBarPosition, PushButton, isDarkTheme, setCustomStyleSheet

from app.ui import theme

# 레벨 -> 좌측 톤 바 색을 고르는 상태 토큰 이름.
_TONES = {
    "info": "accentText",
    "success": "pass",
    "warn": "warn",
    "warning": "warn",
    "error": "danger",
}

# 레벨 -> InfoBar 생성자. 원본 4레벨을 그대로 받는다.
_LEVELS = {
    "info": InfoBar.info,
    "success": InfoBar.success,
    "warn": InfoBar.warning,
    "warning": InfoBar.warning,
    "error": InfoBar.error,
}


class NotificationBanner(QWidget):
    """InfoBar 스택 어댑터.

    자기 자신은 그리지 않는다. 부모 창을 기억했다가 InfoBar 를 그 위에 띄운다. 위젯으로 남겨
    둔 것은 기존 호출부가 `NotificationBanner(root)` 로 만들고 `reposition()` 을 부르기 때문이다.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # 레이아웃 자리를 차지하지 않는다. InfoBar 가 위치를 스스로 잡는다.
        self.setFixedSize(0, 0)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._bars: list[InfoBar] = []

    # ------------------------------------------------------------ 표시
    def show_message(
        self,
        text: str,
        level: str = "info",
        *,
        title: Optional[str] = None,
        action_text: Optional[str] = None,
        action: Optional[Callable[[], None]] = None,
        timeout_ms: Optional[int] = None,
    ) -> InfoBar:
        """알림 하나를 우상단에 띄운다.

        timeout_ms 를 주지 않으면 3.4초 뒤 사라진다. 0 이하면 사용자가 닫을 때까지 남는다
        (조치가 필요한 오류용).
        """
        maker = _LEVELS.get(level, InfoBar.info)
        if timeout_ms is None:
            duration = theme.INFOBAR_DURATION_MS
        elif timeout_ms <= 0:
            duration = -1
        else:
            duration = int(timeout_ms)

        head, body = (title, text) if title else (text, "")
        bar = maker(
            title=head,
            content=body,
            orient=Qt.Vertical if body else Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=duration,
            parent=self._host(),
        )
        _add_tone_bar(bar, level)
        if action_text and action is not None:
            button = PushButton(action_text, bar)
            # 액션을 누르면 알림을 먼저 닫고 실행한다. 눌렀는데 남아 있으면 두 번 눌리기 쉽다.
            button.clicked.connect(bar.close)
            button.clicked.connect(action)
            bar.addWidget(button)

        self._bars = [b for b in self._bars if _alive(b)]
        self._bars.append(bar)
        return bar

    # ------------------------------------------------------------ 제어
    def dismiss(self) -> None:
        """떠 있는 알림을 모두 닫는다. 여러 번 불러도 안전하다."""
        for bar in self._bars:
            if _alive(bar):
                bar.close()
        self._bars.clear()

    def reposition(self) -> None:
        """InfoBar 가 위치를 스스로 잡으므로 할 일이 없다(호출부 호환용)."""

    def _host(self) -> QWidget:
        """InfoBar 는 실제 부모가 있어야 뜬다. 없으면 화면에 나타나지 않는다."""
        window = self.window()
        return window if window is not None else self


def _add_tone_bar(bar: InfoBar, level: str) -> None:
    """좌측 4px 톤 바(03-screens §9). 아이콘만으로는 레벨이 흑백 인쇄·저시력에서 약하다."""
    key = _TONES.get(level, "accentText")
    light = theme.fluent_tokens(False)[key]
    dark = theme.fluent_tokens(True)[key]
    radius = theme.RADIUS["control"]
    rule = "InfoBar {{ border-left: 4px solid {0}; border-top-left-radius: {1}px;" \
           " border-bottom-left-radius: {1}px; }}"
    # Fluent 위젯이라 setStyleSheet 대신 setCustomStyleSheet 로 합성한다.
    setCustomStyleSheet(bar, rule.format(light, radius), rule.format(dark, radius))


def _alive(bar: InfoBar) -> bool:
    """C++ 쪽이 이미 지워진 InfoBar 를 건드리지 않게 한다."""
    try:
        bar.isVisible()
    except RuntimeError:
        return False
    return True
