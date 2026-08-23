# PLAN-01

대상: `king-taek/Defect_Tracking` @ `542301e` (핸드오프 감사 커밋과 동일함을 확인)
작성 근거: 핸드오프 전 문서 + 프로토타입 2종(전 상태·모션·카피를 소스 수준에서 추출) + 저장소
전수 판독. 코드 인용은 전부 실제 라인.

> 이 문서는 Claude Design 에 전달해 `REVIEW-01.md` 를 받은 원본입니다. 실측값 확정과 결정 반영은
> `PLAN-FINAL.md` 를 보세요. A절의 "미설치" 표기는 작성 시점 기준이며, 0단계 실측 결과는
> PLAN-FINAL §0 에 있습니다.

## A. 환경 실측

```
qfluentwidgets.__version__ =  (미설치 - 채택 대상: PySide6-Fluent-Widgets 1.11.3,
                               PyPI 최신 2026-08-01 릴리스에서 확인)
Qt 바인딩                  =  PySide6 (requirements.txt: PySide6>=6.6 - 현 검증 환경에는
                               PySide6 자체도 미설치, CI 는 3.11 + offscreen)
Python                     =  3.11.15 (검증 환경) / CI 3.11 (.github/workflows/test.yml)
설치된 Fluent 패키지        =  0개 (신규 도입. 설치 시 PySide6-Fluent-Widgets 1개만.
                               의존성: PySideSix-Frameless-Window>=0.8.0, darkdetect)
OS / DPI                   =  개발·CI: Linux offscreen / 프로덕션: Windows
                               (Segoe UI Variable·Malgun Gothic, main.py:88-90 의
                               HighDpiScaleFactorRoundingPolicy.PassThrough 유지)
저장소 상태                 =  HEAD 542301e, 워킹트리 클린, 현재 앱 버전 1.33.84
```

- [x] Fluent 패키지 충돌 없음(0개 상태에서 신규 1개만 추가)
- [x] §5 위젯 존재 대조 - v1.11.3 공식 카탈로그 기준 전 항목 존재 확인. 실제 import 전수 실행과
  offscreen `FluentWindow` 스모크는 0단계 첫 작업으로 실측(PLAN-FINAL §0).

| 명세 위젯 | v1.11.3 존재 | 비고/대체안 |
|---|---|---|
| FluentWindow / MSFluentWindow | 있음 | 좌측 nav 필요 → FluentWindow 채택 |
| NavigationInterface / addSubInterface / NavigationItemPosition | 있음 | |
| InfoBadge (+InfoBadgePosition.NAVIGATION_ITEM) | 있음 | |
| CommandBar | 있음 | Q14: 일반 행 구성 제안 |
| ComboBox / EditableComboBox | 있음 | QComboBox 미상속(QPushButton 기반) |
| DoubleSpinBox / CompactDoubleSpinBox | 있음 | |
| Flyout / FlyoutViewBase / FlyoutAnimationType | 있음 | |
| CardWidget / SimpleCardWidget / ElevatedCardWidget | 있음 | |
| SegmentedWidget / Pivot | 있음 | |
| SwitchButton | 있음 | |
| SettingCardGroup / PushSettingCard / ComboBoxSettingCard / SwitchSettingCard / ExpandGroupSettingCard | 있음 | |
| InfoBar / InfoBarPosition | 있음 | 기본 duration 1000ms → 3400ms |
| StateToolTip / ProgressBar / IndeterminateProgressRing | 있음 | |
| MessageBox / MessageBoxBase / MaskDialogBase | 있음 | 시트형은 MaskDialogBase |
| TeachingTip / TeachingTipTailPosition | 있음 | |
| RoundMenu / Action | 있음 | QAction 대신 qfluentwidgets.Action |
| BreadcrumbBar / SearchLineEdit / SplashScreen | 있음 | SplashScreen 은 Q5 |
| SmoothScrollArea / ScrollArea / SingleDirectionScrollArea | 있음 | QScrollArea 상속 |
| ToolTipFilter / TransparentToolButton / HyperlinkButton / PillPushButton | 있음 | 지연 300ms |
| setTheme / toggleTheme / setThemeColor / setCustomStyleSheet / isDarkTheme / qconfig.themeChanged | 있음 | |

