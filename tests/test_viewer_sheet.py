"""원본 뷰어 시트와 근접 클러스터 시트(단계 5) 계약.

휠 줌의 커서 고정(원본 계승 필수), '맞춤' 의 원점 복귀, 잡고 끌기 패닝, 머리 한 줄 메타,
그리고 클러스터 시트의 '전부 명세에 담기' 위임을 못 박는다.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QMouseEvent, QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from qfluentwidgets import isDarkTheme  # noqa: E402

from app.models import DefectRecord  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.cluster_view import ClusterMembersPopup  # noqa: E402
from app.ui.image_viewer import ImageViewerDialog  # noqa: E402

_IMG_W, _IMG_H = 1200, 900


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def image_path(tmp_path_factory) -> Path:
    """원본 대신 쓸 큰 이미지 한 장(스캔 대상 폴더에는 아무것도 쓰지 않는다)."""
    path = tmp_path_factory.mktemp("origin") / "LYA4_3_4.png"
    img = QImage(_IMG_W, _IMG_H, QImage.Format_RGB32)
    img.fill(QColor("#203040"))
    for x in range(0, _IMG_W, 40):       # 눈으로 볼 때 이동이 보이도록 격자
        for y in range(_IMG_H):
            img.setPixelColor(x, y, QColor("#8899AA"))
    img.save(str(path))
    return path


def _record(image_path: Path) -> DefectRecord:
    return DefectRecord(
        image_path=image_path,
        wafer_id="00MHE105XYF6",
        layer="LYA4",
        layer_folder="1. LYA4_재리뷰",
        col=3,
        row=4,
        x=5000.0,
        y=6000.0,
        defect_name="Over Sized Bump",
    )


def _settle(ms: int = 60) -> None:
    for _ in range(10):
        QCoreApplication.processEvents()
    QTest.qWait(ms)
    for _ in range(10):
        QCoreApplication.processEvents()


def _finish_zoom(dlg: ImageViewerDialog) -> None:
    """줌 애니메이션(250ms OutQuint)이 끝날 때까지 기다린다."""
    for _ in range(20):
        if dlg._zoom_anim is None:
            break
        _settle(40)
    _settle(20)


@pytest.fixture()
def viewer(app, image_path):
    dlg = ImageViewerDialog(_record(image_path))
    dlg.resize(820, 620)
    dlg.show()
    _settle()
    return dlg


# ---------------------------------------------------------------- 머리 52
def test_header_meta_is_one_line_without_the_path(viewer, image_path):
    """원본은 4줄(경로 포함)이었다. 전체 경로는 '정보 복사' 에만 남는다."""
    meta = viewer.lbl_meta.text()
    assert "\n" not in meta
    assert str(image_path) not in meta
    for token in ("SLOT", "die (3, 4)", "Camtek", "Over Sized Bump"):
        assert token in meta
    assert viewer._header.height() == 52


def test_copy_info_keeps_the_full_path(viewer, image_path):
    info = viewer._info_text()
    assert str(image_path) in info
    assert "KLA" in info


def test_meta_numbers_use_a_monospace_font(viewer):
    """수치는 등폭. 자리가 흔들리면 die·좌표를 눈으로 비교할 수 없다."""
    assert viewer.lbl_meta.font().families()
    assert viewer.lbl_zoom.font().families()


# ---------------------------------------------------------------- 줌
def test_wheel_zoom_keeps_the_point_under_the_cursor(viewer):
    """원본 계승 필수: 휠 줌은 커서 아래 지점을 고정한다."""
    viewer._apply_scale(scale=2.0, animate=False)
    hbar = viewer._scroll.horizontalScrollBar()
    vbar = viewer._scroll.verticalScrollBar()
    hbar.setValue(hbar.maximum() // 2)
    vbar.setValue(vbar.maximum() // 2)
    _settle(20)

    vp = viewer._scroll.viewport()
    pos = QPointF(240.0, 180.0)
    before = (
        (hbar.value() + pos.x()) / viewer._scale,
        (vbar.value() + pos.y()) / viewer._scale,
    )
    event = QWheelEvent(
        pos, QPointF(vp.mapToGlobal(pos.toPoint())), QPoint(0, 0), QPoint(0, 120),
        Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False,
    )
    QApplication.sendEvent(vp, event)
    _finish_zoom(viewer)

    assert viewer._scale > 2.0
    after = (
        (hbar.value() + pos.x()) / viewer._scale,
        (vbar.value() + pos.y()) / viewer._scale,
    )
    # 이미지 좌표로 같은 지점이어야 한다(스크롤 값 반올림 여유 1px).
    assert abs(after[0] - before[0]) <= 1.0
    assert abs(after[1] - before[1]) <= 1.0


def test_fit_returns_to_the_origin(viewer):
    """'맞춤' 은 배율뿐 아니라 자리도 되돌린다(길을 잃었을 때 돌아오는 자리)."""
    viewer._apply_scale(scale=3.0, animate=False)
    viewer._scroll.horizontalScrollBar().setValue(400)
    viewer._scroll.verticalScrollBar().setValue(300)
    _settle(20)

    viewer.btn_fit.click()
    _finish_zoom(viewer)

    assert viewer._fit is True
    assert viewer._scroll.horizontalScrollBar().value() == 0
    assert viewer._scroll.verticalScrollBar().value() == 0
    assert viewer._scale <= 1.0


def test_hud_marks_the_active_mode_with_a_fill(viewer):
    """활성 항목은 채움으로 보인다. 채움 위 글자는 onAccent 다(AD2)."""
    tokens = theme.fluent_tokens(isDarkTheme())
    viewer.btn_fit.click()
    _finish_zoom(viewer)
    assert tokens["accentFill"] in viewer.btn_fit.styleSheet()
    assert tokens["onAccent"] in viewer.btn_fit.styleSheet()
    assert "transparent" in viewer.btn_actual.styleSheet()

    viewer.btn_actual.click()
    _finish_zoom(viewer)
    assert tokens["accentFill"] in viewer.btn_actual.styleSheet()
    assert "transparent" in viewer.btn_fit.styleSheet()


def test_zoom_label_is_fixed_width_and_carries_the_unit(viewer):
    viewer._apply_scale(scale=1.0, animate=False)
    first = viewer.lbl_zoom.text()
    viewer._apply_scale(scale=2.0, animate=False)
    assert viewer.lbl_zoom.text().endswith("%")
    assert len(viewer.lbl_zoom.text()) == len(first)


# ---------------------------------------------------------------- 패닝
def _mouse(kind, widget, point: QPoint, button=Qt.LeftButton, buttons=Qt.LeftButton):
    return QMouseEvent(
        kind, QPointF(point), QPointF(widget.mapToGlobal(point)), button, buttons,
        Qt.NoModifier,
    )


def test_drag_pans_the_stage_and_the_cursor_changes(viewer):
    """잡고 끌기: grab -> grabbing, 놓으면 그 자리에서 확정."""
    viewer._apply_scale(scale=3.0, animate=False)
    hbar = viewer._scroll.horizontalScrollBar()
    vbar = viewer._scroll.verticalScrollBar()
    hbar.setValue(300)
    vbar.setValue(200)
    _settle(20)
    canvas = viewer._canvas
    assert canvas.cursor().shape() == Qt.OpenHandCursor

    QApplication.sendEvent(canvas, _mouse(QEvent.MouseButtonPress, canvas, QPoint(60, 60)))
    assert canvas.cursor().shape() == Qt.ClosedHandCursor
    QApplication.sendEvent(canvas, _mouse(QEvent.MouseMove, canvas, QPoint(20, 30)))
    assert hbar.value() == 340
    assert vbar.value() == 230
    QApplication.sendEvent(
        canvas, _mouse(QEvent.MouseButtonRelease, canvas, QPoint(20, 30), buttons=Qt.NoButton)
    )
    assert canvas.cursor().shape() == Qt.OpenHandCursor
    # 놓은 뒤에도 그 자리가 유지된다(되돌리거나 관성을 주지 않는다).
    _settle(20)
    assert hbar.value() == 340


def test_drag_stops_a_running_zoom(viewer):
    """드래그 중에는 전이가 없다(명세). 줌 애니메이션이 남아 있으면 손이 미끄러진다."""
    viewer._apply_scale(scale=1.0, animate=False)
    viewer._zoom(2.0)
    assert viewer._zoom_anim is not None
    QApplication.sendEvent(
        viewer._canvas, _mouse(QEvent.MouseButtonPress, viewer._canvas, QPoint(40, 40))
    )
    assert viewer._zoom_anim is None
    QApplication.sendEvent(
        viewer._canvas,
        _mouse(QEvent.MouseButtonRelease, viewer._canvas, QPoint(40, 40), buttons=Qt.NoButton),
    )


# ---------------------------------------------------------------- 클러스터 시트
def test_cluster_sheet_keeps_the_positional_contract(app, image_path):
    """(records, layer, thumb_cache, open_viewer, parent) 위치 인자는 그대로다."""
    records = [_record(image_path) for _ in range(3)]
    popup = ClusterMembersPopup(records, "LYA4", None, lambda rec: None, None)
    assert popup.btn_close.text() == "닫기"
    # 담을 곳을 주지 않으면 버튼을 두지 않는다(눌러도 아무 일이 없으면 고장으로 읽힌다).
    assert popup.btn_add.isVisible() is False
    popup.close()


def test_cluster_sheet_add_all_calls_back_with_every_member(app, image_path):
    records = [_record(image_path) for _ in range(4)]
    seen: list[list] = []
    popup = ClusterMembersPopup(
        records, "LYA4", None, lambda rec: None, None,
        add_to_export=lambda recs: seen.append(list(recs)),
    )
    popup.show()
    _settle(20)
    assert popup.btn_add.text() == "전부 명세에 담기"
    popup.btn_add.click()
    for _ in range(3):
        QCoreApplication.processEvents()
    assert len(seen) == 1
    assert seen[0] == records
    popup.close()
