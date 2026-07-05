"""모듈식 소스(`app/` + `main.py`)에서 읽을 수 있는 단일 파일을 생성한다.

이 도구는 `app/**/*.py` 와 `main.py` 를 위상순서로 이어붙여 하나의 평문 `.py`
(`single_file/defect_tracker.py`)를 만든다. 단일 파일은 **산출물**이며, 소스의 진실은
계속 `app/` + `main.py` 다. 생성기는 소스를 절대 수정하지 않고, 모든 변형을 메모리에서만 한다.

사용:
    python tools/build_single_file.py            # 기본 위치에 생성
    python tools/build_single_file.py --check     # 커밋본이 최신인지 확인(다르면 종료코드 1)
    python tools/build_single_file.py -o PATH     # 지정 경로에 생성

왜 단순 concat 이 아닌가(핵심 변형):
  1. 네임스페이스 접두어 제거: `from app import config` → `config.X` 를 `X` 로(평문엔 config 없음).
     `config._active_product` 는 살아있는 전역이라 스냅샷이 아니라 elision 이어야 함.
  2. Form1 별칭(`X as _Y`)은 삭제가 아니라 `_Y = X` 방출(하위호환 별칭).
  3. 최상위 이름 충돌(예: 6개 모듈의 `_log`)을 `<모듈>__<이름>` 으로 리네임. 새 충돌은 빌드 실패.
  4. import 호이스팅 + `from __future__` 1회 + 의존성 프리앰블(친절한 안내 UX 보존).
  5. `__file__` 경로 보정 2곳(config 데이터 DB, updater app_root).

col_offset 은 UTF-8 바이트 오프셋이므로 한글이 섞인 소스에서 정확하도록 **바이트 단위**로 편집한다.
모든 편집은 잘라낸 바이트가 예상과 일치하는지 assert 해 조용한 손상 대신 실패하게 만든다.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
MAIN_PY = ROOT / "main.py"
DEFAULT_OUT = ROOT / "single_file" / "defect_tracker.py"

# 알려진(이미 처리한) 최상위 이름 충돌. 이 목록 밖의 새 충돌이 생기면 빌드를 실패시킨다.
KNOWN_COLLISIONS = {
    "_log",
    "_norm_wafer",
    "_read_text",
    "ProgressCb",
    "_COLUMNS",
    "_THUMB_PX",
    "_NUM_RE",
    "_MAX_LOG_SIZE",
}

# __file__ 기반 경로 계산 보정. (dotted 모듈, 원본 조각, 대체 조각)
#   단일 파일은 app/ 보다 한 단계 얕으므로 parent 깊이를 조정하고, 자기 위치/CWD 로 degrade.
FILE_FIXUPS = {
    "app.config": [
        (
            'repo_root = Path(__file__).resolve().parent.parent\n'
            '    candidates.append(repo_root / "data" / "AOIDeviceDB.xlsx")',
            '# 단일 파일 배포: 파일 자기 디렉터리 및 CWD 기준으로 data/ 탐색(없으면 미로드).\n'
            '    _here = Path(__file__).resolve().parent\n'
            '    candidates.append(_here / "data" / "AOIDeviceDB.xlsx")\n'
            '    candidates.append(Path.cwd() / "data" / "AOIDeviceDB.xlsx")',
        )
    ],
    "app.updater": [
        (
            "return Path(__file__).resolve().parents[1]",
            "return Path(__file__).resolve().parent  # 단일 파일: 자기 디렉터리를 설치 루트로 본다",
        )
    ],
}

STDLIB = set(sys.stdlib_module_names)


# ---------------------------------------------------------------- 모듈 탐색/순서
def _dotted(path: Path) -> str:
    rel = path.resolve().relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_trivial(tree: ast.Module) -> bool:
    """docstring/`pass` 만 있는(내용 없는) 모듈인가."""
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if isinstance(node, ast.Pass):
            continue
        return False
    return True


def discover() -> tuple[dict[str, Path], set[str]]:
    """(app 모듈 dotted→경로, 패키지 dotted 집합)."""
    modules: dict[str, Path] = {}
    packages: set[str] = set()
    for path in sorted(APP_DIR.rglob("*.py")):
        dotted = _dotted(path)
        if path.name == "__init__.py":
            packages.add(dotted)
        else:
            modules[dotted] = path
    return modules, packages


def module_edges(tree: ast.Module, modules: dict[str, Path], packages: set[str]) -> set[str]:
    """모듈 레벨 `from app...` 의존(먼저 방출돼야 하는 app 모듈들). 함수 내부 import 은 제외."""
    deps: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        mod = node.module or ""
        if mod in modules:  # Form1: from app.x import ...
            deps.add(mod)
        elif mod in packages:  # Form2: from app import x  /  from app.ui import theme
            for alias in node.names:
                full = f"{mod}.{alias.name}"
                if full in modules:
                    deps.add(full)
    return deps


def topo_order(modules: dict[str, Path]) -> list[str]:
    """leaf 우선 위상정렬. 동률은 dotted 이름으로 tie-break(결정적)."""
    _, packages = discover()
    edges: dict[str, set[str]] = {}
    for dotted, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        edges[dotted] = {d for d in module_edges(tree, modules, packages) if d in modules}

    order: list[str] = []
    done: set[str] = set()
    remaining = set(modules)
    while remaining:
        ready = sorted(d for d in remaining if edges[d] <= done)
        if not ready:
            raise SystemExit(f"순환 의존(모듈 레벨) 감지: {sorted(remaining)}")
        for d in ready:
            order.append(d)
            done.add(d)
            remaining.discard(d)
    return order


# --------------------------------------------------------------- 바이트 편집 도구
class ByteBuf:
    def __init__(self, text: str):
        self.data = text.encode("utf-8")
        self.line_start = [0]
        for line in self.data.split(b"\n")[:-1]:
            self.line_start.append(self.line_start[-1] + len(line) + 1)
        self.nlines = len(self.line_start)

    def off(self, lineno: int, col: int) -> int:
        return self.line_start[lineno - 1] + col

    def node_span(self, node: ast.AST) -> tuple[int, int]:
        return self.off(node.lineno, node.col_offset), self.off(node.end_lineno, node.end_col_offset)

    def line_span(self, node: ast.AST) -> tuple[int, int]:
        start = self.off(node.lineno, 0)
        end = self.off(node.end_lineno + 1, 0) if node.end_lineno < self.nlines else len(self.data)
        return start, end

    def slice(self, start: int, end: int) -> str:
        return self.data[start:end].decode("utf-8")

    def apply(self, edits: list[tuple[int, int, bytes]]) -> str:
        edits = sorted(edits, key=lambda e: e[0], reverse=True)
        prev_start = len(self.data) + 1
        out = self.data
        for start, end, repl in edits:
            if end > prev_start:
                raise SystemExit(f"편집 구간 겹침: {start}-{end} > {prev_start}")
            out = out[:start] + repl + out[end:]
            prev_start = start
        return out.decode("utf-8")


# ---------------------------------------------------------------- 모듈 변형
def _sole_stmts(tree: ast.Module) -> set[int]:
    sole: set[int] = set()
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            lst = getattr(node, field, None)
            if isinstance(lst, list) and len(lst) == 1 and isinstance(lst[0], ast.stmt):
                sole.add(id(lst[0]))
    return sole


def _top_level_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                for nm in ast.walk(tgt):
                    if isinstance(nm, ast.Name):
                        names.add(nm.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def transform(path: Path, dotted: str, modules: dict[str, Path], packages: set[str],
              collisions: set[str]) -> tuple[str, list[tuple], str]:
    """모듈 소스를 변형해 (본문 텍스트, 호이스트 import 조각들, 인덱스용 docstring) 반환."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    buf = ByteBuf(src)
    sole = _sole_stmts(tree)
    edits: list[tuple[int, int, bytes]] = []
    hoist: list[tuple] = []

    # 이 모듈의 Form2 네임스페이스 alias 수집 + app import 노드 처리 계획
    aliases: set[str] = set()
    app_import_nodes: list[ast.ImportFrom] = []
    alias_assigns: dict[int, list[tuple[str, str]]] = {}
    future_nodes: list[ast.ImportFrom] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        mod = node.module or ""
        if mod == "__future__":
            future_nodes.append(node)
            continue
        if not (mod == "app" or mod.startswith("app.")):
            continue
        app_import_nodes.append(node)
        zy: list[tuple[str, str]] = []
        if mod in modules:  # Form1
            for a in node.names:
                if a.asname and a.asname != a.name:
                    zy.append((a.asname, a.name))
        elif mod in packages:  # Form2 (또는 패키지 init 심볼)
            for a in node.names:
                full = f"{mod}.{a.name}"
                local = a.asname or a.name
                if full in modules or full in packages:
                    aliases.add(local)  # 네임스페이스 → elision 대상
                elif a.asname and a.asname != a.name:
                    zy.append((a.asname, a.name))  # 예: __version__ as v (드묾)
        else:  # app.<unknown> → Form1 취급
            for a in node.names:
                if a.asname and a.asname != a.name:
                    zy.append((a.asname, a.name))
        if zy:
            alias_assigns[id(node)] = zy

    # 지역 변수/파라미터가 alias 를 가리면 elision 이 위험 → 빌드 실패(수동 확인 유도)
    for node in ast.walk(tree):
        bad = None
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id in aliases:
            bad = node.id
        elif isinstance(node, ast.arg) and node.arg in aliases:
            bad = node.arg
        if bad:
            raise SystemExit(f"{dotted}: 네임스페이스 alias '{bad}' 가 지역으로 재바인딩됨 → elision 위험")

    # 이 모듈이 정의하는 충돌 이름 → 리네임 맵. 모두 `<token>__<name(선행 _ 제거)>` 로 통일.
    token = path.stem
    rename = {n: f"{token}__{n.lstrip('_')}" for n in (_top_level_names(tree) & collisions)}

    # 1) __future__ / 모듈레벨 비-app import → 호이스트하며 라인 삭제
    for node in future_nodes:
        s, e = buf.line_span(node)
        edits.append((s, e, b""))
    for node in tree.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                hoist.append(("import", a.name, a.asname))
            s, e = buf.line_span(node)
            edits.append((s, e, b""))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "__future__" or mod == "app" or mod.startswith("app."):
                continue
            for a in node.names:
                hoist.append(("from", mod, a.name, a.asname))
            s, e = buf.line_span(node)
            edits.append((s, e, b""))

    # 2) app import 노드: 삭제 또는 Z=Y 방출 또는 pass
    for node in app_import_nodes:
        indent = b" " * node.col_offset
        if id(node) in alias_assigns:
            lines = b"\n".join(indent + f"{z} = {y}".encode() for z, y in alias_assigns[id(node)])
            s, e = buf.line_span(node)
            edits.append((s, e, lines + b"\n"))
        elif node.col_offset > 0 and id(node) in sole:
            s, e = buf.line_span(node)
            edits.append((s, e, indent + b"pass\n"))
        else:
            s, e = buf.line_span(node)
            edits.append((s, e, b""))

    # 3) 네임스페이스 접두어 제거: alias.attr → attr
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases:
            s, e = buf.node_span(node)
            expected = f"{node.value.id}.{node.attr}"
            if buf.slice(s, e) != expected:  # f-string 위치 이슈 등 → 실패로 드러냄
                raise SystemExit(f"{dotted}:{node.lineno} elision 위치 불일치: {buf.slice(s, e)!r} != {expected!r}")
            edits.append((s, e, node.attr.encode()))

    # 4) 충돌 이름 리네임(정의 + 참조)
    if rename:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in rename:
                line = buf.data[buf.off(node.lineno, 0):buf.off(node.lineno + 1, 0) if node.lineno < buf.nlines else len(buf.data)]
                m = re.search(rb"(async\s+def|def|class)(\s+)(" + re.escape(node.name.encode()) + rb")\b", line)
                if not m:
                    raise SystemExit(f"{dotted}:{node.lineno} def/class 이름 위치 실패: {node.name}")
                start = buf.off(node.lineno, m.start(3))
                edits.append((start, start + len(node.name.encode()), rename[node.name].encode()))
            elif isinstance(node, ast.Name) and node.id in rename:
                s, e = buf.node_span(node)
                if buf.slice(s, e) != node.id:
                    raise SystemExit(f"{dotted}:{node.lineno} 리네임 위치 불일치: {buf.slice(s, e)!r} != {node.id!r}")
                edits.append((s, e, rename[node.id].encode()))

    # 5) __file__ 경로 보정
    body = buf.apply(edits)
    for old, new in FILE_FIXUPS.get(dotted, []):
        if old not in body:
            raise SystemExit(f"{dotted}: __file__ 보정 대상 조각을 찾지 못함:\n{old}")
        body = body.replace(old, new, 1)

    docstring = ast.get_docstring(tree) or ""
    return body.strip("\n"), hoist, docstring.strip().splitlines()[0] if docstring else ""