리스크: 라이선스 GPLv3 비상업 한정(Q1) / 프레임리스 offscreen(Q3) / 폰트는 README 확정대로
`Segoe UI Variable`+`Malgun Gothic`, 수치 등폭 `Cascadia Mono`.

## B. 작업 분해

| 단계 | 범위 | 주요 파일 | 규모 | 선행 |
|---|---|---|---|---|
| 0 | 기반: 의존성 3중 등록·offscreen 스파이크·토큰 모듈 재작성·대비 게이트 테스트·NoScroll Fluent 서브클래스·아이콘 실측 | requirements.txt, bootstrap.py, main.py, theme.py, widgets.py, tests | 중 | REVIEW-01 |
| 1 | 앱 셸: FluentWindow+NavigationInterface·부팅·빈 상태·InfoBar·스캔 상태+StateToolTip·최근 폴더 RoundMenu | main.py, main_window.py, splash.py, notifications.py, busy_overlay.py | 대 | 0 |
| 2 | 판독 페이지 | controls.py, compare_grid.py, thumbnail_strip.py, widgets.py | 대 | 1 |
| 3 | Excel 재설계(순수 로직, 병행 가능) | excel_report.py, tests | 중 | 0 |
| 4 | 폴더 선택 시트 | folder_picker.py | 대 | 1 |
| 5 | 미매칭 페이지·원본 뷰어·근접 클러스터 | nomatch_gallery.py, image_viewer.py, cluster_view.py | 중 | 1-2 |
| 6 | 히트맵 페이지 | heatmap_dialog.py, heatmap.py, wafer_map.py(삭제) | 대 | 1-2 |
| 7 | 출력 명세 페이지 | export_dialog.py | 중 | 1, 3 |
| 8 | 설정·도움말 페이지·업데이트 | settings_dialog.py, help_dialog.py | 중 | 1 |
| 9 | 마감: 게이트 실측·스크린샷·테스트·패키징·DONE | build_exe.py, tests, docs | 중 | 전부 |

분해 이유: Tier-1 리스크(프레임리스 offscreen·의존성 배포·토큰 체계)가 이후 전 단계의 전제라
0단계에 몰았다. 셸(1)이 모든 페이지의 컨테이너라 다음. 최대 화면(판독)을 가장 이른 대형 단계로
두어 위험을 앞당기고, Excel(3)은 Qt 무관이라 병행 트랙.

## C. 파일별 변경 계획

19개 파일의 신규/전면교체/부분수정 구분과 근거 라인은 `PLAN-FINAL.md` §3 및 아래 요지를 참조.

