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
    ("미분류(class 0) 후보 이미지", "KLA 가 찍었지만 정식 결함으로 분류/등록하지 않은 후보 "
                                   "이미지 — 실제 결함이 아니면 정상이며 무시해도 됩니다."),
]


# 미분류(class 0) 후보 — 원본 info(DefectList)에 정식 결함으로 등록되지 않아 좌표가 없는,
# '정상적으로 제외되는' 이미지. 진짜 실패(info 없음·불일치 등)와 구분해 따로 표기한다.
_UNCLASSIFIED_MARK = "미분류(class 0)"


def _is_unclassified(rec: DefectRecord) -> bool:
    return _UNCLASSIFIED_MARK in (rec.note or "")


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
    # 미분류(class 0) 후보와 '확인 필요' 실패를 분리한다.
    unclassified = [r for r in failed if _is_unclassified(r)]
    real_failed = [r for r in failed if not _is_unclassified(r)]

    lines: list[str] = []
    lines.append(f"# 좌표 추출 진단 — {lot_name}")
    lines.append("")
    lines.append(f"- 전체 이미지: **{total}개**")
    lines.append(f"- 좌표 OK: **{total - len(failed)}개**")
    if unclassified:
        lines.append(
            f"- 미분류(class 0) 후보: **{len(unclassified)}개** (정식 결함 아님 · 무시 가능)"
        )
    lines.append(f"- 실패: **{len(real_failed)}개**")
    lines.append("")

    if not failed:
        lines.append("이번 스캔에서 좌표 추출 실패가 없습니다. ✅")
        if scan_errors:
            lines.append("")
            lines.append("## 접근 실패 경로")
            for e in scan_errors[:50]:
                lines.append(f"- {e}")
        return "\n".join(lines) + "\n"

    # 미분류(class 0) 후보 — 무시 가능(간단 요약만, KLA info 덤프 없음)
    if unclassified:
        lines.extend(_unclassified_section(unclassified))

    # 확인 필요 실패 — 상태별 카운트 + 원인 클러스터(상세)
    if real_failed:
        lines.extend(_failure_clusters(real_failed))
    else:
        lines.append("확인이 필요한 실패는 없습니다 — 위 미분류(class 0) 후보만 있으며 정상입니다. ✅")
        lines.append("")

    if scan_errors:
        lines.append("## 접근 실패 경로")
        for e in scan_errors[:50]:
            lines.append(f"- {e}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _unclassified_section(recs: list[DefectRecord]) -> list[str]:
    """미분류(class 0) 후보 요약 — layer/wafer 분포 + 예시(무거운 info 덤프 없음)."""
    lines: list[str] = []
    lines.append(f"## 미분류(class 0) 후보 — 무시 가능 ({len(recs)}개)")
    lines.append("")
    lines.append(
        "> KLA 가 캡처했지만 정식 결함으로 분류/등록하지 않은 후보 이미지입니다. 원본 "
        "info(DefectList)에 좌표 항목이 없어 정상적으로 제외됩니다(실제 결함 아님)."
    )
    by_layer = Counter(r.layer_folder for r in recs)
    lines.append(
        "- layer 분포: " + ", ".join(f"{k}×{v}" for k, v in by_layer.most_common(10))
    )
    by_wafer = Counter(r.wafer_id for r in recs)
    lines.append(
        "- wafer 분포: " + ", ".join(f"{k}×{v}" for k, v in by_wafer.most_common(10))
    )
    lines.append("- 예시 파일:")
    for r in recs[:5]:
        lines.append(f"  - `{Path(r.image_path).name}`")
    lines.append("")
    return lines


def _failure_clusters(recs: list[DefectRecord]) -> list[str]:
    """확인 필요 실패의 상태별 카운트 + 동일 사유 클러스터(상세 컨텍스트 포함)."""
    lines: list[str] = []
    by_status: Counter[str] = Counter(r.status.value for r in recs)
    lines.append("## 상태별 카운트")
    lines.append("")
    lines.append("| 상태 | 개수 |")
    lines.append("|---|---|")
    for status, n in by_status.most_common():
        lines.append(f"| {_STATUS_LABEL.get(status, status)} | {n} |")
    lines.append("")

    clusters: dict[str, list[DefectRecord]] = defaultdict(list)
    for r in recs:
        clusters[_signature(r)].append(r)
    lines.append("## 실패 원인 클러스터 (동일 사유끼리 묶음)")
    lines.append("")
    for sig, rs in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"### ({len(rs)}개) {sig}")
        hint = _hint_for(sig)
        if hint:
            lines.append(f"> 처방: {hint}")
        by_layer = Counter(r.layer_folder for r in rs)
        dist = ", ".join(f"{k}×{v}" for k, v in by_layer.most_common(6))
        lines.append(f"- layer 분포: {dist}")
        lines.append("- 예시 파일:")
        for r in rs[:5]:
            lines.append(f"  - `{Path(r.image_path).resolve()}`")
        lines.append("")

        # 폴더별 진단 컨텍스트(같은 클러스터에서 고유 wafer_dir 기준)
        seen_dirs: set[str] = set()
        diag_count = 0
        for r in rs:
            if diag_count >= 3:
                break
            d = r.diag
            if not d:
                continue
            wdir = d.get("wafer_dir", "")
            if wdir in seen_dirs:
                continue
            seen_dirs.add(wdir)
            diag_count += 1
            lines.extend(_format_diag_context(r))
    return lines


