"""다크 + 파란 네온 테마 (문서 Section 9).

어두운 바탕, 파란 네온 강조, 깔끔하고 복잡하지 않은 화면.
버튼은 hover/pressed 시 시각적 변화가 있어야 한다(QSS state 로 처리).
"""

from __future__ import annotations

import colorsys
import re

# ---- UI 글자 크기(전역 스케일) ----
# 설정의 ui_font_size 값 → 배율. 보통 기준 크게=+30%.
FONT_SCALES = {"normal": 1.0, "large": 1.3}
# 인라인 스타일(px 직접 지정) 위젯이 참조하는 현재 배율. apply_theme 에서 갱신.
FONT_SCALE = 1.0


def scale_for(key: str | None) -> float:
    """설정 값(normal/large) → 글자 크기 배율."""
    return FONT_SCALES.get(key or "normal", 1.0)


def fpx(base: int) -> int:
    """현재 배율을 반영한 글자 크기(px). 인라인 스타일용."""
    return max(1, round(base * FONT_SCALE))


# 팔레트: 저채도 슬레이트 다크 테마(부드러운 대비, 넓은 여백 지향)
BG = "#11151c"
BG_PANEL = "#171c26"
BG_ELEV = "#1f2632"
NEON = "#5b8db8"        # 강조: 저채도 슬레이트블루
NEON_DIM = "#456b8f"
NEON_SOFT = "#2c343f"   # 저채도 경계선
TEXT = "#dde3ec"
TEXT_DIM = "#8b95a4"
MATCH = "#6ec59a"
NOMATCH = "#d98a8a"
BASE_GLOW = "#7fa8cc"
WARN = "#d8b773"        # "허용오차 초과" 등 진단 강조
OVERLAY_BG = "rgba(17, 21, 28, 0.62)"  # 이미지 위 배지 반투명 배경

