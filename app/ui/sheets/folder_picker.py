"""LOT 폴더 선택 시트 (03-screens §7).

이 화면의 문제는 트리가 아니라 규모다. 자재 폴더 아래에 LOT 이 수백 개, 그 아래에 layer·wafer
가 또 수십 개씩 있어서 한 칸씩 걸어 들어가면 시간이 다 간다. 그래서 세 가지 점프로 걷기를
대체한다.

1. `BreadcrumbBar` - 세그먼트를 눌러 그 위치로, 우클릭으로 그 위치의 형제 폴더로 바로 간다.
2. 즐겨찾기(Device 계층만) + 최근 + 스캔 데이터 바로가기. Device 만 받는 이유는 LOT·wafer 를
   고정하면 목록이 금세 쓰레기통이 되고, 실제로 반복해 여는 자리는 Device 뿐이기 때문이다.
3. 현 위치 하위를 자동 판별해 LOT 후보를 목록 위로 올린다. 나머지는 '기타 폴더' 아래로 내린다.

성능 규칙(계승): 목록은 언제나 `os.scandir` **한 단계**만 부른다. 재귀 스캔은 폴더가 수백 개인
자재 폴더에서 창이 멈추기 때문에 금지다. LOT 후보 판별은 그보다 두 겹 더 봐야 하므로 UI 스레드가
아니라 `QThreadPool` 로 미루고, 결과는 폴더별로 캐시하며, 폴더를 옮기면 토큰을 올려 늦게 도착한
결과를 버린다.

판정(고른 폴더가 LOT 인가)은 하단 고정 행 하나에만 쓴다. 원본은 배너 면 전체가 4색으로 바뀌어
화면이 통째로 흔들렸다. 재설계는 색을 칩 하나에만 쓰고 사유와 수치는 회색으로 둔다.

원본 폴더에는 아무것도 쓰지 않는다(읽기 전용).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QDir,
    QEvent,
    QModelIndex,
    QObject,
    QPoint,
    QRunnable,
    QSize,
    QStorageInfo,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QSizePolicy,
    QStyleOptionViewItem,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qframelesswindow import FramelessDialog
from qfluentwidgets import (
    Action,
    BodyLabel,
    BreadcrumbBar,
    CaptionLabel,
    FluentIcon,
    HyperlinkButton,
    IndeterminateProgressRing,
    LineEdit,
    ListItemDelegate,
    ListWidget,
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    SearchLineEdit,
    StrongBodyLabel,
    TeachingTip,
    TeachingTipTailPosition,
    TogglePushButton,
    ToolTipFilter,
    TransparentToolButton,
    TreeWidget,
    isDarkTheme,
    qconfig,
    setCustomStyleSheet,
)

from app import config, scanner
from app.ui import theme

_NUM_RE = re.compile(r"(\d+)")


def natural_key(name: str) -> list:
    """자연 정렬 키 - 숫자 부분을 정수로 비교해 '2.'가 '10.'보다 앞에 오게 한다.

    예) 1., 2., ..., 10., 11., ..., 21. (사전식 1., 10., 11., 2. 방지)
    """
    return [int(t) if t.isdigit() else t.lower() for t in _NUM_RE.split(name)]


# 수치는 등폭으로 쓴다(자릿수가 흔들리면 목록에서 눈이 다시 자리를 찾아야 한다).
_MONO = "'Cascadia Mono', 'Consolas', 'Menlo', 'DejaVu Sans Mono', monospace"
_MONO_FAMILIES = ("Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono", "monospace")

_RAIL_W = 236          # 프로토타입 좌측 레일 폭
_SHEET_W = 960
_SHEET_H = 620

# 목록 항목 데이터 역할. Qt.UserRole 은 '현재 폴더 기준 상대 이름' 이라는 기존 계약을 지킨다.
_SUB_ROLE = Qt.UserRole + 10    # 오른쪽 등폭 부제(layer n · wafer n)
_RANK_ROLE = Qt.UserRole + 11   # 정렬 순위

RANK_LOT = 0      # LOT 후보(하위에 layer/wafer 두 겹이 있다)
RANK_UNSURE = 1   # 판별 전이거나 읽지 못함
RANK_OTHER = 2    # layer·wafer·잡폴더 - 아래로 강등

# 한 폴더에서 판별·검색할 하위 폴더 수 상한. 네트워크 드라이브에서 수천 개를 훑으면 백그라운드
# 여도 몇 분이 걸린다. 상한을 넘는 항목은 순위 없이 이름순으로 남는다.
_PROBE_LIMIT = 600
_DEEP_LIMIT = 300
# 형제 폴더 점프 메뉴에 세울 항목 수 상한(그 이상은 이름으로 찾는 편이 빠르다).
_MENU_LIMIT = 60

# 즐겨찾기 안내(TeachingTip)를 앱 실행당 한 번만 띄우기 위한 표시. 설정 파일에 새 필드를
# 만들지 않는 이유는 이 안내가 '한 번 보면 되는 것' 이지 사용자가 관리할 값이 아니기 때문이다.
_TIP_SHOWN = False

# 최근·즐겨찾기 상한(계승).
_RECENT_MAX = 5
_FAVORITE_MAX = 10
# 레일에 한 번에 보일 행 수. 나머지는 스크롤한다 - 레일이 길어지면 아래 위치 트리가 잘린다.
_FAV_ROWS = 4
_RECENT_ROWS = 3

# 판정별 (칩 문구, 칩 글자 토큰, 칩 배경 토큰). 색은 이 칩 하나에만 쓴다.
_VERDICT_CHIP: dict[str, tuple[str, str, str]] = {
    "material": ("LOT", "pass", "passBg"),
    "layerwafer": ("LOT 보정", "info", "infoBg"),
    "material_parent": ("상위", "warn", "warnBg"),
    "too_high": ("상위", "warn", "warnBg"),
    "unknown": ("?", "txt2", "subtle"),
    "busy": ("확인", "txt2", "subtle"),
    "none": ("?", "txt2", "subtle"),
}


def _entry_stats(path: Path) -> tuple[list[str], int]:
    """path 바로 아래의 (하위 폴더 이름들, 이미지 파일 수). scandir 1회."""
    dirs: list[str] = []
    images = 0
    try:
        with os.scandir(path) as it:
            for e in it:
                try:
                    if e.is_dir():
                        if not e.name.startswith("."):
                            dirs.append(e.name)
                    elif e.is_file() and Path(e.name).suffix.lower() in config.IMAGE_EXTENSIONS:
                        images += 1
                except OSError:
                    continue
    except OSError:
        return ([], 0)
    dirs.sort(key=natural_key)
    return (dirs, images)


def _subdir_count(path: Path) -> int:
    """path 바로 아래 폴더 수(싸게 os.scandir 1회)."""
    return len(_entry_stats(path)[0])


def _first_subdir(path: Path) -> Optional[Path]:
    dirs, _ = _entry_stats(path)
    return path / dirs[0] if dirs else None


def has_dir_chain(path: Path, depth: int, breadth: int = 2) -> bool:
    """path 아래로 폴더가 depth 단계 더 이어지는가(앞의 breadth 개만 보고 조기 종료).

    우클릭 메뉴처럼 즉답이 필요한 자리에서 쓴다. scanner.classify_selection 은 레벨마다 24개씩
    훑기 때문에 잡폴더에서는 최악 1만 번대 scandir 이 되고, 그 대기는 네트워크 드라이브에서
    그대로 멈춤으로 보인다.
    """
    if depth <= 0:
        return True
    for name in _entry_stats(path)[0][:breadth]:
        if has_dir_chain(path / name, depth - 1, breadth):
            return True
    return False


def _samples(names: list[str], count: int) -> list[str]:
    """앞·가운데·뒤에서 골고루 뽑는다. 첫 폴더가 하필 '00_요약' 같은 잡폴더면 한 번의 표본으로
    폴더 전체를 오판하기 때문이다."""
    if len(names) <= count:
        return list(names)
    step = max(1, len(names) // count)
    return [names[min(i * step, len(names) - 1)] for i in range(count)]


def probe_folder(path: Path, samples: int = 3) -> tuple[int, str]:
    """폴더 하나를 (순위, 부제) 로 판별한다. 하위를 한 단계씩 최대 세 번 따라간다.

    구조는 `Device/LOT/layer/wafer/사진` 이다. 세 겹을 봐야 LOT(layer/wafer/사진)과
    Device(LOT/layer/wafer)를 가를 수 있다. 두 겹만 보면 둘 다 '하위의 하위가 폴더' 라서 Device
    가 LOT 후보로 올라온다.

    표본은 최대 samples 개의 하위 폴더뿐이고 확신이 서면 즉시 멈춘다. 전수 조사는 LOT 이 수백
    개인 자재 폴더에서 그대로 수백 배가 된다. 확정 판정은 고른 뒤 판정 행이 한 번만 한다
    (scanner.classify_selection).

    Returns:
        (순위, 부제) - 순위는 RANK_LOT(LOT 후보) / RANK_UNSURE(Device·판별 불가) /
        RANK_OTHER(layer·wafer·빈 폴더 같은 막다른 길).
    """
    dirs, images = _entry_stats(path)
    if not dirs:
        return (RANK_OTHER, f"사진 {images}") if images else (RANK_OTHER, "빈 폴더")
    best: Optional[tuple[int, str]] = None
    for name in _samples(dirs, samples):
        inner_dirs, inner_images = _entry_stats(path / name)
        cand: Optional[tuple[int, str]] = None
        if not inner_dirs:
            # 하위가 사진을 직접 들고 있으면 path 는 layer, 아무것도 없으면 표본 실패.
            if inner_images:
                cand = (RANK_OTHER, f"wafer {len(dirs)}")
        else:
            deep_dirs, deep_images = _entry_stats(path / name / inner_dirs[0])
            if deep_dirs:
                cand = (RANK_UNSURE, f"LOT {len(dirs)}")   # 세 겹 아래도 폴더 = Device 계층
            elif deep_images:
                cand = (RANK_LOT, f"layer {len(dirs)} · wafer {len(inner_dirs)}")
        if cand is not None and (best is None or cand[0] < best[0]):
            best = cand
        if best is not None and best[0] == RANK_LOT:
            break
    return best if best is not None else (RANK_UNSURE, f"폴더 {len(dirs)}")


class _ProbeSignals(QObject):
    # token, folder, {name: (rank, sub)}
    done = Signal(int, str, object)


class _ProbeWorker(QRunnable):
    """현 위치 하위를 LOT 후보인지 백그라운드로 판별한다(목록 정렬용).

    UI 스레드에서 돌리면 폴더 수백 개 × scandir 세 번이 그대로 멈춤이 된다. 폴더를 옮기면
    token 이 달라져 결과가 버려진다.
    """

    def __init__(self, token: int, folder: str, names: list[str]):
        super().__init__()
        self.token = token
        self.folder = folder
        self.names = names[:_PROBE_LIMIT]
        self.signals = _ProbeSignals()

    @Slot()
    def run(self) -> None:
        base = Path(self.folder)
        out: dict[str, tuple[int, str]] = {}
        for name in self.names:
            try:
                out[name] = probe_folder(base / name)
            except Exception:  # noqa: BLE001 - 한 폴더의 실패가 목록 전체를 막지 않는다
                out[name] = (RANK_UNSURE, "")
        self.signals.done.emit(self.token, self.folder, out)


class _DeepSignals(QObject):
    # token, folder, [상대 경로]
    done = Signal(int, str, object)


class _DeepWorker(QRunnable):
    """'하위 1단계 포함' 검색용 목록. 한 겹만 더 나열하고 재귀하지 않는다."""

    def __init__(self, token: int, folder: str, names: list[str]):
        super().__init__()
        self.token = token
        self.folder = folder
        self.names = names[:_DEEP_LIMIT]
        self.signals = _DeepSignals()

    @Slot()
    def run(self) -> None:
        base = Path(self.folder)
        out: list[str] = []
        for name in self.names:
            for child in _entry_stats(base / name)[0]:
                out.append(os.path.join(name, child))
        self.signals.done.emit(self.token, self.folder, out)


class _ValidateSignals(QObject):
    # token, kind, material_path, layer_count, wafer_count
    done = Signal(int, str, str, int, int)


class _ValidateWorker(QRunnable):
    """고른 폴더의 구조 판정(classify_selection + layer·wafer 개수).

    하단 판정 행 한 줄을 위한 계산이라 UI 스레드를 막으면 안 된다. 오래된 요청은 token 으로
    UI 에서 버린다.
    """

    def __init__(self, token: int, path: str):
        super().__init__()
        self.token = token
        self.path = path
        self.signals = _ValidateSignals()

    @Slot()
    def run(self) -> None:
        kind, material = scanner.classify_selection(self.path)
        layers = wafers = 0
        try:
            if material is not None and kind in ("material", "layer", "wafer"):
                layers = _subdir_count(material)
                first = _first_subdir(material)
                if first is not None:
                    wafers = _subdir_count(first)
        except Exception:  # noqa: BLE001 - 개수는 부가 정보, 실패해도 판별은 전달
            layers = wafers = 0
        mat_str = str(material) if material is not None else ""
        self.signals.done.emit(self.token, kind, mat_str, layers, wafers)


class _FolderDelegate(ListItemDelegate):
    """폴더 행 - 왼쪽 이름, 오른쪽 등폭 부제(layer n · wafer n).

    행마다 위젯을 만들지 않는 이유는 폴더가 수백 개일 때 위젯 수백 개를 만드는 순간 목록이
    열리지 않기 때문이다. 부제는 그리기로만 얹는다.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._sub_font = QFont()
        self._sub_color = QColor(0, 0, 0)
        self._gap = theme.SPACING["gapM"]
        self.apply_tokens()

    def apply_tokens(self, size_key: Optional[str] = None) -> None:
        tok = theme.fluent_tokens(isDarkTheme())
        font = QFont()
        font.setFamilies(list(_MONO_FAMILIES))
        font.setStyleHint(QFont.Monospace)  # 목록 폰트가 없는 환경에서도 등폭으로 떨어지게
        font.setPixelSize(max(1, round(theme.fluent_font_px("captionSm", size_key))))
        self._sub_font = font
        self._sub_color = QColor(theme.flatten(tok["txt3"], tok["layer"]))

    def _sub_width(self, text: str) -> int:
        return QFontMetrics(self._sub_font).horizontalAdvance(text) + self._gap

    def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex) -> None:  # noqa: N802
        super().initStyleOption(option, index)
        sub = index.data(_SUB_ROLE)
        if not sub:
            return
        # 이름을 먼저 줄여야 부제와 겹치지 않는다(부제는 항상 읽혀야 하는 수치다).
        avail = option.rect.width() - self._sub_width(sub) - self._gap
        if avail > 0:
            metrics = QFontMetrics(option.font)
            option.text = metrics.elidedText(option.text, Qt.ElideRight, avail)

    def paint(self, painter, option, index):  # noqa: D102
        sub = index.data(_SUB_ROLE)
        super().paint(painter, option, index)
        if not sub:
            return
        painter.save()
        painter.setFont(self._sub_font)
        painter.setPen(self._sub_color)
        rect = option.rect.adjusted(0, 0, -self._gap, 0)
        painter.drawText(rect, Qt.AlignRight | Qt.AlignVCenter, sub)
        painter.restore()


