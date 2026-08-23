"""판독 페이지.

앱의 주 화면. 기준 layer 사진 한 장과 비교 layer 사진들을 나란히 놓고 같은 defect 인지 본다.

단계 1a 에서는 기존 위젯 구성(사이드바 + 필름스트립 + 그리드)을 그대로 옮겨 담아 셸 전환의
회귀 위험을 줄인다. 컨트롤 행·판독대 다열화·빈 칸 사유 복원은 단계 2 에서 이 파일 안에서 한다.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import BodyLabel, CaptionLabel, PrimaryPushButton, PushButton, SubtitleLabel

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

        self._build_content(image_loader, sidebar_width)
        self.show_empty_state(True)

    # ------------------------------------------------------------ 구성
    def _build_content(self, image_loader, sidebar_width: int) -> None:
        main = QVBoxLayout(self.content)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(theme.SPACING["gapS"])

        self.splitter = QSplitter(Qt.Horizontal, self.content)
        self.sidebar = SideBar()
        self.splitter.addWidget(self.sidebar)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(theme.SPACING["gapS"])

        right_layout.addWidget(self._build_top_band())
        right_layout.addLayout(self._build_progress_row())
        right_layout.addWidget(self._build_grid_area(image_loader), 1)

        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setCollapsible(0, False)
        width = max(180, int(sidebar_width))
        self.splitter.setSizes([width, max(600, 1200 - width)])
        main.addWidget(self.splitter, 1)

    def _build_top_band(self) -> QWidget:
        band = QFrame()
        band.setObjectName("panel")
        layout = QVBoxLayout(band)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACING["gapS"])
        self.strip = ThumbnailStrip()
        row.addWidget(self.strip, 1)

        self.btn_heatmap = QPushButton("히트맵 보기")
        self.btn_heatmap.setFixedSize(96, 96)
        self.btn_heatmap.setToolTip(
            "defect 밀도 히트맵을 엽니다. 위치를 클릭하면 그 자리의 defect 을 layer 별로 "
            "나란히 비교하고 출력에 담을 수 있습니다."
        )
        self.btn_heatmap.setEnabled(False)
        row.addWidget(self.btn_heatmap, 0, Qt.AlignVCenter)

        wafer_box = QVBoxLayout()
        wafer_box.setContentsMargins(0, 0, 0, 0)
        wafer_box.setSpacing(2)
        self.wafer_map = WaferMapWidget()
        wafer_box.addWidget(self.wafer_map, 0, Qt.AlignHCenter)
        self.lbl_wafer = QLabel("")
        self.lbl_wafer.setObjectName("dim")
        self.lbl_wafer.setAlignment(Qt.AlignCenter)
        self.lbl_wafer.setWordWrap(True)
        self.lbl_wafer.setFixedWidth(140)
        wafer_box.addWidget(self.lbl_wafer, 0, Qt.AlignHCenter)
        row.addLayout(wafer_box)
        layout.addLayout(row)

        self.nav = NavBar()
        self.btn_add_export = QPushButton("＋ 출력에 담기")
        self.btn_add_export.setObjectName("mini")
        self.btn_add_export.setToolTip(
            "현재 기준 사진을 출력 명세에 담습니다. (A)\n"
            "담은 것들은 Excel 출력 시 함께 나옵니다."
        )
        self.btn_add_export.setEnabled(False)
        self.nav.add_widget(self.btn_add_export)
        self.lbl_view = QLabel("")
        self.lbl_view.setObjectName("dim")
        self.nav.add_widget(self.lbl_view)
        layout.addWidget(self.nav)
        return band

    def _build_progress_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACING["gapS"])
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        row.addWidget(self.progress, 1)
        # 스캔 중단은 계승 필수 항목이다.
        self.btn_stop = QPushButton("■ 중단")
        self.btn_stop.setObjectName("mini")
        self.btn_stop.setToolTip("진행 중인 스캔을 중단합니다.")
        self.btn_stop.setVisible(False)
        row.addWidget(self.btn_stop, 0)
        return row

    def _build_grid_area(self, image_loader) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        host = QFrame()
        host.setObjectName("panel")
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(12, 12, 12, 12)
        self.grid = CompareGrid(loader=image_loader)
        host_layout.addWidget(self.grid)
        self.grid_message = QLabel("")
        self.grid_message.setObjectName("dim")
        self.grid_message.setAlignment(Qt.AlignCenter)
        self.grid_message.setMinimumHeight(200)
        self.grid_message.hide()
        host_layout.addWidget(self.grid_message)
        host_layout.addStretch()
        scroll.setWidget(host)
        self.grid_scroll = scroll
        return scroll

    # ------------------------------------------------------------ 상태
    def show_empty_state(self, empty: bool) -> None:
        """LOT 이 없으면 빈 상태, 있으면 판독 화면."""
        self.stack.setCurrentWidget(self.empty_state if empty else self.content)

    def is_empty_state(self) -> bool:
        return self.stack.currentWidget() is self.empty_state

    def sidebar_width(self) -> int:
        sizes = self.splitter.sizes()
        return sizes[0] if sizes else 0