STYLESHEET = f"""
* {{
    font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
    color: {TEXT};
}}
QWidget#root, QMainWindow {{
    background-color: {BG};
}}
QFrame#panel {{
    background-color: {BG_PANEL};
    border: 1px solid {NEON_SOFT};
    border-radius: 14px;
}}
QFrame#sidebar {{
    background-color: {BG_PANEL};
    border: 1px solid {NEON_SOFT};
    border-radius: 14px;
}}
QLabel {{
    color: {TEXT};
    background: transparent;
}}
QLabel#dim {{ color: {TEXT_DIM}; }}
QLabel#title {{ font-size: 16px; font-weight: 700; color: {TEXT}; }}
QLabel#meta {{ font-size: 13px; color: {TEXT}; }}
QLabel#lotName {{ font-size: 13px; font-weight: 600; color: {BASE_GLOW}; }}
QLabel#section {{ font-size: 11px; font-weight: 700; color: {TEXT_DIM};
    letter-spacing: 1px; }}
/* 이미지 위 Layer 배지 + 진단 라벨 */
QLabel#layerBadge {{
    background-color: {OVERLAY_BG}; color: {TEXT};
    border-radius: 8px; padding: 3px 10px; font-weight: 700; font-size: 13px;
}}
QLabel#layerBadgeBase {{
    background-color: {OVERLAY_BG}; color: {BASE_GLOW};
    border-radius: 8px; padding: 3px 10px; font-weight: 700; font-size: 13px;
}}
QLabel#diag {{ color: {TEXT_DIM}; font-size: 10px; }}
QLabel#diagWarn {{ color: {WARN}; font-size: 10px; }}

/* ---- 버튼 ---- */
QPushButton {{
    background-color: {BG_ELEV};
    color: {TEXT};
    border: 1px solid {NEON_SOFT};
    border-radius: 10px;
    padding: 8px 16px;
    font-size: 12px;
}}
QPushButton:hover {{
    background-color: {NEON_SOFT};
    border: 1px solid {NEON};
    color: {TEXT};
}}
QPushButton:pressed {{
    background-color: {NEON_DIM};
    border: 1px solid {NEON};
}}
QPushButton:disabled {{
    color: {TEXT_DIM};
    border: 1px solid #232a33;
    background-color: #161b23;
}}
QPushButton#primary {{
    background-color: {NEON_DIM};
    border: 1px solid {NEON};
    font-weight: 700;
    color: {TEXT};
}}
QPushButton#primary:hover {{ background-color: {NEON}; color: {TEXT}; }}
QPushButton#primary:pressed {{ background-color: {NEON_DIM}; }}
/* 컴팩트 버튼(전체/해제·설정 등) */
QPushButton#mini {{
    padding: 3px 10px;
    font-size: 11px;
    border-radius: 8px;
}}
/* 토글(checkable) mini 버튼이 켜지면 네온 배경으로 확실히 구분 */
QPushButton#mini:checked {{
    background-color: {NEON_DIM};
    border: 1px solid {NEON};
    color: {TEXT};
    font-weight: 700;
}}
QPushButton#mini:checked:hover {{ background-color: {NEON}; }}
/* 확대 화면 줌 −/＋ 버튼. 버튼 크기는 그대로 두고 글자만 키운다 */
QPushButton#zoomGlyph {{
    font-size: 20px;
    font-weight: 700;
    padding: 2px 0;
}}

/* 스크롤 영역은 기본 흰 배경 대신 투명(뒤 패널이 비치게) */
QScrollArea {{ background: transparent; border: none; }}

/* ---- 입력(콤보/스핀/라인) ---- */
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background-color: {BG_ELEV};
    border: 1px solid {NEON_SOFT};
    border-radius: 8px;
    padding: 6px 10px;
    min-height: 22px;
    color: {TEXT};
    selection-background-color: {NEON_DIM};
}}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {{
    border: 1px solid {NEON};
}}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
    border: 1px solid {NEON};
    background-color: {BG_PANEL};
}}
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {TEXT_DIM};
    background-color: #161b23;
}}

/* 콤보 드롭다운 버튼 (화살표 이미지는 apply_theme 에서 주입) */
QComboBox::drop-down {{ width: 24px; border: none; }}
QComboBox QAbstractItemView {{
    background-color: {BG_ELEV};
    border: 1px solid {NEON};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {NEON_DIM};
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    min-height: 26px; padding: 3px 8px; border-radius: 6px;
}}
QComboBox QAbstractItemView::item:hover {{ background: {NEON_SOFT}; }}

/* 스핀박스 ↑↓ 버튼 + 화살표 */
QAbstractSpinBox {{ padding-right: 22px; }}
/* 버튼 없는 입력(허용오차)은 일반 패딩 */
QDoubleSpinBox#tol {{ padding-right: 10px; }}
QDoubleSpinBox#tol::up-button, QDoubleSpinBox#tol::down-button {{ width: 0; border: none; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    subcontrol-origin: border;
    width: 20px;
    background-color: {BG_ELEV};
    border-left: 1px solid {NEON_SOFT};
}}
QAbstractSpinBox::up-button {{
    subcontrol-position: top right;
    border-top-right-radius: 8px;
}}
QAbstractSpinBox::down-button {{
    subcontrol-position: bottom right;
    border-bottom-right-radius: 8px;
    border-top: 1px solid {NEON_SOFT};
}}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{
    background-color: {NEON_SOFT};
}}
QAbstractSpinBox::up-button:pressed, QAbstractSpinBox::down-button:pressed {{
    background-color: {NEON_DIM};
}}
/* 스핀박스 화살표 이미지는 apply_theme 에서 주입 */

/* ---- 체크박스(비교 layer 선택) ---- */
QCheckBox {{ spacing: 6px; padding: 4px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {NEON_SOFT};
    border-radius: 5px;
    background: {BG_ELEV};
}}
QCheckBox::indicator:hover {{ border: 1px solid {NEON}; }}
QCheckBox::indicator:checked {{
    background: {NEON};
    border: 1px solid {NEON_DIM};
}}

/* ---- 다이얼로그 ---- */
QDialog {{ background-color: {BG}; }}

/* ---- 리스트(출력 선택) ---- */
QListWidget {{
    background-color: {BG_ELEV};
    border: 1px solid {NEON_SOFT};
    border-radius: 10px;
    outline: none;
}}
QListWidget::item {{ padding: 10px; border-radius: 8px; min-height: 30px; }}
QListWidget::item:hover {{ background: {NEON_SOFT}; }}
QListWidget::item:selected {{ background: {NEON_DIM}; color: {TEXT}; }}

/* ---- 우클릭/드롭다운 메뉴: 어두운 테마 통일(흰 배경 방지) ---- */
QMenu {{
    background-color: {BG_ELEV};
    color: {TEXT};
    border: 1px solid {NEON_SOFT};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 18px; border-radius: 6px; background: transparent;
}}
QMenu::item:selected {{ background: {NEON_DIM}; color: {TEXT}; }}
QMenu::item:disabled {{ color: {TEXT_DIM}; }}
QMenu::separator {{ height: 1px; background: {NEON_SOFT}; margin: 4px 8px; }}

/* ---- 아이템 뷰(트리/리스트/테이블): 어두운 테마 통일(흰 배경 방지) ---- */
QTreeView, QListView, QTableView, QColumnView {{
    background-color: {BG_ELEV};
    alternate-background-color: {BG_ELEV};
    color: {TEXT};
    border: 1px solid {NEON_SOFT};
    border-radius: 8px;
    outline: none;
}}
QTreeView::item, QListView::item, QTableView::item {{
    padding: 3px 6px; border-radius: 6px;
}}
QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {{
    background: {NEON_SOFT};
}}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{
    background: {NEON_DIM}; color: {TEXT};
}}
QTreeView::branch {{ background: transparent; }}
QHeaderView::section {{
    background-color: {BG_PANEL};
    color: {TEXT_DIM};
    border: none;
    border-bottom: 1px solid {NEON_SOFT};
    padding: 4px 6px;
}}

/* ---- 스플리터 손잡이(넓고 차분하게) ---- */
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 10px; }}

/* ---- 스크롤바 ---- */
QScrollBar:horizontal, QScrollBar:vertical {{
    background: transparent; border: none;
}}
QScrollBar:horizontal {{ height: 10px; }}
QScrollBar:vertical {{ width: 10px; }}
QScrollBar::handle {{
    background: {NEON_SOFT}; border-radius: 5px; min-width: 30px; min-height: 30px;
}}
QScrollBar::handle:hover {{ background: {NEON_DIM}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QProgressBar {{
    background-color: {BG_ELEV};
    border: 1px solid {NEON_SOFT};
    border-radius: 8px;
    text-align: center;
    height: 16px;
}}
QProgressBar::chunk {{
    background-color: {NEON_DIM};
    border-radius: 7px;
}}
QToolTip {{
    background-color: {BG_ELEV};
    color: {TEXT};
    border: 1px solid {NEON_SOFT};
    border-radius: 6px;
    padding: 5px;
}}
"""


