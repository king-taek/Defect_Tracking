"""출력 명세 페이지.

Excel 로 내보낼 사진을 확인하고 개별로 빼는 화면이다. 원본은 모달 다이얼로그 안의 3열 카드
격자였고, 아래에 [취소][확인][Excel 출력] 세 버튼이 같은 무게로 놓여 있었다. 담은 목록은
창이 계속 들고 있는 상태인데 그것을 모달 뒤에 숨기면 "지금 몇 장 담겼는지" 를 보려고 매번
창을 열었다 닫아야 한다. 그래서 nav 라우트 페이지로 올리고, 사진 격자 대신 한 줄에 한 건씩
읽는 명세 표(머리 38 + 행 60)로 바꾼다. 주요 액션은 Excel 출력 하나뿐이다(03-screens §4).

버튼 한 번에 대량으로 담은 항목은 사진 수백 줄 대신 `×n` 묶음 행 하나로 접는다. 태그를 그대로
돌려주기 때문에(`tagged_selected`) 페이지를 떠났다 돌아와도 묶음이 개별 행으로 풀리지 않는다.

담긴 목록의 소유자는 창(`MainWindow._export_tray`)이다. 페이지는 `set_tray()` 로 받아서 보여
주고 편집 결과를 `tray_changed` 로 알린다. 화면이 상태를 따로 들고 있으면 판독 화면의
'＋ 출력에 담기' 개수와 어긋난다.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    FluentIcon,
    MessageBox,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SmoothScrollArea,
    TitleLabel,
    TransparentToolButton,
    isDarkTheme,
    qconfig,
    setCustomStyleSheet,
)

# 경고 임계값은 Excel 쪽이 단일 출처다. 출력 규격을 정한 곳과 경고를 띄우는 곳이 갈리면
# 한쪽만 바뀐 채 남는다.
from app.export.excel_report import EXPORT_WARN_BLOCKS
from app.models import BaseDefectMatches
from app.ui import theme

__all__ = [
    "ExportPage",
    "ALL_LAYERS_TAG",
    "EXPORT_WARN_BLOCKS",
    "WARN_TITLE",
    "WARN_BODY",
    "WARN_BTN_OK",
    "WARN_BTN_NO",
    "warn_texts",
]

_PAGE_TITLE = "출력 명세"
_PAGE_SUB = "담은 사진만 Excel 로 나갑니다. 필요 없는 건은 행 끝에서 뺍니다"
_EMPTY_BODY = (
    "담은 사진이 없습니다.\n"
    "판독 화면의 '＋ 출력에 담기' 로 담거나, 위 '매치 전체 담기' 를 누르세요."
)

# 버튼 한 번에 여러 layer 를 합쳐 담을 때 붙는 묶음 이름.
ALL_LAYERS_TAG = "이번 LOT의 모든 매치된 defect"

# 200블록 경고 (REVIEW-01 A13 확정 문구). 자동 분할은 폐기했고 출력 전 확인만 남는다.
# 문구를 여기서 조립하는 이유: 화면과 테스트가 같은 문자열을 읽어야 표기가 조용히 어긋나지 않는다.
WARN_TITLE = "사진이 많습니다"
WARN_BODY = (
    "{n}건을 출력하면 파일이 커지고 열기가 느려집니다.\n"
    "필요한 건만 남기고 출력하는 것을 권합니다."
)
WARN_BTN_OK = "그대로 출력"
WARN_BTN_NO = "명세로 돌아가기"

# 전체 비우기 확인. 되돌릴 수 없는 편집이라 묻는다.
_CLEAR_TITLE = "담은 사진을 모두 뺍니다"
_CLEAR_BODY = "{n}장을 명세에서 뺍니다. 다시 담으려면 판독 화면에서 하나씩 담아야 합니다."
_CLEAR_BTN_OK = "모두 빼기"
_CLEAR_BTN_NO = "그대로 두기"

# 표 규격 (03-screens §4). 머리 38 + 행 60(글자 크게 72).
_HEAD_H = 38
_THUMB_W = 72
_THUMB_H = 44
_COL_NO = 44
_COL_MATCH = 88
_COL_ACTION = 36
_CELL_PAD = theme.SPACING["cardMin"]

_MONO = "'Cascadia Mono','Consolas','DejaVu Sans Mono',monospace"


def warn_texts(n: int) -> tuple[str, str, str, str]:
    """200블록 경고의 (제목, 본문, 확인, 취소). A13 확정 문구를 조립한다."""
    return WARN_TITLE, WARN_BODY.format(n=n), WARN_BTN_OK, WARN_BTN_NO


def _curve(name: str) -> QEasingCurve:
    return QEasingCurve(getattr(QEasingCurve.Type, name))


def _entry(value) -> tuple[BaseDefectMatches, Optional[str]]:
    """`BaseDefectMatches` 와 `(item, tag)` 튜플을 한 형태로 맞춘다.

    창은 태그 포함으로 트레이를 저장하지만 판독 화면에서 갓 담은 항목은 태그가 없다.
    """
    if isinstance(value, tuple):
        return value[0], value[1]
    return value, None


def item_key(item: BaseDefectMatches) -> str:
    """트레이 안에서 사진 한 장을 가리키는 키(원본 이미지 경로)."""
    return str(item.base.image_path)


def _position_text(rec) -> tuple[str, str]:
    """(die 위치, die 내 좌표). 좌표 파싱이 실패한 record 도 빈 칸 없이 읽히게 한다."""
    if not rec.ok:
        return f"{rec.wafer_id} · 좌표 없음", rec.position_key
    return (
        f"{rec.wafer_id} · die ({rec.col}, {rec.row})",
        f"x {round(rec.x)} µm · y {round(rec.y)} µm",
    )


class _SpecRow(QFrame):
    """명세 표의 한 행. 개별 사진 한 장이거나 `×n` 묶음 하나다.

    두 종류를 한 클래스로 두는 이유: 열 위치(NO/사진/위치/매칭/제거)가 같아야 표로 읽힌다.
    묶음이 다른 모양이면 눈이 열을 다시 찾아야 한다.
    """

    remove_requested = Signal(object)  # self

    def __init__(
        self,
        key: str,
        number: int,
        row_h: int,
        size_key: Optional[str],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("specRow")
        self.key = key
        self.is_batch = False
        self.count = 1
        self._row_h = row_h
        self._size_key = size_key
        self._anim: Optional[QPropertyAnimation] = None
        self.setFixedHeight(row_h)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        row = QHBoxLayout(self)
        row.setContentsMargins(_CELL_PAD, 0, _CELL_PAD, 0)
        row.setSpacing(theme.SPACING["gapM"])

        self.lbl_no = QLabel(str(number), self)
        self.lbl_no.setFixedWidth(_COL_NO)
        self.lbl_no.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self.lbl_no)

        self.photo = QLabel(self)
        self.photo.setObjectName("specPhoto")
        self.photo.setFixedSize(_THUMB_W, _THUMB_H)
        self.photo.setAlignment(Qt.AlignCenter)
        row.addWidget(self.photo)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(1)
        self.lbl_pos = QLabel("", self)
        self.lbl_sub = QLabel("", self)
        text.addWidget(self.lbl_pos)
        text.addWidget(self.lbl_sub)
        row.addLayout(text, 1)

        self.lbl_match = QLabel("", self)
        self.lbl_match.setFixedWidth(_COL_MATCH)
        self.lbl_match.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self.lbl_match)

        self.btn_remove = TransparentToolButton(FluentIcon.CLOSE, self)
        self.btn_remove.setFixedSize(_COL_ACTION, _COL_ACTION)
        self.btn_remove.clicked.connect(lambda: self.remove_requested.emit(self))
        row.addWidget(self.btn_remove)

    # ------------------------------------------------------------ 내용
    def fill_item(self, item: BaseDefectMatches, pixmap: Optional[QPixmap]) -> None:
        """개별 사진 행."""
        self.is_batch = False
        self.count = 1
        main, sub = _position_text(item.base)
        self.lbl_pos.setText(main)
        self.lbl_sub.setText(sub)
        matched = sum(1 for r in item.results if r.is_match)
        self.lbl_match.setText(f"{matched}/{len(item.results)}")
        self.lbl_match.setToolTip(
            f"비교 layer {len(item.results)}개 중 {matched}개에서 같은 자리를 찾았습니다."
        )
        if pixmap is not None and not pixmap.isNull():
            self.photo.setPixmap(
                pixmap.scaled(_THUMB_W, _THUMB_H, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            self.photo.setText("사진 없음")
        self.btn_remove.setToolTip("이 사진을 명세에서 뺍니다.")

    def fill_batch(self, tag: str, count: int) -> None:
        """`×n` 묶음 행. 사진 수백 줄 대신 한 줄로 접는다."""
        self.is_batch = True
        self.count = count
        self.photo.setText(f"×{count}")
        self.lbl_pos.setText(tag)
        self.lbl_sub.setText("한 번에 담은 묶음")
        self.lbl_match.setText(f"{count}장")
        self.lbl_match.setToolTip("이 묶음에 들어 있는 사진 수입니다.")
        self.btn_remove.setToolTip("이 묶음 전체를 명세에서 뺍니다.")

    # ------------------------------------------------------------ 모션
    def play_enter(self) -> None:
        """0 -> 행 높이. 묶음을 담았을 때 표가 아래로 밀리는 과정을 보이게 한다."""
        duration, easing = theme.MOTION["rowExpand"]
        self.setMinimumHeight(0)
        self.setMaximumHeight(0)
        anim = QPropertyAnimation(self, b"maximumHeight", self)
        anim.setDuration(duration)
        anim.setEasingCurve(_curve(easing))
        anim.setStartValue(0)
        anim.setEndValue(self._row_h)
        anim.finished.connect(lambda: self.setFixedHeight(self._row_h))
        self._anim = anim
        anim.start()

    def play_exit(self, on_done: Callable[[], None]) -> None:
        """행 높이 -> 0. 제자리에서 접혀야 어느 줄이 빠졌는지 눈이 따라간다."""
        self.setMinimumHeight(0)
        self.btn_remove.setEnabled(False)  # 접히는 동안 두 번 눌리는 것을 막는다
        anim = QPropertyAnimation(self, b"maximumHeight", self)
        duration, easing = theme.MOTION["rowRemove"]
        anim.setDuration(duration)
        anim.setEasingCurve(_curve(easing))
        anim.setStartValue(self.height())
        anim.setEndValue(0)
        anim.finished.connect(on_done)
        self._anim = anim
        anim.start()

    # ------------------------------------------------------------ 색
    def apply_tokens(self) -> None:
        t = theme.fluent_tokens(isDarkTheme())
        card = t["card"]
        divider = theme.flatten(t["divider"], card)
        self.setStyleSheet(
            f"QFrame#specRow {{ background: transparent;"
            f" border-bottom: 1px solid {divider}; }}"
            f"QFrame#specRow:hover {{ background: {t['subtleH']}; }}"
        )
        self.lbl_no.setStyleSheet(
            f"color:{theme.flatten(t['txt3'], card)};"
            f" font-family:{_MONO}; font-size:{theme.fluent_font_px('caption', self._size_key)}px;"
            " background: transparent;"
        )
        # 사진 바탕은 두 테마 모두 순검정(게이트). 묶음의 ×n 도 같은 판 위에 올려 열을 맞춘다.
        self.photo.setStyleSheet(
            f"QLabel#specPhoto {{ background:{theme.PHOTO_BG}; border-radius:4px;"
            f" color: rgba(255,255,255,0.90); font-family:{_MONO};"
            f" font-size:{theme.fluent_font_px('bodySm', self._size_key)}px;"
            " font-weight:600; }"
        )
        # 등폭은 수치에만 쓴다. 묶음 행의 두 줄은 이름과 설명이라 본문 글꼴이 맞다.
        mono = "" if self.is_batch else f" font-family:{_MONO};"
        self.lbl_pos.setStyleSheet(
            f"color:{theme.flatten(t['txt1'], card)};{mono}"
            f" font-size:{theme.fluent_font_px('body', self._size_key)}px;"
            " background: transparent;"
        )
        self.lbl_sub.setStyleSheet(
            f"color:{theme.flatten(t['txt2'], card)};{mono}"
            f" font-size:{theme.fluent_font_px('captionSm', self._size_key)}px;"
            " background: transparent;"
        )
        self.lbl_match.setStyleSheet(
            f"color:{theme.flatten(t['txt2'], card)};"
            f" font-family:{_MONO}; font-size:{theme.fluent_font_px('caption', self._size_key)}px;"
            " background: transparent;"
        )
        # Fluent 위젯이라 setStyleSheet 대신 setCustomStyleSheet 로 합성한다.
        light = theme.fluent_tokens(False)
        dark = theme.fluent_tokens(True)
        rule = "TransparentToolButton:hover {{ background: {0}; border-radius: 4px; }}"
        setCustomStyleSheet(
            self.btn_remove, rule.format(light["dangerBg"]), rule.format(dark["dangerBg"])
        )


class ExportPage(QWidget):
    """출력 명세 라우트.

    창이 배선하는 순서:
      1. `set_thumb_cache` / `set_all_matched` / `set_all_layers_provider` 로 재료를 준다
      2. 트레이가 바뀔 때마다 `set_tray(...)`
      3. `tray_changed` 를 받아 창의 트레이를 갱신한다(`tagged_selected()`)
      4. `export_requested` 를 받아 실제 Excel 출력을 진행한다
    """

    export_requested = Signal()   # Excel 출력을 눌렀고 200블록 확인까지 통과했다
    tray_changed = Signal(int)    # 담긴 사진 총 장수. 판독 화면 버튼의 개수 표시용

    def __init__(
        self,
        thumb_cache=None,
        all_matched: Optional[list[BaseDefectMatches]] = None,
        all_matched_label: str = "기준 layer 매치 전체",
        all_layers_provider: Optional[
            Callable[[Callable[[int, int], None], Callable[[list], None]], None]
        ] = None,
        size_key: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        # objectName 은 라우트 키다. 비면 ValueError, 겹치면 라우팅이 깨진다.
        self.setObjectName("exportInterface")

        self._tagged: list[tuple[BaseDefectMatches, Optional[str]]] = []
        self._keys: set[str] = set()
        self._rows: list[_SpecRow] = []
        self._collapsing: list[_SpecRow] = []
        self._entering: set[str] = set()
        self._thumb_cache = thumb_cache
        self._all_matched: list[BaseDefectMatches] = list(all_matched or [])
        self._all_matched_label = all_matched_label
        self._all_layers_provider = all_layers_provider
        self._all_layers_busy = False
        self._size_key = size_key
        self._row_h = theme.fluent_height("specRow", size_key)
        self._wants_export = False

        self._build()
        self._apply_tokens()
        qconfig.themeChanged.connect(self._apply_tokens)
        self._rebuild()

    # ------------------------------------------------------------ 구성
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            theme.SPACING["pageH"], theme.SPACING["pageV"],
            theme.SPACING["pageH"], theme.SPACING["pageV"],
        )
        outer.setSpacing(theme.SPACING["gapM"])
        outer.addLayout(self._build_header())
        outer.addLayout(self._build_actions())
        outer.addWidget(self._build_card(), 1)

    def _build_header(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACING["gapS"])
        row.addWidget(TitleLabel(_PAGE_TITLE, self))
        row.addStretch(1)
        # 개수는 등폭이라야 목록이 바뀔 때 자릿수가 흔들리지 않는다.
        self.lbl_count = QLabel("", self)
        self.lbl_count.setObjectName("specCount")
        row.addWidget(self.lbl_count)
        col.addLayout(row)
        sub = CaptionLabel(_PAGE_SUB, self)
        sub.setObjectName("dim")
        col.addWidget(sub)
        return col

    def _build_actions(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(theme.SPACING["gapXs"])

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACING["gapXs"])
        height = theme.fluent_height("control", self._size_key)

        self.btn_add_all = PushButton("매치 전체 담기", self)
        self.btn_add_all.setFixedHeight(height)
        self.btn_add_all.setToolTip(
            "지금 기준 layer 로 매칭된 사진을 한 묶음으로 담습니다."
        )
        self.btn_add_all.clicked.connect(self._add_all_matched)
        row.addWidget(self.btn_add_all)

        self.btn_add_all_layers = PushButton("모든 매치 담기", self)
        self.btn_add_all_layers.setFixedHeight(height)
        self.btn_add_all_layers.setToolTip(
            "layer 를 하나씩 기준으로 삼아 어디서든 매치된 defect 을 모두 담습니다"
            "(중복 제거). layer 수만큼 다시 매칭하므로 잠시 걸립니다."
        )
        self.btn_add_all_layers.clicked.connect(self._add_all_layers)
        row.addWidget(self.btn_add_all_layers)

        self.btn_clear = PushButton("전체 비우기", self)
        self.btn_clear.setFixedHeight(height)
        self.btn_clear.setToolTip("담은 사진을 모두 뺍니다.")
        self.btn_clear.clicked.connect(self._on_clear_clicked)
        row.addWidget(self.btn_clear)

        row.addStretch(1)

        # 강조는 한 화면에 하나. 원본의 [취소][확인][Excel 출력] 3버튼 동급을 여기서 끝낸다.
        self.btn_export = PrimaryPushButton("Excel 출력", self)
        self.btn_export.setFixedHeight(theme.fluent_height("primary", self._size_key))
        self.btn_export.setToolTip("담은 사진을 지금 Excel 파일로 출력합니다.")
        self.btn_export.clicked.connect(self._on_export_clicked)
        row.addWidget(self.btn_export)
        box.addLayout(row)

        self.progress = ProgressBar(self)
        self.progress.setVisible(False)
        box.addWidget(self.progress)
        return box

    def _build_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("specCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_table_head(card))

        self.scroll = SmoothScrollArea(card)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        # Fluent 위젯이라 setStyleSheet 로 덮으면 스크롤바 스타일까지 같이 날아간다.
        transparent = "SmoothScrollArea { background: transparent; border: none; }"
        setCustomStyleSheet(self.scroll, transparent, transparent)
        self.scroll.viewport().setStyleSheet("background: transparent;")
        self.host = QWidget(self.scroll)
        self.host.setStyleSheet("background: transparent;")
        self.rows_layout = QVBoxLayout(self.host)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(0)
        self.empty = QLabel(_EMPTY_BODY, self.host)
        self.empty.setObjectName("specEmpty")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setMinimumHeight(160)
        self.rows_layout.addWidget(self.empty)
        self.rows_layout.addStretch(1)
        self.scroll.setWidget(self.host)
        lay.addWidget(self.scroll, 1)
        self._card = card
        return card

    def _build_table_head(self, card: QWidget) -> QWidget:
        head = QFrame(card)
        head.setObjectName("specHead")
        head.setFixedHeight(_HEAD_H)
        row = QHBoxLayout(head)
        row.setContentsMargins(_CELL_PAD, 0, _CELL_PAD, 0)
        row.setSpacing(theme.SPACING["gapM"])
        self._head_labels: list[QLabel] = []

        def cell(text: str, width: int | None, align, stretch: int = 0) -> None:
            label = QLabel(text, head)
            if width is not None:
                label.setFixedWidth(width)
            label.setAlignment(align | Qt.AlignVCenter)
            row.addWidget(label, stretch)
            self._head_labels.append(label)

        cell("NO", _COL_NO, Qt.AlignRight)
        cell("사진", _THUMB_W, Qt.AlignLeft)
        cell("위치", None, Qt.AlignLeft, 1)
        cell("매칭", _COL_MATCH, Qt.AlignRight)
        cell("", _COL_ACTION, Qt.AlignRight)
        return head

    # ------------------------------------------------------------ 창이 주는 것
    def set_thumb_cache(self, cache) -> None:
        self._thumb_cache = cache

    def set_size_key(self, size_key: Optional[str]) -> None:
        """글자 크기 설정(normal/large)을 바꾼다. 행 높이와 글자 크기가 표대로 다시 선다."""
        if size_key == self._size_key:
            return
        self._size_key = size_key
        self._row_h = theme.fluent_height("specRow", size_key)
        self.btn_export.setFixedHeight(theme.fluent_height("primary", size_key))
        for button in (self.btn_add_all, self.btn_add_all_layers, self.btn_clear):
            button.setFixedHeight(theme.fluent_height("control", size_key))
        self._rebuild()
        self._apply_tokens()

    def set_tray(self, entries: list) -> None:
        """창이 들고 있는 트레이를 그대로 받아 표를 다시 세운다.

        `BaseDefectMatches` 와 `(item, tag)` 둘 다 받는다. 창은 태그 포함으로 저장하지만
        판독 화면에서 갓 담은 항목은 태그가 없다.
        """
        self._tagged = []
        self._keys = set()
        for value in entries or []:
            item, tag = _entry(value)
            self._add(item, tag)
        self._wants_export = False
        self._rebuild()

    def set_all_matched(
        self, items: Optional[list[BaseDefectMatches]], label: Optional[str] = None
    ) -> None:
        """'매치 전체 담기' 대상과 묶음 이름. 기준 layer 가 바뀔 때마다 창이 갱신한다."""
        self._all_matched = list(items or [])
        if label:
            self._all_matched_label = label
        self._sync_buttons()

    def set_all_layers_provider(
        self,
        provider: Optional[
            Callable[[Callable[[int, int], None], Callable[[list], None]], None]
        ],
    ) -> None:
        """'모든 매치 담기' 계산 공급자(창이 백그라운드 워커로 돌린다)."""
        self._all_layers_provider = provider
        self._sync_buttons()

    # ------------------------------------------------------------ 창이 읽는 것
    def selected(self) -> list[BaseDefectMatches]:
        """최종 출력 대상(담긴 순서 유지, 태그는 평탄화)."""
        return [m for m, _tag in self._tagged]

    def tagged_selected(self) -> list[tuple[BaseDefectMatches, Optional[str]]]:
        """태그 포함 최종 목록. 창이 이대로 저장하면 다시 열어도 묶음이 풀리지 않는다."""
        return list(self._tagged)

    def wants_export(self) -> bool:
        """마지막 행동이 'Excel 출력' 이었는지. 목록을 편집하면 다시 False 가 된다."""
        return self._wants_export

    # ------------------------------------------------------------ 편집
    def _add(self, item: BaseDefectMatches, tag: Optional[str] = None) -> bool:
        key = item_key(item)
        if key in self._keys:
            return False
        # 목록이 바뀌면 직전의 '출력하겠다' 는 더 이상 이 목록에 대한 뜻이 아니다.
        self._wants_export = False
        self._keys.add(key)
        self._tagged.append((item, tag))
        return True

    def _remove(self, key: str) -> None:
        """개별 사진 한 장을 뺀다. 목록에서는 즉시 빠지고 행은 제자리에서 접힌다."""
        if key not in self._keys:
            return
        self._wants_export = False
        self._tagged = [(m, t) for m, t in self._tagged if item_key(m) != key]
        self._keys.discard(key)
        self._collapse_row(key)

    def _remove_batch(self, tag: str) -> None:
        self._wants_export = False
        removed = {item_key(m) for m, t in self._tagged if t == tag}
        self._tagged = [(m, t) for m, t in self._tagged if t != tag]
        self._keys -= removed
        self._collapse_row(f"tag:{tag}")

    def _clear_all(self) -> None:
        """확인 없이 비운다. 확인 대화는 `_on_clear_clicked` 가 맡는다."""
        self._wants_export = False
        self._tagged = []
        self._keys = set()
        self._rebuild()

    def _add_all_matched(self) -> None:
        added = [m for m in self._all_matched if self._add(m, tag=self._all_matched_label)]
        if added:
            self._entering.add(f"tag:{self._all_matched_label}")
        self._rebuild()

    def _add_all_layers(self) -> None:
        """모든 layer 를 각각 기준으로 삼은 매치를 공급자에게 계산시켜 담는다(중복 제거).

        layer 수만큼 재매칭하는 무거운 작업이라 공급자(창)가 워커로 돌리고 진행을 콜백으로
        알린다. 계산 중에는 담기 버튼을 잠근다.
        """
        if self._all_layers_provider is None or self._all_layers_busy:
            return
        self._all_layers_busy = True
        self._sync_buttons()
        self.progress.setValue(0)
        self.progress.setVisible(True)

        def _progress(cur: int, total: int) -> None:
            self.progress.setMaximum(max(1, total))
            self.progress.setValue(cur)

        def _done(items: list) -> None:
            # 실패로 빈 목록이 와도 잠금은 반드시 풀린다. 안 그러면 버튼이 영영 막힌다.
            self._all_layers_busy = False
            self.progress.setVisible(False)
            added = [m for m in (items or []) if self._add(m, tag=ALL_LAYERS_TAG)]
            if added:
                self._entering.add(f"tag:{ALL_LAYERS_TAG}")
            self._rebuild()

        self._all_layers_provider(_progress, _done)

    # ------------------------------------------------------------ 액션
    def _on_clear_clicked(self) -> None:
        if not self._tagged:
            return
        box = MessageBox(_CLEAR_TITLE, _CLEAR_BODY.format(n=len(self._tagged)), self.window())
        box.yesButton.setText(_CLEAR_BTN_OK)
        box.cancelButton.setText(_CLEAR_BTN_NO)
        if box.exec():
            self._clear_all()

    def _warn_box(self, n: int) -> MessageBox:
        """200블록 경고 대화(A13). 문구 조립을 한 곳에 모아 표기가 어긋나지 않게 한다."""
        title, body, ok, no = warn_texts(n)
        box = MessageBox(title, body, self.window())
        box.yesButton.setText(ok)
        box.cancelButton.setText(no)
        return box

    def confirm_large_export(self) -> bool:
        """블록 수가 임계값을 넘으면 확인을 받는다. 그대로 출력하면 True.

        REVIEW-01 A13: 자동 분할은 폐기했다. 시트를 늘리는 대신 사용자가 범위를 줄이게 한다.
        """
        n = len(self._tagged)
        if n <= EXPORT_WARN_BLOCKS:
            return True
        return bool(self._warn_box(n).exec())

    def _on_export_clicked(self) -> None:
        if not self._tagged:
            return
        if not self.confirm_large_export():
            return
        self._wants_export = True
        self.export_requested.emit()

    # ------------------------------------------------------------ 표 세우기
    def _rebuild(self) -> None:
        """표를 처음부터 다시 세운다. 담긴 순서가 곧 Excel 블록 순서다."""
        # 접히는 중인 행을 먼저 걷어낸다. 남겨 두면 새 표 사이에 이미 뺀 행이 끼어 보인다.
        for row in list(self._collapsing):
            self._drop_row(row)
        for row in self._rows:
            self.rows_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows = []

        groups: list[tuple[Optional[str], list[BaseDefectMatches]]] = []
        index: dict[Optional[str], int] = {}
        for item, tag in self._tagged:
            if tag is None:
                groups.append((None, [item]))  # 개별은 담긴 순서대로 한 줄씩
                continue
            slot = index.get(tag)
            if slot is None:
                index[tag] = len(groups)
                groups.append((tag, [item]))
            else:
                groups[slot][1].append(item)

        for number, (tag, items) in enumerate(groups, start=1):
            key = f"tag:{tag}" if tag is not None else item_key(items[0])
            row = _SpecRow(key, number, self._row_h, self._size_key, self.host)
            if tag is None:
                row.fill_item(items[0], self._pixmap(items[0]))
            else:
                row.fill_batch(tag, len(items))
            row.apply_tokens()
            row.remove_requested.connect(self._on_row_remove)
            # empty 라벨과 마지막 stretch 앞에 쌓는다.
            self.rows_layout.insertWidget(len(self._rows), row)
            self._rows.append(row)
            if key in self._entering:
                row.play_enter()
        self._entering.clear()
        self._sync_buttons()
        self.tray_changed.emit(len(self._tagged))

    def _on_row_remove(self, row: _SpecRow) -> None:
        self._wants_export = False
        if row.is_batch:
            self._remove_batch(row.key[len("tag:"):])
        else:
            self._remove(row.key)

    def _collapse_row(self, key: str) -> None:
        """모델에서 이미 빠진 행을 화면에서 접어 없앤다."""
        target = next((r for r in self._rows if r.key == key), None)
        if target is None:
            self._rebuild()
            return
        self._rows.remove(target)
        self._collapsing.append(target)
        target.play_exit(lambda: self._drop_row(target))
        self._sync_buttons()
        self.tray_changed.emit(len(self._tagged))

    def _drop_row(self, row: _SpecRow) -> None:
        """접기가 끝난(또는 표가 새로 서느라 중단된) 행을 실제로 없앤다."""
        if row not in self._collapsing:
            return  # 애니메이션 완료와 표 재구성이 겹쳐도 두 번 지우지 않는다
        self._collapsing.remove(row)
        self.rows_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self._renumber()

    def _renumber(self) -> None:
        """행이 빠진 뒤 NO 를 다시 매긴다. 표 전체를 다시 세우면 스크롤이 튄다."""
        for number, row in enumerate(self._rows, start=1):
            row.lbl_no.setText(str(number))

    def _pixmap(self, item: BaseDefectMatches) -> Optional[QPixmap]:
        if self._thumb_cache is None:
            return None
        # 72x44 에 넣지만 캐시는 2배로 받아 축소한다(고DPI 에서 뭉개지지 않게).
        path = self._thumb_cache.get_full_thumbnail(item.base.image_path, max_size=_THUMB_W * 2)
        if path is None:
            return None
        pixmap = QPixmap(str(path))
        return None if pixmap.isNull() else pixmap

    def _sync_buttons(self) -> None:
        total = len(self._tagged)
        singles = sum(1 for _m, tag in self._tagged if tag is None)
        batches = len({tag for _m, tag in self._tagged if tag is not None})
        self.lbl_count.setText(f"개별 {singles}장 + 묶음 {batches}건 = 총 {total}장")
        self.btn_export.setEnabled(total > 0)
        self.btn_clear.setEnabled(total > 0)
        has_provider = self._all_layers_provider is not None
        self.btn_add_all.setEnabled(bool(self._all_matched) and not self._all_layers_busy)
        self.btn_add_all_layers.setVisible(has_provider)
        self.btn_add_all_layers.setEnabled(has_provider and not self._all_layers_busy)
        self.empty.setVisible(total == 0)

    # ------------------------------------------------------------ 색
    def _apply_tokens(self, *_args) -> None:
        """카드·표 머리·빈 상태를 현재 테마 토큰으로 칠한다.

        순수 Qt 위젯이라 setStyleSheet 를 쓴다. Fluent 위젯에 직접 거는 것만 금지다.
        """
        t = theme.fluent_tokens(isDarkTheme())
        card = t["card"]
        border = theme.flatten(t["cardBorder"], t["layer"])
        divider = theme.flatten(t["divider"], card)
        self._card.setStyleSheet(
            f"QFrame#specCard {{ background:{card}; border:1px solid {border};"
            f" border-radius:{theme.RADIUS['card']}px; }}"
            f"QFrame#specHead {{ background:{t['subtle']}; border:none;"
            f" border-bottom:1px solid {divider};"
            f" border-top-left-radius:{theme.RADIUS['card']}px;"
            f" border-top-right-radius:{theme.RADIUS['card']}px; }}"
        )
        head_style = (
            f"color:{theme.flatten(t['txt2'], card)}; background: transparent;"
            f" font-size:{theme.fluent_font_px('caption', self._size_key)}px; font-weight:600;"
        )
        for label in self._head_labels:
            label.setStyleSheet(head_style)
        self.lbl_count.setStyleSheet(
            f"color:{theme.flatten(t['txt2'], t['layer'])}; background: transparent;"
            f" font-family:{_MONO};"
            f" font-size:{theme.fluent_font_px('caption', self._size_key)}px;"
        )
        self.empty.setStyleSheet(
            f"color:{theme.flatten(t['txt2'], card)}; background: transparent;"
            f" font-size:{theme.fluent_font_px('bodySm', self._size_key)}px;"
        )
        for row in self._rows:
            row.apply_tokens()