# ---------------------------------------------------------------- 조립/방출
def _emit_hoist(pieces: list[tuple]) -> str:
    plain: set[tuple[str, str | None]] = set()
    froms: dict[str, set[tuple[str, str | None]]] = {}
    for p in pieces:
        if p[0] == "import":
            plain.add((p[1], p[2]))
        else:
            froms.setdefault(p[1], set()).add((p[2], p[3]))

    def top(mod: str) -> str:
        return mod.split(".")[0]

    def fmt_name(name: str, asname: str | None) -> str:
        return f"{name} as {asname}" if asname else name

    def _key(pair: tuple[str, str | None]) -> tuple[str, str]:
        return (pair[0], pair[1] or "")

    def render(mods: list[str], plains: list[tuple[str, str | None]]) -> list[str]:
        out: list[str] = []
        for name, asname in sorted(plains, key=_key):
            out.append(f"import {fmt_name(name, asname)}")
        for mod in sorted(mods):
            names = ", ".join(fmt_name(n, a) for n, a in sorted(froms[mod], key=_key))
            out.append(f"from {mod} import {names}")
        return out

    std_mods = [m for m in froms if top(m) in STDLIB]
    ext_mods = [m for m in froms if top(m) not in STDLIB]
    std_plain = [(n, a) for n, a in plain if top(n) in STDLIB]
    ext_plain = [(n, a) for n, a in plain if top(n) not in STDLIB]

    lines = render(std_mods, std_plain)
    ext = render(ext_mods, ext_plain)
    if ext:
        lines += [""] + ext
    return "\n".join(lines)


