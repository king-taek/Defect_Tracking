"""세션 마킹/메모 저장 (원본 미수정 원칙 준수).

리뷰어가 기준 사진에 별표/메모를 남길 수 있게 한다. 데이터는 **항상 출력 작업공간**
(원본 LOT 폴더 밖)의 `session/<lot>.json` 에만 저장한다. 키는 기준 이미지의 절대 경로.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

_log = logging.getLogger("defect_tracker.session")


def _safe_name(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣._-]", "_", name) or "session"


class SessionStore:
    """LOT 단위 마킹/메모 보관소(작업공간 JSON)."""

    def __init__(self, path: Path, marks: dict[str, dict]):
        self.path = path
        self.marks = marks

    @classmethod
    def load(cls, workspace: Path, lot_name: str) -> "SessionStore":
        path = Path(workspace) / "session" / f"{_safe_name(lot_name)}.json"
        marks: dict[str, dict] = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    marks = {k: v for k, v in raw.items() if isinstance(v, dict)}
            except (OSError, json.JSONDecodeError) as exc:
                _log.warning("세션 파일을 읽지 못했습니다(%s): %s", path, exc)
        return cls(path, marks)

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(
                json.dumps(self.marks, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(tmp, self.path)
        except OSError as exc:
            _log.warning("세션 저장 실패(%s): %s", self.path, exc)

    # ---- 조회/수정 ----
    def is_marked(self, key: str) -> bool:
        return bool(self.marks.get(key, {}).get("marked"))

    def note(self, key: str) -> str:
        return str(self.marks.get(key, {}).get("note", ""))

    def toggle_mark(self, key: str) -> bool:
        entry = self.marks.setdefault(key, {})
        entry["marked"] = not entry.get("marked", False)
        self._prune(key)
        return bool(entry.get("marked"))

    def set_note(self, key: str, note: str) -> None:
        entry = self.marks.setdefault(key, {})
        entry["note"] = note
        self._prune(key)

    def notes_map(self) -> dict[str, str]:
        return {k: v.get("note", "") for k, v in self.marks.items() if v.get("note")}

    def _prune(self, key: str) -> None:
        """빈 항목은 제거(파일을 가볍게 유지)."""
        e = self.marks.get(key)
        if e and not e.get("marked") and not e.get("note"):
            self.marks.pop(key, None)