| 파일 | 구분 | 요지 |
|---|---|---|
| app/ui/theme.py | 전면교체 | 다크 네온 QSS(43-308)·`_make_arrow`(311-342)·regex 폰트 스케일(349-360) 폐기 → 라이트/다크 토큰·accent 3역할·대비 계산기 |
| app/ui/main_window.py | 전면교체 | QMainWindow+스플리터(202-330) → FluentWindow 셸+라우팅. 단축키 12종(342-360)·최근 폴더(445-453)·지오메트리(1573-1587) 계승 |
| app/ui/controls.py | 전면교체 | SideBar 폼 해체 → 컨트롤 행+비교 Flyout. NoScroll*(34-57) Fluent 재작성 |
| app/ui/compare_grid.py | 전면교체 | 2열 고정 `_repack`(266) → 2/3/4열+224px. 미매칭 셀 숨김(258-260) → 빈 판+사유 복원 |
| app/ui/thumbnail_strip.py | 부분수정 | 세로휠→가로(141-154)·220ms OutCubic(47-49) 계승, 지연 로드 |
| app/ui/wafer_map.py | 삭제 | 03 §1. row0 하단·die 점프는 히트맵이 계승 |
| app/ui/heatmap_dialog.py | 전면교체 | 다이얼로그(294) → 페이지. `#39ff14`(198-199) 제거, 래스터 LOD 신설, 드래그(241-282)·지연 로드(835-857) 계승 |
| app/ui/nomatch_gallery.py | 전면교체 | 데드 코드(62) → 신설 페이지. `_REASON_META`(33-43) 계승 |
| app/ui/export_dialog.py | 전면교체 | 카드 격자 → 명세 행. 반환 계약·`layer_order`(main_window.py:1538) 유지 |
| app/ui/settings_dialog.py | 전면교체 | QFormLayout → SettingCard 그룹. LOT 내부 차단(318-332) 계승 |
| app/ui/help_dialog.py | 전면교체 | 다이얼로그 → 페이지. 그룹·항목 구조 계승 |
| app/ui/folder_picker.py | 전면교체 | 트리+4색 배너 → BreadcrumbBar+후보 정렬+판정 행. 자동 보정(763-778)·토큰 가드(653-664) 계승 |
| app/ui/image_viewer.py | 전면교체 | 시트형. 메타 4줄(159-170) → 1줄. 휠 앵커 줌(187-207) 계승 |
| app/ui/splash.py | 전면교체 | Q5 결정 반영 |
| app/ui/busy_overlay.py | 전면교체 | 진행 표시 일원화. `pump()`(149-157) 계약 유지 |
| app/ui/notifications.py | 전면교체 | 상단 중앙 배너 → InfoBar TOP_RIGHT 스택 |
| app/ui/widgets.py | 부분수정 | 픽스맵 합성 크로스페이드, 스테일 가드(82-89) 계승 |
| app/ui/cluster_view.py | 부분수정 | 시트 + [전부 명세에 담기]. 몽키패치(181) 제거 |
| app/export/excel_report.py | 전면교체 | 04 명세. `assert_output_safe`(117) 유지 |

## D. FluentIcon 매핑 확정안

nav 판독 `VIEW`(대체 `PHOTO`) · nav 미매칭 `CANCEL` · nav 히트맵 `TILES`(대체 `ALBUM`) ·
nav 출력 명세 `DOCUMENT` · 도움말 `HELP` · 설정 `SETTING` · LOT 폴더 `FOLDER` ·
최근 `HISTORY` · 담기 `ADD` · 제거/닫기 `CLOSE` · 줌 `ZOOM_IN`/`ZOOM_OUT` · 맞춤 `FIT_PAGE` ·
정보 복사 `COPY` · 업데이트 `UPDATE` · 즐겨찾기 `PIN` · 비우기 `DELETE`.
1:1·맞춤·미매칭 점프·`■ 중단` 은 텍스트 버튼 유지. 이모지 전량 제거(02 §4).

## E. 성능 계획

| 시나리오 | 규모 | 현재 문제 | 대책 |
|---|---|---|---|
| 히트맵 die | 4,096 | paintEvent 전량 재그리기+분할 25×(149-186) | 래스터 LOD, 누적합 영역 합산 |
| 필름스트립 | 599장 | eager 위젯(81-92)+동기 디코드(widgets.py:146-152) | 가시 범위 지연 로드 |
| 판독대 | 12칸 | 2열 고정이라 미노출 | ImageLoader 계승, 셀 크기 디코드 |
| Excel | 144장 | 앵커만 지정(55-70), 318MB 사례 | 셀 맞춤 리사이즈, 담은 것만 |
| 폴더 후보 분류 | 수백 | 신규 부하 | 지연 분류 + 캐시 + 토큰 무효화 |

## F. 테스트 계획

총 237개 중 UI 114개. 순수 로직 123개는 무영향(예외: `theme.STYLESHEET` 잠금 2건, branding grep).
확실 파손: `"⚙ 설정"` 리터럴, QMessageBox 정적 몽키패치, 프레임리스 관련 창 속성, zoomGlyph 계약,
위젯 부모 관계, 픽셀 높이, 지오메트리 왕복. 화면 단계 커밋마다 같은 커밋에서 갱신.
신규: 대비 게이트 / Excel 구조 골든 / 히트맵 LOD 합 보존 / setStyleSheet 정적 검사.

