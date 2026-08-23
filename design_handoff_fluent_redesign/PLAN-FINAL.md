# PLAN-FINAL · Defect Tracker Fluent 재설계

전제: `PLAN-01.md`(플랜) + `REVIEW-01.md`(조건부 승인)를 반영한 확정 계획.
REVIEW-01 "다음 단계 3"이 요구한 3가지(0단계 실측 결과 / P1~P5 반영 내역 / 1a·1b 분리 커밋 목록)를
채웠습니다. PLAN-02 는 불요 판정이므로 이 문서가 착수 기준입니다.

대상: `king-taek/Defect_Tracking` @ `542301e` · 작업 브랜치 `claude/new-session-8t8z4e`

---

## 0. 0단계 실측 결과

검증 환경에 PySide6 + PySide6-Fluent-Widgets 를 설치해 직접 실행한 값입니다.
(저장소에 의존성을 고정하는 커밋은 Q1 미해결이라 만들지 않았습니다. 게이트 준수.)

```
Python                     = 3.11.15
PySide6                    = 6.11.2 (Qt 6.11.2)
qfluentwidgets             = 1.11.3
설치된 Fluent 패키지        = ['PySide6-Fluent-Widgets']  (1개 - 충돌 없음)
플랫폼                     = Linux, QT_QPA_PLATFORM=offscreen (CI 와 동일 조건)
Qt 런타임 시스템 라이브러리 = libegl1 libgl1 libxkbcommon0 libdbus-1-3 필요 (CI 워크플로와 동일)
```

| 항목 | 결과 | 판단 |
|---|---|---|
| `02-design-rules.md` §5 위젯 + 부속 클래스 **93개 전수 import** | **93/93 존재**, 누락 0 | 대체안 불필요 |
| `FluentIcon` 후보 멤버 38개 | `GRID` 만 부재, 나머지 37개 존재 | nav 히트맵은 `TILES` 로 확정 |
| **offscreen `FluentWindow` 생성 + `addSubInterface` + `show`** | **성공** | **Q3 후퇴안 불필요.** 프레임리스 창을 그대로 채택 |
| `setTheme` LIGHT ↔ DARK 전환 | 성공 | |
| `FluentWindow()` 생성 시간 | **35 ms** | |
| `import qfluentwidgets` 시간 | **166 ms** | |
| 셸 최초 표시까지(import + 생성) | **약 201 ms** | **A5 의 A안 조건(150ms 미만) 미달 → B(독립 스플래시) 확정** |
| 기존 테스트 베이스라인 | **241 passed** (offscreen) | 재설계 전 그린 확인 |

추가 발견 2건:

1. **`qfluentwidgets` 는 import 시점에 홍보 문구를 stdout 으로 출력합니다**
   (`qfluentwidgets/common/config.py:411` 의 무조건 `print(ALERT)`).
   `--windowed` PyInstaller 빌드는 `sys.stdout` 이 `None` 인데, CPython 의 `print()` 는 이 경우
   조용히 무시하므로(직접 확인함) **크래시하지 않습니다.** 다만 콘솔 실행 시 매번 노출되므로
   부팅 로그를 볼 때 감안해야 합니다.
2. **핸드오프 폴더는 자동 업데이트 배포 대상에서 제외**해야 합니다. `app/updater.py` 의
   `_SKIP_DIRS` 는 "실행 필수만 배포" 원칙(최근 커밋들의 취지, `test_updater.py`에 명문화)을
   구현하는데, 536KB 문서 폴더가 저장소 루트에 생기면 모든 사용자 업데이트에 실려 갑니다.
   → `design_handoff_fluent_redesign` 을 `_SKIP_DIRS` 에 등록하고 회귀 테스트를 확장했습니다.

## 1. REVIEW-01 결정 반영표

