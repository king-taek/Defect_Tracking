"""아직 옮기지 않은 화면으로 가는 임시 라우트.

nav 6칸을 먼저 세우되 기능은 끊지 않기 위한 다리다. 각 페이지는 제목·설명·주요 액션 하나를
두고, 액션이 기존 다이얼로그를 연다. 해당 단계(4~8)에서 실제 페이지로 교체하며 이 파일을 지운다.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, PrimaryPushButton, SubtitleLabel

from app.ui import theme


class LauncherPage(QWidget):
    """제목 + 설명 + 주요 액션 하나로 된 임시 페이지."""

    triggered = Signal()

    def __init__(
        self,
        object_name: str,
        title: str,
        body: str,
        action: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # objectName 은 라우트 키다. 비면 ValueError, 겹치면 라우팅이 깨진다.
        self.setObjectName(object_name)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            theme.SPACING["pageH"], theme.SPACING["pageV"],
            theme.SPACING["pageH"], theme.SPACING["pageV"],
        )
        outer.setAlignment(Qt.AlignCenter)
        outer.setSpacing(0)

        box = QWidget(self)
        box.setMaximumWidth(460)
        col = QVBoxLayout(box)
        col.setAlignment(Qt.AlignHCenter)
        col.setSpacing(0)

        head = SubtitleLabel(title, box)
        head.setAlignment(Qt.AlignCenter)
        col.addWidget(head)
        col.addSpacing(8)

        text = BodyLabel(body, box)
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignCenter)
        col.addWidget(text)
        col.addSpacing(20)

        self.button = PrimaryPushButton(action, box)
        self.button.setMinimumHeight(theme.fluent_height("primary"))
        self.button.clicked.connect(self.triggered)
        col.addWidget(self.button, 0, Qt.AlignHCenter)

        outer.addWidget(box)

    def set_enabled(self, enabled: bool) -> None:
        self.button.setEnabled(enabled)
