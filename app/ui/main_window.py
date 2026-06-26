"""메인 윈도우 — 전체 workflow 조립 (문서 Section 8 전체).

폴더 선택 → 스캔 → 기준/비교 layer 선택 → 매칭 → 탐색/비교 → 결과 출력.
모든 원본 접근은 read-only, 결과는 output workspace 에만 저장한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import layout, matcher
from app.config import AppSettings
from app.export.excel_report import export_excel
from app.models import BaseDefectMatches, DefectRecord, ParseStatus
from app.safety import OriginalProtectionError, conflicting_source
from app.scanner import LotIndex
from app.thumbnails import ThumbnailCache
from app.ui.compare_grid import CompareGrid
from app.ui.controls import NavBar, TopBar
from app.ui.export_dialog import ExportSelectDialog
from app.ui.image_loader import ImageLoader
from app.ui.thumbnail_strip import ThumbnailStrip
from app.workers import ScanWorker, ThumbnailWorker


class MainWindow(QMainWindow):
    def __init__(self, settings: Optional[AppSettings] = None):
        super().__init__()
        self.setWindowTitle("Conder Scan Review Image Compare Viewer")
        self.resize(1280, 860)

        self.settings = settings or AppSettings.load()
        self.settings.ensure_workspace()
        self.thumb_cache = ThumbnailCache(self.settings.cache_path)
        self.image_loader = ImageLoader()
        self.pool = QThreadPool.globalInstance()

        self.lot_index: Optional[LotIndex] = None
        self.base_records: list[DefectRecord] = []
        self.matches: list[BaseDefectMatches] = []
        self.current = -1
        self._thumb_worker: Optional[ThumbnailWorker] = None

        self._build_ui()
        self._restore_settings()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        main = QVBoxLayout(root)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(10)

        self.top = TopBar()
        self.top.open_folder.connect(self._choose_folder)
        self.top.base_layer_changed.connect(lambda _: self._recompute())
        self.top.compare_layers_changed.connect(self._recompute)
        self.top.tolerance_changed.connect(lambda _: self._recompute())
        self.top.export_requested.connect(self._export)
        main.addWidget(self.top)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        main.addWidget(self.progress)

        self.strip = ThumbnailStrip()
        self.strip.thumb_clicked.connect(self._goto)
        main.addWidget(self.strip)

        # 비교 그리드 (스크롤 가능)
        grid_scroll = QScrollArea()
        grid_scroll.setWidgetResizable(True)
        grid_host = QFrame()
        grid_host.setObjectName("panel")
        grid_host_layout = QVBoxLayout(grid_host)
        grid_host_layout.setContentsMargins(10, 10, 10, 10)
        self.grid = CompareGrid(loader=self.image_loader)
        grid_host_layout.addWidget(self.grid)
        self._empty_label = QLabel("LOT 폴더를 선택하면 비교 화면이 표시됩니다.")
        self._empty_label.setObjectName("dim")
        self._empty_label.setAlignment(Qt.AlignCenter)
        grid_host_layout.addWidget(self._empty_label)
        grid_scroll.setWidget(grid_host)
        main.addWidget(grid_scroll, 1)

        self.nav = NavBar()
        self.nav.prev_clicked.connect(self._prev)
        self.nav.next_clicked.connect(self._next)
        main.addWidget(self.nav)

        self.setCentralWidget(root)

    def _restore_settings(self) -> None:
        if self.settings.last_lot_folder and Path(self.settings.last_lot_folder).exists():
            self.nav.set_status("이전 LOT 경로를 불러오려면 폴더 선택을 누르세요.")

    # ----------------------------------------------------------- 폴더/스캔
    def _choose_folder(self) -> None:
        start = self.settings.last_lot_folder or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "LOT 폴더 선택", start)
        if folder:
            self.load_lot(folder)

    def load_lot(self, folder: str) -> None:
        # 2차 원본 보호(Section 1.1): 캐시/결과 작업공간이 이 LOT 내부면 차단한다.
        if not self._verify_workspace_outside(folder):
            return

        self.settings.last_lot_folder = folder
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.nav.set_status("스캔 중...")
        self.top.set_lot_name(Path(folder).name)

        worker = ScanWorker(folder)
        worker.signals.progress.connect(self._on_scan_progress)
        worker.signals.finished.connect(self._on_scan_finished)
        worker.signals.error.connect(self._on_scan_error)
        self.pool.start(worker)

    def _verify_workspace_outside(self, folder: str) -> bool:
        """캐시/내보내기 작업공간이 선택한 LOT 폴더 내부면 경고하고 차단한다."""
        for target in (self.settings.cache_path, self.settings.exports_path):
            conflict = conflicting_source(target, [folder])
            if conflict is not None:
                QMessageBox.critical(
                    self,
                    "원본 보호",
                    "프로그램 작업공간(캐시/결과)이 선택한 원본 LOT 폴더 내부에 있습니다.\n"
                    "원본 보호 규칙상 원본 폴더 안에는 어떤 파일도 만들 수 없습니다.\n\n"
                    f"  작업공간 : {target}\n"
                    f"  원본 폴더 : {conflict}\n\n"
                    "작업공간을 원본 밖으로 옮긴 뒤 다시 시도하세요.",
                )
                return False
        return True

    def _on_scan_progress(self, msg: str, cur: int, total: int) -> None:
        self.nav.set_status(msg)

    def _on_scan_error(self, message: str) -> None:
        self.progress.setVisible(False)
        QMessageBox.critical(self, "스캔 오류", f"폴더 스캔 중 오류가 발생했습니다:\n{message}")
        self.nav.set_status("스캔 오류")

    def _on_scan_finished(self, index: LotIndex) -> None:
        self.progress.setVisible(False)
        self.lot_index = index
        layers = index.layer_canonicals()
        if not layers:
            QMessageBox.warning(self, "데이터 없음", "선택한 폴더에서 layer 를 찾지 못했습니다.")
            self.nav.set_status("layer 없음")
            return
        self.top.set_layers(layers)
        self.settings.save()

        ok = sum(1 for r in index.records if r.ok)
        failed = [r for r in index.records if not r.ok]
        status = (
            f"layer {len(layers)}개 · wafer {len(index.wafers())}개 · "
            f"이미지 {len(index.records)}개(좌표 OK {ok}개"
        )
        if failed:
            status += f", 실패 {len(failed)}개"
        status += ")"
        self.nav.set_status(status)
        self.nav.set_status_tooltip(self._failure_summary(failed))
        self._recompute()

    @staticmethod
    def _failure_summary(failed: list[DefectRecord]) -> str:
        """좌표 파싱 실패 항목 요약(상태 표시줄 tooltip)."""
        if not failed:
            return "모든 이미지의 좌표를 정상 추출했습니다."
        by_status: dict[str, int] = {}
        for r in failed:
            by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
        lines = ["좌표 추출 실패 항목:"]
        labels = {
            ParseStatus.NOT_FOUND.value: "좌표/매칭 정보 없음",
            ParseStatus.INFO_FILE_NOT_FOUND.value: "info 파일 없음",
            ParseStatus.INVALID_INFO.value: "info 값 부족/오류",
        }
        for code, n in sorted(by_status.items(), key=lambda kv: -kv[1]):
            lines.append(f"  · {labels.get(code, code)}: {n}개")
        for r in failed[:8]:
            lines.append(f"    - {r.layer}/{r.wafer_id}/{Path(r.image_path).name}")
        if len(failed) > 8:
            lines.append(f"    … 외 {len(failed) - 8}개")
        return "\n".join(lines)

    # -------------------------------------------------------------- 매칭
    def _recompute(self) -> None:
        if self.lot_index is None:
            return
        base_layer = self.top.base_layer()
        compare_layers = self.top.compare_layers()
        tolerance = self.top.tolerance()
        if not base_layer:
            return

        self.base_records = [
            r for r in self.lot_index.records_for_layer(base_layer) if r.ok
        ]
        rbl = self.lot_index.records_by_layer()
        self.matches = matcher.match_all(
            self.base_records, compare_layers, rbl, tolerance
        )

        # 그리드 배치 재구성 (기준 + 비교 layer)
        grid = layout.build_grid([base_layer] + compare_layers)
        self._empty_label.setVisible(not self.base_records)
        self.grid.build_layout(grid, base_layer)

        # 썸네일 스트립
        captions = [
            f"{r.wafer_id}\n({r.col},{r.row})" for r in self.base_records
        ]
        self.strip.set_items(captions)
        self._start_thumbnails()

        self.nav.set_enabled(bool(self.base_records))
        if self.base_records:
            self._goto(0)
        else:
            self.nav.set_index(0, 0)
            self.grid.show_empty("기준 layer 에 좌표 OK 인 사진이 없습니다.")

    def _start_thumbnails(self) -> None:
        if self._thumb_worker is not None:
            self._thumb_worker.cancel()
        items = [(i, r.image_path) for i, r in enumerate(self.base_records)]
        if not items:
            return
        worker = ThumbnailWorker(self.thumb_cache, items)
        worker.signals.ready.connect(self.strip.set_thumbnail)
        self._thumb_worker = worker
        self.pool.start(worker)

    # ------------------------------------------------------------ 탐색
    def _goto(self, index: int) -> None:
        if not self.matches or not (0 <= index < len(self.matches)):
            return
        self.current = index
        item = self.matches[index]
        self.grid.update_for_base(item, self.top.compare_layers())
        self.strip.set_current(index)
        self.nav.set_index(index + 1, len(self.matches))

    def _prev(self) -> None:
        if self.matches:
            self._goto((self.current - 1) % len(self.matches))

    def _next(self) -> None:
        if self.matches:
            self._goto((self.current + 1) % len(self.matches))

    # ------------------------------------------------------------ 출력
    def _export(self) -> None:
        if not self.matches:
            QMessageBox.information(self, "출력", "먼저 LOT 폴더를 불러오세요.")
            return
        dlg = ExportSelectDialog(self.matches, self.current, self)
        if not dlg.exec():
            return
        indices = dlg.selected_indices()
        if not indices:
            QMessageBox.information(self, "출력", "선택된 기준 사진이 없습니다.")
            return

        default_dir = str(self.settings.exports_path)
        Path(default_dir).mkdir(parents=True, exist_ok=True)
        default_name = f"{self.lot_index.lot_name}_compare.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Excel 저장 위치", str(Path(default_dir) / default_name),
            "Excel 파일 (*.xlsx)",
        )
        if not path:
            return

        selected = [self.matches[i] for i in indices]
        try:
            out = export_excel(
                path,
                lot_name=self.lot_index.lot_name,
                base_layer=self.top.base_layer(),
                compare_layers=self.top.compare_layers(),
                tolerance=self.top.tolerance(),
                selected=selected,
                thumb_cache=self.thumb_cache,
                source_roots=[self.lot_index.lot_path],
            )
        except OriginalProtectionError as exc:
            QMessageBox.critical(self, "원본 보호", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "출력 오류", f"Excel 출력 중 오류:\n{exc}")
            return

        if self.settings.output_folder == "":
            self.settings.output_folder = str(Path(out).parent)
            self.settings.save()
        QMessageBox.information(
            self, "출력 완료", f"결과를 저장했습니다:\n{out}"
        )
