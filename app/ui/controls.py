"""좌측 사이드바 컨트롤 및 하단 탐색 바 (문서 Section 8.1, 8.3, 8.5).

사이드바(세로): 자재 폴더 선택 / 자재명 / 기준 Layer / 허용 오차 / DEFECT 클러스터 길이 /
비교 Layer(체크, 세로 스크롤) / 설정·업데이트·결과 출력하기
탐색 바: 이전 / 현재 index·전체 / 다음

비교 Layer 선택부는 세로 스크롤 영역에 한 줄에 하나씩 쌓는다.
layer 목록 설정 시 시그널을 차단해 재계산 폭주를 막는다.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
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
from app.ui import theme


class NoScrollDoubleSpinBox(QDoubleSpinBox):
    """마우스 휠로 값이 바뀌지 않는 스핀박스.

    사이드바를 세로 스크롤하다 허용오차가 실수로 바뀌는 것을 막는다. 포커스가 있을 때
    키보드/직접 입력은 정상 동작한다.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.StrongFocus)  # 휠이 아니라 클릭/탭으로만 포커스

    def wheelEvent(self, event):  # noqa: N802
        event.ignore()  # 휠은 항상 무시(부모 스크롤로 전달)


class NoScrollComboBox(QComboBox):
    """마우스 휠로 항목이 바뀌지 않는 콤보박스(실수 변경 방지)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event):  # noqa: N802
        event.ignore()


class SideBar(QFrame):
    """좌측 세로 컨트롤 사이드바.

    상단 컨트롤 바를 대체하지만 공개 API(시그널/메서드/속성)는 동일하게 유지한다.
    """

    open_folder = Signal()
    base_layer_changed = Signal(str)
    compare_layers_changed = Signal()
    tolerance_changed = Signal(float)
    cluster_radius_changed = Signal(float)
    export_requested = Signal()
    settings_requested = Signal()
    update_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setMinimumWidth(200)
        self.setMaximumWidth(360)
        self._compare_checks: list[QCheckBox] = []
        self._rereview_set: set = set()  # '재리뷰' 버튼이 선택할 선호 재리뷰 집합
        self._build()

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("section")
        return lbl

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 10)
        outer.setSpacing(8)

        # ── 헤더: 자재 폴더 선택 + 자재명
        self.btn_open = QPushButton("📁  자재 폴더 선택")
        self.btn_open.setToolTip("리뷰가 진행된 자재(LOT) 폴더를 선택 (Ctrl+O)")
        self.btn_open.clicked.connect(self.open_folder)
        self.lbl_lot = QLabel("선택된 자재 없음")
        self.lbl_lot.setObjectName("lotName")
        self.lbl_lot.setWordWrap(True)
        outer.addWidget(self.btn_open)
        outer.addWidget(self.lbl_lot)

        # ── 기준 Layer
        outer.addWidget(self._section_label("기준 LAYER"))
        self.cmb_base = NoScrollComboBox()
        self.cmb_base.setMinimumWidth(150)
        self.cmb_base.currentTextChanged.connect(self._on_base_changed)
        outer.addWidget(self.cmb_base)

        # ── 허용 오차
        outer.addWidget(self._section_label("허용 오차"))
        self.spn_tol = NoScrollDoubleSpinBox()
        self.spn_tol.setObjectName("tol")
        self.spn_tol.setButtonSymbols(QAbstractSpinBox.NoButtons)  # ↑↓ 버튼 제거(깔끔한 입력)
        self.spn_tol.setRange(0.0, 100000.0)
        self.spn_tol.setDecimals(1)
        self.spn_tol.setValue(config.DEFAULT_TOLERANCE)
        self.spn_tol.setSingleStep(10.0)
        self.spn_tol.setSuffix(" µm")
        self.spn_tol.setToolTip(
            "기준과 비교 defect 의 die 내 local 좌표 거리(µm) 허용값.\n"
            "작을수록 엄격, 클수록 느슨하게 매칭됩니다."
        )
        self.spn_tol.valueChanged.connect(self.tolerance_changed)
        outer.addWidget(self.spn_tol)

        # ── DEFECT 클러스터 길이 (허용 오차 바로 아래)
        outer.addWidget(self._section_label("DEFECT 클러스터 길이"))
        self.spn_cluster = NoScrollDoubleSpinBox()
        self.spn_cluster.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spn_cluster.setRange(0.0, 100000.0)
        self.spn_cluster.setDecimals(1)
        self.spn_cluster.setSingleStep(5.0)
        self.spn_cluster.setValue(config.DEFAULT_CLUSTER_RADIUS)
        self.spn_cluster.setToolTip(
            "같은 die 안에서 이 거리(좌표 단위) 미만인 defect 을 하나로 묶어"
            " 대표 1장+'+n' 으로 봅니다."
        )
        self.spn_cluster.valueChanged.connect(self.cluster_radius_changed)
        outer.addWidget(self.spn_cluster)

        # 실시간 매칭 요약(허용오차 튜닝 피드백)
        self.lbl_match = QLabel("")
        self.lbl_match.setObjectName("dim")
        self.lbl_match.setWordWrap(True)
        outer.addWidget(self.lbl_match)

        # ── 비교 Layer: 라벨 + (아래 줄) 재리뷰/전체/해제 — 좁은 폭에서 라벨이 잘리지 않도록 분리
        outer.addWidget(self._section_label("비교 LAYER"))
        cmp_btns = QHBoxLayout()
        cmp_btns.setSpacing(6)
        self.btn_rereview = QPushButton("재리뷰")
        self.btn_rereview.setObjectName("mini")
        self.btn_rereview.setToolTip(
            "재리뷰 layer 만 선택(같은 layer 에 재재리뷰가 있으면 재재리뷰 우선)"
        )
        self.btn_rereview.clicked.connect(self._set_rereview_compares)
        self.btn_all = QPushButton("전체")
        self.btn_all.setObjectName("mini")
        self.btn_all.setToolTip("선택 가능한 비교 layer 를 모두 선택")
        self.btn_all.clicked.connect(lambda: self._set_all_compares(True))
        self.btn_none = QPushButton("해제")
        self.btn_none.setObjectName("mini")
        self.btn_none.setToolTip("비교 layer 선택 모두 해제")
        self.btn_none.clicked.connect(lambda: self._set_all_compares(False))
        cmp_btns.addWidget(self.btn_rereview)
        cmp_btns.addWidget(self.btn_all)
        cmp_btns.addWidget(self.btn_none)
        outer.addLayout(cmp_btns)

        # 비교 Layer 체크박스 (세로 스크롤 영역에 한 줄씩)
        self._compare_scroll = QScrollArea()
        self._compare_scroll.setWidgetResizable(True)
        self._compare_scroll.setFrameShape(QFrame.NoFrame)
        self._compare_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # viewport 기본 흰색 제거 → 사이드바 패널이 비쳐 글자가 보이게
        self._compare_scroll.setStyleSheet("background: transparent;")
        self._compare_scroll.viewport().setAutoFillBackground(False)
        self._compare_host = QWidget()
        self._compare_host.setAutoFillBackground(False)
        self._compare_host.setStyleSheet("background: transparent;")
        self._compare_box = QVBoxLayout(self._compare_host)
        self._compare_box.setContentsMargins(0, 0, 0, 0)
        self._compare_box.setSpacing(4)
        self._compare_box.addStretch()
        self._compare_scroll.setWidget(self._compare_host)
        outer.addWidget(self._compare_scroll, 1)

        # ── 푸터: 설정(작게) + 결과 출력  — 업데이트는 설정 안으로 이동
        self.btn_settings = QPushButton("⚙ 설정")
        self.btn_settings.setObjectName("mini")
        self.btn_settings.setToolTip("작업공간·출력 폴더·기본값·업데이트")
        self.btn_settings.clicked.connect(self.settings_requested)
        self.btn_settings.setMaximumHeight(30)

        self.btn_export = QPushButton("결과 출력")
        self.btn_export.setObjectName("primary")
        self.btn_export.setToolTip("선택한 기준 사진의 비교 결과를 Excel 로 출력 (Ctrl+E)")
        self.btn_export.clicked.connect(self.export_requested)
        self.btn_export.setEnabled(False)
        self.btn_export.setMaximumHeight(30)

        footer = QHBoxLayout()
        footer.setSpacing(6)
        footer.addWidget(self.btn_settings)
        footer.addWidget(self.btn_export, 1)
        outer.addLayout(footer)

        # 제작 크레딧(항상 보이는 사이드바 하단) — 두 줄로 표기.
        credit = QLabel(config.CREDITS.replace(", ", "\n"))
        credit.setObjectName("dim")
        credit.setWordWrap(True)
        credit.setStyleSheet(f"font-size:{theme.fpx(11)}px;")  # 만든이 문구 +20%(9→11)
        credit.setAlignment(Qt.AlignHCenter)
        outer.addWidget(credit)

        # 업데이트 버튼은 사이드바에서 제거(설정 다이얼로그로 이동). 호환용 더미 참조.
        self.btn_update = None
        self._update_available = False

    # ---- API ----------------------------------------------------------
    def set_lot_name(self, name: str) -> None:
        self.lbl_lot.setText(f"자재: {name}")

    def set_layers(
        self,
        layers: list[str],
        base: Optional[str] = None,
        compares: Optional[list[str]] = None,
        rereview: Optional[set] = None,
    ) -> None:
        """layer 목록으로 기준 콤보 + 비교 체크박스를 채운다.

        기본값 설정 중에는 시그널을 차단하여 재계산이 0회가 되도록 한다(호출 측에서 1회만 재구성).
        base 가 None 이면 기준은 **빈칸**으로 두어 사용자가 직접 고르게 한다(자동 선택 안 함).
        compares 가 None 이면 비교 기본값은 rereview(선호 재리뷰 집합)만 체크한다.
        """
        self._rereview_set = set(rereview) if rereview else set()

        self.cmb_base.blockSignals(True)
        self.cmb_base.clear()
        self.cmb_base.addItems(layers)
        self.cmb_base.setPlaceholderText("기준 layer 선택")

        # 비교 체크박스 재구성 (세로 스택: 끝의 stretch 앞에 삽입)
        for cb in self._compare_checks:
            self._compare_box.removeWidget(cb)
            cb.setParent(None)
            cb.deleteLater()
        self._compare_checks.clear()
        for lyr in layers:
            cb = QCheckBox(lyr)
            cb.blockSignals(True)
            cb.stateChanged.connect(lambda _=0: self.compare_layers_changed.emit())
            self._compare_box.insertWidget(self._compare_box.count() - 1, cb)
            self._compare_checks.append(cb)

        # 기준 선택: base 가 주어지면 적용, 없으면 빈칸(-1)으로 두어 사용자 선택을 유도.
        chosen_base = base if (base and base in layers) else ""
        if chosen_base:
            self.cmb_base.setCurrentText(chosen_base)
        else:
            self.cmb_base.setCurrentIndex(-1)

        # 비교 선택 기본값:
        #  - 저장된 선택(compares)이 있으면 그것(+체크 유지용 기준)을 복원
        #  - 없으면 선호 재리뷰 집합을 체크. 재리뷰 layer 가 전혀 없는 자재는
        #    빈 선택(매칭 불가)이 되어 막다른 화면이 되므로 전체를 기본 체크한다(폴백).
        # 기준 layer 는 비교에서 자동 제외되지만(아래 compare_layers) 체크 상태는 유지한다.
        if compares is not None:
            compare_set = set(compares)
            if chosen_base:
                compare_set.add(chosen_base)
        elif self._rereview_set:
            compare_set = set(self._rereview_set)
        else:
            compare_set = set(layers)
        for cb in self._compare_checks:
            cb.setChecked(cb.text() in compare_set)

        self._sync_compare_enabled(chosen_base)

        # 시그널 복원
        self.cmb_base.blockSignals(False)
        for cb in self._compare_checks:
            cb.blockSignals(False)
        self.btn_export.setEnabled(bool(layers))
        self.btn_all.setEnabled(bool(layers))
        self.btn_none.setEnabled(bool(layers))
        self.btn_rereview.setEnabled(bool(self._rereview_set))

    def set_match_summary(self, text: str) -> None:
        self.lbl_match.setText(text)

    def set_tolerance(self, value: float) -> None:
        self.spn_tol.blockSignals(True)
        self.spn_tol.setValue(value)
        self.spn_tol.blockSignals(False)

    def set_update_available(self, available: bool) -> None:
        """업데이트 가용 시 설정 버튼에 표식(•)을 단다(업데이트는 설정 안에 있음)."""
        self._update_available = available
        self.btn_settings.setText("⚙ 설정 •" if available else "⚙ 설정")
        self.btn_settings.setToolTip(
            "업데이트 있음 — 설정에서 적용" if available
            else "작업공간·출력 폴더·기본값·업데이트"
        )

    def set_update_busy(self, busy: bool) -> None:
        self.btn_settings.setEnabled(not busy)
        self.btn_open.setEnabled(not busy)

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

    def _set_rereview_compares(self) -> None:
        """선호 재리뷰 집합만 체크(같은 layer 재재리뷰 우선). 그 외는 해제 — 한 번의 신호."""
        if not self._rereview_set:
            return
        changed = False
        for cb in self._compare_checks:
            want = cb.text() in self._rereview_set
            if cb.isEnabled() and cb.isChecked() != want:
                cb.blockSignals(True)
                cb.setChecked(want)
                cb.blockSignals(False)
                changed = True
        if changed:
            self.compare_layers_changed.emit()

    def _on_base_changed(self, base: str) -> None:
        self._sync_compare_enabled(base)
        self.base_layer_changed.emit(base)

    def _sync_compare_enabled(self, base: str) -> None:
        """기준 layer 의 체크박스는 비활성(토글 불가)하되 체크 상태는 보존한다.

        실제 비교에서는 compare_layers() 가 기준 layer 를 자동 제외한다. 기준을 바꾸면
        이전 기준 layer 는 다시 활성화되고, 보존된 체크 상태로 비교에 복귀한다.
        """
        for cb in self._compare_checks:
            cb.setEnabled(cb.text() != base)

    def base_layer(self) -> str:
        return self.cmb_base.currentText()

    def compare_layers(self) -> list[str]:
        """체크된 layer 중 기준 layer 를 제외한 목록(기준은 비교 대상에서 자동 제외)."""
        base = self.base_layer()
        return [
            cb.text() for cb in self._compare_checks
            if cb.isChecked() and cb.text() != base
        ]

    def tolerance(self) -> float:
        return self.spn_tol.value()

    def cluster_radius(self) -> float:
        return self.spn_cluster.value()

    def set_cluster_radius(self, value: float) -> None:
        self.spn_cluster.blockSignals(True)
        self.spn_cluster.setValue(value)
        self.spn_cluster.blockSignals(False)


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
        self.lbl_index.setStyleSheet(f"font-size:{theme.fpx(13)}px; font-weight:600;")
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
        self._lay = lay
        self.set_enabled(False)

    def add_widget(self, widget: QWidget) -> None:
        """탐색 바 오른쪽(다음 버튼 앞)에 보조 위젯을 추가한다."""
        self._lay.insertWidget(self._lay.count() - 1, widget)

    def set_index(self, current: int, total: int) -> None:
        self.lbl_index.setText(f"{current} / {total}")

    def set_status(self, text: str) -> None:
        self.lbl_status.setText(text)

    def set_status_tooltip(self, text: str) -> None:
        self.lbl_status.setToolTip(text)

    def set_enabled(self, enabled: bool) -> None:
        self.btn_prev.setEnabled(enabled)
        self.btn_next.setEnabled(enabled)


# 하위 호환: 옛 이름으로 import 하던 코드 지원
TopBar = SideBar
