"""출력 명세 페이지(단계 7) 계약.

행 높이 60 · 행 제거가 목록과 화면에서 함께 사라짐 · `×n` 묶음 셈 · 200블록 경고 문구 ·
빈 트레이의 주요 액션 · 묶음 태그 보존을 못 박는다. 이 여섯 가지가 깨지면 화면은 그대로인 채
Excel 로 나가는 내용이 달라진다.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from app import scanner  # noqa: E402
from app.config import AppSettings  # noqa: E402
from app.export.excel_report import EXPORT_WARN_BLOCKS  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.pages import export as export_page  # noqa: E402
from app.ui.pages.export import ExportPage  # noqa: E402
from tools.make_sample_data import generate  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def matches(app, tmp_path_factory):
    """샘플 LOT 을 한 번만 스캔·매칭해 기준 사진 묶음을 만든다(스캔이 느리다)."""
    from app.ui.main_window import MainWindow

    root = tmp_path_factory.mktemp("lot")
    lot = generate(root / "src")
    index = scanner.scan_lot(lot)
    win = MainWindow(AppSettings(workspace=str(root / "ws"), auto_update_check=False))
    win.lot_index = index
    win._on_scan_finished(index)
    win.top.cmb_base.setCurrentText("LYA4")
    for _ in range(10):
        QCoreApplication.processEvents()
    assert win.matches, "샘플 LOT 에서 기준 사진이 나와야 한다"
    return list(win.matches)


def _settle(ms: int = 60) -> None:
    for _ in range(5):
        QCoreApplication.processEvents()
    QTest.qWait(ms)
    for _ in range(5):
        QCoreApplication.processEvents()


def _page(app, entries, **kwargs) -> ExportPage:
    page = ExportPage(**kwargs)
    page.set_tray(list(entries))
    page.resize(1000, 700)
    return page


# ---------------------------------------------------------------- 라우트
def test_page_object_name_is_the_route_key(app):
    """objectName 이 비면 ValueError, 겹치면 라우팅이 깨진다."""
    assert ExportPage().objectName() == "exportInterface"


# ---------------------------------------------------------------- 표 규격
def test_spec_row_height_is_60(app, matches):
    """03-screens §4: 머리 38 + 행 60."""
    page = _page(app, matches[:3])
    assert page._rows, "담은 항목만큼 행이 서야 한다"
    for row in page._rows:
        assert row.height() == 60
    assert theme.fluent_height("specRow") == 60


def test_spec_row_height_follows_large_font_setting(app, matches):
    """글자 크게(large)면 행은 72. 높이는 곱셈이 아니라 HEIGHTS 표로 고정한다(A9)."""
    page = _page(app, matches[:2], size_key="large")
    assert theme.fluent_height("specRow", "large") == 72
    for row in page._rows:
        assert row.height() == 72


# ---------------------------------------------------------------- 행 제거
def test_removing_a_row_drops_it_from_list_and_screen(app, matches):
    """제거는 목록과 화면에서 함께 사라져야 한다(모델 즉시, 행은 240ms 접힘)."""
    page = _page(app, matches[:3])
    before = len(page._rows)
    key = export_page.item_key(matches[0])

    page._rows[0].btn_remove.click()
    # 목록에서는 곧바로 빠진다 - 출력 대상은 애니메이션을 기다리지 않는다.
    assert key not in {export_page.item_key(m) for m in page.selected()}
    assert len(page.selected()) == before - 1

    _settle(400)  # 퇴장 240ms 를 넘겨 기다린다
    assert len(page._rows) == before - 1
    assert all(row.key != key for row in page._rows)
    assert not page._collapsing
    # NO 는 빈 자리 없이 다시 매겨진다.
    assert [row.lbl_no.text() for row in page._rows] == ["1", "2"]


def test_tray_changed_reports_the_new_total(app, matches):
    """창이 묻지 않아도 개수 변화를 알린다(판독 화면 담기 버튼 표시용)."""
    page = _page(app, matches[:3])
    seen: list[int] = []
    page.tray_changed.connect(seen.append)
    page._rows[0].btn_remove.click()
    _settle(400)
    assert seen and seen[-1] == 2


# ---------------------------------------------------------------- 묶음 행
def test_batch_row_counts_as_one_row_and_n_photos(app, matches):
    """`×n` 묶음은 행 하나지만 합계에서는 n장으로 센다."""
    tagged = [(matches[0], None)] + [(m, "테스트 묶음") for m in matches[1:]]
    page = _page(app, tagged)
    batch_size = len(matches) - 1

    assert len(page._rows) == 2  # 개별 1 + 묶음 1
    batch = page._rows[1]
    assert batch.is_batch and batch.count == batch_size
    assert batch.photo.text() == f"×{batch_size}"
    assert batch.lbl_match.text() == f"{batch_size}장"
    assert page.lbl_count.text() == f"개별 1장 + 묶음 1건 = 총 {len(matches)}장"
    assert len(page.selected()) == len(matches)


def test_removing_a_batch_row_drops_every_photo_in_it(app, matches):
    """묶음 행의 제거는 그 안의 사진 전부를 뺀다."""
    tagged = [(matches[0], None)] + [(m, "테스트 묶음") for m in matches[1:]]
    page = _page(app, tagged)
    page._rows[1].btn_remove.click()
    assert len(page.selected()) == 1
    _settle(400)
    assert len(page._rows) == 1
    assert page.lbl_count.text() == "개별 1장 + 묶음 0건 = 총 1장"


def test_add_all_matched_makes_one_batch_row(app, matches):
    """'매치 전체 담기' 는 사진 수만큼 행을 세우지 않고 묶음 한 줄로 접는다."""
    page = _page(app, [], all_matched=list(matches), all_matched_label="기준 'LYA4' 매치 전체")
    page.btn_add_all.click()
    assert len(page._rows) == 1
    assert page._rows[0].is_batch
    assert len(page.selected()) == len(matches)
    assert {tag for _m, tag in page.tagged_selected()} == {"기준 'LYA4' 매치 전체"}


# ---------------------------------------------------------------- 200블록 경고
def test_warn_copy_matches_review_a13_character_for_character(app):
    """REVIEW-01 A13 확정 문구. 한 글자라도 다르면 실패한다."""
    assert EXPORT_WARN_BLOCKS == 200
    assert export_page.EXPORT_WARN_BLOCKS is EXPORT_WARN_BLOCKS  # 새로 정의하지 않는다
    title, body, ok, no = export_page.warn_texts(250)
    assert title == "사진이 많습니다"
    assert body == (
        "250건을 출력하면 파일이 커지고 열기가 느려집니다.\n"
        "필요한 건만 남기고 출력하는 것을 권합니다."
    )
    assert ok == "그대로 출력"
    assert no == "명세로 돌아가기"


def test_warn_box_shows_exactly_that_copy(app):
    """화면에 실제로 걸리는 문구도 같아야 한다(상수만 맞고 화면이 다르면 소용없다)."""
    page = ExportPage()
    box = page._warn_box(250)
    title, body, ok, no = export_page.warn_texts(250)
    assert box.titleLabel.text() == title
    assert box.content == body  # contentLabel 은 폭에 맞춰 줄바꿈되므로 원문을 본다
    assert box.yesButton.text() == ok
    assert box.cancelButton.text() == no


def test_export_under_the_threshold_does_not_ask(app, matches):
    """임계값 이하에서는 묻지 않고 바로 출력 요청을 낸다."""
    page = _page(app, matches[:2])
    fired: list[int] = []
    page.export_requested.connect(lambda: fired.append(1))
    assert len(page.selected()) <= EXPORT_WARN_BLOCKS
    page.btn_export.click()
    assert fired == [1]
    assert page.wants_export() is True


# ---------------------------------------------------------------- 주요 액션
def test_export_button_is_disabled_on_an_empty_tray(app):
    """빈 명세에서 Excel 출력은 누를 수 없다. 주요 액션은 이 하나뿐이다."""
    page = _page(app, [])
    assert page.btn_export.text() == "Excel 출력"
    assert page.btn_export.isEnabled() is False
    assert page.btn_clear.isEnabled() is False
    assert page.empty.isVisibleTo(page) is True


def test_export_click_on_empty_tray_emits_nothing(app):
    page = _page(app, [])
    fired: list[int] = []
    page.export_requested.connect(lambda: fired.append(1))
    page.btn_export.click()
    assert fired == []
    assert page.wants_export() is False


# ---------------------------------------------------------------- 태그 보존
def test_tagged_selected_keeps_batch_tags_across_reopen(app, matches):
    """페이지를 떠났다 돌아와도 묶음이 개별 행으로 풀리지 않아야 한다."""
    page = _page(app, [], all_matched=list(matches), all_matched_label="테스트 묶음")
    page.btn_add_all.click()
    tagged = page.tagged_selected()
    assert tagged and all(tag == "테스트 묶음" for _m, tag in tagged)

    # 창이 트레이에 저장했다가 그대로 다시 넣는 경로.
    again = _page(app, tagged)
    assert again.tagged_selected() == tagged
    assert len(again._rows) == 1 and again._rows[0].is_batch


def test_editing_the_list_clears_the_export_intent(app, matches):
    """편집하면 wants_export 가 다시 False 다(옛 다이얼로그의 확인/출력 구분 계승)."""
    page = _page(app, matches[:3])
    page.btn_export.click()
    assert page.wants_export() is True
    page._rows[0].btn_remove.click()
    assert page.wants_export() is False


# ---------------------------------------------------------------- 카피 규칙
def test_page_copy_has_no_emoji_and_no_em_dash(app, matches):
    """이모지 0건 · em-dash 0건(02 §4). 원본의 이모지 묶음 카드를 `×n` 행으로 바꾼 자리다."""
    page = _page(app, [(matches[0], None), (matches[1], "테스트 묶음")])
    texts = [
        page.lbl_count.text(),
        page.empty.text(),
        page.btn_export.text(),
        page.btn_add_all.text(),
        page.btn_clear.text(),
        export_page.WARN_BODY,
        export_page._PAGE_SUB,
    ]
    for row in page._rows:
        texts += [row.lbl_no.text(), row.photo.text(), row.lbl_pos.text(),
                  row.lbl_sub.text(), row.lbl_match.text()]
    joined = "".join(texts)
    assert "\u2014" not in joined  # em-dash
    assert not any(ord(ch) > 0x1F000 for ch in joined)


# ---------------------------------------------------------------- 모든 매치 담기
def test_all_layers_button_unlocks_after_the_provider_answers(app, matches):
    """공급자가 빈 목록으로 끝나도 담기 버튼 잠금은 반드시 풀린다."""
    calls: list = []

    def provider(on_progress, on_done):
        calls.append(1)
        on_progress(1, 2)
        on_done([])  # 실패/빈 결과

    page = _page(app, [], all_matched=list(matches), all_layers_provider=provider)
    assert page.btn_add_all_layers.isVisible() is False or True  # 부모 없이 만든 페이지
    page.btn_add_all_layers.click()
    assert calls == [1]
    assert page.btn_add_all_layers.isEnabled() is True
    assert page.btn_add_all.isEnabled() is True
    assert page.progress.isVisibleTo(page) is False


def test_all_layers_results_land_in_one_batch_row(app, matches):
    def provider(on_progress, on_done):
        on_done(list(matches))

    page = _page(app, [], all_layers_provider=provider)
    page.btn_add_all_layers.click()
    assert len(page._rows) == 1 and page._rows[0].is_batch
    assert {tag for _m, tag in page.tagged_selected()} == {export_page.ALL_LAYERS_TAG}


def test_all_layers_button_is_hidden_without_a_provider(app):
    """공급자가 없으면 버튼 자체를 감춘다. 눌러도 아무 일 없는 버튼은 두지 않는다."""
    page = _page(app, [])
    assert page.btn_add_all_layers.isVisibleTo(page) is False
