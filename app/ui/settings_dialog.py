"""설정 다이얼로그 — 작업공간/출력 폴더/기본 허용오차/업데이트 확인 (사용성).

OK 시 AppSettings 를 갱신·저장한다. 작업공간이 현재 LOT 내부면 경고하고 차단한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import __version__, config
from app.config import AppSettings
from app.safety import conflicting_source


class SettingsDialog(QDialog):
    """설정 편집 다이얼로그."""

    update_requested = Signal()  # "지금 업데이트 확인" 클릭 시

    def __init__(
        self,
        settings: AppSettings,
        current_lot: Optional[str] = None,
        parent: Optional[QWidget] = None,
        update_available: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle("설정")
        self.setMinimumWidth(560)
        self._settings = settings
        self._current_lot = current_lot
        self._update_available = update_available
        self._wants_update = False
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 14)
        outer.setSpacing(12)

        title = QLabel("설정")
        title.setObjectName("title")
        outer.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)

        self.ed_workspace = QLineEdit(self._settings.workspace)
        form.addRow("작업공간 폴더", self._with_browse(self.ed_workspace, self._pick_workspace))

        self.ed_output = QLineEdit(self._settings.output_folder)
        self.ed_output.setPlaceholderText("(비우면 작업공간/exports 사용)")
        form.addRow("출력 폴더", self._with_browse(self.ed_output, self._pick_output))

        self.spn_tol = QDoubleSpinBox()
        self.spn_tol.setRange(0.0, 100000.0)
        self.spn_tol.setDecimals(1)
        self.spn_tol.setSingleStep(10.0)
        self.spn_tol.setSuffix(" µm")
        self.spn_tol.setValue(self._settings.tolerance or config.DEFAULT_TOLERANCE)
        form.addRow("기본 허용 오차", self.spn_tol)

        # 제품 프로파일(좌표 변환 상수). 변경은 다음 스캔부터 적용.
        self.cmb_product = QComboBox()
        for key, prod in config.PRODUCTS.items():
            self.cmb_product.addItem(f"{prod.name} ({key})", key)
        cur = self._settings.product
        idx = self.cmb_product.findData(cur)
        if idx >= 0:
            self.cmb_product.setCurrentIndex(idx)
        self.cmb_product.setToolTip("제품별 좌표 변환 상수 — 변경 후 다시 스캔(F5)하세요")
        form.addRow("제품 프로파일", self.cmb_product)

        self.chk_update = QCheckBox("시작할 때 업데이트 확인")
        self.chk_update.setChecked(self._settings.auto_update_check)
        form.addRow("자동 업데이트", self.chk_update)

        # 수동 업데이트(사이드바에서 이동): 확인/적용 버튼
        upd_host = QWidget()
        upd_lay = QHBoxLayout(upd_host)
        upd_lay.setContentsMargins(0, 0, 0, 0)
        upd_lay.setSpacing(8)
        self.btn_update = QPushButton(
            "지금 업데이트" if self._update_available else "업데이트 확인"
        )
        if self._update_available:
            self.btn_update.setObjectName("primary")
        self.btn_update.setToolTip("최신 버전(메인 브랜치)으로 업데이트")
        self.btn_update.clicked.connect(self._on_update_clicked)
        self.lbl_update = QLabel(
            "새 버전이 있습니다." if self._update_available else ""
        )
        self.lbl_update.setObjectName("dim")
        upd_lay.addWidget(self.btn_update)
        upd_lay.addWidget(self.lbl_update, 1)
        form.addRow("업데이트", upd_host)

        outer.addLayout(form)

        self.lbl_err = QLabel("")
        self.lbl_err.setStyleSheet("color:#f87171;")
        self.lbl_err.setWordWrap(True)
        self.lbl_err.setVisible(False)
        outer.addWidget(self.lbl_err)

        footer = QLabel(f"{config.APP_NAME}  ·  버전 {__version__}")
        footer.setObjectName("dim")
        outer.addWidget(footer)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("저장")
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _with_browse(self, line: QLineEdit, handler) -> QWidget:
        host = QWidget()
        lay = QHBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        btn = QPushButton("찾아보기")
        btn.clicked.connect(handler)
        lay.addWidget(line, 1)
        lay.addWidget(btn)
        return host

    def _pick_workspace(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "작업공간 폴더 선택", self.ed_workspace.text() or str(Path.home())
        )
        if folder:
            self.ed_workspace.setText(folder)

    def _pick_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "출력 폴더 선택", self.ed_output.text() or self.ed_workspace.text()
        )
        if folder:
            self.ed_output.setText(folder)

    def _on_accept(self) -> None:
        workspace = self.ed_workspace.text().strip()
        output = self.ed_output.text().strip()
        if not workspace:
            self._error("작업공간 폴더를 지정하세요.")
            return
        # 원본 보호: 작업공간/출력이 현재 LOT 내부면 차단.
        if self._current_lot:
            for target, label in ((workspace, "작업공간"), (output or workspace, "출력")):
                if conflicting_source(target, [self._current_lot]) is not None:
                    self._error(
                        f"{label} 폴더가 현재 LOT 폴더 내부에 있습니다. 원본 보호를 위해 "
                        "원본 밖의 폴더를 선택하세요."
                    )
                    return
        self.accept()

    def _on_update_clicked(self) -> None:
        """현재 입력값을 먼저 저장 의도로 반영하고 업데이트를 요청하며 닫는다."""
        self._wants_update = True
        self.updated_settings()
        self.update_requested.emit()
        self.accept()

    def wants_update(self) -> bool:
        return self._wants_update

    def _error(self, msg: str) -> None:
        self.lbl_err.setText(msg)
        self.lbl_err.setVisible(True)

    def updated_settings(self) -> AppSettings:
        """다이얼로그 입력을 반영한 설정(저장은 호출 측)."""
        self._settings.workspace = self.ed_workspace.text().strip()
        self._settings.output_folder = self.ed_output.text().strip()
        self._settings.tolerance = self.spn_tol.value()
        self._settings.auto_update_check = self.chk_update.isChecked()
        self._settings.product = self.cmb_product.currentData() or config.DEFAULT_PRODUCT
        return self._settings
