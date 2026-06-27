"""다크 + 파란 네온 테마 (문서 Section 9).

어두운 바탕, 파란 네온 강조, 깔끔하고 복잡하지 않은 화면.
버튼은 hover/pressed 시 시각적 변화가 있어야 한다(QSS state 로 처리).
"""

from __future__ import annotations

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

/* ---- 입력 ---- */
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background-color: {BG_ELEV};
    border: 1px solid {NEON_SOFT};
    border-radius: 8px;
    padding: 5px 9px;
    selection-background-color: {NEON_DIM};
}}
QComboBox:hover, QDoubleSpinBox:hover {{ border: 1px solid {NEON}; }}
QComboBox QAbstractItemView {{
    background-color: {BG_ELEV};
    border: 1px solid {NEON};
    selection-background-color: {NEON_DIM};
    outline: none;
}}

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


def apply_theme(app) -> None:
    app.setStyleSheet(STYLESHEET)
