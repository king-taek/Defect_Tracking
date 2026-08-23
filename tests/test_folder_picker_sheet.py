"""폴더 선택 시트(단계 4) 계약.

이 화면이 지켜야 하는 것은 두 가지다. 하나는 규모(폴더 수백 개에서 목록이 즉시 열릴 것), 다른
하나는 보정(layer·wafer 를 골라도 LOT 으로 되돌릴 것)이다. 둘 다 눈으로는 확인되지 않으므로
여기서 못 박는다.

특히 '한 단계만 scandir' 는 회귀하면 네트워크 드라이브에서만 드러난다(로컬 tmp 는 빨라서
안 보인다). 그래서 깊은 트리를 만들고 UI 스레드가 실제로 만진 경로를 세는 방식으로 검사한다.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
pytest.importorskip("qfluentwidgets")

from PySide6.QtCore import QCoreApplication, Qt, QThreadPool  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from qfluentwidgets import Theme, isDarkTheme, setTheme  # noqa: E402

from app.config import AppSettings  # noqa: E402
from app.ui.folder_picker import (  # noqa: E402
    RANK_LOT,
    RANK_OTHER,
    RANK_UNSURE,
    FolderPickerDialog,
    probe_folder,
)

_JPEG = b"\xff\xd8\xff\xd9"


@pytest.fixture(scope="module")
def app():
    inst = QApplication.instance() or QApplication([])
    setTheme(Theme.LIGHT)
    yield inst


def _settle(times: int = 6) -> None:
    """백그라운드 판별(QThreadPool)이 끝나고 큐된 시그널이 배달될 때까지 돌린다."""
    for _ in range(times):
        QThreadPool.globalInstance().waitForDone(5000)
        for _ in range(5):
            QCoreApplication.processEvents()


def _make_lot(base: Path, name: str, layers: int = 2, wafers: int = 2) -> Path:
    """LOT/layer/wafer/사진 구조 하나를 만든다."""
    lot = base / name
    for i in range(layers):
        for w in range(wafers):
            wafer = lot / f"{i + 1}. LY{i}" / f"W{w + 1}"
            wafer.mkdir(parents=True)
            (wafer / "shot.jpg").write_bytes(_JPEG)
    return lot


def _make_device(base: Path, name: str, lots: int = 1) -> Path:
    """Device(자재) 폴더 - LOT 을 자식으로 갖는 계층."""
    device = base / name
    for i in range(lots):
        _make_lot(device, f"{name}_LOT{i + 1}")
    return device


def _rows(dlg: FolderPickerDialog) -> list[str]:
    """목록에 보이는 항목 이름(머리글은 None 이라 제외)."""
    out = []
    for i in range(dlg.listw.count()):
        name = dlg.listw.item(i).data(Qt.UserRole)
        if name is not None:
            out.append(name)
    return out


def _texts(dlg: FolderPickerDialog) -> list[str]:
    return [dlg.listw.item(i).text() for i in range(dlg.listw.count())]


# ------------------------------------------------------------------ 성능(깊이 1)
def test_opening_a_folder_scans_only_one_level(app, tmp_path, monkeypatch):
    """폴더를 열 때 UI 스레드는 그 폴더 한 단계만 읽는다(재귀·자식별 스캔 금지).

    자식마다 한 번씩만 더 읽어도 폴더가 500개면 500번이라 창이 멈춘다. LOT 후보 판별은 그래서
    백그라운드로 미룬다 - 여기서는 메인 스레드가 만진 경로만 센다.
    """
    root = tmp_path / "scan"
    for i in range(40):  # 넓게(형제 40)
        deep = root / f"dev{i:02d}" / "lot" / "layer" / "wafer"
        deep.mkdir(parents=True)
        (deep / "shot.jpg").write_bytes(_JPEG)

    seen: list[str] = []
    real = os.scandir
    main = threading.main_thread()

    def spy(path="."):
        if threading.current_thread() is main:
            seen.append(str(path))
        return real(path)

    monkeypatch.setattr(os, "scandir", spy)
    dlg = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws")), str(root))
    seen.clear()
    dlg._go_to(root, push=False)

    inside = [p for p in seen if Path(p) != root and root in Path(p).parents]
    assert inside == [], f"현재 폴더 아래를 UI 스레드가 다시 읽었다: {inside[:5]}"
    # 현재 폴더 나열 + 트리 조상 확장 정도. 자식 수(40)와 무관하게 작아야 한다.
    assert len(seen) < 20, f"UI 스레드 scandir 호출이 너무 많다: {len(seen)}"
    dlg.deleteLater()


def test_probe_separates_lot_from_device_and_dead_ends(app, tmp_path):
    """판별은 하위 세 겹까지만 본다. 세 겹을 봐야 LOT 과 Device 가 갈린다."""
    lot = _make_lot(tmp_path, "LOT_A", layers=3, wafers=4)
    assert probe_folder(lot) == (RANK_LOT, "layer 3 · wafer 4")
    assert probe_folder(lot / "1. LY0")[0] == RANK_OTHER   # 하위가 사진 = layer
    assert probe_folder(lot / "1. LY0" / "W1")[0] == RANK_OTHER  # 사진뿐 = wafer
    device = _make_device(tmp_path, "DEV_X", lots=2)
    assert probe_folder(device) == (RANK_UNSURE, "LOT 2")  # LOT 후보로 올리지 않는다
    empty = tmp_path / "empty"
    empty.mkdir()
    assert probe_folder(empty) == (RANK_OTHER, "빈 폴더")


def test_probe_survives_a_junk_folder_in_first_position(app, tmp_path):
    """첫 하위가 잡폴더여도 오판하지 않는다(앞·가운데·뒤에서 표본을 뽑는다)."""
    lot = _make_lot(tmp_path, "LOT_B", layers=3, wafers=2)
    (lot / "00_요약").mkdir()  # 자연 정렬에서 맨 앞에 오는 빈 폴더
    assert probe_folder(lot)[0] == RANK_LOT


# ------------------------------------------------------------------ LOT 후보 우선
def test_lot_candidates_are_hoisted_above_other_folders(app, tmp_path):
    device = tmp_path / "DEVICE"
    device.mkdir()
    for name in ("zz_LOT", "mm_LOT", "aa_LOT"):
        _make_lot(device, name, layers=2, wafers=3)
    for name in ("00_docs", "01_report"):
        (device / name).mkdir()

    dlg = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws")), str(device))
    _settle()
    rows = _rows(dlg)
    assert rows[:3] == ["aa_LOT", "mm_LOT", "zz_LOT"], rows  # 후보가 위, 자연 정렬
    assert set(rows[3:]) == {"00_docs", "01_report"}       # 기타는 이름이 앞서도 아래로
    assert "기타 폴더" in _texts(dlg)
    assert dlg.lbl_candidates.text() == "LOT 후보 3"
    # 부제는 등폭 수치 - 이 자리에서 layer·wafer 개수를 미리 읽을 수 있어야 점프가 산다.
    item = dlg.listw.item(0)
    assert item.data(Qt.UserRole + 10) == "layer 2 · wafer 3"
    dlg.deleteLater()


def test_stale_probe_result_is_discarded(app, tmp_path):
    """폴더를 옮긴 뒤 도착한 판별 결과는 버린다(엉뚱한 폴더가 LOT 으로 표시되지 않게)."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    (first / "child").mkdir(parents=True)
    (second / "child").mkdir(parents=True)
    dlg = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws")), str(first))
    _settle()
    stale_token = dlg._probe_token
    dlg._go_to(second)
    _settle()
    dlg._on_probed(stale_token, str(first), {"child": (RANK_LOT, "layer 9 · wafer 9")})
    assert "layer 9 · wafer 9" not in [
        dlg.listw.item(i).data(Qt.UserRole + 10) for i in range(dlg.listw.count())
    ]
    dlg.deleteLater()


