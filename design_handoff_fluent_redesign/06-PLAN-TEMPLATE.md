# 06 · PLAN 템플릿 (STEP 1에서 이 파일을 복사해 PLAN-01.md 로 채우세요)

## A. 환경 실측

```
qfluentwidgets.__version__ =
Qt 바인딩 =                     (PySide6 / PyQt6 / ...)
Python =
설치된 Fluent 패키지 =           (1개여야 함. pip list | grep -i fluent)
OS / DPI 스케일 =
```

- [ ] Fluent 패키지가 1개만 설치되어 있음을 확인했습니다
- [ ] `02-design-rules.md` §5의 위젯이 이 버전에 모두 존재함을 확인했습니다 (없는 것은 아래 표에 기록)

| 명세 위젯 | 이 버전 존재 여부 | 대체안 |
|---|---|---|

## B. 작업 분해

| 단계 | 범위 | 파일 | 예상 규모 | 선행 조건 |
|---|---|---|---|---|
| 1 |  |  |  |  |

분해 이유(왜 이 순서인지 한 문단):

## C. 파일별 변경 계획

| 파일 | 신규/전면교체/부분수정 | 요지 | 위험 |
|---|---|---|---|
| app/ui/theme.py |  |  |  |
| app/ui/main_window.py |  |  |  |
| app/ui/controls.py |  |  |  |
| app/ui/compare_grid.py |  |  |  |
| app/ui/thumbnail_strip.py |  |  |  |
| app/ui/wafer_map.py |  |  |  |
| app/ui/heatmap_dialog.py |  |  |  |
| app/ui/nomatch_gallery.py |  |  |  |
| app/ui/export_dialog.py |  |  |  |
| app/ui/settings_dialog.py |  |  |  |
| app/ui/help_dialog.py |  |  |  |
| app/ui/folder_picker.py |  |  |  |
| app/ui/image_viewer.py |  |  |  |
| app/ui/splash.py |  |  |  |
| app/ui/busy_overlay.py |  |  |  |
| app/ui/notifications.py |  |  |  |
| app/ui/widgets.py |  |  |  |
| app/ui/cluster_view.py |  |  |  |
| app/export/excel_report.py |  |  |  |

## D. FluentIcon 매핑

| 용도 | 프로토타입 글리프 | FluentIcon 후보 | 확정 |
|---|---|---|---|
| nav 판독 | ◉ |  |  |
| nav 미매칭 | ⊘ |  |  |
| nav 히트맵 | ▦ |  |  |
| nav 출력 명세 | ☰ |  |  |
| nav 도움말 | ? | `FluentIcon.HELP` |  |
| nav 설정 | ⚙ | `FluentIcon.SETTING` |  |
| LOT 폴더 | 🗀 | `FluentIcon.FOLDER` |  |
| 줌 ＋/－ |  | `ZOOM_IN`/`ZOOM_OUT` |  |
| 맞춤 |  | `FIT_PAGE` |  |
| 정보 복사 |  | `COPY` |  |
| 업데이트 | ⬆ | `UPDATE` |  |

## E. 성능 계획

| 시나리오 | 규모 | 현재 예상 | 대책 |
|---|---|---|---|
| 히트맵 die | 4,096 |  | 래스터 LOD |
| 필름스트립 썸네일 | 599장 |  |  |
| 판독대 동시 이미지 | 12칸 |  |  |
| Excel 이미지 | 담은 12건 × 12 = 144 |  |  |

## F. 테스트 계획

- `tests/test_ui_smoke.py` (26,888 bytes) 중 깨질 것으로 예상되는 항목:
- `tests/test_new_features.py` (55,194 bytes) 중 영향 범위:
- 대응 방안:

## G. 질의 목록

> 형식은 `01-PROTOCOL.md` STEP 1 참조. 우선순위 태그: `[BLOCKER]` / `[택1]` / `[확인]`

### Q1. [BLOCKER] 
- **분류**: 
- **근거 파일**: 
- **현재 상황**: 
- **충돌 내용**: 
- **내 제안 A**: (비용: )
- **내 제안 B**: (비용: )
- **원하는 답 형태**: 

### Q2. 
...

## H. 완료 기준 (DoD)

- [ ] 게이트 4개 준수 (대비 5.0 / accent 3역할 / 미매칭 회색 1단 / 판독대 12칸)
- [ ] 모든 서브 인터페이스에 고유 `setObjectName()`
- [ ] Fluent 위젯에 `setStyleSheet()` 직접 호출 0건
- [ ] 라이트/다크 양쪽 스크린샷 확인
- [ ] 원본 계승 항목 유지 (`assert_output_safe`, read-only 원본, NoScroll 입력, 세로휠→가로스크롤, row 0 하단)
- [ ] 기존 테스트 통과 또는 갱신 근거 문서화
