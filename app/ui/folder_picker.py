"""자재(LOT) 폴더 선택 다이얼로그 — 브레드크럼 + 한 단계 목록 + 사이드바.

성능: 현재 디렉터리의 하위 폴더 한 단계만 os.scandir 로 나열한다(트리·워처·재귀·셸 아이콘
없음 → 네트워크 드라이브에서도 즉시). 명확함: 고른 폴더가 자재/layer/wafer 중 무엇인지,
유효한지(layer·wafer 개수)를 하단 배너에 실시간 표시한다(scanner.classify_selection 을
백그라운드로 실행). layer/wafer 를 골라도 선택 시 상위 자재 폴더로 보정한다.

편의: 최근 폴더·즐겨찾기·드라이브 사이드바, 이름 타이핑 필터. 원본은 읽기만 한다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QDir,
    QObject,
    QRunnable,
    QStorageInfo,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app import scanner
from app.ui import theme

# 검증 배너 종류별 색(테마 팔레트 재사용).
_BANNER_COLORS = {
    "material": (theme.MATCH, "#10241b"),
    "layerwafer": (theme.NEON, "#101a24"),
    "too_high": (theme.WARN, "#241f10"),
    "unknown": (theme.TEXT_DIM, theme.BG_ELEV),
    "busy": (theme.TEXT_DIM, theme.BG_ELEV),
    "none": (theme.TEXT_DIM, theme.BG_ELEV),
}


def _subdir_count(path: Path) -> int:
    """path 바로 아래 폴더 수(싸게 os.scandir 1회)."""
    n = 0
    try:
        with os.scandir(path) as it:
            for e in it:
                if e.is_dir():
                    n += 1
    except OSError:
        return 0
    return n


def _first_subdir(path: Path) -> Optional[Path]:
    try:
        with os.scandir(path) as it:
            names = sorted(e.name for e in it if e.is_dir())
    except OSError:
        return None
    return path / names[0] if names else None


class _ValidateSignals(QObject):
    # token, kind, material_path, layer_count, wafer_count
    done = Signal(int, str, str, int, int)


class _ValidateWorker(QRunnable):
    """후보 폴더를 백그라운드로 판별한다(classify_selection + 개수 계산).

    UI 스레드를 막지 않도록 무거운 깊이 BFS 를 여기서 수행한다. 오래된 요청은 token 으로
    UI 에서 무시한다.
    """

    def __init__(self, token: int, path: str):
        super().__init__()
        self.token = token
        self.path = path
        self.signals = _ValidateSignals()

    @Slot()
    def run(self) -> None:
        kind, material = scanner.classify_selection(self.path)
        layers = wafers = 0
        try:
            if material is not None and kind in ("material", "layer", "wafer"):
                layers = _subdir_count(material)
                first = _first_subdir(material)
                if first is not None:
                    wafers = _subdir_count(first)
        except Exception:  # noqa: BLE001 - 개수는 부가 정보, 실패해도 판별은 전달
            layers = wafers = 0
        mat_str = str(material) if material is not None else ""
        self.signals.done.emit(self.token, kind, mat_str, layers, wafers)


class FolderPickerDialog(QDialog):
    """자재 폴더 선택기. `settings` 로 최근·즐겨찾기를 읽고 고정 토글 시 저장한다."""

    def __init__(self, settings, start_path: str, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("자재(LOT) 폴더 선택")
        self.setMinimumSize(860, 560)
        self.resize(980, 640)

        self._pool = QThreadPool.globalInstance()
        self._cur: Path = self._safe_dir(start_path)
        self._history: list[Path] = []
        self._candidate: Optional[Path] = None
        # 마지막 검증 결과 캐시(candidate 경로 기준).
        self._valid_for: Optional[Path] = None
        self._valid_kind: str = ""
        self._valid_material: str = ""
        self._token = 0

        self._build_ui()
        self._reload_sidebar()
        self._go_to(self._cur, push=False)

    # ----------------------------------------------------------- helpers
    @staticmethod
    def _safe_dir(path: str) -> Path:
        try:
            p = Path(path)
            if p.exists() and p.is_dir():
                return p
        except OSError:
            pass
        return Path.home()

    def _list_subdirs(self, path: Path) -> list[str]:
        """한 단계 하위 폴더 이름만 나열(숨김 제외, 이름순). 네트워크에서도 가볍다."""
        try:
            with os.scandir(path) as it:
                names = [e.name for e in it if e.is_dir() and not e.name.startswith(".")]
        except OSError:
            return []
        return sorted(names, key=str.lower)

    # ----------------------------------------------------------- UI build
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # 상단: 뒤로/위로 + 브레드크럼 + 경로 입력
        topbar = QHBoxLayout()
        topbar.setSpacing(6)
        self.btn_back = QPushButton("‹ 뒤로")
        self.btn_back.setFixedWidth(72)
        self.btn_back.clicked.connect(self._go_back)
        self.btn_up = QPushButton("↑ 위로")
        self.btn_up.setFixedWidth(72)
        self.btn_up.clicked.connect(self._go_up)
        self.btn_explorer = QPushButton("🗂 기본 탐색기")
        self.btn_explorer.setToolTip(
            "OS 기본 폴더 탐색기로 선택합니다.\n"
            "(네트워크 공유 등 트리에 아직 안 보이는 위치를 여기서 바로 고를 수 있습니다.)"
        )
        self.btn_explorer.clicked.connect(self._open_native_explorer)
        topbar.addWidget(self.btn_back)
        topbar.addWidget(self.btn_up)
        topbar.addWidget(self.btn_explorer)

        self._crumbs = QHBoxLayout()
        self._crumbs.setSpacing(2)
        crumb_host = QWidget()
        crumb_host.setLayout(self._crumbs)
        topbar.addWidget(crumb_host, 1)
        root.addLayout(topbar)

        self.ed_path = QLineEdit()
        self.ed_path.setPlaceholderText("경로를 붙여넣고 Enter — 예: \\\\server\\share\\LOT")
        self.ed_path.returnPressed.connect(self._on_path_entered)
        root.addWidget(self.ed_path)

        # 본문: 좌 사이드바 / 우 (필터 + 목록)
        body = QHBoxLayout()
        body.setSpacing(10)

        # 좌측: 폴더 구조 트리(지연 로딩) + 접이식 최근/즐겨찾기. 기본 탐색기처럼 탐색.
        self.sidebar = QTreeWidget()
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setFixedWidth(260)
        self.sidebar.setIndentation(12)  # 기본(~20)은 하위로 갈수록 여백 과다 → 축소
        self.sidebar.setRootIsDecorated(True)
        self.sidebar.itemClicked.connect(self._on_tree_clicked)
        self.sidebar.itemExpanded.connect(self._on_tree_expanded)
        body.addWidget(self.sidebar)

        right = QVBoxLayout()
        right.setSpacing(6)
        self.ed_filter = QLineEdit()
        self.ed_filter.setPlaceholderText("이 폴더 안에서 이름으로 거르기…")
        self.ed_filter.setClearButtonEnabled(True)
        self.ed_filter.textChanged.connect(self._apply_filter)
        right.addWidget(self.ed_filter)

        self.listw = QListWidget()
        self.listw.itemClicked.connect(self._on_item_clicked)
        self.listw.itemActivated.connect(self._on_item_activated)
        self.listw.itemDoubleClicked.connect(self._on_item_activated)
        right.addWidget(self.listw, 1)
        body.addLayout(right, 1)
        root.addLayout(body, 1)

        # 하단: 검증 배너 + ★ 고정 + 취소/선택
        self.banner = QLabel("폴더를 고르면 자재 여부를 여기서 확인합니다.")
        self.banner.setWordWrap(True)
        self.banner.setMinimumHeight(40)
        self.banner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.banner.setContentsMargins(10, 6, 10, 6)
        self._set_banner("none", "폴더를 고르면 자재 여부를 여기서 확인합니다.")
        root.addWidget(self.banner)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.btn_pin = QPushButton("☆ 즐겨찾기")
        self.btn_pin.setFixedWidth(120)
        self.btn_pin.clicked.connect(self._toggle_favorite)
        bottom.addWidget(self.btn_pin)
        bottom.addStretch(1)
        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton("이 폴더 선택")
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.accept)
        bottom.addWidget(btn_cancel)
        bottom.addWidget(self.btn_ok)
        root.addLayout(bottom)

        # 검증 디바운스 타이머
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self._run_validation)

    # ----------------------------------------------------------- sidebar (폴더 트리)
    _LOADED = Qt.UserRole + 1  # 지연 로딩 완료 플래그

    def _make_dir_node(self, parent, label: str, path: str):
        """지연 확장 폴더 노드(펼치면 그때 한 단계만 os.scandir). 더미 자식으로 화살표 표시."""
        node = QTreeWidgetItem(parent, [label])
        node.setData(0, Qt.UserRole, path)
        node.setData(0, self._LOADED, False)
        node.setToolTip(0, path)
        QTreeWidgetItem(node, ["…"])  # placeholder → 펼침 화살표
        return node

    def _make_group_node(self, label: str):
        """접이식 그룹 헤더(경로 없음). 자식은 폴더 노드."""
        node = QTreeWidgetItem(self.sidebar, [label])
        node.setData(0, Qt.UserRole, None)
        node.setData(0, self._LOADED, True)  # 그룹은 지연 로딩 대상 아님
        node.setFlags(Qt.ItemIsEnabled)
        return node

    @staticmethod
    def _unc_anchor(s: str) -> str:
        """경로의 루트(anchor). UNC(\\\\server\\share)는 플랫폼과 무관하게 공유 루트를 돌려준다."""
        s = str(s)
        if s.startswith("\\\\") or s.startswith("//"):
            sep = "\\" if s[0] == "\\" else "/"
            parts = s.replace("/", "\\").split("\\")  # ['', '', server, share, ...]
            if len(parts) >= 4 and parts[2] and parts[3]:
                return f"{sep}{sep}{parts[2]}{sep}{parts[3]}{sep}"
            return s
        try:
            return Path(s).anchor
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def _drive_label(p: str) -> str:
        """드라이브 표시명 — 네트워크 드라이브는 볼륨 이름·UNC 대상까지 함께 보여준다."""
        drive = p.rstrip("/\\") or p
        name = ""
        dev = ""
        try:
            si = QStorageInfo(p)
            name = si.name() or ""
            raw = si.device()
            try:
                dev = bytes(raw).decode("utf-8", "ignore")
            except Exception:  # noqa: BLE001
                dev = str(raw)
        except Exception:  # noqa: BLE001
            pass
        is_net = dev.startswith("\\\\") or dev.startswith("//")
        extra = []
        if name:
            extra.append(name)
        if is_net and dev:
            extra.append(dev)
        label = drive + (f"  ({' · '.join(extra)})" if extra else "")
        return ("🌐 " if is_net else "💾 ") + label

    def _ensure_root_for(self, path) -> None:
        """path 를 포함하는 최상위 루트가 없으면(예: UNC 네트워크 폴더) 그 루트를 추가한다."""
        anchor = self._unc_anchor(path)
        if not anchor:
            return
        na = anchor.rstrip("/\\")
        for rp, _ in self._root_nodes:
            if str(rp).rstrip("/\\") == na:
                return
        is_net = anchor.startswith("\\\\") or anchor.startswith("//")
        label = ("🌐 " + anchor) if is_net else self._drive_label(anchor)
        node = self._make_dir_node(self.sidebar.invisibleRootItem(), label, anchor)
        self._root_nodes.append((anchor, node))

    def _open_native_explorer(self) -> None:
        """OS 기본 폴더 선택 대화상자로 폴더를 고른다(트리에 안 보이는 네트워크 공유 등)."""
        start = str(self._cur) if self._cur.exists() else str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "폴더 선택 (기본 탐색기)", start)
        if path:
            self._go_to(self._safe_dir(path))

    def _pin_scan_roots(self, search_roots: list[str]) -> None:
        """각 루트 바로 아래에 scan_root_name 폴더가 있으면 최상위 '📌' 고정 노드로 추가."""
        name = (getattr(self.settings, "scan_root_name", "") or "").strip()
        if not name:
            return
        root = self.sidebar.invisibleRootItem()
        seen: set[str] = set()
        for r in search_roots:
            try:
                p = Path(r) / name
                if not p.is_dir():
                    continue
            except OSError:
                continue  # 연결 끊긴 드라이브/네트워크 → 스킵
            key = str(p).rstrip("/\\")
            if key in seen:
                continue
            seen.add(key)
            disp = r.rstrip("/\\") or r
            node = self._make_dir_node(root, f"📌 {name}  ({disp})", str(p))
            self._root_nodes.append((str(p), node))

    def _reload_sidebar(self) -> None:
        self.sidebar.clear()
        self._root_nodes = []  # (path, node) — 현재 위치 트리 동기화용 루트
        root = self.sidebar.invisibleRootItem()
        favs = [f for f in getattr(self.settings, "favorite_folders", []) if Path(f).exists()]
        recents = [f for f in getattr(self.settings, "recent_folders", []) if Path(f).exists()]
        # 검색 대상 루트(홈·드라이브·현재/즐겨찾기/최근의 네트워크 앵커).
        search_roots = [str(Path.home())] + [d.absoluteFilePath() for d in QDir.drives()]
        for cand in [str(self._cur), *favs, *recents]:
            a = self._unc_anchor(cand)
            if a and a not in search_roots:
                search_roots.append(a)
        # 1) 스캔 데이터 폴더(scan_root_name)가 있는 위치를 최상위에 📌 고정.
        self._pin_scan_roots(search_roots)
        # 2) 폴더 트리 위주: 홈 + 드라이브를 최상위 폴더 노드로 노출(탐색기처럼).
        home = self._make_dir_node(root, "🏠 홈", str(Path.home()))
        self._root_nodes.append((str(Path.home()), home))
        for d in QDir.drives():
            p = d.absoluteFilePath()
            self._root_nodes.append((p, self._make_dir_node(root, self._drive_label(p), p)))
        # 3) 네트워크(UNC) 위치는 드라이브 목록에 안 나오므로 앵커 루트를 추가.
        for cand in [str(self._cur), *favs, *recents]:
            self._ensure_root_for(cand)
        # 즐겨찾기·최근은 맨 아래 접이식 소형 그룹(기본 접힘).
        if favs:
            grp = self._make_group_node("★ 즐겨찾기")
            for f in favs:
                self._make_dir_node(grp, "★ " + (Path(f).name or f), f)
            grp.setExpanded(False)
        if recents:
            grp = self._make_group_node("↻ 최근")
            for f in recents:
                self._make_dir_node(grp, "📁 " + (Path(f).name or f), f)
            grp.setExpanded(False)
        self._reveal_in_tree(self._cur)

    def _on_tree_expanded(self, node: QTreeWidgetItem) -> None:
        if node.data(0, self._LOADED):
            return
        path = node.data(0, Qt.UserRole)
        node.takeChildren()  # 더미 제거
        if path:
            for name in self._list_subdirs(Path(path)):
                self._make_dir_node(node, "📁 " + name, str(Path(path) / name))
        node.setData(0, self._LOADED, True)

    def _reveal_in_tree(self, path: Path) -> None:
        """현재 경로를 포함하는 루트를 찾아 세그먼트마다 지연 확장하며 그 노드를 선택·스크롤."""
        roots = getattr(self, "_root_nodes", None)
        if roots is None:
            return
        # 네트워크(UNC) 등 기존 루트에 없는 위치면 루트를 즉석에서 추가.
        self._ensure_root_for(path)
        roots = self._root_nodes
        target = Path(path)
        best = None  # 가장 깊은(구체적인) 접두 루트
        for rp, node in roots:
            rpp = Path(rp)
            if target == rpp or rpp in target.parents:
                if best is None or len(str(rpp)) > len(str(Path(best[0]))):
                    best = (rp, node)
        if best is None:
            return
        rp, node = best
        node.setExpanded(True)  # itemExpanded → 지연 로딩(동기)
        try:
            rel = target.relative_to(Path(rp))
        except ValueError:
            rel = Path()
        cur = node
        for part in rel.parts:
            child = self._find_child_by_name(cur, part)
            if child is None:
                break
            cur = child
            cur.setExpanded(True)
        self.sidebar.setCurrentItem(cur)
        self.sidebar.scrollToItem(cur)

    @staticmethod
    def _find_child_by_name(parent: QTreeWidgetItem, name: str) -> Optional[QTreeWidgetItem]:
        for i in range(parent.childCount()):
            ch = parent.child(i)
            p = ch.data(0, Qt.UserRole)
            if p and Path(p).name == name:
                return ch
        return None

    def _on_tree_clicked(self, node: QTreeWidgetItem, _col: int = 0) -> None:
        path = node.data(0, Qt.UserRole)
        if path:
            self._go_to(self._safe_dir(path))

    # ----------------------------------------------------------- navigation
    def _go_to(self, path: Path, push: bool = True) -> None:
        path = self._safe_dir(str(path))
        if push and path != self._cur:
            self._history.append(self._cur)
        self._cur = path
        self.ed_path.setText(str(path))
        self.ed_filter.clear()
        self._populate_list()
        self._rebuild_crumbs()
        self.btn_back.setEnabled(bool(self._history))
        self.btn_up.setEnabled(path.parent != path)
        self._reveal_in_tree(path)  # 좌측 폴더 트리를 현재 위치로 확장·강조
        # 현재 폴더 자체를 후보로 삼아 자동 검증(자재로 바로 들어오면 즉시 확인).
        self._set_candidate(path)

    def _go_up(self) -> None:
        if self._cur.parent != self._cur:
            self._go_to(self._cur.parent)

    def _go_back(self) -> None:
        if self._history:
            prev = self._history.pop()
            self._go_to(prev, push=False)

    def _on_path_entered(self) -> None:
        text = self.ed_path.text().strip()
        if not text:
            return
        p = Path(text)
        if p.exists() and p.is_dir():
            self._go_to(p)
        else:
            self._set_banner("too_high", f"경로를 찾을 수 없습니다: {text}")

    def _rebuild_crumbs(self) -> None:
        while self._crumbs.count():
            w = self._crumbs.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        parts = list(self._cur.parts)
        acc = Path(parts[0]) if parts else self._cur
        for i, part in enumerate(parts):
            if i > 0:
                acc = acc / part
            label = part if part not in ("/", "\\") else "/"
            btn = QPushButton(label)
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ border: none; padding: 2px 6px; color: {theme.NEON}; }}"
                f"QPushButton:hover {{ color: {theme.TEXT}; text-decoration: underline; }}"
            )
            target = acc
            btn.clicked.connect(lambda _=False, t=target: self._go_to(t))
            self._crumbs.addWidget(btn)
            if i < len(parts) - 1:
                sep = QLabel("›")
                sep.setStyleSheet(f"color: {theme.TEXT_DIM};")
                self._crumbs.addWidget(sep)
        self._crumbs.addStretch(1)

    # ----------------------------------------------------------- list
    def _populate_list(self) -> None:
        self.listw.clear()
        for name in self._list_subdirs(self._cur):
            it = QListWidgetItem("📁 " + name)
            it.setData(Qt.UserRole, name)
            self.listw.addItem(it)
        if self.listw.count() == 0:
            it = QListWidgetItem("(하위 폴더 없음 — 이 폴더가 자재일 수 있습니다)")
            it.setFlags(Qt.NoItemFlags)
            it.setForeground(Qt.gray)
            self.listw.addItem(it)

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            name = it.data(Qt.UserRole)
            if name is None:  # 안내/빈 항목은 그대로 둔다
                continue
            it.setHidden(bool(needle) and needle not in name.lower())

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.UserRole)
        if name is None:
            return
        self._set_candidate(self._cur / name)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.UserRole)
        if name is None:
            return
        self._go_to(self._cur / name)

    # ----------------------------------------------------------- validation
    def _set_candidate(self, path: Path) -> None:
        self._candidate = path
        self._update_pin_button()
        self._set_banner("busy", f"‘{path.name or path}’ 확인 중…")
        self._debounce.start()

    def _run_validation(self) -> None:
        if self._candidate is None:
            return
        self._token += 1
        worker = _ValidateWorker(self._token, str(self._candidate))
        worker.signals.done.connect(self._on_validated)
        self._pool.start(worker)

    @Slot(int, str, str, int, int)
    def _on_validated(
        self, token: int, kind: str, material: str, layers: int, wafers: int
    ) -> None:
        if token != self._token or self._candidate is None:
            return  # 오래된 결과 무시
        self._valid_for = self._candidate
        self._valid_kind = kind
        self._valid_material = material
        name = self._candidate.name or str(self._candidate)
        if kind == "material":
            self._set_banner(
                "material",
                f"✓ 자재(LOT) 폴더 · layer {layers}개 · wafer {wafers}개",
            )
            self.btn_ok.setEnabled(True)
        elif kind in ("layer", "wafer"):
            mat_name = Path(material).name if material else "?"
            self._set_banner(
                "layerwafer",
                f"{kind} 폴더 · 선택 시 자재 ‘{mat_name}’ 로 이동합니다"
                f" (layer {layers}개 · wafer {wafers}개)",
            )
            self.btn_ok.setEnabled(True)
        elif kind == "too_high":
            self._set_banner(
                "too_high",
                f"‘{name}’ 는 상위(device) 폴더입니다 · 자재 폴더로 들어가세요",
            )
            self.btn_ok.setEnabled(False)
        else:  # unknown
            self._set_banner(
                "unknown",
                f"‘{name}’ 에서 이미지를 찾지 못함 · 그래도 선택할 수 있습니다",
            )
            self.btn_ok.setEnabled(True)

    def _set_banner(self, kind: str, text: str) -> None:
        fg, bg = _BANNER_COLORS.get(kind, _BANNER_COLORS["none"])
        self.banner.setText(text)
        self.banner.setStyleSheet(
            f"QLabel {{ background-color: {bg}; color: {fg};"
            f" border: 1px solid {fg}; border-radius: 6px; padding: 8px 10px; }}"
        )

    # ----------------------------------------------------------- favorites
    def _update_pin_button(self) -> None:
        target = self._candidate or self._cur
        favs = list(getattr(self.settings, "favorite_folders", []))
        if str(target) in favs:
            self.btn_pin.setText("★ 고정됨")
        else:
            self.btn_pin.setText("☆ 즐겨찾기")

    def _toggle_favorite(self) -> None:
        target = str(self._candidate or self._cur)
        favs = list(getattr(self.settings, "favorite_folders", []))
        if target in favs:
            favs.remove(target)
        else:
            favs.insert(0, target)
        self.settings.favorite_folders = favs[:10]
        try:
            self.settings.save()
        except Exception:  # noqa: BLE001 - 저장 실패해도 세션 내 반영은 유지
            pass
        self._reload_sidebar()
        self._update_pin_button()

    # ----------------------------------------------------------- result
    def selected_path(self) -> str:
        """선택 확정 시 반환할 자재 경로(보정 포함). 취소/부적합이면 빈 문자열."""
        target = self._candidate or self._cur
        # 마지막 검증이 현재 후보에 대한 것이면 캐시 사용, 아니면 동기 재판정.
        if self._valid_for == target and self._valid_kind:
            kind, material = self._valid_kind, self._valid_material
        else:
            k, m = scanner.classify_selection(target)
            kind, material = k, (str(m) if m is not None else "")
        if kind == "material":
            return str(target)
        if kind in ("layer", "wafer") and material:
            return material
        if kind == "unknown":
            return str(target)
        return ""  # too_high / none
