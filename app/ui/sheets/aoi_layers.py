"""AOI 엔지니어 전용 모드 — layer 이름·폴더 지정 시트.

AOI 모드에서는 layer 들이 한 LOT 폴더 아래에 모여 있지 않다(장비별 scanresult 가 흩어져
있다).  그래서 LOT 폴더를 고르는 대신 **layer 이름과 그 layer 의 scanresult 폴더를 한 줄씩**
손으로 지정한다.  공개 계약: ``AoiLayersDialog(settings, parent)`` / ``exec()`` /
``layers() -> list[AoiLayer]``.  마지막 지정은 ``settings.aoi_layers`` 에 남아 다음에
그대로 채워진다.  원본 폴더는 읽기만 한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
)
from qframelesswindow import FramelessDialog
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    TableWidget,
)

from app.scanner import AoiLayer
from app.ui import theme

_COL_NAME, _COL_FOLDER = 0, 1
_SHEET_W, _SHEET_H = 760, 460
_HINT = (
    "layer 이름은 비교 화면·엑셀에 그대로 쓰입니다. 폴더는 그 layer 의 AOI scanresult "
    "폴더(slot 폴더들의 상위, 또는 사진이 든 wafer 폴더 하나)입니다. "
    "layer 간 slot 폴더명이 같아야 같은 wafer 로 매칭됩니다."
)


def validate_layers(layers: list[AoiLayer]) -> Optional[str]:
    """지정 목록의 문제를 한 줄 문구로. 문제 없으면 None (순수 함수 — 단위 테스트용)."""
    if not layers:
        return "layer 를 하나 이상 지정하세요."
    seen: set[str] = set()
    for i, lyr in enumerate(layers, start=1):
        if not lyr.name:
            return f"{i}번째 줄: layer 이름이 비어 있습니다."
        if lyr.name in seen:
            return f"layer 이름 ‘{lyr.name}’ 이 중복됩니다."
        seen.add(lyr.name)
        if not str(lyr.folder) or str(lyr.folder) == ".":
            return f"‘{lyr.name}’: 폴더가 비어 있습니다."
        if not lyr.folder.is_dir():
            return f"‘{lyr.name}’: 폴더를 찾을 수 없습니다 - {lyr.folder}"
    return None


class AoiLayersDialog(FramelessDialog):
    """layer 이름 ↔ scanresult 폴더 표를 편집하는 시트."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setObjectName("aoiLayersSheet")
        self.setWindowTitle("AOI 엔지니어 모드 - layer 지정")
        self._size_key = getattr(settings, "ui_font_size", "normal")
        self._build_ui()
        saved = [AoiLayer.from_dict(d) for d in (getattr(settings, "aoi_layers", None) or [])]
        self.set_layers(saved or [AoiLayer("", Path(""))])

    # ----------------------------------------------------------- UI
    def _height(self, key: str) -> int:
        return theme.fluent_height(key, self._size_key)

    def _build_ui(self) -> None:
        self.resize(_SHEET_W, _SHEET_H)
        self.setMinimumSize(600, 360)
        title_h = self._height("titleBar")
        self.titleBar.setFixedHeight(title_h)
        self.titleBar.minBtn.hide()
        self.titleBar.maxBtn.hide()
        self.titleBar.setDoubleClickEnabled(False)
        self.lbl_title = StrongBodyLabel("AOI 엔지니어 모드 - layer 지정", self.titleBar)
        self.titleBar.hBoxLayout.insertSpacing(0, theme.SPACING["pageH"])
        self.titleBar.hBoxLayout.insertWidget(1, self.lbl_title, 0, Qt.AlignVCenter)

        root = QVBoxLayout(self)
        root.setContentsMargins(
            theme.SPACING["pageH"], title_h + theme.SPACING["gapM"],
            theme.SPACING["pageH"], theme.SPACING["gapM"],
        )
        root.setSpacing(theme.SPACING["gapM"])

        hint = BodyLabel(_HINT, self)
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.table = TableWidget(self)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["layer 이름", "scanresult 폴더"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(_COL_FOLDER, QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        root.addWidget(self.table, 1)

        row_btns = QHBoxLayout()
        row_btns.setSpacing(theme.SPACING["gapS"])
        self.btn_add = PushButton("줄 추가", self)
        self.btn_add.clicked.connect(lambda: self._add_row())
        self.btn_remove = PushButton("줄 삭제", self)
        self.btn_remove.clicked.connect(self._remove_row)
        self.btn_browse = PushButton("폴더 찾기…", self)
        self.btn_browse.setToolTip("선택한 줄의 폴더를 탐색기로 고릅니다(폴더 칸 더블클릭도 됩니다)")
        self.btn_browse.clicked.connect(self._browse_selected)
        for b in (self.btn_add, self.btn_remove, self.btn_browse):
            row_btns.addWidget(b)
        row_btns.addStretch(1)
        root.addLayout(row_btns)

        footer = QHBoxLayout()
        footer.setSpacing(theme.SPACING["gapS"])
        self.lbl_error = CaptionLabel("", self)
        self.lbl_error.setObjectName("aoiError")
        self.lbl_error.setWordWrap(True)
        footer.addWidget(self.lbl_error, 1)
        self.btn_cancel = PushButton("취소", self)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok = PrimaryPushButton("불러오기", self)
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.accept)
        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_ok)
        root.addLayout(footer)

    # ----------------------------------------------------------- 표 편집
    def _add_row(self, name: str = "", folder: str = "") -> int:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, _COL_NAME, QTableWidgetItem(name))
        self.table.setItem(r, _COL_FOLDER, QTableWidgetItem(folder))
        self.table.setCurrentCell(r, _COL_NAME)
        return r

    def _remove_row(self) -> None:
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        if col == _COL_FOLDER:
            self._browse_row(row)

    def _browse_selected(self) -> None:
        r = self.table.currentRow()
        if r < 0:
            r = self._add_row()
        self._browse_row(r)

    def _browse_row(self, row: int) -> None:
        item = self.table.item(row, _COL_FOLDER)
        start = item.text() if item and item.text() else str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "scanresult 폴더 선택", start)
        if folder:
            self.table.setItem(row, _COL_FOLDER, QTableWidgetItem(folder))
            name_item = self.table.item(row, _COL_NAME)
            if name_item is not None and not name_item.text().strip():
                name_item.setText(Path(folder).name)

    # ----------------------------------------------------------- 계약
    def set_layers(self, layers: list[AoiLayer]) -> None:
        self.table.setRowCount(0)
        for lyr in layers:
            self._add_row(lyr.name, "" if str(lyr.folder) == "." else str(lyr.folder))
        if self.table.rowCount():
            self.table.setCurrentCell(0, _COL_NAME)

    def layers(self) -> list[AoiLayer]:
        """표의 줄 → AoiLayer 목록. 이름·폴더가 모두 빈 줄은 건너뛴다."""
        out: list[AoiLayer] = []
        for r in range(self.table.rowCount()):
            name_item = self.table.item(r, _COL_NAME)
            folder_item = self.table.item(r, _COL_FOLDER)
            name = (name_item.text() if name_item else "").strip()
            folder = (folder_item.text() if folder_item else "").strip()
            if not name and not folder:
                continue
            out.append(AoiLayer(name=name, folder=Path(folder)))
        return out

    def accept(self) -> None:  # noqa: D102 - QDialog 계약
        problem = validate_layers(self.layers())
        if problem:
            self.lbl_error.setText(problem)
            return
        self.lbl_error.setText("")
        super().accept()
