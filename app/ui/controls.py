"""판독 화면의 컨트롤 행과 탐색 바.

원본은 좌측 240px 사이드바에 폼 아홉 줄을 세워 두고 판독 내내 시야를 차지했다. 판독 중에 조건은
비켜나 있어야 하므로 한 줄(높이 40)로 접고, 후보가 많은 비교 layer 선택은 필요할 때만 여는
Flyout 으로 옮겼다(03-screens §1, REVIEW-01 A14).

클래스 이름과 공개 API(시그널·메서드·속성)는 유지한다. 배선과 테스트가 이 계약에 기대고 있고,
레이아웃 교체와 계약 변경을 한 커밋에 섞으면 회귀 원인을 분리할 수 없다.

휠로 값이 바뀌지 않는 입력(NoScroll*)은 계승 필수 항목이다.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CheckBox,
    ComboBox,
    DoubleSpinBox,
    Flyout,
    FlyoutAnimationManager,
    FlyoutAnimationType,
    FlyoutViewBase,
    FluentIcon,
    PrimaryPushButton,
    PushButton,
    SmoothScrollArea,
    StrongBodyLabel,
    TransparentPushButton,
    isDarkTheme,
    qconfig,
    setCustomStyleSheet,
)

from app import config
from app.ui import theme

# 표시 이름 뒤에 붙는 재리뷰 깊이. 긴 것부터 봐야 "재재리뷰" 가 "재리뷰" 로 잘리지 않는다.
_DEPTH_SUFFIXES = ("_재재리뷰", "_재리뷰")

# A14 고정값: 컨트롤 행 높이 40, 항목 간 gap 6, 구분선 1px x 20.
_ROW_H = 40


def split_depth(display: str) -> tuple[str, str]:
    """표시 이름을 (canonical, 깊이 라벨) 로 나눈다.

    scanner 는 canonical 이 겹칠 때만 "LYA4_재리뷰" 같은 표시 이름을 만든다. 목록에서는
    canonical 을 이름으로 세우고 깊이는 칩으로 떼어 놓아야 후보 24개가 흩어지지 않는다.
    """
    for suffix in _DEPTH_SUFFIXES:
        if display.endswith(suffix):
            return display[: -len(suffix)], suffix[1:]
    return display, ""


class NoScrollDoubleSpinBox(DoubleSpinBox):
    """마우스 휠로 값이 바뀌지 않는 스핀박스.

    판독대를 스크롤하다 허용오차가 실수로 바뀌는 것을 막는다. 포커스가 있을 때 키보드·직접
    입력은 정상 동작한다. 계승 필수 항목이다.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.StrongFocus)  # 휠이 아니라 클릭/탭으로만 포커스

    def wheelEvent(self, event):  # noqa: N802
        event.ignore()  # 휠은 항상 무시(부모 스크롤로 전달)


