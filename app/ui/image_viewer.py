"""원본 확대 뷰어 (read-only) — defect review 사용성.

그리드의 이미지를 클릭하면 원본 전체 해상도를 별도 창에서 확대해 본다.
맞춤/실제(1:1) 토글, 마우스 휠 줌, 메타데이터 표시, Esc 닫기를 지원한다.
원본은 QImageReader 로 읽기 전용 접근만 하며 수정하지 않는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.models import DefectRecord, Source

_MIN_SCALE = 0.1
_MAX_SCALE = 8.0


class ImageViewerDialog(QDialog):
    """원본 전체 해상도 확대 뷰어."""

    def __init__(self, record: DefectRecord, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.record = record
        self.setWindowTitle(f"원본 보기 — {Path(record.image_path).name}")
        self.setMinimumSize(640, 520)
        self.resize(960, 760)
        self._scale = 1.0
        self._fit = True
        # 클릭-드래그 패닝 상태(항목 6)
        self._panning = False
        self._pan_start = None  # QPoint (뷰포트 좌표)
        self._pan_h0 = 0
        self._pan_v0 = 0

        self._image = self._load(record.image_path)
        self._build()
        self._apply_scale(fit=True)

        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.accept)
        QShortcut(QKeySequence.ZoomIn, self, activated=lambda: self._zoom(1.25))
        QShortcut(QKeySequence.ZoomOut, self, activated=lambda: self._zoom(0.8))

    @staticmethod
    def _load(path) -> QImage:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)  # EXIF 회전 반영
        img = reader.read()
        return img  # null 이면 placeholder 처리

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        # 사진을 열면 '정보 복사'와 동일한 라벨링된 정보를 그대로 텍스트로 보여준다(작은 글씨).
        meta = QLabel(self._info_text())
        meta.setTextFormat(Qt.PlainText)
        meta.setWordWrap(True)
        meta.setObjectName("meta")
        self._meta = meta
        # 정보 텍스트를 드래그 선택·복사 가능하게(Ctrl+C). 마우스 커서도 텍스트형으로.
        meta.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        meta.setCursor(Qt.IBeamCursor)
        meta_row = QHBoxLayout()
        meta_row.addWidget(meta, 1)
        btn_copy = QPushButton("정보 복사")
        btn_copy.setObjectName("mini")
        btn_copy.setToolTip("이 사진의 layer·wafer·die·좌표·경로를 클립보드로 복사")
        btn_copy.clicked.connect(self._copy_info)
        meta_row.addWidget(btn_copy, 0, Qt.AlignTop)
        outer.addLayout(meta_row)

        bar = QHBoxLayout()
        self.btn_fit = QPushButton("실제 크기 (1:1)")
        self.btn_fit.setCheckable(False)
        self.btn_fit.clicked.connect(self._toggle_fit)
        btn_zoom_out = QPushButton("－")
        btn_zoom_out.setFixedWidth(40)
        btn_zoom_out.clicked.connect(lambda: self._zoom(0.8))
        btn_zoom_in = QPushButton("＋")
        btn_zoom_in.setFixedWidth(40)
        btn_zoom_in.clicked.connect(lambda: self._zoom(1.25))
        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setObjectName("dim")
        self.lbl_zoom.setFixedWidth(56)
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.accept)

        bar.addWidget(self.btn_fit)
        bar.addWidget(btn_zoom_out)
        bar.addWidget(self.lbl_zoom)
        bar.addWidget(btn_zoom_in)
        bar.addStretch()
        bar.addWidget(btn_close)
        outer.addLayout(bar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignCenter)
        # 확대 시 스크롤바는 못 쓰므로(드래그로 이동) 숨긴다. value 이동은 계속 동작.
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._canvas = QLabel()
        self._canvas.setAlignment(Qt.AlignCenter)
        if self._image.isNull():
            self._canvas.setText("이미지를 불러올 수 없습니다.")
        else:
            # 클릭-드래그로 화면 이동: 캔버스에서 마우스 이벤트를 받는다.
            self._canvas.setCursor(Qt.OpenHandCursor)
            self._canvas.installEventFilter(self)
            # 휠은 스크롤이 아니라 항상 줌으로만 동작하도록 뷰포트/캔버스에서 가로챈다.
            self._scroll.viewport().installEventFilter(self)
        self._scroll.setWidget(self._canvas)
        outer.addWidget(self._scroll, 1)

    def _coord_versions(self):
        """die 내부 좌표를 Camtek·KLA 두 규약으로 반환. (x,y) 없으면 None.

        record 의 (x,y) 는 매칭을 위해 top-left 원점(Camtek 규약)으로 저장된다.
        KLA 규약은 within-die Y 를 DiePitchY 기준으로 반전한 값(YREL)이며 X 는 동일하다.
        DiePitchY 는 record 에 저장된 info 실측값(die_pitch_y)을 우선 쓰고, 없으면(Camtek 등
        info 가 없는 소스) 활성 제품의 camtek_pitch_y 로 폴백한다.
        """
        r = self.record
        if r.x is None or r.y is None:
            return None
        pitch_y = r.die_pitch_y if r.die_pitch_y is not None \
            else config.active_product().camtek_pitch_y
        camtek = (round(r.x), round(r.y))
        kla = (round(r.x), round(pitch_y - r.y))
        return camtek, kla

    def _info_text(self) -> str:
        """표시·클립보드 복사용 정돈된 정보 텍스트."""
        r = self.record
        parts = [
            f"layer: {r.layer}",
            f"wafer: {r.wafer_id}",
            f"die: ({r.col},{r.row})",
        ]
        cv = self._coord_versions()
        if cv is not None:
            (cx, cy), (kx, ky) = cv
            # 사진을 실제 scan 한 도구의 좌표가 measured, 반대 규약으로 환산한 값이 calculated.
            kla_scanned = r.source == Source.KLA
            camtek_tag = "calculated" if kla_scanned else "measured"
            kla_tag = "measured" if kla_scanned else "calculated"
            parts.append(f"coordinate (Camtek): ({cx}, {cy}) -> {camtek_tag}")
            parts.append(f"coordinate (KLA): ({kx}, {ky}) -> {kla_tag}")
        if r.defect_name:
            parts.append(f"defect: {r.defect_name}")
        if r.dx_size is not None or r.dy_size is not None or r.d_area is not None:
            parts.append(f"size: dx={r.dx_size}, dy={r.dy_size}, area={r.d_area}")
        parts.append(f"path: {r.image_path}")
        return "\n".join(parts)

    def _copy_info(self) -> None:
        QApplication.clipboard().setText(self._info_text())

    # ---- 줌/맞춤 ---------------------------------------------------------
    def _toggle_fit(self) -> None:
        if self._fit:
            self._apply_scale(scale=1.0)  # 실제 크기
        else:
            self._apply_scale(fit=True)

    def _zoom(self, factor: float) -> None:
        if self._image.isNull():
            return
        self._apply_scale(scale=max(_MIN_SCALE, min(_MAX_SCALE, self._scale * factor)))

    def _zoom_at_cursor(self, factor: float) -> None:
        """마우스 커서 아래 지점을 고정한 채 확대/축소(휠 줌)."""
        if self._image.isNull():
            return
        from PySide6.QtGui import QCursor
        vp = self._scroll.viewport()
        pos = vp.mapFromGlobal(QCursor.pos())
        hbar = self._scroll.horizontalScrollBar()
        vbar = self._scroll.verticalScrollBar()
        old = self._scale
        new = max(_MIN_SCALE, min(_MAX_SCALE, old * factor))
        if new == old:
            return
        # 스케일 전, 커서 아래 콘텐츠 좌표
        cx = hbar.value() + pos.x()
        cy = vbar.value() + pos.y()
        self._apply_scale(scale=new)
        ratio = new / old
        # 스케일 후 그 콘텐츠 좌표가 다시 커서 아래 오도록 스크롤 이동
        hbar.setValue(round(cx * ratio - pos.x()))
        vbar.setValue(round(cy * ratio - pos.y()))

    def _apply_scale(self, scale: Optional[float] = None, fit: bool = False) -> None:
        if self._image.isNull():
            return
        if fit:
            self._fit = True
            area = self._scroll.viewport().size()
            iw, ih = self._image.width(), self._image.height()
            if iw > 0 and ih > 0:
                self._scale = min(area.width() / iw, area.height() / ih, 1.0)
                self._scale = max(self._scale, _MIN_SCALE)
        else:
            self._fit = False
            self._scale = scale if scale is not None else self._scale

        w = max(1, int(self._image.width() * self._scale))
        h = max(1, int(self._image.height() * self._scale))
        pix = QPixmap.fromImage(self._image).scaled(
            w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self._canvas.setPixmap(pix)
        self._canvas.resize(pix.size())
        self.lbl_zoom.setText(f"{int(self._scale * 100)}%")
        self.btn_fit.setText("화면 맞춤" if not self._fit else "실제 크기 (1:1)")

    def wheelEvent(self, event):  # noqa: N802
        if self._image.isNull():
            return
        delta = event.angleDelta().y()
        if delta != 0:
            self._zoom_at_cursor(1.2 if delta > 0 else 1 / 1.2)
            event.accept()

    # ---- 클릭-드래그 패닝(항목 6) --------------------------------------
    def eventFilter(self, obj, event):  # noqa: N802
        """휠=줌 전용, 캔버스 좌클릭 드래그=화면 이동."""
        from PySide6.QtCore import QEvent

        # 휠은 스크롤 영역이 먹어 스크롤되지 않도록 가로채 항상 줌으로만 처리한다.
        if event.type() == QEvent.Wheel and not self._image.isNull():
            delta = event.angleDelta().y()
            if delta != 0:
                self._zoom_at_cursor(1.2 if delta > 0 else 1 / 1.2)
            return True

        if obj is self._canvas and not self._image.isNull():
            et = event.type()
            if et == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._panning = True
                self._pan_start = event.globalPosition().toPoint()
                self._pan_h0 = self._scroll.horizontalScrollBar().value()
                self._pan_v0 = self._scroll.verticalScrollBar().value()
                self._canvas.setCursor(Qt.ClosedHandCursor)
                return True
            if et == QEvent.MouseMove and self._panning and self._pan_start is not None:
                delta = event.globalPosition().toPoint() - self._pan_start
                self._scroll.horizontalScrollBar().setValue(self._pan_h0 - delta.x())
                self._scroll.verticalScrollBar().setValue(self._pan_v0 - delta.y())
                return True
            if et == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                self._panning = False
                self._pan_start = None
                self._canvas.setCursor(Qt.OpenHandCursor)
                return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if self._fit:
            self._apply_scale(fit=True)
