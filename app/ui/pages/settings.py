"""설정 페이지.

원본은 저장/취소가 있는 모달이었다. Fluent 설정은 카드마다 즉시 반영이라 저장 버튼이 없다.
대신 원본 보호 규칙(작업공간이 LOT 폴더 안이면 차단)을 "고르는 순간" 판정해 값 자체를 받지
않는다. 잘못된 값이 저장 버튼을 누를 때까지 화면에 남아 있으면 사용자는 그것이 적용된 줄 안다.

카드 순서는 REVIEW-01 A8 확정 순서다. 제품 프로파일은 디바이스 DB 바로 아래(같은 성격의
지오메트리 입력), 글자 크기는 테마 아래(표시 설정)에 둔다.

높이는 A9 대로 하한으로 다룬다. qfluentwidgets 의 SettingCard 는 고정 높이 70/50 이라
글자 크기 '크게'(1.3배)에서 글자가 잘리므로, 크게에서는 최소 높이를 올리고 최대 높이를 푼다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEasingCurve, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    ExpandGroupSettingCard,
    FluentIcon,
    HyperlinkButton,
    IndicatorPosition,
    InfoBar,
    InfoBarPosition,
    MessageBox,
    PushButton,
    PushSettingCard,
    SegmentedWidget,
    SettingCard,
    SettingCardGroup,
    SmoothScrollArea,
    SwitchButton,
    Theme,
    TitleLabel,
    isDarkTheme,
    qconfig,
    setCustomStyleSheet,
    setFont,
    setTheme,
    setThemeColor,
)

from app import __version__, config
from app.config import AppSettings
from app.safety import conflicting_source
from app.ui import theme

_PAGE_TITLE = "설정"
_PAGE_SUB = "경로 · 표시 · 동작"

# 그룹·카드 제목. 테스트가 이 순서를 그대로 확인한다(REVIEW-01 A8).
GROUP_PATHS = "경로 · 데이터"
GROUP_DISPLAY = "표시 · 동작"
CARD_ORDER: list[tuple[str, list[str]]] = [
    (GROUP_PATHS, ["작업공간 폴더", "출력 폴더", "디바이스 DB", "제품 프로파일"]),
    (GROUP_DISPLAY, ["테마", "글자 크기", "업데이트", "개발자 모드"]),
]

# 원본 보호 안내. 원본(LOT) 폴더 안에는 어떤 것도 쓰지 않는다는 절대 규칙의 사용자 문구다.
LOT_CONFLICT_MESSAGE = (
    "{label} 폴더가 현재 LOT 폴더 내부에 있습니다. 원본 보호를 위해 "
    "원본 밖의 폴더를 선택하세요."
)
_EMPTY_WORKSPACE_MESSAGE = "작업공간 폴더를 지정하세요."

# 첫 실행 테마 안내(REVIEW-01 A10). 기본이 라이트로 바뀐 것을 한 번만 알린다.
THEME_NOTICE_TITLE = "새 화면으로 바뀌었습니다"
THEME_NOTICE_BODY = (
    "어두운 화면을 쓰시려면 설정 · 표시 · 동작에서 다크로 바꿀 수 있습니다."
)
_THEME_NOTICE_MS = 6000

_THEME_OPTIONS = [("light", "라이트"), ("dark", "다크")]
_FONT_OPTIONS = [("normal", "보통"), ("large", "크게")]

# 경로는 등폭으로 읽는다(02 §2). 사진 카드와 같은 글꼴 목록.
_MONO_FAMILIES = ["Cascadia Mono", "Consolas", "monospace"]
_UNSET_HEIGHT = 16777215  # QWIDGETSIZE_MAX. 고정 높이를 하한으로 되돌릴 때 쓴다.
# 02 §2 의 굵기 600. PySide6 setFont 는 정수 대신 QFont.Weight 를 받는다.
_W600 = QFont.Weight.DemiBold


def _easing(key: str) -> QEasingCurve.Type:
    """모션 토큰 이름을 Qt easing 으로 바꾼다."""
    return getattr(QEasingCurve.Type, theme.MOTION[key][1])


def _titles(cards: list[QWidget]) -> list[str]:
    """카드 제목 목록. 펼침 카드는 제목을 머리 카드가 갖는다."""
    return [getattr(card, "card", card).titleLabel.text() for card in cards]


def apply_theme_mode(mode: str) -> bool:
    """테마를 즉시 반영하고 다크 여부를 돌려준다.

    아직 Fluent 로 옮기지 않은 화면은 브리지 QSS 색에 기대고 있으므로 테마와 함께 다시 만든다.
    빼먹으면 전환 후 옛 다이얼로그만 반대 테마로 남는다.
    """
    dark = (mode or "light").lower() == "dark"
    setTheme(Theme.DARK if dark else Theme.LIGHT)
    setThemeColor(theme.ACCENT_BASE)
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(theme.build_bridge_qss(dark))
    return dark


def theme_notice_pending(settings: AppSettings) -> bool:
    """첫 실행 테마 안내를 아직 보여주지 않았는지 판정한다(A10).

    저장 파일에 theme_mode 키가 없으면 다크만 쓰던 판(또는 새 설치)이다. 별도 플래그를 만들지
    않는 이유는 키가 생기는 순간이 곧 "안내를 마쳤다"는 뜻이라 상태가 하나로 유지되기 때문이다.
    """
    path = Path(settings.settings_file())
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return "theme_mode" not in raw


def ask_update(parent: QWidget, status=None) -> bool:
    """새 버전을 지금 적용할지 묻는다(03-screens §10). True 면 지금 업데이트.

    창의 `_on_update_checked` 가 쓰던 순수 Qt QMessageBox.question 을 대체한다. parent 는
    실제 창이어야 한다(Fluent 팝업은 부모 위에 스크림을 깐다).
    """
    remote = getattr(status, "remote", None)
    lines = []
    if remote:
        lines.append(f"최신 커밋 {str(remote)[:7]} 을 내려받아 적용합니다.")
    lines.append("업데이트 후 프로그램이 종료됩니다. 다시 시작하면 적용됩니다.")
    box = MessageBox("새 버전이 있습니다", "\n".join(lines), parent)
    box.yesButton.setText("지금 업데이트")
    box.cancelButton.setText("나중에")
    box.widget.setFixedWidth(440)
    return bool(box.exec())


def show_update_notice(parent: QWidget, title: str, content: str) -> None:
    """업데이트 결과처럼 선택지가 없는 알림. 확인 버튼 하나만 둔다."""
    box = MessageBox(title, content, parent)
    box.yesButton.setText("확인")
    box.hideCancelButton()
    box.widget.setFixedWidth(440)
    box.exec()


class _PathSettingCard(PushSettingCard):
    """경로 카드. 현재 경로를 등폭으로 보여주고 버튼으로 고른다.

    `text()` / `setText()` 는 옛 다이얼로그가 QLineEdit 을 쓰던 시절의 이름이다. 호출부를
    한꺼번에 바꾸면 회귀 원인을 분리할 수 없어 이름만 남긴다.
    """

    path_changed = Signal(str)

    def __init__(
        self,
        icon,
        title: str,
        placeholder: str,
        value: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("찾아보기", icon, title, placeholder, parent)
        self._placeholder = placeholder
        self._path = ""
        self.set_path(value, notify=False)

    def path(self) -> str:
        return self._path

    def set_path(self, value: str, notify: bool = True) -> None:
        value = (value or "").strip()
        changed = value != self._path
        self._path = value
        self.setContent(value or self._placeholder)
        if changed and notify:
            self.path_changed.emit(value)

    # 옛 이름 유지(호출부 호환).
    def text(self) -> str:
        return self.path()

    def setText(self, value: str) -> None:  # noqa: N802 - Qt 관례 이름
        self.set_path(value)


class _ComboSettingCard(SettingCard):
    """콤보 카드. 목록이 런타임(디바이스 DB)에 따라 바뀌므로 ConfigItem 대신 직접 채운다."""

    current_changed = Signal(object)

    def __init__(self, icon, title: str, content: str, parent: QWidget | None = None) -> None:
        super().__init__(icon, title, content, parent)
        self._loading = False
        self.comboBox = ComboBox(self)
        self.comboBox.setMinimumWidth(220)
        self.hBoxLayout.addWidget(self.comboBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.comboBox.currentIndexChanged.connect(self._on_index_changed)

    def _on_index_changed(self, _index: int) -> None:
        if not self._loading:
            self.current_changed.emit(self.comboBox.currentData())

    def fill(self, items: list[tuple[str, object]], select: object = None) -> None:
        """(표시문구, 데이터) 목록으로 다시 채운다. 채우는 동안은 신호를 내지 않는다."""
        self._loading = True
        self.comboBox.clear()
        for label, data in items:
            # qfluentwidgets ComboBox 는 두 번째 위치 인자가 아이콘이라 데이터는 키워드로 준다.
            self.comboBox.addItem(label, userData=data)
        if select is not None:
            index = self.comboBox.findData(select)
            if index >= 0:
                self.comboBox.setCurrentIndex(index)
        self._loading = False

    def current_data(self) -> object:
        return self.comboBox.currentData()


class _SegmentSettingCard(SettingCard):
    """분절 선택 카드(테마 · 글자 크기). 두 값 중 하나라 콤보보다 분절이 읽기 쉽다."""

    current_changed = Signal(str)

    def __init__(
        self,
        icon,
        title: str,
        content: str,
        options: list[tuple[str, str]],
        current: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(icon, title, content, parent)
        self.segment = SegmentedWidget(self)
        for key, label in options:
            self.segment.addItem(routeKey=key, text=label)
        self._keys = [key for key, _ in options]
        self._loading = False
        self.set_current(current, notify=False)
        self.hBoxLayout.addWidget(self.segment, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.segment.currentItemChanged.connect(self._on_item_changed)

    def _on_item_changed(self, key: str) -> None:
        if not self._loading:
            self.current_changed.emit(key)

    def set_current(self, key: str, notify: bool = True) -> None:
        if key not in self._keys:
            key = self._keys[0]
        self._loading = not notify
        self.segment.setCurrentItem(key)
        self._loading = False

    def current(self) -> str:
        return self.segment.currentRouteKey()


class _DevExpandCard(ExpandGroupSettingCard):
    """개발자 모드 카드. 펼침 250ms / 접힘 150ms 로 토큰에 맞춘다(02 §3).

    기본 구현은 두 방향 모두 200ms 이고, 셰브론 회전은 setExpand 안에서 매번 200ms 로
    되돌리기 때문에 애니메이션을 시작한 뒤 다시 맞춘다.
    """

    def setExpand(self, isExpand: bool) -> None:  # noqa: N802 - 상위 클래스 이름
        if self.isExpand == isExpand:
            return
        key = "rowExpand" if isExpand else "rowCollapse"
        duration = theme.MOTION[key][0]
        self.expandAni.setDuration(duration)
        self.expandAni.setEasingCurve(_easing(key))
        super().setExpand(isExpand)
        rotate = self.card.expandButton.rotateAni
        rotate.stop()
        rotate.setDuration(duration)
        rotate.setEasingCurve(_easing(key))
        rotate.start()


class SettingsPage(QWidget):
    """설정 라우트. 값 변경은 즉시 AppSettings 에 반영하고 저장은 창이 한다."""

    settings_changed = Signal(object)  # AppSettings - 저장 시점은 창이 정한다
    theme_changed = Signal(str)  # "light" / "dark"
    font_size_changed = Signal(str)  # "normal" / "large"
    update_requested = Signal()
    help_requested = Signal()

    def __init__(
        self,
        settings: AppSettings,
        current_lot: Optional[str] = None,
        parent: Optional[QWidget] = None,
        update_available: bool = False,
    ) -> None:
        super().__init__(parent)
        # objectName 은 라우트 키다. 비면 ValueError, 겹치면 라우팅이 깨진다.
        self.setObjectName("settingsInterface")
        self._settings = settings
        self._current_lot = current_lot
        self._wants_update = False
        self._last_error = ""
        self._size_key = getattr(settings, "ui_font_size", "normal") or "normal"
        self._dev_env_forced = config.dev_mode()  # 환경변수 강제(설정보다 우선)

        self._build()
        self.set_update_available(update_available)
        qconfig.themeChanged.connect(self._apply_palette)
        self._apply_size()
        self._apply_palette()

    # ------------------------------------------------------------ 구성
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = SmoothScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        transparent = "SmoothScrollArea { background: transparent; border: none; }"
        setCustomStyleSheet(self.scroll, transparent, transparent)
        self.scroll.viewport().setStyleSheet("background: transparent;")
        outer.addWidget(self.scroll)

        body = QWidget(self.scroll)
        body.setObjectName("settingsBody")
        body.setStyleSheet("QWidget#settingsBody { background: transparent; }")
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
        lay.addSpacing(theme.SPACING["pageV"])

        lay.addWidget(self._build_path_group(body))
        lay.addSpacing(theme.SPACING["pageV"])
        lay.addWidget(self._build_display_group(body))

        self.lbl_error = CaptionLabel("", body)
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setVisible(False)
        lay.addSpacing(theme.SPACING["gapM"])
        lay.addWidget(self.lbl_error)

        lay.addSpacing(theme.SPACING["gapL"])
        lay.addLayout(self._build_footer(body))
        lay.addStretch(1)
        self.scroll.setWidget(body)

    def _build_path_group(self, parent: QWidget) -> SettingCardGroup:
        group = SettingCardGroup(GROUP_PATHS, parent)
        self.group_paths = group

        self.card_workspace = _PathSettingCard(
            FluentIcon.FOLDER, "작업공간 폴더",
            "결과 · 캐시 · 로그를 모아 두는 폴더입니다. 원본(자재/LOT) 폴더에는 "
            "아무것도 쓰지 않으므로 원본 밖에 따로 둡니다",
            self._settings.workspace, group,
        )
        self.card_workspace.clicked.connect(self._pick_workspace)
        self.card_workspace.path_changed.connect(self._on_workspace_changed)

        self.card_output = _PathSettingCard(
            FluentIcon.SAVE_AS, "출력 폴더",
            "Excel 결과만 따로 받을 폴더입니다. 공유 폴더 등 다른 곳에 결과를 바로 "
            "내보낼 때 지정하고, 비우면 작업공간/exports 를 씁니다",
            self._settings.output_folder, group,
        )
        self.card_output.clicked.connect(self._pick_output)
        self.card_output.path_changed.connect(self._on_output_changed)

        self.card_device_db = _PathSettingCard(
            FluentIcon.DOCUMENT, "디바이스 DB",
            "선택 항목. AOIDeviceDB.xlsx 경로", self._settings.device_db_path, group,
        )
        self.card_device_db.clicked.connect(self._pick_device_db)
        self.card_device_db.path_changed.connect(self._on_device_db_changed)

        self.card_product = _ComboSettingCard(
            FluentIcon.TILES, "제품 프로파일",
            "die 배치와 좌표 변환에 사용합니다", group,
        )
        self.card_product.current_changed.connect(self._on_product_changed)

        # 순서는 A8 확정값이다. ExpandLayout 은 담은 위젯을 되돌려 주지 않으므로 직접 기억한다.
        self._path_cards = [
            self.card_workspace, self.card_output, self.card_device_db, self.card_product,
        ]
        for card in self._path_cards:
            group.addSettingCard(card)

        # 시작 시 DB 경로가 있으면 먼저 읽어 목록을 채운다. 없으면 등록된 제품만 보인다.
        if self._settings.device_db_path:
            self._load_device_db(self._settings.device_db_path, quiet=True)
        self.reload_products(select=self._settings.product)
        return group

    def _build_display_group(self, parent: QWidget) -> SettingCardGroup:
        group = SettingCardGroup(GROUP_DISPLAY, parent)
        self.group_display = group

        self.card_theme = _SegmentSettingCard(
            FluentIcon.BRIGHTNESS, "테마", "",
            _THEME_OPTIONS, (self._settings.theme_mode or "light").lower(), group,
        )
        self.card_theme.current_changed.connect(self._on_theme_changed)

        self.card_font = _SegmentSettingCard(
            FluentIcon.FONT_SIZE, "글자 크기", "",
            _FONT_OPTIONS, self._size_key, group,
        )
        self.card_font.current_changed.connect(self._on_font_changed)

        # 자동 확인은 항상 켜져 있다(토글 없음). 이 카드는 수동 확인 버튼만 둔다.
        self.card_update = SettingCard(FluentIcon.UPDATE, "업데이트", "", group)
        self._add_update_action(self.card_update)

        self.card_dev = self._build_dev_card(group)

        self._display_cards = [
            self.card_theme, self.card_font, self.card_update, self.card_dev,
        ]
        for card in self._display_cards:
            group.addSettingCard(card)
        return group

    def _add_update_action(self, card: SettingCard) -> None:
        """업데이트 카드 오른쪽에 수동 확인 버튼을 붙인다(사이드바에서 옮겨 온 기능)."""
        self.lbl_update = CaptionLabel("", card)
        self.lbl_update.setVisible(False)
        self.btn_update = PushButton("업데이트 확인", card)
        self.btn_update.setToolTip("최신 버전(메인 브랜치)으로 업데이트합니다.")
        self.btn_update.clicked.connect(self._on_update_clicked)
        card.hBoxLayout.addWidget(self.lbl_update, 0, Qt.AlignRight)
        card.hBoxLayout.addSpacing(theme.SPACING["gapS"])
        card.hBoxLayout.addWidget(self.btn_update, 0, Qt.AlignRight)
        card.hBoxLayout.addSpacing(16)

    def _build_dev_card(self, parent: QWidget) -> _DevExpandCard:
        card = _DevExpandCard(
            FluentIcon.DEVELOPER_TOOLS, "개발자 모드", "", parent
        )
        dev_on = self._dev_env_forced or bool(getattr(self._settings, "dev_mode", False))
        self._dev_labels: list[tuple[QWidget, QWidget]] = []

        self.sw_dev = SwitchButton(card, IndicatorPosition.RIGHT)
        self.sw_dev.setOnText("켜짐")
        self.sw_dev.setOffText("꺼짐")
        self.sw_dev.setChecked(dev_on)
        if self._dev_env_forced:
            self.sw_dev.setEnabled(False)
            self.sw_dev.setToolTip("환경변수 DEFECT_TRACKER_DEV 로 강제로 켜져 있습니다.")
        self.sw_dev.checkedChanged.connect(self._on_dev_toggled)
        card.addWidget(self.sw_dev)

        self._dev_box = QWidget(card.view)
        dev_lay = QVBoxLayout(self._dev_box)
        dev_lay.setContentsMargins(0, 0, 0, 0)
        dev_lay.setSpacing(0)

        self.btn_log_dir = PushButton("찾아보기", self._dev_box)
        self.btn_log_dir.clicked.connect(self._pick_log_dir)
        self.lbl_log_dir = self._dev_row(
            dev_lay, "로그 저장 경로",
            self._settings.log_dir or "비우면 작업공간/logs 를 씁니다", self.btn_log_dir,
        )
        self.btn_logs = PushButton("폴더 열기", self._dev_box)
        self.btn_logs.setToolTip("좌표 추출 진단(parse_failures.md)과 실행 로그가 있는 폴더")
        self.btn_logs.clicked.connect(self._open_logs)
        self._dev_row(dev_lay, "진단 · 로그", "탐색기로 로그 폴더를 엽니다", self.btn_logs)

        card.addGroupWidget(self._dev_box)
        self._dev_box.setVisible(dev_on)
        return card

    def _dev_row(
        self, layout: QVBoxLayout, title: str, content: str, button: QWidget
    ) -> CaptionLabel:
        """펼침 영역 한 줄. 아이콘 자리만큼 왼쪽을 들여써 카드 제목과 축을 맞춘다."""
        row = QWidget(self._dev_box)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(48, 12, 48, 12)
        lay.setSpacing(theme.SPACING["gapL"])
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        head = BodyLabel(title, row)
        col.addWidget(head)
        sub = CaptionLabel(content, row)
        sub.setWordWrap(True)
        col.addWidget(sub)
        lay.addLayout(col, 1)
        button.setParent(row)
        lay.addWidget(button, 0, Qt.AlignRight)
        layout.addWidget(row)
        self._dev_labels.append((head, sub))
        return sub

    def _build_footer(self, parent: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACING["gapM"])
        self.btn_help = HyperlinkButton(parent)
        self.btn_help.setText("단축키 · 도움말 (F1)")
        self.btn_help.clicked.connect(self.help_requested)
        row.addWidget(self.btn_help, 0, Qt.AlignLeft)
        row.addStretch(1)
        self.lbl_credit = CaptionLabel(
            f"{config.APP_NAME} v{__version__} · {config.CREDITS}", parent
        )
        row.addWidget(self.lbl_credit, 0, Qt.AlignRight)
        return row

    # ------------------------------------------------------------ 값 반영
    def _on_workspace_changed(self, value: str) -> None:
        if self._blocked(workspace=value):
            self.card_workspace.set_path(self._settings.workspace, notify=False)
            return
        self._settings.workspace = value
        self._changed()

    def _on_output_changed(self, value: str) -> None:
        if self._blocked(output=value):
            self.card_output.set_path(self._settings.output_folder, notify=False)
            return
        self._settings.output_folder = value
        self._changed()

    def _on_device_db_changed(self, value: str) -> None:
        self._settings.device_db_path = value
        if value:
            self._load_device_db(value)
        self._changed()

    def _on_log_dir_changed(self, value: str) -> None:
        if self._blocked(log_dir=value):
            return
        self._settings.log_dir = value
        self.lbl_log_dir.setText(value or "비우면 작업공간/logs 를 씁니다")
        self._changed()

    def _on_product_changed(self, data: object) -> None:
        self._settings.product = str(data or config.DEFAULT_PRODUCT)
        self._changed()

    def _on_dev_toggled(self, checked: bool) -> None:
        """개발자 모드. 켤 때만 로그 항목을 펼쳐 보여 준다(꺼져 있으면 볼 이유가 없다)."""
        self._settings.dev_mode = bool(checked)
        self._dev_box.setVisible(bool(checked))
        self.card_dev.setExpand(bool(checked))
        self.card_dev._adjustViewSize()
        self._changed()

    def _on_theme_changed(self, key: str) -> None:
        self._settings.theme_mode = key
        apply_theme_mode(key)
        self.theme_changed.emit(key)
        self._changed()

    def _on_font_changed(self, key: str) -> None:
        self._settings.ui_font_size = key
        app = QApplication.instance()
        if app is not None:
            theme.apply_font_scale(app, theme.scale_for(key))
        self._size_key = key
        self._apply_size()
        self._apply_palette()
        self.font_size_changed.emit(key)
        self._changed()

    def _on_update_clicked(self) -> None:
        """지금 확인/적용. 창이 비동기 흐름을 갖고 있으므로 요청만 올린다."""
        self._wants_update = True
        self.update_requested.emit()

    def _changed(self) -> None:
        self.settings_changed.emit(self._settings)

    # ------------------------------------------------------------ 검증
    def _blocked(
        self,
        workspace: str | None = None,
        output: str | None = None,
        log_dir: str | None = None,
    ) -> bool:
        """바꾸려는 값으로 원본 보호 규칙을 먼저 판정한다. 어기면 값을 받지 않는다."""
        message = self._conflict(
            self._settings.workspace if workspace is None else workspace,
            self._settings.output_folder if output is None else output,
            self._settings.log_dir if log_dir is None else log_dir,
        )
        if message:
            self._error(message)
            return True
        self._clear_error()
        return False

    def _conflict(self, workspace: str, output: str, log_dir: str) -> str | None:
        if not self._current_lot:
            return None
        targets = [(workspace, "작업공간"), (output or workspace, "출력")]
        if self.sw_dev.isChecked():  # 개발자 모드에서만 로그 경로를 쓴다
            targets.append((log_dir or workspace, "로그"))
        for target, label in targets:
            if target and conflicting_source(target, [self._current_lot]) is not None:
                return LOT_CONFLICT_MESSAGE.format(label=label)
        return None

    def validate(self) -> str | None:
        """지금 값이 저장 가능한지. 문제가 있으면 안내 문구를, 없으면 None."""
        if not (self._settings.workspace or "").strip():
            return _EMPTY_WORKSPACE_MESSAGE
        return self._conflict(
            self._settings.workspace, self._settings.output_folder, self._settings.log_dir
        )

    def _error(self, message: str) -> None:
        self._last_error = message
        self.lbl_error.setText(message)
        self.lbl_error.setVisible(True)
        InfoBar.warning(
            title="원본 보호",
            content=message,
            orient=Qt.Vertical,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=theme.INFOBAR_DURATION_MS,
            parent=self.window() or self,
        )

    def _clear_error(self) -> None:
        self._last_error = ""
        self.lbl_error.setVisible(False)

    def last_error(self) -> str:
        return self._last_error

    # ------------------------------------------------------------ 외부 계약
    def updated_settings(self) -> AppSettings:
        """화면 값을 반영한 설정. 저장은 호출 측이 한다(옛 다이얼로그 계약)."""
        self._settings.workspace = self.card_workspace.path()
        self._settings.output_folder = self.card_output.path()
        self._settings.device_db_path = self.card_device_db.path()
        self._settings.product = str(
            self.card_product.current_data() or config.DEFAULT_PRODUCT
        )
        self._settings.theme_mode = self.card_theme.current()
        self._settings.ui_font_size = self.card_font.current()
        self._settings.dev_mode = bool(self.sw_dev.isChecked())
        return self._settings

    def wants_update(self) -> bool:
        return self._wants_update

    def set_update_available(self, available: bool) -> None:
        """업데이트 가용 표식. 버튼 문구와 안내 한 줄만 바꾼다(강조는 nav 배지가 맡는다)."""
        self.btn_update.setText("지금 업데이트" if available else "업데이트 확인")
        self.lbl_update.setText("새 버전이 있습니다" if available else "")
        self.lbl_update.setVisible(bool(available))

    def set_current_lot(self, lot_path: Optional[str]) -> None:
        """현재 LOT 이 바뀌면 원본 보호 판정 기준도 바뀐다."""
        self._current_lot = lot_path

    def card_titles(self) -> list[tuple[str, list[str]]]:
        """그룹별 카드 제목 순서(A8 확정 순서 확인용)."""
        return [
            (self.group_paths.titleLabel.text(), _titles(self._path_cards)),
            (self.group_display.titleLabel.text(), _titles(self._display_cards)),
        ]

    def maybe_show_theme_notice(self) -> bool:
        """첫 실행이면 테마 전환 경로를 1회만 알린다(A10). 알렸으면 True."""
        if not theme_notice_pending(self._settings):
            return False
        InfoBar.info(
            title=THEME_NOTICE_TITLE,
            content=THEME_NOTICE_BODY,
            orient=Qt.Vertical,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=_THEME_NOTICE_MS,
            parent=self.window() or self,
        )
        # 저장 파일에 theme_mode 를 남기는 것이 곧 "안내 완료" 표시다.
        self._settings.theme_mode = (self._settings.theme_mode or "light").lower()
        try:
            self._settings.save()
        except OSError:
            pass
        return True

    # ------------------------------------------------------------ 제품 목록
    def reload_products(self, select: str | None = None) -> None:
        """config.PRODUCTS 로 제품 목록을 다시 채운다.

        익명 기본 프로파일(DEFAULT_PRODUCT)은 실제 디바이스가 아니라 내부 폴백이므로 목록에
        노출하지 않고 '자동 인식' 항목으로 대체한다. 그 항목을 고르면 저장 시 LOT 경로로
        디바이스를 자동 인식한다.
        """
        items: list[tuple[str, object]] = [("자동 인식", config.DEFAULT_PRODUCT)]
        for key, product in config.PRODUCTS.items():
            if key == config.DEFAULT_PRODUCT:
                continue
            items.append((f"{product.name} ({key})", key))
        self.card_product.fill(items, select or self._settings.product)

    def _load_device_db(self, path: str, quiet: bool = False) -> None:
        if not path or not Path(path).exists():
            return
        try:
            from app.device_db import load_device_db

            profiles = load_device_db(path)
            config.register_devices(profiles)
            self.reload_products(select=self._settings.product)
            if not quiet:
                InfoBar.success(
                    title="디바이스 DB",
                    content=f"디바이스 {len(profiles)}개를 읽었습니다.",
                    orient=Qt.Vertical,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=theme.INFOBAR_DURATION_MS,
                    parent=self.window() or self,
                )
        except Exception as exc:  # noqa: BLE001 - 어떤 실패든 사용자에게 알려야 한다
            self._error(f"디바이스 DB 를 읽지 못했습니다: {exc}")

    # ------------------------------------------------------------ 폴더 선택
    def _pick_workspace(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "작업공간 폴더 선택", self.card_workspace.path() or str(Path.home())
        )
        if folder:
            self.card_workspace.set_path(folder)

    def _pick_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "출력 폴더 선택", self.card_output.path() or self.card_workspace.path()
        )
        if folder:
            self.card_output.set_path(folder)

    def _pick_device_db(self) -> None:
        start = self.card_device_db.path() or self.card_workspace.path() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "디바이스 DB(AOIDeviceDB.xlsx) 선택", start, "Excel 파일 (*.xlsx)"
        )
        if path:
            self.card_device_db.set_path(path)

    def _pick_log_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "로그 저장 경로 선택", self._settings.log_dir or self.card_workspace.path()
        )
        if folder:
            self._on_log_dir_changed(folder)

    def _open_logs(self) -> None:
        """진단/로그 폴더(비어 있으면 작업공간/logs)를 탐색기로 연다."""
        base = self._settings.log_dir or ""
        logs = Path(base) if base else Path(self.card_workspace.path() or ".") / "logs"
        try:
            logs.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(logs)))

    # ------------------------------------------------------------ 크기 · 색
    def set_font_size(self, size_key: str) -> None:
        """글자 크기를 밖에서 바꿀 때(창이 설정을 되돌리는 경우 등)."""
        self._size_key = size_key or "normal"
        self.card_font.set_current(self._size_key, notify=False)
        self._apply_size()
        self._apply_palette()

    def control_height(self) -> int:
        """이 화면의 컨트롤 높이. 글자 크기에 따라 A9 높이표에서 가져온다."""
        return theme.fluent_height("control", self._size_key)

    def _apply_size(self) -> None:
        """고정 높이를 하한으로 되돌리고 컨트롤 높이를 표에서 가져온다(A9)."""
        control_h = self.control_height()
        for card in self._all_cards():
            self._relax_card_height(card)
        for button in (
            self.card_workspace.button, self.card_output.button,
            self.card_device_db.button, self.btn_update,
            self.btn_log_dir, self.btn_logs,
        ):
            button.setMinimumHeight(control_h)
        self.card_product.comboBox.setFixedHeight(control_h)
        for card in (self.card_theme, self.card_font):
            card.segment.setMinimumHeight(control_h)

    def _relax_card_height(self, card: QWidget) -> None:
        """SettingCard 의 고정 높이(70/50)를 하한으로 바꾼다. 크게에서 글자가 잘리지 않도록.

        그룹은 ExpandLayout 이라 위젯의 **현재 높이**로 줄을 세운다. 최소 높이만 올려 두면
        카드가 70px 에 머물러 글자가 그대로 잘리므로 실제 높이도 함께 맞춘다.
        """
        head = getattr(card, "card", card)  # 펼침 카드는 머리 카드가 높이를 갖는다
        base = 70 if head.contentLabel.text() else 50
        grow = theme.fluent_height("control", self._size_key) - theme.fluent_height("control")
        height = base + grow
        head.setMaximumHeight(_UNSET_HEIGHT)
        head.setMinimumHeight(height)
        head.resize(head.width(), height)
        if card is not head:  # ExpandGroupSettingCard: 머리 높이만큼 뷰포트를 다시 잡는다
            card.setViewportMargins(0, height, 0, 0)
            inner = card.spaceWidget.height() if card.isExpand else 0
            card.setFixedHeight(height + inner)
        else:
            card.resize(card.width(), height)

    def _all_cards(self) -> list[QWidget]:
        return [
            self.card_workspace, self.card_output, self.card_device_db, self.card_product,
            self.card_theme, self.card_font, self.card_update, self.card_dev,
        ]

    def _apply_palette(self) -> None:
        """색과 글자 크기를 다시 칠한다. 테마 전환·글자 크기 변경의 공통 경로다."""
        light_tokens = theme.fluent_tokens(False)
        dark_tokens = theme.fluent_tokens(True)
        tokens = dark_tokens if isDarkTheme() else light_tokens

        # 페이지 면(layer). 셸의 StackedWidget 이 계산해 내는 색과 같은 값이라 이음매가 없고,
        # 페이지만 따로 띄워도(검증 렌더) 글자가 읽힌다.
        self.setStyleSheet(
            f"QWidget#settingsInterface {{ background-color: {tokens['layer']}; }}"
        )

        setFont(self.title, round(self._px("title")), _W600)
        setFont(self.subtitle, round(self._px("bodySm")))
        setFont(self.group_paths.titleLabel, round(self._px("section")), _W600)
        setFont(self.group_display.titleLabel, round(self._px("section")), _W600)

        # 카드 안 글자는 Fluent qss 가 font 단축속성으로 크기를 못박아 두어 setFont 가 지므로
        # 위젯 시트를 덧붙여(setCustomStyleSheet) 크기만 다시 지정한다.
        # 버튼 높이도 시트에 함께 넣는다. 임시 브리지 QSS 가 앱 전체 QPushButton 의 min-height
        # 를 잡고 있어서, 위젯 시트로 덮지 않으면 다시 칠할 때마다 setMinimumHeight 가 지워진다.
        # QSS min-height 는 내용 높이라 위아래 패딩·테두리를 뺀 값을 준다(순수 Qt 12 / Fluent 13).
        control_h = self.control_height()
        card_qss = (
            f"QLabel {{ font-size: {self._px('body'):.0f}px; }}"
            f"QLabel#contentLabel {{ font-size: {self._px('captionSm'):.0f}px; }}"
            f"QPushButton {{ font-size: {self._px('caption'):.0f}px;"
            f" min-height: {control_h - 12}px;"
            " padding-left: 18px; padding-right: 18px; }"
            f"PushButton {{ min-height: {control_h - 13}px; }}"
        )
        # 경로 카드의 내용은 등폭이다. Fluent qss 가 font 단축속성으로 글꼴까지 못박으므로
        # 크기만 덧쓰면 글꼴 목록이 돌아오지 않는다. 두 값을 한 규칙에 같이 준다.
        mono = ",".join(f"'{name}'" for name in _MONO_FAMILIES)
        path_qss = card_qss + (
            f"QLabel#contentLabel {{ font-size: {self._px('captionSm'):.0f}px;"
            f" font-family: {mono}; }}"
        )
        for card in self._all_cards():
            sheet = path_qss if isinstance(card, _PathSettingCard) else card_qss
            setCustomStyleSheet(card, sheet, sheet)
            # 펼침 카드의 머리 카드는 자기 시트를 따로 갖고 있어 부모 시트가 닿지 않는다.
            head = getattr(card, "card", None)
            if head is not None:
                setCustomStyleSheet(head, card_qss, card_qss)
        for label, sub in getattr(self, "_dev_labels", []):
            setFont(label, round(self._px("bodySm")))
            setFont(sub, round(self._px("captionSm")))
        for item in list(self.card_theme.segment.items.values()) + list(
            self.card_font.segment.items.values()
        ):
            setFont(item, round(self._px("caption")), _W600)
        setFont(self.card_product.comboBox, round(self._px("bodySm")))
        setFont(self.btn_help, round(self._px("bodySm")))
        setFont(self.lbl_credit, round(self._px("captionSm")))
        setFont(self.lbl_update, round(self._px("captionSm")))
        setFont(self.lbl_error, round(self._px("caption")))

        # 작은 내용 텍스트는 txt3, 오류는 danger. 두 테마 값을 함께 넘겨 전환에 따라오게 한다.
        self.lbl_credit.setTextColor(
            QColor(theme.flatten(light_tokens["txt3"], light_tokens["layer"])),
            QColor(theme.flatten(dark_tokens["txt3"], dark_tokens["layer"])),
        )
        self.lbl_update.setTextColor(
            QColor(light_tokens["accentText"]), QColor(dark_tokens["accentText"])
        )
        self.lbl_error.setTextColor(
            QColor(light_tokens["danger"]), QColor(dark_tokens["danger"])
        )
        self.subtitle.setTextColor(
            QColor(theme.flatten(light_tokens["txt2"], light_tokens["layer"])),
            QColor(theme.flatten(dark_tokens["txt2"], dark_tokens["layer"])),
        )

    def _px(self, role: str) -> float:
        return theme.fluent_font_px(role, self._size_key)
