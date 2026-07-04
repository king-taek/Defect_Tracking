"""도움말 다이얼로그 — 단축키 + 기능 안내(섹션 구성, 스크롤)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme

# 단축키 그룹: (그룹명, [(키, 설명), ...])
_SHORTCUT_GROUPS = [
    ("탐색", [
        ("← / → · PageUp / PageDown", "이전 / 다음 기준 사진"),
        ("Home / End", "처음 / 끝 기준 사진으로"),
        ("U", "다음 '미매칭 포함' 기준으로 점프"),
        ("F5", "현재 자재 폴더 다시 스캔"),
    ]),
    ("선택 · 마킹", [
        ("M", "현재 기준 사진 마킹 토글"),
        ("Ctrl + A / Ctrl + D", "비교 Layer 전체 선택 / 모두 해제"),
    ]),
    ("출력", [
        ("A", "현재 기준 사진을 출력 트레이에 담기"),
        ("Ctrl + E", "Excel 결과 출력"),
    ]),
    ("파일 · 도움말", [
        ("Ctrl + O", "자재 폴더 열기 (우클릭: 최근 폴더)"),
        ("F1", "이 도움말 열기"),
        ("이미지 클릭", "원본 전체 해상도 확대 보기"),
        ("이미지 우클릭", "경로 복사 / 파일·폴더 열기 (기준: 마킹·메모)"),
    ]),
]

# 기능 안내: (기능명, 설명)
_FEATURES = [
    ("자재 폴더 선택기",
     "브레드크럼·폴더 트리·최근/즐겨찾기로 탐색하고, 고른 폴더가 자재(LOT)인지 실시간으로 "
     "확인합니다. layer·wafer 폴더를 골라도 자재 폴더로 자동 보정됩니다."),
    ("Defect 히트맵",
     "웨이퍼맵에 defect 밀도를 색으로 표시합니다. 위치를 클릭하면 그 자리의 defect 이 "
     "오른쪽에 나열됩니다. 상단 캡션에서 현재 모드·wafer 를 확인할 수 있습니다."),
    ("매치만 / 전체 defect 모드",
     "기본은 '매치만'(매칭된 기준 defect). '전체 defect'를 켜면 특정 기준 없이 선택 layer 를 "
     "서로 교차 매칭해 모든 defect 을 보여주고, 매칭 안 된 것은 개별로 표시합니다. "
     "웨이퍼맵 색도 모드에 따라 바뀝니다."),
    ("여러 다이 선택 · 드래그 박스",
     "웨이퍼맵에서 드래그하면 사각형으로 여러 die 를 한 번에 선택합니다(항상 가능). "
     "'여러 다이 선택'을 켜면 클릭이 die 를 누적 토글합니다."),
    ("defect 클러스터링",
     "같은 layer 에서 거리 50 미만으로 붙은 defect 은 하나로 묶어 대표 1장만 보이고, "
     "좌하단 '+n' 을 누르면 묶인 나머지도 모두 볼 수 있습니다."),
    ("출력 트레이",
     "'담기'로 원하는 defect 을 모아 두었다가 'Excel 출력'으로 한 번에 리포트를 만듭니다. "
     "layer·자재를 바꿔도 담은 사진은 유지됩니다."),
]

_KEY_COL_WIDTH = 190


class ShortcutsDialog(QDialog):
    """단축키 + 기능 안내."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("도움말")
        self.setMinimumSize(560, 560)
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setAutoFillBackground(False)
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(20, 18, 20, 14)
        lay.setSpacing(14)

        lay.addWidget(self._title("단축키"))
        for name, rows in _SHORTCUT_GROUPS:
            lay.addWidget(self._group_header(name))
            lay.addWidget(self._shortcut_grid(rows))

        lay.addSpacing(4)
        lay.addWidget(self._title("기능 안내"))
        for name, desc in _FEATURES:
            lay.addWidget(self._feature_card(name, desc))

        lay.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        footer = QVBoxLayout()
        footer.setContentsMargins(20, 8, 20, 12)
        btn = QPushButton("닫기")
        btn.setObjectName("primary")
        btn.setDefault(True)
        btn.clicked.connect(self.accept)
        footer.addWidget(btn, alignment=Qt.AlignRight)
        outer.addLayout(footer)

    @staticmethod
    def _title(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("title")
        return lbl

    @staticmethod
    def _group_header(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color:{theme.NEON}; font-weight:700; font-size:12px;"
            " letter-spacing:1px; margin-top:2px;"
        )
        return lbl

    @staticmethod
    def _shortcut_grid(rows: list[tuple[str, str]]) -> QWidget:
        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(6, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        grid.setColumnMinimumWidth(0, _KEY_COL_WIDTH)
        grid.setColumnStretch(1, 1)
        for r, (key, desc) in enumerate(rows):
            k = QLabel(key)
            k.setStyleSheet(
                f"font-weight:700; color:{theme.TEXT};"
                f" background:{theme.BG_ELEV}; border:1px solid {theme.NEON_SOFT};"
                " border-radius:5px; padding:2px 8px;"
            )
            k.setTextInteractionFlags(Qt.TextSelectableByMouse)
            d = QLabel(desc)
            d.setObjectName("dim")
            d.setWordWrap(True)
            grid.addWidget(k, r, 0, Qt.AlignTop | Qt.AlignLeft)
            grid.addWidget(d, r, 1, Qt.AlignVCenter)
        return host

    @staticmethod
    def _feature_card(name: str, desc: str) -> QWidget:
        card = QFrame()
        card.setObjectName("cell")
        card.setStyleSheet(
            f"QFrame#cell {{ background:{theme.BG_ELEV};"
            f" border:1px solid {theme.NEON_SOFT}; border-radius:8px; }}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 10)
        lay.setSpacing(3)
        title = QLabel(name)
        title.setStyleSheet(f"font-weight:700; color:{theme.TEXT};")
        desc_lbl = QLabel(desc)
        desc_lbl.setObjectName("dim")
        desc_lbl.setWordWrap(True)
        lay.addWidget(title)
        lay.addWidget(desc_lbl)
        return card
