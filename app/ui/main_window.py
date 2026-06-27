"""메인 윈도우 — 전체 workflow 조립 (문서 Section 8 전체).

폴더 선택 → 스캔 → 기준/비교 layer 선택 → 매칭 → 탐색/비교 → 결과 출력.
모든 원본 접근은 read-only, 결과는 output workspace 에만 저장한다.

상태 갱신 원칙(사용성):
  - 기준 layer 변경/새 LOT  → 전체 재구성(_rebuild_all), 인덱스 0.
  - 비교 layer 토글         → 그리드 컬럼만 재구성(_rematch, rebuild_grid=True), 현재 인덱스 유지.
  - 허용 오차 변경          → 재매칭만(_rematch, rebuild_grid=False), 그리드/썸네일 유지, 인덱스 유지.
오류는 비차단 배너로 안내하여 작업 흐름을 끊지 않는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QKeySequence, QShortcut
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

from app import __version__, config, layout, matcher, updater
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
from app.ui.image_viewer import ImageViewerDialog
from app.ui.notifications import NotificationBanner
from app.ui.settings_dialog import SettingsDialog
from app.ui.thumbnail_strip import ThumbnailStrip
from app.workers import ScanWorker, ThumbnailWorker


class MainWindow(QMainWindow):
    def __init__(self, settings: Optional[AppSettings] = None):
        super().__init__()
        self._base_title = f"{config.APP_NAME}  ·  v{__version__}"
        self.setWindowTitle(self._base_title)

        self.settings = settings or AppSettings.load()
        self.settings.ensure_workspace()
        self.thumb_cache = ThumbnailCache(self.settings.cache_path)
        self.image_loader = ImageLoader(max_dim=self._target_image_dim())
        self.pool = QThreadPool.globalInstance()

        self.lot_index: Optional[LotIndex] = None
        self.base_records: list[DefectRecord] = []
        self.matches: list[BaseDefectMatches] = []
        self.current = -1
        self._thumb_worker: Optional[ThumbnailWorker] = None
        self._scan_token = 0  # stale 스캔/썸네일 결과 무시용
        # 실행 중 워커는 풀 스레드에서 도는 동안 GC 되지 않도록 참조를 유지한다.
        self._active_workers: set = set()

        self._update_status: Optional[updater.UpdateStatus] = None
        self._updating = False

        self._restore_geometry()
        self._build_ui()
        self._install_shortcuts()
        self._apply_saved_prefs()
        self._maybe_check_update()

    # ----------------------------------------------------- 화면/DPI 보조
    @staticmethod
    def _target_image_dim() -> int:
        """그리드 이미지 로딩 해상도를 화면 크기·DPR 기준으로 산정(고DPI 선명도)."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return 700
        geo = screen.availableGeometry()
        dpr = screen.devicePixelRatio()
        # 셀은 화면 절반 폭 이하 → 그 정도 해상도면 충분히 선명
        return int(max(560, min(1600, (geo.width() // 2) * dpr)))

    def _restore_geometry(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if self.settings.window_geometry:
            try:
                x, y, w, h = (int(v) for v in self.settings.window_geometry.split(","))
                self.setGeometry(x, y, w, h)
                return
            except (ValueError, TypeError):
                pass
        if screen is not None:
            avail = screen.availableGeometry()
            w = int(avail.width() * 0.80)
            h = int(avail.height() * 0.84)
            self.resize(max(1100, w), max(720, h))
            self.move(avail.center().x() - self.width() // 2,
                      avail.center().y() - self.height() // 2)
        else:
            self.resize(1280, 860)
        self.setMinimumSize(1024, 680)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        main = QVBoxLayout(root)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(10)

        self.banner = NotificationBanner()
        main.addWidget(self.banner)

        self.top = TopBar()
        self.top.open_folder.connect(self._choose_folder)
        self.top.base_layer_changed.connect(lambda _: self._rebuild_all())
        self.top.compare_layers_changed.connect(lambda: self._rematch(rebuild_grid=True))
        self.top.tolerance_changed.connect(lambda _: self._rematch(rebuild_grid=False))
        self.top.export_requested.connect(self._export)
        self.top.settings_requested.connect(self._open_settings)
        self.top.update_requested.connect(self._manual_update)
        main.addWidget(self.top)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        main.addWidget(self.progress)

        self.strip = ThumbnailStrip()
        self.strip.thumb_clicked.connect(self._goto)
        main.addWidget(self.strip)

        # 비교 그리드 (스크롤 가능)
        grid_scroll = QScrollArea()
        grid_scroll.setWidgetResizable(True)
        grid_scroll.setFrameShape(QFrame.NoFrame)
        grid_host = QFrame()
        grid_host.setObjectName("panel")
        grid_host_layout = QVBoxLayout(grid_host)
        grid_host_layout.setContentsMargins(10, 10, 10, 10)
        self.grid = CompareGrid(loader=self.image_loader)
        self.grid.image_clicked.connect(self._open_viewer)
        grid_host_layout.addWidget(self.grid)
        self._empty_label = QLabel("LOT 폴더를 선택하면 비교 화면이 표시됩니다.")
        self._empty_label.setObjectName("dim")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setMinimumHeight(200)
        grid_host_layout.addWidget(self._empty_label)
        grid_host_layout.addStretch()
        grid_scroll.setWidget(grid_host)
        main.addWidget(grid_scroll, 1)

        self.nav = NavBar()
        self.nav.prev_clicked.connect(self._prev)
        self.nav.next_clicked.connect(self._next)
        main.addWidget(self.nav)

        self.setCentralWidget(root)

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=self._next)
        QShortcut(QKeySequence(Qt.Key_Left), self, activated=self._prev)
        QShortcut(QKeySequence(Qt.Key_PageDown), self, activated=self._next)
        QShortcut(QKeySequence(Qt.Key_PageUp), self, activated=self._prev)
        QShortcut(QKeySequence(Qt.Key_Home), self, activated=lambda: self._goto(0))
        QShortcut(QKeySequence(Qt.Key_End), self,
                  activated=lambda: self._goto(len(self.matches) - 1))
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._choose_folder)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self._export)
        QShortcut(QKeySequence(Qt.Key_F5), self, activated=self._rescan)

    def _apply_saved_prefs(self) -> None:
        if self.settings.tolerance:
            self.top.set_tolerance(self.settings.tolerance)

    # ----------------------------------------------------------- 폴더/스캔
    def _choose_folder(self) -> None:
        last = self.settings.last_lot_folder
        start = str(Path(last).parent) if last and Path(last).exists() else str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "LOT 폴더 선택", start)
        if folder:
            self.load_lot(folder)

    def _rescan(self) -> None:
        """현재 LOT 폴더를 다시 스캔한다(F5). 데이터가 갱신됐을 때 사용."""
        last = self.settings.last_lot_folder
        if last and Path(last).exists():
            self.load_lot(last)

    def load_lot(self, folder: str) -> None:
        # 2차 원본 보호(Section 1.1): 캐시/결과 작업공간이 이 LOT 내부면 차단한다.
        if not self._verify_workspace_outside(folder):
            return

        self.settings.last_lot_folder = folder
        self._scan_token += 1
        token = self._scan_token

        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.nav.set_status("스캔 중...")
        self.top.set_lot_name(Path(folder).name)
        self.setWindowTitle(f"{self._base_title}  —  {Path(folder).name}")

        worker = ScanWorker(folder)
        worker.signals.progress.connect(self._on_scan_progress)
        worker.signals.finished.connect(lambda idx, t=token: self._on_scan_finished(idx, t))
        worker.signals.error.connect(lambda msg, t=token: self._on_scan_error(msg, t))
        self._track_worker(worker, worker.signals.finished, worker.signals.error)
        self.pool.start(worker)

    def _track_worker(self, worker, *terminal_signals) -> None:
        """워커가 끝날 때까지 참조를 유지(실행 중 GC 로 인한 시그널 삭제 방지)."""
        self._active_workers.add(worker)
        for sig in terminal_signals:
            sig.connect(lambda *_, w=worker: self._active_workers.discard(w))

    def _verify_workspace_outside(self, folder: str) -> bool:
        """캐시/내보내기 작업공간이 선택한 LOT 폴더 내부면 안내하고 차단한다."""
        for target in (self.settings.cache_path, self.settings.exports_path):
            conflict = conflicting_source(target, [folder])
            if conflict is not None:
                self.banner.show_message(
                    "작업공간(캐시/결과)이 원본 LOT 폴더 내부에 있어 차단했습니다. "
                    "원본 보호를 위해 다른 폴더를 선택하세요.",
                    "error",
                    action_text="작업공간 변경",
                    action=self._change_workspace,
                    timeout_ms=0,
                )
                return False
        return True

    def _change_workspace(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "작업공간(캐시/결과) 폴더 선택", str(Path.home())
        )
        if folder:
            self.settings.workspace = folder
            self.settings.output_folder = ""
            self.settings.ensure_workspace()
            self.thumb_cache = ThumbnailCache(self.settings.cache_path)
            self.settings.save()
            self.banner.show_message("작업공간을 변경했습니다.", "success")

    def _on_scan_progress(self, msg: str, cur: int, total: int) -> None:
        self.nav.set_status(msg)

    def _on_scan_error(self, message: str, token: int) -> None:
        if token != self._scan_token:
            return
        self.progress.setVisible(False)
        self.nav.set_status("스캔 오류")
        self.banner.show_message(f"폴더 스캔 중 오류: {message}", "error", timeout_ms=0)

    def _on_scan_finished(self, index: LotIndex, token: int = -1) -> None:
        if token != -1 and token != self._scan_token:
            return  # 오래된(stale) 스캔 결과 무시
        self.progress.setVisible(False)
        self.lot_index = index
        layers = index.layer_canonicals()
        if not layers:
            self.banner.show_message(
                "선택한 폴더에서 layer 를 찾지 못했습니다. LOT 폴더를 확인하세요.",
                "warn", timeout_ms=0,
            )
            self.nav.set_status("layer 없음")
            self._empty_label.setVisible(True)
            self.grid.build_layout([], "")
            self.nav.set_enabled(False)
            return

        # 설정 복원(현재 LOT 에 존재하는 경우에만)
        saved_base = self.settings.base_layer if self.settings.base_layer in layers else None
        saved_compares = [l for l in self.settings.compare_layers if l in layers] or None
        self.top.set_layers(layers, base=saved_base, compares=saved_compares)
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
        if failed:
            self.banner.show_message(
                f"{len(failed)}개 이미지의 좌표를 추출하지 못했습니다(상태표시줄에 상세).",
                "warn",
            )
        self._rebuild_all()

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

    # ------------------------------------------------------- 재계산(분리)
    def _rebuild_all(self) -> None:
        """새 LOT·기준 layer 변경: base 목록·썸네일·그리드 전체 재구성, 인덱스 0."""
        if self.lot_index is None:
            return
        base_layer = self.top.base_layer()
        if not base_layer:
            return
        self._save_prefs()

        self.base_records = [
            r for r in self.lot_index.records_for_layer(base_layer) if r.ok
        ]
        self._compute_matches()

        # 썸네일 스트립(기준 layer 에만 의존 → 여기서만 재구성)
        captions, tooltips = [], []
        for r in self.base_records:
            captions.append(f"{r.wafer_id}\n({r.col},{r.row})")
            tt = f"wafer {r.wafer_id} · die({r.col},{r.row}) · pos {r.position_key}"
            if r.defect_name:
                tt += f" · {r.defect_name}"
            tooltips.append(tt)
        self.strip.set_items(captions, tooltips)
        self._start_thumbnails()

        self._rebuild_grid()
        self._empty_label.setVisible(not self.base_records)
        self.nav.set_enabled(bool(self.base_records))
        if self.base_records:
            self._goto(0)
        else:
            self.nav.set_index(0, 0)
            self.grid.show_empty("기준 layer 에 좌표 OK 인 사진이 없습니다.")

    def _rematch(self, rebuild_grid: bool) -> None:
        """비교 토글/허용오차 변경: 재매칭. 현재 인덱스는 유지(범위 clamp)."""
        if self.lot_index is None or not self.base_records:
            return
        self._save_prefs()
        self._compute_matches()
        if rebuild_grid:
            self._rebuild_grid()
        if self.matches:
            self.current = max(0, min(self.current, len(self.matches) - 1))
            self._goto(self.current)
        else:
            self.nav.set_index(0, 0)

    def _compute_matches(self) -> None:
        compare_layers = self.top.compare_layers()
        tolerance = self.top.tolerance()
        rbl = self.lot_index.records_by_layer()
        self.matches = matcher.match_all(
            self.base_records, compare_layers, rbl, tolerance
        )

    def _rebuild_grid(self) -> None:
        base_layer = self.top.base_layer()
        compare_layers = self.top.compare_layers()
        grid = layout.build_grid([base_layer] + compare_layers)
        self.grid.build_layout(grid, base_layer)

    def _start_thumbnails(self) -> None:
        if self._thumb_worker is not None:
            self._thumb_worker.cancel()
        items = [(i, r.image_path) for i, r in enumerate(self.base_records)]
        if not items:
            return
        worker = ThumbnailWorker(self.thumb_cache, items)
        token = self._scan_token
        worker.signals.ready.connect(
            lambda i, p, t=token: self.strip.set_thumbnail(i, p)
            if t == self._scan_token else None
        )
        self._track_worker(worker, worker.signals.done)
        self._thumb_worker = worker
        self.pool.start(worker)

    def _save_prefs(self) -> None:
        self.settings.tolerance = self.top.tolerance()
        self.settings.base_layer = self.top.base_layer()
        self.settings.compare_layers = self.top.compare_layers()

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

    def _open_viewer(self, record: object) -> None:
        if isinstance(record, DefectRecord):
            dlg = ImageViewerDialog(record, self)
            dlg.exec()

    # ------------------------------------------------------------ 설정
    def _open_settings(self) -> None:
        current_lot = str(self.lot_index.lot_path) if self.lot_index else None
        old_workspace = self.settings.workspace
        old_output = self.settings.output_folder
        dlg = SettingsDialog(self.settings, current_lot, self)
        if not dlg.exec():
            return
        s = dlg.updated_settings()
        # 작업공간/출력 폴더가 바뀌면 캐시를 재생성한다(원본 밖 보장은 다이얼로그에서 검증).
        if s.workspace != old_workspace or s.output_folder != old_output:
            s.ensure_workspace()
            self.thumb_cache = ThumbnailCache(s.cache_path)
        # 기본 허용오차를 스핀박스에도 반영(현재 매칭은 사용자가 바꾼 값 유지).
        try:
            s.save()
        except OSError as exc:
            self.banner.show_message(f"설정 저장 실패: {exc}", "error", timeout_ms=0)
            return
        self.banner.show_message("설정을 저장했습니다.", "success")

    # ------------------------------------------------------------ 업데이트
    def _maybe_check_update(self) -> None:
        if not self.settings.auto_update_check:
            return
        self._start_update_check(manual=False)

    def _manual_update(self) -> None:
        if self._updating:
            return
        self.nav.set_status("업데이트 확인 중...")
        self._start_update_check(manual=True)

    def _start_update_check(self, manual: bool) -> None:
        worker = updater.UpdateCheckWorker(token=self.settings.update_token)
        worker.signals.done.connect(lambda st, m=manual: self._on_update_checked(st, m))
        self._track_worker(worker, worker.signals.done)
        self.pool.start(worker)

    def _on_update_checked(self, status, manual: bool) -> None:
        self._update_status = status
        if status.available:
            self.top.set_update_available(True)
            answer = QMessageBox.question(
                self,
                "업데이트",
                "새 버전이 있습니다. 지금 업데이트할까요?\n"
                "업데이트 후 프로그램이 종료되며, 다시 시작하면 적용됩니다.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer == QMessageBox.Yes:
                self._do_update(status)
            elif not manual:
                self.banner.show_message(
                    "상단 '업데이트' 버튼으로 언제든 업데이트할 수 있습니다.", "info"
                )
        else:
            self.top.set_update_available(False)
            if manual:
                if status.error:
                    self.banner.show_message(
                        f"업데이트 확인 실패: {status.error}", "warn", timeout_ms=6000
                    )
                else:
                    self.banner.show_message("이미 최신 버전입니다.", "success")

    def _do_update(self, status) -> None:
        self._updating = True
        self.top.set_update_busy(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.nav.set_status("업데이트 준비 중...")

        worker = updater.UpdateApplyWorker(status, token=self.settings.update_token)
        worker.signals.progress.connect(self.nav.set_status)
        worker.signals.finished.connect(self._on_update_finished)
        self._track_worker(worker, worker.signals.finished)
        self.pool.start(worker)

    def _on_update_finished(self, ok: bool, message: str) -> None:
        self._updating = False
        self.progress.setVisible(False)
        self.top.set_update_busy(False)
        if ok:
            QMessageBox.information(
                self,
                "업데이트 완료",
                f"{message}\n\n프로그램을 종료합니다. 다시 시작해 주세요.",
            )
            self.close()
        else:
            self.nav.set_status("업데이트 실패")
            self.banner.show_message(f"업데이트 실패: {message}", "error", timeout_ms=0)

    @staticmethod
    def _safe_filename(name: str) -> str:
        """Windows 금지문자/끝 공백·점 제거."""
        for ch in '<>:"/\\|?*':
            name = name.replace(ch, "_")
        name = name.rstrip(" .")
        return name or "compare"

    # ------------------------------------------------------------ 출력
    def _export(self) -> None:
        if not self.matches:
            self.banner.show_message("먼저 LOT 폴더를 불러오세요.", "info")
            return
        dlg = ExportSelectDialog(self.matches, self.current, self.thumb_cache, self)
        if not dlg.exec():
            return
        indices = dlg.selected_indices()
        if not indices:
            self.banner.show_message("선택된 기준 사진이 없습니다.", "info")
            return

        default_dir = str(self.settings.exports_path)
        Path(default_dir).mkdir(parents=True, exist_ok=True)
        default_name = self._safe_filename(f"{self.lot_index.lot_name}_compare") + ".xlsx"
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
            # 차단은 명확히 알려야 하므로 액션 가능한 배너로 안내
            self.banner.show_message(str(exc).split("\n")[0], "error", timeout_ms=0)
            return
        except Exception as exc:  # noqa: BLE001
            self.banner.show_message(f"Excel 출력 중 오류: {exc}", "error", timeout_ms=0)
            return

        if self.settings.output_folder == "":
            self.settings.output_folder = str(Path(out).parent)
        self.settings.save()
        self.banner.show_message(
            f"결과를 저장했습니다: {Path(out).name}",
            "success",
            action_text="폴더 열기",
            action=lambda p=out: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(Path(p).parent))
            ),
            timeout_ms=7000,
        )

    # ------------------------------------------------------------ 종료
    def closeEvent(self, event):  # noqa: N802
        geo = self.geometry()
        self.settings.window_geometry = f"{geo.x()},{geo.y()},{geo.width()},{geo.height()}"
        self._save_prefs()
        try:
            self.settings.save()
        except OSError:
            pass
        super().closeEvent(event)
