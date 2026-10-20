# Vendored skills

프로젝트에 설치된 외부 skill 모음. 각 폴더는 `SKILL.md` 를 가진 독립 skill 이며,
Claude Code 세션에서 자동 인식된다(별도 플러그인 설치·네트워크 불필요).

## 출처 / 버전

| Skill 폴더 | 출처 | 버전 |
|---|---|---|
| `impeccable/` | https://github.com/pbakaus/impeccable | 3.9.1 |
| `ponytail/`, `ponytail-review/`, `ponytail-audit/`, `ponytail-debt/`, `ponytail-help/`, `ponytail-gain/` | https://github.com/DietrichGebert/ponytail `skills/*` @ `09c434ab` (MIT) | 2026-10-18 |
| `graphify/` | https://github.com/safishamsi/graphify `graphify/skill.md` + `graphify/skills/claude/references/` @ `86c57be8` (0.9.92, Apache-2.0 · `NOTICE`) | 2026-10-18 |
| `brainstorming/`, `systematic-debugging/`, `test-driven-development/`, `writing-plans/`, `executing-plans/`, `subagent-driven-development/`, `dispatching-parallel-agents/`, `requesting-code-review/`, `receiving-code-review/`, `verification-before-completion/`, `finishing-a-development-branch/`, `using-git-worktrees/`, `writing-skills/`, `using-superpowers/` | https://github.com/obra/superpowers | 6.1.1 |

`impeccable-manual-edit-applier` 서브에이전트(`.claude/agents/`)는 impeccable 의 `live` 수동
편집 흐름에서만 쓰인다.

## 의도적으로 설치하지 않은 것 (hooks)

원본 저장소는 다음 hook 을 포함하지만, 편집마다 지연/잡음을 유발하거나 세션 동작을
강제하므로 이 프로젝트에는 **연결하지 않았다**. 필요하면 직접 `.claude/settings.json` 에 추가:

- impeccable `PostToolUse` 감지 hook — 매 Edit/Write 후 UI 파일을 검사(웹 프론트엔드 전용,
  이 프로젝트는 PySide6 데스크톱 앱이라 대부분 무관).
- superpowers `session-start` hook — 매 세션 시작 시 skill 사용을 강제.

## 업데이트

vendoring 방식이라 자동 업데이트되지 않는다. 갱신하려면 위 저장소에서 해당 폴더
(impeccable 은 `.claude/skills/impeccable/`, superpowers 는 `skills/*`)를 다시 복사한다.

## ponytail · graphify 메모 (2026-10-18)

- ponytail 은 원본 플러그인의 hook·band(세션 상태 표시줄)는 연결하지 않고 스킬 파일만 복사했다. 강도는 CLAUDE.md 규칙대로 로직 full, UI lite.
- graphify 는 처음 실행할 때 `graphifyy` 를 pip 으로 설치한다. 코드만 볼 때는 `--code-only` 로 돌린다(문서·이미지는 Claude 로 보내 분석한다). 산출물 `graphify-out/` 은 `.gitignore` 에 있다.

## 10/18 추가 설치 (사용자 요청 — 다양하게, 자동으로)

| 폴더 | 출처 · 고정 커밋 | 라이선스 | 무엇 |
|---|---|---|---|
| `interview-me/` · `documentation-and-adrs/` · `observability-and-instrumentation/` · `deprecation-and-migration/` · `security-and-hardening/` · `performance-optimization/` | https://github.com/addyosmani/agent-skills `skills/*` @ `aeac41d4` | MIT (`.claude/licenses/addyosmani-agent-skills-MIT.txt`) | 요구 묻기 · 결정 기록 · 로그 · 삭제/이전 · 보안 · 성능. 체크리스트는 `.claude/references/` |
| `debugging-and-error-recovery/` · `code-review-and-quality/` | 위와 같음 | MIT | CLAUDE.md 표가 이미 부르던 두 스킬 |
| `change-impact/` · `codebase-onboarding/` · `code-tour/` · `python-testing/` · `regex-vs-llm-structured-text/` · `skill-stocktake/` + 에이전트 `.claude/agents/silent-failure-hunter.md` · `python-reviewer.md` | https://github.com/affaan-m/ecc @ `76aaa77d` (v2.2.3) 에서 발췌 | MIT (`.claude/licenses/ecc-MIT.txt`) | 변경 영향 · 코드 안내 · pytest · 파서 판단 · 스킬 점검 · 조용한 실패/파이썬 리뷰 |
| `ui-ux-pro-max/` | https://github.com/nextlevelbuilder/ui-ux-pro-max-skill `.claude/skills/ui-ux-pro-max` @ `56ea9cf1` (2.15.0) | MIT (`.claude/licenses/ui-ux-pro-max-MIT.txt`) | 로컬 CSV 로 팔레트 · 글꼴 · UX 지침 검색(네트워크 없음) |
| `design-dna/` | https://github.com/zanwei/design-dna @ `593e39bc` | MIT (`LICENSE`) | 참고 화면에서 토큰 · 느낌 · 효과를 JSON 으로 뽑고 적용 |
| `awesome-design-md/` | https://github.com/VoltAgent/awesome-design-md `design-md/` @ `13be5c05` | MIT (`LICENSE`) | DESIGN.md 73개 참고 라이브러리(SKILL.md 는 이 저장소용으로 새로 씀) |
| `taste-skill/` | https://github.com/Leonxlnx/taste-skill `skills/taste-skill` @ `ce26fc25` | MIT (`LICENSE`) | 안티-슬롭 원칙(랜딩 페이지 중심 — 원칙만 골라 씀, 사진 URL 조언은 무시) |

- 원본을 고치지 않고 그대로 복사했다(awesome-design-md 의 `SKILL.md` 만 예외). hook 은 하나도 연결하지 않았다 — ECC 의 gateguard 처럼 수정마다 멈추게 하는 것이 있어서다. ECC 의 토큰 · 모델 설정도 가져오지 않았다.
- 설치 전 NVIDIA SkillSpector(`--no-llm`)로 전부 검사했다. 걸린 항목은 공격 용어를 설명하는 문서 · 스킬 파일을 고치라는 안내(writing-skills) · 중첩 코드 블록을 위한 폭 0 공백(improve-animations `PLAN-TEMPLATE.md`) 같은 오탐이었고, 스크립트에 바깥 전송은 없었다.
- Addy 스킬이 `../../references/*.md` 로 가리키는 체크리스트는 `.claude/references/` 에 있다. 폴더 안에 라이선스가 없는 출처의 원문은 `.claude/licenses/` 에 있다.
- 겹칠 때 우선순위는 `CLAUDE.md` 에 적었다. 갱신은 같은 고정 커밋 경로에서 다시 복사한다.
- 데스크톱(PySide6) 앱이라 디자인 스킬의 CSS · 웹폰트 · CDN 조언은 버리고 원칙만 쓴다.

## 모션 레퍼런스 링크 (2026-10-20, 사용자 요청)

| 폴더 | 출처 | 라이선스 | 무엇 |
|---|---|---|---|
| `motion-reference/` | https://motion-reference.takayustudio.jp/ (TakayuStudio) — 외부 파일 없음, `SKILL.md` 만 이 저장소에서 새로 씀 | **명시 없음**("개인 학습용 레퍼런스") — 그래서 링크만 둔다 | 모션 이름 · 시간 · 이징을 찾는 사전. 코드 · 설명 · 목록은 복사하지 않고 수치와 원리만 참고 |

- 받아 온 파일이 없어 SkillSpector 검사는 하지 않았다.
