"""Layer 폴더명 정규화 및 비교 그리드 배치 (문서 Section 8.2 / 8.4).

폴더명 예: "1. RDL4", "2. PIDS3_재리뷰"
  - 선행 순번 "N. " 제거
  - 접미 "_재리뷰" 제거 후 is_re_review 플래그
  - 남은 토큰을 canonical layer 토큰으로 사용 (예: RDL4, PIDS3)

비교 화면 그리드(Section 8.4)는 config.DEFAULT_LAYER_GRID 를 기본으로 하되,
실제 존재하는 layer 만 배치하고 나머지는 발견 순서대로 빈 칸을 채운다(graceful fallback).
"""

from __future__ import annotations

import re

from app import config

_ORDER_PREFIX_RE = re.compile(r"^\s*\d+\s*[.\-_)]\s*")
_RE_REVIEW_SUFFIXES = ("_재리뷰", "_재 리뷰", "_rereview", "_re-review")
# 재리뷰 레벨: 접미가 "_" + ("재"×n) + "리뷰"(공백 허용). n = 재리뷰 깊이.
#   _재리뷰=1, _재재리뷰=2, _재재재리뷰=3 …
_RE_REVIEW_LEVEL_RE = re.compile(r"_\s*((?:재\s*)+)리뷰\s*$")
# 영문 다중 re- 도 보조 지원: _re-review=1, _re-re-review=2 …
_EN_RE_REVIEW_RE = re.compile(r"_\s*((?:re-?)+)review\s*$", re.IGNORECASE)


def re_review_level(folder_name: str) -> int:
    """폴더명의 재리뷰 깊이를 센다(0 없음 / 1 재리뷰 / 2 재재리뷰 …).

    한국어 "_재리뷰"·"_재재리뷰"(반복 재) 및 영문 "_rereview"/"_re-re-review" 를 인식한다.
    """
    name = _ORDER_PREFIX_RE.sub("", folder_name.strip())
    m = _RE_REVIEW_LEVEL_RE.search(name)
    if m:
        return m.group(1).count("재")
    m = _EN_RE_REVIEW_RE.search(name)
    if m:
        # "re" 출현 횟수 = 레벨(re-review→1, re-re-review→2)
        return max(1, m.group(1).lower().count("re"))
    return 0


def normalize_layer(folder_name: str) -> tuple[str, bool]:
    """폴더명 -> (canonical 토큰, 재리뷰 여부).

    재리뷰 접미(재재리뷰 포함)는 모두 제거해 같은 canonical 로 정규화한다.
    """
    name = folder_name.strip()
    name = _ORDER_PREFIX_RE.sub("", name)

    level = re_review_level(folder_name)
    if level > 0:
        # 접미(재…리뷰 / re…review)를 통째로 제거
        name = _RE_REVIEW_LEVEL_RE.sub("", name)
        name = _EN_RE_REVIEW_RE.sub("", name)
    else:
        lowered = name.lower()
        for suffix in _RE_REVIEW_SUFFIXES:
            if lowered.endswith(suffix.lower()):
                name = name[: -len(suffix)]
                level = 1
                break

    canonical = name.strip().strip("._- ")
    return canonical, level > 0


def _canon_token(s: str) -> str:
    """배치 매칭용 단순화 토큰 (대문자/영숫자만)."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def build_grid(layers: list[str]) -> list[list[str | None]]:
    """주어진 layer 목록을 기본 그리드 배치에 채워 2열 그리드를 만든다.

    기본 배치(config.DEFAULT_LAYER_GRID)의 셀과 canonical 토큰이 일치하면 그 자리에 두고,
    배치에 없는 layer 는 남은 빈 칸/추가 행에 순서대로 채운다.
    """
    remaining = list(layers)
    grid: list[list[str | None]] = []

    # 1차: 기본 배치 위치에 일치하는 layer 부터 채운다.
    template = config.DEFAULT_LAYER_GRID
    for row_tpl in template:
        row: list[str | None] = []
        for cell in row_tpl:
            match = None
            for lyr in remaining:
                if _canon_token(lyr) == _canon_token(cell):
                    match = lyr
                    break
            if match is not None:
                remaining.remove(match)
                row.append(match)
            else:
                row.append(None)
        grid.append(row)

    # 2차: 배치에 없던 layer 들을 빈 칸 → 추가 행 순으로 채운다.
    def next_remaining() -> str | None:
        return remaining.pop(0) if remaining else None

    for row in grid:
        for c in range(len(row)):
            if row[c] is None and remaining:
                row[c] = next_remaining()

    while remaining:
        grid.append([next_remaining(), next_remaining()])

    # 완전히 빈 행 제거
    grid = [r for r in grid if any(cell is not None for cell in r)]
    return grid
