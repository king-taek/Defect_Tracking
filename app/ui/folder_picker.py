"""앱 내 커스텀 폴더 선택 다이얼로그.

윈도우 기본(네이티브) 폴더 탐색기 대신, 테마가 적용된 트리 탐색기로 자재 폴더를 고른다.
디렉터리만 보이며, 경로 직접 입력·최근 폴더 바로가기를 지원한다. 원본은 읽기만 한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QDir, Qt
from PySide6.QtGui import QIcon

try:  # Qt6: QFileSystemModel 은 QtGui 로 이동(배포판에 따라 QtWidgets 에도 존재)
    from PySide6.QtGui import QFileSystemModel
except ImportError:  # pragma: no cover
    from PySide6.QtWidgets import QFileSystemModel  # type: ignore

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileIconProvider,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme


class _NoIconProvider(QFileIconProvider):
    """빈 아이콘만 반환 — 항목마다의 셸 아이콘 조회(네트워크 드라이브에서 매우 느림)를 제거."""

    def icon(self, _info) -> QIcon:  # noqa: N802
        return QIcon()


class FolderPickerDialog(QDialog):
    """디렉터리 트리로 폴더를 고르는 다이얼로그(테마 적용)."""

    def __init__(
        self,
        start_path: str = "",
        recent: Optional[list[str]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("자재 폴더 선택")
        self.setMinimumSize(640, 520)
        # 안전망: 다이얼로그에도 어두운 테마를 명시(아이템 뷰 흰 배경 방지).
        self.setStyleSheet(
            f"QDialog {{ background:{theme.BG}; }}"
            f" QTreeView, QComboBox {{ background:{theme.BG_ELEV}; color:{theme.TEXT};"
            f" border:1px solid {theme.NEON_SOFT}; border-radius:8px; }}"
        )
        self._recent = [p for p in (recent or []) if Path(p).exists()]
        self._build()
        if start_path and Path(start_path).exists():
            self._go_to(start_path)

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 12)
        outer.setSpacing(8)

        title = QLabel("자재(LOT) 폴더를 선택하세요")
        title.setObjectName("title")
        outer.addWidget(title)

        # 경로 입력 + 이동
        path_row = QHBoxLayout()
        self.ed_path = QLineEdit()
        self.ed_path.setPlaceholderText("경로를 직접 입력하고 Enter (또는 아래 트리에서 선택)")
        self.ed_path.returnPressed.connect(lambda: self._go_to(self.ed_path.text().strip()))
        path_row.addWidget(self.ed_path, 1)
        btn_go = QPushButton("이동")
        btn_go.clicked.connect(lambda: self._go_to(self.ed_path.text().strip()))
        path_row.addWidget(btn_go)
        outer.addLayout(path_row)

        # 최근 폴더 바로가기(있을 때만)
        if self._recent:
            rec_row = QHBoxLayout()
            rec_row.addWidget(QLabel("최근:"))
            self.cmb_recent = QComboBox()
            self.cmb_recent.addItem("최근 폴더 선택…", "")
            for p in self._recent:
                self.cmb_recent.addItem(p, p)
            self.cmb_recent.activated.connect(self._on_recent)
            rec_row.addWidget(self.cmb_recent, 1)
            outer.addLayout(rec_row)

        # 디렉터리 트리
        self.model = QFileSystemModel(self)
        # 성능: 파일시스템 워처 제거(네트워크 드라이브 렉의 핵심 원인) + 셸 아이콘 조회 제거.
        try:
            self.model.setOption(QFileSystemModel.DontWatchForChanges, True)
        except (AttributeError, TypeError):  # pragma: no cover - 배포판별 enum 차이
            pass
        self.model.setIconProvider(_NoIconProvider())
        self.model.setResolveSymlinks(False)
        self.model.setFilter(QDir.Dirs | QDir.NoDotAndDotDot | QDir.Drives)
        self.model.setRootPath("")
        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setUniformRowHeights(True)  # 렌더 성능
        # 이름 열만 보이게(크기/형식/날짜 숨김)
        for col in range(1, self.model.columnCount()):
            self.tree.hideColumn(col)
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(False)
        self.tree.selectionModel().currentChanged.connect(self._on_tree_selection)
        self.tree.doubleClicked.connect(lambda _idx: self.accept())
        outer.addWidget(self.tree, 1)

        self.lbl_sel = QLabel("")
        self.lbl_sel.setObjectName("dim")
        self.lbl_sel.setStyleSheet("font-size:11px;")
        self.lbl_sel.setWordWrap(True)
        outer.addWidget(self.lbl_sel)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("선택")
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        self._ok_btn = buttons.button(QDialogButtonBox.Ok)
        self._ok_btn.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _on_recent(self, idx: int) -> None:
        path = self.cmb_recent.itemData(idx)
        if path:
            self._go_to(path)

    def _go_to(self, path: str) -> None:
        if not path or not Path(path).exists():
            return
        index = self.model.index(path)
        if not index.isValid():
            return
        self.tree.setCurrentIndex(index)
        self.tree.scrollTo(index)
        self.tree.expand(index)

    def _on_tree_selection(self, current, _previous) -> None:
        # 모델 정보로 판단(네트워크 stat 최소화). filePath 는 캐시된 경로라 저렴하다.
        is_dir = current.isValid() and self.model.isDir(current)
        path = self.model.filePath(current) if is_dir else ""
        self.ed_path.setText(path)
        self.lbl_sel.setText(f"선택: {path}" if path else "")
        self._ok_btn.setEnabled(is_dir)

    def selected_path(self) -> str:
        idx = self.tree.currentIndex()
        if idx.isValid() and self.model.isDir(idx):
            return self.model.filePath(idx)
        text = self.ed_path.text().strip()
        return text if text and Path(text).is_dir() else ""