## G. 질의 목록 (14건)

> 답변은 `REVIEW-01.md` 의 A1~A14 참조.

### Q1. [BLOCKER] qfluentwidgets 라이선스(GPLv3·비상업 한정)로 진행해도 되는가
- **분류**: 범위 | **근거**: PyPI PySide6-Fluent-Widgets 1.11.3 (상업 사용 유료)
- **현재 상황**: 사내 반도체 검사 실무 도구 - 상업 사용 소지
- **충돌**: 핸드오프 전체가 qfluentwidgets 전제
- **제안 A**: 사용 조건 확인 후 진행(비용 낮음, 외부 절차) / **B**: 02 토큰만으로 커스텀 QSS 재구현(높음)
- **원하는 답**: 규칙 확인

### Q2. [BLOCKER] 자동 업데이트가 코드만 배포(pip 미실행) - 기존 설치본 크래시 방지책
- **분류**: 범위 | **근거**: app/updater.py:222-260, main.py:16-20, bootstrap.py:27-31
- **현재 상황**: 의존성 검사 목록에 qfluentwidgets 없음
- **충돌**: 반영 순간 기존 사용자 전원 ImportError
- **제안 A**: `_REQUIRED` 3중 등록 + 안내(낮음) / **B**: 업데이트 직후 pip 자동 설치(중)
- **원하는 답**: A/B 택1

### Q3. [BLOCKER] offscreen 에서 FluentWindow 불안정 시 후퇴 허용?
- **분류**: 충돌 | **근거**: tests/test_ui_smoke.py:14, .github/workflows/test.yml:18-31
- **현재 상황**: UI 테스트 114개 전부 offscreen. qframelesswindow 는 네이티브 훅 사용
- **충돌**: 실패 시 픽스처에서 전량 사망
- **제안 A**: 스파이크 후 실패 시 QMainWindow+NavigationInterface(낮음) / **B**: 테스트만 창 클래스 분기(중)
- **원하는 답**: 규칙 확인

### Q4. [택1] Excel 「기준 없음」 교차 그룹 - 신규 데이터 경로 신설 범위
- **분류**: 범위 | **근거**: 04 §기준 없음, excel_report.py:91-103, heatmap_dialog.py:775-784
- **현재 상황**: 교차 그룹은 base 인덱스로 환원되고 기준 없는 그룹은 버려짐
- **충돌**: "블록=교차 그룹·매칭 n/12·★ 없음" 구현 불가
- **제안 A**: 전용 항목형+export 경로 신설(높음, 나는 A 제안) / **B**: 1차는 ★ 미표기·동등 열만(낮음)
- **원하는 답**: A/B 택1

### Q5. [택1] 스플래시: 즉시 표시(현행) vs 창 내 SplashScreen
- **분류**: 동작 | **근거**: 05 계승 필수, main.py:98-122, 프로토타입 z80
- **충돌**: SplashScreen 은 창이 먼저 필요 - 셸 생성 시간만큼 첫 피드백 지연
- **제안 A**: 셸 경량 생성 후 부착(중) / **B**: 독립 스플래시 Fluent 리스킨(낮음)
- **원하는 답**: A/B 택1

### Q6. [택1] 도움말 문구: 원본 유지 vs 프로토타입 개정판
- **분류**: 카피 | **근거**: help_dialog.py:22-65, 프로토타입 HELP/FEAT, heatmap_dialog.py:423-425
- **충돌**: 개명("출력 명세")·현 동작과 불일치. FEAT#3 은 제거된 토글을 설명
- **제안 A**: 프로토타입 문구 + FEAT#3 재작성(낮음) / **B**: 원문 유지(불일치 잔존)
- **원하는 답**: A/B + FEAT#3 확정 문구

### Q7. [확인] 히트맵 42/1,024/4,096 분절은 데모 전용인가
- **분류**: 동작 | **근거**: 프로토타입 hsSeg, app/heatmap.py:19-21, heatmap_dialog.py:534-540
- **제안**: 데모 전용. 실앱은 자동 LOD + 사진 크기 슬라이더 계승(낮음)
- **원하는 답**: 규칙 확인

