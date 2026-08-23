"""클러스터 defect 표시용 공유 위젯 (히트맵·메인 매치 공통).

- `load_thumb_holder`: 썸네일 QLabel 생성.
- `ClickThumb`: 썸네일 클릭 시 원본 뷰어 열기.
- `ClusteredThumb`: 대표 썸네일 + layer 배지 + (클러스터면) 좌하단 '+n' 버튼.
- `ClusterMembersPopup`: 묶인 defect 전체를 가로(줄바꿈)로 보여주는 팝업.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    PrimaryPushButton,
    PushButton,
    SmoothScrollArea,
    SubtitleLabel,
    isDarkTheme,
    qconfig,
    setCustomStyleSheet,
)

from app.clustering import Cluster
from app.ui import theme
from app.ui.flow_layout import FlowLayout

# 시트 폭(03-screens §10). 150px 썸네일 4장이 한 줄에 들어간다.
_SHEET_W = 660
_THUMB_PX = 150
_THUMB_H = int(_THUMB_PX * 0.78)
_PER_ROW = 3   # 660px 시트에서 실제로 한 줄에 들어가는 장수
_MAX_ROWS = 3   # 첫 화면에 보이는 줄. 더 있으면 스크롤한다.
_TRANSPARENT = "SmoothScrollArea { background: transparent; border: none; }"


def _stage_height(count: int) -> int:
    """묶음 장수에 맞는 첫 화면 사진 영역 높이."""
    rows = max(1, min(_MAX_ROWS, -(-max(count, 1) // _PER_ROW)))
    return rows * _THUMB_H + (rows - 1) * 8


def attach_image_context_menu(widget: QWidget, path_getter) -> None:
    """위젯에 사진 우클릭 메뉴(경로 복사·파일 열기·폴더 열기)를 붙인다.

    path_getter() 는 표시 중인 이미지 경로를 반환한다(호출 시점 값 사용).
    메인 그리드(compare_grid)의 우클릭 메뉴와 동일한 동작을 히트맵 썸네일에도 제공한다.
    """
    widget.setContextMenuPolicy(Qt.CustomContextMenu)

    def _show(pos) -> None:
        path = str(path_getter())
        if not path:
            return
        menu = QMenu(widget)
        menu.addAction("경로 복사", lambda: QGuiApplication.clipboard().setText(path))
        menu.addAction(
            "파일 열기",
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)),
        )
        menu.addAction(
            "폴더 열기",
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent))),
        )
        menu.exec(widget.mapToGlobal(pos))

    widget.customContextMenuRequested.connect(_show)


def _blank_holder(px: int) -> QLabel:
    """썸네일 자리. 사진 바탕은 두 테마 모두 순검정이고 hover 에서만 테두리가 accent 로 간다."""
    t = theme.fluent_tokens(isDarkTheme())
    holder = QLabel()
    holder.setObjectName("clusterThumb")
    holder.setAlignment(Qt.AlignCenter)
    holder.setFixedSize(px, int(px * 0.78))
    holder.setStyleSheet(
        f"QLabel#clusterThumb {{ background:{theme.PHOTO_BG};"
        f" border:1px solid {theme.flatten(t['cardBorder'], t['win'])};"
        f" border-radius:4px; color:rgba(255,255,255,0.62);"
        f" font-size:{int(theme.TYPO['captionSm']['size'])}px; }}"
        f"QLabel#clusterThumb:hover {{ border-color:{t['accentFill']}; }}"
    )
    return holder


def _start_loading_anim(holder: QLabel) -> None:
    """지연 로딩 placeholder 에 '로딩' 말줄임(…) 애니메이션을 건다(홀더 자식 타이머)."""
    holder._load_dots = 0  # type: ignore[attr-defined]
    holder.setText("로딩")
    timer = QTimer(holder)
    timer.setInterval(350)

    def _tick() -> None:
        holder._load_dots = (holder._load_dots + 1) % 4  # type: ignore[attr-defined]
        holder.setText("로딩" + "." * holder._load_dots)  # type: ignore[attr-defined]

    timer.timeout.connect(_tick)
    timer.start()
    holder._load_timer = timer  # type: ignore[attr-defined]


def _stop_loading_anim(holder: QLabel) -> None:
    timer = getattr(holder, "_load_timer", None)
    if timer is not None:
        timer.stop()
        holder._load_timer = None  # type: ignore[attr-defined]


def fill_holder(holder: QLabel, thumb_cache, image_path, px: int) -> None:
    """(UI 스레드) 캐시된 썸네일을 holder 에 그린다. 실패 시 '이미지 없음'."""
    _stop_loading_anim(holder)  # 로딩 애니메이션 정지 후 실제 이미지로 교체
    path = thumb_cache.get_full_thumbnail(image_path, max_size=px) \
        if thumb_cache is not None else None
    if path is not None:
        pix = QPixmap(str(path))
        if not pix.isNull():
            holder.setPixmap(
                pix.scaled(px, int(px * 0.78), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            holder.setToolTip(str(image_path))
            return
    holder.setText("이미지 없음")


def load_thumb_holder(thumb_cache, image_path, px: int, defer: bool = False) -> QLabel:
    """썸네일 QLabel. defer=True 면 '로딩…' 애니메이션을 두고 나중에 fill_holder 로 채운다."""
    holder = _blank_holder(px)
    if defer:
        _start_loading_anim(holder)
        return holder
    fill_holder(holder, thumb_cache, image_path, px)
    return holder


class ClickThumb(QWidget):
    """썸네일 홀더를 감싸 클릭 시 원본 뷰어를 여는 래퍼."""

    def __init__(self, holder: QLabel, record, open_viewer, parent=None):
        super().__init__(parent)
        self._record = record
        self._open_viewer = open_viewer
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(holder)
        self.setCursor(Qt.PointingHandCursor)
        # 우클릭 → 경로 복사·파일/폴더 열기
        if record is not None:
            attach_image_context_menu(self, lambda: record.image_path)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and self._record is not None:
            self._open_viewer(self._record)


class ClusterMembersPopup(QDialog):
    """근접해 하나로 묶인 defect 사진 전체를 보여주는 시트(03-screens §10).

    생성자 계약 `(records, layer, thumb_cache, open_viewer, parent)` 는 유지한다. 호출부가
    둘(판독대 '＋n', 히트맵)이라 위치 인자를 바꾸면 한쪽이 조용히 어긋난다. '전부 명세에
    담기' 는 키워드 인자로만 더한다.
    """

    def __init__(
        self,
        records: list,
        layer: str,
        thumb_cache,
        open_viewer,
        parent=None,
        add_to_export=None,
    ):
        super().__init__(parent)
        self._records = list(records)
        self._add_to_export = add_to_export
        self.setObjectName("clusterSheet")
        self.setWindowTitle(f"{layer} · 묶인 defect {len(self._records)}개")
        self.setMinimumWidth(_SHEET_W)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            theme.SPACING["cardMax"], theme.SPACING["cardMax"],
            theme.SPACING["cardMax"], theme.SPACING["cardMin"],
        )
        outer.setSpacing(theme.SPACING["gapM"])

        head = QVBoxLayout()
        head.setSpacing(2)
        self.lbl_title = SubtitleLabel(f"{layer} 근접 묶음 {len(self._records)}장", self)
        head.addWidget(self.lbl_title)
        self.lbl_sub = CaptionLabel(
            "같은 자리에 근접해 하나로 접힌 defect 입니다. 누르면 원본을 엽니다.", self
        )
        self.lbl_sub.setObjectName("dim")
        head.addWidget(self.lbl_sub)
        outer.addLayout(head)

        host = QWidget(self)
        flow = FlowLayout(host, margin=0, h_spacing=theme.SPACING["gapS"],
                          v_spacing=theme.SPACING["gapS"])
        for rec in self._records:
            thumb = ClickThumb(load_thumb_holder(thumb_cache, rec.image_path, _THUMB_PX),
                               rec, open_viewer)
            flow.addWidget(thumb)
        # FlowLayout 의 sizeHint 는 한 장 크기라, 스크롤 없이 두면 둘째 줄부터 잘린다.
        # 묶음이 몇 장이든 열리게 스크롤에 넣고 첫 화면 높이만 줄 수로 계산한다.
        stage = SmoothScrollArea(self)
        stage.setWidgetResizable(True)
        stage.setFrameShape(QFrame.NoFrame)
        # Fluent 위젯이라 setStyleSheet 로 덮으면 스크롤바 스타일까지 같이 날아간다.
        setCustomStyleSheet(stage, _TRANSPARENT, _TRANSPARENT)
        stage.viewport().setStyleSheet("background: transparent;")
        stage.setWidget(host)
        stage.setMinimumHeight(_stage_height(len(self._records)))
        outer.addWidget(stage, 1)
        self.stage = stage

        row = QHBoxLayout()
        row.setSpacing(theme.SPACING["gapS"])
        row.addStretch(1)
        self.btn_add = PrimaryPushButton("전부 명세에 담기", self)
        self.btn_add.setMinimumHeight(theme.fluent_height("primary"))
        self.btn_add.setToolTip("이 묶음 전체를 출력 명세에 담습니다.")
        self.btn_add.clicked.connect(self._emit_add_all)
        # 담을 곳이 없으면 버튼을 두지 않는다. 눌리는데 아무 일도 없으면 고장으로 읽힌다.
        self.btn_add.setVisible(add_to_export is not None)
        row.addWidget(self.btn_add)
        self.btn_close = PushButton("닫기", self)
        self.btn_close.setMinimumHeight(theme.fluent_height("primary"))
        self.btn_close.clicked.connect(self.accept)
        row.addWidget(self.btn_close)
        outer.addLayout(row)
        self._apply_tokens()
        qconfig.themeChanged.connect(self._apply_tokens)

    def _emit_add_all(self) -> None:
        """묶음 전체를 위임한다. 담고 나면 시트를 닫는다(끝난 일이라 남아 있을 이유가 없다)."""
        if self._add_to_export is None:
            return
        self._add_to_export(list(self._records))
        self.accept()

    def _apply_tokens(self, *_args) -> None:
        """시트 면. 순수 Qt 위젯이라 setStyleSheet 를 쓴다."""
        t = theme.fluent_tokens(isDarkTheme())
        self.setStyleSheet(
            f"QDialog#clusterSheet {{ background:{t['win']};"
            f" border-radius:{theme.RADIUS['sheet']}px; }}"
        )


class ClusteredThumb(QWidget):
    """대표 썸네일 + layer 배지 + (클러스터면) 좌하단 '+n' 버튼.

    대표 클릭 → 원본 확대. '+n' 클릭 → 묶인 defect 전체 팝업.
    """

    def __init__(self, cluster: Cluster, layer: str, is_base: bool,
                 thumb_cache, open_viewer, px: int, parent=None, defer: bool = False):
        super().__init__(parent)
        self._cluster = cluster
        self._layer = layer
        self._thumb_cache = thumb_cache
        self._open_viewer = open_viewer
        rep = cluster.representative
        # 비동기(지연) 로딩용으로 holder·경로·크기를 노출한다.
        self.rep_path = rep.image_path
        self._px = px

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        holder = load_thumb_holder(thumb_cache, rep.image_path, px, defer=defer)
        self.holder = holder
        holder.setCursor(Qt.PointingHandCursor)
        # 대표 클릭 → 뷰어
        holder.mousePressEvent = self._on_rep_click  # type: ignore[assignment]
        # 우클릭 → 경로 복사·파일/폴더 열기(메인 그리드와 동일)
        attach_image_context_menu(
            holder, lambda: self._cluster.representative.image_path
        )
        # layer 배지
        badge = QLabel(("★ " + layer) if is_base else layer, holder)
        badge.setObjectName("layerBadgeBase" if is_base else "layerBadge")
        badge.adjustSize()
        badge.move(5, 5)
        badge.show()
        # '+n' 오버레이 버튼(클러스터 여분)
        if cluster.extra_count > 0:
            more = QPushButton(f"+{cluster.extra_count}", holder)
            more.setObjectName("mini")
            more.setToolTip("이 자리에 근접해 하나로 묶인 defect 을 모두 봅니다.")
            more.setCursor(Qt.PointingHandCursor)
            more.adjustSize()
            more.move(5, holder.height() - more.height() - 5)
            more.clicked.connect(self._on_more)
            more.show()
        lay.addWidget(holder)

    def fill(self) -> None:
        """지연 로딩(defer)한 대표 썸네일을 실제 이미지로 채운다(UI 스레드)."""
        fill_holder(self.holder, self._thumb_cache, self.rep_path, self._px)

    def _on_rep_click(self, event):
        if event.button() == Qt.LeftButton:
            self._open_viewer(self._cluster.representative)

    def _on_more(self) -> None:
        popup = ClusterMembersPopup(
            self._cluster.members, self._layer, self._thumb_cache, self._open_viewer, self
        )
        popup.exec()