class NoScrollComboBox(ComboBox):
    """마우스 휠로 항목이 바뀌지 않는 콤보박스(실수 변경 방지)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event):  # noqa: N802
        event.ignore()


class _LayerCheck(CheckBox):
    """비교 layer 한 줄의 체크박스.

    화면에는 canonical 만 쓰고 깊이는 옆 칩으로 보이지만, `text()` 는 계속 **layer 이름**
    (표시 이름)을 준다. 배선과 테스트가 `cb.text()` 로 layer 를 읽기 때문이다.
    """

    def __init__(self, layer: str, label: str, parent: Optional[QWidget] = None):
        # 텍스트를 생성자로 넘기면 qfluentwidgets 오버로드가 self.__init__(parent) 로 되돌아와
        # 이 서명과 어긋난다. 부모만 넘기고 라벨은 뒤에 세운다.
        super().__init__(parent)
        self._layer = layer
        self.setText(label)

    def text(self) -> str:  # noqa: D102  (계약: 표시 라벨이 아니라 layer 이름)
        return self._layer


class _DepthChip(QLabel):
    """재리뷰 깊이 칩. 순수 Qt 위젯이라 setStyleSheet 를 직접 쓴다."""

    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(18)
        self.setContentsMargins(0, 0, 0, 0)
        self._apply_tokens()
        qconfig.themeChanged.connect(self._apply_tokens)

    def _apply_tokens(self) -> None:
        tok = theme.fluent_tokens(isDarkTheme())
        self.setStyleSheet(
            f"QLabel {{ color: {tok['txt2']}; background: {tok['subtle']};"
            f" border: 1px solid {tok['ctrlBd']}; border-radius: {theme.RADIUS['chip']}px;"
            f" padding: 0 7px; font-size: {theme.fluent_font_px('captionSm')}px; }}"
        )


def _divider(parent: Optional[QWidget] = None) -> QFrame:
    """컨트롤 행의 1px 세로 구분선(A14: 높이 20, 좌우 마진 4)."""
    line = QFrame(parent)
    line.setObjectName("ctrlDivider")
    line.setFixedSize(1, 20)
    line.setContentsMargins(0, 0, 0, 0)

    def paint() -> None:
        tok = theme.fluent_tokens(isDarkTheme())
        line.setStyleSheet(f"QFrame#ctrlDivider {{ background: {tok['divider']}; border: none; }}")

    paint()
    qconfig.themeChanged.connect(paint)
    return line


class CompareLayerView(FlyoutViewBase):
    """비교 layer 선택 Flyout 의 내용.

    canonical 한 줄씩 세우고 재리뷰 깊이는 칩으로 붙인다. 클러스터 길이도 여기 둔다 - 판독
    중에 만지는 값이 아니라 비교 조건을 정할 때 한 번 정하는 값이기 때문이다.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("compareLayerView")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 2, 4, 4)
        outer.setSpacing(theme.SPACING["gapS"])

        head = QHBoxLayout()
        head.setSpacing(theme.SPACING["gapXs"])
        head.addWidget(StrongBodyLabel("비교 layer", self))
        head.addStretch(1)
        self.btn_rereview = TransparentPushButton("재리뷰", self)
        self.btn_rereview.setToolTip(
            "재리뷰 layer 만 선택(같은 layer 에 재재리뷰가 있으면 재재리뷰 우선)"
        )
        self.btn_all = TransparentPushButton("전체", self)
        self.btn_all.setToolTip("선택 가능한 비교 layer 를 모두 선택 (Ctrl+A)")
        self.btn_none = TransparentPushButton("해제", self)
        self.btn_none.setToolTip("비교 layer 선택 모두 해제 (Ctrl+D)")
        for btn in (self.btn_rereview, self.btn_all, self.btn_none):
            btn.setFixedHeight(theme.fluent_height("control"))
            head.addWidget(btn)
        outer.addLayout(head)

        self.scroll = SmoothScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Fluent 위젯이라 setStyleSheet 로 덮으면 스크롤바 스타일까지 같이 날아간다.
        _TRANSPARENT = "SmoothScrollArea { background: transparent; border: none; }"
        setCustomStyleSheet(self.scroll, _TRANSPARENT, _TRANSPARENT)
        self.scroll.viewport().setStyleSheet("background: transparent;")
        self.host = QWidget(self.scroll)
        self.host.setStyleSheet("background: transparent;")
        self.rows = QVBoxLayout(self.host)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(2)
        self.rows.addStretch(1)
        self.scroll.setWidget(self.host)
        # 12행이 한 번에 보이고 그 이상은 스크롤. 폭은 표시 이름이 길어도 잘리지 않게 여유를 준다.
        self.scroll.setFixedSize(272, 12 * 30)
        outer.addWidget(self.scroll)

        outer.addWidget(_divider_h(self))

        cluster = QHBoxLayout()
        cluster.setSpacing(theme.SPACING["gapXs"])
        label = BodyLabel("클러스터 길이", self)
        label.setToolTip(
            "같은 die 안에서 이 거리(좌표 단위) 미만인 defect 을 하나로 묶어"
            " 대표 1장 + ＋n 근접 으로 봅니다."
        )
        cluster.addWidget(label)
        cluster.addStretch(1)
        self.spn_cluster = NoScrollDoubleSpinBox(self)
        self.spn_cluster.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spn_cluster.setSymbolVisible(False)
        self.spn_cluster.setRange(0.0, 100000.0)
        self.spn_cluster.setDecimals(0)  # 자연수만
        self.spn_cluster.setSingleStep(5.0)
        self.spn_cluster.setValue(config.DEFAULT_CLUSTER_RADIUS)
        self.spn_cluster.setFixedSize(96, theme.fluent_height("control"))
        self.spn_cluster.setToolTip(label.toolTip())
        cluster.addWidget(self.spn_cluster)
        outer.addLayout(cluster)

    def clear_rows(self) -> None:
        """layer 행을 모두 비운다(마지막 stretch 는 남긴다)."""
        while self.rows.count() > 1:
            item = self.rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def add_row(self, check: _LayerCheck, depth: str) -> QWidget:
        """canonical 체크박스 한 줄 + 깊이 칩."""
        row = QWidget(self.host)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.SPACING["gapXs"])
        check.setParent(row)
        lay.addWidget(check)
        if depth:
            lay.addWidget(_DepthChip(depth, row))
        lay.addStretch(1)
        self.rows.insertWidget(self.rows.count() - 1, row)
        return row


