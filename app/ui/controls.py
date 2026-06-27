"""상단 컨트롤 바 및 하단 탐색 바 (문서 Section 8.1, 8.3, 8.5).

상단: 폴더 선택 / LOT명 / 기준 Layer / 허용 오차 / 비교 Layer(체크, 줄바꿈) / 결과 출력하기
하단: 이전 / 현재 index·전체 / 다음

비교 Layer 선택부는 가로 스크롤(가로 휠 필요) 대신 줄바꿈 FlowLayout 을 사용한다.
layer 목록 설정 시 시그널을 차단해 재계산 폭주를 막는다.
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
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.ui.flow_layout import FlowLayout


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

        # 2행: 기준 layer / 허용 오차
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("기준 Layer"))
        self.cmb_base = QComboBox()
        self.cmb_base.setMinimumWidth(150)
        self.cmb_base.currentTextChanged.connect(self._on_base_changed)
        row2.addWidget(self.cmb_base)

        row2.addSpacing(16)
        row2.addWidget(QLabel("허용 오차"))
        self.spn_tol = QDoubleSpinBox()
        self.spn_tol.setRange(0.0, 100000.0)
        self.spn_tol.setDecimals(1)
        self.spn_tol.setValue(config.DEFAULT_TOLERANCE)
        self.spn_tol.setSingleStep(10.0)
        self.spn_tol.setSuffix(" µm")
        self.spn_tol.setToolTip("같은 die 내 local 좌표 거리 허용값 (작을수록 엄격)")
        self.spn_tol.valueChanged.connect(self.tolerance_changed)
        row2.addWidget(self.spn_tol)
        row2.addStretch()
        outer.addLayout(row2)

        # 3행: 비교 Layer 라벨 + 전체/해제
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("비교 Layer"))
        self.btn_all = QPushButton("전체")
        self.btn_all.setToolTip("선택 가능한 비교 layer 를 모두 선택")
        self.btn_all.clicked.connect(lambda: self._set_all_compares(True))
        self.btn_none = QPushButton("해제")
        self.btn_none.setToolTip("비교 layer 선택 모두 해제")
        self.btn_none.clicked.connect(lambda: self._set_all_compares(False))
        for b in (self.btn_all, self.btn_none):
            b.setFixedHeight(24)
        row3.addWidget(self.btn_all)
        row3.addWidget(self.btn_none)
        row3.addStretch()
        outer.addLayout(row3)

        # 비교 Layer 체크박스 (줄바꿈 FlowLayout) — 가로 휠 불필요
        self._compare_host = QWidget()
        sp = self._compare_host.sizePolicy()
        sp.setHeightForWidth(True)
        sp.setVerticalPolicy(QSizePolicy.Minimum)
        self._compare_host.setSizePolicy(sp)
        self._compare_flow = FlowLayout(self._compare_host, margin=0, h_spacing=10, v_spacing=6)
        outer.addWidget(self._compare_host)

    # ---- API ----------------------------------------------------------
    def set_lot_name(self, name: str) -> None:
        self.lbl_lot.setText(f"LOT: {name}")

    def set_layers(
        self,
        layers: list[str],
        base: Optional[str] = None,
        compares: Optional[list[str]] = None,
    ) -> None:
        """layer 목록으로 기준 콤보 + 비교 체크박스를 채운다.

        기본값 설정 중에는 시그널을 차단하여 재계산이 0회가 되도록 한다(호출 측에서 1회만 재구성).
        base/compares 가 주어지면(설정 복원) 그 선택을 best-effort 로 적용한다.
        """
        self.cmb_base.blockSignals(True)
        self.cmb_base.clear()
        self.cmb_base.addItems(layers)

        # 비교 체크박스 재구성
        for cb in self._compare_checks:
            self._compare_flow.removeWidget(cb)
            cb.setParent(None)
            cb.deleteLater()
        self._compare_checks.clear()
        for lyr in layers:
            cb = QCheckBox(lyr)
            cb.blockSignals(True)
            cb.stateChanged.connect(lambda _=0: self.compare_layers_changed.emit())
            self._compare_flow.addWidget(cb)
            self._compare_checks.append(cb)

        # 기준 선택(복원 우선)
        chosen_base = base if (base and base in layers) else (layers[0] if layers else "")
        if chosen_base:
            self.cmb_base.setCurrentText(chosen_base)

        # 비교 선택(복원 우선, 없으면 기준 외 전체)
        compare_set = (
            set(compares) if compares is not None else {l for l in layers if l != chosen_base}
        )
        for cb in self._compare_checks:
            cb.setChecked(cb.text() != chosen_base and cb.text() in compare_set)

        self._sync_compare_enabled(chosen_base)

        # 시그널 복원
        self.cmb_base.blockSignals(False)
        for cb in self._compare_checks:
            cb.blockSignals(False)
        self.btn_export.setEnabled(bool(layers))
        self.btn_all.setEnabled(bool(layers))
        self.btn_none.setEnabled(bool(layers))

    def set_tolerance(self, value: float) -> None:
        self.spn_tol.blockSignals(True)
        self.spn_tol.setValue(value)
        self.spn_tol.blockSignals(False)

    def _set_all_compares(self, checked: bool) -> None:
        """비교 layer 전체 선택/해제 — 한 번의 신호로 처리."""
        changed = False
        for cb in self._compare_checks:
            if cb.isEnabled() and cb.isChecked() != checked:
                cb.blockSignals(True)
                cb.setChecked(checked)
                cb.blockSignals(False)
                changed = True
        if changed:
            self.compare_layers_changed.emit()

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
        self.btn_prev.setToolTip("이전 기준 사진 (← / PageUp)")
        self.btn_prev.clicked.connect(self.prev_clicked)
        self.btn_next = QPushButton("다음  ▶")
        self.btn_next.setToolTip("다음 기준 사진 (→ / PageDown)")
        self.btn_next.clicked.connect(self.next_clicked)

        self.lbl_index = QLabel("0 / 0")
        self.lbl_index.setAlignment(Qt.AlignCenter)
        self.lbl_index.setStyleSheet("font-size:13px; font-weight:600;")
        self.lbl_index.setMinimumWidth(90)

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
