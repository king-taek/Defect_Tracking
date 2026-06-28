"""도움말 다이얼로그 — 단축키 + 보기 필터/매칭 상태 범례."""

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

from app.ui import theme

# (단축키, 설명)
_SHORTCUTS = [
    ("← / → , PageUp / PageDown", "이전 / 다음 기준 사진"),
    ("Home / End", "필터 기준 처음 / 끝으로"),
    ("U", "다음 '미매칭 포함' 기준으로 점프"),
    ("M", "현재 기준 사진 마킹 토글"),
    ("Ctrl + A / Ctrl + D", "비교 Layer 전체 선택 / 모두 해제"),
    ("Ctrl + O", "자재 폴더 열기 (우클릭: 최근 폴더)"),
    ("Ctrl + E", "Excel 결과 출력"),
    ("F5", "현재 자재 폴더 다시 스캔"),
    ("F1", "이 도움말 열기"),
    ("이미지 클릭", "원본 전체 해상도 확대 보기"),
    ("이미지 우클릭", "경로 복사 / 파일·폴더 열기 (기준: 마킹·메모)"),
]

# (필터 이름, 설명)
_FILTERS = [
    ("매칭만 (기본)", "어떤 비교 layer 와도 매칭 안 된 기준 사진을 후보에서 제외"),
    ("전체", "모든 기준 사진을 표시(제외 없음)"),
    ("미매칭 있음", "하나라도 매칭 안 된 layer 가 있는 사진(검토 대상)"),
    ("완전 매칭", "선택한 비교 layer 전부와 매칭된 사진만"),
]

# (색, 상태 설명) — 썸네일/웨이퍼 맵의 상태 점 색과 일치
_STATUS = [
    (theme.MATCH, "완전 매칭 — 선택한 모든 비교 layer 와 매칭"),
    (theme.WARN, "부분 매칭 — 일부 layer 만 매칭"),
    (theme.NOMATCH, "미매칭 — 어떤 비교 layer 와도 매칭되지 않음"),
]


class ShortcutsDialog(QDialog):
    """키보드 단축키 · 보기 필터 · 매칭 상태 색 안내."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("도움말")
        self.setMinimumWidth(480)
        self._build()

    @staticmethod
    def _section(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("title")
        return lbl

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(12)

        outer.addWidget(self._section("단축키 / 동작"))
        outer.addLayout(self._pairs(_SHORTCUTS, key_bold=True))

        outer.addWidget(self._section("보기 필터"))
        outer.addLayout(self._pairs(_FILTERS, key_bold=True))

        outer.addWidget(self._section("매칭 상태 색"))
        status_grid = QGridLayout()
        status_grid.setHorizontalSpacing(18)
        status_grid.setVerticalSpacing(8)
        status_grid.setColumnStretch(1, 1)
        for row, (color, desc) in enumerate(_STATUS):
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{color}; font-size:14px;")
            d = QLabel(desc)
            d.setObjectName("dim")
            d.setWordWrap(True)
            status_grid.addWidget(dot, row, 0, Qt.AlignTop)
            status_grid.addWidget(d, row, 1, Qt.AlignTop)
        outer.addLayout(status_grid)

        btn = QPushButton("닫기")
        btn.setObjectName("primary")
        btn.clicked.connect(self.accept)
        outer.addWidget(btn, alignment=Qt.AlignRight)

    @staticmethod
    def _pairs(rows: list[tuple[str, str]], *, key_bold: bool) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        for row, (key, desc) in enumerate(rows):
            k = QLabel(key)
            if key_bold:
                k.setStyleSheet("font-weight:700;")
            k.setTextInteractionFlags(Qt.TextSelectableByMouse)
            d = QLabel(desc)
            d.setObjectName("dim")
            d.setWordWrap(True)
            grid.addWidget(k, row, 0, Qt.AlignTop)
            grid.addWidget(d, row, 1, Qt.AlignTop)
        return grid