def _make_arrow(direction: str, color: str, size: int = 12) -> str:
    """삼각형 화살표 PNG 를 생성하고 파일 경로(posix)를 반환한다.

    QSS 의 border-삼각형 트릭은 Qt 버전/플랫폼에 따라 깨지므로, 깔끔한 화살표를
    런타임에 그려 이미지로 주입한다(에셋 파일 불필요).
    """
    import tempfile
    from pathlib import Path

    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QColor, QPainter, QPixmap, QPolygon

    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    m = 2  # 여백
    if direction == "down":
        pts = [QPoint(m, m + 1), QPoint(size - m, m + 1), QPoint(size // 2, size - m)]
    else:  # up
        pts = [QPoint(m, size - m - 1), QPoint(size - m, size - m - 1), QPoint(size // 2, m)]
    p.drawPolygon(QPolygon(pts))
    p.end()

    out_dir = Path(tempfile.gettempdir()) / "defect_tracker_theme"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = color.lstrip("#")
    path = out_dir / f"arrow_{direction}_{safe}_{size}.png"
    pm.save(str(path), "PNG")
    return path.as_posix()


_FONT_RE = re.compile(r"font-size:\s*(\d+)px")
_ORIG_PT: float | None = None


def _scaled_sheet(scale: float) -> str:
    """스타일시트의 모든 font-size(px)를 배율만큼 키운다.

    보통(1.0)은 현재와 완전히 동일. 크게일 때는 명시 크기 없는 위젯(콤보/입력/체크박스 등)의
    기본 글자 크기도 커지도록 `*` 규칙에 기본 font-size 를 함께 주입한다(구체 선택자가 우선).
    """
    if scale == 1.0:
        return STYLESHEET
    sheet = _FONT_RE.sub(
        lambda m: f"font-size: {max(8, round(int(m.group(1)) * scale))}px", STYLESHEET
    )
    return sheet + f"\n* {{ font-size: {round(12 * scale)}px; }}\n"


def apply_theme(app, scale: float = 1.0) -> None:
    global FONT_SCALE, _ORIG_PT
    FONT_SCALE = scale
    # 앱 기본 폰트 크기도 배율만큼(명시 크기 없는 네이티브 요소·메뉴 등 대응). 원본을 한 번만
    # 기억해 반복 적용해도 배율이 누적되지 않게 한다.
    if _ORIG_PT is None:
        f0 = app.font()
        _ORIG_PT = f0.pointSizeF() if f0.pointSizeF() > 0 else 9.0
    f = app.font()
    f.setPointSizeF(_ORIG_PT * scale)
    app.setFont(f)

    # 콤보/스핀 화살표를 런타임 이미지로 주입(테마색 삼각형).
    # 주의: `QComboBox:hover::down-arrow` 규칙은 Qt 에서 화살표가 두 번 그려지는
    # QSS 버그를 유발하므로 사용하지 않는다(화살표 색은 고정 TEXT_DIM 으로 충분).
    down = _make_arrow("down", TEXT_DIM)
    up = _make_arrow("up", TEXT_DIM)
    arrow_qss = f"""
QComboBox::down-arrow {{ image: url("{down}"); width: 12px; height: 12px; }}
QAbstractSpinBox::down-arrow {{ image: url("{down}"); width: 9px; height: 9px; }}
QAbstractSpinBox::up-arrow {{ image: url("{up}"); width: 9px; height: 9px; }}
"""
    app.setStyleSheet(_scaled_sheet(scale) + arrow_qss)


# ======================================================================
# Fluent 재설계 토큰
# ======================================================================
# 단일 출처: design_handoff_fluent_redesign/02-design-rules.md (+ REVIEW-01 확정값).
# 화면에서 색·간격·duration 을 새로 만들지 말고 여기서만 가져다 쓴다.
#
# 위쪽 레거시 팔레트/STYLESHEET 는 화면 이행이 끝날 때까지 함께 남는다.
# 이 절은 Qt 를 import 하지 않는 순수 값·계산이라 단위 테스트에서 바로 검증된다.

# ---- 색: 표면 (02 §1.1 라이트 / §1.2 다크) ----
FLUENT_LIGHT: dict[str, str] = {
    "win": "#F3F3F3",
    "layer": "#F9F9F9",
    "card": "#FFFFFF",
    "cardHover": "#F7F7F7",
    "cardBorder": "rgba(0,0,0,.058)",
    "cardBorderH": "rgba(0,0,0,.16)",
    "txt1": "rgba(0,0,0,.90)",
    "txt2": "rgba(0,0,0,.61)",
    "txt3": "rgba(0,0,0,.62)",
    "txtDeco": "rgba(0,0,0,.38)",
    "divider": "rgba(0,0,0,.08)",
    "ctrlBg": "rgba(255,255,255,.70)",
    "ctrlBgH": "rgba(249,249,249,.50)",
    "ctrlBgP": "rgba(249,249,249,.30)",
    "ctrlBd": "rgba(0,0,0,.07)",
    "ctrlBdBottom": "rgba(0,0,0,.16)",
    "subtle": "rgba(0,0,0,.03)",
    "subtleH": "rgba(0,0,0,.037)",
}

FLUENT_DARK: dict[str, str] = {
    "win": "#202020",
    "layer": "#272727",
    "card": "#2B2B2B",
    "cardHover": "#313131",
    "cardBorder": "rgba(255,255,255,.07)",
    "cardBorderH": "rgba(255,255,255,.16)",
    "txt1": "rgba(255,255,255,.94)",
    "txt2": "rgba(255,255,255,.72)",
    "txt3": "rgba(255,255,255,.72)",
    "txtDeco": "rgba(255,255,255,.42)",
    "divider": "rgba(255,255,255,.09)",
    "ctrlBg": "rgba(255,255,255,.06)",
    "ctrlBgH": "rgba(255,255,255,.09)",
    "ctrlBgP": "rgba(255,255,255,.04)",
    "ctrlBd": "rgba(255,255,255,.09)",
    "ctrlBdBottom": "rgba(255,255,255,.09)",
    "subtle": "rgba(255,255,255,.04)",
    "subtleH": "rgba(255,255,255,.06)",
}

# ---- 색: accent 3역할 분리 (02 §1.3, 게이트 2) ----
# 채움(fill) 위의 글자는 반드시 onAccent, 글자·글리프로 쓰는 accent 는 반드시 text.
ACCENT_BASE = "#0078D4"

ACCENT_LIGHT: dict[str, str] = {
    "fill": "#0078D4",
    "hover": "#106EBE",
    "pressed": "#005A9E",
    "onAccent": "#FFFFFF",
    "text": "#005A9E",
    "tint": "rgba(0,120,212,.09)",
}

ACCENT_DARK: dict[str, str] = {
    "fill": "#4CC2FF",
    "hover": "#4CC2FF",
    "pressed": "#3AA9E0",
    "onAccent": "#16140F",  # 다크에서 채움 위 흰 글자는 2.01:1 이므로 near-black 을 쓴다
    "text": "#4CC2FF",
    "tint": "rgba(76,194,255,.13)",
}

# ---- 색: 상태 (02 §1.4) ----
STATUS_LIGHT: dict[str, str] = {
    "pass": "#0F7B0F",
    "passBg": "#DFF6DD",
    "warn": "#9D5D00",
    "warnBg": "#FFF4CE",
    "danger": "#C42B1E",
    "dangerBg": "#FDE7E9",
    "info": ACCENT_LIGHT["text"],
    "infoBg": "#F4F9FE",
}

STATUS_DARK: dict[str, str] = {
    "pass": "#6CCB70",
    "passBg": "rgba(15,123,15,.18)",
    "warn": "#FFD68A",
    "warnBg": "rgba(157,93,0,.20)",
    "danger": "#FF99A4",
    "dangerBg": "rgba(196,43,30,.20)",
    "info": ACCENT_DARK["text"],
    "infoBg": "rgba(76,194,255,.14)",
}

# 사진 바탕은 두 테마 모두 순검정. 예외 없음(명암 판독에 바탕색이 섞이면 안 된다).
PHOTO_BG = "#000000"

# ---- 형태 (02 §2) ----
RADIUS: dict[str, int] = {"control": 5, "card": 7, "sheet": 8, "chip": 13}

SPACING: dict[str, int] = {
    "pageV": 22,
    "pageH": 28,
    "cardMin": 14,
    "cardMax": 18,
    "gapXs": 6,
    "gapS": 8,
    "gapM": 12,
    "gapL": 16,
}

# 글자 크기·굵기·자간. 크기는 FONT_SCALES 배율을 곱해 쓴다(fluent_font_px 참고).
TYPO: dict[str, dict[str, float]] = {
    "title": {"size": 26.0, "weight": 600, "tracking": -0.5},
    "section": {"size": 17.0, "weight": 600, "tracking": 0.0},
    "body": {"size": 13.0, "weight": 400, "tracking": 0.0},
    "bodySm": {"size": 12.5, "weight": 400, "tracking": 0.0},
    "caption": {"size": 12.0, "weight": 400, "tracking": 0.0},
    "captionSm": {"size": 11.5, "weight": 400, "tracking": 0.0},
    "label": {"size": 11.0, "weight": 600, "tracking": 0.0},
}

# 높이는 고정값이 아니라 하한(min-height)으로 쓴다. 글자 크기 large 에서는 아래 표 값으로
# 올린다(곱셈이 아니라 표로 고정). radius·gap·패딩은 두 배율에서 동일하다(게이트).
HEIGHTS: dict[str, dict[str, int]] = {
    "control": {"normal": 32, "large": 40},
    "primary": {"normal": 36, "large": 44},
    "navItem": {"normal": 40, "large": 48},
    "tableRow": {"normal": 21, "large": 27},
    "specRow": {"normal": 60, "large": 72},
    "titleBar": {"normal": 48, "large": 48},
    "icon": {"normal": 16, "large": 20},
}

# 판독대 한 칸의 최소 높이(게이트 4: layer 12개를 켜도 사진이 읽혀야 한다).
WELL_MIN_PX = 224

# ---- 모션 (02 §3) ----
# (지속시간 ms, Qt easing curve 이름). CSS cubic-bezier 대응은 02 §3 번역표를 따른다.
MOTION: dict[str, tuple[int, str]] = {
    "control": (120, "Linear"),
    "enter": (250, "OutQuint"),
    "exit": (150, "InQuart"),
    "navPill": (300, "OutQuart"),
    "flyoutIn": (187, "OutQuint"),
    "flyoutOut": (120, "InQuart"),
    "scrim": (200, "Linear"),
    "sheet": (250, "OutQuint"),
    "infoBarIn": (200, "OutQuint"),
    "photoSwap": (220, "OutQuint"),
    "rowExpand": (250, "OutQuint"),
    "rowCollapse": (150, "InQuart"),
    "spinner": (900, "Linear"),
    "zoom": (250, "OutQuint"),
    "themeSwap": (280, "Linear"),
}

# InfoBar 자동 소멸(ms). qfluentwidgets 기본값 1000 은 너무 짧다.
INFOBAR_DURATION_MS = 3400
# 툴팁 지연(ms).
TOOLTIP_DELAY_MS = 300

# 대비 게이트(게이트 1). 텍스트/배경 전 조합이 이 값 이상이어야 한다.
CONTRAST_GATE = 5.0


# ---- 색 계산 (Qt 없이 동작) ----
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_FUNC_RE = re.compile(
    r"^rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*(?:,\s*([0-9.]*\.?[0-9]+)\s*)?\)$"
)


def parse_rgba(color: str) -> tuple[float, float, float, float]:
    """'#RGB' / '#RRGGBB' / 'rgb(r,g,b)' / 'rgba(r,g,b,a)' 를 (r, g, b, a) 로 판다.

    r/g/b 는 0~255, a 는 0~1.
    """
    value = color.strip()
    if _HEX_RE.match(value):
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(ch * 2 for ch in digits)
        return (
            float(int(digits[0:2], 16)),
            float(int(digits[2:4], 16)),
            float(int(digits[4:6], 16)),
            1.0,
        )
    m = _FUNC_RE.match(value)
    if m:
        alpha = 1.0 if m.group(4) is None else float(m.group(4))
        return (float(m.group(1)), float(m.group(2)), float(m.group(3)), alpha)
    raise ValueError(f"색 형식을 알 수 없습니다: {color!r}")


def to_hex(rgb: tuple[float, float, float]) -> str:
    """(r, g, b) 실수 튜플을 '#RRGGBB' 로."""
    return "#" + "".join(f"{max(0, min(255, round(c))):02X}" for c in rgb)


def flatten(*layers: str) -> str:
    """위에서 아래 순서로 알파 합성해 불투명 '#RRGGBB' 를 만든다.

    맨 마지막 층(가장 아래)은 불투명해야 한다. 예: flatten(txt2, card).
    """
    if not layers:
        raise ValueError("합성할 색이 없습니다")
    r, g, b, a = parse_rgba(layers[-1])
    if a < 1.0:
        raise ValueError(f"가장 아래 층은 불투명해야 합니다: {layers[-1]!r}")
    out = (r, g, b)
    for layer in reversed(layers[:-1]):
        lr, lg, lb, la = parse_rgba(layer)
        out = (
            lr * la + out[0] * (1 - la),
            lg * la + out[1] * (1 - la),
            lb * la + out[2] * (1 - la),
        )
    return to_hex(out)


def _linearize(channel: float) -> float:
    v = channel / 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    """WCAG 상대 휘도. 불투명 색만 받는다(알파가 있으면 먼저 flatten)."""
    r, g, b, a = parse_rgba(color)
    if a < 1.0:
        raise ValueError(f"불투명 색이 필요합니다(먼저 flatten): {color!r}")
    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def contrast(fg: str, bg: str) -> float:
    """전경/배경 대비비. 전경에 알파가 있으면 배경 위에 합성한 뒤 계산한다.

    배경은 불투명이어야 한다(다크 상태 배경처럼 알파가 있으면 flatten 으로 먼저 깔 것).
    """
    bg_hex = flatten(bg)
    fg_hex = flatten(fg, bg_hex)
    l1 = relative_luminance(fg_hex)
    l2 = relative_luminance(bg_hex)
    hi, lo = (l1, l2) if l1 >= l2 else (l2, l1)
    return (hi + 0.05) / (lo + 0.05)


def _shift_value(color: str, factor: float) -> str:
    """QColor.lighter/darker 와 같은 방식(HSV 의 V 에 배율)으로 밝기를 옮긴다."""
    r, g, b, _a = parse_rgba(color)
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    v = max(0.0, min(1.0, v * factor))
    nr, ng, nb = colorsys.hsv_to_rgb(h, s, v)
    return to_hex((nr * 255.0, ng * 255.0, nb * 255.0))


def accent_roles(dark: bool = False, base: str = ACCENT_BASE) -> dict[str, str]:
    """accent 3역할(fill / onAccent / text)과 hover·pressed·tint 를 돌려준다.

    기본 accent 는 02 §1.3 의 확정값 표를 그대로 쓴다. 사용자가 accent 를 바꾸면
    같은 관계(다크는 밝게, 라이트는 글자용을 어둡게)로 파생한다.
    """
    if parse_rgba(base)[:3] == parse_rgba(ACCENT_BASE)[:3]:
        return dict(ACCENT_DARK if dark else ACCENT_LIGHT)

    r, g, b, _a = parse_rgba(base)
    rgb = f"{round(r)},{round(g)},{round(b)}"
    if dark:
        lifted = _shift_value(base, 1.60)
        return {
            "fill": lifted,
            "hover": lifted,
            "pressed": _shift_value(base, 1.30),
            "onAccent": "#16140F",
            "text": lifted,
            "tint": f"rgba({rgb},.13)",
        }
    return {
        "fill": to_hex((r, g, b)),
        "hover": _shift_value(base, 0.89),
        "pressed": _shift_value(base, 0.77),
        "onAccent": "#FFFFFF",
        "text": _shift_value(base, 0.77),
        "tint": f"rgba({rgb},.09)",
    }


def fluent_tokens(dark: bool = False, accent: str = ACCENT_BASE) -> dict[str, str]:
    """표면 + accent + 상태 토큰을 한 딕셔너리로 합쳐 돌려준다.

    accent 는 'accentFill' 처럼 접두어를 붙여 표면 토큰과 이름이 겹치지 않게 한다.
    """
    merged: dict[str, str] = dict(FLUENT_DARK if dark else FLUENT_LIGHT)
    for role, value in accent_roles(dark, accent).items():
        key = "onAccent" if role == "onAccent" else f"accent{role[0].upper()}{role[1:]}"
        merged[key] = value
    merged.update(STATUS_DARK if dark else STATUS_LIGHT)
    merged["photo"] = PHOTO_BG
    return merged


def fluent_height(key: str, size_key: str | None = None) -> int:
    """컨트롤 최소 높이(px). size_key 는 설정의 ui_font_size(normal/large)."""
    row = HEIGHTS[key]
    return row.get(size_key or "normal", row["normal"])


def fluent_font_px(role: str, size_key: str | None = None) -> float:
    """타이포 역할별 글자 크기(px)에 글자 크기 배율을 적용해 돌려준다."""
    return TYPO[role]["size"] * scale_for(size_key)