class _FavoriteDelegate(ListItemDelegate):
    """즐겨찾기 행 - 이름 앞에 DEV 배지.

    즐겨찾기가 Device 계층만 받는다는 규칙을 목록에서 다시 말해 준다(문구 대신 배지 하나).
    """

    _BADGE_W = 26
    _BADGE_H = 14

    def __init__(self, parent):
        super().__init__(parent)
        self._font = QFont()
        self._fg = QColor()
        self._bg = QColor()
        self.apply_tokens()

    def apply_tokens(self, size_key: Optional[str] = None) -> None:
        tok = theme.fluent_tokens(isDarkTheme())
        font = QFont()
        font.setPixelSize(max(1, round(theme.fluent_font_px("label", size_key))))
        font.setWeight(QFont.Bold)
        self._font = font
        self._fg = QColor(theme.flatten(tok["accentText"], tok["layer"]))
        self._bg = QColor(theme.flatten(tok["accentTint"], tok["layer"]))

    def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex) -> None:  # noqa: N802
        super().initStyleOption(option, index)
        if index.data(Qt.UserRole):
            option.rect.setLeft(option.rect.left() + self._BADGE_W + theme.SPACING["gapS"])

    def paint(self, painter, option, index):  # noqa: D102
        rect = option.rect
        has_badge = bool(index.data(Qt.UserRole))
        left, top, height = rect.left(), rect.top(), rect.height()
        super().paint(painter, option, index)
        if not has_badge:
            return
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._bg)
        y = top + (height - self._BADGE_H) // 2
        painter.drawRoundedRect(left + 4, y, self._BADGE_W, self._BADGE_H, 3, 3)
        painter.setPen(self._fg)
        painter.setFont(self._font)
        painter.drawText(
            left + 4, y, self._BADGE_W, self._BADGE_H, Qt.AlignCenter, "DEV"
        )
        painter.restore()


class _CrumbBar(BreadcrumbBar):
    """경로 막대. 좌클릭은 그 위치로, 우클릭은 그 위치의 형제 폴더 메뉴를 연다.

    형제 점프가 이 화면의 핵심 단축이라 세그먼트마다 붙어 있어야 한다. BreadcrumbBar 는 항목에
    보조 동작이 없으므로 항목에 이벤트 필터를 달아 오른쪽 버튼만 가로챈다(왼쪽 버튼 동작은
    라이브러리 것을 그대로 둔다).
    """

    siblingsRequested = Signal(str)

    def addItem(self, routeKey: str, text: str) -> None:  # noqa: N802, N803
        super().addItem(routeKey, text)
        item = self.item(routeKey)
        if item is not None:
            item.installEventFilter(self)

    def eventFilter(self, obj, event):  # noqa: D102
        etype = event.type()
        if etype in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            if event.button() == Qt.RightButton:
                if etype == QEvent.MouseButtonRelease:
                    self.siblingsRequested.emit(getattr(obj, "routeKey", ""))
                return True  # 이동은 막는다(형제 메뉴만 연다)
        return super().eventFilter(obj, event)


