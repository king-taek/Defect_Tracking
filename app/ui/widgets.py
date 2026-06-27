"""재사용 위젯 및 애니메이션 헬퍼 (문서 Section 8.6, 9).

- FadeImageLabel: 이미지 교체 시 부드러운 fade(기준) / 빠른 fade(비교) 전환.
- ClickableThumb: 클릭 가능한 썸네일(현재 선택 강조).
- 모든 움직임은 부드럽게(QPropertyAnimation 이징).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme
from app.ui.image_loader import ImageLoader


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

    def set_loader(self, loader: ImageLoader) -> None:
        self._loader = loader
        loader.loaded.connect(self._on_loaded)

    def set_duration(self, ms: int) -> None:  # 호환용 no-op (fade 제거)
        pass

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
        self._source_pixmap = pixmap
        if pixmap is None:
            self.show_message(self._placeholder)
            return
        self.setText("")
        sc = self._scaled()
        if sc is not None:
            super().setPixmap(sc)


class ClickableThumb(QFrame):
    """클릭 가능한 기준 썸네일 (현재 선택 강조)."""

    clicked = Signal(int)

    def __init__(self, index: int, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.index = index
        self._selected = False
        self.setObjectName("thumb")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(96, 96)
        self._build()
        self._refresh_style()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        self.img = QLabel()
        self.img.setAlignment(Qt.AlignCenter)
        self.img.setFixedSize(84, 62)
        self.img.setStyleSheet(
            f"background:{theme.BG}; border-radius:6px; color:{theme.TEXT_DIM};"
        )
        self.caption = QLabel("")
        self.caption.setObjectName("dim")
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setStyleSheet("font-size: 9px;")
        lay.addWidget(self.img)
        lay.addWidget(self.caption)

    def set_image(self, path: Optional[str | Path]) -> None:
        if path is not None:
            p = QPixmap(str(path))
            if not p.isNull():
                self.img.setPixmap(
                    p.scaled(84, 62, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                return
        self.img.setText("?")

    def set_caption(self, text: str) -> None:
        self.caption.setText(text)

    def set_tooltip(self, text: str) -> None:
        # 자식 위젯은 부모 tooltip 을 상속하지 않으므로 모두 지정한다.
        self.setToolTip(text)
        self.img.setToolTip(text)
        self.caption.setToolTip(text)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._refresh_style()

    def _refresh_style(self) -> None:
        if self._selected:
            self.setStyleSheet(
                f"QFrame#thumb {{ background: {theme.NEON_DIM};"
                f" border: 2px solid {theme.BASE_GLOW}; border-radius: 8px; }}"
            )
        else:
            self.setStyleSheet(
                f"QFrame#thumb {{ background: {theme.BG_ELEV};"
                f" border: 1px solid {theme.NEON_SOFT}; border-radius: 8px; }}"
                f"QFrame#thumb:hover {{ border: 1px solid {theme.NEON}; }}"
            )

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(event)
