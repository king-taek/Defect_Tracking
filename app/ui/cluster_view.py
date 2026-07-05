"""클러스터 defect 표시용 공유 위젯 (히트맵·메인 매치 공통).

- `load_thumb_holder`: 썸네일 QLabel 생성.
- `ClickThumb`: 썸네일 클릭 시 원본 뷰어 열기.
- `ClusteredThumb`: 대표 썸네일 + layer 배지 + (클러스터면) 좌하단 '+n' 버튼.
- `ClusterMembersPopup`: 묶인 defect 전체를 가로(줄바꿈)로 보여주는 팝업.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.clustering import Cluster
from app.ui import theme
from app.ui.flow_layout import FlowLayout


def _blank_holder(px: int) -> QLabel:
    holder = QLabel()
    holder.setAlignment(Qt.AlignCenter)
    holder.setFixedSize(px, int(px * 0.78))
    holder.setStyleSheet(
        f"background:{theme.BG}; border:1px solid {theme.NEON_SOFT};"
        f" border-radius:6px; color:{theme.TEXT_DIM}; font-size:10px;"
    )
    return holder


def fill_holder(holder: QLabel, thumb_cache, image_path, px: int) -> None:
    """(UI 스레드) 캐시된 썸네일을 holder 에 그린다. 실패 시 '이미지 없음'."""
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
    """썸네일 이미지 QLabel(배지 없음). defer=True 면 '…'만 두고 나중에 fill_holder 로 채운다."""
    holder = _blank_holder(px)
    if defer:
        holder.setText("로딩…")
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

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and self._record is not None:
            self._open_viewer(self._record)


class ClusterMembersPopup(QDialog):
    """클러스터에 묶인 defect 사진 전체를 가로(줄바꿈)로 보여주는 작은 팝업."""

    def __init__(self, records: list, layer: str, thumb_cache, open_viewer, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{layer} — 묶인 defect {len(records)}개")
        self.setMinimumWidth(520)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        cap = QLabel("거리 50 미만으로 하나로 묶인 defect (클릭=원본)")
        cap.setObjectName("dim")
        outer.addWidget(cap)
        host = QWidget()
        flow = FlowLayout(host, margin=0, h_spacing=8, v_spacing=8)
        for rec in records:
            thumb = ClickThumb(load_thumb_holder(thumb_cache, rec.image_path, 150),
                               rec, open_viewer)
            flow.addWidget(thumb)
        outer.addWidget(host)


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
            more.setToolTip("이 자리에 근접(<50)해 하나로 묶인 defect 을 모두 봅니다.")
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
