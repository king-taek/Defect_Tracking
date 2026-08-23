# Handoff: Defect Tracker - Fluent Design 전면 재설계

## 0. 이 문서를 읽는 순서 (Claude Code 필독)

1. 이 README 전체
2. `01-PROTOCOL.md` - **Claude Design과 왕복하는 절차. 먼저 플랜 MD를 쓰고 검토받은 뒤 구현합니다.**
3. `02-design-rules.md` - 판단 기준(토큰/모션/카피/대비 게이트)
4. `03-screens.md` - 화면별 구현 명세
5. `04-excel-report.md` - Excel 출력 재설계 명세
6. `05-verified-source-facts.md` - 원본 코드 실측값(전수조사 결과, BEFORE 근거)
7. HTML 프로토타입 2종을 브라우저로 직접 열어 조작

> **중요**: 코드를 쓰기 전에 `01-PROTOCOL.md`의 STEP 1(플랜 작성 → 질의)을 먼저 수행하세요.
> 플랜 검토 없이 구현을 시작하지 마세요.

## Overview

기존 `king-taek/Defect_Tracking` (PySide6 + 커스텀 QSS 다크 네온 테마) 데스크톱 앱의
전 화면·전 상태를 **QFluentWidgets(PySide6-Fluent-Widgets) 기반 Fluent Design**으로 재설계한 결과물입니다.

- 대상 저장소: `king-taek/Defect_Tracking` @ `main` (commit `542301e05d41` 기준으로 감사)
- 재설계 범위: `app/ui/*` 전체(21파일) + `app/export/excel_report.py`
- 실사용 규모 전제: **layer 12개(후보 24개) · layer당 사진 40~60장 · 총 599장 · wafer 25슬롯 · die 수천 개까지**

## About the Design Files

번들에 든 HTML은 **디자인 레퍼런스**입니다 - 의도한 외관·모션·상태 전이를 브라우저에서 조작해 볼 수 있는
프로토타입이며, 그대로 옮겨 붙일 프로덕션 코드가 아닙니다.

과제는 이 HTML이 보여주는 것을 **대상 코드베이스의 환경(PySide6 + qfluentwidgets)으로 재현**하는 것입니다.
HTML의 CSS 값은 Qt 위젯 속성/QSS/QPropertyAnimation으로 번역해야 합니다.
`02-design-rules.md`에 CSS → Qt 대응표가 있습니다.

## Fidelity

**High-fidelity (hifi)** 입니다. 색상 hex, 폰트 크기, 간격, 반경, 모션 duration·easing이 모두 확정값입니다.
`02-design-rules.md`의 토큰을 단일 출처로 삼고, 화면에서 색을 새로 만들지 마세요.

단, 다음은 **의도적으로 미확정**이며 STEP 1에서 질의 대상입니다:
- 아이콘: 프로토타입은 텍스트 글리프(◉ ▦ ☰ ⊘ ⚙ ?)로 대체했습니다. 실제로는 `FluentIcon` 열거값을 쓰세요.
- 폰트: 프로토타입은 웹폰트(Inter Tight/Noto Sans KR)를 씁니다. 실제로는 `Segoe UI Variable` + `Malgun Gothic` 폴백.
- 수치용 등폭 서체: 프로토타입 `Inter Tight` → Qt에서는 `Cascadia Mono`/`Consolas` + `QFont.setStyleHint(QFont.Monospace)`.

## HTML 프로토타입 파일

| 파일 | 내용 | 조작 방법 |
|---|---|---|
| `Fluent 프로토타입.dc.html` | **주 산출물.** 앱 전체(6페이지 + 9오버레이) 실동작 | 좌측 nav로 페이지 이동, 상단 버튼으로 빈 상태/스캔/업데이트/Splash 재생 |
| `Excel 리포트 개선.dc.html` | Excel 출력 BEFORE/AFTER | 상단 [기준 있음]/[기준 없음] 토글, 기준 layer 버튼, 인쇄 경계 보기 |

