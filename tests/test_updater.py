"""자동 업데이트 로직 테스트 (네트워크 없음 — opener 주입/로컬 zip)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from app import updater


def _make_zip(tmp_path: Path, files: dict[str, str], top: str = "repo-main") -> Path:
    """최상위 폴더 top/ 를 가진 zip 을 만든다(GitHub archive 형태)."""
    zp = tmp_path / "main.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        for rel, content in files.items():
            zf.writestr(f"{top}/{rel}", content)
    return zp


def test_extract_over_overwrites_and_adds(tmp_path):
    target = tmp_path / "install"
    (target / "app").mkdir(parents=True)
    (target / "app" / "old.py").write_text("OLD", encoding="utf-8")
    (target / "user_data.txt").write_text("KEEP", encoding="utf-8")

    zp = _make_zip(tmp_path, {
        "main.py": "print('new')",
        "app/old.py": "NEW",
        "app/new.py": "added",
    })
    written = updater.extract_over(zp, target)

    assert written == 3
    assert (target / "main.py").read_text() == "print('new')"
    assert (target / "app" / "old.py").read_text() == "NEW"  # 덮어쓰기
    assert (target / "app" / "new.py").read_text() == "added"  # 추가
    assert (target / "user_data.txt").read_text() == "KEEP"  # 미삭제


def test_extract_over_skips_protected_dirs(tmp_path):
    target = tmp_path / "install"
    target.mkdir()
    zp = _make_zip(tmp_path, {
        ".git/config": "should-skip",
        "app/__pycache__/x.pyc": "skip",
        "app/keep.py": "keep",
    })
    updater.extract_over(zp, target)
    assert not (target / ".git").exists()
    assert not (target / "app" / "__pycache__").exists()
    assert (target / "app" / "keep.py").exists()


def test_extract_over_ships_only_runtime_essentials(tmp_path):
    """자동 업데이트(ZIP)는 실행 필수 파일만 배포하고 개발/부가 리소스는 모두 제외한다.

    배포 대상: app/·main.py·bootstrap.py·requirements.txt
    제외 대상: .claude·tests·tools·.github·build_exe.py·개발 문서·.gitignore
    """
    target = tmp_path / "install"
    target.mkdir()
    zp = _make_zip(tmp_path, {
        # 개발/부가 → 제외
        ".claude/skills/impeccable/SKILL.md": "skill",
        "tests/test_x.py": "dev-test",
        "tools/compute_version.py": "dev-tool",
        ".github/workflows/ci.yml": "ci",
        "build_exe.py": "dev-build",
        "CLAUDE.md": "dev-doc",
        ".gitignore": "gitcfg",
        # 실행 필수 → 배포
        "app/keep.py": "keep",
        "main.py": "entry",
        "bootstrap.py": "boot",
        "requirements.txt": "PySide6>=6.6",
    })
    updater.extract_over(zp, target)
    for gone in (".claude", "tests", "tools", ".github",
                 "build_exe.py", "CLAUDE.md", ".gitignore"):
        assert not (target / gone).exists(), f"{gone} 는 배포본에 없어야 함"
    for kept, content in (("app/keep.py", "keep"), ("main.py", "entry"),
                          ("bootstrap.py", "boot"), ("requirements.txt", "PySide6>=6.6")):
        assert (target / kept).read_text() == content, f"{kept} 는 배포되어야 함"


def test_extract_over_skips_dev_docs(tmp_path):
    """자동 업데이트(ZIP)로 CLAUDE.md·README.md 는 받아오지 않는다(로컬 유지)."""
    target = tmp_path / "install"
    target.mkdir()
    (target / "README.md").write_text("LOCAL-README", encoding="utf-8")
    (target / "CLAUDE.md").write_text("LOCAL-CLAUDE", encoding="utf-8")
    zp = _make_zip(tmp_path, {
        "README.md": "REMOTE-README",
        "CLAUDE.md": "REMOTE-CLAUDE",
        "app/keep.py": "keep",
    })
    updater.extract_over(zp, target)
    # 문서는 원격 내용으로 덮이지 않고 로컬 그대로여야 한다.
    assert (target / "README.md").read_text() == "LOCAL-README"
    assert (target / "CLAUDE.md").read_text() == "LOCAL-CLAUDE"
    assert (target / "app" / "keep.py").read_text() == "keep"  # 나머지는 정상 적용


def test_extract_over_zip_slip_blocked(tmp_path):
    target = tmp_path / "install"
    target.mkdir()
    zp = tmp_path / "evil.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("repo-main/../escape.py", "evil")
    updater.extract_over(zp, target)
    assert not (tmp_path / "escape.py").exists()


def test_version_roundtrip(tmp_path):
    updater.write_version(tmp_path, "abc123")
    assert updater.read_version(tmp_path) == "abc123"


def test_current_sha_from_version_json(tmp_path):
    # git 체크아웃이 아닌 폴더 → version.json 사용
    updater.write_version(tmp_path, "deadbeef")
    assert updater.current_sha(tmp_path) == "deadbeef"


def test_read_installed_version_parses_dunder_version(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text(
        '"""docstring"""\n__version__ = "1.42.7"\n', encoding="utf-8"
    )
    assert updater.read_installed_version(tmp_path) == "1.42.7"


def test_read_installed_version_missing_file_returns_none(tmp_path):
    assert updater.read_installed_version(tmp_path) is None


def test_fetch_remote_sha_parses_json():
    class FakeResp:
        def __init__(self, payload):
            self._p = payload.encode("utf-8")
        def read(self):
            return self._p
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake_opener(req, timeout=0):
        return FakeResp(json.dumps({"sha": "1234abcd"}))

    sha = updater.fetch_remote_sha("o", "r", "main", opener=fake_opener)
    assert sha == "1234abcd"


def test_check_update_available(tmp_path):
    updater.write_version(tmp_path, "localsha")

    def fake_opener(req, timeout=0):
        class R:
            def read(self_inner):
                return json.dumps({"sha": "remotesha"}).encode()
            def __enter__(self_inner):
                return self_inner
            def __exit__(self_inner, *a):
                return False
        return R()

    st = updater.check_update(root=tmp_path, opener=fake_opener)
    assert st.available is True
    assert st.local == "localsha" and st.remote == "remotesha"
    assert st.method == "zip"


def test_check_update_up_to_date(tmp_path):
    updater.write_version(tmp_path, "samesha")

    def fake_opener(req, timeout=0):
        class R:
            def read(self_inner):
                return json.dumps({"sha": "samesha"}).encode()
            def __enter__(self_inner):
                return self_inner
            def __exit__(self_inner, *a):
                return False
        return R()

    st = updater.check_update(root=tmp_path, opener=fake_opener)
    assert st.available is False


def test_check_update_network_error_graceful(tmp_path):
    def boom(req, timeout=0):
        raise OSError("no network")

    st = updater.check_update(root=tmp_path, opener=boom)
    assert st.available is False
    assert st.error


def test_apply_via_zip_updates_only_target(tmp_path):
    target = tmp_path / "install"
    target.mkdir()
    real_root_marker = tmp_path / "REAL_ROOT_UNTOUCHED"
    real_root_marker.write_text("x")

    zp = _make_zip(tmp_path, {"main.py": "v2", "app/x.py": "y"})

    def fake_opener(req, timeout=0):
        # download_zip 은 응답 객체를 copyfileobj 로 읽는다 → file-like 반환
        return open(zp, "rb")

    ok, msg = updater.apply_via_zip(
        target, owner="o", repo="r", branch="main",
        remote_sha="newsha", opener=fake_opener,
    )
    assert ok is True
    assert (target / "main.py").read_text() == "v2"
    assert updater.read_version(target) == "newsha"
    # 실제 루트(여기선 tmp_path)에 다른 파일은 그대로
    assert real_root_marker.read_text() == "x"