# ------------------------------------------------------------------ 즐겨찾기 / 최근
def test_favorites_accept_device_folders_only(app, tmp_path):
    device = _make_device(tmp_path, "DEV_A")
    lot = device / "DEV_A_LOT1"
    settings = AppSettings(workspace=str(tmp_path / "ws"))
    dlg = FolderPickerDialog(settings, str(tmp_path))

    assert dlg._add_favorite(device) is True
    assert settings.favorite_folders == [str(device)]
    # LOT 은 대상이 아니다(고정해 봐야 한 번 쓰고 버리는 경로다).
    assert dlg._add_favorite(lot) is False
    assert str(lot) not in settings.favorite_folders
    # 거절 사유는 하단 판정 행에 남는다.
    assert "Device" in dlg.lbl_verdict.text()
    dlg.deleteLater()


def test_favorites_stop_at_ten(app, tmp_path):
    settings = AppSettings(workspace=str(tmp_path / "ws"))
    dlg = FolderPickerDialog(settings, str(tmp_path))
    devices = [_make_device(tmp_path, f"DEV{i:02d}") for i in range(12)]
    for device in devices:
        assert dlg._add_favorite(device) is True
    assert len(settings.favorite_folders) == 10
    assert settings.favorite_folders[0] == str(devices[-1])  # 최근 추가가 앞
    assert str(devices[0]) not in settings.favorite_folders
    dlg.deleteLater()