def _format_diag_context(rec: DefectRecord) -> list[str]:
    """단일 실패 record 의 진단 컨텍스트를 markdown 줄 목록으로 포맷한다."""
    d = rec.diag
    if not d:
        return []
    lines: list[str] = []
    wdir = d.get("wafer_dir", str(Path(rec.image_path).parent))
    lines.append(f"#### 폴더 컨텍스트: `{wdir}`")
    lines.append("")

    # 좌표 출처·상태
    lines.append(f"- 좌표 출처(source): **{rec.source.value if hasattr(rec.source, 'value') else rec.source}**")
    lines.append(f"- 파싱 상태(status): **{rec.status.value if hasattr(rec.status, 'value') else rec.status}**")
    lines.append(f"- 시도 트레일(note): {rec.note or '(없음)'}")
    lines.append("")

    # 폴더 내 파일 목록
    all_files = d.get("files_in_folder", [])
    img_count = d.get("image_count", 0)
    lines.append(f"**폴더 내 파일 ({len(all_files)}개, 이미지 {img_count}개):**")
    lines.append("")
    for fname in all_files:
        lines.append(f"- `{fname}`")
    lines.append("")

    # Camtek INI 정보
    ini_files = d.get("ini_files", [])
    has_ini = d.get("has_ini_sections", False)
    if ini_files:
        lines.append(f"**Camtek INI 파일:** {', '.join(f'`{f}`' for f in ini_files)}")
        if has_ini:
            keys = d.get("ini_section_keys", [])
            lines.append(f"- INI section 수: {len(keys)}")
            if keys:
                preview = ", ".join(keys[:10])
                suffix = f" ... 외 {len(keys) - 10}개" if len(keys) > 10 else ""
                lines.append(f"- section 키 예시: `{preview}`{suffix}")
        lines.append("")
    else:
        lines.append("**Camtek INI 파일:** 없음")
        lines.append("")

    # KLA info 정보
    kla_file = d.get("kla_info_file")
    if kla_file:
        lines.append(f"**KLA info 파일:** `{kla_file}`")
        pitch_y = d.get("kla_die_pitch_y")
        tiff_count = d.get("kla_tiff_count", 0)
        all_defect_count = d.get("kla_all_defect_count", 0)
        lines.append(f"- DiePitchY: {pitch_y}")
        lines.append(f"- TiffFileName 매핑 수: {tiff_count}")
        lines.append(f"- 전체 DefectList 엔트리 수: {all_defect_count}")
        lines.append("")
        info_text = d.get("kla_info_text", "")
        if info_text:
            lines.append("<details><summary>KLA info 파일 내용 (펼치기)</summary>")
            lines.append("")
            lines.append("```")
            lines.append(info_text)
            lines.append("```")
            lines.append("")
            lines.append("</details>")
            lines.append("")
    else:
        lines.append("**KLA info 파일:** 없음 (선택된 info 파일 없음)")
        lines.append("")

    return lines


_MAX_LOG_SIZE = 25 * 1024 * 1024  # 25 MB


def _pick_log_file(logs_dir: Path) -> Path:
    """현재 쓸 로그 파일을 반환한다. 25MB 초과 시 다음 번호 파일을 만든다."""
    base = logs_dir / "parse_failures.md"
    if not base.exists() or base.stat().st_size < _MAX_LOG_SIZE:
        return base
    idx = 2
    while True:
        candidate = logs_dir / f"parse_failures_{idx}.md"
        if not candidate.exists() or candidate.stat().st_size < _MAX_LOG_SIZE:
            return candidate
        idx += 1


def write_parse_failure_report(
    log_dir: Path, lot_name: str, records: list[DefectRecord],
    scan_errors: list[str] | None = None,
) -> Path:
    """진단 리포트를 log_dir/parse_failures*.md 에 **누적 추가**하고 경로를 반환한다."""
    logs = Path(log_dir)
    logs.mkdir(parents=True, exist_ok=True)
    out = _pick_log_file(logs)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    separator = f"\n---\n\n> 스캔 시각: {stamp}\n\n"
    report = build_failure_report(lot_name, records, scan_errors)
    with open(out, "a", encoding="utf-8") as f:
        f.write(separator + report)
    return out
