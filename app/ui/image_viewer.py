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
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.models import DefectRecord
from app.ui import theme

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

        rec = self.record
        meta = QLabel(
            f"<b>{rec.layer}</b> · wafer {rec.wafer_id} · die({rec.col},{rec.row}) · "
            f"pos {rec.position_key} · <span style='color:{theme.TEXT_DIM}'>"
            f"{rec.image_path}</span>"
        )
        meta.setWordWrap(True)
        meta.setObjectName("title")
        outer.addWidget(meta)

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
        self._canvas = QLabel()
        self._canvas.setAlignment(Qt.AlignCenter)
        if self._image.isNull():
            self._canvas.setText("이미지를 불러올 수 없습니다.")
        self._scroll.setWidget(self._canvas)
        outer.addWidget(self._scroll, 1)

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
            self._zoom(1.2 if delta > 0 else 1 / 1.2)
            event.accept()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if self._fit:
            self._apply_scale(fit=True)