def test_favorite_menu_is_disabled_outside_device_level(app, tmp_path):
    device = _make_device(tmp_path, "DEV_B")
    lot = device / "DEV_B_LOT1"
    dlg = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws")), str(device))

    add = [a for a in dlg._folder_menu(device).actions() if a.text() == "즐겨찾기에 추가"]
    assert add and add[0].isEnabled()
    add_lot = [a for a in dlg._folder_menu(lot).actions() if a.text() == "즐겨찾기에 추가"]
    assert add_lot and not add_lot[0].isEnabled()
    dlg.deleteLater()


def test_recent_stops_at_five(app, tmp_path):
    settings = AppSettings(workspace=str(tmp_path / "ws"))
    dlg = FolderPickerDialog(settings, str(tmp_path))
    for i in range(8):
        dlg._remember_recent(str(tmp_path / f"lot{i}"))
    assert settings.recent_folders == [str(tmp_path / f"lot{i}") for i in (7, 6, 5, 4, 3)]
    # 같은 폴더를 다시 열면 자리만 앞으로 옮긴다(중복 없음).
    dlg._remember_recent(str(tmp_path / "lot3"))
    assert settings.recent_folders[0] == str(tmp_path / "lot3")
    assert len(settings.recent_folders) == 5
    dlg.deleteLater()


def test_rail_shows_favorites_and_recents(app, tmp_path):
    device = _make_device(tmp_path, "DEV_C")
    settings = AppSettings(
        workspace=str(tmp_path / "ws"),
        favorite_folders=[str(device)],
        recent_folders=[str(device / "DEV_C_LOT1")],
    )
    dlg = FolderPickerDialog(settings, str(tmp_path))
    assert dlg.fav_list.item(0).data(Qt.UserRole) == str(device)
    assert dlg.recent_list.item(0).data(Qt.UserRole) == str(device / "DEV_C_LOT1")
    dlg.deleteLater()


def test_favorite_tip_is_shown_once_per_run(app, tmp_path, monkeypatch):
    """추가 방법 안내는 즐겨찾기가 비었을 때 실행당 한 번만 뜬다(반복 안내 금지)."""
    import app.ui.folder_picker as picker

    monkeypatch.setattr(picker, "_TIP_SHOWN", False)
    first = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws1")), str(tmp_path))
    first.show()
    QTest.qWait(120)
    _settle(1)
    assert first._tip is not None

    second = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws2")), str(tmp_path))
    second.show()
    QTest.qWait(120)
    _settle(1)
    assert second._tip is None
    # '추가 방법' 링크로는 언제든 다시 볼 수 있다.
    second._show_favorite_tip(force=True)
    assert second._tip is not None
    first.close()
    second.close()
    first.deleteLater()
    second.deleteLater()


# ------------------------------------------------------------------ LOT 보정
def test_layer_and_wafer_selection_correct_to_lot(app, tmp_path):
    lot = _make_lot(tmp_path, "LOT_C", layers=2, wafers=2)
    layer = lot / "1. LY0"
    wafer = layer / "W1"
    dlg = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws")), str(lot))

    dlg._set_candidate(layer)
    assert dlg.selected_path() == str(lot)
    dlg._set_candidate(wafer)
    assert dlg.selected_path() == str(lot)
    assert dlg.selected_wafer_folder() == str(wafer)
    dlg._set_candidate(lot)
    assert dlg.selected_path() == str(lot)
    assert dlg.selected_wafer_folder() == ""
    dlg.deleteLater()


def test_confirming_a_lot_records_it_as_recent(app, tmp_path):
    lot = _make_lot(tmp_path, "LOT_D")
    settings = AppSettings(workspace=str(tmp_path / "ws"))
    dlg = FolderPickerDialog(settings, str(lot))
    dlg._set_candidate(lot)
    dlg.accept()
    assert settings.recent_folders[:1] == [str(lot)]
    dlg.deleteLater()


# ------------------------------------------------------------------ 판정 행
def _verdict(dlg: FolderPickerDialog, kind: str, material: str = "", layers=0, wafers=0):
    dlg._candidate = Path(material or "/tmp/target")
    dlg._on_validated(dlg._token, kind, material, layers, wafers)
    return (dlg.chip.text(), dlg.lbl_verdict.text(), dlg.lbl_verdict_sub.text())