_PREAMBLE = '''\
# --- 의존성 프리앰블: 무거운 import 전에 친절한 안내(원본 main.py UX 보존) ---
import importlib.util as _importlib_util
import sys


def _require_dependencies() -> None:
    _req = {"PySide6": "PySide6", "PIL": "Pillow", "openpyxl": "openpyxl"}
    _missing = [name for mod, name in _req.items() if _importlib_util.find_spec(mod) is None]
    if _missing:
        sys.stderr.write(
            "필요한 라이브러리가 설치되어 있지 않습니다: " + ", ".join(_missing) + "\\n"
            "다음 명령으로 설치하세요:\\n    python bootstrap.py\\n"
            "또는:\\n    pip install PySide6 Pillow openpyxl\\n"
        )
        raise SystemExit(1)


_require_dependencies()'''


def build() -> str:
    modules, packages = discover()
    for pkg in packages:
        init = APP_DIR.parent / Path(*pkg.split(".")) / "__init__.py"
        tree = ast.parse(init.read_text(encoding="utf-8"))
        if pkg != "app" and not _is_trivial(tree):
            raise SystemExit(f"{pkg}/__init__.py 에 코드가 있음 — 매니페스트 반영 필요")

    # 충돌 검출
    where: dict[str, list[str]] = {}
    for dotted, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name in _top_level_names(tree):
            where.setdefault(name, []).append(dotted)
    collisions = {n for n, mods in where.items() if len(mods) >= 2}
    unexpected = collisions - KNOWN_COLLISIONS
    if unexpected:
        detail = "; ".join(f"{n}: {where[n]}" for n in sorted(unexpected))
        raise SystemExit(f"새 최상위 이름 충돌 발견 → build_single_file 갱신 필요: {detail}")

    order = topo_order(modules)
    # 매니페스트 순서 검증: 각 모듈의 모듈레벨 app 의존이 앞서 방출되는지
    seen: set[str] = set()
    for dotted in order:
        tree = ast.parse(modules[dotted].read_text(encoding="utf-8"))
        for dep in module_edges(tree, modules, packages):
            if dep in modules and dep not in seen:
                raise SystemExit(f"순서 오류: {dotted} 가 아직 방출되지 않은 {dep} 에 의존")
        seen.add(dotted)

    version = re.search(
        r'__version__\s*=\s*["\']([^"\']*)["\']',
        (APP_DIR / "__init__.py").read_text(encoding="utf-8"),
    ).group(1)

    # 각 모듈 변형
    hoist: list[tuple] = []
    bodies: list[tuple[str, str, str]] = []  # (dotted, body, first_docline)
    for dotted in order:
        body, pieces, doc = transform(modules[dotted], dotted, modules, packages, collisions)
        hoist += pieces
        bodies.append((dotted, body, doc))
    main_body, main_pieces, _ = transform(MAIN_PY, "main", modules, packages, collisions)
    hoist += main_pieces

    # 목차
    layer_of = {d: i for i, d in enumerate(order)}
    toc = ["# 모듈 맵 (위상순서, leaf → top):"]
    for dotted, _b, doc in bodies:
        rel = dotted.replace(".", "/") + ".py"
        toc.append(f"#   {rel:<34}{('— ' + doc) if doc else ''}".rstrip())
    toc.append("#   main.py                           — 진입점")

    parts: list[str] = []
    parts.append(
        "# =============================================================================\n"
        "# Defect Layer Tracker — 단일 파일 배포본 (AUTO-GENERATED — 편집 금지)\n"
        "#\n"
        "# 이 파일은 `app/` + `main.py` 에서 자동 생성된 산출물입니다. 소스의 진실은 모듈식\n"
        "# 소스이며, 이 파일을 직접 고치지 마세요. 재생성:\n"
        "#     python tools/build_single_file.py\n"
        f"# 버전: {version}   (실행: python defect_tracker.py / 의존성 설치: python bootstrap.py)\n"
        "# ============================================================================="
    )
    parts.append("from __future__ import annotations")
    parts.append(_PREAMBLE.rstrip())
    parts.append(_emit_hoist(hoist))
    parts.append(f'__version__ = "{version}"')
    parts.append("\n".join(toc))
    for dotted, body, _doc in bodies:
        rel = dotted.replace(".", "/") + ".py"
        banner = (
            "# =============================================================================\n"
            f"# {rel}   [#{layer_of[dotted]}]\n"
            "# ============================================================================="
        )
        parts.append(banner + "\n" + body)
    parts.append(
        "# =============================================================================\n"
        "# main.py   [진입점]\n"
        "# =============================================================================\n"
        + main_body
    )
    return "\n\n\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="단일 파일 생성기")
    ap.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="커밋본이 최신인지만 확인")
    args = ap.parse_args(argv)

    text = build()
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != text:
            print(f"stale — `python tools/build_single_file.py` 를 실행하세요 ({args.output})", file=sys.stderr)
            return 1
        print(f"최신 ({args.output})")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    lines = text.count("\n") + 1
    ver = re.search(r'^__version__ = "([^"]*)"', text, re.MULTILINE).group(1)
    print(f"생성 완료: {args.output}  ({lines} 줄, 버전 {ver})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
