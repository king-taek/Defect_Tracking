"""도움말 페이지.

원본은 모달 다이얼로그였다. 단축키를 확인하려면 보던 화면을 덮어야 했으므로 nav 라우트로
옮긴다(03-screens §5). 문구는 REVIEW-01 A6 확정본이다. 담기 화면의 이름이 "출력 명세"로
바뀌었으니 도움말도 그 이름을 쓰고, FEAT#3 은 코드에서 사라진 모드 토글을 설명하던 문장이라
layer 교차 판독 설명으로 교체했다.

단축키 표와 기능 카드는 순수 Qt 위젯(QFrame/QLabel)이라 setStyleSheet 로 칠한다. Fluent
위젯이 아니므로 금지 대상이 아니고, 대신 테마가 바뀌면 qconfig.themeChanged 로 다시 칠한다.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    SmoothScrollArea,
    TitleLabel,
    isDarkTheme,
    qconfig,
    setCustomStyleSheet,
    setFont,
)

from app.ui import theme

# 단축키 그룹: (그룹명, [(키, 설명), ...]). 원본 4그룹을 유지한다.
SHORTCUT_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("탐색", [
        ("← / → · PageUp / PageDown", "이전 / 다음 기준 사진"),
        ("Home / End", "처음 / 끝 기준 사진으로"),
        ("U", "다음 '미매칭 포함' 기준으로 점프"),
        ("F5", "현재 LOT 폴더 다시 스캔"),
    ]),
    ("선택", [
        ("Ctrl + A / Ctrl + D", "비교 Layer 전체 선택 / 모두 해제"),
    ]),
    ("출력", [
        ("A", "현재 기준 사진을 출력 명세에 담기"),
        ("Ctrl + E", "Excel 결과 출력"),
    ]),
    ("파일 · 도움말", [
        ("Ctrl + O", "LOT 폴더 열기 (우클릭: 최근 폴더)"),
        ("F1", "이 도움말 열기"),
        ("이미지 클릭", "원본 전체 해상도 확대 보기"),
        ("이미지 우클릭", "경로 복사 / 파일·폴더 열기"),
    ]),
]

# 기능 안내: (기능명, 설명). 원본 6항목을 유지하되 3번째는 REVIEW-01 A6 확정 문구다.
FEATURES: list[tuple[str, str]] = [
    ("LOT 폴더 선택기",
     "브레드크럼·폴더 트리·최근/즐겨찾기로 탐색하고, 고른 폴더가 LOT 인지 실시간으로 "
     "확인합니다. layer·wafer 폴더를 골라도 LOT 폴더로 자동 보정됩니다."),
    # 마지막 문장은 '매치만 / 전체 defect' 모드를 가리키던 잔재였다. 그 모드가 없어졌으므로
    # 지금 화면에 실제로 있는 것(슬롯 레일)을 가리킨다. 없는 것을 안내하면 안 하느니만 못하다.
    ("Defect 히트맵",
     "웨이퍼맵에 defect 밀도를 색으로 표시합니다. 위치를 클릭하면 그 자리의 defect 이 "
     "오른쪽에 나열됩니다. 슬롯 레일에서 보는 wafer 를 좁힐 수 있습니다."),
    ("layer 교차 판독",
     "히트맵에서 위치를 고르면 그 자리의 defect 을 layer 별로 나란히 놓고 봅니다. "
     "선택한 layer 들을 서로 교차 매칭하므로 기준 없이도 비교할 수 있고, "
     "어느 layer 와도 매칭되지 않은 defect 은 따로 표시됩니다."),
    ("여러 다이 선택 · 드래그 박스",
     "웨이퍼맵에서 드래그하면 사각형으로 여러 die 를 한 번에 선택합니다(항상 가능). "
     "'여러 다이 선택'을 켜면 클릭이 die 를 누적 토글합니다."),
    ("defect 클러스터링",
     "같은 layer 에서 거리 50 미만으로 붙은 defect 은 하나로 묶어 대표 1장만 보이고, "
     "좌하단 '+n' 을 누르면 묶인 나머지도 모두 볼 수 있습니다."),
    ("출력 명세",
     "'담기'로 원하는 defect 을 모아 두었다가 'Excel 출력'으로 한 번에 리포트를 만듭니다. "
     "layer·LOT 을 바꿔도 담은 사진은 유지됩니다."),
]

_PAGE_TITLE = "도움말"
_PAGE_SUB = "단축키와 기능 안내 · F1"
_SECTION_SHORTCUT = "단축키"
_SECTION_FEATURE = "기능 안내"

# 키캡 최소 폭. 가장 긴 키 조합("← / → · PageUp / PageDown")이 한 줄에 들어가는 값이다.
_KEYCAP_MIN_PX = 214
# 수치·키 표기는 등폭(02 §2). 사진 카드와 같은 글꼴 목록을 쓴다.
_MONO = "'Cascadia Mono','Consolas',monospace"
_FEATURE_COLUMNS = 2
# 02 §2 의 굵기 600. PySide6 setFont 는 정수 대신 QFont.Weight 를 받는다.
_W600 = QFont.Weight.DemiBold


class HelpPage(QWidget):
    """단축키 표 + 기능 카드 그리드. 읽기 전용이라 상태를 갖지 않는다."""

    def __init__(self, parent: QWidget | None = None, size_key: str = "normal") -> None:
        super().__init__(parent)
        # objectName 은 라우트 키다. 비면 ValueError, 겹치면 라우팅이 깨진다.
        self.setObjectName("helpInterface")
        self._size_key = size_key or "normal"

        # 다시 칠할 대상만 모아 둔다. 위젯 트리를 매번 훑으면 다른 화면의 라벨까지 건드린다.
        self._group_heads: list[QLabel] = []
        self._rows: list[QFrame] = []
        self._keycaps: list[QLabel] = []
        self._descs: list[QLabel] = []
        self._feature_cards: list[QFrame] = []
        self._feature_titles: list[QLabel] = []
        self._feature_bodies: list[QLabel] = []
        self._section_labels: list[QLabel] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = SmoothScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        # Fluent 위젯이라 setStyleSheet 로 덮으면 스크롤바 스타일까지 같이 날아간다.
        transparent = "SmoothScrollArea { background: transparent; border: none; }"
        setCustomStyleSheet(self.scroll, transparent, transparent)
        self.scroll.viewport().setStyleSheet("background: transparent;")
        outer.addWidget(self.scroll)

        body = QWidget(self.scroll)
        body.setObjectName("helpBody")
        body.setStyleSheet("QWidget#helpBody { background: transparent; }")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(
            theme.SPACING["pageH"], theme.SPACING["pageV"],
            theme.SPACING["pageH"], theme.SPACING["pageH"],
        )
        lay.setSpacing(0)

        self.title = TitleLabel(_PAGE_TITLE, body)
        lay.addWidget(self.title)
        self.subtitle = CaptionLabel(_PAGE_SUB, body)
        self.subtitle.setObjectName("dim")
        lay.addWidget(self.subtitle)

        lay.addSpacing(24)
        lay.addWidget(self._section_label(_SECTION_SHORTCUT, body))
        lay.addSpacing(10)
        lay.addWidget(self._build_shortcut_card(body))

        lay.addSpacing(24)
        lay.addWidget(self._section_label(_SECTION_FEATURE, body))
        lay.addSpacing(10)
        lay.addLayout(self._build_feature_grid(body))
        lay.addStretch(1)

        self.scroll.setWidget(body)
        # 테마 전환은 앱 어디서나 일어난다. 페이지가 살아 있는 동안 계속 따라가야 한다.
        qconfig.themeChanged.connect(self._apply_palette)
        self._apply_palette()

    # ------------------------------------------------------------ 구성
    def _section_label(self, text: str, parent: QWidget) -> QLabel:
        label = QLabel(text, parent)
        label.setObjectName("helpSection")
        self._section_labels.append(label)
        return label

    def _build_shortcut_card(self, parent: QWidget) -> QFrame:
        """4그룹을 카드 하나에 담는다. 그룹마다 카드를 쪼개면 세로로 너무 길어진다."""
        card = QFrame(parent)
        card.setObjectName("helpShortcutCard")
        self.shortcut_card = card
        col = QVBoxLayout(card)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        for name, rows in SHORTCUT_GROUPS:
            head = QLabel(name, card)
            head.setObjectName("helpGroupHead")
            self._group_heads.append(head)
            col.addWidget(head)
            for key, desc in rows:
                col.addWidget(self._shortcut_row(card, key, desc))
        return card

    def _shortcut_row(self, parent: QWidget, key: str, desc: str) -> QFrame:
        row = QFrame(parent)
        row.setObjectName("helpRow")
        row.setMinimumHeight(theme.fluent_height("control", self._size_key))
        lay = QHBoxLayout(row)
        lay.setContentsMargins(18, 11, 18, 11)
        lay.setSpacing(theme.SPACING["gapL"])

        cap = QLabel(key, row)
        cap.setObjectName("helpKeycap")
        cap.setMinimumWidth(_KEYCAP_MIN_PX)
        cap.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(cap, 0, Qt.AlignVCenter)
        self._keycaps.append(cap)

        text = QLabel(desc, row)
        text.setObjectName("helpDesc")
        text.setWordWrap(True)
        lay.addWidget(text, 1, Qt.AlignVCenter)
        self._descs.append(text)

        self._rows.append(row)
        return row

    def _build_feature_grid(self, parent: QWidget) -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        for index, (name, desc) in enumerate(FEATURES):
            card = QFrame(parent)
            card.setObjectName("helpFeatureCard")
            col = QVBoxLayout(card)
            col.setContentsMargins(17, 15, 17, 15)
            col.setSpacing(6)

            head = QLabel(name, card)
            head.setObjectName("helpFeatureTitle")
            head.setWordWrap(True)
            col.addWidget(head)

            text = QLabel(desc, card)
            text.setObjectName("helpFeatureBody")
            text.setWordWrap(True)
            col.addWidget(text)
            col.addStretch(1)

            grid.addWidget(card, index // _FEATURE_COLUMNS, index % _FEATURE_COLUMNS)
            self._feature_cards.append(card)
            self._feature_titles.append(head)
            self._feature_bodies.append(text)
        for column in range(_FEATURE_COLUMNS):
            grid.setColumnStretch(column, 1)
        return grid

    # ------------------------------------------------------------ 표시
    def set_font_size(self, size_key: str) -> None:
        """글자 크기(보통/크게)를 즉시 반영한다. 높이는 하한이라 함께 올린다(A9)."""
        self._size_key = size_key or "normal"
        for row in self._rows:
            row.setMinimumHeight(theme.fluent_height("control", self._size_key))
        self._apply_palette()

    def _apply_palette(self) -> None:
        """색과 글자 크기를 한 번에 다시 칠한다. 테마 전환·글자 크기 변경의 공통 경로다."""
        dark = isDarkTheme()
        t = theme.fluent_tokens(dark)
        # 페이지 면(layer). 셸의 StackedWidget 이 계산해 내는 색과 같은 값이라 이음매가 없고,
        # 페이지만 따로 띄워도(검증 렌더) 글자가 읽힌다.
        self.setStyleSheet(
            f"QWidget#helpInterface {{ background-color: {t['layer']}; }}"
        )
        card = t["card"]
        txt1 = theme.flatten(t["txt1"], card)
        txt2 = theme.flatten(t["txt2"], card)
        layer_txt2 = theme.flatten(t["txt2"], t["layer"])
        border = theme.flatten(t["cardBorder"], t["layer"])
        border_hover = theme.flatten(t["cardBorderH"], t["layer"])
        divider = theme.flatten(t["divider"], card)
        subtle = theme.flatten(t["subtle"], card)
        ctrl_bg = theme.flatten(t["ctrlBg"], card)
        ctrl_bd = theme.flatten(t["ctrlBd"], card)
        ctrl_bd_bottom = theme.flatten(t["ctrlBdBottom"], card)
        card_hover = t["cardHover"]
        radius = theme.RADIUS["card"]

        setFont(self.title, round(self._px("title")), _W600)
        setFont(self.subtitle, round(self._px("bodySm")))

        for label in self._section_labels:
            label.setStyleSheet(
                f"QLabel#helpSection {{ color:{layer_txt2};"
                f" font-size:{self._px('caption'):.1f}px; font-weight:600;"
                " background:transparent; }"
            )

        self.shortcut_card.setStyleSheet(
            f"QFrame#helpShortcutCard {{ background:{card}; border:1px solid {border};"
            f" border-radius:{radius}px; }}"
        )
        for head in self._group_heads:
            head.setStyleSheet(
                f"QLabel#helpGroupHead {{ color:{t['accentText']}; background:{subtle};"
                f" font-size:{self._px('captionSm'):.1f}px; font-weight:600;"
                f" padding:11px 18px 8px 18px; border-bottom:1px solid {divider}; }}"
            )
        for row in self._rows:
            row.setStyleSheet(
                f"QFrame#helpRow {{ background:transparent;"
                f" border-bottom:1px solid {divider}; }}"
                f"QFrame#helpRow:hover {{ background:{subtle}; }}"
            )
        for cap in self._keycaps:
            cap.setStyleSheet(
                f"QLabel#helpKeycap {{ color:{txt1}; background:{ctrl_bg};"
                f" border:1px solid {ctrl_bd}; border-bottom-color:{ctrl_bd_bottom};"
                f" border-radius:4px; padding:4px 9px; font-family:{_MONO};"
                f" font-size:{self._px('captionSm'):.1f}px; font-weight:600; }}"
            )
        for desc in self._descs:
            desc.setStyleSheet(
                f"QLabel#helpDesc {{ color:{txt2}; background:transparent;"
                f" font-size:{self._px('bodySm'):.1f}px; }}"
            )

        for feature in self._feature_cards:
            feature.setStyleSheet(
                f"QFrame#helpFeatureCard {{ background:{card};"
                f" border:1px solid {border}; border-radius:{radius}px; }}"
                f"QFrame#helpFeatureCard:hover {{ background:{card_hover};"
                f" border-color:{border_hover}; }}"
            )
        for head in self._feature_titles:
            head.setStyleSheet(
                f"QLabel#helpFeatureTitle {{ color:{txt1}; background:transparent;"
                f" font-size:{self._px('body'):.1f}px; font-weight:600; }}"
            )
        for text in self._feature_bodies:
            text.setStyleSheet(
                f"QLabel#helpFeatureBody {{ color:{txt2}; background:transparent;"
                f" font-size:{self._px('caption'):.1f}px; }}"
            )

    def _px(self, role: str) -> float:
        return theme.fluent_font_px(role, self._size_key)