class FolderPickerDialog(FramelessDialog):
    """LOT 폴더 선택 시트.

    공개 계약은 그대로다: `FolderPickerDialog(settings, start_path, parent)` / `exec()` /
    `selected_path()` / `selected_wafer_folder()`. main_window 의 `_choose_folder` 가 이 넷에
    기대고 있다.
    """

    def __init__(self, settings, start_path: str, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setObjectName("folderPickerSheet")
        self.setWindowTitle("LOT 폴더 선택")
        self._size_key = getattr(settings, "ui_font_size", "normal")

        self._pool = QThreadPool.globalInstance()
        self._cur: Path = self._safe_dir(start_path)
        self._history: list[Path] = []
        self._candidate: Optional[Path] = None
        # 마지막 검증 결과 캐시(candidate 경로 기준).
        self._valid_for: Optional[Path] = None
        self._valid_kind: str = ""
        self._valid_material: str = ""
        self._token = 0

        # 하위 판별·검색 캐시와 토큰. 폴더를 옮기면 토큰이 올라가고 늦게 온 결과는 버려진다.
        self._names: list[str] = []
        self._probe_token = 0
        self._probe_cache: dict[str, dict[str, tuple[int, str]]] = {}
        self._deep_cache: dict[str, list[str]] = {}
        self._probing = False
        self._deep_pending: set[str] = set()
        self._deep_shown = False
        self._crumb_guard = False
        self._chip_kind = "none"
        self._tip: Optional[TeachingTip] = None

        self._build_ui()
        self._reload_shortcuts()
        self._go_to(self._cur, push=False)
        self._apply_tokens()
        qconfig.themeChanged.connect(self._apply_tokens)

    # ----------------------------------------------------------- helpers
    @staticmethod
    def _safe_dir(path: str) -> Path:
        try:
            p = Path(path)
            if p.exists() and p.is_dir():
                return p
        except OSError:
            pass
        return Path.home()

    def _list_subdirs(self, path: Path) -> list[str]:
        """한 단계 하위 폴더 이름만 나열(숨김 제외, 자연 정렬). 네트워크에서도 가볍다."""
        return _entry_stats(path)[0]

    def _font_px(self, role: str) -> int:
        return max(1, round(theme.fluent_font_px(role, self._size_key)))

    def _height(self, key: str) -> int:
        return theme.fluent_height(key, self._size_key)

    # ----------------------------------------------------------- UI build
    def _build_ui(self) -> None:
        self.resize(_SHEET_W, _SHEET_H)
        self.setMinimumSize(760, 520)
        title_h = self._height("titleBar")
        self.titleBar.setFixedHeight(title_h)
        self.titleBar.minBtn.hide()
        self.titleBar.maxBtn.hide()
        self.titleBar.setDoubleClickEnabled(False)
        self.lbl_title = StrongBodyLabel("LOT 폴더 선택", self.titleBar)
        self.titleBar.hBoxLayout.insertSpacing(0, theme.SPACING["pageH"])
        self.titleBar.hBoxLayout.insertWidget(1, self.lbl_title, 0, Qt.AlignVCenter)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, title_h, 0, 0)
        root.setSpacing(0)

        root.addLayout(self._build_crumb_row())
        body = QHBoxLayout()
        body.setContentsMargins(
            theme.SPACING["pageH"], theme.SPACING["gapM"],
            theme.SPACING["pageH"], theme.SPACING["gapM"],
        )
        body.setSpacing(theme.SPACING["gapL"])
        body.addWidget(self._build_rail())
        body.addLayout(self._build_list_pane(), 1)
        root.addLayout(body, 1)
        root.addWidget(self._build_footer())

        # 검증 디바운스 - 목록을 훑는 동안 클릭마다 판정이 날아가지 않게 한다.
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self._run_validation)

        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._focus_path_edit)

    def _build_crumb_row(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setContentsMargins(
            theme.SPACING["pageH"], theme.SPACING["gapXs"], theme.SPACING["pageH"], 0
        )
        col.setSpacing(theme.SPACING["gapXs"])

        row = QHBoxLayout()
        row.setSpacing(theme.SPACING["gapXs"])
        self.btn_back = TransparentToolButton(FluentIcon.RETURN, self)
        self.btn_back.setToolTip("이전 폴더로 돌아가기")
        self.btn_back.clicked.connect(self._go_back)
        self.btn_up = TransparentToolButton(FluentIcon.UP, self)
        self.btn_up.setToolTip("상위 폴더로 올라가기")
        self.btn_up.clicked.connect(self._go_up)
        for btn in (self.btn_back, self.btn_up):
            btn.setFixedSize(self._height("control"), self._height("control"))
            btn.installEventFilter(ToolTipFilter(btn, theme.TOOLTIP_DELAY_MS))
            row.addWidget(btn)

        self.crumbs = _CrumbBar(self)
        self.crumbs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.crumbs.setToolTip(
            "세그먼트를 누르면 그 위치로 이동합니다.\n우클릭하면 그 위치의 형제 폴더가 열립니다."
        )
        self.crumbs.installEventFilter(ToolTipFilter(self.crumbs, theme.TOOLTIP_DELAY_MS))
        self.crumbs.currentItemChanged.connect(self._on_crumb)
        self.crumbs.siblingsRequested.connect(self._show_siblings)
        row.addWidget(self.crumbs, 1)

        self.btn_siblings = TransparentToolButton(FluentIcon.ARROW_DOWN, self)
        self.btn_siblings.setToolTip("현재 폴더의 형제 폴더로 이동 (경로 세그먼트 우클릭도 같음)")
        self.btn_siblings.setFixedSize(self._height("control"), self._height("control"))
        self.btn_siblings.clicked.connect(lambda: self._show_siblings(str(self._cur)))
        self.btn_siblings.installEventFilter(
            ToolTipFilter(self.btn_siblings, theme.TOOLTIP_DELAY_MS)
        )
        row.addWidget(self.btn_siblings)

        self.btn_explorer = TransparentToolButton(FluentIcon.FOLDER, self)
        self.btn_explorer.setToolTip(
            "OS 기본 폴더 탐색기로 고르기\n"
            "(네트워크 공유 등 목록에 아직 안 보이는 위치를 여기서 바로 고릅니다.)"
        )
        self.btn_explorer.setFixedSize(self._height("control"), self._height("control"))
        self.btn_explorer.clicked.connect(self._open_native_explorer)
        self.btn_explorer.installEventFilter(
            ToolTipFilter(self.btn_explorer, theme.TOOLTIP_DELAY_MS)
        )
        row.addWidget(self.btn_explorer)

        self.btn_pin = TransparentToolButton(FluentIcon.PIN, self)
        self.btn_pin.setToolTip("현재 폴더를 즐겨찾기에 고정 (Device 폴더만)")
        self.btn_pin.setFixedSize(self._height("control"), self._height("control"))
        self.btn_pin.clicked.connect(self._toggle_favorite)
        self.btn_pin.installEventFilter(ToolTipFilter(self.btn_pin, theme.TOOLTIP_DELAY_MS))
        row.addWidget(self.btn_pin)

        self.lbl_hint = CaptionLabel("우클릭 형제 폴더 · Ctrl+L 경로", self)
        row.addWidget(self.lbl_hint)
        col.addLayout(row)

        self.ed_path = LineEdit(self)
        self.ed_path.setPlaceholderText("경로를 붙여넣고 Enter 를 누르세요")
        self.ed_path.setFixedHeight(self._height("control"))
        self.ed_path.returnPressed.connect(self._on_path_entered)
        self.ed_path.hide()  # Ctrl+L 로만 부른다(평소에는 경로 막대가 자리를 갖는다)
        col.addWidget(self.ed_path)
        return col

    def _build_rail(self) -> QWidget:
        rail = QWidget(self)
        rail.setFixedWidth(_RAIL_W)
        col = QVBoxLayout(rail)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACING["gapXs"])

        fav_head = QHBoxLayout()
        fav_head.setSpacing(theme.SPACING["gapXs"])
        self.lbl_fav = CaptionLabel("즐겨찾기", rail)
        fav_head.addWidget(self.lbl_fav)
        fav_head.addStretch(1)
        self.btn_fav_help = HyperlinkButton("", "추가 방법", rail)
        self.btn_fav_help.clicked.connect(lambda: self._show_favorite_tip(force=True))
        fav_head.addWidget(self.btn_fav_help)
        col.addLayout(fav_head)

        self.fav_list = ListWidget(rail)
        self.fav_delegate = _FavoriteDelegate(self.fav_list)
        self.fav_list.setItemDelegate(self.fav_delegate)
        self.fav_list.setMaximumHeight(self._height("control") * _FAV_ROWS)
        self.fav_list.itemClicked.connect(self._on_shortcut_clicked)
        self.fav_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.fav_list.customContextMenuRequested.connect(
            lambda pos: self._show_shortcut_menu(self.fav_list, pos, favorite=True)
        )
        col.addWidget(self.fav_list)

        col.addWidget(self._divider(rail))
        self.lbl_recent = CaptionLabel("최근", rail)
        col.addWidget(self.lbl_recent)
        self.recent_list = ListWidget(rail)
        self.recent_list.setMaximumHeight(self._height("control") * _RECENT_ROWS)
        self.recent_list.itemClicked.connect(self._on_shortcut_clicked)
        self.recent_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.recent_list.customContextMenuRequested.connect(
            lambda pos: self._show_shortcut_menu(self.recent_list, pos, favorite=False)
        )
        col.addWidget(self.recent_list)

        col.addWidget(self._divider(rail))
        scan_head = QHBoxLayout()
        scan_head.setSpacing(theme.SPACING["gapXs"])
        self.lbl_places = CaptionLabel("스캔 데이터 · 위치", rail)
        scan_head.addWidget(self.lbl_places)
        scan_head.addStretch(1)
        self.btn_scan_pick = HyperlinkButton("", "찾기", rail)
        self.btn_scan_pick.setToolTip("스캔 데이터 폴더를 골라 맨 위에 고정합니다.")
        self.btn_scan_pick.clicked.connect(self._pick_scan_root)
        scan_head.addWidget(self.btn_scan_pick)
        col.addLayout(scan_head)

        scan_row = QHBoxLayout()
        scan_row.setSpacing(theme.SPACING["gapXs"])
        self.ed_scan_root = LineEdit(rail)
        self.ed_scan_root.setText(getattr(self.settings, "scan_root_path", "") or "")
        self.ed_scan_root.setPlaceholderText("스캔 데이터 폴더 경로")
        self.ed_scan_root.setFixedHeight(self._height("control"))
        self.ed_scan_root.returnPressed.connect(self._apply_scan_root)
        scan_row.addWidget(self.ed_scan_root, 1)
        self.btn_goto_scan = PushButton("이동", rail)
        self.btn_goto_scan.setToolTip("지정된 스캔 데이터 폴더로 이동")
        self.btn_goto_scan.setFixedHeight(self.ed_scan_root.sizeHint().height())
        self.btn_goto_scan.clicked.connect(self._goto_scan_root)
        scan_row.addWidget(self.btn_goto_scan, 0)
        col.addLayout(scan_row)

        # 위치 트리: 고정된 스캔 루트 + 홈 + 드라이브. 점프 세 가지로 못 가는 곳(새 드라이브,
        # 네트워크 공유)에 닿는 마지막 경로라서 남긴다. 펼칠 때만 한 단계씩 읽는다.
        self.sidebar = TreeWidget(rail)
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setIndentation(12)  # 기본(~20)은 하위로 갈수록 여백 과다 -> 축소
        self.sidebar.setRootIsDecorated(True)
        self.sidebar.setMinimumHeight(100)
        self.sidebar.itemClicked.connect(self._on_tree_clicked)
        self.sidebar.itemExpanded.connect(self._on_tree_expanded)
        col.addWidget(self.sidebar, 1)
        return rail

    def _build_list_pane(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACING["gapXs"])

        search = QHBoxLayout()
        search.setSpacing(theme.SPACING["gapS"])
        self.ed_filter = SearchLineEdit(self)
        self.ed_filter.setPlaceholderText("이 폴더에서 이름으로 찾기")
        self.ed_filter.setFixedHeight(self._height("control"))
        self.ed_filter.textChanged.connect(self._on_search_changed)
        search.addWidget(self.ed_filter, 1)
        self.btn_deep = TogglePushButton("하위 1단계 포함", self)
        self.btn_deep.setFixedHeight(self._height("control"))
        self.btn_deep.setToolTip(
            "찾기 대상을 하위 한 단계까지 넓힙니다. 재귀는 하지 않습니다."
        )
        self.btn_deep.toggled.connect(self._on_deep_toggled)
        self.btn_deep.installEventFilter(ToolTipFilter(self.btn_deep, theme.TOOLTIP_DELAY_MS))
        search.addWidget(self.btn_deep)
        col.addLayout(search)

        caption = QHBoxLayout()
        caption.setSpacing(theme.SPACING["gapS"])
        self.lbl_candidates = CaptionLabel("LOT 후보", self)
        caption.addWidget(self.lbl_candidates)
        self.lbl_auto = CaptionLabel("하위 구조 자동 판별", self)
        caption.addWidget(self.lbl_auto)
        caption.addStretch(1)
        self.lbl_column = CaptionLabel("layer · wafer", self)
        caption.addWidget(self.lbl_column)
        col.addLayout(caption)

        self.listw = ListWidget(self)
        self.listw.setUniformItemSizes(True)  # 수백 행에서 높이 계산을 한 번만 한다
        self.delegate = _FolderDelegate(self.listw)
        self.listw.setItemDelegate(self.delegate)
        self.listw.itemClicked.connect(self._on_item_clicked)
        self.listw.itemActivated.connect(self._on_item_activated)
        self.listw.itemDoubleClicked.connect(self._on_item_activated)
        self.listw.setContextMenuPolicy(Qt.CustomContextMenu)
        self.listw.customContextMenuRequested.connect(self._show_folder_menu)
        col.addWidget(self.listw, 1)
        return col

    def _build_footer(self) -> QWidget:
        foot = QFrame(self)
        foot.setObjectName("pickerFooter")
        foot.setFixedHeight(64)
        row = QHBoxLayout(foot)
        row.setContentsMargins(theme.SPACING["pageH"], 0, theme.SPACING["pageH"], 0)
        row.setSpacing(theme.SPACING["gapM"])

        self.ring = IndeterminateProgressRing(foot)
        self.ring.setFixedSize(15, 15)
        self.ring.setStrokeWidth(2)
        self.ring.hide()
        row.addWidget(self.ring)

        self.chip = QLabel("?", foot)
        self.chip.setObjectName("verdictChip")
        self.chip.setAlignment(Qt.AlignCenter)
        self.chip.setFixedHeight(22)
        row.addWidget(self.chip)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        self.lbl_verdict = BodyLabel("폴더를 고르면 LOT 여부를 여기서 확인합니다.", foot)
        text_col.addWidget(self.lbl_verdict)
        self.lbl_verdict_sub = QLabel("", foot)
        self.lbl_verdict_sub.setObjectName("verdictSub")
        text_col.addWidget(self.lbl_verdict_sub)
        row.addLayout(text_col)
        row.addStretch(1)

        self.btn_cancel = PushButton("취소", foot)
        self.btn_cancel.setFixedHeight(self._height("control"))
        self.btn_cancel.clicked.connect(self.reject)
        row.addWidget(self.btn_cancel)
        self.btn_ok = PrimaryPushButton("이 폴더 선택", foot)
        self.btn_ok.setFixedHeight(self._height("control"))
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.accept)
        row.addWidget(self.btn_ok)
        return foot

    def _divider(self, parent: QWidget) -> QFrame:
        line = QFrame(parent)
        line.setObjectName("railDivider")
        line.setFixedHeight(1)
        return line

    # ----------------------------------------------------------- 토큰
    def _apply_tokens(self) -> None:
        """색·글자 크기를 토큰에서 다시 칠한다. 테마 전환에도 같은 경로를 탄다."""
        tok = theme.fluent_tokens(isDarkTheme())
        win = tok["win"]
        layer = tok["layer"]
        txt3 = theme.flatten(tok["txt3"], layer)
        divider = theme.flatten(tok["divider"], layer)

        # 시트 면은 layer, 판정·행동이 있는 하단 띠는 win. Fluent 대화상자의 버튼 띠와 같은
        # 단차라서 눈이 '내용'과 '결정'을 자동으로 나눈다.
        self.setStyleSheet(
            f"#folderPickerSheet {{ background-color: {layer}; }}"
            f"#railDivider {{ background: {divider}; border: none; }}"
            f"#pickerFooter {{ background: {win}; border: none;"
            f" border-top: 1px solid {divider}; }}"
            f"#verdictSub {{ color: {txt3}; font-family: {_MONO};"
            f" font-size: {self._font_px('captionSm')}px; background: transparent; }}"
        )
        # 라벨은 라이트·다크 QSS 를 함께 등록한다. 한쪽만 넣으면 테마를 바꾼 순간 이 핸들러가
        # 다시 돌기 전까지 이전 테마의 글자색이 남는다.
        light = theme.fluent_tokens(False)
        dark = theme.fluent_tokens(True)

        def rule(cls: str, key: str, px: int, weight: int, tokens: dict[str, str]) -> str:
            value = (
                tokens[key] if key.startswith("accent")
                else theme.flatten(tokens[key], tokens["layer"])
            )
            return (
                f"{cls} {{ font-size: {px}px; font-weight: {weight}; color: {value};"
                " background: transparent; }"
            )

        for label, key, px, weight in (
            (self.lbl_title, "txt1", self._font_px("section"), 600),
            (self.lbl_fav, "txt2", self._font_px("captionSm"), 600),
            (self.lbl_recent, "txt2", self._font_px("captionSm"), 600),
            (self.lbl_places, "txt2", self._font_px("captionSm"), 600),
            (self.lbl_auto, "txt3", self._font_px("captionSm"), 400),
            (self.lbl_column, "txt3", self._font_px("captionSm"), 600),
            (self.lbl_hint, "txt3", self._font_px("captionSm"), 400),
            (self.lbl_verdict, "txt1", self._font_px("bodySm"), 400),
            # 'LOT 후보 n' 은 이 화면에서 유일한 accent 글자다(강조는 한 화면에 하나).
            (self.lbl_candidates, "accentText", self._font_px("captionSm"), 600),
        ):
            cls = type(label).__name__
            setCustomStyleSheet(
                label,
                rule(cls, key, px, weight, light),
                rule(cls, key, px, weight, dark),
            )
        transparent_list = (
            "QListWidget { background: transparent; border: none; }"
            "QListWidget::item { padding-left: 4px; }"
        )
        for view in (self.listw, self.fav_list, self.recent_list):
            setCustomStyleSheet(view, transparent_list, transparent_list)
        transparent_tree = "QTreeWidget, TreeWidget { background: transparent; border: none; }"
        setCustomStyleSheet(self.sidebar, transparent_tree, transparent_tree)
        self.delegate.apply_tokens(self._size_key)
        self.fav_delegate.apply_tokens(self._size_key)
        self.listw.viewport().update()
        self.fav_list.viewport().update()
        self._paint_chip(self._chip_kind or "none")

    def _paint_chip(self, kind: str) -> None:
        tok = theme.fluent_tokens(isDarkTheme())
        text, fg_key, bg_key = _VERDICT_CHIP.get(kind, _VERDICT_CHIP["none"])
        fg = theme.flatten(tok[fg_key], tok["layer"])
        bg = theme.flatten(tok[bg_key], tok["layer"])
        self.chip.setText(text)
        self.chip.setStyleSheet(
            f"QLabel#verdictChip {{ background: {bg}; color: {fg};"
            f" border-radius: 4px; padding: 0 9px;"
            f" font-size: {self._font_px('captionSm')}px; font-weight: 600; }}"
        )

    # ----------------------------------------------------------- 바로가기 레일
    def _favorites(self) -> list[str]:
        return [
            f for f in getattr(self.settings, "favorite_folders", [])[:_FAVORITE_MAX]
            if Path(f).exists()
        ]

    def _recents(self) -> list[str]:
        return [
            f for f in getattr(self.settings, "recent_folders", [])[:_RECENT_MAX]
            if Path(f).exists()
        ]

    def _reload_shortcuts(self) -> None:
        """즐겨찾기·최근 목록과 위치 트리를 다시 만든다."""
        tok = theme.fluent_tokens(isDarkTheme())
        self.fav_list.clear()
        for path in self._favorites():
            item = QListWidgetItem(Path(path).name or path)
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            item.setSizeHint(QSize(0, self._height("control")))
            self.fav_list.addItem(item)
        if self.fav_list.count() == 0:
            empty = QListWidgetItem("폴더 우클릭으로 추가")
            empty.setFlags(Qt.NoItemFlags)
            empty.setForeground(QColor(theme.flatten(tok["txt3"], tok["layer"])))
            empty.setSizeHint(QSize(0, self._height("control")))
            self.fav_list.addItem(empty)

        self.recent_list.clear()
        for path in self._recents():
            item = QListWidgetItem(Path(path).name or path)
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            item.setSizeHint(QSize(0, self._height("control")))
            self.recent_list.addItem(item)
        if self.recent_list.count() == 0:
            empty = QListWidgetItem("최근 연 LOT 없음")
            empty.setFlags(Qt.NoItemFlags)
            empty.setForeground(QColor(theme.flatten(tok["txt3"], tok["layer"])))
            empty.setSizeHint(QSize(0, self._height("control")))
            self.recent_list.addItem(empty)

        self._fit_rail_list(self.fav_list, _FAV_ROWS)
        self._fit_rail_list(self.recent_list, _RECENT_ROWS)
        self._reload_sidebar()

    @staticmethod
    def _fit_rail_list(view, max_rows: int) -> None:
        """행 수에 맞춰 높이를 고정한다.

        레일에는 즐겨찾기·최근·위치 트리가 함께 서 있어서, 목록이 남는 공간을 다 차지하면
        아래 트리가 한 줄만 남고 잘린다. 반대로 고정 높이만 주면 항목이 하나일 때 빈 상자가
        된다. 그래서 '내용 높이, 단 max_rows 까지' 로 맞춘다.
        """
        rows = max(1, min(view.count(), max_rows))
        row_h = view.sizeHintForRow(0) if view.count() else 0
        if row_h <= 0:
            row_h = theme.HEIGHTS["control"]["normal"]
        view.setFixedHeight(rows * row_h + 2 * view.frameWidth() + 2)

    def _on_shortcut_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if path:
            self._go_to(self._safe_dir(path))

    def _show_shortcut_menu(self, view, pos, favorite: bool) -> None:
        item = view.itemAt(pos)
        path = item.data(Qt.UserRole) if item is not None else None
        if not path:
            return
        menu = RoundMenu(parent=self)
        if favorite:
            action = Action(FluentIcon.UNPIN, "즐겨찾기에서 제거", self)
            action.triggered.connect(lambda _=False, p=path: self._remove_favorite(p))
        else:
            action = Action(FluentIcon.FOLDER, "이 폴더로 이동", self)
            action.triggered.connect(lambda _=False, p=path: self._go_to(self._safe_dir(p)))
        menu.addAction(action)
        menu.exec(view.viewport().mapToGlobal(pos))

    # ----------------------------------------------------------- 위치 트리
    _LOADED = Qt.UserRole + 1  # 지연 로딩 완료 플래그

    def _make_dir_node(self, parent, label: str, path: str):
        """지연 확장 폴더 노드(펼치면 그때 한 단계만 os.scandir). 더미 자식으로 화살표 표시."""
        node = QTreeWidgetItem(parent, [label])
        node.setData(0, Qt.UserRole, path)
        node.setData(0, self._LOADED, False)
        node.setToolTip(0, path)
        QTreeWidgetItem(node, ["..."])  # placeholder -> 펼침 화살표
        return node

    @staticmethod
    def _unc_anchor(s: str) -> str:
        r"""경로의 루트(anchor). UNC(\\server\share)는 플랫폼과 무관하게 공유 루트를 돌려준다."""
        s = str(s)
        if s.startswith("\\\\") or s.startswith("//"):
            sep = "\\" if s[0] == "\\" else "/"
            parts = s.replace("/", "\\").split("\\")  # ['', '', server, share, ...]
            if len(parts) >= 4 and parts[2] and parts[3]:
                return f"{sep}{sep}{parts[2]}{sep}{parts[3]}{sep}"
            return s
        try:
            return Path(s).anchor
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def _drive_label(p: str) -> str:
        """드라이브 표시명 - 네트워크 드라이브는 볼륨 이름·UNC 대상까지 함께 보여준다."""
        drive = p.rstrip("/\\") or p
        name = ""
        dev = ""
        try:
            si = QStorageInfo(p)
            name = si.name() or ""
            raw = si.device()
            try:
                dev = bytes(raw).decode("utf-8", "ignore")
            except Exception:  # noqa: BLE001
                dev = str(raw)
        except Exception:  # noqa: BLE001
            pass
        is_net = dev.startswith("\\\\") or dev.startswith("//")
        extra = []
        if name:
            extra.append(name)
        if is_net and dev:
            extra.append(dev)
        label = drive + (f"  ({' · '.join(extra)})" if extra else "")
        return ("네트워크 " if is_net else "드라이브 ") + label

    def _ensure_root_for(self, path) -> None:
        """path 를 포함하는 최상위 루트가 없으면(예: UNC 네트워크 폴더) 그 루트를 추가한다."""
        anchor = self._unc_anchor(path)
        if not anchor:
            return
        na = anchor.rstrip("/\\")
        for rp, _ in self._root_nodes:
            if str(rp).rstrip("/\\") == na:
                return
        is_net = anchor.startswith("\\\\") or anchor.startswith("//")
        label = ("네트워크 " + anchor) if is_net else self._drive_label(anchor)
        node = self._make_dir_node(self.sidebar.invisibleRootItem(), label, anchor)
        self._root_nodes.append((anchor, node))

    def _pin_scan_roots(self, search_roots: list[str]) -> None:
        """스캔 데이터 폴더를 최상위 고정 노드로 추가.

        1) 명시 지정 경로(scan_root_path)가 있으면 그것을 먼저(맨 위). 2) 이후 각 루트 바로
        아래에서 scan_root_name 폴더를 탐지해 추가(경로 중복 제거).
        """
        root = self.sidebar.invisibleRootItem()
        seen: set[str] = set()
        explicit = (getattr(self.settings, "scan_root_path", "") or "").strip()
        if explicit:
            try:
                ok = Path(explicit).is_dir()
            except OSError:
                ok = False
            if ok:
                key = str(Path(explicit)).rstrip("/\\")
                seen.add(key)
                node = self._make_dir_node(
                    root, f"스캔 {Path(explicit).name or explicit}", explicit
                )
                self._root_nodes.append((explicit, node))
        name = (getattr(self.settings, "scan_root_name", "") or "").strip()
        if not name:
            return
        for r in search_roots:
            try:
                p = Path(r) / name
                if not p.is_dir():
                    continue
            except OSError:
                continue  # 연결 끊긴 드라이브/네트워크 -> 스킵
            key = str(p).rstrip("/\\")
            if key in seen:
                continue
            seen.add(key)
            disp = r.rstrip("/\\") or r
            node = self._make_dir_node(root, f"스캔 {name}  ({disp})", str(p))
            self._root_nodes.append((str(p), node))

    def _reload_sidebar(self) -> None:
        self.sidebar.clear()
        self._root_nodes = []  # (path, node) - 현재 위치 트리 동기화용 루트
        root = self.sidebar.invisibleRootItem()
        favs = self._favorites()
        recents = self._recents()
        search_roots = [str(Path.home())] + [d.absoluteFilePath() for d in QDir.drives()]
        for cand in [str(self._cur), *favs, *recents]:
            a = self._unc_anchor(cand)
            if a and a not in search_roots:
                search_roots.append(a)
        # 1) 스캔 데이터 폴더를 최상위에 고정한다(가장 자주 여는 자리).
        self._pin_scan_roots(search_roots)
        # 2) 홈 + 드라이브. 점프로 못 가는 위치에 닿는 마지막 경로다.
        home = self._make_dir_node(root, "홈", str(Path.home()))
        self._root_nodes.append((str(Path.home()), home))
        for d in QDir.drives():
            p = d.absoluteFilePath()
            self._root_nodes.append((p, self._make_dir_node(root, self._drive_label(p), p)))
        # 3) 네트워크(UNC) 위치는 드라이브 목록에 안 나오므로 앵커 루트를 추가.
        for cand in [str(self._cur), *favs, *recents]:
            self._ensure_root_for(cand)
        self._reveal_in_tree(self._cur)

    def _on_tree_expanded(self, node: QTreeWidgetItem) -> None:
        if node.data(0, self._LOADED):
            return
        path = node.data(0, Qt.UserRole)
        node.takeChildren()  # 더미 제거
        if path:
            for name in self._list_subdirs(Path(path)):
                self._make_dir_node(node, name, str(Path(path) / name))
        node.setData(0, self._LOADED, True)

    def _reveal_in_tree(self, path: Path) -> None:
        """현재 경로를 포함하는 루트를 찾아 세그먼트마다 지연 확장하며 그 노드를 선택·스크롤."""
        roots = getattr(self, "_root_nodes", None)
        if roots is None:
            return
        self._ensure_root_for(path)
        roots = self._root_nodes
        target = Path(path)
        best = None  # 가장 깊은(구체적인) 접두 루트
        for rp, node in roots:
            rpp = Path(rp)
            if target == rpp or rpp in target.parents:
                if best is None or len(str(rpp)) > len(str(Path(best[0]))):
                    best = (rp, node)
        if best is None:
            return
        rp, node = best
        node.setExpanded(True)  # itemExpanded -> 지연 로딩(동기)
        try:
            rel = target.relative_to(Path(rp))
        except ValueError:
            rel = Path()
        cur = node
        for part in rel.parts:
            child = self._find_child_by_name(cur, part)
            if child is None:
                break
            cur = child
            cur.setExpanded(True)
        self.sidebar.setCurrentItem(cur)
        self.sidebar.scrollToItem(cur)

    @staticmethod
    def _find_child_by_name(parent: QTreeWidgetItem, name: str) -> Optional[QTreeWidgetItem]:
        for i in range(parent.childCount()):
            ch = parent.child(i)
            p = ch.data(0, Qt.UserRole)
            if p and Path(p).name == name:
                return ch
        return None

    def _on_tree_clicked(self, node: QTreeWidgetItem, _col: int = 0) -> None:
        path = node.data(0, Qt.UserRole)
        if path:
            self._go_to(self._safe_dir(path))

    # ----------------------------------------------------------- 스캔 데이터 폴더
    def _open_native_explorer(self) -> None:
        """OS 기본 폴더 선택 대화상자로 폴더를 고른다(트리에 안 보이는 네트워크 공유 등)."""
        start = str(self._cur) if self._cur.exists() else str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "폴더 선택 (기본 탐색기)", start)
        if path:
            self._go_to(self._safe_dir(path))

    def _apply_scan_root(self) -> None:
        """지정 칸의 스캔 데이터 폴더 경로를 저장·고정하고 그 폴더로 이동."""
        path = self.ed_scan_root.text().strip()
        self.settings.scan_root_path = path
        self._save_settings()
        self._reload_sidebar()
        if path and Path(path).is_dir():
            self._go_to(self._safe_dir(path))

    def _pick_scan_root(self) -> None:
        start = self.ed_scan_root.text().strip() or str(self._cur)
        if not Path(start).exists():
            start = str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "스캔 데이터 폴더 선택", start)
        if path:
            self.ed_scan_root.setText(path)
            self._apply_scan_root()

    def _goto_scan_root(self) -> None:
        """지정 칸에 이미 저장된 스캔 데이터 폴더 경로로 바로 이동."""
        path = self.ed_scan_root.text().strip()
        if path and Path(path).is_dir():
            self._go_to(self._safe_dir(path))
        else:
            self._set_verdict("too_high", "지정된 스캔 데이터 폴더가 없습니다.", "")

    def _save_settings(self) -> None:
        try:
            self.settings.save()
        except Exception:  # noqa: BLE001 - 저장 실패해도 세션 내 반영은 유지
            pass

    # ----------------------------------------------------------- navigation
    def _go_to(self, path: Path, push: bool = True) -> None:
        path = self._safe_dir(str(path))
        if push and path != self._cur:
            self._history.append(self._cur)
        self._cur = path
        self.ed_path.setText(str(path))
        # 목록을 새로 채우기 직전이라 검색 신호로 옛 목록을 다시 그릴 필요가 없다.
        self.ed_filter.blockSignals(True)
        self.ed_filter.clear()
        self.ed_filter.blockSignals(False)
        self._probe_token += 1  # 이전 폴더의 판별·검색 결과를 버린다
        self._populate_list()
        self._rebuild_crumbs()
        self.btn_back.setEnabled(bool(self._history))
        self.btn_up.setEnabled(path.parent != path)
        self._reveal_in_tree(path)  # 위치 트리를 현재 위치로 확장·강조
        # 현재 폴더 자체를 후보로 삼아 자동 검증(LOT 으로 바로 들어오면 즉시 확인).
        self._set_candidate(path)

    def _go_up(self) -> None:
        if self._cur.parent != self._cur:
            self._go_to(self._cur.parent)

    def _go_back(self) -> None:
        if self._history:
            prev = self._history.pop()
            self._go_to(prev, push=False)

    def _focus_path_edit(self) -> None:
        self.ed_path.setVisible(True)
        self.ed_path.setText(str(self._cur))
        self.ed_path.setFocus()
        self.ed_path.selectAll()

    def _on_path_entered(self) -> None:
        text = self.ed_path.text().strip()
        if not text:
            return
        p = Path(text)
        if p.exists() and p.is_dir():
            self.ed_path.hide()
            self._go_to(p)
        else:
            self._set_verdict("too_high", f"경로를 찾을 수 없습니다: {text}", "")

    def _rebuild_crumbs(self) -> None:
        self._crumb_guard = True  # addItem 이 곧바로 currentItemChanged 를 쏘므로 되돌이를 막는다
        try:
            self.crumbs.clear()
            parts = list(self._cur.parts)
            acc = Path(parts[0]) if parts else self._cur
            for i, part in enumerate(parts):
                if i > 0:
                    acc = acc / part
                label = part.rstrip("/\\") or part
                self.crumbs.addItem(str(acc), label)
        finally:
            self._crumb_guard = False

    def _on_crumb(self, route_key: str) -> None:
        if self._crumb_guard or not route_key:
            return
        if Path(route_key) != self._cur:
            self._go_to(Path(route_key))

    def _siblings_menu(self, path_str: str) -> Optional[RoundMenu]:
        """세그먼트의 형제 폴더 메뉴(부모를 한 단계만 나열)."""
        if not path_str:
            return None
        path = Path(path_str)
        parent = path.parent
        if parent == path:
            return None
        names = self._list_subdirs(parent)
        menu = RoundMenu(parent=self)
        for name in names[:_MENU_LIMIT]:
            target = parent / name
            action = Action(FluentIcon.FOLDER, name, self)
            action.triggered.connect(lambda _=False, t=target: self._go_to(t))
            menu.addAction(action)
        if len(names) > _MENU_LIMIT:
            more = Action(f"이하 {len(names) - _MENU_LIMIT}개 생략 · 이름으로 찾으세요", self)
            more.setEnabled(False)
            menu.addSeparator()
            menu.addAction(more)
        if not names:
            empty = Action("하위 폴더 없음", self)
            empty.setEnabled(False)
            menu.addAction(empty)
        return menu

    def _show_siblings(self, path_str: str) -> None:
        menu = self._siblings_menu(path_str)
        if menu is None:
            return
        item = self.crumbs.item(path_str)
        if item is not None and item.isVisible():
            pos = item.mapToGlobal(QPoint(0, item.height()))
        else:
            pos = QCursor.pos()
        menu.exec(pos)

    # ----------------------------------------------------------- list
    def _populate_list(self) -> None:
        """현재 폴더의 하위 폴더를 한 단계만 나열하고, 판별은 백그라운드에 맡긴다."""
        self._names = self._list_subdirs(self._cur)
        self._render_list()
        key = str(self._cur)
        if key not in self._probe_cache and self._names:
            self._probing = True
            worker = _ProbeWorker(self._probe_token, key, self._names)
            worker.signals.done.connect(self._on_probed)
            self._pool.start(worker)
        else:
            self._probing = False
        self._update_caption()

    def _ranked(self, name: str) -> tuple[int, str]:
        return self._probe_cache.get(str(self._cur), {}).get(name, (RANK_UNSURE, ""))

    def _add_row(self, name: str, rank: int, sub: str) -> None:
        tok = theme.fluent_tokens(isDarkTheme())
        item = QListWidgetItem(name)
        item.setData(Qt.UserRole, name)
        item.setData(_SUB_ROLE, sub)
        item.setData(_RANK_ROLE, rank)
        item.setSizeHint(QSize(0, self._height("navItem")))
        # LOT 후보만 본문 색, 강등된 폴더는 보조 색. 색으로 순위를 한 번 더 말한다.
        color = tok["txt1"] if rank == RANK_LOT else tok["txt2"]
        item.setForeground(QColor(theme.flatten(color, tok["layer"])))
        item.setToolTip(str(self._cur / name))
        self.listw.addItem(item)

    def _add_header(self, text: str) -> None:
        tok = theme.fluent_tokens(isDarkTheme())
        item = QListWidgetItem(text)
        item.setFlags(Qt.NoItemFlags)  # 이름이 없는 항목은 클릭·필터 대상이 아니다
        item.setForeground(QColor(theme.flatten(tok["txt3"], tok["layer"])))
        font = item.font()
        font.setPixelSize(self._font_px("label"))
        font.setWeight(QFont.DemiBold)
        item.setFont(font)
        item.setSizeHint(QSize(0, self._height("navItem")))
        self.listw.addItem(item)

    def _render_list(self) -> None:
        """순위대로 다시 그린다. 선택은 경로로 되살려 재정렬이 자리 이동으로 보이지 않게 한다."""
        keep = None
        cur_item = self.listw.currentItem()
        if cur_item is not None:
            keep = cur_item.data(Qt.UserRole)
        self.listw.clear()
        rows = [(self._ranked(n), n) for n in self._names]
        rows.sort(key=lambda r: (r[0][0], natural_key(r[1])))
        has_lot = any(r[0][0] == RANK_LOT for r in rows)
        seen_other = False
        for (rank, sub), name in rows:
            if rank == RANK_OTHER and not seen_other and has_lot:
                seen_other = True
                self._add_header("기타 폴더")
            self._add_row(name, rank, sub)
        query = self.ed_filter.text().strip()
        deep = (
            self._deep_cache.get(str(self._cur))
            if self.btn_deep.isChecked() and query
            else None
        )
        self._deep_shown = bool(deep)
        if deep:
            self._add_header("하위 1단계")
            for rel in deep:
                self._add_row(rel, RANK_UNSURE, "")
        if self.listw.count() == 0:
            item = QListWidgetItem("하위 폴더 없음 · 이 폴더가 wafer 등 최하위일 수 있습니다")
            item.setFlags(Qt.NoItemFlags)
            tok = theme.fluent_tokens(isDarkTheme())
            item.setForeground(QColor(theme.flatten(tok["txt3"], tok["layer"])))
            item.setSizeHint(QSize(0, self._height("navItem")))
            self.listw.addItem(item)
        if keep:
            for i in range(self.listw.count()):
                if self.listw.item(i).data(Qt.UserRole) == keep:
                    self.listw.setCurrentRow(i)
                    self.listw.scrollToItem(self.listw.item(i))
                    break
        if query:
            self._apply_filter(query)

    def _update_caption(self) -> None:
        cache = self._probe_cache.get(str(self._cur), {})
        lots = sum(1 for v in cache.values() if v[0] == RANK_LOT)
        if self._probing:
            self.lbl_candidates.setText("LOT 후보 확인 중")
        elif cache:
            self.lbl_candidates.setText(f"LOT 후보 {lots}")
        else:
            self.lbl_candidates.setText("LOT 후보")
        if self._probing:
            self.lbl_auto.setText("하위 한 단계씩만 읽습니다")
        elif self.btn_deep.isChecked() and not self.ed_filter.text().strip():
            self.lbl_auto.setText("이름을 입력하면 하위 1단계까지 찾습니다")
        else:
            self.lbl_auto.setText("하위 구조 자동 판별")

    @Slot(int, str, object)
    def _on_probed(self, token: int, folder: str, result: object) -> None:
        """판별 결과 도착.

        결과는 폴더에 딸린 값이라 늦게 와도 캐시에는 남긴다(같은 폴더로 돌아왔을 때 다시 읽지
        않는다). 화면은 지금 보고 있는 폴더의 최신 요청일 때만 다시 그린다 - 토큰이 지난 결과로
        목록을 흔들면 이미 다른 폴더에 있는 사용자의 선택이 튄다.
        """
        self._probe_cache[folder] = dict(result)  # type: ignore[arg-type]
        if token != self._probe_token or folder != str(self._cur):
            return
        self._probing = False
        self._render_list()
        self._update_caption()

    # ----------------------------------------------------------- 검색
    def _apply_filter(self, text: str) -> None:
        """이름으로 숨김만 갱신한다(목록 구성은 건드리지 않는다)."""
        needle = text.strip().lower()
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            name = it.data(Qt.UserRole)
            if name is None:  # 안내·머리 항목은 검색 중에는 감춘다
                it.setHidden(bool(needle))
                continue
            it.setHidden(bool(needle) and needle not in name.lower())

    def _on_search_changed(self, text: str) -> None:
        """검색어 변경. 목록 구성이 달라질 때만 다시 그리고, 아니면 숨김만 갱신한다.

        글자마다 목록을 새로 만들면 폴더가 수백 개일 때 타이핑이 끊긴다.
        """
        want_deep = bool(text.strip()) and self.btn_deep.isChecked()
        if want_deep:
            self._start_deep_search()
        shown_now = bool(want_deep and self._deep_cache.get(str(self._cur)))
        if shown_now != self._deep_shown:
            self._render_list()
        else:
            self._apply_filter(text)
        self._update_caption()

    def _on_deep_toggled(self, checked: bool) -> None:
        if checked and self.ed_filter.text().strip():
            self._start_deep_search()
        self._render_list()
        self._update_caption()

    def _start_deep_search(self) -> None:
        """하위 한 겹을 추가로 나열한다(재귀 아님). 결과는 폴더별로 캐시한다."""
        key = str(self._cur)
        # 글자를 칠 때마다 부르므로 이미 읽었거나 읽는 중이면 다시 시작하지 않는다.
        if key in self._deep_cache or key in self._deep_pending or not self._names:
            return
        self._deep_pending.add(key)
        worker = _DeepWorker(self._probe_token, key, self._names)
        worker.signals.done.connect(self._on_deep_done)
        self._pool.start(worker)

    @Slot(int, str, object)
    def _on_deep_done(self, token: int, folder: str, result: object) -> None:
        self._deep_cache[folder] = list(result)  # type: ignore[arg-type]
        self._deep_pending.discard(folder)
        if token != self._probe_token or folder != str(self._cur):
            return
        if self.btn_deep.isChecked():
            self._render_list()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.UserRole)
        if name is None:
            return
        self._set_candidate(self._cur / name)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.UserRole)
        if name is None:
            return
        self._go_to(self._cur / name)

    # ----------------------------------------------------------- validation
    def _set_candidate(self, path: Path) -> None:
        self._candidate = path
        # 후보가 바뀌는 즉시 이전 후보의 검증을 무효화한다. 토큰은 디바운스 뒤에만 올라가므로,
        # 그 사이 도착한 이전 후보의 판정이 새 후보 이름으로 표시되고 캐시(_valid_*)까지
        # 오염되는 레이스가 있었다(빠른 연속 클릭 시 엉뚱한 폴더가 LOT 으로 표시됨).
        self._token += 1
        self._valid_for = None
        self._valid_kind = ""
        self._update_pin_button()
        self._set_verdict("busy", f"'{path.name or path}' 확인 중", "")
        self._debounce.start()

    def _run_validation(self) -> None:
        if self._candidate is None:
            return
        self._token += 1
        worker = _ValidateWorker(self._token, str(self._candidate))
        worker.signals.done.connect(self._on_validated)
        self._pool.start(worker)

    @Slot(int, str, str, int, int)
    def _on_validated(
        self, token: int, kind: str, material: str, layers: int, wafers: int
    ) -> None:
        if token != self._token or self._candidate is None:
            return  # 오래된 결과 무시
        self._valid_for = self._candidate
        self._valid_kind = kind
        self._valid_material = material
        name = self._candidate.name or str(self._candidate)
        counts = f"layer {layers} · wafer {wafers}"
        if kind == "material":
            self._set_verdict("material", f"'{name}' 를 선택할 수 있습니다", counts)
            self.btn_ok.setEnabled(True)
        elif kind in ("layer", "wafer"):
            mat_name = Path(material).name if material else "?"
            self._set_verdict(
                "layerwafer",
                f"{kind} 폴더입니다 · 선택하면 상위 LOT '{mat_name}' 로 보정합니다",
                counts,
            )
            self.btn_ok.setEnabled(True)
        elif kind == "material_parent":
            self._set_verdict(
                "material_parent",
                f"'{name}' 는 Device 폴더입니다 · 안의 LOT 폴더를 고르세요",
                "즐겨찾기에 추가할 수 있는 계층",
            )
            self.btn_ok.setEnabled(False)
        elif kind == "too_high":
            self._set_verdict(
                "too_high", f"'{name}' 는 상위 폴더입니다 · LOT 폴더로 들어가세요", ""
            )
            self.btn_ok.setEnabled(False)
        else:  # unknown
            self._set_verdict(
                "unknown", f"'{name}' 에서 사진을 찾지 못했습니다 · 그래도 선택할 수 있습니다", ""
            )
            self.btn_ok.setEnabled(True)
        self._update_pin_button()

    def _set_verdict(self, kind: str, text: str, sub: str) -> None:
        """하단 고정 판정 행. 색은 칩 하나에만 쓰고 사유·수치는 회색으로 둔다."""
        self._chip_kind = kind
        self._paint_chip(kind)
        self.lbl_verdict.setText(text)
        self.lbl_verdict_sub.setText(sub)
        self.lbl_verdict_sub.setVisible(bool(sub))
        busy = kind == "busy"
        self.ring.setVisible(busy)
        # 숨긴 스피너가 계속 돌면 목록을 훑는 내내 CPU 를 먹는다.
        (self.ring.start if busy else self.ring.stop)()

    # ----------------------------------------------------------- favorites
    def _is_device_folder(self, path) -> bool:
        """즐겨찾기 대상인가. Device(자재) 계층만 받는다.

        LOT·wafer 를 고정하면 목록이 금세 일회용 경로로 가득 차고, 반복해 여는 자리는 Device
        하나다. 판정은 구조로 한다(classify_selection 의 material_parent).
        """
        try:
            kind, _ = scanner.classify_selection(str(path))
        except Exception:  # noqa: BLE001
            return False
        return kind == "material_parent"

    def _add_favorite(self, path) -> bool:
        """Device 폴더만 즐겨찾기에 넣는다. 상한 10개(계승)."""
        if not self._is_device_folder(path):
            self._set_verdict(
                "too_high",
                "즐겨찾기는 Device 폴더만 받습니다 · LOT·wafer 폴더는 대상이 아닙니다",
                "",
            )
            return False
        favs = [f for f in getattr(self.settings, "favorite_folders", []) if f != str(path)]
        favs.insert(0, str(path))
        self.settings.favorite_folders = favs[:_FAVORITE_MAX]
        self._save_settings()
        self._reload_shortcuts()
        self._update_pin_button()
        return True

    def _remove_favorite(self, path) -> None:
        favs = [f for f in getattr(self.settings, "favorite_folders", []) if f != str(path)]
        self.settings.favorite_folders = favs
        self._save_settings()
        self._reload_shortcuts()
        self._update_pin_button()

    def _update_pin_button(self) -> None:
        target = str(self._candidate or self._cur)
        favs = list(getattr(self.settings, "favorite_folders", []))
        pinned = target in favs
        self.btn_pin.setIcon(FluentIcon.UNPIN if pinned else FluentIcon.PIN)
        self.btn_pin.setToolTip(
            "즐겨찾기에서 제거" if pinned else "현재 폴더를 즐겨찾기에 고정 (Device 폴더만)"
        )
        # 고정은 Device 계층에서만 열어 준다. 판정이 아직 없으면(확인 중) 그대로 둔다.
        if pinned or self._valid_kind == "material_parent":
            self.btn_pin.setEnabled(True)
        elif self._valid_kind:
            self.btn_pin.setEnabled(False)

    def _toggle_favorite(self) -> None:
        """현재 후보를 즐겨찾기에 넣거나 뺀다(고정 버튼용).

        Device 계층 제한은 버튼 활성 상태로 건다. 이 메서드 자체는 조건 없이 토글한다 -
        제거는 어떤 계층이든 언제나 가능해야 하기 때문이다.
        """
        target = str(self._candidate or self._cur)
        favs = list(getattr(self.settings, "favorite_folders", []))
        if target in favs:
            favs.remove(target)
        else:
            favs.insert(0, target)
        self.settings.favorite_folders = favs[:_FAVORITE_MAX]
        self._save_settings()
        self._reload_shortcuts()
        self._update_pin_button()

    def _looks_like_device(self, path) -> bool:
        """메뉴를 열 때 쓰는 싼 Device 판별(LOT/layer/wafer 세 겹이 더 있는가).

        확정 판정은 즐겨찾기에 넣는 순간 `_is_device_folder` 가 한 번만 한다. 메뉴는 우클릭
        즉시 떠야 하므로 여기서 정확도 대신 속도를 고른다.
        """
        try:
            return has_dir_chain(Path(path), 3)
        except OSError:
            return False

    def _folder_menu(self, path) -> RoundMenu:
        """폴더 우클릭 메뉴. 즐겨찾기 추가는 Device 계층에서만 열린다."""
        menu = RoundMenu(parent=self)
        favs = list(getattr(self.settings, "favorite_folders", []))
        if str(path) in favs:
            action = Action(FluentIcon.UNPIN, "즐겨찾기에서 제거", self)
            action.triggered.connect(lambda _=False, p=path: self._remove_favorite(p))
            menu.addAction(action)
        else:
            action = Action(FluentIcon.PIN, "즐겨찾기에 추가", self)
            action.setEnabled(self._looks_like_device(path))
            if not action.isEnabled():
                action.setToolTip("Device 폴더만 추가할 수 있습니다")
            action.triggered.connect(lambda _=False, p=path: self._add_favorite(p))
            menu.addAction(action)
        menu.addSeparator()
        open_action = Action(FluentIcon.FOLDER, "이 폴더 열기", self)
        open_action.triggered.connect(lambda _=False, p=path: self._go_to(self._safe_dir(str(p))))
        menu.addAction(open_action)
        return menu

    def _show_folder_menu(self, pos) -> None:
        item = self.listw.itemAt(pos)
        name = item.data(Qt.UserRole) if item is not None else None
        if not name:
            return
        target = self._cur / name
        self._set_candidate(target)
        self._folder_menu(target).exec(self.listw.viewport().mapToGlobal(pos))

    # ----------------------------------------------------------- 안내
    def showEvent(self, event):  # noqa: D102
        super().showEvent(event)
        if not self._favorites():
            QTimer.singleShot(0, self._show_favorite_tip)

    def _show_favorite_tip(self, force: bool = False) -> None:
        """즐겨찾기 추가 방법을 한 번만 알린다.

        앱을 켜고 처음 이 시트를 열 때(그리고 즐겨찾기가 비어 있을 때)만 뜬다. 이미 즐겨찾기를
        쓰고 있는 사용자에게 같은 안내를 반복하지 않기 위해서다. '추가 방법'을 누르면 언제든
        다시 볼 수 있다.
        """
        global _TIP_SHOWN
        if not force and _TIP_SHOWN:
            return
        if not self.isVisible():
            return  # 아직 안 뜬 창에 붙이면 팁이 화면 밖에 그려진다(표시는 다음 기회로)
        _TIP_SHOWN = True
        try:
            self._tip = TeachingTip.create(
                target=self.btn_fav_help,
                title="즐겨찾기에 추가",
                content=(
                    "Device 폴더에서 우클릭 후 '즐겨찾기에 추가' 를 고르세요. "
                    "LOT·wafer 폴더는 대상이 아니며, 추가한 항목은 DEV 배지로 구분됩니다."
                ),
                isClosable=True,
                duration=-1,
                tailPosition=TeachingTipTailPosition.TOP,
                parent=self,
            )
        except Exception:  # noqa: BLE001 - 안내가 실패해도 선택 흐름은 계속된다
            self._tip = None

    # ----------------------------------------------------------- result
    def _remember_recent(self, folder: str) -> None:
        """최근 연 LOT 폴더를 앞에 넣고 5개로 자른다(계승)."""
        if not folder:
            return
        recents = [f for f in getattr(self.settings, "recent_folders", []) if f != folder]
        recents.insert(0, folder)
        self.settings.recent_folders = recents[:_RECENT_MAX]
        self._save_settings()

    def accept(self) -> None:  # noqa: D102
        self._remember_recent(self.selected_path())
        super().accept()

    def selected_path(self) -> str:
        """선택 확정 시 반환할 LOT 경로(보정 포함). 취소·부적합이면 빈 문자열."""
        target = self._candidate or self._cur
        # 마지막 검증이 현재 후보에 대한 것이면 캐시 사용, 아니면 동기 재판정.
        if self._valid_for == target and self._valid_kind:
            kind, material = self._valid_kind, self._valid_material
        else:
            k, m = scanner.classify_selection(target)
            kind, material = k, (str(m) if m is not None else "")
        if kind == "material":
            return str(target)
        if kind in ("layer", "wafer") and material:
            return material
        if kind == "unknown":
            return str(target)
        return ""  # material_parent / too_high / none

    def _resolved_kind(self) -> str:
        """마지막 후보의 구조 판정(material/layer/wafer/material_parent/too_high/unknown)."""
        target = self._candidate or self._cur
        if self._valid_for == target and self._valid_kind:
            return self._valid_kind
        kind, _ = scanner.classify_selection(target)
        return kind

    def selected_wafer_folder(self) -> str:
        """wafer 폴더를 직접 골랐다면 그 폴더 경로, 아니면 빈 문자열.

        호출 측이 '개별 wafer 만 볼지' 를 물어보고, 아니면 selected_path()(상위 LOT)로
        회귀할 수 있게 한다.
        """
        target = self._candidate or self._cur
        return str(target) if self._resolved_kind() == "wafer" else ""
