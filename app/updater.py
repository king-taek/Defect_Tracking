"""자동 업데이트 — 메인 브랜치를 가져와 적용.

설치 형태에 따라 자동 감지:
  - git 체크아웃(.git 존재 + git 설치) → git fetch + reset --hard origin/main
  - 그 외 → GitHub codeload 에서 main ZIP 을 받아 설치 폴더에 덮어쓰기

순수 함수로 분리(네트워크/Qt 없이 테스트 가능)하고, Qt 워커가 이를 감싼다.
사용자 작업공간(LOCALAPPDATA)은 건드리지 않으며, 앱 설치 폴더만 갱신한다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.request import Request, urlopen

from app import config

ProgressCb = Optional[Callable[[str], None]]

# ZIP 추출 시 덮어쓰지 않을 최상위 폴더
_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv"}

_API = "https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
_ZIP = "https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{branch}"


@dataclass
class UpdateStatus:
    available: bool
    local: Optional[str]
    remote: Optional[str]
    method: str  # "git" | "zip"
    error: Optional[str] = None


# ----------------------------------------------------------------- 경로/버전
def app_root() -> Path:
    """설치 루트(이 파일의 상위의 상위)."""
    return Path(__file__).resolve().parents[1]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def git_available() -> bool:
    return shutil.which("git") is not None


def is_git_checkout(root: Path) -> bool:
    return (root / ".git").exists() and git_available()


def version_file(root: Path) -> Path:
    return root / "version.json"


def read_version(root: Path) -> Optional[str]:
    vf = version_file(root)
    if vf.exists():
        try:
            return json.loads(vf.read_text(encoding="utf-8")).get("commit")
        except (json.JSONDecodeError, OSError):
            return None
    return None


def write_version(root: Path, sha: str) -> None:
    version_file(root).write_text(
        json.dumps({"commit": sha}, indent=2), encoding="utf-8"
    )


def current_sha(root: Optional[Path] = None) -> Optional[str]:
    """현재 설치본의 커밋 sha (git 우선, 없으면 version.json)."""
    root = root or app_root()
    if is_git_checkout(root):
        try:
            out = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=15,
            )
            if out.returncode == 0:
                return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return read_version(root)


# -------------------------------------------------------------------- 원격
def fetch_remote_sha(
    owner: str,
    repo: str,
    branch: str,
    token: str = "",
    opener=urlopen,
    timeout: float = 10.0,
) -> Optional[str]:
    """GitHub API 로 브랜치 최신 커밋 sha 를 가져온다(public 무인증)."""
    url = _API.format(owner=owner, repo=repo, branch=branch)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Defect Tracker"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    with opener(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    sha = data.get("sha")
    return sha if isinstance(sha, str) and sha else None


def check_update(
    root: Optional[Path] = None,
    owner: str = config.UPDATE_OWNER,
    repo: str = config.UPDATE_REPO,
    branch: str = config.UPDATE_BRANCH,
    token: str = "",
    opener=urlopen,
) -> UpdateStatus:
    """업데이트 가능 여부를 판정(백그라운드 호출용, 예외는 error 로 흡수)."""
    root = root or app_root()
    method = "git" if is_git_checkout(root) else "zip"
    local = current_sha(root)
    try:
        remote = fetch_remote_sha(owner, repo, branch, token, opener)
    except Exception as exc:  # noqa: BLE001 - 네트워크/파싱 오류는 graceful
        return UpdateStatus(False, local, None, method, error=str(exc))
    if remote is None:
        return UpdateStatus(False, local, None, method, error="원격 버전 확인 실패")
    available = local is None or (local[:40] != remote[:40])
    return UpdateStatus(available, local, remote, method)


# --------------------------------------------------------------- 적용(git)
def apply_via_git(
    root: Path, branch: str = config.UPDATE_BRANCH, progress: ProgressCb = None
) -> tuple[bool, str]:
    """git fetch + reset --hard origin/branch 로 메인을 그대로 반영."""
    def run(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=180,
        )

    if progress:
        progress("원격 변경사항 받는 중...")
    f = run(["fetch", "--depth", "1", "origin", branch])
    if f.returncode != 0:
        return False, f"git fetch 실패: {f.stderr.strip()}"
    if progress:
        progress("최신 버전 적용 중...")
    r = run(["reset", "--hard", f"origin/{branch}"])
    if r.returncode != 0:
        return False, f"git reset 실패: {r.stderr.strip()}"
    return True, "git 으로 업데이트했습니다."


# --------------------------------------------------------------- 적용(ZIP)
def download_zip(url: str, dest: Path, opener=urlopen, timeout: float = 60.0) -> Path:
    req = Request(url, headers={"User-Agent": "Defect Tracker"})
    with opener(req, timeout=timeout) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)
    return dest


def _safe_join(target_root: Path, rel: str) -> Optional[Path]:
    """zip-slip 방지: target_root 밖으로 나가는 경로는 None."""
    dest = (target_root / rel).resolve()
    root = target_root.resolve()
    if dest == root or root in dest.parents:
        return dest
    return None


def extract_over(
    zip_path: Path, target_root: Path, skip: Optional[set[str]] = None
) -> int:
    """ZIP(최상위 단일 폴더)을 target_root 에 덮어쓴다(삭제는 하지 않음).

    Returns: 기록한 파일 수.
    """
    skip = skip if skip is not None else _SKIP_DIRS
    written = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = Path(info.filename).parts
            if len(parts) <= 1:
                continue  # 최상위 폴더 자체
            rel_parts = parts[1:]  # 'repo-branch/' 접두 제거
            if any(p in skip for p in rel_parts):
                continue
            rel = "/".join(rel_parts)
            dest = _safe_join(target_root, rel)
            if dest is None:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            written += 1
    return written


def apply_via_zip(
    target_root: Path,
    owner: str = config.UPDATE_OWNER,
    repo: str = config.UPDATE_REPO,
    branch: str = config.UPDATE_BRANCH,
    remote_sha: Optional[str] = None,
    opener=urlopen,
    progress: ProgressCb = None,
) -> tuple[bool, str]:
    """ZIP 을 받아 설치 폴더에 덮어쓰고 version.json 을 기록."""
    url = _ZIP.format(owner=owner, repo=repo, branch=branch)
    tmpdir = Path(tempfile.mkdtemp(prefix="defect_tracker_update_"))
    try:
        if progress:
            progress("새 버전 내려받는 중...")
        zip_path = download_zip(url, tmpdir / "main.zip", opener)
        if progress:
            progress("설치 폴더에 적용 중...")
        count = extract_over(zip_path, target_root)
        if count == 0:
            return False, "받은 패키지에 적용할 파일이 없습니다."
        if remote_sha:
            write_version(target_root, remote_sha)
        return True, f"{count}개 파일을 갱신했습니다."
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def apply_update(
    status: UpdateStatus,
    root: Optional[Path] = None,
    owner: str = config.UPDATE_OWNER,
    repo: str = config.UPDATE_REPO,
    branch: str = config.UPDATE_BRANCH,
    opener=urlopen,
    progress: ProgressCb = None,
) -> tuple[bool, str]:
    """감지된 방식(method)에 따라 업데이트를 적용."""
    root = root or app_root()
    if is_frozen():
        return False, "실행파일(exe) 버전은 자동 업데이트를 지원하지 않습니다. 새 버전을 내려받아 교체하세요."
    if status.method == "git" and is_git_checkout(root):
        return apply_via_git(root, branch, progress)
    return apply_via_zip(
        root, owner, repo, branch, remote_sha=status.remote, opener=opener, progress=progress
    )


# ----------------------------------------------------------------- Qt 워커
try:
    from PySide6.QtCore import QObject, QRunnable, Signal, Slot

    class UpdateCheckSignals(QObject):
        done = Signal(object)  # UpdateStatus

    class UpdateCheckWorker(QRunnable):
        """시작 시 백그라운드로 업데이트 여부 확인."""

        def __init__(self, token: str = ""):
            super().__init__()
            self.token = token
            self.signals = UpdateCheckSignals()

        @Slot()
        def run(self) -> None:
            status = check_update(token=self.token)
            self.signals.done.emit(status)

    class UpdateApplySignals(QObject):
        progress = Signal(str)
        finished = Signal(bool, str)  # ok, message

    class UpdateApplyWorker(QRunnable):
        """업데이트 적용(진행 상황 신호)."""

        def __init__(self, status: UpdateStatus, token: str = ""):
            super().__init__()
            self.status = status
            self.token = token
            self.signals = UpdateApplySignals()

        @Slot()
        def run(self) -> None:
            try:
                ok, msg = apply_update(
                    self.status, progress=self.signals.progress.emit
                )
            except Exception as exc:  # noqa: BLE001
                ok, msg = False, f"업데이트 중 오류: {exc}"
            self.signals.finished.emit(ok, msg)

except ImportError:  # PySide6 미설치 환경(부트스트랩 전)
    pass
