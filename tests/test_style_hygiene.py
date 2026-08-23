"""스타일 위생 정적 검사.

Fluent 위젯은 qfluentwidgets 가 위젯 단위 스타일시트로 칠한다. 거기에 `setStyleSheet()` 를
직접 부르면 그 시트를 통째로 갈아치워 테마 전환·hover·포커스 표시가 조용히 사라진다. 화면에서
바로 안 보이고 다크로 바꿀 때나 드러나므로 사람 눈으로는 못 잡는다. 그래서 정적으로 막는다.

대상은 **qfluentwidgets 파생 객체로 한정**한다(PLAN-FINAL P3). 순수 Qt 위젯에는 직접 호출이
정상이고, `theme.py` 는 QSS 문자열을 만드는 곳이라 allowlist 다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytest.importorskip("qfluentwidgets")

import qfluentwidgets  # noqa: E402

APP = Path(__file__).resolve().parent.parent / "app"

# QSS 문자열을 만들거나 레거시 테마를 들고 있는 곳. 여기서는 직접 호출이 목적 그 자체다.
ALLOWLIST = {"theme.py"}

# Fluent 위젯이 아니지만 이름이 겹칠 수 있는 것들(경로 문자열 등)은 생성자 이름으로만 본다.
_FLUENT_NAMES = {
    name for name in dir(qfluentwidgets)
    if isinstance(getattr(qfluentwidgets, name, None), type)
}


def _modules() -> list[Path]:
    return sorted(p for p in APP.rglob("*.py") if p.name != "__init__.py")


def _class_bases(tree: ast.AST) -> dict[str, set[str]]:
    """모듈 안 클래스 이름 -> 베이스 이름 집합."""
    out: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = set()
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.add(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.add(base.attr)
            out[node.name] = bases
    return out


def _fluent_derived(trees: dict[Path, ast.AST]) -> set[str]:
    """qfluentwidgets 에서 내려온 클래스 이름 전체(앱 안의 하위 클래스 포함)."""
    derived = set(_FLUENT_NAMES)
    all_bases: dict[str, set[str]] = {}
    for tree in trees.values():
        all_bases.update(_class_bases(tree))
    # 상속이 여러 단계일 수 있으므로 더 늘지 않을 때까지 돈다.
    changed = True
    while changed:
        changed = False
        for name, bases in all_bases.items():
            if name not in derived and bases & derived:
                derived.add(name)
                changed = True
    return derived


def _ctor_name(value: ast.AST) -> str | None:
    """대입 우변이 생성자 호출이면 그 클래스 이름."""
    if not isinstance(value, ast.Call):
        return None
    func = value.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _violations(path: Path, tree: ast.AST, derived: set[str]) -> list[str]:
    found: list[str] = []
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        cls_is_fluent = cls.name in derived
        # self.<attr> = Fluent(...) 로 만든 속성을 모은다.
        attrs: dict[str, str] = {}
        for node in ast.walk(cls):
            if isinstance(node, ast.Assign):
                name = _ctor_name(node.value)
                if name is None:
                    continue
                for target in node.targets:
                    if (isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"):
                        attrs[target.attr] = name
        for func in [n for n in ast.walk(cls)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            # 같은 함수 안에서 지역 변수로 만든 Fluent 위젯도 본다.
            locals_: dict[str, str] = {}
            for node in ast.walk(func):
                if isinstance(node, ast.Assign):
                    name = _ctor_name(node.value)
                    if name is None:
                        continue
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            locals_[target.id] = name
            for node in ast.walk(func):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "setStyleSheet"):
                    continue
                target = node.func.value
                hit = None
                if isinstance(target, ast.Name):
                    if target.id == "self" and cls_is_fluent:
                        hit = cls.name
                    elif locals_.get(target.id) in derived:
                        hit = locals_[target.id]
                elif (isinstance(target, ast.Attribute)
                      and isinstance(target.value, ast.Name)
                      and target.value.id == "self"
                      and attrs.get(target.attr) in derived):
                    hit = attrs[target.attr]
                if hit:
                    found.append(f"{path.name}:{node.lineno} {ast.unparse(target)} ({hit})")
    return found


@pytest.fixture(scope="module")
def parsed() -> dict[Path, ast.AST]:
    return {p: ast.parse(p.read_text(encoding="utf-8")) for p in _modules()}


def test_fluent_widgets_are_not_restyled_directly(parsed):
    """Fluent 위젯에는 setCustomStyleSheet 를 쓴다. setStyleSheet 는 시트를 덮어쓴다."""
    derived = _fluent_derived(parsed)
    hits: list[str] = []
    for path, tree in parsed.items():
        if path.name in ALLOWLIST:
            continue
        hits.extend(_violations(path, tree, derived))
    assert not hits, (
        "Fluent 위젯에 setStyleSheet 직접 호출:\n  " + "\n  ".join(hits)
        + "\nsetCustomStyleSheet(w, light, dark) 를 쓰세요."
    )


def test_the_check_can_actually_see_a_violation():
    """검사기 자체가 죽어 있으면 위 테스트는 항상 통과한다. 가짜 위반으로 확인한다."""
    src = (
        "from qfluentwidgets import PushButton\n"
        "class Bad(PushButton):\n"
        "    def paint(self):\n"
        "        self.setStyleSheet('color: red')\n"
    )
    tree = ast.parse(src)
    derived = _fluent_derived({Path("fake.py"): tree})
    assert _violations(Path("fake.py"), tree, derived)
