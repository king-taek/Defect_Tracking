"""다크 + 파란 네온 테마 (문서 Section 9).

어두운 바탕, 파란 네온 강조, 깔끔하고 복잡하지 않은 화면.
버튼은 hover/pressed 시 시각적 변화가 있어야 한다(QSS state 로 처리).
"""

from __future__ import annotations

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


# 팔레트 — 저채도 슬레이트 다크 테마(부드러운 대비, 넓은 여백 지향)
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
/* 확대 화면 줌 −/＋ 버튼 — 버튼 크기는 그대로 두고 글자만 키운다 */
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

/* ---- 우클릭/드롭다운 메뉴 — 어두운 테마 통일(흰 배경 방지) ---- */
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

/* ---- 아이템 뷰(트리/리스트/테이블) — 어두운 테마 통일(흰 배경 방지) ---- */
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
