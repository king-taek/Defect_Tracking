"""다크 + 파란 네온 테마 (문서 Section 9).

어두운 바탕, 파란 네온 강조, 깔끔하고 복잡하지 않은 화면.
버튼은 hover/pressed 시 시각적 변화가 있어야 한다(QSS state 로 처리).
"""

from __future__ import annotations

# 팔레트
BG = "#0b0f17"
BG_PANEL = "#121826"
BG_ELEV = "#1a2333"
NEON = "#1e90ff"
NEON_DIM = "#1668c4"
NEON_SOFT = "#2b3d5c"
TEXT = "#e6edf7"
TEXT_DIM = "#8a98ad"
MATCH = "#34d399"
NOMATCH = "#f87171"
BASE_GLOW = "#38bdf8"

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
    border-radius: 10px;
}}
QLabel {{
    color: {TEXT};
    background: transparent;
}}
QLabel#dim {{ color: {TEXT_DIM}; }}
QLabel#title {{ font-size: 16px; font-weight: 700; color: {TEXT}; }}
QLabel#lotName {{ font-size: 13px; font-weight: 600; color: {BASE_GLOW}; }}

/* ---- 버튼 ---- */
QPushButton {{
    background-color: {BG_ELEV};
    color: {TEXT};
    border: 1px solid {NEON_SOFT};
    border-radius: 8px;
    padding: 7px 14px;
    font-size: 12px;
}}
QPushButton:hover {{
    background-color: {NEON_DIM};
    border: 1px solid {NEON};
    color: #ffffff;
}}
QPushButton:pressed {{
    background-color: {NEON};
    border: 1px solid {BASE_GLOW};
    padding-top: 8px; padding-bottom: 6px;
}}
QPushButton:disabled {{
    color: {TEXT_DIM};
    border: 1px solid #232b3a;
    background-color: #131825;
}}
QPushButton#primary {{
    background-color: {NEON_DIM};
    border: 1px solid {NEON};
    font-weight: 700;
}}
QPushButton#primary:hover {{ background-color: {NEON}; }}
QPushButton#primary:pressed {{ background-color: {BASE_GLOW}; }}

/* ---- 입력 ---- */
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background-color: {BG_ELEV};
    border: 1px solid {NEON_SOFT};
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: {NEON};
}}
QComboBox:hover, QDoubleSpinBox:hover {{ border: 1px solid {NEON}; }}
QComboBox QAbstractItemView {{
    background-color: {BG_ELEV};
    border: 1px solid {NEON};
    selection-background-color: {NEON_DIM};
    outline: none;
}}

/* ---- 체크박스(비교 layer 선택) ---- */
QCheckBox {{ spacing: 6px; padding: 3px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {NEON_SOFT};
    border-radius: 4px;
    background: {BG_ELEV};
}}
QCheckBox::indicator:hover {{ border: 1px solid {NEON}; }}
QCheckBox::indicator:checked {{
    background: {NEON};
    border: 1px solid {BASE_GLOW};
}}

/* ---- 리스트(출력 선택) ---- */
QListWidget {{
    background-color: {BG_ELEV};
    border: 1px solid {NEON_SOFT};
    border-radius: 8px;
    outline: none;
}}
QListWidget::item {{ padding: 6px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {NEON_SOFT}; }}
QListWidget::item:selected {{ background: {NEON_DIM}; color: #fff; }}

/* ---- 스크롤바 ---- */
QScrollBar:horizontal, QScrollBar:vertical {{
    background: transparent; border: none;
}}
QScrollBar:horizontal {{ height: 10px; }}
QScrollBar:vertical {{ width: 10px; }}
QScrollBar::handle {{
    background: {NEON_SOFT}; border-radius: 5px; min-width: 30px; min-height: 30px;
}}
QScrollBar::handle:hover {{ background: {NEON}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QProgressBar {{
    background-color: {BG_ELEV};
    border: 1px solid {NEON_SOFT};
    border-radius: 6px;
    text-align: center;
    height: 16px;
}}
QProgressBar::chunk {{
    background-color: {NEON};
    border-radius: 5px;
}}
QToolTip {{
    background-color: {BG_ELEV};
    color: {TEXT};
    border: 1px solid {NEON};
    border-radius: 4px;
    padding: 4px;
}}
"""


def apply_theme(app) -> None:
    app.setStyleSheet(STYLESHEET)