def _divider_h(parent: Optional[QWidget] = None) -> QFrame:
    """Flyout 안의 1px 가로 구분선."""
    line = QFrame(parent)
    line.setObjectName("flyoutDivider")
    line.setFixedHeight(1)

    def paint() -> None:
        tok = theme.fluent_tokens(isDarkTheme())
        line.setStyleSheet(f"QFrame#flyoutDivider {{ background: {tok['divider']}; border: none; }}")

    paint()
    qconfig.themeChanged.connect(paint)
    return line


class SideBar(QFrame):
    """판독 화면 상단 컨트롤 행.

    이름은 원본 그대로다(배선·테스트 계약). 세로 사이드바가 아니라 높이 40 의 한 줄이며
    좌측은 조건, 우측은 행동이다(A14).
    """

    open_folder = Signal()
    base_layer_changed = Signal(str)
    compare_layers_changed = Signal()
    tolerance_changed = Signal(float)
    cluster_radius_changed = Signal(float)
    export_requested = Signal()
    settings_requested = Signal()
    update_requested = Signal()
    nomatch_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("controlRow")
        self.setFixedHeight(_ROW_H)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._compare_checks: list[_LayerCheck] = []
        self._rereview_set: set = set()  # '재리뷰' 버튼이 선택할 선호 재리뷰 집합
        self._flyout: Optional[Flyout] = None
        self._build()

    def _build(self) -> None:
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACING["gapXs"])
        height = theme.fluent_height("control")

        self.btn_open = PushButton(FluentIcon.FOLDER, "LOT 폴더", self)
        self.btn_open.setFixedHeight(height)
        self.btn_open.setToolTip("리뷰가 진행된 LOT 폴더를 선택 (Ctrl+O)")
        self.btn_open.clicked.connect(self.open_folder)
        row.addWidget(self.btn_open)

        self.lbl_lot = BodyLabel("선택된 LOT 없음", self)
        self.lbl_lot.setObjectName("lotName")
        row.addWidget(self.lbl_lot)

        row.addSpacing(4)
        row.addWidget(_divider(self))
        row.addSpacing(4)

        row.addWidget(CaptionLabel("기준", self))
        self.cmb_base = NoScrollComboBox(self)
        self.cmb_base.setFixedHeight(height)
        self.cmb_base.setMinimumWidth(132)
        self.cmb_base.setPlaceholderText("기준 layer 선택")
        self.cmb_base.setToolTip("이 layer 의 defect 을 기준으로 다른 layer 에서 같은 위치를 찾습니다.")
        self.cmb_base.currentTextChanged.connect(self._on_base_changed)
        row.addWidget(self.cmb_base)

        row.addWidget(CaptionLabel("오차", self))
        self.spn_tol = NoScrollDoubleSpinBox(self)
        self.spn_tol.setObjectName("tol")
        # ↑↓ 버튼 제거(깔끔한 입력). Fluent 는 자체 심볼을 그리므로 둘 다 꺼야 한다.
        self.spn_tol.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spn_tol.setSymbolVisible(False)
        self.spn_tol.setRange(0.0, 100000.0)
        self.spn_tol.setDecimals(0)  # 자연수만 - "300.0" 대신 "300"
        self.spn_tol.setValue(config.DEFAULT_TOLERANCE)
        self.spn_tol.setSingleStep(10.0)
        self.spn_tol.setSuffix(" µm")
        self.spn_tol.setFixedSize(120, height)
        self.spn_tol.setToolTip(
            "기준과 비교 defect 의 die 내 local 좌표 거리(µm) 허용값.\n"
            "작을수록 엄격, 클수록 느슨하게 매칭됩니다."
        )
        self.spn_tol.valueChanged.connect(self.tolerance_changed)
        row.addWidget(self.spn_tol)

        self.compare_view = CompareLayerView(self)
        # Flyout 이 가져가기 전까지는 컨트롤 행 위에 겹쳐 그려진다. 숨겨 둔다.
        self.compare_view.hide()
        self.compare_view.btn_rereview.clicked.connect(self._set_rereview_compares)
        self.compare_view.btn_all.clicked.connect(lambda: self._set_all_compares(True))
        self.compare_view.btn_none.clicked.connect(lambda: self._set_all_compares(False))
        self.compare_view.spn_cluster.valueChanged.connect(self.cluster_radius_changed)
        # 호환 별칭: 배선과 테스트가 사이드바에서 직접 찾는다.
        self.btn_rereview = self.compare_view.btn_rereview
        self.btn_all = self.compare_view.btn_all
        self.btn_none = self.compare_view.btn_none
        self.spn_cluster = self.compare_view.spn_cluster

        self.btn_compare = PushButton("비교 layer", self)
        self.btn_compare.setFixedHeight(height)
        self.btn_compare.clicked.connect(self._open_compare_flyout)
        row.addWidget(self.btn_compare)

        self.lbl_match = CaptionLabel("", self)
        self.lbl_match.setObjectName("dim")
        row.addWidget(self.lbl_match)

        row.addStretch(1)

        self.btn_nomatch = PushButton("미매칭 점프", self)
        self.btn_nomatch.setFixedHeight(height)
        self.btn_nomatch.setToolTip("다음 미매칭 기준 사진으로 점프 (U)")
        self.btn_nomatch.clicked.connect(self.nomatch_requested)
        row.addWidget(self.btn_nomatch)

        self.btn_add_export = PrimaryPushButton("＋ 출력에 담기", self)
        self.btn_add_export.setFixedHeight(height)
        self.btn_add_export.setToolTip(
            "현재 기준 사진을 출력 명세에 담습니다. (A)\n담은 것들은 Excel 출력 시 함께 나옵니다."
        )
        self.btn_add_export.setEnabled(False)
        row.addWidget(self.btn_add_export)

        self._update_available = False
        # 업데이트/설정은 nav 로 옮겼다. 옛 이름을 참조하는 코드가 남아도 죽지 않게 둔다.
        self.btn_update = None
        self.btn_settings = None
        self.btn_export = None
        self._refresh_compare_button()

    # ---- Flyout -------------------------------------------------------
    def _open_compare_flyout(self) -> None:
        """비교 layer Flyout 을 버튼 아래로 연다.

        뷰는 한 번만 만들어 재사용한다. 체크박스 객체가 곧 선택 상태이기 때문에 열 때마다
        새로 만들면 상태가 사라진다.
        """
        if self._flyout is None:
            self._flyout = Flyout(self.compare_view, self.window(), isDeleteOnClose=False)
        flyout = self._flyout
        flyout.show()  # 크기를 먼저 확정해야 위치 계산이 맞는다
        manager = FlyoutAnimationManager.make(FlyoutAnimationType.DROP_DOWN, flyout)
        flyout.exec(manager.position(self.btn_compare), FlyoutAnimationType.DROP_DOWN)

    def _refresh_compare_button(self) -> None:
        """버튼에 현재 선택 수를 적는다. Flyout 을 열지 않고도 몇 개인지 보이게."""
        total = len(self._compare_checks)
        chosen = len(self.compare_layers())
        self.btn_compare.setText(f"비교 layer {chosen}" if total else "비교 layer")
        self.btn_compare.setToolTip(
            f"비교 layer 선택 - 후보 {total}개, 선택 {chosen}개" if total
            else "비교 layer 선택 - LOT 을 열면 후보가 채워집니다"
        )
        self.btn_compare.setEnabled(bool(total))

    # ---- API ----------------------------------------------------------
    def set_lot_name(self, name: str) -> None:
        self.lbl_lot.setText(name)
        self.lbl_lot.setToolTip(f"LOT: {name}")

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

        # 비교 체크박스 재구성: canonical 한 줄 + 깊이 칩
        self.compare_view.clear_rows()
        self._compare_checks.clear()
        for lyr in layers:
            canonical, depth = split_depth(lyr)
            cb = _LayerCheck(lyr, canonical)
            cb.blockSignals(True)
            cb.stateChanged.connect(self._on_compare_toggled)
            self.compare_view.add_row(cb, depth)
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
        self.btn_all.setEnabled(bool(layers))
        self.btn_none.setEnabled(bool(layers))
        self.btn_rereview.setEnabled(bool(self._rereview_set))
        self._refresh_compare_button()

    def set_match_summary(self, text: str) -> None:
        self.lbl_match.setText(text)

    def set_tolerance(self, value: float) -> None:
        self.spn_tol.blockSignals(True)
        self.spn_tol.setValue(value)
        self.spn_tol.blockSignals(False)

    def set_update_available(self, available: bool) -> None:
        """업데이트 가용 여부를 기억한다. 표식은 nav 설정 항목의 배지가 보여 준다(A10)."""
        self._update_available = available

    def update_available(self) -> bool:
        return self._update_available

    def set_update_busy(self, busy: bool) -> None:
        self.btn_open.setEnabled(not busy)

    def _set_all_compares(self, checked: bool) -> None:
        """비교 layer 전체 선택/해제 - 한 번의 신호로 처리."""
        changed = False
        for cb in self._compare_checks:
            if cb.isEnabled() and cb.isChecked() != checked:
                cb.blockSignals(True)
                cb.setChecked(checked)
                cb.blockSignals(False)
                changed = True
        if changed:
            self._refresh_compare_button()
            self.compare_layers_changed.emit()

    def _set_rereview_compares(self) -> None:
        """선호 재리뷰 집합만 체크(같은 layer 재재리뷰 우선). 그 외는 해제 - 한 번의 신호."""
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
            self._refresh_compare_button()
            self.compare_layers_changed.emit()

    def _on_compare_toggled(self, _state: int = 0) -> None:
        self._refresh_compare_button()
        self.compare_layers_changed.emit()

    def _on_base_changed(self, base: str) -> None:
        self._sync_compare_enabled(base)
        self._refresh_compare_button()
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
    """판독대 아래 탐색 바: 이전 / index·전체 / SLOT·die / 힌트 / 다음.

    SLOT·die 는 눌리는 링크다. 히트맵에서 die 로 오갈 때 지금 자리를 잃지 않게 하는
    되돌아가기 지점이다(A12).
    """

    prev_clicked = Signal()
    next_clicked = Signal()
    die_clicked = Signal()

    _HINT = "사진 클릭 = 원본 뷰어 · 휠 = 필름스트립 좌우"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("navBar")
        self.setFixedHeight(44)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 6)
        lay.setSpacing(theme.SPACING["gapXs"])

        size = theme.fluent_height("control")
        self.btn_prev = PushButton("‹", self)
        self.btn_prev.setFixedSize(size, size)
        self.btn_prev.setToolTip("이전 기준 사진 (← / PageUp)")
        self.btn_prev.clicked.connect(self.prev_clicked)
        self.btn_next = PushButton("›", self)
        self.btn_next.setFixedSize(size, size)
        self.btn_next.setToolTip("다음 기준 사진 (→ / PageDown)")
        self.btn_next.clicked.connect(self.next_clicked)

        self.lbl_index = StrongBodyLabel("0 / 0", self)
        self.lbl_index.setMinimumWidth(72)

        self.lbl_die = TransparentPushButton("", self)
        self.lbl_die.setFixedHeight(size)
        self.lbl_die.setToolTip("이 defect 의 wafer 와 die. 눌러 히트맵에서 위치를 봅니다.")
        self.lbl_die.clicked.connect(self.die_clicked)
        self.lbl_die.hide()  # 내용이 있을 때만 보인다

        self.lbl_status = CaptionLabel("", self)
        self.lbl_status.setObjectName("dim")

        self.lbl_hint = CaptionLabel(self._HINT, self)
        self.lbl_hint.setObjectName("dim")

        lay.addWidget(self.btn_prev)
        lay.addWidget(self.btn_next)
        lay.addWidget(self.lbl_index)
        lay.addWidget(_divider(self))
        lay.addWidget(self.lbl_die)
        lay.addWidget(self.lbl_status)
        lay.addStretch(1)
        lay.addWidget(self.lbl_hint)
        self._lay = lay
        self.set_enabled(False)

    def add_widget(self, widget: QWidget) -> None:
        """탐색 바 오른쪽(힌트 앞)에 보조 위젯을 추가한다."""
        self._lay.insertWidget(self._lay.count() - 1, widget)

    def set_index(self, current: int, total: int) -> None:
        self.lbl_index.setText(f"{current} / {total}")

    def set_status(self, text: str) -> None:
        self.lbl_status.setText(text)

    def set_status_tooltip(self, text: str) -> None:
        self.lbl_status.setToolTip(text)

    def set_die(self, text: str) -> None:
        """SLOT·die 표기. 빈 문자열이면 구분선처럼 사라진다."""
        self.lbl_die.setText(text)
        self.lbl_die.setVisible(bool(text))

    def set_enabled(self, enabled: bool) -> None:
        self.btn_prev.setEnabled(enabled)
        self.btn_next.setEnabled(enabled)


# 하위 호환: 옛 이름으로 import 하던 코드 지원
TopBar = SideBar
