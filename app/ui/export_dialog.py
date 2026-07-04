"""결과 출력 트레이 다이얼로그 (문서 Section 8.7 재설계).

'출력에 추가'로 담아 둔 기준 사진(트레이)들을 썸네일 카드로 확인하고, 개별 제거·전체
비우기 후 Excel 로 출력한다. 카드 그리드 패턴은 nomatch_gallery 와 동일한 톤으로 맞춘다.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.models import BaseDefectMatches
from app.thumbnails import ThumbnailCache
from app.ui import theme

_COLUMNS = 3
_THUMB_PX = 180  # 카드 썸네일 크기(크게)


class ExportTrayDialog(QDialog):
    """출력 트레이(담긴 기준 사진)를 카드로 관리하고 Excel 출력을 확정하는 다이얼로그."""

    def __init__(
        self,
        entries: list[BaseDefectMatches],
        thumb_cache: Optional[ThumbnailCache] = None,
        all_matched: Optional[list[BaseDefectMatches]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        # 담긴 항목(스냅샷). base image_path 로 중복 제거하며 유지한다.
        self._kept: list[BaseDefectMatches] = []
        self._keys: set[str] = set()
        for m in entries:
            self._add(m)
        # 이번 LOT 의 매칭 있는 기준 사진(전체 추가 버튼용).
        self._all_matched = list(all_matched or [])
        self._thumb_cache = thumb_cache
        self.setWindowTitle("결과 출력 — 담은 사진")
        self.setMinimumSize(620, 540)
        self._build()
        self._populate()

    @staticmethod
    def _key(item: BaseDefectMatches) -> str:
        return str(item.base.image_path)

    def _add(self, item: BaseDefectMatches) -> bool:
        k = self._key(item)
        if k in self._keys:
            return False
        self._keys.add(k)
        self._kept.append(item)
        return True

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 12)
        outer.setSpacing(10)

        head = QHBoxLayout()
        self.title = QLabel("")
        self.title.setObjectName("title")
        head.addWidget(self.title)
        head.addStretch()
        self.btn_add_all = QPushButton("이번 LOT 전체(매치) 추가")
        self.btn_add_all.setObjectName("mini")
        self.btn_add_all.setToolTip("이번 자재(LOT)에서 매칭이 있는 기준 사진을 모두 담습니다.")
        self.btn_add_all.clicked.connect(self._add_all_matched)
        self.btn_add_all.setEnabled(bool(self._all_matched))
        head.addWidget(self.btn_add_all)
        self.btn_clear = QPushButton("전체 비우기")
        self.btn_clear.setObjectName("mini")
        self.btn_clear.setToolTip("담은 사진을 모두 뺍니다.")
        self.btn_clear.clicked.connect(self._clear_all)
        head.addWidget(self.btn_clear)
        outer.addLayout(head)

        hint = QLabel("담은 사진만 Excel 로 출력됩니다. 각 카드의 ✕ 로 개별 제거할 수 있습니다.")
        hint.setObjectName("dim")
        outer.addWidget(hint)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        # 흰 배경 제거 → 다이얼로그(테마) 배경이 비치게.
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._scroll.viewport().setAutoFillBackground(False)
        self._host = QWidget()
        self._host.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._host)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(10)
        self._grid.setAlignment(Qt.AlignTop)
        self._scroll.setWidget(self._host)
        outer.addWidget(self._scroll, 1)

        self._empty = QLabel("담은 사진이 없습니다. '이번 LOT 전체(매치) 추가'로 담거나 창을 닫고 '＋ 출력에 추가'로 담아 주세요.")
        self._empty.setObjectName("dim")
        self._empty.setWordWrap(True)
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setVisible(False)
        outer.addWidget(self._empty)

        # 하단 바 — 취소 + 확인(Excel 출력). QDialogButtonBox 는 빈 트레이일 때 OK 가
        # 흐려져 '없는 것'처럼 보였으므로, 명시적 버튼으로 확인을 항상 뚜렷하게 노출한다.
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(btn_cancel)
        self.btn_export = QPushButton("Excel 출력")
        self.btn_export.setObjectName("primary")
        self.btn_export.setToolTip("담은 사진을 Excel 파일로 출력합니다.")
        self.btn_export.setDefault(True)
        self.btn_export.clicked.connect(self.accept)
        bottom.addWidget(self.btn_export)
        outer.addLayout(bottom)

    def _clear_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _populate(self) -> None:
        self._clear_grid()
        for i, item in enumerate(self._kept):
            self._grid.addWidget(self._make_card(item), i // _COLUMNS, i % _COLUMNS)
        shown = len(self._kept)
        self.title.setText(f"담은 사진 — 총 {shown}장")
        self._empty.setVisible(shown == 0)
        self.btn_export.setEnabled(shown > 0)
        self.btn_clear.setEnabled(shown > 0)

    def _make_card(self, item: BaseDefectMatches) -> QWidget:
        base = item.base
        px = _THUMB_PX
        card = QFrame()
        card.setFixedWidth(px + 20)
        card.setObjectName("cell")
        card.setStyleSheet(
            f"QFrame#cell {{ background:{theme.BG_ELEV};"
            f" border:1px solid {theme.NEON_SOFT}; border-radius:8px; }}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(6, 6, 6, 8)
        lay.setSpacing(4)

        # 큰 썸네일 + 그 위에 오버레이된 제거(✕) 버튼
        thumb = QLabel()
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setFixedSize(px, int(px * 0.78))
        thumb.setStyleSheet(
            f"background:{theme.BG}; border:1px solid {theme.NEON_SOFT};"
            f" border-radius:6px; color:{theme.TEXT_DIM}; font-size:10px;"
        )
        if self._thumb_cache is not None:
            path = self._thumb_cache.get_full_thumbnail(base.image_path, max_size=px)
            if path is not None:
                pix = QPixmap(str(path))
                if not pix.isNull():
                    thumb.setPixmap(pix.scaled(
                        px, int(px * 0.78), Qt.KeepAspectRatio, Qt.SmoothTransformation
                    ))
                else:
                    thumb.setText("이미지 없음")
            else:
                thumb.setText("이미지 없음")
        # ✕ 오버레이: 썸네일 우상단, 대비가 큰 반투명 어두운 배경 + 밝은 X.
        btn_x = QPushButton("✕", thumb)
        btn_x.setFixedSize(24, 24)
        btn_x.setCursor(Qt.PointingHandCursor)
        btn_x.setToolTip("이 사진을 출력 목록에서 뺍니다.")
        btn_x.setStyleSheet(
            "QPushButton { color:#ffffff; background:rgba(17,21,28,0.72);"
            " border:1px solid rgba(255,255,255,0.55); border-radius:12px;"
            " font-size:13px; font-weight:700; padding:0; }"
            "QPushButton:hover { background:#b00020; border:1px solid #ffffff; }"
        )
        btn_x.move(px - 28, 4)
        btn_x.clicked.connect(lambda _=0, k=self._key(item): self._remove(k))
        lay.addWidget(thumb, alignment=Qt.AlignHCenter)

        n_match = sum(1 for r in item.results if r.is_match)
        cap = QLabel(
            f"wafer {base.wafer_id} · die({base.col},{base.row})\n"
            f"매칭 {n_match}/{len(item.results)} · pos {base.position_key}"
        )
        cap.setObjectName("dim")
        cap.setStyleSheet("font-size:10px;")
        cap.setWordWrap(True)
        cap.setAlignment(Qt.AlignCenter)
        cap.setFixedWidth(px)
        lay.addWidget(cap, alignment=Qt.AlignHCenter)
        return card

    def _remove(self, key: str) -> None:
        self._kept = [m for m in self._kept if self._key(m) != key]
        self._keys.discard(key)
        self._populate()

    def _clear_all(self) -> None:
        self._kept = []
        self._keys = set()
        self._populate()

    def _add_all_matched(self) -> None:
        added = 0
        for m in self._all_matched:
            if self._add(m):
                added += 1
        self._populate()

    def selected(self) -> list[BaseDefectMatches]:
        """최종 출력 대상 스냅샷 목록(담긴 순서 유지)."""
        return list(self._kept)
