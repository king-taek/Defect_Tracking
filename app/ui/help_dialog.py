"""도움말 다이얼로그 - 도움말 페이지를 창에 띄우는 얇은 껍데기.

내용(단축키 4그룹 · 기능 6항목)은 `app/ui/pages/help.py` 가 갖는다. nav 라우트로 옮긴 뒤에도
F1 과 설정의 "단축키 · 도움말 보기"가 계속 동작해야 해서 이 껍데기를 남긴다. 라우팅이 붙으면
호출부는 페이지로 옮겨 가고 이 파일은 단계 9에서 지운다.

`_SHORTCUT_GROUPS` / `_FEATURES` 는 기존 테스트가 이 이름으로 읽으므로 별칭으로 유지한다.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget
from qfluentwidgets import PrimaryPushButton

from app.ui import theme
from app.ui.pages.help import FEATURES, SHORTCUT_GROUPS, HelpPage

# 옛 이름(비공개 표기)으로 참조하던 호출부·테스트를 위한 별칭. 단일 출처는 pages/help.py 다.
_SHORTCUT_GROUPS = SHORTCUT_GROUPS
_FEATURES = FEATURES

__all__ = ["ShortcutsDialog", "HelpPage", "SHORTCUT_GROUPS", "FEATURES"]


class ShortcutsDialog(QDialog):
    """단축키 + 기능 안내를 담은 창."""

    def __init__(self, parent: Optional[QWidget] = None, size_key: str = "normal"):
        super().__init__(parent)
        self.setWindowTitle("도움말")
        self.setMinimumSize(720, 620)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.page = HelpPage(self, size_key=size_key)
        outer.addWidget(self.page, 1)

        footer = QWidget(self)
        footer_lay = QVBoxLayout(footer)
        footer_lay.setContentsMargins(
            theme.SPACING["pageH"], 0, theme.SPACING["pageH"], theme.SPACING["gapM"]
        )
        self.btn_close = PrimaryPushButton("닫기", footer)
        self.btn_close.setMinimumHeight(theme.fluent_height("primary", size_key))
        self.btn_close.setDefault(True)
        self.btn_close.clicked.connect(self.accept)
        footer_lay.addWidget(self.btn_close, 0, Qt.AlignRight)
        outer.addWidget(footer)
