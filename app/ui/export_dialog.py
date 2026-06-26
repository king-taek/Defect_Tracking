"""결과 출력 대상 선택 다이얼로그 (문서 Section 8.7).

"어떤 기준 사진의 결과를 출력하겠습니까?" — 기준 사진들을 보여주고
사용자가 하나 또는 여러 개를 선택하게 한다.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models import BaseDefectMatches


class ExportSelectDialog(QDialog):
    """출력할 기준 사진들을 다중 선택하는 다이얼로그."""

    def __init__(
        self,
        items: list[BaseDefectMatches],
        current_index: int = -1,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("결과 출력 — 기준 사진 선택")
        self.setMinimumWidth(520)
        self._items = items
        self._build(current_index)

    def _build(self, current_index: int) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        title = QLabel("어떤 기준 사진의 결과를 출력하겠습니까?")
        title.setObjectName("title")
        lay.addWidget(title)
        hint = QLabel("하나 또는 여러 개를 선택할 수 있습니다. (Ctrl/Shift 다중 선택)")
        hint.setObjectName("dim")
        lay.addWidget(hint)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for i, item in enumerate(self._items):
            base = item.base
            n_match = sum(1 for r in item.results if r.is_match)
            text = (
                f"#{i + 1}  wafer {base.wafer_id}  "
                f"die({base.col},{base.row})  pos {base.position_key}  "
                f"— 매칭 {n_match}/{len(item.results)}"
            )
            li = QListWidgetItem(text)
            li.setData(Qt.UserRole, i)
            self.list.addItem(li)
        lay.addWidget(self.list)

        # 선택 보조 버튼
        helper = QHBoxLayout()
        btn_all = QPushButton("전체 선택")
        btn_all.clicked.connect(self.list.selectAll)
        btn_current = QPushButton("현재 사진만")
        btn_current.clicked.connect(lambda: self._select_only(current_index))
        helper.addWidget(btn_all)
        helper.addWidget(btn_current)
        helper.addStretch()
        lay.addLayout(helper)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("Excel 출력")
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        # 기본 선택: 현재 사진
        if 0 <= current_index < self.list.count():
            self._select_only(current_index)
        elif self.list.count():
            self.list.item(0).setSelected(True)

    def _select_only(self, index: int) -> None:
        self.list.clearSelection()
        if 0 <= index < self.list.count():
            self.list.item(index).setSelected(True)
            self.list.setCurrentRow(index)

    def selected_indices(self) -> list[int]:
        return sorted(
            it.data(Qt.UserRole) for it in self.list.selectedItems()
        )
