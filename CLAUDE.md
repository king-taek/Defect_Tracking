# Defect Tracker — 개발 지침

반도체 defect 이미지 비교 뷰어(PySide6 데스크톱 앱). 기준 layer 의 defect 위치를 기준으로
다른 layer 에서 같은 위치의 defect 를 찾아 비교하고 결과를 Excel 로 출력한다.

## 절대 원칙
- **원본 read-only**: 스캔 대상(자재/LOT) 폴더에는 어떤 것도 쓰지 않는다. 모든 산출물
  (캐시·결과·로그·세션·진단)은 워크스페이스(`AppSettings.workspace`, 기본
  `%LOCALAPPDATA%\DefectTracker` / `~/DefectTracker`)에만 저장한다.
- 순수 로직(파서/매처/정합/진단/버전)은 UI 와 분리하고 단위 테스트로 못 박는다.

## 버전 규칙 (중요 — 세션이 바뀌어도 반드시 지킬 것)
`app/__init__.py` 의 `__version__` 은 **손으로 고정하지 말고** git 이력에서 계산한다.
규칙: `1.{MINOR}.{PATCH}` — MINOR = 변경 라인 ≥200 인 "큰 커밋" 수, PATCH = 전체 커밋 수
(+워킹트리 변경 시 1, 곧 만들 커밋 반영).

**app 코드(`app/`, `main.py`)를 변경해 커밋하기 직전에 반드시 실행한다:**

```
python tools/compute_version.py --write
```

그 결과로 갱신된 `app/__init__.py` 를 같은 커밋에 포함한다. (런타임에 git 을 호출하지
않으므로 시작 속도에 영향 없음. 자동 업데이트는 커밋 SHA 로 비교하므로 버전 표기 형식은
업데이트 로직과 무관하다.) 계산 로직은 `tools/compute_version.py` 참고.

## 테스트
```
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q
```
UI 는 오프스크린 스모크, 순수 로직은 단위 테스트로 검증한다. 새 동작은 회귀 테스트 동반.

## Git 워크플로
- **현재 체크아웃된 작업 브랜치**(세션/작업마다 다름)에서 개발 → 테스트 통과 후 `main` 으로
  fast-forward 머지 → push. 기능 단위로 커밋한다. (브랜치 이름을 여기 고정하지 않는다 —
  새 브랜치로 옮겨도 이 규칙이 그대로 적용되도록.)
- 기밀(고객 디바이스 좌표가 담긴 `Origin/*.xlsx`, `*.xlsm`)은 커밋 금지(.gitignore 유지).
  외부 `AOIDeviceDB.xlsx` 는 런타임에만 읽고 저장소에 포함하지 않는다.
- updater 의 `_SKIP_DIRS`·`_SKIP_FILES` 를 바꾸면 루트 `.gitattributes`(export-ignore)도 같이 고친다.
  zip 단계에서 빼지 않으면 개발 파일이 사용자 PC 임시 폴더로 내려온다.

## 스킬 사용 규칙 (세션마다 적용)
설치한 스킬은 `.claude/skills/README.md` 에 있다. 사용자가 초보라 **알아서 쓰는 쪽**을 원한다(2026-10-18).
- **읽기 · 검토 · 디버깅 · 설계 조언 스킬은 묻지 않고 바로 쓴다.** 쓸 때 답에 한 줄로 "`<스킬>` 로 확인했다" 고 밝힌다.
- **여러 파일을 고치거나 지우는 스킬**(`deprecation-and-migration` 실행, `ponytail-audit` 결과 적용, `using-git-worktrees`)만
  먼저 짧게 제안하고 승낙을 받는다: "이 작업은 `<스킬>` 을 쓰면 <이점 1~2줄>. 사용할까요?"
- 사용자가 `/스킬명` 으로 직접 부른 경우는 묻지 않고 바로 실행한다.

| 상황 | 쓸 스킬 | 이점 |
|---|---|---|
| 코드 작성/수정 (특히 새 의존성·추상화 추가) | `ponytail` (로직 full, UI lite) | stdlib/기존 코드로 대체 가능한지 먼저 걸러 코드량과 유지보수 부담 감소 |
| 테스트 실패·예외·예상 밖 동작 | `debugging-and-error-recovery` | 재현→국소화→축소→수정→회귀테스트 순서로 추측 수정과 재발 방지 |
| `main` 머지 전 | `ponytail-review` → `code-review-and-quality` | 삭제 가능한 코드와 설계·가독성·테스트 누락을 머지 전에 잡음 |
| 모듈/다이얼로그/기능 삭제 또는 다른 구현으로 이전 | `deprecation-and-migration` | 남는 호출자·참조를 추적해 제거 순서를 정하고 깨진 import 방지 |
| 되돌리기 어려운 설계 결정 (저장 위치, 포맷, 버전 규칙, 매칭 알고리즘) | `documentation-and-adrs` | `docs/adr/` 에 "왜"를 남겨 세션이 바뀌어도 결정 근거 보존 |
| 워크스페이스 로그·진단 출력 추가/변경 | `observability-and-instrumentation` | 현장 문제 보고 시 로그만으로 원인 추적 가능한 구조화 로깅 |
| "뭘 지울 수 있나", "비대하다" 요청 | `ponytail-audit` | 저장소 전체에서 삭제·단순화 후보를 우선순위로 정리 |
| 요청이 모호함 (범위·완료 조건이 안 보임) | `interview-me` → `brainstorming` | 추측 대신 질문으로 범위를 먼저 정함 |
| 처음 보는 모듈·흐름 설명 요청 | `codebase-onboarding` · `code-tour` · `graphify` | 진입점 지도와 단계별 투어 |
| 파서·매처·좌표 해석을 여러 곳에 걸쳐 고침 | `change-impact` | 고치기 전 영향 범위를 근거로 적고, 고친 뒤 diff 와 대조 |
| 리뷰 · 머지 전 | `silent-failure-hunter`(에이전트) · `python-reviewer`(에이전트) | 삼킨 예외·조용한 기본값·파이썬 관용 위반을 따로 잡음 |
| 화면 배치·색·글꼴 | `impeccable` → `ui-ux-pro-max` · `design-dna` · `awesome-design-md` · `taste-skill` | 근거 있는 디자인 결정 |
| "됐다" 고 말하기 직전 | `verification-before-completion` | 실행 결과를 붙여 완료 보고 |

- 사소한 변경(오타, 한 줄 수정, 주석)에는 스킬을 꺼내지 않는다.
- **겹칠 때 우선순위**: 이 CLAUDE.md(원본 read-only · 버전 규칙) → 작업 절차(superpowers) → 관점(Addy · ECC · ponytail) → 디자인 스킬.
  같은 일을 하는 스킬이 여럿이면 위 표가 정한 것을 쓴다(표가 superpowers 보다 우선) — 예: 디버깅은 `debugging-and-error-recovery`, 리뷰는 `ponytail-review` → `code-review-and-quality`.
- 디자인 스킬은 웹 기준으로 쓰인 것이 많다. PySide6 화면에는 원칙(위계 · 간격 · 대비 · 색)만 옮기고 CSS · 웹폰트 · CDN 조언은 따르지 않는다.