def test_verdict_row_changes_with_the_kind(app, tmp_path):
    lot = _make_lot(tmp_path, "LOT_E", layers=3, wafers=2)
    dlg = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws")), str(tmp_path))

    chip, msg, sub = _verdict(dlg, "material", str(lot), 3, 2)
    assert chip == "LOT" and sub == "layer 3 · wafer 2"
    assert dlg.btn_ok.isEnabled()

    chip_layer, msg_layer, _ = _verdict(dlg, "layer", str(lot), 3, 2)
    assert chip_layer == "LOT 보정" and "보정" in msg_layer
    assert dlg.btn_ok.isEnabled()

    chip_dev, msg_dev, _ = _verdict(dlg, "material_parent")
    assert chip_dev == "상위" and "Device" in msg_dev
    assert not dlg.btn_ok.isEnabled()

    chip_high, msg_high, _ = _verdict(dlg, "too_high")
    assert chip_high == "상위" and "상위 폴더" in msg_high
    assert not dlg.btn_ok.isEnabled()

    chip_unknown, msg_unknown, _ = _verdict(dlg, "unknown")
    assert chip_unknown == "?" and "사진" in msg_unknown
    assert dlg.btn_ok.isEnabled()  # 사진을 못 찾아도 선택 자체는 막지 않는다(계승)

    assert len({msg, msg_layer, msg_dev, msg_high, msg_unknown}) == 5
    dlg.deleteLater()


def test_verdict_reaches_the_result_through_the_background_worker(app, tmp_path):
    """후보를 고르면 '확인 중' 을 거쳐 실제 판정으로 바뀐다(디바운스 + 워커 + 토큰 경로)."""
    lot = _make_lot(tmp_path, "LOT_F", layers=2, wafers=2)
    dlg = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws")), str(tmp_path))
    dlg._set_candidate(lot)
    assert dlg.chip.text() == "확인"
    for _ in range(40):
        QTest.qWait(50)
        _settle(1)
        if dlg.chip.text() != "확인":
            break
    assert dlg.chip.text() == "LOT"
    assert dlg.lbl_verdict_sub.text() == "layer 2 · wafer 2"
    dlg.deleteLater()


def test_right_click_gate_stays_cheap_on_junk_trees(app, tmp_path, monkeypatch):
    """우클릭 메뉴의 Device 판별은 넓고 깊은 잡폴더에서도 몇 번만 읽는다.

    확정 판정(classify_selection)은 레벨마다 24개씩 훑어서 최악이 만 단위다. 그 대기를 메뉴에
    걸면 네트워크 드라이브에서 우클릭이 멈춘 것처럼 보인다.
    """
    junk = tmp_path / "junk"
    for i in range(20):
        for j in range(20):
            (junk / f"a{i:02d}" / f"b{j:02d}").mkdir(parents=True)
    dlg = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws")), str(tmp_path))

    calls: list[str] = []
    real = os.scandir
    main = threading.main_thread()

    def spy(path="."):
        if threading.current_thread() is main:
            calls.append(str(path))
        return real(path)

    monkeypatch.setattr(os, "scandir", spy)
    menu = dlg._folder_menu(junk)
    add = [a for a in menu.actions() if a.text() == "즐겨찾기에 추가"]
    assert add and not add[0].isEnabled()
    assert len(calls) <= 12, f"우클릭 한 번에 scandir {len(calls)}회"
    dlg.deleteLater()


def test_verdict_uses_color_on_the_chip_only(app, tmp_path):
    """색은 칩 하나에만. 원본은 배너 면 전체가 4색으로 바뀌었다."""
    from app.ui import theme

    dlg = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws")), str(tmp_path))
    _verdict(dlg, "material", str(tmp_path), 1, 1)
    tok = theme.fluent_tokens(isDarkTheme())
    assert theme.flatten(tok["pass"], tok["layer"]).lower() in dlg.chip.styleSheet().lower()
    # 사유·수치 줄에는 상태색이 없다.
    for color in ("pass", "warn", "danger"):
        assert theme.flatten(tok[color], tok["layer"]).lower() not in (
            dlg.styleSheet().lower()
        )
    dlg.deleteLater()


def test_verdict_numbers_are_monospaced(app, tmp_path):
    """layer n · wafer n 은 등폭이어야 자릿수가 바뀌어도 눈이 다시 자리를 찾지 않는다."""
    dlg = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws")), str(tmp_path))
    assert "monospace" in dlg.styleSheet()
    dlg.deleteLater()