### Q8. [확인] 설정 페이지에 제품 프로파일·글자 크기 카드 추가
- **분류**: 레이아웃 | **근거**: settings_dialog.py:81-85, :96-104, 03 §6, 프로토타입(둘 다 부재)
- **충돌**: 프로토타입 그대로면 기능 소실
- **제안**: 경로 그룹에 제품 프로파일, 표시·동작에 글자 크기 추가(낮음)
- **원하는 답**: 규칙 확인 / 배치 지정

### Q9. [택1] 글자 크기 1.3배와 고정 높이 토큰의 상호작용
- **분류**: 토큰 | **근거**: theme.py:349-360(반쪽 동작), 02 §2 높이 토큰
- **제안 A**: 폰트만 1.3배(낮음) / **B**: 폰트+높이·간격 동시(중)
- **원하는 답**: A/B + 적용 범위

### Q10. [확인] 기본 라이트 · 라이트/다크 2개 · theme_mode 신설
- **분류**: 토큰 | **근거**: 02 §1.1, 프로토타입 설정, config.py:269-295(테마 필드 없음)
- **제안**: 기본 라이트, AUTO 미도입(낮음)
- **원하는 답**: 규칙 확인

### Q11. [확인] 미매칭 페이지 신설 · U 점프 재정의
- **분류**: 동작 | **근거**: nomatch_gallery.py:62(데드), main_window.py:86·1054-1059·1096-1112(불능)
- **제안**: 필터 제거, U 는 미매칭 포함 기준으로 점프, nav 배지 = 완전 미매칭 수(낮음)
- **원하는 답**: 규칙 확인

### Q12. [확인] wafer_map.py 삭제
- **분류**: 범위 | **근거**: 03 §1, app/ui/wafer_map.py, main_window.py:1236-1244
- **제안**: 삭제. row0 하단·die 점프는 히트맵이 계승(낮음)
- **원하는 답**: 규칙 확인

### Q13. [확인] Excel 200블록 자동 분할 - 확정 여부·임계값
- **분류**: 범위 | **근거**: 프로토타입 각주에만 존재, 04 에는 없음
- **제안**: 임계 200블록으로 구현, 시트명 「사진 대조 (2)」(낮음)
- **원하는 답**: 새 값 지정 또는 미구현 확정

### Q14. [확인] CommandBar 위젯 대신 QHBox 일반 행
- **분류**: 레이아웃 | **근거**: 프로토타입 혼합 행 vs qfluentwidgets CommandBar(Action 스트립)
- **제안**: QHBox + Fluent 컨트롤 직접 배치(낮음)
- **원하는 답**: 규칙 확인

## H. 완료 기준 (DoD)

- [ ] 게이트 4개: 대비 5.0(자동 계산 테스트) / accent 3역할 / Excel 미매칭 회색 1단 / 판독대 12칸
- [ ] 모든 서브 인터페이스 고유 `setObjectName()`
- [ ] Fluent 위젯 `setStyleSheet()` 직접 호출 0건 - `setCustomStyleSheet` 만
- [ ] `setTheme()` 은 QApplication 직후·위젯 생성 전 / Fluent 패키지 1개만
- [ ] 라이트/다크 양 테마 스크린샷 확인
- [ ] 계승 필수: `assert_output_safe`(excel_report.py:117) · 원본 read-only · 캐시 원자적 쓰기 ·
  NoScroll 입력 · 세로휠→가로 · row0 하단 · 드래그 선택 항상 가능 · `■ 중단` · 스테일 토큰 가드 ·
  크레딧/버전 2곳 · 최근 5개/즐겨찾기 10개 · 작업공간 LOT 내부 차단
- [ ] 합성 목업 이미지 코드 미사용 · 이모지 0건 · em-dash 0건 · 수치 등폭+단위
- [ ] 전체 테스트 그린 · app 커밋마다 `tools/compute_version.py --write`
- [ ] PyInstaller `--collect-all qfluentwidgets` 등 패키징 플래그 문서화