각 파일은 `support.js`와 `img/` 폴더를 같은 위치에서 참조합니다. 함께 두고 열어야 렌더됩니다.

## Screens / Views

`03-screens.md`에 화면별 전체 명세가 있습니다. 요약:

| # | 화면 | 원본 파일 | 핵심 변경 |
|---|---|---|---|
| 1 | 판독 | main_window.py, controls.py, compare_grid.py | 사이드바 폼 → NavigationInterface + CommandBar. 판독대 12칸까지 4열 확장 |
| 2 | 미매칭 | nomatch_gallery.py | 4열 갤러리 + 사유 SegmentedWidget 필터 |
| 3 | 히트맵 | heatmap_dialog.py | 단일 잉크 램프, die 수천개 래스터 LOD |
| 4 | 출력 명세 | export_dialog.py | 카드 격자 → 명세 행 + 합계 |
| 5 | 도움말 | help_dialog.py | 단축키 표 + 기능 카드 |
| 6 | 설정 | settings_dialog.py | SettingCard 그룹 + ExpandGroupSettingCard |
| 7 | 폴더 선택 | folder_picker.py | BreadcrumbBar + LOT 후보 자동 판별 + Device 즐겨찾기 |
| 8 | 원본 뷰어 | image_viewer.py | 순검정 무대 + CommandBar HUD + grab 패닝 |
| 9 | 로딩·알림 | splash.py, busy_overlay.py, notifications.py | SplashScreen / StateToolTip / InfoBar |
| 10 | Excel 출력 | app/export/excel_report.py | `04-excel-report.md` 참조 |

## Interactions & Behavior

`02-design-rules.md` §3 모션 규격 참조. 요약:
- 컨트롤 상태(hover/pressed): 120ms linear
- 진입: 250ms `cubic-bezier(0,0,0,1)` / 퇴장: 150ms `cubic-bezier(.7,0,1,.5)`
- nav pill 인디케이터: 300ms `cubic-bezier(.1,.9,.2,1)`
- 시트/다이얼로그: 스크림 200ms linear + 시트 250ms scale .96→1
- pressed 피드백: `translateY(1px)` + 채움색 한 단 어둡게

## State Management

`03-screens.md` 각 화면의 "상태" 절 참조. 앱 전역 상태:
```
page, navExpanded, theme(light|dark), baseLayer, compareLayers{}, tolerance, clusterRadius,
cur(현재 기준 index), tray[], batchSnapshot, heatSel, heatScale, heatLayers{},
zoom, pan, sheet(''|picker|viewer), infoBars[], devMode, autoUpdate
```

## Design Tokens

`02-design-rules.md` §1~2. 라이트/다크 각 15토큰, accent 3역할 분리(fill/on-fill/text).

## Assets

- `img/def01.jpg` ~ `def10.jpg`: **합성 샘플 이미지**입니다. 실제 defect 사진이 아니며 구현 시 사용하지 마세요.
  프로토타입에서 사진 자리를 채우기 위한 목업입니다.
- 아이콘: 전부 `qfluentwidgets.FluentIcon` 으로 대체 (STEP 1에서 매핑 확정)
- 폰트: 시스템 폰트만 사용. 번들 폰트 없음.

## Files

```
design_handoff_fluent_redesign/
  README.md                      이 파일
  01-PROTOCOL.md                 Claude Code <-> Claude Design 왕복 절차 (먼저 읽으세요)
  02-design-rules.md             토큰 · 모션 · 카피 · 대비 게이트 + CSS→Qt 대응표
  03-screens.md                  화면별 구현 명세 10개
  04-excel-report.md             Excel 출력 재설계 명세
  05-verified-source-facts.md    원본 코드 실측값(전수조사 결과)
  06-PLAN-TEMPLATE.md            STEP 1에서 채워 제출할 플랜 양식
  Fluent 프로토타입.dc.html        주 산출물
  Excel 리포트 개선.dc.html         Excel BEFORE/AFTER
  support.js                     HTML 런타임 (수정하지 마세요)
  img/                           합성 샘플 이미지 10장
```
