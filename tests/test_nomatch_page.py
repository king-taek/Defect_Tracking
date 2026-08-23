"""미매칭 페이지(단계 5) 계약.

사유 필터가 남기는 부분집합, layer 별 사유 행의 개수와 글자 크기, 그리고 U 점프(A11)의
순수 함수를 못 박는다. 사유 행이 이 화면의 주 내용이라 12px 아래로 내려가면 게이트 위반이다.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.models import (  # noqa: E402
    BaseDefectMatches,
    DefectRecord,
    MatchResult,
    NoMatchReason,
)
from app.ui.pages.nomatch import (  # noqa: E402
    NoMatchPage,
    dominant_reason,
    fully_unmatched_indices,
    has_unmatched,
    is_fully_unmatched,
    layer_reason_rows,
    next_unmatched_index,
)

_LAYERS = ["LYB4", "LYA3", "LYB3"]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------- 표본
def _record(layer: str, col: int = 3, row: int = 4) -> DefectRecord:
    return DefectRecord(
        image_path=Path(f"/nowhere/{layer}_{col}_{row}.jpg"),
        wafer_id="00MHE105XYF6",
        layer=layer,
        layer_folder=f"1. {layer}",
        col=col,
        row=row,
        x=5000.0,
        y=6000.0,
        defect_name="Particle",
    )


def _result(layer: str, reason: NoMatchReason, base: DefectRecord) -> MatchResult:
    """사유별 MatchResult. reason 은 die_candidates/failed_in_die 에서 파생된다."""
    if reason == NoMatchReason.NONE:
        return MatchResult(compare_layer=layer, base=base, matched=_record(layer),
                           distance=12.4)
    if reason == NoMatchReason.OVER_TOLERANCE:
        return MatchResult(compare_layer=layer, base=base, die_candidates=2,
                           nearest=_record(layer), nearest_distance=118.4)
    if reason == NoMatchReason.COORD_FAIL:
        return MatchResult(compare_layer=layer, base=base, failed_in_die=3)
    return MatchResult(compare_layer=layer, base=base)


def _item(reasons: list[NoMatchReason], col: int = 3) -> BaseDefectMatches:
    base = _record("LYA4", col=col)
    return BaseDefectMatches(
        base=base,
        results=[_result(_LAYERS[i], r, base) for i, r in enumerate(reasons)],
    )


def _sample() -> list[BaseDefectMatches]:
    """사유가 서로 다른 완전 미매칭 3장 + 부분 미매칭 1장 + 전부 매칭 1장."""
    return [
        _item([NoMatchReason.OVER_TOLERANCE] * 3, col=1),
        _item([NoMatchReason.COORD_FAIL] * 3, col=2),
        _item([NoMatchReason.NO_DIE_PHOTO] * 3, col=3),
        _item([NoMatchReason.NONE, NoMatchReason.OVER_TOLERANCE,
               NoMatchReason.NONE], col=4),
        _item([NoMatchReason.NONE] * 3, col=5),
    ]


# ---------------------------------------------------------------- 순수 로직
def test_u_jump_targets_any_unmatched_not_only_total_failures():
    """A11 재정의: U 는 '미매칭을 하나 이상 포함한' 기준으로 간다."""
    matches = _sample()
    assert has_unmatched(matches[3]) is True        # 부분 미매칭도 대상
    assert has_unmatched(matches[4]) is False
    assert next_unmatched_index(matches, current=-1) == 0
    assert next_unmatched_index(matches, current=0) == 1
    assert next_unmatched_index(matches, current=2) == 3


def test_u_jump_wraps_around_when_current_is_the_last_target():
    matches = _sample()
    assert next_unmatched_index(matches, current=3) == 0
    assert next_unmatched_index(matches, current=4) == 0


def test_u_jump_returns_none_when_there_is_no_target():
    """후보가 없으면 None. 호출부가 A11 의 '미매칭 없음' 문구로 알린다."""
    assert next_unmatched_index([_item([NoMatchReason.NONE] * 3)], current=0) is None
    assert next_unmatched_index([], current=0) is None
    assert next_unmatched_index(None, current=0) is None


def test_u_jump_stays_inside_the_current_view():
    """보기(필터)에서 빠진 후보로는 점프하지 않는다."""
    matches = _sample()
    assert next_unmatched_index(matches, current=0, view=[0, 2, 4]) == 2
    assert next_unmatched_index(matches, current=2, view=[0, 2, 4]) == 0
    assert next_unmatched_index(matches, current=0, view=[4]) is None


def test_u_jump_returns_current_when_it_is_the_only_target():
    """순환이므로 후보가 자기 하나면 제자리다(빈 화면으로 튀지 않는다)."""
    matches = [_item([NoMatchReason.NONE] * 3), _item([NoMatchReason.COORD_FAIL] * 3)]
    assert next_unmatched_index(matches, current=1) == 1


def test_page_lists_only_fully_unmatched_bases():
    """A11: 부분 미매칭은 판독대가 이미 보여 준다. 목록은 완전 미매칭만."""
    matches = _sample()
    assert fully_unmatched_indices(matches) == [0, 1, 2]
    assert is_fully_unmatched(matches[3]) is False


def test_no_compare_layer_selected_is_not_counted_as_unmatched():
    """비교 layer 를 아직 고르지 않은 상태를 '전부 실패'로 세면 배지가 전체 장수가 된다."""
    empty = BaseDefectMatches(base=_record("LYA4"), results=[])
    assert is_fully_unmatched(empty) is False
    assert has_unmatched(empty) is False


def test_dominant_reason_keeps_the_original_priority():
    """원본 계승: 허용오차 초과 > 좌표 추출 실패 > 같은 die 사진 없음."""
    mixed = _item([NoMatchReason.NO_DIE_PHOTO, NoMatchReason.COORD_FAIL,
                   NoMatchReason.OVER_TOLERANCE])
    assert dominant_reason(mixed) == NoMatchReason.OVER_TOLERANCE
    partial = _item([NoMatchReason.NO_DIE_PHOTO, NoMatchReason.COORD_FAIL,
                     NoMatchReason.NONE])
    assert dominant_reason(partial) == NoMatchReason.COORD_FAIL


def test_layer_rows_follow_the_compare_layer_order():
    item = _item([NoMatchReason.OVER_TOLERANCE] * 3)
    rows = layer_reason_rows(item, ["LYB3", "LYB4", "LYA3"])
    assert [layer for layer, _text, _reason in rows] == ["LYB3", "LYB4", "LYA3"]
    assert "허용오차 초과" in rows[0][1] and "µm" in rows[0][1]


# ---------------------------------------------------------------- 화면
@pytest.fixture()
def page(app):
    p = NoMatchPage()
    p.set_data(_sample(), None, "LYA4", _LAYERS)
    p.resize(1200, 800)
    for _ in range(5):
        QCoreApplication.processEvents()
    return p


def test_page_object_name_is_the_route_key(page):
    """objectName 이 곧 nav 라우트 키다. 비면 ValueError, 겹치면 라우팅이 깨진다."""
    assert page.objectName() == "nomatchInterface"


def test_reason_filter_leaves_the_right_subset(page):
    """각 칸이 그 사유를 가진 기준만 남긴다."""
    assert page.shown_count() == 3

    page.set_filter(NoMatchReason.OVER_TOLERANCE.value)
    assert [c.index for c in page.cells()] == [0]

    page.set_filter(NoMatchReason.COORD_FAIL.value)
    assert [c.index for c in page.cells()] == [1]

    page.set_filter(NoMatchReason.NO_DIE_PHOTO.value)
    assert [c.index for c in page.cells()] == [2]

    page.set_filter("all")
    assert [c.index for c in page.cells()] == [0, 1, 2]


def test_filter_keeps_a_base_that_has_that_reason_among_others(page):
    """사유가 섞인 기준은 해당 사유 칸에 모두 남는다(원본 필터 의미 계승)."""
    mixed = _item([NoMatchReason.OVER_TOLERANCE, NoMatchReason.COORD_FAIL,
                   NoMatchReason.NO_DIE_PHOTO])
    page.set_data([mixed], None, "LYA4", _LAYERS)
    for key in (NoMatchReason.OVER_TOLERANCE.value, NoMatchReason.COORD_FAIL.value,
                NoMatchReason.NO_DIE_PHOTO.value, "all"):
        page.set_filter(key)
        assert page.shown_count() == 1, key


def test_cell_has_one_reason_row_per_layer_at_12px_or_more(page):
    """이 화면의 주 내용이다. 9px 한 줄 요약으로 되돌아가면 안 된다."""
    cell = page.cells()[0]
    assert len(cell.reason_rows) == len(_LAYERS)
    assert [r.key.text() for r in cell.reason_rows] == _LAYERS
    for row in cell.reason_rows:
        assert row.key.font().pixelSize() >= 12
        assert row.text.font().pixelSize() >= 12
        assert "허용오차 초과" in row.text.text()
    # layer 키는 굵게 세워 세로로 읽히게 한다(12px/600).
    assert cell.reason_rows[0].key.font().weight() >= 600


def test_cell_shows_the_dominant_reason_badge_and_caption(page):
    cell = page.cells()[1]
    assert cell.badge.text() == "좌표 추출 실패"
    assert "00MHE105XYF6" in cell.caption.text()


def test_clicking_a_cell_emits_the_base_index(page):
    """셀 클릭 -> 판독 화면의 그 기준 사진으로. 창이 _goto 에 연결한다."""
    seen: list[int] = []
    page.record_activated.connect(seen.append)
    cell = page.cells()[2]
    QTest.mouseClick(cell, Qt.LeftButton, Qt.NoModifier, QPoint(20, 20))
    for _ in range(3):
        QCoreApplication.processEvents()
    assert seen == [cell.index]


def test_empty_data_shows_the_empty_line(page):
    page.set_data([], None, "LYA4", _LAYERS)
    assert page.shown_count() == 0
    # 페이지를 띄우지 않은 상태라 isVisible 은 항상 False 다. 명시적 숨김만 본다.
    assert page.lbl_empty.isHidden() is False
    assert page.scroll.isHidden() is True
    assert "총 0장" in page.lbl_count.text()
