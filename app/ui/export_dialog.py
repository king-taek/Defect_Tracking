"""출력 명세를 모달로 여는 임시 다리.

단계 7 에서 화면 자체는 nav 라우트 페이지(`app.ui.pages.export.ExportPage`)로 옮겼다. 이 파일에
남은 것은 라우트 배선이 끝날 때까지 기존 호출부(`MainWindow._export`, Ctrl+E)가 끊기지 않게
같은 페이지를 다이얼로그에 담아 주는 껍데기다. 반환 계약(`selected` / `tagged_selected` /
`wants_export`)은 페이지에 그대로 위임한다.

라우트 배선이 끝나면 이 파일과 `ExportTrayDialog` 를 함께 지운다.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget
from qfluentwidgets import PushButton

from app.models import BaseDefectMatches
from app.thumbnails import ThumbnailCache
from app.ui import theme
from app.ui.pages.export import ALL_LAYERS_TAG, ExportPage

# 기존 호출부·테스트가 이 이름으로 묶음 태그를 확인한다.
_ALL_LAYERS_TAG = ALL_LAYERS_TAG


class ExportTrayDialog(QDialog):
    """출력 명세 페이지를 모달로 감싼 껍데기."""

    def __init__(
        self,
        entries: list[BaseDefectMatches | tuple[BaseDefectMatches, Optional[str]]],
        thumb_cache: Optional[ThumbnailCache] = None,
        all_matched: Optional[list[BaseDefectMatches]] = None,
        all_matched_label: str = "기준 layer 매치 전체",
        all_layers_provider: Optional[
            Callable[[Callable[[int, int], None], Callable[[list], None]], None]
        ] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("출력 명세")
        self.resize(920, 640)

        self.page = ExportPage(
            thumb_cache=thumb_cache,
            all_matched=all_matched,
            all_matched_label=all_matched_label,
            all_layers_provider=all_layers_provider,
            parent=self,
        )
        self.page.set_tray(list(entries or []))
        # 페이지의 주요 액션이 곧 이 다이얼로그의 확정이다. 버튼을 한 벌 더 두면
        # 원본의 3버튼 동급 문제가 그대로 돌아온다.
        self.page.export_requested.connect(self.accept)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.page, 1)

        bar = QVBoxLayout()
        bar.setContentsMargins(
            theme.SPACING["pageH"], 0, theme.SPACING["pageH"], theme.SPACING["pageV"]
        )
        self.btn_close = PushButton("닫기", self)
        self.btn_close.setFixedHeight(theme.fluent_height("control"))
        self.btn_close.setToolTip("명세를 그대로 두고 닫습니다.")
        self.btn_close.clicked.connect(self.accept)
        bar.addWidget(self.btn_close, 0)
        outer.addLayout(bar)

        # 페이지가 소유한 컨트롤을 옛 이름으로도 노출한다(호출부·테스트 계약).
        self.btn_export = self.page.btn_export
        self.btn_add_all = self.page.btn_add_all
        self.btn_add_all_layers = self.page.btn_add_all_layers
        self.btn_clear = self.page.btn_clear

    # ---- 옛 계약: 편집 --------------------------------------------------
    @property
    def _tagged(self) -> list[tuple[BaseDefectMatches, Optional[str]]]:
        return self.page._tagged

    def _remove(self, key: str) -> None:
        self.page._remove(key)

    def _remove_batch(self, tag: str) -> None:
        self.page._remove_batch(tag)

    def _clear_all(self) -> None:
        self.page._clear_all()

    def _add_all_matched(self) -> None:
        self.page._add_all_matched()

    def _add_all_layers(self) -> None:
        self.page._add_all_layers()

    # ---- 옛 계약: 확정 --------------------------------------------------
    def _on_ok(self) -> None:
        """저장만 하고 닫는다. 명세가 라우트로 올라간 뒤에는 닫기와 같은 뜻이다."""
        self.accept()

    def _on_export(self) -> None:
        self.page._on_export_clicked()

    def reject(self) -> None:
        """Esc·창 닫기도 편집을 유지한다.

        트레이는 창이 계속 들고 있는 상태다. 모달을 닫았다고 방금 뺀 행이 되살아나면
        페이지로 옮긴 의미가 사라진다.
        """
        self.accept()

    def selected(self) -> list[BaseDefectMatches]:
        return self.page.selected()

    def tagged_selected(self) -> list[tuple[BaseDefectMatches, Optional[str]]]:
        return self.page.tagged_selected()

    def wants_export(self) -> bool:
        return self.page.wants_export()
