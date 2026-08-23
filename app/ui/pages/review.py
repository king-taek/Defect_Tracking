"""판독 페이지.

앱의 주 화면. 기준 layer 사진 한 장과 비교 layer 사진들을 나란히 놓고 같은 defect 인지 본다.

세로 순서는 프로토타입 그대로다(03-screens §1): 헤더 / 컨트롤 행 40 / 판독대(flex 1) /
탐색 바 44 / 필름스트립 96. 판독대가 남는 높이를 전부 가져가는 것이 이 화면의 전부이므로
그 위아래는 모두 고정 높이다.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    IndeterminateProgressBar,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SmoothScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
    TitleLabel,
)

from app.ui import theme
from app.ui.compare_grid import CompareGrid
from app.ui.controls import NavBar, SideBar
from app.ui.thumbnail_strip import ThumbnailStrip
from app.ui.wafer_map import WaferMapWidget

_EMPTY_TITLE = "LOT 폴더를 선택하세요"
_EMPTY_BODY = (
    "리뷰가 끝난 LOT 폴더를 열면 layer·wafer 구조를 스캔해 기준 사진과 비교 layer 를 "
    "자동으로 매칭합니다."
)
_EMPTY_HINT = "Ctrl+O · 버튼 우클릭으로도 최근 폴더를 엽니다"

_PAGE_TITLE = "판독"
_PAGE_SUB = "기준 layer 의 defect 을 다른 layer 의 같은 자리와 비교합니다"


class EmptyState(QWidget):
    """LOT 미선택 상태. 다음 행동을 한 화면에서 고르게 한다."""

    open_requested = Signal()
    recent_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("reviewEmptyState")
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)
        outer.setSpacing(0)

        box = QWidget(self)
        box.setMaximumWidth(460)
        col = QVBoxLayout(box)
        col.setAlignment(Qt.AlignHCenter)
        col.setSpacing(0)

        title = SubtitleLabel(_EMPTY_TITLE, box)
        title.setAlignment(Qt.AlignCenter)
        col.addWidget(title)
        col.addSpacing(8)

        body = BodyLabel(_EMPTY_BODY, box)
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignCenter)
        col.addWidget(body)
        col.addSpacing(20)

        row = QHBoxLayout()
        row.setSpacing(theme.SPACING["gapS"])
        row.setAlignment(Qt.AlignHCenter)
        self.btn_open = PrimaryPushButton("LOT 폴더 선택", box)
        self.btn_open.setMinimumHeight(theme.fluent_height("primary"))
        self.btn_open.clicked.connect(self.open_requested)
        row.addWidget(self.btn_open)
        self.btn_recent = PushButton("최근 폴더", box)
        self.btn_recent.setMinimumHeight(theme.fluent_height("primary"))
        self.btn_recent.clicked.connect(self.recent_requested)
        row.addWidget(self.btn_recent)
        col.addLayout(row)
        col.addSpacing(16)

        hint = CaptionLabel(_EMPTY_HINT, box)
        hint.setAlignment(Qt.AlignCenter)
        col.addWidget(hint)

        outer.addWidget(box)


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
        main.setContentsMargins(
            theme.SPACING["pageH"], theme.SPACING["pageV"], theme.SPACING["pageH"], 0
        )
        main.setSpacing(theme.SPACING["gapM"])

        main.addLayout(self._build_header())
        self.sidebar = SideBar(self.content)
        main.addWidget(self.sidebar)
        main.addLayout(self._build_progress_row())
        main.addWidget(self._build_grid_area(image_loader), 1)
        main.addWidget(self._build_nav_row())
        main.addWidget(self._build_strip())

        # 별칭: 컨트롤 행이 소유하지만 창은 짧은 이름으로 쓴다.
        self.btn_add_export = self.sidebar.btn_add_export
        self.lbl_wafer = self.nav.lbl_die

        # 히트맵/웨이퍼맵은 단계 6에서 전용 페이지로 옮긴다. 그때까지 nav 라우트가 실제
        # 경로이고, 이 둘은 배선을 끊지 않기 위한 보이지 않는 자리다.
        self.wafer_map = WaferMapWidget(self.content)
        self.wafer_map.hide()
        self.btn_heatmap = PushButton("히트맵 보기", self.content)
        self.btn_heatmap.setEnabled(False)
        self.btn_heatmap.hide()
        # 창 크기 저장 계약(splitter.sizes)을 위해 남기지만 화면에는 없다.
        self.splitter = None

    def _build_header(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACING["gapS"])
        title = TitleLabel(_PAGE_TITLE, self.content)
        row.addWidget(title)
        row.addStretch(1)
        self.lbl_view = CaptionLabel("", self.content)
        self.lbl_view.setObjectName("dim")
        row.addWidget(self.lbl_view)
        col.addLayout(row)
        sub = CaptionLabel(_PAGE_SUB, self.content)
        sub.setObjectName("dim")
        col.addWidget(sub)
        return col

    def _build_progress_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACING["gapS"])
        self.progress = ProgressBar(self.content)
        self.progress.setVisible(False)
        row.addWidget(self.progress, 1)
        # 스캔 중단은 계승 필수 항목이다.
        self.btn_stop = PushButton("■ 중단", self.content)
        self.btn_stop.setFixedHeight(theme.fluent_height("control"))
        self.btn_stop.setToolTip("진행 중인 스캔을 중단합니다.")
        self.btn_stop.setVisible(False)
        row.addWidget(self.btn_stop, 0)
        return row

    def _build_grid_area(self, image_loader) -> QWidget:
        scroll = SmoothScrollArea(self.content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        scroll.viewport().setStyleSheet("background: transparent;")
        host = QWidget(scroll)
        host_layout = QVBoxLayout(host)
        # 오른쪽 여백은 겹쳐 그려지는 스크롤바 자리. 없으면 마지막 열이 가려진다.
        host_layout.setContentsMargins(0, 0, 12, 0)
        host_layout.setSpacing(0)
        self.grid = CompareGrid(loader=image_loader, parent=host)
        # 판독대가 남는 높이를 전부 가져간다. stretch 를 뒤에 두면 칸이 224px 에 붙어 버린다.
        host_layout.addWidget(self.grid, 1)
        self.grid_message = BodyLabel("", host)
        self.grid_message.setObjectName("dim")
        self.grid_message.setAlignment(Qt.AlignCenter)
        self.grid_message.setMinimumHeight(200)
        self.grid_message.hide()
        host_layout.addWidget(self.grid_message)
        scroll.setWidget(host)
        self.grid_scroll = scroll
        return scroll

    def _build_nav_row(self) -> QWidget:
        self.nav = NavBar(self.content)
        return self.nav

    def _build_strip(self) -> QWidget:
        box = QWidget(self.content)
        box.setFixedHeight(96)
        box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, theme.SPACING["gapM"])
        lay.setSpacing(0)
        self.strip = ThumbnailStrip(box)
        lay.addWidget(self.strip)
        return box

    # ------------------------------------------------------------ 상태
    def show_empty_state(self, empty: bool) -> None:
        """LOT 이 없으면 빈 상태, 있으면 판독 화면."""
        self.stack.setCurrentWidget(self.empty_state if empty else self.content)

    def is_empty_state(self) -> bool:
        return self.stack.currentWidget() is self.empty_state

    def sidebar_width(self) -> int:
        """옛 창 지오메트리 계약. 사이드바가 없어졌으므로 0."""
        return 0
