# Vendored skills

프로젝트에 설치된 외부 skill 모음. 각 폴더는 `SKILL.md` 를 가진 독립 skill 이며,
Claude Code 세션에서 자동 인식된다(별도 플러그인 설치·네트워크 불필요).

## 출처 / 버전

| Skill 폴더 | 출처 | 버전 |
|---|---|---|
| `impeccable/` | https://github.com/pbakaus/impeccable | 3.9.1 |
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
