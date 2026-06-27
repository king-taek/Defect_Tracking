"""겹쳐 보기 / 블링크 비교 (read-only).

기준 이미지와 선택한 비교 layer 이미지를 같은 자리에 겹쳐 보며, 불투명도 조절 또는
블링크(번갈아 표시)로 층간 defect 위치/크기 변화를 감지한다. 원본은 읽기 전용.

실사용 보정:
  - KLA 등 상하/좌우 검은 letterbox 를 자동 크롭(_autocrop)해 실제 화면만 비교.
  - defect 는 이미지 중앙에 위치하므로 두 이미지를 **중앙 기준**으로 겹친다.
  - 배율이 다른 점을 사람이 맞출 수 있도록 비교 이미지 **배율(50~150%)** 과
    **위치 미세조정(화살표 키/버튼)** 을 제공한다.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import (
    QImage,
    QImageReader,
    QKeySequence,
    QPainter,
    QPixmap,
    QShortcut,
)
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
_BLACK_THRESHOLD = 18  # 이보다 어두우면 검은 여백으로 간주
_NUDGE = 5  # 위치 미세조정 한 칸(px)


def _load(path) -> QImage:
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    return reader.read()


def _autocrop(img: QImage, thresh: int = _BLACK_THRESHOLD) -> QImage:
    """가장자리의 거의 검은 행/열(letterbox)을 잘라낸다(다운샘플로 빠르게)."""
    if img.isNull():
        return img
    w, h = img.width(), img.height()
    # 검출은 축소본에서(속도), 좌표는 원본으로 환산
    if max(w, h) > 256:
        small = img.scaled(256, 256, Qt.KeepAspectRatio, Qt.FastTransformation)
    else:
        small = img
    sw, sh = small.width(), small.height()
    if sw < 2 or sh < 2:
        return img

    def row_lit(y: int) -> bool:
        for x in range(sw):
            c = small.pixelColor(x, y)
            if max(c.red(), c.green(), c.blue()) > thresh:
                return True
        return False

    def col_lit(x: int) -> bool:
        for y in range(sh):
            c = small.pixelColor(x, y)
            if max(c.red(), c.green(), c.blue()) > thresh:
                return True
        return False

    top = 0
    while top < sh and not row_lit(top):
        top += 1
    bot = sh - 1
    while bot > top and not row_lit(bot):
        bot -= 1
    left = 0
    while left < sw and not col_lit(left):
        left += 1
    right = sw - 1
    while right > left and not col_lit(right):
        right -= 1
    if top >= bot or left >= right:
        return img  # 전부 어둡거나 검출 실패 → 원본 유지
    fx, fy = w / sw, h / sh
    rect = QRect(
        int(left * fx), int(top * fy),
        max(1, int((right - left + 1) * fx)), max(1, int((bot - top + 1) * fy)),
    )
    return img.copy(rect)


class OverlayCompareDialog(QDialog):
    """기준 + 비교 layer 겹쳐 보기/블링크 (자동 크롭·중앙 정렬·수동 배율/이동)."""

    def __init__(
        self,
        base: DefectRecord,
        base_layer: str,
        pairs: list[tuple[str, DefectRecord]],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("겹쳐 보기 / 블링크")
        self.setMinimumSize(640, 580)
        self.resize(900, 780)
        self._base_layer = base_layer
        self._base_img = _autocrop(_load(base.image_path))
        self._pairs = pairs
        self._comp_imgs = [_autocrop(_load(rec.image_path)) for _, rec in pairs]

        self._scale = 1.0          # 전체 줌
        self._ov_scale = 1.0       # 비교 이미지 상대 배율
        self._ov_dx = 0            # 비교 이미지 가로 오프셋(px, 화면 기준)
        self._ov_dy = 0            # 세로 오프셋
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
        QShortcut(QKeySequence(Qt.Key_Left), self, activated=lambda: self._nudge(-_NUDGE, 0))
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=lambda: self._nudge(_NUDGE, 0))
        QShortcut(QKeySequence(Qt.Key_Up), self, activated=lambda: self._nudge(0, -_NUDGE))
        QShortcut(QKeySequence(Qt.Key_Down), self, activated=lambda: self._nudge(0, _NUDGE))

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        # 1행: layer 선택 / 불투명도 / 블링크
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
        self.sld_opacity.setFixedWidth(120)
        self.sld_opacity.valueChanged.connect(self._render)
        bar.addWidget(self.sld_opacity)

        self.btn_blink = QPushButton("블링크 (Space)")
        self.btn_blink.setCheckable(True)
        self.btn_blink.toggled.connect(self._set_blink)
        bar.addWidget(self.btn_blink)
        bar.addStretch()
        outer.addLayout(bar)

        # 2행: 비교 배율 / 위치 미세조정 / 줌 / 닫기
        bar2 = QHBoxLayout()
        bar2.addWidget(QLabel("비교 배율"))
        self.sld_ovscale = QSlider(Qt.Horizontal)
        self.sld_ovscale.setRange(50, 150)
        self.sld_ovscale.setValue(100)
        self.sld_ovscale.setFixedWidth(120)
        self.sld_ovscale.valueChanged.connect(self._on_ovscale)
        bar2.addWidget(self.sld_ovscale)

        bar2.addSpacing(8)
        bar2.addWidget(QLabel("위치"))
        for text, dx, dy in (("←", -_NUDGE, 0), ("→", _NUDGE, 0), ("↑", 0, -_NUDGE), ("↓", 0, _NUDGE)):
            b = QPushButton(text)
            b.setFixedWidth(34)
            b.clicked.connect(lambda _=False, x=dx, y=dy: self._nudge(x, y))
            bar2.addWidget(b)
        b_reset = QPushButton("정렬 초기화")
        b_reset.clicked.connect(self._reset_align)
        bar2.addWidget(b_reset)

        bar2.addStretch()
        btn_out = QPushButton("－")
        btn_out.setFixedWidth(36)
        btn_out.clicked.connect(lambda: self._zoom(0.8))
        btn_in = QPushButton("＋")
        btn_in.setFixedWidth(36)
        btn_in.clicked.connect(lambda: self._zoom(1.25))
        bar2.addWidget(btn_out)
        bar2.addWidget(btn_in)
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.accept)
        bar2.addWidget(btn_close)
        outer.addLayout(bar2)

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

    # ---- 상태 변경 ----
    def _on_ovscale(self) -> None:
        self._ov_scale = self.sld_ovscale.value() / 100.0
        self._render()

    def _nudge(self, dx: int, dy: int) -> None:
        self._ov_dx += dx
        self._ov_dy += dy
        self._render()

    def _reset_align(self) -> None:
        self._ov_dx = self._ov_dy = 0
        self._ov_scale = 1.0
        self.sld_ovscale.setValue(100)
        self._render()

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

    def _comp_on_base(self, base_pix: QPixmap) -> Optional[QPixmap]:
        """비교 이미지를 base_pix 크기 캔버스에 중앙+배율+오프셋으로 배치한 pixmap."""
        comp = self._current_comp()
        if comp.isNull():
            return None
        bw, bh = base_pix.width(), base_pix.height()
        # 기본은 base 와 같은 자리에 맞추되(KeepAspect), 비교 배율을 곱한다
        cw = max(1, int(bw * self._ov_scale))
        ch = max(1, int(bh * self._ov_scale))
        comp_scaled = QPixmap.fromImage(comp).scaled(
            cw, ch, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        canvas = QPixmap(bw, bh)
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        x = (bw - comp_scaled.width()) // 2 + self._ov_dx
        y = (bh - comp_scaled.height()) // 2 + self._ov_dy
        painter.drawPixmap(QPoint(x, y), comp_scaled)
        painter.end()
        return canvas

    def _render(self) -> None:
        base = self._base_img
        if base.isNull():
            return
        w = max(1, int(base.width() * self._scale))
        h = max(1, int(base.height() * self._scale))
        base_pix = QPixmap.fromImage(base).scaled(
            w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        comp_pix = self._comp_on_base(base_pix)
        align = f"배율 {int(self._ov_scale * 100)}% · 이동 ({self._ov_dx},{self._ov_dy})"

        if self._blink:
            if self._blink_show_base or comp_pix is None:
                out = base_pix
                self._hint.setText(f"블링크: ★ {self._base_layer} (기준)  ·  {align}")
            else:
                out = QPixmap(base_pix.size())
                out.fill(Qt.black)
                p = QPainter(out)
                p.drawPixmap(0, 0, comp_pix)
                p.end()
                self._hint.setText(f"블링크: {self.cmb_layer.currentText()}  ·  {align}")
        else:
            out = QPixmap(base_pix)
            if comp_pix is not None:
                painter = QPainter(out)
                painter.setOpacity(self.sld_opacity.value() / 100.0)
                painter.drawPixmap(0, 0, comp_pix)
                painter.end()
            self._hint.setText(
                f"★ {self._base_layer} + {self.cmb_layer.currentText()} "
                f"(불투명도 {self.sld_opacity.value()}%)  ·  {align}"
            )
        self._canvas.setPixmap(out)
        self._canvas.resize(out.size())
