"""겹쳐 보기 / 블링크 비교 (read-only).

기준 이미지와 선택한 비교 layer 이미지를 같은 자리에 겹쳐 보며, 불투명도 조절 또는
블링크(번갈아 표시)로 층간 defect 위치/크기 변화를 감지한다. 원본은 읽기 전용.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QImageReader, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.models import DefectRecord

_MIN_SCALE = 0.1
_MAX_SCALE = 8.0


def _load(path) -> QImage:
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    return reader.read()


class OverlayCompareDialog(QDialog):
    """기준 + 비교 layer 겹쳐 보기/블링크."""

    def __init__(
        self,
        base: DefectRecord,
        base_layer: str,
        pairs: list[tuple[str, DefectRecord]],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("겹쳐 보기 / 블링크")
        self.setMinimumSize(640, 560)
        self.resize(900, 760)
        self._base_layer = base_layer
        self._base_img = _load(base.image_path)
        self._pairs = pairs  # [(layer, record)]
        self._comp_imgs = [_load(rec.image_path) for _, rec in pairs]
        self._scale = 1.0
        self._blink = False
        self._blink_show_base = True

        self._timer = QTimer(self)
        self._timer.setInterval(550)
        self._timer.timeout.connect(self._on_blink_tick)

        self._build()
        self._render()

        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.accept)
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self._toggle_blink)
        QShortcut(QKeySequence.ZoomIn, self, activated=lambda: self._zoom(1.25))
        QShortcut(QKeySequence.ZoomOut, self, activated=lambda: self._zoom(0.8))

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("비교 Layer"))
        self.cmb_layer = QComboBox()
        for layer, _ in self._pairs:
            self.cmb_layer.addItem(layer)
        self.cmb_layer.currentIndexChanged.connect(self._render)
        bar.addWidget(self.cmb_layer)

        bar.addSpacing(12)
        bar.addWidget(QLabel("불투명도"))
        self.sld_opacity = QSlider(Qt.Horizontal)
        self.sld_opacity.setRange(0, 100)
        self.sld_opacity.setValue(50)
        self.sld_opacity.setFixedWidth(140)
        self.sld_opacity.valueChanged.connect(self._render)
        bar.addWidget(self.sld_opacity)

        self.btn_blink = QPushButton("블링크 (Space)")
        self.btn_blink.setCheckable(True)
        self.btn_blink.toggled.connect(self._set_blink)
        bar.addWidget(self.btn_blink)

        bar.addStretch()
        btn_out = QPushButton("－")
        btn_out.setFixedWidth(40)
        btn_out.clicked.connect(lambda: self._zoom(0.8))
        btn_in = QPushButton("＋")
        btn_in.setFixedWidth(40)
        btn_in.clicked.connect(lambda: self._zoom(1.25))
        bar.addWidget(btn_out)
        bar.addWidget(btn_in)
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.accept)
        bar.addWidget(btn_close)
        outer.addLayout(bar)

        self._hint = QLabel("")
        self._hint.setObjectName("dim")
        self._hint.setAlignment(Qt.AlignCenter)
        outer.addWidget(self._hint)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignCenter)
        self._canvas = QLabel()
        self._canvas.setAlignment(Qt.AlignCenter)
        if self._base_img.isNull():
            self._canvas.setText("기준 이미지를 불러올 수 없습니다.")
        self._scroll.setWidget(self._canvas)
        outer.addWidget(self._scroll, 1)

    # ---- 블링크 ----
    def _toggle_blink(self) -> None:
        self.btn_blink.toggle()

    def _set_blink(self, on: bool) -> None:
        self._blink = on
        if on:
            self._blink_show_base = True
            self._timer.start()
        else:
            self._timer.stop()
        self._render()

    def _on_blink_tick(self) -> None:
        self._blink_show_base = not self._blink_show_base
        self._render()

    def _zoom(self, factor: float) -> None:
        self._scale = max(_MIN_SCALE, min(_MAX_SCALE, self._scale * factor))
        self._render()

    def wheelEvent(self, event):  # noqa: N802
        delta = event.angleDelta().y()
        if delta != 0:
            self._zoom(1.2 if delta > 0 else 1 / 1.2)
            event.accept()

    def _current_comp(self) -> QImage:
        i = self.cmb_layer.currentIndex()
        if 0 <= i < len(self._comp_imgs):
            return self._comp_imgs[i]
        return QImage()

    def _render(self) -> None:
        base = self._base_img
        if base.isNull():
            return
        w = max(1, int(base.width() * self._scale))
        h = max(1, int(base.height() * self._scale))
        base_pix = QPixmap.fromImage(base).scaled(
            w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        comp = self._current_comp()

        if self._blink:
            if self._blink_show_base or comp.isNull():
                out = base_pix
                self._hint.setText(f"블링크: ★ {self._base_layer} (기준)")
            else:
                out = QPixmap.fromImage(comp).scaled(
                    base_pix.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self._hint.setText(f"블링크: {self.cmb_layer.currentText()}")
        else:
            out = QPixmap(base_pix)
            if not comp.isNull():
                painter = QPainter(out)
                painter.setOpacity(self.sld_opacity.value() / 100.0)
                comp_pix = QPixmap.fromImage(comp).scaled(
                    out.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                painter.drawPixmap(0, 0, comp_pix)
                painter.end()
            self._hint.setText(
                f"★ {self._base_layer} + {self.cmb_layer.currentText()} "
                f"(불투명도 {self.sld_opacity.value()}%)"
            )
        self._canvas.setPixmap(out)
        self._canvas.resize(out.size())
