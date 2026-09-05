"""판독 페이지.

앱의 주 화면. 기준 layer 사진 한 장과 비교 layer 사진들을 나란히 놓고 같은 defect 인지 본다.

세로 순서는 시안(DefectTracker-Redesign.dc.html, docs/adr/0001) 그대로다.
  조건 행 44 / (스캔 진행 줄) / 판독대(남는 높이 전부) / 하단 바 112(색인 · 필름스트립 · 담기).
페이지 제목·부제는 두지 않는다. 판독대가 남는 높이를 전부 가져가는 것이 이 화면의 전부이므로
그 위아래는 모두 고정 높이다. 좌우 여백 20 은 각 띠가 스스로 갖는다(조건 행의 경계선이 페이지
끝까지 닿아야 하기 때문).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    IconWidget,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    isDarkTheme,
    qconfig,
    setCustomStyleSheet,
)

from app.ui import theme
from app.ui.compare_grid import CompareGrid
from app.ui.controls import NavBar, SideBar
from app.ui.thumbnail_strip import ThumbnailStrip
from app.ui.widgets import mono_font

_EMPTY_TITLE = "LOT 폴더를 선택하세요"
_EMPTY_BODY = (
    "LOT 을 열고 기준 layer 를 고르면 기준 defect 을 다른 layer 의 같은 자리와 비교합니다. "
    "layer · wafer 폴더를 골라도 LOT 폴더로 자동 보정됩니다."
)
_RECENT_HEAD = "최근 LOT"
_BODY_PAD_X = 20
_RECENT_ROW_H = 36


class _RecentRow(PushButton):
    """최근 LOT 한 줄: 이름(굵게) + 경로(등폭·흐리게). 누르면 그 LOT 을 연다."""

    chosen = Signal(str)

    def __init__(self, folder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.folder = folder
        self.setFixedHeight(_RECENT_ROW_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(folder)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(10)
        self.name = QLabel(Path(folder).name, self)
        self.name.setObjectName("recentName")
        lay.addWidget(self.name, 0)
        self.path = QLabel(str(Path(folder).parent), self)
        self.path.setObjectName("recentPath")
        self.path.setFont(mono_font(11.5))
        lay.addWidget(self.path, 1)
        self.clicked.connect(lambda: self.chosen.emit(self.folder))
        self._apply_tokens()
        qconfig.themeChanged.connect(self._apply_tokens)

    def _apply_tokens(self, *_args) -> None:
        t = theme.fluent_tokens(isDarkTheme())
        rule = (
            "PushButton {{ background: transparent; border: none; border-radius: 6px;"
            " text-align: left; }}"
            "PushButton:hover {{ background: {0}; }}"
        )
        setCustomStyleSheet(
            self,
            rule.format(theme.flatten(theme.fluent_tokens(False)["subtle"],
                                      theme.fluent_tokens(False)["layer"])),
            rule.format(theme.flatten(theme.fluent_tokens(True)["subtle"],
                                      theme.fluent_tokens(True)["layer"])),
        )
        layer = t["layer"]
        self.name.setStyleSheet(
            f"color:{theme.flatten(t['txt1'], layer)}; font-size:13px; font-weight:600;"
            " background:transparent;"
        )
        self.path.setStyleSheet(
            f"color:{theme.flatten(t['txt2'], layer)}; background:transparent;"
        )


class EmptyState(QWidget):
    """LOT 미선택 상태. 다음 행동(LOT 열기 / 최근 LOT)을 한 화면에서 고르게 한다."""

    open_requested = Signal()
    recent_chosen = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("reviewEmptyState")
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)
        outer.setSpacing(0)

        box = QWidget(self)
        box.setFixedWidth(440)
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setAlignment(Qt.AlignHCenter)
        col.setSpacing(14)

        icon = IconWidget(FluentIcon.FOLDER, box)
        icon.setFixedSize(44, 44)
        col.addWidget(icon, 0, Qt.AlignHCenter)

        self.title = QLabel(_EMPTY_TITLE, box)
        self.title.setObjectName("emptyTitle")
        self.title.setAlignment(Qt.AlignCenter)
        col.addWidget(self.title)

        body = BodyLabel(_EMPTY_BODY, box)
        body.setObjectName("dim")
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignCenter)
        col.addWidget(body)

        self.btn_open = PrimaryPushButton("LOT 폴더 열기", box)
        self.btn_open.setMinimumHeight(theme.fluent_height("primary"))
        self.btn_open.setToolTip("Ctrl+O · 버튼 우클릭으로도 최근 폴더를 엽니다")
        self.btn_open.clicked.connect(self.open_requested)
        col.addWidget(self.btn_open, 0, Qt.AlignHCenter)

        # 최근 LOT 목록. 없으면 머리글도 숨긴다.
        self.recent_head = CaptionLabel(_RECENT_HEAD, box)
        self.recent_head.setObjectName("dim")
        self.recent_head.setContentsMargins(10, 8, 0, 0)
        col.addWidget(self.recent_head)
        self._recent_host = QWidget(box)
        self._recent_rows = QVBoxLayout(self._recent_host)
        self._recent_rows.setContentsMargins(0, 0, 0, 0)
        self._recent_rows.setSpacing(2)
        col.addWidget(self._recent_host)
        self._rows: list[_RecentRow] = []
        self.set_recents([])

        outer.addWidget(box)
        self._apply_tokens()
        qconfig.themeChanged.connect(self._apply_tokens)

    def set_recents(self, folders: list[str]) -> None:
        """최근 LOT 폴더 목록(최신 순). 존재하는 폴더만 넘길 것."""
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        for folder in folders[:5]:
            row = _RecentRow(folder, self._recent_host)
            row.chosen.connect(self.recent_chosen)
            self._recent_rows.addWidget(row)
            self._rows.append(row)
        has = bool(self._rows)
        self.recent_head.setVisible(has)
        self._recent_host.setVisible(has)

    def recent_folders(self) -> list[str]:
        return [row.folder for row in self._rows]

    def _apply_tokens(self, *_args) -> None:
        t = theme.fluent_tokens(isDarkTheme())
        self.title.setStyleSheet(
            f"color:{theme.flatten(t['txt1'], t['layer'])}; font-size:20px; font-weight:600;"
            " letter-spacing:-0.3px; background:transparent;"
        )


class ReviewPage(QWidget):
    """판독 라우트. 위젯을 만들어 두고 배선은 MainWindow 가 한다."""

    def __init__(self, image_loader, sidebar_width: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("reviewInterface")

        self.stack = QStackedWidget(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.stack)

        self.empty_state = EmptyState(self)
        self.content = QWidget(self)
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.content)

        self._build_content(image_loader)
        self.show_empty_state(True)

    # ------------------------------------------------------------ 구성
    def _build_content(self, image_loader) -> None:
        main = QVBoxLayout(self.content)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        self.sidebar = SideBar(self.content)
        main.addWidget(self.sidebar)
        main.addWidget(self._build_progress_row())
        main.addWidget(self._build_grid_area(image_loader), 1)
        main.addWidget(self._build_bottom_bar())

        # 별칭: 하단 바가 소유하지만 창은 짧은 이름으로 쓴다.
        self.btn_add_export = self.nav.btn_add_export
        # 보기 수 "(24개 · 제외 3)" 는 조건 행 오른쪽에 있다.
        self.lbl_view = self.sidebar.lbl_view
        # SLOT·die 는 기준 카드 머리의 링크다(A12). 웨이퍼 맵 위젯은 히트맵 페이지가 흡수했다.
        self.lbl_wafer = self.grid.base_cell.die_link
        # 창 크기 저장 계약(splitter.sizes)을 위해 남기지만 화면에는 없다.
        self.splitter = None

    def _build_progress_row(self) -> QWidget:
        host = QWidget(self.content)
        row = QHBoxLayout(host)
        row.setContentsMargins(_BODY_PAD_X, 4, _BODY_PAD_X, 0)
        row.setSpacing(theme.SPACING["gapS"])
        self.progress = ProgressBar(host)
        self.progress.setVisible(False)
        row.addWidget(self.progress, 1)
        # 스캔 중단은 계승 필수 항목이다.
        self.btn_stop = PushButton("■ 중단", host)
        self.btn_stop.setFixedHeight(theme.fluent_height("control"))
        self.btn_stop.setToolTip("진행 중인 스캔을 중단합니다.")
        self.btn_stop.setVisible(False)
        row.addWidget(self.btn_stop, 0)
        return host

    def _build_grid_area(self, image_loader) -> QWidget:
        host = QWidget(self.content)
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(_BODY_PAD_X, theme.SPACING["gapM"], _BODY_PAD_X, 0)
        host_layout.setSpacing(0)
        self.grid = CompareGrid(loader=image_loader, parent=host)
        # 판독대가 남는 높이를 전부 가져간다. 비교 열이 넘치면 그 열만 스크롤한다.
        host_layout.addWidget(self.grid, 1)
        self.grid_message = BodyLabel("", host)
        self.grid_message.setObjectName("dim")
        self.grid_message.setAlignment(Qt.AlignCenter)
        self.grid_message.setMinimumHeight(200)
        self.grid_message.hide()
        host_layout.addWidget(self.grid_message)
        # 옛 이름. 스크롤은 이제 판독대 안(비교 열)에 있다.
        self.grid_scroll = self.grid.scroll
        return host

    def _build_bottom_bar(self) -> QWidget:
        self.nav = NavBar(self.content)
        self.strip = ThumbnailStrip(self.nav)
        self.strip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.nav.add_widget(self.strip, 1)
        return self.nav

    # ------------------------------------------------------------ 상태
    def show_empty_state(self, empty: bool) -> None:
        """LOT 이 없으면 빈 상태, 있으면 판독 화면."""
        self.stack.setCurrentWidget(self.empty_state if empty else self.content)

    def is_empty_state(self) -> bool:
        return self.stack.currentWidget() is self.empty_state

    def sidebar_width(self) -> int:
        """옛 창 지오메트리 계약. 사이드바가 없어졌으므로 0."""
        return 0
