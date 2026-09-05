"""미매칭 페이지.

어떤 비교 layer 와도 매칭되지 않아 후보에서 제외된 기준 사진을 사유별로 훑고, 눌러서 판독
화면의 그 사진으로 간다(03-screens §2).

원본은 다이얼로그였고 layer 별 사유를 9px 한 줄로 이어 붙였다. 이 화면의 주 내용이 바로 그
사유이므로 layer 마다 행을 나누고 12px 로 올린다. 미매칭을 회색 한 단어로 줄이는 규칙은 Excel
리포트에만 적용된다(REVIEW-01 AD1).

U 점프(A11)가 쓰는 순수 함수도 여기 둔다. U 는 화면 전환이 아니라 판독 화면의 탐색 점프지만
"미매칭이 무엇인가"의 정의가 두 곳에 있으면 배지 수와 점프 대상이 소리 없이 어긋난다.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    SegmentedWidget,
    SmoothScrollArea,
    TitleLabel,
    isDarkTheme,
    qconfig,
    setCustomStyleSheet,
)

from app.models import NoMatchReason
from app.ui import theme
from app.ui.compare_grid import CompareGrid
from app.ui.widgets import PageHeader

_PAGE_TITLE = "미매칭"
_PAGE_SUB = (
    "어떤 비교 layer 와도 매칭되지 않아 후보에서 빠진 기준 사진입니다. "
    "누르면 판독 화면의 그 사진으로 갑니다."
)
_EMPTY_TEXT = "해당하는 미매칭 기준 사진이 없습니다."

_COLUMNS = 4
_PHOTO_H = 112          # 03-screens §2 의 사진 높이
_DOT_PX = 9             # 우상단 danger dot
_CARD_PAD = 10
# 캡션은 명세가 10.5 지만 QFont 픽셀 크기는 정수다. 읽기 쪽으로 올림한다.
_CAPTION_PX = 11
_ROW_PX = 12            # layer 별 사유 행. 이 화면의 주 내용이라 12 미만으로 내리지 않는다.
_LAYER_KEY_W = 62

_MONO = ("Cascadia Mono", "Consolas", "Menlo", "monospace")
_TRANSPARENT = "SmoothScrollArea { background: transparent; border: none; }"

# 사유별 (표시명, 글자 토큰, 배경 토큰). 원본 _REASON_META 의 색 의미를 Fluent 토큰으로 옮겼다.
#   허용오차 초과 = 거의 맞은 것       -> warn
#   좌표 추출 실패 = 고칠 수 있는 결손  -> danger
#   같은 die 사진 없음 = 원래 없음      -> 중립 회색
_REASON_META: dict[NoMatchReason, tuple[str, str, str]] = {
    NoMatchReason.OVER_TOLERANCE: ("허용오차 초과", "warn", "warnBg"),
    NoMatchReason.COORD_FAIL: ("좌표 추출 실패", "danger", "dangerBg"),
    NoMatchReason.NO_DIE_PHOTO: ("같은 die 사진 없음", "txt2", "subtle"),
}
# 트리아지 우선순위(앞일수록 먼저). 거의 매칭된 것을 가장 눈에 띄게 - 원본 계승.
_PRIORITY = [
    NoMatchReason.OVER_TOLERANCE,
    NoMatchReason.COORD_FAIL,
    NoMatchReason.NO_DIE_PHOTO,
]


# ---------------------------------------------------------------- 순수 로직
def has_unmatched(item: Any) -> bool:
    """비교 layer 중 하나라도 매칭되지 않았는가. A11 의 U 점프 대상 정의다."""
    return any(not r.is_match for r in getattr(item, "results", ()) or ())


def is_fully_unmatched(item: Any) -> bool:
    """모든 비교 layer 와 매칭이 0 인가. nav 배지와 이 페이지의 목록 기준이다.

    결과가 비어 있으면(비교 layer 미선택) 미매칭으로 세지 않는다. 아직 아무것도 비교하지 않은
    상태를 '전부 실패'로 세면 배지가 전체 장수로 부풀어 트리아지가 무의미해진다.
    """
    results = list(getattr(item, "results", ()) or ())
    return bool(results) and not any(r.is_match for r in results)


def fully_unmatched_indices(matches: Optional[Sequence[Any]]) -> list[int]:
    """완전 미매칭 기준의 index 목록(이 페이지가 나열하는 대상, nav 배지 수)."""
    return [i for i, m in enumerate(matches or ()) if is_fully_unmatched(m)]


def next_unmatched_index(
    matches: Optional[Sequence[Any]],
    current: int,
    view: Optional[Iterable[int]] = None,
) -> Optional[int]:
    """A11 의 U: 현재 index 이후에서 '미매칭을 하나 이상 포함한' 기준으로 점프(순환).

    view 는 현재 보기(필터)에 남은 index 목록이다. 주지 않으면 전체를 본다. 끝까지 없으면
    처음으로 돌아오고, 후보가 아예 없으면 None 을 돌려준다(호출부가 A11 문구로 알린다).

    '완전 미매칭'이 아니라 '하나 이상 미매칭'이 대상인 것이 A11 의 재정의다. 판독대가 빈 칸과
    사유를 항상 보여 주므로, 부분 미매칭도 확인이 필요한 자리다.
    """
    items = list(matches or ())
    order = list(view) if view is not None else list(range(len(items)))
    targets = [i for i in order if 0 <= i < len(items) and has_unmatched(items[i])]
    if not targets:
        return None
    for i in targets:
        if i > current:
            return i
    return targets[0]


def dominant_reason(item: Any) -> Optional[NoMatchReason]:
    """기준 1개의 대표 미매칭 사유(우선순위가 가장 높은 것). 원본 _dominant 계승."""
    present = {r.reason for r in getattr(item, "results", ()) or () if not r.is_match}
    for reason in _PRIORITY:
        if reason in present:
            return reason
    return None


def reasons_of(item: Any) -> set:
    """이 기준에 등장한 미매칭 사유 집합(필터가 쓰는 값)."""
    return {r.reason for r in getattr(item, "results", ()) or () if not r.is_match}


def layer_reason_rows(
    item: Any, compare_layers: Optional[Sequence[str]] = None
) -> list[tuple[str, str, NoMatchReason]]:
    """layer 별 (layer, 사유 문구, 사유) 행.

    문구는 판독대와 같은 함수에서 가져온다. 같은 사유를 두 화면이 다르게 적으면 사용자가 둘을
    다른 일로 읽는다.
    """
    failed = [r for r in getattr(item, "results", ()) or () if not r.is_match]
    if compare_layers:
        rank = {name: i for i, name in enumerate(compare_layers)}
        failed.sort(key=lambda r: rank.get(r.compare_layer, len(rank)))
    return [(r.compare_layer, CompareGrid._diag_text(r)[0], r.reason) for r in failed]


# ---------------------------------------------------------------- 표시 헬퍼
def _font(px: int, *, bold: bool = False, mono: bool = False) -> QFont:
    """글자 크기를 QFont 로 지정한다.

    스타일시트의 font-size 로 주면 위젯이 자기 크기를 계산할 때만 쓰이고 QFont 에는 남지 않아
    회귀 테스트가 크기를 못 읽는다. 이 화면은 글자 크기 자체가 게이트라 QFont 로 못 박는다.
    """
    f = QFont()
    if mono:
        f.setFamilies(list(_MONO))
    f.setPixelSize(px)
    f.setWeight(QFont.DemiBold if bold else QFont.Normal)
    return f


def _reason_colors(reason: NoMatchReason, tokens: dict) -> tuple[str, str, str]:
    """(표시명, 글자색, 배경색). 알파 토큰은 카드 면과 합성해 불투명하게 만든다."""
    label, fg_key, bg_key = _REASON_META[reason]
    bg = theme.flatten(tokens[bg_key], tokens["card"])
    return label, theme.flatten(tokens[fg_key], bg), bg


class _ReasonRow(QWidget):
    """`LYB4  허용오차 초과 · 최근접 118.4 µm` 한 행.

    layer 키와 사유를 다른 위젯으로 나눈 것은 키 폭을 맞춰 세로로 읽히게 하기 위해서다.
    """

    def __init__(self, layer: str, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACING["gapS"])

        self.key = QLabel(layer, self)
        self.key.setFont(_font(_ROW_PX, bold=True, mono=True))
        self.key.setMinimumWidth(_LAYER_KEY_W)
        self.key.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        row.addWidget(self.key, 0)

        self.text = QLabel(text, self)
        self.text.setFont(_font(_ROW_PX))
        self.text.setWordWrap(True)
        self.text.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        row.addWidget(self.text, 1)
        self.setToolTip(f"{layer}  {text}")

    def apply_tokens(self, tokens: dict) -> None:
        color = theme.flatten(tokens["txt2"], tokens["card"])
        self.key.setStyleSheet(f"color:{color}; background:transparent;")
        self.text.setStyleSheet(f"color:{color}; background:transparent;")


class NoMatchCell(QFrame):
    """미매칭 기준 한 장. 사진 + 캡션 + 대표 사유 배지 + layer 별 사유 행."""

    activated = Signal(int)

    def __init__(
        self,
        index: int,
        item: Any,
        thumb_cache: Any = None,
        compare_layers: Optional[Sequence[str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.index = index
        self.item = item
        self.setObjectName("nomatchCell")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.reason_rows: list[_ReasonRow] = []
        self._build(item, thumb_cache, compare_layers)
        self._apply_tokens()
        qconfig.themeChanged.connect(self._apply_tokens)

    # ------------------------------------------------------------ 구성
    def _build(self, item: Any, thumb_cache: Any, compare_layers) -> None:
        col = QVBoxLayout(self)
        col.setContentsMargins(_CARD_PAD, _CARD_PAD, _CARD_PAD, _CARD_PAD)
        col.setSpacing(theme.SPACING["gapS"])

        base = getattr(item, "base", None)

        self.photo = QLabel(self)
        self.photo.setObjectName("nomatchPhoto")
        self.photo.setFixedHeight(_PHOTO_H)
        self.photo.setAlignment(Qt.AlignCenter)
        self.photo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._fill_photo(base, thumb_cache)
        col.addWidget(self.photo)

        # 우상단 점: 사진을 가리지 않는 자리에서 미매칭임을 한눈에 알린다.
        self.dot = QLabel(self.photo)
        self.dot.setFixedSize(_DOT_PX, _DOT_PX)

        self.caption = QLabel(self._caption_text(base), self)
        self.caption.setFont(_font(_CAPTION_PX, mono=True))
        self.caption.setAlignment(Qt.AlignLeft)
        col.addWidget(self.caption)

        self.badge = QLabel("", self)
        self.badge.setFont(_font(int(theme.TYPO["label"]["size"]), bold=True))
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self._reason = dominant_reason(item)
        if self._reason is None:
            self.badge.hide()
        else:
            self.badge.setText(_REASON_META[self._reason][0])
        col.addWidget(self.badge, 0, Qt.AlignLeft)

        for layer, text, _reason in layer_reason_rows(item, compare_layers):
            row = _ReasonRow(layer, text, self)
            self.reason_rows.append(row)
            col.addWidget(row)

        if base is not None:
            self.setToolTip(str(getattr(base, "image_path", "")))

    def _fill_photo(self, base: Any, thumb_cache: Any) -> None:
        path = None
        if base is not None and thumb_cache is not None:
            path = thumb_cache.get_full_thumbnail(base.image_path, max_size=200)
        if path is not None:
            pix = QPixmap(str(path))
            if not pix.isNull():
                self.photo.setPixmap(
                    pix.scaledToHeight(_PHOTO_H - 8, Qt.SmoothTransformation)
                )
                return
        self.photo.setText("사진 없음")

    @staticmethod
    def _caption_text(base: Any) -> str:
        if base is None:
            return ""
        return f"{getattr(base, 'wafer_id', '')} ({getattr(base, 'col', '')},{getattr(base, 'row', '')})"

    # ------------------------------------------------------------ 색
    def _apply_tokens(self, *_args) -> None:
        """순수 Qt 위젯이라 setStyleSheet 를 쓴다. 금지 대상은 Fluent 위젯뿐이다."""
        t = theme.fluent_tokens(isDarkTheme())
        border = theme.flatten(t["cardBorder"], t["layer"])
        hover = theme.flatten(t["cardBorderH"], t["layer"])
        self.setStyleSheet(
            f"QFrame#nomatchCell {{ background:{t['card']}; border:1px solid {border};"
            f" border-radius:{theme.RADIUS['card']}px; }}"
            f"QFrame#nomatchCell:hover {{ background:{t['cardHover']};"
            f" border-color:{hover}; }}"
        )
        self.photo.setStyleSheet(
            f"QLabel#nomatchPhoto {{ background:{theme.PHOTO_BG}; border-radius:4px;"
            " color:rgba(255,255,255,0.62); }"
        )
        self.dot.setStyleSheet(
            f"background:{t['danger']}; border:1px solid {theme.PHOTO_BG};"
            f" border-radius:{_DOT_PX // 2}px;"
        )
        self.caption.setStyleSheet(
            f"color:{theme.flatten(t['txt2'], t['card'])}; background:transparent;"
        )
        if self._reason is not None:
            _label, fg, bg = _reason_colors(self._reason, t)
            self.badge.setStyleSheet(
                f"color:{fg}; background:{bg}; border-radius:4px; padding:2px 8px;"
            )
        for row in self.reason_rows:
            row.apply_tokens(t)

    def detach(self) -> None:
        """테마 구독을 끊는다. 셀은 필터를 바꿀 때마다 새로 만들어지므로 그냥 두면 쌓인다."""
        try:
            qconfig.themeChanged.disconnect(self._apply_tokens)
        except (RuntimeError, TypeError):
            pass

    # ------------------------------------------------------------ 상호작용
    def resizeEvent(self, event):  # noqa: N802 - Qt 규약
        super().resizeEvent(event)
        self.dot.move(self.photo.width() - _DOT_PX - 6, 6)
        self.dot.raise_()

    def mousePressEvent(self, event):  # noqa: N802 - Qt 규약
        if event.button() == Qt.LeftButton:
            self.activated.emit(self.index)
        super().mousePressEvent(event)


class NoMatchPage(QWidget):
    """미매칭 라우트. 완전 미매칭 기준만 나열한다(A11).

    부분 미매칭은 판독대의 빈 칸이 이미 보여 준다. 여기까지 같이 세면 목록이 전체 장수에
    가까워져 트리아지가 되지 않는다.
    """

    record_activated = Signal(int)   # 기준 index. 창이 판독 화면 이동에 쓴다.

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # objectName 은 라우트 키다. 비면 ValueError, 겹치면 라우팅이 깨진다.
        self.setObjectName("nomatchInterface")
        self._entries: list[tuple[int, Any]] = []
        self._thumb_cache: Any = None
        self._compare_layers: list[str] = []
        self._total = 0
        self._shown = 0
        self._build()

    # ------------------------------------------------------------ 구성
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 머리 행 44(시안): 제목 · 설명 … 총계 · 사유 필터. 목록이 그만큼 높이를 더 가진다.
        head = PageHeader(_PAGE_TITLE, self)
        self.lbl_sub = CaptionLabel(_PAGE_SUB, head)
        self.lbl_sub.setObjectName("dim")
        head.add_widget(self.lbl_sub)
        head.add_stretch()
        self.lbl_count = CaptionLabel("", head)
        self.lbl_count.setObjectName("dim")
        self.lbl_count.setFont(_font(_ROW_PX, mono=True))
        head.add_widget(self.lbl_count)
        head.add_spacing(theme.SPACING["gapXs"])

        # 사유 필터. 원본 ComboBox 는 값이 접혀 있어 지금 무엇으로 걸러진 상태인지 안 보였다.
        self.filter = SegmentedWidget(head)
        self.filter.addItem("all", "전체", lambda: self._set_filter("all"))
        for reason in _PRIORITY:
            self.filter.addItem(
                reason.value,
                _REASON_META[reason][0],
                lambda r=reason: self._set_filter(r.value),
            )
        self.filter.setCurrentItem("all")
        self._filter = "all"
        head.add_widget(self.filter)
        outer.addWidget(head)

        self.scroll = SmoothScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        # Fluent 위젯이라 setStyleSheet 로 덮으면 스크롤바 스타일까지 같이 날아간다.
        setCustomStyleSheet(self.scroll, _TRANSPARENT, _TRANSPARENT)
        self.scroll.viewport().setStyleSheet("background: transparent;")
        host = QWidget(self.scroll)
        self._grid = QGridLayout(host)
        # 오른쪽 여백은 겹쳐 그려지는 스크롤바 자리. 없으면 마지막 열이 가려진다.
        pad = PageHeader.PAD_X
        self._grid.setContentsMargins(pad, theme.SPACING["gapL"], pad, theme.SPACING["gapL"])
        self._grid.setHorizontalSpacing(theme.SPACING["gapM"])
        self._grid.setVerticalSpacing(theme.SPACING["gapM"])
        self._grid.setAlignment(Qt.AlignTop)
        for c in range(_COLUMNS):
            self._grid.setColumnStretch(c, 1)
        self.scroll.setWidget(host)
        self._host = host
        outer.addWidget(self.scroll, 1)

        self.lbl_empty = BodyLabel(_EMPTY_TEXT, self)
        self.lbl_empty.setObjectName("dim")
        self.lbl_empty.setAlignment(Qt.AlignCenter)
        self.lbl_empty.hide()
        # 빈 상태일 때 스크롤 자리를 대신 차지해 화면 가운데에 선다.
        outer.addWidget(self.lbl_empty, 1)

    # ------------------------------------------------------------ 데이터
    def set_data(
        self,
        matches: Optional[Sequence[Any]],
        thumb_cache: Any = None,
        base_layer: str = "",
        compare_layers: Optional[Sequence[str]] = None,
    ) -> None:
        """창이 가진 것을 그대로 받는다.

        matches 는 `MainWindow.matches` 전체다. 완전 미매칭만 고르는 일은 이 페이지가 한다
        (A11 의 정의를 한 곳에 둔다).
        """
        self._thumb_cache = thumb_cache
        self._compare_layers = list(compare_layers or [])
        self._entries = [
            (i, matches[i]) for i in fully_unmatched_indices(matches)
        ]
        self._total = len(self._entries)
        self.lbl_sub.setText(
            f"기준 {base_layer}. {_PAGE_SUB}" if base_layer else _PAGE_SUB
        )
        self._populate()

    def entries(self) -> list[tuple[int, Any]]:
        """완전 미매칭 (index, 기준) 목록. 창이 nav 배지 수로 쓸 수 있다."""
        return list(self._entries)

    def shown_count(self) -> int:
        return self._shown

    def current_filter(self) -> str:
        return self._filter

    def set_filter(self, key: str) -> None:
        """필터를 코드에서 바꾼다(분절 표시도 함께 옮긴다)."""
        self.filter.setCurrentItem(key)
        self._set_filter(key)

    # ------------------------------------------------------------ 내부
    def _set_filter(self, key: str) -> None:
        self._filter = key
        self._populate()

    def _clear(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                if isinstance(w, NoMatchCell):
                    w.detach()
                w.setParent(None)
                w.deleteLater()

    def _populate(self) -> None:
        self._clear()
        shown = 0
        for index, entry in self._entries:
            if self._filter != "all":
                if self._filter not in {r.value for r in reasons_of(entry)}:
                    continue
            cell = NoMatchCell(
                index, entry, self._thumb_cache, self._compare_layers, self._host
            )
            cell.activated.connect(self.record_activated)
            self._grid.addWidget(cell, shown // _COLUMNS, shown % _COLUMNS)
            shown += 1
        self._shown = shown
        self.lbl_count.setText(f"총 {self._total}장 · 표시 {shown}장")
        self.lbl_empty.setVisible(shown == 0)
        self.scroll.setVisible(shown > 0)

    def cells(self) -> list[NoMatchCell]:
        """현재 그리드에 놓인 셀(테스트·검증용)."""
        out: list[NoMatchCell] = []
        for i in range(self._grid.count()):
            w = self._grid.itemAt(i).widget()
            if isinstance(w, NoMatchCell):
                out.append(w)
        return out
