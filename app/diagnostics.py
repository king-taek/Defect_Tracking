"""좌표 추출 실패 진단 리포트(개발용) — 단일 markdown 파일로 관리.

스캔에서 좌표를 뽑지 못한 record 의 '왜'를 모아 한 파일로 남긴다. 매 스캔마다
**누적 추가(append)** 하여 이력을 보존한다. 원본이 아닌 워크스페이스에만 쓴다.
민감정보(좌표값 등)는 적지 않고 파일명/구조/카운트/사유만 기록한다.

핵심: 같은 '시도 트레일(note)'을 가진 실패끼리 **서명(signature) 클러스터링**해
대표 예시·카운트·처방 힌트를 보여줌으로써 대량 실패의 근본 원인을 빠르게 파악한다.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from app.models import DefectRecord, ParseStatus

_STATUS_LABEL = {
    ParseStatus.NOT_FOUND.value: "좌표/매칭 정보 없음",
    ParseStatus.INFO_FILE_NOT_FOUND.value: "info 파일 없음",
    ParseStatus.INVALID_INFO.value: "info 값 부족/오류",
}

# 서명(시도 트레일)에 특정 신호가 있으면 처방 힌트를 붙인다.
_HINTS = [
    ("KLA 원본", "파일명이 KLA 원본형 — 자재(material) 폴더가 아니라 KLA 원본 폴더를 "
                 "선택했을 가능성. 폴더 레벨을 확인하세요."),
    ("ColorImageGrabingInfo.ini 없음", "Camtek INI 가 없는 layer — KLA info(.001)로만 "
                                       "좌표가 나옵니다. info 파일 존재를 확인하세요."),
    ("TiffFileName", "KLA info 의 TiffFileName 목록과 이미지 파일명이 어긋남 — 확장자/명명 "
                     "규칙 불일치 가능."),
    ("DiePitchY 없음", "KLA info header 가 비표준 — DiePitchY 라인을 확인하세요."),
    ("die 위치 음수", "XINDEX/YINDEX 또는 제품 zero offset 이 맞지 않음 — 제품 프로파일을 "
                     "확인하세요."),
    ("필드 누락", "INI section 에 x/y/col/row 키가 부족 — INI 생성 설정을 확인하세요."),
]


def _signature(rec: DefectRecord) -> str:
    """동일 원인 묶음을 위한 서명(시도 트레일 문자열)."""
    return rec.note or rec.status.value


def _hint_for(signature: str) -> str:
    for needle, hint in _HINTS:
        if needle in signature:
            return hint
    return ""


def build_failure_report(lot_name: str, records: list[DefectRecord],
                         scan_errors: list[str] | None = None) -> str:
    """실패 진단 markdown 문자열을 만든다(파일 쓰기는 write_parse_failure_report)."""
    failed = [r for r in records if not r.ok]
    total = len(records)
    lines: list[str] = []
    lines.append(f"# 좌표 추출 진단 — {lot_name}")
    lines.append("")
    lines.append(f"- 전체 이미지: **{total}개**")
    lines.append(f"- 좌표 OK: **{total - len(failed)}개**")
    lines.append(f"- 실패: **{len(failed)}개**")
    lines.append("")

    if not failed:
        lines.append("이번 스캔에서 좌표 추출 실패가 없습니다. ✅")
        if scan_errors:
            lines.append("")
            lines.append("## 접근 실패 경로")
            for e in scan_errors[:50]:
                lines.append(f"- {e}")
        return "\n".join(lines) + "\n"

    # 상태별 카운트
    by_status: Counter[str] = Counter(r.status.value for r in failed)
    lines.append("## 상태별 카운트")
    lines.append("")
    lines.append("| 상태 | 개수 |")
    lines.append("|---|---|")
    for status, n in by_status.most_common():
        lines.append(f"| {_STATUS_LABEL.get(status, status)} | {n} |")
    lines.append("")

    # 실패 서명 클러스터링(동일 트레일끼리)
    clusters: dict[str, list[DefectRecord]] = defaultdict(list)
    for r in failed:
        clusters[_signature(r)].append(r)
    lines.append("## 실패 원인 클러스터 (동일 사유끼리 묶음)")
    lines.append("")
    for sig, recs in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"### ({len(recs)}개) {sig}")
        hint = _hint_for(sig)
        if hint:
            lines.append(f"> 처방: {hint}")
        # layer/wafer 분포
        by_layer = Counter(r.layer_folder for r in recs)
        dist = ", ".join(f"{k}×{v}" for k, v in by_layer.most_common(6))
        lines.append(f"- layer 분포: {dist}")
        lines.append("- 예시 파일:")
        for r in recs[:5]:
            lines.append(f"  - `{Path(r.image_path).resolve()}`")
        lines.append("")

    if scan_errors:
        lines.append("## 접근 실패 경로")
        for e in scan_errors[:50]:
            lines.append(f"- {e}")
        lines.append("")
    return "\n".join(lines) + "\n"


def write_parse_failure_report(
    workspace_path: Path, lot_name: str, records: list[DefectRecord],
    scan_errors: list[str] | None = None,
) -> Path:
    """진단 리포트를 workspace/logs/parse_failures.md 에 **누적 추가**하고 경로를 반환한다."""
    logs = Path(workspace_path) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    out = logs / "parse_failures.md"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    separator = f"\n---\n\n> 스캔 시각: {stamp}\n\n"
    report = build_failure_report(lot_name, records, scan_errors)
    with open(out, "a", encoding="utf-8") as f:
        f.write(separator + report)
    return out
