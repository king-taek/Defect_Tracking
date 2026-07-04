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
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app import __version__, config, layout, matcher, scanner, updater
from app.config import AppSettings
from app.models import BaseDefectMatches, DefectRecord, ParseStatus
from app.safety import OriginalProtectionError, conflicting_source
from app.scanner import LotIndex
from app.session import SessionStore
from app.thumbnails import ThumbnailCache
from app.ui.compare_grid import CompareGrid
from app.ui.controls import NavBar, SideBar
from app.ui.export_dialog import ExportTrayDialog
from app.ui.heatmap_dialog import HeatmapDialog
from app.ui.help_dialog import ShortcutsDialog
from app.ui.image_loader import ImageLoader
from app.ui.image_viewer import ImageViewerDialog
from app.ui.notifications import NotificationBanner
from app.ui.settings_dialog import SettingsDialog
from app.ui.thumbnail_strip import ThumbnailStrip
from app.ui.wafer_map import WaferMapWidget
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
        self._scan_worker: Optional[ScanWorker] = None  # 진행 중 스캔(중단용)
        self._scan_token = 0  # stale 스캔/썸네일 결과 무시용
        # 매칭 인덱스 캐시(비교 layer 집합이 같으면 허용오차만 바뀔 때 재사용)
        self._match_sig: object = None
        self._match_idx = None
        self._match_fail = None
        self._layer_offsets: dict = {}  # 비교 layer 별 전역 정합오차(median)
        # 보기 필터는 '매칭만' 고정(드롭다운 제거) — 매칭 0인 후보는 항상 후보에서 제외.
        self._filter = "matched"
        # 출력 담기 트레이: 담은 BaseDefectMatches 스냅샷 목록(base image_path 로 중복 제거).
        # 스냅샷이라 기준 layer·자재(LOT)를 바꿔도 담은 것이 그대로 유지된다.
        self._export_tray: list = []
        self._view_cache: Optional[list[int]] = None  # _view_indices 캐시
        self._align_cache: dict = {}  # (lot_id, wafer, product) -> Alignment (웨이퍼 맵 정합)
        self.session: Optional[SessionStore] = None  # 세션 마킹/메모(작업공간 저장)
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

    def show_initial(self) -> None:
        """초기 표시 — 기본 최대화(설정). 최대화를 끈 적이 있으면 저장된 창 크기로 연다.

        _restore_geometry 가 normal 상태의 창 크기/위치를 미리 설정해 두므로, 최대화를
        해제하면 그 크기로 복원된다.
        """
        if self.settings.window_maximized:
            self.showMaximized()
        else:
            self.show()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        main = QVBoxLayout(root)
        main.setContentsMargins(10, 10, 10, 10)
        main.setSpacing(8)

        # 알림 배너는 레이아웃에 넣지 않고 창 위 오버레이로 띄운다(표시 시 UI 가 밀리지 않음).
        self.banner = NotificationBanner(root)
        self.banner.hide()

        # 좌측 사이드바 | 우측(짧은 상단 + 큰 그리드) — 수평 스플리터
        self.splitter = QSplitter(Qt.Horizontal)

        # ── 좌측: 컨트롤 사이드바
        self.top = SideBar()
        self.top.open_folder.connect(self._choose_folder)
        self.top.base_layer_changed.connect(lambda _: self._rebuild_all())
        self.top.compare_layers_changed.connect(lambda: self._rematch(rebuild_grid=True))
        self.top.tolerance_changed.connect(lambda _: self._rematch(rebuild_grid=False))
        self.top.export_requested.connect(self._export)
        self.top.settings_requested.connect(self._open_settings)
        # 업데이트는 설정 다이얼로그로 이동(_open_settings 에서 연결)
        # 자재 폴더 버튼: 우클릭 시 최근 폴더 메뉴
        self.top.btn_open.setContextMenuPolicy(Qt.CustomContextMenu)
        self.top.btn_open.customContextMenuRequested.connect(self._show_recent_menu)
        self.top.btn_open.setToolTip(
            "리뷰가 진행된 자재(LOT) 폴더를 선택 (Ctrl+O) · 우클릭: 최근 폴더"
        )
        self.splitter.addWidget(self.top)

        # ── 우측: 짧은 상단(썸네일 + 탐색) + 큰 비교 그리드
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        top_band = QFrame()
        top_band.setObjectName("panel")
        band_layout = QVBoxLayout(top_band)
        band_layout.setContentsMargins(10, 8, 10, 8)
        band_layout.setSpacing(6)
        self.strip = ThumbnailStrip()
        self.strip.thumb_clicked.connect(self._goto)
        # 썸네일 + 웨이퍼 맵을 한 줄에(맵은 현재 wafer 의 die 현황)
        strip_row = QHBoxLayout()
        strip_row.setContentsMargins(0, 0, 0, 0)
        strip_row.setSpacing(8)
        strip_row.addWidget(self.strip, 1)
        # defect 히트맵 보기(항목 4) — 웨이퍼맵에 defect 밀도를 표시하고 위치별 비교.
        self.btn_heatmap = QPushButton("히트맵\n보기")
        self.btn_heatmap.setFixedSize(96, 96)
        self.btn_heatmap.setToolTip(
            "defect 밀도 히트맵을 새 창으로 엽니다. 위치를 클릭하면 그 자리의 defect 들을 "
            "layer 별로 나란히 비교하고 출력에 담을 수 있습니다."
        )
        self.btn_heatmap.clicked.connect(self._open_heatmap)
        self.btn_heatmap.setEnabled(False)
        strip_row.addWidget(self.btn_heatmap, 0, Qt.AlignVCenter)
        # 웨이퍼 맵 + 캡션(디바이스/정합 안내)을 세로로 묶는다.
        wafer_box = QVBoxLayout()
        wafer_box.setContentsMargins(0, 0, 0, 0)
        wafer_box.setSpacing(2)
        self.wafer_map = WaferMapWidget()
        self.wafer_map.die_clicked.connect(self._jump_to_die)
        wafer_box.addWidget(self.wafer_map, 0, Qt.AlignHCenter)
        self.lbl_wafer = QLabel("")
        self.lbl_wafer.setObjectName("dim")
        self.lbl_wafer.setStyleSheet("font-size:9px;")
        self.lbl_wafer.setAlignment(Qt.AlignCenter)
        self.lbl_wafer.setWordWrap(True)
        self.lbl_wafer.setFixedWidth(140)
        wafer_box.addWidget(self.lbl_wafer, 0, Qt.AlignHCenter)
        strip_row.addLayout(wafer_box)
        band_layout.addLayout(strip_row)
        self.nav = NavBar()
        self.nav.prev_clicked.connect(self._prev)
        self.nav.next_clicked.connect(self._next)
        # 보기 필터는 '매칭만' 고정(드롭다운 제거) — 어떤 비교 layer 와도 매칭 안 된
        # 기준 사진은 항상 후보에서 제외한다.
        # 항목 9 에서 비운 자리에 '출력에 추가'(트레이 담기) 버튼을 둔다(항목 1).
        self.btn_add_export = QPushButton("＋ 출력에 추가")
        self.btn_add_export.setObjectName("mini")
        self.btn_add_export.setToolTip(
            "현재 기준 사진을 출력 목록(트레이)에 담습니다. (A)\n"
            "담은 것들은 '결과 출력' 시 함께 Excel 로 나옵니다."
        )
        self.btn_add_export.clicked.connect(self._add_current_to_export)
        self.btn_add_export.setEnabled(False)
        self.nav.add_widget(self.btn_add_export)
        self.lbl_view = QLabel("")
        self.lbl_view.setObjectName("dim")
        self.nav.add_widget(self.lbl_view)
        band_layout.addWidget(self.nav)
        right_layout.addWidget(top_band)

        # 진행바 + 중단 버튼(스캔 중에만 표시)
        progress_row = QHBoxLayout()
        progress_row.setContentsMargins(0, 0, 0, 0)
        progress_row.setSpacing(8)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        progress_row.addWidget(self.progress, 1)
        self.btn_stop = QPushButton("■ 중단")
        self.btn_stop.setObjectName("mini")
        self.btn_stop.setToolTip("진행 중인 스캔을 중단합니다.")
        self.btn_stop.clicked.connect(self._stop_scan)
        self.btn_stop.setVisible(False)
        progress_row.addWidget(self.btn_stop, 0)
        right_layout.addLayout(progress_row)

        # 비교 그리드 (스크롤 가능) — 큰 메인 영역
        grid_scroll = QScrollArea()
        grid_scroll.setWidgetResizable(True)
        grid_scroll.setFrameShape(QFrame.NoFrame)
        grid_host = QFrame()
        grid_host.setObjectName("panel")
        grid_host_layout = QVBoxLayout(grid_host)
        grid_host_layout.setContentsMargins(12, 12, 12, 12)
        self.grid = CompareGrid(loader=self.image_loader)
        self.grid.image_clicked.connect(self._open_viewer)
        self.grid.mark_requested.connect(self._toggle_mark)
        self.grid.note_requested.connect(self._edit_note)
        grid_host_layout.addWidget(self.grid)
        self._empty_label = QLabel("자재 폴더를 선택하면 비교 화면이 표시됩니다.")
        self._empty_label.setObjectName("dim")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setMinimumHeight(200)
        grid_host_layout.addWidget(self._empty_label)
        grid_host_layout.addStretch()
        grid_scroll.setWidget(grid_host)
        right_layout.addWidget(grid_scroll, 1)

        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setCollapsible(0, False)
        sw = max(180, int(self.settings.sidebar_width))
        self.splitter.setSizes([sw, max(600, self.width() - sw)])
        main.addWidget(self.splitter, 1)

        self.setCentralWidget(root)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        # 오버레이 배너를 창 크기에 맞춰 상단 중앙에 유지한다.
        if getattr(self, "banner", None) is not None:
            self.banner.reposition()
            self.banner.raise_()

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=self._next)
        QShortcut(QKeySequence(Qt.Key_Left), self, activated=self._prev)
        QShortcut(QKeySequence(Qt.Key_PageDown), self, activated=self._next)
        QShortcut(QKeySequence(Qt.Key_PageUp), self, activated=self._prev)
        QShortcut(QKeySequence(Qt.Key_Home), self,
                  activated=lambda: self._goto_view_edge(False))
        QShortcut(QKeySequence(Qt.Key_End), self,
                  activated=lambda: self._goto_view_edge(True))
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._choose_folder)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self._export)
        QShortcut(QKeySequence(Qt.Key_F5), self, activated=self._rescan)
        # 비교 layer 전체/해제, 다음 미매칭 점프
        QShortcut(QKeySequence("Ctrl+A"), self,
                  activated=lambda: self.top._set_all_compares(True))
        QShortcut(QKeySequence("Ctrl+D"), self,
                  activated=lambda: self.top._set_all_compares(False))
        QShortcut(QKeySequence(Qt.Key_U), self, activated=self._jump_unmatched)
        QShortcut(QKeySequence(Qt.Key_M), self, activated=self._toggle_mark_current)
        QShortcut(QKeySequence(Qt.Key_A), self, activated=self._add_current_to_export)
        QShortcut(QKeySequence(Qt.Key_F1), self, activated=self._open_help)

    def _apply_saved_prefs(self) -> None:
        # 0.0(정확 일치)도 유효한 사용자 설정이므로 falsy 검사로 떨어뜨리지 않는다.
        if self.settings.tolerance is not None:
            self.top.set_tolerance(self.settings.tolerance)

    # ----------------------------------------------------------- 폴더/스캔
    def _choose_folder(self) -> None:
        last = self.settings.last_lot_folder
        start = str(Path(last).parent) if last and Path(last).exists() else str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "자재 폴더 선택", start)
        if folder:
            self._open_folder(folder)

    def _open_folder(self, folder: str) -> None:
        """선택 폴더의 구조 레벨을 판별해 자재 폴더로 보정하거나 재선택을 안내한다.

        모든 안내는 비차단 배너로(팝업 없음). 원본 read-only.
        """
        kind, material = scanner.classify_selection(folder)
        if kind == "material":
            self.load_lot(folder)
        elif kind in ("layer", "wafer") and material is not None:
            label = "layer" if kind == "layer" else "wafer"
            self.banner.show_message(
                f"{label} 폴더가 선택되었으니 자재 폴더로 자동 이동하여 탐색합니다.",
                "info",
            )
            self.load_lot(str(material))
        elif kind == "too_high":
            self.banner.show_message(
                "상위(device) 폴더가 선택되었습니다. 자재 폴더를 선택해 주세요.",
                "warn",
                action_text="자재 폴더 선택",
                action=self._choose_folder,
                timeout_ms=0,
            )
        else:  # unknown — 그대로 시도(스캔에서 layer 없음 경고로 처리)
            self.load_lot(folder)

    def _rescan(self) -> None:
        """현재 LOT 폴더를 다시 스캔한다(F5). 데이터가 갱신됐을 때 사용."""
        last = self.settings.last_lot_folder
        if last and Path(last).exists():
            self.load_lot(last)

    def _show_recent_menu(self) -> None:
        recents = [f for f in self.settings.recent_folders if Path(f).exists()]
        if not recents:
            self.banner.show_message("최근 연 자재 폴더가 없습니다.", "info")
            return
        menu = QMenu(self)
        for folder in recents:
            menu.addAction(folder, lambda f=folder: self._open_folder(f))
        menu.exec(self.top.btn_open.mapToGlobal(self.top.btn_open.rect().bottomLeft()))

    def _push_recent(self, folder: str) -> None:
        recents = [f for f in self.settings.recent_folders if f != folder]
        recents.insert(0, folder)
        self.settings.recent_folders = recents[:5]

    def _auto_select_product(self, folder: str) -> None:
        """자재 경로에서 디바이스(제품)를 자동 인식해 활성화한다(스캔 전 호출).

        인식되면 좌표 변환·웨이퍼 맵 die 배치가 그 제품 기준으로 적용된다. 실패하면
        설정의 제품(settings.product)을 그대로 둔다.
        """
        try:
            key, score = config.match_product_for_path(folder)
        except Exception:  # noqa: BLE001 - 인식 실패는 치명적이지 않음
            return
        if key and key != config._active_product:
            config.set_active_product(key)
            # 빌트인(die_map 없음)으로 인식됐으면 같은 크기의 DB die_map 제품으로 승격.
            config.ensure_die_map_product()
            prod = config.active_product()
            if prod.source == "db":
                self.banner.show_message(
                    f"디바이스 자동 인식: {prod.name}", "info", timeout_ms=2500
                )

    def load_lot(self, folder: str) -> None:
        # 2차 원본 보호(Section 1.1): 캐시/결과 작업공간이 이 LOT 내부면 차단한다.
        if not self._verify_workspace_outside(folder):
            return

        # 디바이스 자동 인식(스캔 전): 좌표 변환·die 배치를 올바른 제품으로 맞춘다.
        self._auto_select_product(folder)

        self.settings.last_lot_folder = folder
        self._push_recent(folder)
        self._scan_token += 1
        token = self._scan_token

        self.progress.setVisible(True)
        self.btn_stop.setVisible(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("스캔 준비 중...  %p%")
        self.nav.set_status("스캔 중...")
        self.top.set_lot_name(Path(folder).name)
        self.setWindowTitle(f"{self._base_title}  —  {Path(folder).name}")

        worker = ScanWorker(folder)
        self._scan_worker = worker
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

    def _stop_scan(self) -> None:
        """진행 중인 스캔을 중단한다(협조적 취소 + stale 토큰으로 결과 폐기)."""
        if self._scan_worker is not None:
            self._scan_worker.cancel()
            self._scan_worker = None
        self._scan_token += 1  # 늦게 도착하는 finished/progress 결과를 무시
        self.progress.setVisible(False)
        self.btn_stop.setVisible(False)
        self.nav.set_status("스캔 중단됨")
        self.banner.show_message("스캔을 중단했습니다.", "info")

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
        if total > 0:
            # layer 단위 진행을 0~100%로 환산해 진행바에 표시
            pct = int(round(min(cur, total) / total * 100))
            self.progress.setRange(0, 100)
            self.progress.setValue(pct)
            self.progress.setFormat(f"{msg}  %p%")

    def _on_scan_error(self, message: str, token: int) -> None:
        if token != self._scan_token:
            return
        self.progress.setVisible(False)
        self.btn_stop.setVisible(False)
        self._scan_worker = None
        self.nav.set_status("스캔 오류")
        self.banner.show_message(f"폴더 스캔 중 오류: {message}", "error", timeout_ms=0)

    def _on_scan_finished(self, index: LotIndex, token: int = -1) -> None:
        if token != -1 and token != self._scan_token:
            return  # 오래된(stale) 스캔 결과 무시
        self.progress.setVisible(False)
        self.btn_stop.setVisible(False)
        self._scan_worker = None
        self.lot_index = index
        # 새 LOT: 웨이퍼 맵 정합 캐시를 비운다(id(lot_index) 재사용으로 인한 stale 방지).
        self._align_cache.clear()
        # 세션 마킹/메모 로드(작업공간, 원본 밖)
        self.session = SessionStore.load(self.settings.workspace_path, index.lot_name)
        layers = index.layer_canonicals()
        if not layers:
            self.banner.show_message(
                "선택한 폴더에서 layer 를 찾지 못했습니다. 자재 폴더를 확인하세요.",
                "warn", timeout_ms=0,
            )
            self.nav.set_status("layer 없음")
            self._empty_label.setVisible(True)
            self.grid.build_layout([], "")
            self.nav.set_enabled(False)
            return

        # 기준 layer 는 빈칸으로 시작(사용자가 직접 선택), 비교 기본값은 선호 재리뷰 집합만.
        # (자재 폴더를 바꿀 때마다 재리뷰만 선택되도록 저장값을 자동 복원하지 않는다.)
        rereview = self._preferred_rereview(index)
        self.top.set_layers(layers, base=None, compares=None, rereview=rereview)
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
        # 좌표 추출 실패 진단 리포트는 개발자 모드(CONDER_DEV)에서만 파일로 남긴다.
        report_path = self._write_diag_report(index) if config.dev_mode() else None
        if failed:
            self.banner.show_message(
                f"{len(failed)}개 이미지의 좌표를 추출하지 못했습니다(상태표시줄에 상세).",
                "warn",
                action_text="진단 로그 열기" if report_path else None,
                action=(lambda p=report_path: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(p)))) if report_path else None,
            )
        # 접근 불가(권한/네트워크) 경로가 있으면 조용히 누락되지 않도록 알린다.
        errors = getattr(index, "scan_errors", [])
        if errors:
            preview = "\n".join(errors[:8])
            if len(errors) > 8:
                preview += f"\n… 외 {len(errors) - 8}개"
            self.banner.show_message(
                f"{len(errors)}개 경로를 읽지 못해 일부 layer/wafer 가 누락됐을 수 있습니다.",
                "warn",
                timeout_ms=0,
            )
            self.nav.set_status_tooltip(
                self._failure_summary(failed) + "\n\n[접근 실패 경로]\n" + preview
            )
        self._rebuild_all()

    def _write_diag_report(self, index):
        """좌표 추출 실패 진단 리포트를 단일 md 에 누적 추가한다(실패 시 None)."""
        try:
            from app import diagnostics
            return diagnostics.write_parse_failure_report(
                self.settings.log_dir_path,
                index.lot_name,
                index.records,
                getattr(index, "scan_errors", []),
            )
        except OSError:
            return None

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

    def _recommended_base(self) -> str:
        """그리드 기본 배치 순서에서 현재 LOT 에 존재하는 첫 layer 를 추천(자동선택 X)."""
        if self.lot_index is None:
            return ""
        layers = self.lot_index.layer_canonicals()
        from app.layout import _canon_token
        present = {_canon_token(l): l for l in layers}
        for row in config.DEFAULT_LAYER_GRID:
            for cell in row:
                if _canon_token(cell) in present:
                    return present[_canon_token(cell)]
        return layers[0] if layers else ""

    def _show_base_prompt(self) -> None:
        """기준 layer 미선택 시 대기 화면: 매칭·탐색·스트립·맵을 비우고 선택을 안내한다."""
        self.base_records = []
        self.matches = []
        self._view_cache = None
        self.current = -1
        self.strip.set_items([], [])
        self.wafer_map.clear()
        self.lbl_wafer.setText("")
        self.nav.set_enabled(False)
        self.nav.set_index(0, 0)
        self.top.set_match_summary("")
        self._update_add_export_button()  # 트레이는 유지, 버튼 상태만 갱신
        rec = self._recommended_base()
        hint = f"  (추천: {rec})" if rec else ""
        self.grid.show_empty(f"기준 layer 를 선택하세요.{hint}")
        self._empty_label.setVisible(False)

    # ------------------------------------------------------- 재계산(분리)
    def _rebuild_all(self) -> None:
        """새 LOT·기준 layer 변경: base 목록·썸네일·그리드 전체 재구성, 인덱스 0."""
        if self.lot_index is None:
            return
        base_layer = self.top.base_layer()
        if not base_layer:
            # 기준 layer 미선택: 매칭/탐색을 비우고 선택을 유도(대기 상태).
            self._show_base_prompt()
            return
        self._save_prefs()

        self.base_records = [
            r for r in self.lot_index.records_for_layer(base_layer) if r.ok
        ]
        # 출력 트레이는 스냅샷이라 기준 layer/자재 변경에도 유지한다(초기화하지 않음).
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
            view = self._view_indices()
            self._goto(view[0] if view else 0)
        else:
            self.nav.set_index(0, 0)
            self.grid.show_empty("기준 layer 에 좌표 OK 인 사진이 없습니다.")
            self.wafer_map.clear()
        self._refresh_strip_marks()
        self._update_add_export_button()

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
        self._refresh_strip_marks()

    def _compute_matches(self) -> None:
        compare_layers = self.top.compare_layers()
        tolerance = self.top.tolerance()
        rbl = self.lot_index.records_by_layer()
        idx, fidx = self._get_match_indices(compare_layers, rbl)
        # 인덱스를 재사용(허용오차만 변경 시 재인덱싱 없음) + 전역 정합오차 보정 매칭.
        self.matches, self._layer_offsets = matcher.match_all_with_offsets(
            self.base_records, compare_layers, rbl, tolerance,
            index=idx, fail_index=fidx,
        )
        self._view_cache = None  # 매칭이 바뀌면 필터 결과 캐시 무효화
        self._update_match_summary()

    def _open_heatmap(self) -> None:
        if not self.matches:
            self.banner.show_message("먼저 자재 폴더와 기준 layer 를 선택하세요.", "info")
            return
        current_wafer = None
        if 0 <= self.current < len(self.matches):
            current_wafer = self.matches[self.current].base.wafer_id
        dlg = HeatmapDialog(
            self.matches,
            self.top.base_layer(),
            self.top.compare_layers(),
            self.thumb_cache,
            self._add_indices_to_export,
            self.settings,
            current_wafer=current_wafer,
            parent=self,
        )
        dlg.exec()

    def _get_match_indices(self, compare_layers, rbl):
        """(lot, 비교 layer 집합) 기준으로 die/실패 인덱스를 캐시·재사용한다."""
        sig = (id(self.lot_index), tuple(compare_layers))
        if sig != self._match_sig:
            self._match_idx = matcher.build_die_index(rbl, compare_layers)
            self._match_fail = matcher.build_fail_index(rbl, compare_layers)
            self._match_sig = sig
        return self._match_idx, self._match_fail

    def _update_match_summary(self) -> None:
        """사이드바에 실시간 매칭 요약을 표시(허용오차 튜닝 피드백)."""
        if not self.matches:
            self.top.set_match_summary("")
            return
        total_pairs = sum(len(m.results) for m in self.matches)
        matched_pairs = sum(1 for m in self.matches for r in m.results if r.is_match)
        bases_matched = sum(
            1 for m in self.matches if any(r.is_match for r in m.results)
        )
        self.top.set_match_summary(
            f"매칭 {matched_pairs}/{total_pairs} 쌍 · "
            f"기준 {bases_matched}/{len(self.matches)}장"
        )
        # layer 간 전역 정합오차(median)를 tooltip 으로 안내(레지스트레이션 shift 파악)
        lines = ["[layer 간 정합오차(중앙값)]"]
        for layer, off in self._layer_offsets.items():
            if off.count:
                lines.append(
                    f"  {layer}: dx {off.dx:+.1f}, dy {off.dy:+.1f} µm "
                    f"(1:1 {off.count}쌍 기준, 보정 적용)"
                )
        if len(lines) > 1:
            self.top.lbl_match.setToolTip("\n".join(lines))
        else:
            self.top.lbl_match.setToolTip("")

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
        worker = ThumbnailWorker(
            self.thumb_cache, items, center_ratio=self._thumbnail_center_ratio()
        )
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

    # ------------------------------------------------- 썸네일 확대율
    @staticmethod
    def _thumbnail_center_ratio() -> float:
        """상단 썸네일 중앙 crop 비율 — 5× 고정(사진 중앙 20%)."""
        return config.THUMBNAIL_CENTER_RATIO

    # ------------------------------------------------- 출력 담기 트레이(항목 1)
    def _add_current_to_export(self) -> None:
        if not self.matches or not (0 <= self.current < len(self.matches)):
            self.banner.show_message("담을 기준 사진이 없습니다.", "info")
            return
        self._add_indices_to_export([self.current])

    def _tray_keys(self) -> set:
        return {str(m.base.image_path) for m in self._export_tray}

    def _add_indices_to_export(self, indices: list[int]) -> None:
        """주어진 base index 들의 매칭 스냅샷을 출력 트레이에 담는다(중복 무시)."""
        keys = self._tray_keys()
        added = 0
        for i in indices:
            if 0 <= i < len(self.matches):
                m = self.matches[i]
                k = str(m.base.image_path)
                if k not in keys:
                    self._export_tray.append(m)
                    keys.add(k)
                    added += 1
        self._update_add_export_button()
        if added:
            self.banner.show_message(
                f"출력 목록에 {added}장 담았습니다. (현재 {len(self._export_tray)}장)",
                "success", timeout_ms=2000,
            )
        else:
            self.banner.show_message("이미 담긴 사진입니다.", "info", timeout_ms=1500)

    def _clear_export_tray(self) -> None:
        self._export_tray = []
        self._update_add_export_button()

    def _update_add_export_button(self) -> None:
        n = len(self._export_tray)
        self.btn_add_export.setText(f"＋ 출력에 추가 ({n})" if n else "＋ 출력에 추가")
        self.btn_add_export.setEnabled(bool(self.matches))
        self.btn_heatmap.setEnabled(bool(self.matches))

    # ------------------------------------------------------------ 탐색
    def _goto(self, index: int) -> None:
        if not self.matches or not (0 <= index < len(self.matches)):
            return
        self.current = index
        item = self.matches[index]
        self.grid.update_for_base(item, self.top.compare_layers())
        self.strip.set_current(index)
        # 탐색 번호는 현재 보기(필터 후보) 기준으로 표시(제외된 후보는 세지 않음)
        view = self._view_indices()
        if index in view:
            self.nav.set_index(view.index(index) + 1, len(view))
        else:
            self.nav.set_index(index + 1, len(self.matches))
        self._prefetch_neighbors(index)
        self._update_wafer_map(item)

    def _prefetch_neighbors(self, index: int) -> None:
        """인접 기준의 이미지(기준+매칭 비교)를 미리 로드해 탐색 체감을 높인다."""
        paths: list[str] = []
        for j in (index + 1, index - 1, index + 2):
            if 0 <= j < len(self.matches):
                m = self.matches[j]
                paths.append(str(m.base.image_path))
                for r in m.results:
                    if r.is_match and r.matched is not None:
                        paths.append(str(r.matched.image_path))
        if paths:
            self.image_loader.prefetch(paths)

    @staticmethod
    def _preferred_rereview(index) -> set:
        """선호 재리뷰 layer 집합: canonical 별 최대 재리뷰 레벨(≥1)의 display 만.

        같은 canonical 에 재리뷰·재재리뷰가 모두 있으면 더 깊은(재재리뷰) 것만 고른다.
        """
        best_level: dict[str, int] = {}
        for layer in index.layers:
            lv = getattr(layer, "re_review_level", 0)
            if lv >= 1:
                best_level[layer.canonical] = max(best_level.get(layer.canonical, 0), lv)
        chosen = set()
        for layer in index.layers:
            lv = getattr(layer, "re_review_level", 0)
            if lv >= 1 and lv == best_level.get(layer.canonical):
                chosen.add(layer.display or layer.canonical)
        return chosen

    @staticmethod
    def _match_status(item) -> str:
        """기준 1개의 매칭 상태: full(전부) / partial(일부) / none(전무)."""
        results = item.results
        if not results:
            return "none"
        matched = sum(1 for r in results if r.is_match)
        if matched == 0:
            return "none"
        if matched == len(results):
            return "full"
        return "partial"

    def _passes_filter(self, item) -> bool:
        if self._filter == "all":
            return True
        status = self._match_status(item)
        if self._filter == "matched":
            return status != "none"
        if self._filter == "unmatched":
            return status != "full"
        if self._filter == "full":
            return status == "full"
        return True

    def _view_indices(self) -> list[int]:
        if self._view_cache is None:
            idxs = [i for i, m in enumerate(self.matches) if self._passes_filter(m)]
            # 기본 '매칭만' 필터가 모든 후보를 제외하면(예: 비교 layer 미선택) 빈 화면
            # 대신 전체를 보인다(혼란 방지). 사용자가 고른 명시 필터는 그대로 둔다.
            if not idxs and self.matches and self._filter == "matched":
                idxs = list(range(len(self.matches)))
            self._view_cache = idxs
        return self._view_cache

    def _step(self, delta: int) -> None:
        if not self.matches:
            return
        view = self._view_indices()
        if not view:
            self.banner.show_message("필터에 해당하는 기준 사진이 없습니다.", "info")
            return
        if self.current in view:
            pos = view.index(self.current)
            nxt = view[(pos + delta) % len(view)]
        else:
            nxt = view[0]
        self._goto(nxt)

    def _prev(self) -> None:
        self._step(-1)

    def _next(self) -> None:
        self._step(1)

    def _goto_view_edge(self, last: bool) -> None:
        view = self._view_indices()
        if view:
            self._goto(view[-1] if last else view[0])

    def _jump_unmatched(self) -> None:
        """현재 다음에 위치한 '미매칭 포함' 기준으로 점프(트리아지).

        현재 보기(필터)에 포함된 후보 중에서만 점프한다(제외된 후보는 건너뜀).
        """
        if not self.matches:
            return
        view = self._view_indices()
        targets = [i for i in view if self._match_status(self.matches[i]) != "full"]
        if not targets:
            self.banner.show_message("미매칭이 있는 기준 사진이 없습니다.", "success")
            return
        for i in targets:
            if i > self.current:
                self._goto(i)
                return
        self._goto(targets[0])  # 끝까지 없으면 처음으로 순환

    def _refresh_view_count(self) -> None:
        if self._filter == "all" or not self.matches:
            self.lbl_view.setText("")
            return
        n_view = len(self._view_indices())
        excluded = len(self.matches) - n_view
        if self._filter == "matched" and excluded > 0:
            self.lbl_view.setText(f"({n_view}개 · 제외 {excluded})")
        else:
            self.lbl_view.setText(f"({n_view}개)")

    def _refresh_strip_marks(self) -> None:
        """썸네일에 매칭 상태 점 + 세션 마킹 별을 반영한다."""
        if not self.matches:
            return
        statuses = [self._match_status(m) for m in self.matches]
        self.strip.set_status_marks(statuses)
        if self.session is not None:
            for i, m in enumerate(self.matches):
                self.strip.set_marked(i, self.session.is_marked(str(m.base.image_path)))
        # 매칭 0인 기준 사진은 후보(썸네일)에서도 제외해 보이도록 반영
        self.strip.set_visible_set(self._view_indices())
        self._refresh_view_count()

    # ---- 세션 마킹/메모 ----
    def _toggle_mark(self, record) -> None:
        if self.session is None or record is None:
            return
        marked = self.session.toggle_mark(str(record.image_path))
        for i, m in enumerate(self.matches):
            if m.base.image_path == record.image_path:
                self.strip.set_marked(i, marked)
        self.banner.show_message("마킹함." if marked else "마킹 해제.", "info", timeout_ms=1500)

    def _toggle_mark_current(self) -> None:
        if self.matches and 0 <= self.current < len(self.matches):
            self._toggle_mark(self.matches[self.current].base)

    def _edit_note(self, record) -> None:
        if self.session is None or record is None:
            return
        key = str(record.image_path)
        text, ok = QInputDialog.getText(
            self, "메모", "이 기준 사진에 대한 메모:", text=self.session.note(key)
        )
        if ok:
            self.session.set_note(key, text.strip())
            self.banner.show_message("메모를 저장했습니다.", "success", timeout_ms=1500)

    def _open_viewer(self, record: object) -> None:
        if isinstance(record, DefectRecord):
            dlg = ImageViewerDialog(record, self)
            dlg.exec()

    def _open_help(self) -> None:
        ShortcutsDialog(self).exec()

    # ---- 웨이퍼 맵 ----
    _ALIGN_MIN_OVERLAP = 0.6  # 이 비율 이상 겹쳐야 디바이스 모양을 신뢰

    def _update_wafer_map(self, item) -> None:
        """현재 wafer 의 die 격자를 매칭 상태로 갱신한다.

        디바이스 DB die_map 이 있으면 관측 die 와 **정합(평행이동)** 시켜 실제 모양으로
        그린다. 정합 신뢰도가 낮으면 사각 전체로 폴백하고 캡션·로그로 알린다.
        """
        from app import wafermap_align

        wafer = item.base.wafer_id
        states: dict[tuple[int, int], str] = {}
        for m in self.matches:
            b = m.base
            if b.wafer_id != wafer or b.col is None or b.row is None:
                continue
            if b.col < 0 or b.row < 0:
                continue
            states[(b.col, b.row)] = self._match_status(m)
        observed = set(states.keys())

        prod = config.active_product()
        valid: Optional[set] = None
        # 캡션은 제품명만 표기(‘모양 정합 %’ 등은 노출하지 않음).
        caption = prod.name if prod.source == "db" else ""
        if prod.die_map and observed:
            align = self._get_alignment(wafer, prod, observed)
            if align.overlap >= self._ALIGN_MIN_OVERLAP:
                valid = wafermap_align.shifted_die_map(prod.die_map, align)

        current = (item.base.col, item.base.row)
        # 실제 관측(매칭)된 die 는 DB 고정 모양(valid) 밖이어도 항상 그린다 — 그렇지 않으면
        # 정합 후 모양 밖으로 나온 새 die 가 격자만 커지고 색칠 없이 사라져 보인다.
        paint_valid = (valid | observed) if valid is not None else None

        if paint_valid is not None:
            # 디바이스 모양: 실제로 그려지는 셀(paint_valid = valid∪observed)의 bounding box
            # 로 격자를 정규화한다. 좌표계 원점이 wafer 마다 달라도 맵이 여백에 떠 보이거나
            # 좌·상단이 잘리지 않는다. (current 는 여기서 제외 — 음수 좌표로 걸러진 die 가
            # 헛여백을 만들지 않도록. 유효한 current 는 이미 paint_valid 안에 있다.)
            content = set(paint_valid)
            min_col = min(c for c, _ in content)
            min_row = min(r for _, r in content)
            max_col = max(c for c, _ in content)
            max_row = max(r for _, r in content)
            cols = max_col - min_col + 1
            rows = max_row - min_row + 1
            origin = (min_col, min_row)
        else:
            # 사각 폴백: 원점 (0,0) + 패키지 크기(관측 max 로 확장).
            max_col = max((c for c, _ in observed), default=0)
            max_row = max((r for _, r in observed), default=0)
            cols = max(prod.kla_package_x_count, max_col + 1)
            rows = max(prod.kla_package_y_count, max_row + 1)
            origin = (0, 0)

        self.wafer_map.set_data(cols, rows, states, current, valid=paint_valid, origin=origin)
        self.lbl_wafer.setText(caption)
        self.wafer_map.setToolTip(
            "웨이퍼 맵 — die 클릭 시 해당 기준 사진으로 이동"
            + (f"\n{caption}" if caption else "")
        )

    def _get_alignment(self, wafer: str, prod, observed: set):
        """(lot, wafer, product) 단위로 정합 결과를 캐시·재사용한다."""
        from app import wafermap_align

        key = (id(self.lot_index), wafer, prod.key)
        cached = self._align_cache.get(key)
        if cached is None:
            cached = wafermap_align.align_observed_to_diemap(observed, prod.die_map)
            self._align_cache[key] = cached
            if cached.overlap < self._ALIGN_MIN_OVERLAP:
                import logging
                logging.getLogger("conder.wafermap").info(
                    "die 정합 신뢰도 낮음 — wafer=%s product=%s overlap=%.2f",
                    wafer, prod.key, cached.overlap,
                )
        return cached

    def _jump_to_die(self, col: int, row: int) -> None:
        if not self.matches:
            return
        wafer = self.matches[self.current].base.wafer_id
        for i, m in enumerate(self.matches):
            b = m.base
            if b.wafer_id == wafer and b.col == col and b.row == row:
                self._goto(i)
                return

    # ------------------------------------------------------------ 설정
    def _open_settings(self) -> None:
        current_lot = str(self.lot_index.lot_path) if self.lot_index else None
        old_workspace = self.settings.workspace
        old_output = self.settings.output_folder
        update_available = bool(self._update_status and self._update_status.available)
        dlg = SettingsDialog(
            self.settings, current_lot, self, update_available=update_available
        )
        accepted = dlg.exec()
        # "지금 업데이트/업데이트 확인" 클릭 시: 설정 저장 후 기존 비동기 흐름 재사용
        if dlg.wants_update():
            try:
                dlg.updated_settings().save()
            except OSError:
                pass
            self._manual_update()
            return
        if not accepted:
            return
        s = dlg.updated_settings()
        # 디바이스 DB 를 다시 읽어 제품 목록을 갱신한 뒤 활성 제품 적용.
        # 경로가 지정되면 그 경로를, 비면 번들 DB 를 자동으로 읽는다(하드코딩 금지).
        try:
            from pathlib import Path as _P

            from app.device_db import load_device_db
            db_path = _P(s.device_db_path) if s.device_db_path else None
            if db_path is None or not db_path.exists():
                db_path = config.bundled_device_db_path()
            if db_path is not None:
                config.register_devices(load_device_db(db_path))
        except Exception:  # noqa: BLE001
            self.banner.show_message("디바이스 DB 로드 실패(설정 확인).", "warn")
        config.set_active_product(s.product)
        config.ensure_die_map_product()
        # 제품/DB 가 바뀌면 die_map 이 달라지므로 웨이퍼 맵 정합 캐시를 무효화한다.
        self._align_cache.clear()
        # 다음 네비게이션까지 기다리지 않고 지금 바로 새 제품 기준으로 다시 그린다.
        if self.matches:
            self._goto(self.current)
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
            self.banner.show_message("먼저 자재 폴더를 불러오세요.", "info")
            return
        # 이번 LOT 에서 매칭 있는 기준 사진(스냅샷) — 다이얼로그의 '전체 추가' 버튼용.
        all_matched = [
            m for m in self.matches if self._match_status(m) != "none"
        ]
        # 트레이가 비어 있어도 다이얼로그를 열어(전체 추가 버튼 사용) 담을 수 있게 한다.
        dlg = ExportTrayDialog(
            list(self._export_tray), self.thumb_cache,
            all_matched=all_matched, parent=self,
        )
        if not dlg.exec():
            return
        selected = dlg.selected()  # list[BaseDefectMatches]
        # 다이얼로그에서 편집한 결과를 트레이에 반영(다음 출력에도 유지).
        self._export_tray = list(selected)
        self._update_add_export_button()
        if not selected:
            self.banner.show_message("출력할 사진이 없습니다.", "info")
            return

        # 컬럼(compare layer)은 담긴 스냅샷들에 등장하는 비교 layer 의 합집합(등장 순서).
        compare_union: list[str] = []
        for m in selected:
            for r in m.results:
                if r.compare_layer not in compare_union:
                    compare_union.append(r.compare_layer)

        default_dir = str(self.settings.exports_path)
        Path(default_dir).mkdir(parents=True, exist_ok=True)
        default_name = self._safe_filename(f"{self.lot_index.lot_name}_compare") + ".xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Excel 저장 위치", str(Path(default_dir) / default_name),
            "Excel 파일 (*.xlsx)",
        )
        if not path:
            return

        # openpyxl 은 출력 시에만 필요 → 시작 비용을 줄이기 위해 지연 임포트.
        from app.export.excel_report import export_excel
        try:
            out = export_excel(
                path,
                lot_name=self.lot_index.lot_name,
                base_layer=self.top.base_layer(),
                compare_layers=compare_union or self.top.compare_layers(),
                tolerance=self.top.tolerance(),
                selected=selected,
                thumb_cache=self.thumb_cache,
                source_roots=[self.lot_index.lot_path],
                notes=self.session.notes_map() if self.session else None,
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
        # 최대화 상태를 기억하고, 창 크기는 normal(복원) 기하로 저장한다.
        self.settings.window_maximized = self.isMaximized()
        geo = self.normalGeometry()
        self.settings.window_geometry = f"{geo.x()},{geo.y()},{geo.width()},{geo.height()}"
        try:
            self.settings.sidebar_width = self.splitter.sizes()[0]
        except (AttributeError, IndexError):
            pass
        self._save_prefs()
        try:
            self.settings.save()
        except OSError:
            pass
        if self.session is not None:
            self.session.save()
        super().closeEvent(event)
