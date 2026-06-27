"""단축키 도움말 다이얼로그."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# (단축키, 설명)
_SHORTCUTS = [
    ("← / → , PageUp / PageDown", "이전 / 다음 기준 사진"),
    ("Home / End", "필터 기준 처음 / 끝으로"),
    ("U", "다음 '미매칭 포함' 기준으로 점프"),
    ("M", "현재 기준 사진 마킹 토글"),
    ("O", "겹쳐 보기 / 블링크 열기"),
    ("Ctrl + A / Ctrl + D", "비교 Layer 전체 선택 / 모두 해제"),
    ("Ctrl + O", "자재 폴더 열기 (우클릭: 최근 폴더)"),
    ("Ctrl + E", "Excel 결과 출력"),
    ("F5", "현재 자재 폴더 다시 스캔"),
    ("F1", "이 도움말 열기"),
    ("이미지 클릭", "원본 전체 해상도 확대 보기"),
    ("이미지 우클릭", "경로 복사 / 파일·폴더 열기 (기준: 마킹·메모)"),
]


class ShortcutsDialog(QDialog):
    """키보드 단축키 및 마우스 동작 안내."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("단축키 도움말")
        self.setMinimumWidth(460)
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(12)

        title = QLabel("단축키 / 동작")
        title.setObjectName("title")
        outer.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        for row, (key, desc) in enumerate(_SHORTCUTS):
            k = QLabel(key)
            k.setStyleSheet("font-weight:700;")
            k.setTextInteractionFlags(Qt.TextSelectableByMouse)
            d = QLabel(desc)
            d.setObjectName("dim")
            d.setWordWrap(True)
            grid.addWidget(k, row, 0, Qt.AlignTop)
            grid.addWidget(d, row, 1, Qt.AlignTop)
        outer.addLayout(grid)

        btn = QPushButton("닫기")
        btn.setObjectName("primary")
        btn.clicked.connect(self.accept)
        outer.addWidget(btn, alignment=Qt.AlignRight)
