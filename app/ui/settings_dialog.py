"""설정 다이얼로그 - 설정 페이지를 창에 띄우는 얇은 껍데기.

내용은 `app/ui/pages/settings.py` 가 갖는다. nav 라우트로 옮긴 뒤에도 기존 호출부
(`MainWindow._open_settings`)가 그대로 동작해야 해서 이 껍데기를 남긴다. 라우팅이 붙으면
호출부는 페이지로 옮겨 가고 이 파일은 단계 9에서 지운다.

페이지는 카드마다 즉시 반영이라 취소가 의미를 잃는다. 그래서 버튼은 '닫기' 하나이고,
닫기 전에 저장 가능한 값인지(작업공간이 비었는지 · LOT 내부인지) 한 번 더 판정한다.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget
from qfluentwidgets import PrimaryPushButton

from app.config import AppSettings
from app.ui import theme
from app.ui.pages.settings import SettingsPage, ask_update, show_update_notice

__all__ = ["SettingsDialog", "SettingsPage", "ask_update", "show_update_notice"]


class _SwitchAlias:
    """개발자 모드 토글의 옛 이름(`btn_dev`) 어댑터.

    원본은 켜짐/꺼짐을 글자로 쓰는 QPushButton 이었고 지금은 SwitchButton 이다. SwitchButton
    에서 `text` 는 메서드가 아니라 Property 라 `btn_dev.text()` 가 그대로는 깨진다. 호출부를
    한꺼번에 바꾸면 회귀 원인을 분리할 수 없어 읽는 방법만 맞춰 준다.
    """

    def __init__(self, switch) -> None:
        self._switch = switch

    def text(self) -> str:
        return self._switch.text

    def isChecked(self) -> bool:  # noqa: N802 - Qt 관례 이름
        return self._switch.isChecked()

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt 관례 이름
        self._switch.setChecked(checked)

    def isEnabled(self) -> bool:  # noqa: N802 - Qt 관례 이름
        return self._switch.isEnabled()


class SettingsDialog(QDialog):
    """설정 페이지를 담은 창."""

    update_requested = Signal()  # "지금 업데이트/업데이트 확인" 클릭 시

    def __init__(
        self,
        settings: AppSettings,
        current_lot: Optional[str] = None,
        parent: Optional[QWidget] = None,
        update_available: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle("설정")
        self.setMinimumSize(760, 640)
        self._settings = settings

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.page = SettingsPage(
            settings, current_lot, self, update_available=update_available
        )
        outer.addWidget(self.page, 1)
        self.page.update_requested.connect(self._on_page_update_requested)

        footer = QWidget(self)
        footer_lay = QVBoxLayout(footer)
        footer_lay.setContentsMargins(
            theme.SPACING["pageH"], 0, theme.SPACING["pageH"], theme.SPACING["gapM"]
        )
        size_key = getattr(settings, "ui_font_size", "normal")
        self.btn_close = PrimaryPushButton("닫기", footer)
        self.btn_close.setMinimumHeight(theme.fluent_height("primary", size_key))
        self.btn_close.setDefault(True)
        self.btn_close.clicked.connect(self._on_accept)
        footer_lay.addWidget(self.btn_close, 0, Qt.AlignRight)
        outer.addWidget(footer)

        # 옛 이름 유지(호출부·기존 테스트 호환). 실제 위젯은 페이지가 갖는다.
        self.ed_workspace = self.page.card_workspace
        self.ed_output = self.page.card_output
        self.ed_device_db = self.page.card_device_db
        self.cmb_product = self.page.card_product.comboBox
        self.cmb_font = self.page.card_font.segment
        self.chk_update = self.page.card_update
        self.btn_update = self.page.btn_update
        self.btn_dev = _SwitchAlias(self.page.sw_dev)
        self._dev_box = self.page._dev_box
        self.btn_help = self.page.btn_help

    # ------------------------------------------------------------ 계약
    def updated_settings(self) -> AppSettings:
        """화면 값을 반영한 설정(저장은 호출 측)."""
        return self.page.updated_settings()

    def wants_update(self) -> bool:
        return self.page.wants_update()

    def _on_page_update_requested(self) -> None:
        """업데이트 요청은 창의 비동기 흐름이 처리하므로 값만 넘기고 닫는다."""
        self.updated_settings()
        self.update_requested.emit()
        self.accept()

    def _on_update_clicked(self) -> None:
        self.page._on_update_clicked()

    def _on_accept(self) -> None:
        message = self.page.validate()
        if message:
            self.page._error(message)
            return
        self.updated_settings()
        self.accept()

    def _error(self, message: str) -> None:
        self.page._error(message)
