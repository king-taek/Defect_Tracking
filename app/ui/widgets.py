"""재사용 위젯 및 애니메이션 헬퍼 (문서 Section 8.6, 9).

- FadeImageLabel: 이미지 교체 시 부드러운 fade(기준) / 빠른 fade(비교) 전환.
- ClickableThumb: 클릭 가능한 썸네일(현재 선택 강조).
- 모든 움직임은 부드럽게(QPropertyAnimation 이징).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEasingCurve, QVariantAnimation, Qt, Signal
from PySide6.QtGui import QFont, QPainter, QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import isDarkTheme, qconfig

from app.ui import theme
from app.ui.image_loader import ImageLoader


def mono_font(px: float, *, bold: bool = False) -> QFont:
    """수치용 등폭 글꼴(02 §2: Δ µm · 개수 · 좌표는 예외 없이 등폭).

    스타일시트의 font-size 는 QFont 에 남지 않아 회귀 테스트가 크기를 못 읽는다. QFont 로 준다.
    """
    f = QFont()
    f.setFamilies(theme.MONO_FAMILIES)
    f.setPixelSize(max(1, int(round(px))))
    f.setWeight(QFont.DemiBold if bold else QFont.Normal)
    return f


class FadeImageLabel(QLabel):
    """이미지를 표시하는 라벨.

    ImageLoader 가 주입되면 이미지를 비동기로 로드하여 UI 멈춤을 막는다(Section 10).
    주입되지 않으면 동기 로드로 폴백한다(테스트/단독 사용).

    주의: QScrollArea 안에서 QGraphicsOpacityEffect 를 쓰면 스크롤 시 위젯이
    엉뚱한 위치에 그려지거나 사라지는 Qt 렌더 버그가 있어, 그리드 이미지는
    그래픽 이펙트 fade 를 쓰지 않고 즉시 교체한다.
    """

    def __init__(self, parent: Optional[QWidget] = None, duration: int = 220):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(120, 120)
        self.setScaledContents(False)
        self._source_pixmap: Optional[QPixmap] = None
        self._placeholder = "이미지 없음"
        self._loader: Optional[ImageLoader] = None
        self._pending_id = -1
        self._pending_animated = True
        self._duration = max(0, int(duration))
        self._prev_pixmap: Optional[QPixmap] = None
        self._fade: Optional[QVariantAnimation] = None

    def set_loader(self, loader: ImageLoader) -> None:
        self._loader = loader
        loader.loaded.connect(self._on_loaded)

    def set_duration(self, ms: int) -> None:
        """전환 길이(ms). 0 이면 즉시 교체."""
        self._duration = max(0, int(ms))

    def _scaled(self) -> Optional[QPixmap]:
        if self._source_pixmap is None or self._source_pixmap.isNull():
            return None
        return self._source_pixmap.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

    def resizeEvent(self, event):  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        sc = self._scaled()
        if sc is not None:
            super().setPixmap(sc)

    def show_path(self, path: Optional[str | Path], animated: bool = True) -> None:
        """이미지 경로를 표시. None 이면 placeholder."""
        if path is None:
            self._pending_id = -1
            self._apply(None, animated)
            return
        self._pending_animated = animated
        if self._loader is not None:
            # 비동기 로드: 결과 도착 시 _on_loaded 에서 적용
            self._pending_id = self._loader.request(str(path))
        else:
            p = QPixmap(str(path))
            self._apply(p if not p.isNull() else None, animated)

    def _on_loaded(self, request_id: int, image: object) -> None:
        if request_id != self._pending_id:
            return  # 빠른 탐색으로 인한 지난 요청 결과는 무시
        animated = self._pending_animated
        if isinstance(image, QImage) and not image.isNull():
            self._apply(QPixmap.fromImage(image), animated)
        else:
            self._apply(None, animated)

    def show_message(self, text: str) -> None:
        self._source_pixmap = None
        super().clear()
        self.setText(text)

    def _apply(self, pixmap: Optional[QPixmap], animated: bool) -> None:
        previous = self._scaled()
        self._source_pixmap = pixmap
        if pixmap is None:
            self.show_message(self._placeholder)
            return
        self.setText("")
        target = self._scaled()
        if target is None:
            return
        if not animated or self._duration <= 0 or previous is None or previous.isNull():
            self._stop_fade()
            super().setPixmap(target)
            return
        self._start_fade(previous, target)

    # ---- 크로스페이드 -------------------------------------------------
    # QGraphicsOpacityEffect 를 쓰면 QScrollArea 안에서 위젯이 엉뚱한 자리에 그려지거나
    # 사라진다(위 클래스 주석 참고). 그래서 두 픽스맵을 알파 합성해 직접 섞는다.
    def _start_fade(self, old: QPixmap, new: QPixmap) -> None:
        self._stop_fade()
        self._prev_pixmap = old
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(self._duration)
        anim.setEasingCurve(QEasingCurve.OutQuint)
        anim.valueChanged.connect(self._on_fade_step)
        anim.finished.connect(self._on_fade_done)
        self._fade = anim
        anim.start()

    def _on_fade_step(self, value: object) -> None:
        target = self._scaled()
        if target is None:
            return
        super().setPixmap(_blend(self._prev_pixmap, target, float(value)))

    def _on_fade_done(self) -> None:
        target = self._scaled()
        if target is not None:
            super().setPixmap(target)
        self._prev_pixmap = None
        self._fade = None

    def _stop_fade(self) -> None:
        if self._fade is not None:
            self._fade.stop()
            self._fade = None
        self._prev_pixmap = None


class PageHeader(QFrame):
    """페이지 머리 행(44px). 제목 15/600 과 그 화면의 조건·행동을 한 줄에 놓고 아래 1px 선을 긋는다.

    시안(docs/adr/0001)은 26px 제목 + 부제 두 줄 대신 이 한 줄을 쓴다. 지도·목록이 그만큼
    높이를 더 가져간다. 좌우 여백 20 은 행이 스스로 갖는다(경계선이 페이지 끝까지 닿도록).
    """

    HEIGHT = theme.HEADER_ROW_PX
    PAD_X = 20

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("pageHeader")
        self.setFixedHeight(self.HEIGHT)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(self.PAD_X, 0, self.PAD_X, 0)
        self._lay.setSpacing(theme.SPACING["gapS"])
        self.title = QLabel(title, self)
        self.title.setObjectName("pageTitle")
        self._lay.addWidget(self.title, 0)
        self._apply_tokens()
        qconfig.themeChanged.connect(self._apply_tokens)

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        self._lay.addWidget(widget, stretch)

    def add_stretch(self) -> None:
        self._lay.addStretch(1)

    def add_spacing(self, px: int) -> None:
        self._lay.addSpacing(px)

    def add_divider(self) -> None:
        """1px x 20 세로 구분선."""
        line = QFrame(self)
        line.setObjectName("headerDivider")
        line.setFixedSize(1, 20)
        self._lay.addWidget(line, 0)

    def _apply_tokens(self, *_args) -> None:
        t = theme.fluent_tokens(isDarkTheme())
        layer = t["layer"]
        divider = theme.flatten(t["divider"], layer)
        self.setStyleSheet(
            f"QFrame#pageHeader {{ background: transparent; border-bottom: 1px solid {divider}; }}"
            f"QFrame#headerDivider {{ background: {theme.flatten(t['popBorder'], layer)};"
            " border: none; }"
        )
        self.title.setStyleSheet(
            f"color: {theme.flatten(t['txt1'], layer)}; font-size: 15px; font-weight: 600;"
            " background: transparent;"
        )


class ClickableThumb(QFrame):
    """필름스트립 카드 한 장. 클릭하면 그 사진이 기준이 된다.

    사진은 경로만 받아 두고 화면에 들어올 때 읽는다(`ensure_loaded`). LOT 하나에 기준
    사진이 599장까지 오는데 전부 QPixmap 으로 들고 있으면 스크롤 전에 메모리부터 무너진다.
    """

    clicked = Signal(int)

    # 시안: 카드 96x80, 사진 86x50, 캡션 등폭 11px.
    CARD_W = 96
    CARD_H = 80
    IMG_W = 86
    IMG_H = 50

    def __init__(self, index: int, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.index = index
        self._selected = False
        self._source: Optional[str] = None
        self._loaded = False
        self.setObjectName("thumb")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.CARD_W, self.CARD_H)
        self._build()
        self._refresh_style()
        qconfig.themeChanged.connect(self._refresh_style)

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(3)
        self.img = QLabel(self)
        self.img.setAlignment(Qt.AlignCenter)
        self.img.setFixedSize(self.IMG_W, self.IMG_H)
        self.img.setStyleSheet(
            f"background: {theme.PHOTO_BG}; border-radius: 3px; color: #FFFFFF;"
        )
        # 매칭 상태 점(미매칭만 표시) - 트리아지 표식
        self.dot = QLabel(self.img)
        self.dot.setFixedSize(8, 8)
        self.dot.move(self.IMG_W - 12, 4)
        self.dot.hide()
        # 좌상단 "담김": 이 사진이 출력 명세에 들어 있다는 표식
        self.tray_mark = QLabel("담김", self.img)
        self.tray_mark.setFixedHeight(14)
        self.tray_mark.move(4, 3)
        self.tray_mark.hide()
        self.caption = QLabel("", self)
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setFont(mono_font(11))
        lay.addWidget(self.img)
        lay.addWidget(self.caption)

    def set_in_tray(self, in_tray: bool) -> None:
        """출력 명세에 담긴 사진이면 좌상단에 '담김' 표식을 보인다."""
        self.tray_mark.setVisible(bool(in_tray))

    # ---- 사진 --------------------------------------------------------
    def set_source(self, path: Optional[str | Path]) -> None:
        """사진 경로만 기억한다. 실제 읽기는 화면에 들어올 때."""
        self._source = str(path) if path is not None else None
        self._loaded = False

    def ensure_loaded(self) -> bool:
        """아직 안 읽었으면 지금 읽는다. 읽었으면 아무 일도 하지 않는다."""
        if self._loaded or self._source is None:
            return False
        self._loaded = True
        self.set_image(self._source)
        return True

    def is_loaded(self) -> bool:
        return self._loaded

    def set_image(self, path: Optional[str | Path]) -> None:
        if path is not None:
            p = QPixmap(str(path))
            if not p.isNull():
                self.img.setPixmap(
                    p.scaled(self.IMG_W, self.IMG_H, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                self._loaded = True
                return
        self.img.setText("?")

    def set_caption(self, text: str) -> None:
        self.caption.setText(text)

    def set_status(self, status: str) -> None:
        """매칭 상태 점 표시: 'none'(사유 있는 점) / 그 외(점 없음)."""
        if status != "none":
            self.dot.hide()
            return
        t = theme.fluent_tokens(isDarkTheme())
        self.dot.setStyleSheet(
            f"background: {t['danger']}; border: 1px solid {theme.PHOTO_BG}; border-radius: 4px;"
        )
        self.dot.show()

    def set_tooltip(self, text: str) -> None:
        # 자식 위젯은 부모 tooltip 을 상속하지 않으므로 모두 지정한다.
        self.setToolTip(text)
        self.img.setToolTip(text)
        self.caption.setToolTip(text)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._refresh_style()

    def _refresh_style(self) -> None:
        t = theme.fluent_tokens(isDarkTheme())
        radius = 6
        if self._selected:
            border = t["accentFill"]
            background = theme.flatten(t["thumbSel"], t["layer"])
        else:
            border = theme.flatten(t["cardBorder"], t["card"])
            background = t["card"]
        hover = theme.flatten(t["cardBorderH"], t["card"])
        self.setStyleSheet(
            f"QFrame#thumb {{ background: {background}; border: 1px solid {border};"
            f" border-radius: {radius}px; }}"
            f"QFrame#thumb:hover {{ border-color: {hover}; background: {t['cardHover']}; }}"
        )
        self.caption.setStyleSheet(
            f"color: {theme.flatten(t['txt2'], t['card'])}; background: transparent;"
        )
        self.tray_mark.setStyleSheet(
            f"color: {t['onAccent']}; background: {t['accentFill']}; border-radius: 3px;"
            " padding: 0 4px; font-size: 10px;"
        )

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(event)


def _blend(old: Optional[QPixmap], new: QPixmap, t: float) -> QPixmap:
    """old 에서 new 로 t(0~1) 만큼 섞은 픽스맵을 만든다."""
    out = QPixmap(new.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    if old is not None and not old.isNull():
        p.setOpacity(1.0 - t)
        x = (new.width() - old.width()) // 2
        y = (new.height() - old.height()) // 2
        p.drawPixmap(x, y, old)
    p.setOpacity(t)
    p.drawPixmap(0, 0, new)
    p.end()
    return out
