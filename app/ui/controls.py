"""상단 컨트롤 바 및 하단 탐색 바 (문서 Section 8.1, 8.3, 8.5).

상단: 폴더 선택 / LOT명 / 기준 Layer / 비교 Layer(체크) / 허용 오차 / 결과 출력하기
하단: 이전 / 현재 index·전체 / 다음
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import config


class TopBar(QFrame):
    """상단 컨트롤 바."""

    open_folder = Signal()
    base_layer_changed = Signal(str)
    compare_layers_changed = Signal()
    tolerance_changed = Signal(float)
    export_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("panel")
        self._compare_checks: list[QCheckBox] = []
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        # 1행: 폴더 / LOT / 출력
        row1 = QHBoxLayout()
        self.btn_open = QPushButton("📁  LOT 폴더 선택")
        self.btn_open.clicked.connect(self.open_folder)
        self.lbl_lot = QLabel("선택된 LOT 없음")
        self.lbl_lot.setObjectName("lotName")
        self.btn_export = QPushButton("결과 출력하기")
        self.btn_export.setObjectName("primary")
        self.btn_export.clicked.connect(self.export_requested)
        self.btn_export.setEnabled(False)

        row1.addWidget(self.btn_open)
        row1.addSpacing(8)
        row1.addWidget(self.lbl_lot, 1)
        row1.addWidget(self.btn_export)
        outer.addLayout(row1)

        # 2행: 기준 layer / 허용 오차 / 비교 layer
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("기준 Layer"))
        self.cmb_base = QComboBox()
        self.cmb_base.setMinimumWidth(140)
        self.cmb_base.currentTextChanged.connect(self._on_base_changed)
        row2.addWidget(self.cmb_base)

        row2.addSpacing(12)
        row2.addWidget(QLabel("허용 오차"))
        self.spn_tol = QDoubleSpinBox()
        self.spn_tol.setRange(0.0, 100000.0)
        self.spn_tol.setDecimals(1)
        self.spn_tol.setValue(config.DEFAULT_TOLERANCE)
        self.spn_tol.setSingleStep(10.0)
        self.spn_tol.setSuffix("  µm")
        self.spn_tol.valueChanged.connect(self.tolerance_changed)
        row2.addWidget(self.spn_tol)

        row2.addSpacing(12)
        row2.addWidget(QLabel("비교 Layer"))
        self._compare_area = QScrollArea()
        self._compare_area.setWidgetResizable(True)
        self._compare_area.setFixedHeight(40)
        self._compare_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._compare_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._compare_host = QWidget()
        self._compare_layout = QHBoxLayout(self._compare_host)
        self._compare_layout.setContentsMargins(4, 2, 4, 2)
        self._compare_layout.setSpacing(10)
        self._compare_layout.addStretch()
        self._compare_area.setWidget(self._compare_host)
        row2.addWidget(self._compare_area, 1)

        outer.addLayout(row2)

    # ---- API ----------------------------------------------------------
    def set_lot_name(self, name: str) -> None:
        self.lbl_lot.setText(f"LOT: {name}")

    def set_layers(self, layers: list[str]) -> None:
        """layer 목록으로 기준 콤보 + 비교 체크박스를 채운다."""
        self.cmb_base.blockSignals(True)
        self.cmb_base.clear()
        self.cmb_base.addItems(layers)
        self.cmb_base.blockSignals(False)

        # 비교 체크박스 재구성
        for cb in self._compare_checks:
            cb.setParent(None)
            cb.deleteLater()
        self._compare_checks.clear()
        for lyr in layers:
            cb = QCheckBox(lyr)
            cb.stateChanged.connect(lambda _=0: self.compare_layers_changed.emit())
            self._compare_layout.insertWidget(
                self._compare_layout.count() - 1, cb
            )
            self._compare_checks.append(cb)

        # 기본값: 첫 layer 기준, 나머지 비교 체크
        if layers:
            self.cmb_base.setCurrentIndex(0)
            self._sync_compare_enabled(layers[0])
            for cb in self._compare_checks:
                cb.setChecked(cb.text() != layers[0])
        self.btn_export.setEnabled(bool(layers))

    def _on_base_changed(self, base: str) -> None:
        self._sync_compare_enabled(base)
        self.base_layer_changed.emit(base)

    def _sync_compare_enabled(self, base: str) -> None:
        """기준으로 선택된 layer 는 비교에서 비활성/해제한다."""
        for cb in self._compare_checks:
            if cb.text() == base:
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.setEnabled(False)
                cb.blockSignals(False)
            else:
                cb.setEnabled(True)

    def base_layer(self) -> str:
        return self.cmb_base.currentText()

    def compare_layers(self) -> list[str]:
        return [cb.text() for cb in self._compare_checks if cb.isChecked()]

    def tolerance(self) -> float:
        return self.spn_tol.value()


class NavBar(QFrame):
    """하단 탐색 바: 이전 / index·전체 / 다음 (문서 Section 8.5)."""

    prev_clicked = Signal()
    next_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("panel")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)

        self.btn_prev = QPushButton("◀  이전")
        self.btn_prev.clicked.connect(self.prev_clicked)
        self.btn_next = QPushButton("다음  ▶")
        self.btn_next.clicked.connect(self.next_clicked)

        self.lbl_index = QLabel("0 / 0")
        self.lbl_index.setAlignment(Qt.AlignCenter)
        self.lbl_index.setStyleSheet("font-size:13px; font-weight:600;")

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("dim")

        lay.addWidget(self.btn_prev)
        lay.addStretch()
        lay.addWidget(self.lbl_index)
        lay.addStretch()
        lay.addWidget(self.lbl_status)
        lay.addStretch()
        lay.addWidget(self.btn_next)
        self.set_enabled(False)

    def set_index(self, current: int, total: int) -> None:
        self.lbl_index.setText(f"{current} / {total}")

    def set_status(self, text: str) -> None:
        self.lbl_status.setText(text)

    def set_status_tooltip(self, text: str) -> None:
        self.lbl_status.setToolTip(text)

    def set_enabled(self, enabled: bool) -> None:
        self.btn_prev.setEnabled(enabled)
        self.btn_next.setEnabled(enabled)