# ------------------------------------------------------------------ 점프 3종
def test_breadcrumb_tracks_path_and_offers_siblings(app, tmp_path):
    base = tmp_path / "root"
    for name in ("aa", "bb", "cc"):
        (base / name).mkdir(parents=True)
    dlg = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws")), str(base / "bb"))

    assert dlg.crumbs.count() == len(Path(base / "bb").parts)
    assert dlg.crumbs.currentItem().text == "bb"
    menu = dlg._siblings_menu(str(base / "bb"))
    assert [a.text() for a in menu.actions()] == ["aa", "bb", "cc"]
    # 형제를 고르면 그 폴더로 간다.
    menu.actions()[2].trigger()
    assert dlg._cur == base / "cc"
    dlg.deleteLater()


def test_sibling_menu_is_capped_and_never_empty(app, tmp_path):
    """형제가 수백 개여도 메뉴는 잘라서 연다(메뉴가 화면을 넘기면 점프가 아니라 장애물이다)."""
    base = tmp_path / "many"
    for i in range(80):
        (base / f"f{i:03d}").mkdir(parents=True)
    dlg = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws")), str(base / "f000"))

    actions = dlg._siblings_menu(str(base / "f000")).actions()
    assert len(actions) == 61  # 60개 + 생략 안내
    assert not actions[-1].isEnabled() and "생략" in actions[-1].text()

    empty = tmp_path / "none"
    empty.mkdir()
    hollow = dlg._siblings_menu(str(empty / "child")).actions()
    assert [a.text() for a in hollow] == ["하위 폴더 없음"]
    dlg.deleteLater()


def test_search_filters_and_deep_toggle_adds_one_level(app, tmp_path):
    base = tmp_path / "root"
    (base / "alpha" / "alpha_child").mkdir(parents=True)
    (base / "alpha" / "alpha_child" / "too_deep").mkdir(parents=True)
    (base / "beta").mkdir()
    dlg = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws")), str(base))

    dlg._apply_filter("alpha")
    hidden = {
        dlg.listw.item(i).data(Qt.UserRole): dlg.listw.item(i).isHidden()
        for i in range(dlg.listw.count())
    }
    assert hidden.get("alpha") is False
    assert hidden.get("beta") is True

    # 검색어가 있을 때만 하위 한 겹을 더 나열한다(빈 검색어에 수천 행이 붙지 않게).
    dlg.ed_filter.setText("alpha")
    dlg.btn_deep.setChecked(True)
    _settle()
    names = _rows(dlg)
    assert os.path.join("alpha", "alpha_child") in names
    assert not any("too_deep" in n for n in names)  # 재귀는 하지 않는다
    dlg.deleteLater()


def test_scan_root_shortcut_is_pinned_on_top(app, tmp_path):
    target = tmp_path / "ScanData"
    target.mkdir()
    settings = AppSettings(workspace=str(tmp_path / "ws"), scan_root_path=str(target))
    dlg = FolderPickerDialog(settings, str(tmp_path))
    top = dlg.sidebar.topLevelItem(0)
    assert "ScanData" in top.text(0)
    assert top.data(0, Qt.UserRole) == str(target)
    dlg.deleteLater()


# ------------------------------------------------------------------ 테마
def test_sheet_repaints_on_theme_change(app, tmp_path):
    dlg = FolderPickerDialog(AppSettings(workspace=str(tmp_path / "ws")), str(tmp_path))
    light = dlg.styleSheet()
    try:
        setTheme(Theme.DARK)
        QCoreApplication.processEvents()
        dark = dlg.styleSheet()
        assert dark != light, "테마 전환에 시트 배경이 따라오지 않는다"
    finally:
        setTheme(Theme.LIGHT)
        QCoreApplication.processEvents()
    dlg.deleteLater()


def test_copy_has_no_emoji_or_em_dash():
    """카피 규칙: 이모지 0건, em-dash 0건(코드·주석·docstring 전부).

    금지 문자를 그대로 적으면 이 파일이 규칙을 어기게 되므로 코드포인트로만 쓴다.
    """
    source = Path(__file__).resolve().parent.parent / "app" / "ui" / "folder_picker.py"
    text = source.read_text(encoding="utf-8")
    assert "\u2014" not in text  # em-dash
    # 원본에 있던 장식 문자들(별·압정·집·디스켓·지구본·회전화살표·폴더).
    legacy = {0x2605, 0x2606, 0x21BB, 0x1F4CC, 0x1F3E0, 0x1F4BE, 0x1F310, 0x1F5C2, 0x1F4C1}
    bad = [hex(ord(ch)) for ch in text if ord(ch) >= 0x1F300 or ord(ch) in legacy]
    assert bad == [], f"이모지가 남아 있다: {bad[:5]}"
