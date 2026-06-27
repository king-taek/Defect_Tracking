"""의존성 점검·설치 스크립트 (Windows/uv/PEP 668 대응).

프로그램 실행에 필요한 라이브러리가 설치되어 있는지 확인하고, 없으면 자동으로 설치한다.
표준 라이브러리만 사용한다.

사용:
    python bootstrap.py           # 현재 파이썬에 설치(여러 방법 자동 시도)
    python bootstrap.py --check   # 점검만
    python bootstrap.py --venv    # .venv 가상환경을 만들고 거기에 설치(가장 안전)

설치 후 실행:
    python main.py
    (또는 --venv 사용 시 안내되는 경로의 python 으로 main.py 실행)
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

# import 이름 -> requirements 표기(설치 이름/버전)
REQUIRED: dict[str, str] = {
    "PySide6": "PySide6>=6.6",
    "PIL": "Pillow>=10.0",
    "openpyxl": "openpyxl>=3.1",
}

ROOT = Path(__file__).resolve().parent
REQUIREMENTS_FILE = ROOT / "requirements.txt"
VENV_DIR = ROOT / ".venv"
# PySide6 휠이 안정적으로 제공되는 권장 파이썬(가상환경용)
RECOMMENDED_PY = "3.12"


# ----------------------------------------------------------------- 점검
def missing_modules() -> list[str]:
    """현재 인터프리터에서 설치되지 않은 import 이름 목록."""
    return [n for n in REQUIRED if importlib.util.find_spec(n) is None]


def verify_installed(python: str) -> list[str]:
    """설치 후 점검은 새 인터프리터 프로세스로 수행(현재 프로세스 sys.path 캐시 회피)."""
    names = ",".join(REQUIRED)
    code = (
        "import importlib.util as u;"
        f"print(','.join(n for n in '{names}'.split(',') if u.find_spec(n) is None))"
    )
    try:
        out = subprocess.run(
            [python, "-c", code], capture_output=True, text=True, timeout=30
        )
        return [n for n in out.stdout.strip().split(",") if n]
    except (OSError, subprocess.SubprocessError):
        return list(REQUIRED)


def _target_args() -> list[str]:
    if REQUIREMENTS_FILE.exists():
        return ["-r", str(REQUIREMENTS_FILE)]
    return list(REQUIRED.values())


def is_externally_managed() -> bool:
    """PEP 668: stdlib 에 EXTERNALLY-MANAGED 표식이 있으면 True (uv/배포판 관리 환경)."""
    try:
        stdlib = sysconfig.get_path("stdlib")
        return stdlib is not None and os.path.exists(
            os.path.join(stdlib, "EXTERNALLY-MANAGED")
        )
    except OSError:
        return False


def _uv() -> str | None:
    return shutil.which("uv")


def _run(cmd: list[str]) -> int:
    print("\n실행:", " ".join(cmd))
    try:
        return subprocess.call(cmd)
    except OSError as exc:
        print("  (실행 실패:", exc, ")")
        return 1


# --------------------------------------------------- 현재 파이썬에 설치
def install_strategies(python: str) -> list[list[str]]:
    """설치 명령 후보를 우선순위대로 만든다(환경에 따라 자동 선택)."""
    target = _target_args()
    cmds: list[list[str]] = []
    uv = _uv()
    managed = is_externally_managed()

    if uv:
        # uv 가 관리하는 파이썬에는 uv 로 설치하는 것이 가장 자연스럽다.
        cmds.append([uv, "pip", "install", "--python", python, *target])
        cmds.append([uv, "pip", "install", "--system", "--python", python, *target])

    pip = [python, "-m", "pip", "install"]
    if managed:
        # PEP 668 환경: 명시적으로 override
        cmds.append([*pip, "--break-system-packages", *target])
        cmds.append([*pip, "--user", "--break-system-packages", *target])
    else:
        cmds.append([*pip, *target])
        cmds.append([*pip, "--user", *target])
    return cmds


def install_in_place() -> int:
    for cmd in install_strategies(sys.executable):
        rc = _run(cmd)
        if rc == 0 and not verify_installed(sys.executable):
            return 0
        print("  → 이 방법은 실패했습니다. 다음 방법을 시도합니다.")
    return 1


# ----------------------------------------------------- 가상환경에 설치
def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def install_in_venv() -> int:
    """uv(권장) 또는 표준 venv 로 .venv 를 만들고 거기에 설치한다."""
    uv = _uv()
    if uv:
        print(f"uv 로 가상환경 생성(파이썬 {RECOMMENDED_PY})...")
        if _run([uv, "venv", "--python", RECOMMENDED_PY, str(VENV_DIR)]) != 0:
            # 권장 버전 다운로드/생성 실패 시 현재 파이썬으로라도 생성
            if _run([uv, "venv", str(VENV_DIR)]) != 0:
                print("✗ 가상환경 생성 실패")
                return 1
        vpy = _venv_python(VENV_DIR)
        if _run([uv, "pip", "install", "--python", str(vpy), *_target_args()]) != 0:
            print("✗ 가상환경 의존성 설치 실패")
            return 1
    else:
        print("표준 venv 로 가상환경 생성...")
        if _run([sys.executable, "-m", "venv", str(VENV_DIR)]) != 0:
            print("✗ 가상환경 생성 실패")
            return 1
        vpy = _venv_python(VENV_DIR)
        if _run([str(vpy), "-m", "pip", "install", "--upgrade", "pip"]) != 0:
            pass  # pip 업그레이드 실패는 치명적이지 않음
        if _run([str(vpy), "-m", "pip", "install", *_target_args()]) != 0:
            print("✗ 가상환경 의존성 설치 실패")
            return 1

    vpy = _venv_python(VENV_DIR)
    if verify_installed(str(vpy)):
        print("✗ 설치 후에도 일부 라이브러리가 누락되었습니다.")
        return 1
    print("\n✓ 가상환경 준비 완료. 다음 명령으로 실행하세요:")
    print(f'    "{vpy}" main.py')
    return 0


# ----------------------------------------------------------------- 안내
def _print_failure_help() -> None:
    print("\n자동 설치에 실패했습니다. 다음을 시도하세요:")
    if sys.version_info >= (3, 14):
        print(
            f"  · 현재 파이썬 {sys.version.split()[0]} 은(는) 매우 최신이라 PySide6 휠이\n"
            f"    아직 없을 수 있습니다. 권장 파이썬({RECOMMENDED_PY})으로 가상환경을 만드세요:\n"
            "        python bootstrap.py --venv"
        )
    else:
        print("  · 가상환경에 설치(권장):\n        python bootstrap.py --venv")
    print(
        "  · 또는 현재 파이썬에 강제 설치:\n"
        "        python -m pip install --break-system-packages -r requirements.txt"
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    print(f"Python: {sys.version.split()[0]}  ({sys.executable})")
    if is_externally_managed():
        print("환경: 외부 관리(PEP 668, 예: uv) — 적절한 설치 옵션을 자동 선택합니다.")

    if "--venv" in argv:
        return install_in_venv()

    missing = missing_modules()
    if not missing:
        print("✓ 모든 의존성이 충족되었습니다. `python main.py` 로 실행하세요.")
        return 0

    print("누락된 라이브러리:", ", ".join(REQUIRED[m] for m in missing))
    if "--check" in argv:
        print("`python bootstrap.py` 를 실행하면 자동 설치합니다.")
        return 1

    if sys.version_info >= (3, 14):
        print(
            f"주의: 파이썬 {sys.version.split()[0]} 은 최신이라 일부 라이브러리 휠이 없을 수 있습니다. "
            "실패하면 `python bootstrap.py --venv` 를 권장합니다."
        )

    if install_in_place() == 0:
        print("\n✓ 설치 완료. `python main.py` 로 실행하세요.")
        return 0

    _print_failure_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
