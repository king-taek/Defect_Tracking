"""원본 뷰어 시트 (read-only).

판독대의 사진을 눌러 원본 전체 해상도를 확대해 본다. 원본은 QImageReader 로 읽기만 하고
어떤 것도 쓰지 않는다.

재설계(03-screens §8)에서 바뀐 것:
- 머리 4줄(경로 포함)을 52px 한 줄로 줄였다. 전체 경로는 '정보 복사' 에만 담긴다. 경로는
  읽는 값이 아니라 옮기는 값이라 화면에서 두 줄을 차지할 이유가 없다.
- 무대를 순검정 전면으로 두고, 배율 조작은 하단 중앙 HUD 로 모았다. 사진 위에 놓되 반투명
  이라 판독을 가리지 않는다.
- 잡고 끌기(grab -> grabbing) 패닝과 커서 고정 휠 줌은 원본 동작을 그대로 이어받는다.

생성자 계약 `ImageViewerDialog(record, parent)` + `exec()` 는 유지한다(호출부 계약).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, Qt, QVariantAnimation
from PySide6.QtGui import (
    QCursor,
    QFont,
    QImage,
    QImageReader,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    FluentIcon,
    TransparentPushButton,
    TransparentToolButton,
    isDarkTheme,
    qconfig,
    setCustomStyleSheet,
)

from app import config
from app.models import DefectRecord
from app.ui import theme

_MIN_SCALE = 0.1
_MAX_SCALE = 8.0
_HEADER_H = 52
_HUD_MARGIN = 14        # 무대 아래 여백
_ZOOM_LABEL_CHARS = 6   # 배율은 등폭 6자 고정폭(값이 바뀌어도 HUD 가 흔들리지 않게)
_MONO = ("Cascadia Mono", "Consolas", "Menlo", "monospace")

# 무대는 두 테마 모두 순검정이라 그 위 글자는 테마와 무관한 흰색 알파를 쓴다.
# 값은 tests/test_tokens.py 의 '순검정 무대 텍스트' 회귀와 같은 계열이다.
_ON_STAGE = "rgba(255,255,255,0.90)"
_ON_STAGE_DIM = "rgba(255,255,255,0.72)"
_ON_STAGE_SOFT = "rgba(255,255,255,0.62)"


def _mono_font(px: int, bold: bool = False) -> QFont:
    """등폭 글꼴(수치용). 크기는 QFont 로 지정해 회귀 테스트가 읽을 수 있게 한다."""
    f = QFont()
    f.setFamilies(list(_MONO))
    f.setPixelSize(px)
    f.setWeight(QFont.DemiBold if bold else QFont.Normal)
    return f


class ImageViewerDialog(QDialog):
    """원본 전체 해상도 확대 뷰어."""

    def __init__(self, record: DefectRecord, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.record = record
        self.setObjectName("imageViewerSheet")
        self.setWindowTitle(f"원본 보기 · {Path(record.image_path).name}")
        # 최대화 버튼 힌트를 켜면 창이 확실히 리사이즈 가능한 일반 창으로 동작한다.
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint
        )
        self.setSizeGripEnabled(True)
        self.setMinimumSize(640, 440)
        self.resize(960, 620)
        self._scale = 1.0
        self._fit = True
        # 잡고 끌기 패닝 상태
        self._panning = False
        self._pan_start: Optional[QPoint] = None
        self._pan_h0 = 0
        self._pan_v0 = 0
        # 줌 애니메이션(250ms OutQuint)과 그 동안 유지할 고정점
        self._zoom_anim: Optional[QVariantAnimation] = None
        self._hud_state: Optional[tuple[bool, bool]] = None

        self._image = self._load(record.image_path)
        self._build()
        self._apply_tokens()
        qconfig.themeChanged.connect(self._apply_tokens)
        self._apply_scale(fit=True)
        # 최초 표시 전엔 viewport 크기가 아직 확정되지 않아 잘려 보일 수 있다.
        # 첫 showEvent 에서 실제 크기로 한 번 더 정확히 재계산한다.
        self._fit_pending = True

        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.accept)
        QShortcut(QKeySequence.ZoomIn, self, activated=lambda: self._zoom(1.25))
        QShortcut(QKeySequence.ZoomOut, self, activated=lambda: self._zoom(0.8))

    @staticmethod
    def _load(path) -> QImage:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)  # EXIF 회전 반영
        img = reader.read()
        return img  # null 이면 placeholder 처리

    # ------------------------------------------------------------ 구성
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())
        outer.addWidget(self._build_stage(), 1)
        self._build_hud()

    def _build_header(self) -> QWidget:
        head = QFrame(self)
        head.setObjectName("viewerHeader")
        head.setFixedHeight(_HEADER_H)
        row = QHBoxLayout(head)
        row.setContentsMargins(theme.SPACING["cardMax"], 0, theme.SPACING["gapS"], 0)
        row.setSpacing(theme.SPACING["gapM"])

        self.lbl_title = QLabel(self._title_text(), head)
        self.lbl_title.setObjectName("viewerTitle")
        row.addWidget(self.lbl_title, 0)

        # 메타는 한 줄. 값이 등폭이라 die·좌표가 자리에서 읽힌다.
        self.lbl_meta = QLabel(self._meta_text(), head)
        self.lbl_meta.setObjectName("viewerMeta")
        self.lbl_meta.setFont(_mono_font(int(theme.TYPO["caption"]["size"])))
        # 결함명·파일명에 '<' 가 들어와도 그대로 글자로 보이게(원본 계약 계승).
        self.lbl_meta.setTextFormat(Qt.PlainText)
        self.lbl_meta.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.lbl_meta.setCursor(Qt.IBeamCursor)
        self.lbl_meta.setToolTip(self._info_text())
        row.addWidget(self.lbl_meta, 1)

        self.btn_copy = TransparentPushButton("정보 복사", head)
        self.btn_copy.setToolTip("이 사진의 layer·wafer·die·좌표·경로를 클립보드로 복사")
        self.btn_copy.setMinimumHeight(theme.fluent_height("control"))
        self.btn_copy.clicked.connect(self._copy_info)
        row.addWidget(self.btn_copy, 0)

        self.btn_close = TransparentToolButton(FluentIcon.CLOSE, head)
        self.btn_close.setToolTip("닫기 (Esc)")
        self.btn_close.setFixedSize(
            theme.fluent_height("control"), theme.fluent_height("control")
        )
        self.btn_close.clicked.connect(self.accept)
        row.addWidget(self.btn_close, 0)
        self._header = head
        return head

    def _build_stage(self) -> QWidget:
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("viewerStage")
        self._scroll.setWidgetResizable(False)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setAlignment(Qt.AlignCenter)
        # 확대 시 스크롤바 대신 잡고 끌기로 움직인다. value 이동은 계속 동작한다.
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._canvas = QLabel()
        self._canvas.setObjectName("viewerCanvas")
        self._canvas.setAlignment(Qt.AlignCenter)
        if self._image.isNull():
            self._canvas.setText("이미지를 불러올 수 없습니다.")
        else:
            self._canvas.setCursor(Qt.OpenHandCursor)
            self._canvas.installEventFilter(self)
            # 휠은 스크롤이 아니라 항상 줌으로 동작하도록 뷰포트/캔버스에서 가로챈다.
            self._scroll.viewport().installEventFilter(self)
        self._scroll.setWidget(self._canvas)

        # 좌하단 위치 표기. 명세의 µm 스케일바는 픽셀 대 µm 실비율 근거가 코드에 없어
        # 만들지 않는다(REVIEW-01 P1). 판독대 기준 칸과 같은 자리에 die 좌표를 둔다.
        self.lbl_die = QLabel(self._die_text(), self._scroll.viewport())
        self.lbl_die.setObjectName("viewerDie")
        self.lbl_die.setFont(_mono_font(int(theme.TYPO["captionSm"]["size"])))
        self.lbl_die.setVisible(bool(self._die_text()))
        return self._scroll

    def _build_hud(self) -> None:
        """하단 중앙 HUD: `－ 배율 ＋ | 1:1 맞춤`. 활성 항목은 채움으로 보인다."""
        hud = QFrame(self._scroll.viewport())
        hud.setObjectName("viewerHud")
        row = QHBoxLayout(hud)
        row.setContentsMargins(6, 5, 6, 5)
        row.setSpacing(theme.SPACING["gapXs"])

        self.btn_zoom_out = QPushButton("－", hud)
        self.btn_zoom_out.setObjectName("zoomGlyph")
        self.btn_zoom_out.setCursor(Qt.PointingHandCursor)
        self.btn_zoom_out.setToolTip("축소")
        self.btn_zoom_out.clicked.connect(lambda: self._zoom(0.8))
        row.addWidget(self.btn_zoom_out)

        self.lbl_zoom = QLabel("", hud)
        self.lbl_zoom.setObjectName("hudZoom")
        self.lbl_zoom.setFont(_mono_font(int(theme.TYPO["caption"]["size"])))
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        # 등폭 6자 폭으로 고정한다. 배율이 바뀔 때마다 HUD 폭이 흔들리면 눈이 따라간다.
        self.lbl_zoom.setFixedWidth(
            self.lbl_zoom.fontMetrics().horizontalAdvance("0") * _ZOOM_LABEL_CHARS + 8
        )
        row.addWidget(self.lbl_zoom)

        self.btn_zoom_in = QPushButton("＋", hud)
        self.btn_zoom_in.setObjectName("zoomGlyph")
        self.btn_zoom_in.setCursor(Qt.PointingHandCursor)
        self.btn_zoom_in.setToolTip("확대")
        self.btn_zoom_in.clicked.connect(lambda: self._zoom(1.25))
        row.addWidget(self.btn_zoom_in)

        sep = QFrame(hud)
        sep.setObjectName("hudSep")
        sep.setFixedSize(1, 18)
        row.addWidget(sep)

        self.btn_actual = QPushButton("1:1", hud)
        self.btn_actual.setObjectName("hudMode")
        self.btn_actual.setCursor(Qt.PointingHandCursor)
        self.btn_actual.setToolTip("실제 크기로 보기")
        self.btn_actual.clicked.connect(self._show_actual)
        row.addWidget(self.btn_actual)

        self.btn_fit = QPushButton("맞춤", hud)
        self.btn_fit.setObjectName("hudMode")
        self.btn_fit.setCursor(Qt.PointingHandCursor)
        self.btn_fit.setToolTip("화면에 맞추고 원점으로 돌아가기")
        self.btn_fit.clicked.connect(self._show_fit)
        row.addWidget(self.btn_fit)

        hud.adjustSize()
        self._hud = hud

    # ------------------------------------------------------------ 색
    def _apply_tokens(self, *_args) -> None:
        """머리는 테마 토큰, 무대와 HUD 는 순검정 위 흰색 알파로 칠한다.

        QDialog·QLabel·QFrame 은 순수 Qt 위젯이라 setStyleSheet 를 쓴다. Fluent 위젯
        (TransparentPushButton 등)에는 setCustomStyleSheet 로 건다.
        """
        t = theme.fluent_tokens(isDarkTheme())
        card = t["card"]
        divider = theme.flatten(t["divider"], card)
        title_px = int(theme.TYPO["body"]["size"])
        self.setStyleSheet(
            f"QDialog#imageViewerSheet {{ background:{t['win']}; }}"
            f"QFrame#viewerHeader {{ background:{card};"
            f" border-bottom:1px solid {divider}; }}"
            f"QLabel#viewerTitle {{ color:{theme.flatten(t['txt1'], card)};"
            f" font-size:{title_px}px; font-weight:600; background:transparent; }}"
            f"QLabel#viewerMeta {{ color:{theme.flatten(t['txt2'], card)};"
            " background:transparent; }"
            f"QScrollArea#viewerStage {{ background:{theme.PHOTO_BG}; border:none; }}"
            f"QLabel#viewerCanvas {{ background:{theme.PHOTO_BG};"
            f" color:{_ON_STAGE_DIM}; }}"
            f"QLabel#viewerDie {{ color:{_ON_STAGE_SOFT}; background:transparent; }}"
        )
        self._scroll.viewport().setStyleSheet(f"background:{theme.PHOTO_BG};")

        # 닫기는 hover 에서 danger 틴트. Fluent 위젯이라 커스텀 시트로 합성한다.
        light = "TransparentToolButton:hover { background: %s; }" % theme.STATUS_LIGHT["dangerBg"]
        dark = "TransparentToolButton:hover { background: %s; }" % theme.STATUS_DARK["dangerBg"]
        setCustomStyleSheet(self.btn_close, light, dark)
        self._style_hud()

    def _style_hud(self) -> None:
        """HUD 색. 활성(현재 모드) 항목만 accent 채움으로 보인다."""
        t = theme.fluent_tokens(isDarkTheme())
        radius = theme.RADIUS["control"]
        self._hud.setStyleSheet(
            f"QFrame#viewerHud {{ background:rgba(255,255,255,0.10);"
            f" border:1px solid rgba(255,255,255,0.18); border-radius:{radius + 3}px; }}"
            f"QFrame#hudSep {{ background:rgba(255,255,255,0.24); border:none; }}"
            f"QLabel#hudZoom {{ color:{_ON_STAGE}; background:transparent; }}"
            f"QPushButton#zoomGlyph, QPushButton#hudMode {{ background:transparent;"
            f" border:none; border-radius:{radius}px; color:{_ON_STAGE};"
            " padding:3px 10px; font-size:13px; font-weight:600; }"
            "QPushButton#zoomGlyph:hover, QPushButton#hudMode:hover"
            " { background:rgba(255,255,255,0.16); }"
            "QPushButton#zoomGlyph:pressed, QPushButton#hudMode:pressed"
            " { background:rgba(255,255,255,0.10); }"
        )
        fill = (
            f"background:{t['accentFill']}; color:{t['onAccent']};"
            f" border:none; border-radius:{radius}px; padding:3px 10px;"
            " font-size:13px; font-weight:600;"
        )
        idle = (
            f"background:transparent; color:{_ON_STAGE_DIM}; border:none;"
            f" border-radius:{radius}px; padding:3px 10px;"
            " font-size:13px; font-weight:600;"
        )
        actual = abs(self._scale - 1.0) < 1e-6 and not self._fit
        self.btn_actual.setStyleSheet(fill if actual else idle)
        self.btn_fit.setStyleSheet(fill if self._fit else idle)

    # ------------------------------------------------------------ 텍스트
    def _title_text(self) -> str:
        layer = getattr(self.record, "layer", "") or ""
        return f"{layer} 원본" if layer else "원본"

    def _die_text(self) -> str:
        r = self.record
        if r.col is None or r.row is None:
            return ""
        return f"die ({r.col}, {r.row})"

    def _meta_text(self) -> str:
        """머리 한 줄: SLOT · die · Camtek 좌표 · 결함명. 경로는 넣지 않는다."""
        r = self.record
        parts = [f"SLOT {r.wafer_id}"]
        if r.col is not None and r.row is not None:
            parts.append(f"die ({r.col}, {r.row})")
        cv = self._coord_versions()
        if cv is not None:
            (cx, cy), _kla = cv
            parts.append(f"Camtek ({cx}, {cy})")
        if r.defect_name:
            parts.append(r.defect_name)
        return "  ·  ".join(parts)

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
        """클립보드 복사용 정돈된 정보 텍스트. 전체 경로는 여기에만 있다."""
        r = self.record
        parts = [f"Layer: {r.layer} / Wafer: {r.wafer_id} / die: ({r.col},{r.row})"]
        cv = self._coord_versions()
        if cv is not None:
            (cx, cy), (kx, ky) = cv
            parts.append(f"좌표: Camtek: ({cx},{cy}) / KLA: ({kx},{ky})")
        if r.defect_name:
            parts.append(f"Defect: {r.defect_name}")
        parts.append(f"Path: {r.image_path}")
        return "\n".join(parts)

    def _copy_info(self) -> None:
        QApplication.clipboard().setText(self._info_text())

    # ------------------------------------------------------------ 줌·맞춤
    def _show_actual(self) -> None:
        """1:1. 화면 중앙을 고정점으로 삼아 보고 있던 자리를 잃지 않는다."""
        self._apply_scale(scale=1.0, anchor=self._center_anchor())

    def _show_fit(self) -> None:
        """맞춤 + 원점 복귀(명세). 길을 잃었을 때 돌아오는 자리다."""
        self._apply_scale(fit=True)

    def _zoom(self, factor: float) -> None:
        if self._image.isNull():
            return
        target = max(_MIN_SCALE, min(_MAX_SCALE, self._scale * factor))
        self._apply_scale(scale=target, anchor=self._center_anchor())

    def _zoom_at_cursor(self, factor: float, pos: Optional[QPoint] = None) -> None:
        """커서 아래 지점을 고정한 채 확대/축소(휠 줌). 원본 동작 계승.

        pos 는 무대(viewport) 좌표다. 주지 않으면 현재 커서 자리를 쓴다. 휠 이벤트가 자기
        위치를 들고 오므로 보통은 그 값을 넘긴다(전역 커서보다 정확하고 검증도 된다).
        """
        if self._image.isNull():
            return
        old = self._scale
        new = max(_MIN_SCALE, min(_MAX_SCALE, old * factor))
        if abs(new - old) < 1e-9:
            return
        if pos is None:
            pos = self._scroll.viewport().mapFromGlobal(QCursor.pos())
        self._apply_scale(scale=new, anchor=self._anchor_at(pos))

    def _wheel_pos(self, source, event) -> QPoint:
        """휠 이벤트 좌표를 무대(viewport) 좌표로 옮긴다.

        캔버스는 viewport 의 자식이라 mapFrom 으로는 못 간다. 전역 좌표를 거친다.
        """
        point = event.position().toPoint()
        if source is None or source is self:
            source = self
        return self._scroll.viewport().mapFromGlobal(source.mapToGlobal(point))

    def _center_anchor(self):
        vp = self._scroll.viewport()
        return self._anchor_at(QPoint(vp.width() // 2, vp.height() // 2))

    def _anchor_at(self, pos: QPoint):
        """(뷰포트 좌표, 그 아래 콘텐츠 좌표, 그때의 배율)을 고정점으로 잡는다."""
        hbar = self._scroll.horizontalScrollBar()
        vbar = self._scroll.verticalScrollBar()
        return (pos, hbar.value() + pos.x(), vbar.value() + pos.y(), self._scale)

    def _fit_scale(self) -> float:
        area = self._scroll.viewport().size()
        iw, ih = self._image.width(), self._image.height()
        if iw <= 0 or ih <= 0:
            return 1.0
        return max(min(area.width() / iw, area.height() / ih, 1.0), _MIN_SCALE)

    def _apply_scale(
        self,
        scale: Optional[float] = None,
        fit: bool = False,
        anchor=None,
        animate: bool = True,
    ) -> None:
        """목표 배율로 간다. 250ms OutQuint 로 이동하고 고정점은 매 프레임 유지한다."""
        if self._image.isNull():
            return
        self._stop_zoom()
        if fit:
            self._fit = True
            target = self._fit_scale()
            anchor = None
        else:
            self._fit = False
            target = scale if scale is not None else self._scale

        duration = theme.MOTION["zoom"][0]
        if not animate or duration <= 0 or abs(target - self._scale) < 1e-6:
            self._render(target, anchor)
            if fit:
                self._reset_scroll()
            return

        start = self._scale
        anim = QVariantAnimation(self)
        anim.setDuration(duration)
        anim.setEasingCurve(QEasingCurve.OutQuint)
        anim.setStartValue(float(start))
        anim.setEndValue(float(target))
        anim.valueChanged.connect(lambda v: self._render(float(v), anchor))
        anim.finished.connect(lambda: self._on_zoom_finished(target, anchor, fit))
        self._zoom_anim = anim
        anim.start()

    def _on_zoom_finished(self, target: float, anchor, fit: bool) -> None:
        """마지막 한 장은 부드러운 변환으로 다시 그린다(애니메이션 중에는 빠른 변환)."""
        self._zoom_anim = None
        self._render(target, anchor)
        if fit:
            self._reset_scroll()

    def _stop_zoom(self) -> None:
        """진행 중인 줌을 그 자리에서 멈춘다. 끌기 중에는 전이가 없어야 한다(명세)."""
        if self._zoom_anim is not None:
            self._zoom_anim.stop()
            self._zoom_anim = None

    def _reset_scroll(self) -> None:
        self._scroll.horizontalScrollBar().setValue(0)
        self._scroll.verticalScrollBar().setValue(0)

    def _render(self, scale: float, anchor=None) -> None:
        """한 프레임을 그린다. 애니메이션 중에는 빠른 변환, 끝나면 부드러운 변환.

        원본은 수천 픽셀짜리라 매 프레임 SmoothTransformation 을 쓰면 줌이 끊긴다.
        """
        self._scale = scale
        w = max(1, int(self._image.width() * scale))
        h = max(1, int(self._image.height() * scale))
        moving = self._zoom_anim is not None and self._zoom_anim.state() == QVariantAnimation.Running
        mode = Qt.FastTransformation if moving else Qt.SmoothTransformation
        pix = QPixmap.fromImage(self._image).scaled(w, h, Qt.KeepAspectRatio, mode)
        self._canvas.setPixmap(pix)
        self._canvas.resize(pix.size())
        if anchor is not None:
            pos, cx, cy, base = anchor
            ratio = scale / base if base else 1.0
            self._scroll.horizontalScrollBar().setValue(round(cx * ratio - pos.x()))
            self._scroll.verticalScrollBar().setValue(round(cy * ratio - pos.y()))
        self.lbl_zoom.setText(f"{int(round(scale * 100)):>5d}%")
        # 활성 표시가 바뀔 때만 다시 칠한다. 매 프레임 칠하면 줌 중에 색 계산이 반복된다.
        state = (self._fit, abs(self._scale - 1.0) < 1e-6)
        if state != self._hud_state:
            self._hud_state = state
            self._style_hud()

    # ------------------------------------------------------------ 입력
    def wheelEvent(self, event):  # noqa: N802
        if self._image.isNull():
            return
        delta = event.angleDelta().y()
        if delta != 0:
            self._zoom_at_cursor(1.2 if delta > 0 else 1 / 1.2, self._wheel_pos(self, event))
            event.accept()

    def eventFilter(self, obj, event):  # noqa: N802
        """휠=줌 전용, 캔버스 좌클릭 드래그=잡고 끌기."""
        if event.type() == QEvent.Wheel and not self._image.isNull():
            delta = event.angleDelta().y()
            if delta != 0:
                self._zoom_at_cursor(
                    1.2 if delta > 0 else 1 / 1.2, self._wheel_pos(obj, event)
                )
            return True

        if obj is self._canvas and not self._image.isNull():
            et = event.type()
            if et == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._stop_zoom()   # 끌기 중에는 전이가 없다
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
                # 놓으면 그 자리에서 확정. 되돌리거나 관성을 주지 않는다.
                self._panning = False
                self._pan_start = None
                self._canvas.setCursor(Qt.OpenHandCursor)
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------ 배치
    def _reposition_overlays(self) -> None:
        vp = self._scroll.viewport()
        if self.lbl_die.isVisible():
            self.lbl_die.adjustSize()
            self.lbl_die.move(_HUD_MARGIN, vp.height() - self.lbl_die.height() - _HUD_MARGIN)
            self.lbl_die.raise_()
        self._hud.adjustSize()
        self._hud.move(
            max(0, (vp.width() - self._hud.width()) // 2),
            max(0, vp.height() - self._hud.height() - _HUD_MARGIN),
        )
        self._hud.raise_()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if self._fit_pending:
            self._fit_pending = False
            self._apply_scale(fit=True, animate=False)
        self._reposition_overlays()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if self._fit:
            self._apply_scale(fit=True, animate=False)
        self._reposition_overlays()
