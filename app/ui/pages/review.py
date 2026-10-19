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

from PySide6.QtCore import Qt, QTimer, Signal
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
from app.ui.controls import NavBar, SideBar, split_depth
from app.ui.flow_layout import FlowLayout
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


class GridNotice(QWidget):
    """판독대 자리에 대신 서는 안내판.

    기준 layer 를 아직 안 골랐거나 기준 사진이 하나도 없을 때 판독대는 빈 검은 상자만 남았다.
    무엇을 해야 하는지 문장으로 말하고, 기준을 고르는 경우에는 layer 버튼을 바로 내민다(콤보를
    찾아 열 필요가 없게). 추천 layer 하나만 accent 채움이다(강조는 한 화면에 하나).
    """

    layer_chosen = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("gridNotice")
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)
        box = QWidget(self)
        box.setFixedWidth(520)
        self._box = box
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)
        self.title = QLabel("", box)
        self.title.setAlignment(Qt.AlignCenter)
        col.addWidget(self.title)
        self.body = BodyLabel("", box)
        self.body.setObjectName("dim")
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignCenter)
        col.addWidget(self.body)
        self._buttons_host = QWidget(box)
        self._flow = FlowLayout(self._buttons_host, h_spacing=8, v_spacing=8, center=True)
        col.addWidget(self._buttons_host)
        self._buttons: list[PushButton] = []
        outer.addWidget(box)
        self._apply_tokens()
        qconfig.themeChanged.connect(self._apply_tokens)

    def set_notice(
        self,
        title: str,
        body: str = "",
        layers: list[str] | None = None,
        counts: dict[str, int] | None = None,
        recommended: str = "",
    ) -> None:
        self.title.setText(title)
        self.body.setText(body)
        self.body.setVisible(bool(body))
        for button in self._buttons:
            self._flow.removeWidget(button)
            button.setParent(None)
            button.deleteLater()
        self._buttons = []
        counts = counts or {}
        for layer in layers or []:
            canonical, depth = split_depth(layer)
            label = canonical + (f" · {depth}" if depth else "")
            if layer in counts:
                label += f"  {counts[layer]}장"
            cls = PrimaryPushButton if layer == recommended else PushButton
            button = cls(label, self._buttons_host)
            button.setFixedHeight(theme.fluent_height("primary"))
            button.setToolTip(
                f"{layer} 을 기준으로 봅니다" + (" (추천)" if layer == recommended else "")
            )
            button.clicked.connect(lambda _=False, l=layer: self.layer_chosen.emit(l))
            self._flow.addWidget(button)
            self._buttons.append(button)
        self._buttons_host.setVisible(bool(self._buttons))
        self._sync_heights()
        QTimer.singleShot(0, self._sync_heights)

    def _sync_heights(self) -> None:
        """줄바꿈 글과 버튼 줄의 높이를 폭에서 다시 잡는다.

        가운데 정렬 레이아웃은 sizeHint 만 보고 높이를 주므로, 그대로 두면 본문 셋째 줄과
        둘째 줄 버튼이 잘린다.
        """
        width = self._box.width()
        self.body.setMinimumHeight(self.body.heightForWidth(width) if self.body.text() else 0)
        self._buttons_host.setMinimumHeight(
            self._flow.heightForWidth(width) if self._buttons else 0
        )

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self._sync_heights()

    def layer_buttons(self) -> list[PushButton]:
        return list(self._buttons)

    def _apply_tokens(self, *_args) -> None:
        t = theme.fluent_tokens(isDarkTheme())
        self.title.setStyleSheet(
            f"color:{theme.flatten(t['txt1'], t['layer'])}; font-size:18px; font-weight:600;"
            " background:transparent;"
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
        # 판독대와 안내판이 같은 자리를 번갈아 쓴다.
        self.grid_stack = QStackedWidget(host)
        self.grid = CompareGrid(loader=image_loader, parent=self.grid_stack)
        self.grid_notice = GridNotice(self.grid_stack)
        self.grid_stack.addWidget(self.grid)
        self.grid_stack.addWidget(self.grid_notice)
        # 판독대가 남는 높이를 전부 가져간다. 비교 열이 넘치면 그 열만 스크롤한다.
        host_layout.addWidget(self.grid_stack, 1)
        # 옛 이름(본문 라벨).
        self.grid_message = self.grid_notice.body
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

    def show_grid_notice(self, title: str, body: str = "", **layer_choice) -> None:
        """판독대 대신 안내판을 세운다. layer_choice 는 GridNotice.set_notice 인자."""
        self.grid_notice.set_notice(title, body, **layer_choice)
        self.grid_stack.setCurrentWidget(self.grid_notice)
        # 볼 사진이 없으면 "0 / 0" 과 꺼진 버튼뿐인 하단 바도 거둔다.
        self.nav.setVisible(False)

    def show_grid(self) -> None:
        self.grid_stack.setCurrentWidget(self.grid)
        self.nav.setVisible(True)

    def is_grid_notice(self) -> bool:
        return self.grid_stack.currentWidget() is self.grid_notice

    def sidebar_width(self) -> int:
        """옛 창 지오메트리 계약. 사이드바가 없어졌으므로 0."""
        return 0