| 질의 | 결정 | 반영 |
|---|---|---|
| Q1 라이선스 | 외부 결정. **미해결 상태로 의존성 고정 커밋 금지(게이트)** | 의존성 3중 등록은 보류. 토큰·테스트만 선행 |
| Q2 배포 크래시 | **A**(3중 등록 + 안내). 트레이스백 노출 금지(게이트) | 아래 §3 단계 0b. 안내 문구는 REVIEW 확정값 사용, 순수 Qt `QMessageBox` |
| Q3 offscreen | **A**(스파이크 후 판단). 창 클래스 이원화 금지(게이트) | 스파이크 통과 → `FluentWindow` 채택, 후퇴안 미발동 |
| Q4 Excel 기준 없음 | **B**(1차는 ★ 미표기 + 동등 열). 교차 그룹 경로는 후속 | 단계 3 범위 축소. `layer_order` 항상 전달은 게이트 |
| Q5 스플래시 | **B**(독립 스플래시 리스킨) | 실측 201ms 로 A 조건 미달 → B 확정. REVIEW 스펙 그대로 |
| Q6 도움말 문구 | **A**(프로토타입 문구 + FEAT#3 재작성) | REVIEW 제공 문구 그대로 사용. "출력 트레이" → "출력 명세" 전수 교체 |
| Q7 히트맵 분절 | 승인(데모 전용) | 자동 LOD 임계 표(A7) 채택. 지도가 한 화면은 게이트 |
| Q8 설정 카드 | 승인 + 배치 지정 | A8 카드 순서 그대로 |
| Q9 글자 크기 | **A 변형**(폰트 1.3×, 높이는 표 하한) | `HEIGHTS` 표를 `theme.py` 에 상수화 + 테스트 |
| Q10 기본 라이트 | 승인 + 첫 실행 안내 1회 | `theme_mode` 신규 필드, 미보유 사용자에게 InfoBar 1회 |
| Q11 미매칭·U | 승인 | A11 정의 채택 |
| Q12 wafer_map 삭제 | 승인 + 조건 | 탐색 바의 `SLOT · die` 를 클릭 가능하게 만들어 die 점프 경로 유지(게이트) |
| Q13 Excel 200블록 | **분할 미구현 + 출력 전 경고** | `EXPORT_WARN_BLOCKS = 200`, REVIEW 확정 문구 |
| Q14 CommandBar | 승인(QHBox) | A14 시각 고정값 준수 |

## 2. 플랜 지적사항(P1~P5) 반영

| # | 조치 | 반영 위치 |
|---|---|---|
| P1 | **µm 스케일바 미구현.** 픽셀↔µm 실비율 근거가 코드에 없으므로 가짜 정밀을 만들지 않습니다. 기준 칸 좌하단에는 `die (c, r)` 를 표기. 실비율 획득 경로(디바이스 DB·INI 배율 필드)를 발견하면 즉시 QUESTIONS 로 재질의 | 단계 2 |
| P2 | 폴더 후보 분류 `scandir` **깊이 1 고정**(`classify_selection` 계승) | 단계 4, §5 성능 |
| P3 | `setStyleSheet` 정적 검사 대상을 **qfluentwidgets 파생 객체로 한정**, `theme.py` 는 allowlist | 단계 9 테스트 |
| P4 | 단계 1을 **1a(셸·라우팅·빈 상태) / 1b(알림·진행 표시 일원화)** 로 분리 | §3 |
| P5 | **6페이지 전부 `app/ui/pages/`**, 시트·다이얼로그는 `app/ui/sheets/` | §3 전 단계 |

## 3. 단계 · 커밋 목록

`REVIEW-01` 착수 승인 범위에 따라 0a 만 선행하고, 0b 이후는 Q1 확인 후 진행합니다.

| 단계 | 커밋 | 내용 | 선행 |
|---|---|---|---|
| **0a** | ① 문서 | 핸드오프 + REVIEW-01 + PLAN-FINAL + QUESTIONS-02 저장소 반영, 업데이터 배포 제외 등록 | 없음 (완료) |
| **0a** | ② 토큰 | `theme.py` Fluent 토큰(표면·accent 3역할·상태·형태·타이포·높이표·모션) + 색 계산기(`flatten`/`contrast`/`accent_roles`) + `tests/test_tokens.py` 회귀 | 없음 (완료) |
| 0b | ③ 의존성 | `requirements.txt` `PySide6-Fluent-Widgets==1.11.3` 고정, `main.py`/`bootstrap.py` 의존성 3중 등록 + A2 안내 문구(순수 Qt QMessageBox) | **Q1** |
| 0c | ④ 부팅 | `setTheme`/`setThemeColor` 를 QApplication 직후 배치, `theme_mode` 필드 신설, 독립 스플래시 리스킨(A5 스펙) | ③ |
| **1a** | ⑤ 셸 | `FluentWindow` + `NavigationInterface` 6라우트(판독·미매칭·히트맵·출력 명세 + 하단 도움말·설정), `app/ui/pages/` 골격, 빈 상태, nav InfoBadge | ④ |
| **1b** | ⑥ 알림·진행 | `InfoBar` 스택(3.4s), 스캔 전면 상태 + `StateToolTip` + 하단 3px 바로 진행 표시 일원화, 최근 폴더 `RoundMenu` | ⑤ |
| 2 | ⑦ 판독 | 컨트롤 행(A14 고정값) + 비교 layer Flyout, 판독대 2/3/4열 + 224px + 빈 칸/사유, 220ms 크로스페이드(AD4), 필름스트립 지연 로드, 탐색 바 die 점프(A12) | ⑥ |
| 3 | ⑧ Excel | 단일 「사진 대조」 4행 블록, 회색 1단, LOT 열 순서 고정, 셀 맞춤 리사이즈, 인쇄 설정, Q4=B 범위, `EXPORT_WARN_BLOCKS`, 구조 골든 테스트 | ③ (2와 병행 가능) |
| 4 | ⑨ 폴더 선택 | BreadcrumbBar + LOT 후보 우선(지연 분류, 깊이 1) + Device 즐겨찾기 + 고정 판정 행 + TeachingTip | ⑤ |
| 5 | ⑩ 미매칭·뷰어·클러스터 | 미매칭 페이지 신설, 원본 뷰어 시트(HUD·grab 패닝), 근접 클러스터 시트([전부 명세에 담기]) | ⑤ |
| 6 | ⑪ 히트맵 | 페이지 전환, 단일 잉크 램프, 자동 LOD(A7 임계표), 드래그 영역 합산, 우측 교차 판독 | ⑦ |
| 7 | ⑫ 출력 명세 | 60px 명세 행 + 묶음 행, 행 접힘/펼침, 비우기 MessageBox, Excel 연결 | ⑥, ⑧ |
| 8 | ⑬ 설정·도움말 | SettingCard 그룹(A8 순서), ExpandGroup 개발자 모드, 도움말 페이지(A6 문구), 업데이트 다이얼로그, 첫 실행 테마 안내(A10) | ⑤ |
| 9 | ⑭ 마감 | 게이트 실측, 라이트/다크 스크린샷, `setStyleSheet` 정적 검사(P3), PyInstaller `--collect-all`, `DONE-*.md` 대조표 | 전부 |

각 커밋은 테스트 그린 상태로 만들고, `app/` 또는 `main.py` 를 건드리면
`python tools/compute_version.py --write` 결과를 같은 커밋에 포함합니다(CLAUDE.md 규칙).

## 4. 확정 규격 (구현 시 그대로 사용)

- **미매칭 표기 범위(AD1)**: Excel 은 회색 1단 + "미매칭" 한 단어(게이트 3). **앱 판독대와 미매칭
  페이지는 사유를 유지**합니다. 앱에서 사유를 지우면 판독 근거가 사라집니다.
- **accent 3역할(AD2)**: `theme.accent_roles(dark, base)` 하나에서 파생. 채움 위 글자는 반드시
  `onAccent`, 글자·글리프는 반드시 `text`. 다크 `onAccent` 는 near-black `#16140F`.
- **대비 게이트(AD3)**: `theme.contrast()` + `tests/test_tokens.py` 로 고정. 알파 토큰은 배경과
  합성 후 계산.
- **크로스페이드(AD4)**: `QGraphicsOpacityEffect` 금지(스크롤 영역 렌더 버그). 픽스맵 2장 알파
  합성 + `QVariantAnimation(0->1, 220ms, OutQuint)`. scale 1.012->1 은 생략 가능.
- **em-dash 0건(AD5)**: 손대는 파일 범위에서 기존 주석까지 정리. `theme.py` 는 이번에 완료.
- **자동 LOD(A7)**: die 한 변 20px 이상은 현행 + 5x5 분할 / 6~19px 는 하위분할 → 간격 → 테두리
  순서로 해제 / 6px 미만은 `QImage` 래스터 1장 + 드래그 영역 합산. 지도는 항상 한 화면(게이트).
- **높이(A9)**: `theme.HEIGHTS` 표. 폰트만 1.3배, radius·gap·패딩은 두 배율 동일(게이트).

## 5. 미해결 (착수 전 답변 필요)

| 항목 | 상태 | 막는 범위 |
|---|---|---|
| **Q1 라이선스** | 사업 주체 확인 대기 | 커밋 ③ 이후 전부 |
| **QUESTIONS-02 Q15·Q16** | 라이트 테마 대비 게이트 미달 4쌍(accent 채움, 상태색 3종) | 토큰 확정. 현재 strict xfail 로 표시 |
| QUESTIONS-02 Q17 | 게이트 적용 대상 정의 | 테스트 목록만 영향, 구현은 진행 가능 |

## 6. 완료 기준 (DoD)

PLAN-01 H절 그대로 유지하고 아래를 추가합니다.

- [ ] QUESTIONS-02 결론 반영 + `tests/test_tokens.py` 의 strict xfail 제거
- [ ] die 점프 경로 유지(A12 게이트): 탐색 바 `SLOT · die` 클릭 → 히트맵에서 해당 die 선택
- [ ] Excel `layer_order` 항상 전달(게이트) + 기준 없음 모드에서 ★ 미표기
- [ ] 지도가 항상 한 화면(A7 게이트)
- [ ] 6페이지 `app/ui/pages/` · 시트 `app/ui/sheets/` 배치(P5)
- [ ] `design_handoff_fluent_redesign` 이 자동 업데이트 배포본에 포함되지 않음(회귀 테스트로 고정)
