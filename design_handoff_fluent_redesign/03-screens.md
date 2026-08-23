# 03 · 화면별 구현 명세

각 화면: 목적 / 레이아웃 / 컴포넌트 / 상태 / 모션 / 원본 대비 변경.
색·간격·duration은 `02-design-rules.md` 토큰 이름으로 참조합니다.

---

## 1. 판독 (main_window.py, controls.py, compare_grid.py, thumbnail_strip.py, wafer_map.py)

### 목적
기준 layer 사진 1장과 비교 layer 사진들을 나란히 놓고 같은 defect인지 판독한다. 앱의 주 화면.

### 레이아웃 (창 1464×940 기준)
```
[타이틀바 48]
[nav 200 또는 48] [페이지 면 (layer, 좌상단 radius 8)]
                    ├ 헤더 22/28 패딩: 제목 26 + 부제 + 우측 통계 2개(매칭/기준)
                    ├ CommandBar 40: LOT폴더 | 기준layer ComboBox | 오차 SpinBox | 비교layer Flyout | (spacer) | 미매칭점프 | ＋출력에담기(primary)
                    ├ 판독대 flex:1, overflow-y:auto
                    │   grid: repeat(cols,1fr) / auto-rows minmax(224px,1fr) / gap 12
                    │   cols = 칸 4개 이하 2열, 9개 이하 3열, 그 이상 4열
                    ├ 탐색 바 44: ‹ › index/총계 | SLOT·die | 힌트
                    └ 필름스트립 96: 104px 카드 가로 스크롤
```

### 판독 카드 (한 칸)
- 카드: `card` 배경, `cardBorder` 1px, radius 7, hover `cardBorderH`
- 헤더 34: layer명 12.5/600 + 배지(기준/동률 후보) + 우측 Δ 수치(등폭, pass색)
- 사진 영역: `inset 34px 8px 8px`, 배경 **#000**, radius 4, 이미지 contain
- 기준 칸에만: 좌하단 µm 스케일바(48px 선 + 9.5px 라벨), 우하단 `＋n 근접` 버튼
- 미매칭 칸: 배경 #000 유지, 중앙에 "매치 없음"(12.5/600, 흰색 62%) + 사유(12px, 흰색 66%)
  > 앱 화면에서는 사유를 남깁니다. **Excel 리포트만** 회색 1단 규칙(게이트 3).

### 상태
`baseLayer`, `compareLayers{}`(canonical 12 × 깊이), `tolerance`, `clusterRadius`, `cur`, `tray[]`,
`navExpanded`, `theme`

### 모션
- 사진 교체: 220ms opacity + scale 1.012→1 (`imgIn`)
- nav pill: 300ms OutQuart (top/bottom/height)
- 필름스트립 선택 이동: 260ms OutCubic 스크롤 + 카드 `translateY(-2px)` 180ms
- CommandBar 값 변경 → StateToolTip + 하단 3px 진행바 (재매칭 시뮬레이션)

### 원본 대비 변경
| 원본 | 재설계 | 이유 |
|---|---|---|
| 좌측 240px 사이드바에 폼 9줄 | nav 200/48 + 상단 CommandBar | 판독 중 조건은 시야에서 비켜나야 함 |
| 원시 layer 체크리스트 24행 | canonical 12행 × 깊이 칩(원본/재/재재) | 후보 24개가 뿔뿔이 흩어지는 문제 |
| 매칭 없는 layer 셀을 숨김(repack) | 칸 고정 + 빈 판 + 사유 | 왜 없는지가 화면에서 사라짐 |
| 배지가 사진 위에 겹침 | 카드 헤더로 분리 | 사진 가림 |
| 사진 바탕 #1f2632 | #000 | 명암 판독에 바탕색 혼입 |
| 기준 전환 즉시 교체(fade 제거됨) | 220ms 크로스페이드 | Qt 렌더 버그 회피는 §3 참조 |
| 웨이퍼맵 상시 노출(16px 셀) | nav 접힘 가능 + 별도 히트맵 | 정보 밀도 |

---

## 2. 미매칭 (nomatch_gallery.py)

### 목적
어떤 비교 layer와도 매칭되지 않아 후보에서 제외된 기준 사진을 사유별로 훑고, 클릭해 판독으로 이동.

### 레이아웃
헤더(제목 26 + 총계/표시 개수) → 사유 필터 SegmentedWidget 4칸(전체/허용오차 초과/좌표 추출 실패/같은 die 사진 없음)
→ 4열 그리드 gap 12, overflow-y:auto

### 셀
카드 radius 7 패딩 10 / 사진 112px(#000) + 우상단 danger dot 9px / 캡션 등폭 10.5 `txt2`
/ 대표 사유 배지(사유색 배경+글자) / **layer별 사유 행 분리**: `LYB4  허용오차 초과 · 최근접 118.4 µm` (12px `txt2`, layer 키 12px/600 `txt2`)

> 이 텍스트가 이 화면의 주 내용입니다. 10px/45%로 낮추면 게이트 위반입니다.

### 원본 대비
`_REASON_META` 색/우선순위(`OVER_TOLERANCE` → `COORD_FAIL` → `NO_DIE_PHOTO`)와 4열 그리드는 계승.
ComboBox 필터 → SegmentedWidget, 9px 한 줄 요약 → 12px layer별 행.

---

## 3. 히트맵 (heatmap_dialog.py, app/heatmap.py)

### 목적
defect 밀도 지도에서 위치를 골라 그 자리의 layer 교차 판독.

### 레이아웃
헤더 → 컨트롤 행(스케일 SegmentedWidget 3칸 + 조사 layer 칩 4개 + ＋20 접힘 + 총계)
→ 좌 430 지도 카드 / 우 판독 카드

### 지도
- 기본(42 die): 45×45 셀 gap 3, die 안 5×5 하위셀, 단일 잉크 램프(accentFill 알파 0.12→1.0)
- 선택: `2px accentFill` 테두리. **원본의 #39ff14 네온 그린 제거**
- 범례: 0 → 최대 9 그라디언트 바
- **LOD (수천 die)**: 6px 미만이면 테두리·간격·하위분할을 순서대로 해제 → 래스터 이미지 1장 렌더
  (`QImage` 픽셀 채움 후 `QPixmap` 1회 draw). 낱개 클릭 대신 드래그 영역 합산이 기본 상호작용.
  프로토타입은 1,024/4,096 die를 canvas 래스터로 시연합니다.

### 원본 대비
| 원본 | 재설계 |
|---|---|
| 파랑→코랄 2색 램프 + 네온그린 선택 + 초록/빨강 태그 = 색상축 4개 | 단일 잉크 램프 + 포커스 링 + 예외만 태그 |
| die 20px 고정 / 하위셀 9px | 패널 폭에 맞춰 클램프 + LOD |
| wafer 드롭다운 | 슬롯 레일 또는 ComboBox + 보유 슬롯 강조 |
| 매치 그룹마다 "교차매치" 초록 태그 | 무표기, "매치 없음"만 태그 |

**계승할 것**: 드래그 사각 선택(항상 가능), 여러 다이 선택 모드(클릭 누적 토글), row 0이 화면 맨 아래.

---

## 4. 출력 명세 (export_dialog.py)

### 목적
Excel로 내보낼 사진 목록을 확인하고 개별 제거.

### 레이아웃
헤더(개별 n + 묶음 n = 총 n장) → [매치 전체 담기][전체 비우기] ... [Excel 출력(primary)]
→ 표 카드: 머리 38(NO/사진/위치/매칭/빈칸) + 행 60

### 행
NO 등폭 `txt3` / 썸네일 72×44(#000) / 위치 등폭 `txt1` / 매칭 n/11 `txt2` / ✕ TransparentToolButton(hover danger 틴트)

### 모션
- 행 제거: height 60→0 + opacity, 240ms 퇴장 (제자리 접힘)
- 묶음 추가: height 0→60, 250ms 진입
- 비우기: MessageBox(마스크 200ms + 시트 250ms scale)

### 원본 대비
3열 카드 격자 → 명세 행. 🗂 이모지 묶음 카드 → `×n` 명세 행. [취소][확인][Excel 출력] 3버튼 동급 → 주요 액션 1개.

---

## 5. 도움말 (help_dialog.py)

원본 `_SHORTCUT_GROUPS` 4그룹 · `_FEATURES` 6항목을 **문구 그대로** 유지.
- 단축키: 카드 안 그룹 헤더(accentText 11.5/600 + subtle 배경) + 행 11 패딩 18, 키캡 214px 등폭 11.5/600
- 기능: 2열 카드 그리드, 제목 13/600 + 본문 12 `txt2`

## 6. 설정 (settings_dialog.py)

- 그룹 "경로": 작업공간 / 출력 폴더 / 디바이스 DB → `PushSettingCard`
- 그룹 "표시·동작": 테마 SegmentedWidget · 자동 업데이트 `SwitchSettingCard` · 개발자 모드 `ExpandGroupSettingCard`(로그 경로 250ms 펼침, 셰브론 180° 회전)
- 하단: 도움말 HyperlinkButton + 버전·크레딧 `txt3`
- 원본 계승: 작업공간이 LOT 내부면 차단(안내 문구 유지), 글자 크기 보통/크게(1.0/1.3)

## 7. 폴더 선택 (folder_picker.py)

### 핵심 문제: 상·하위 폴더가 수백 개
3가지 점프로 트리 걷기를 대체:
1. `BreadcrumbBar` 세그먼트마다 ▾ 형제 폴더 점프
2. 즐겨찾기(**Device 폴더만**, DEV 배지) + 최근 + 스캔 루트 바로가기
3. 현 위치 하위를 자동 판별해 **LOT 후보만 우선 정렬**(기타 폴더는 아래로 강등)
- 검색: `SearchLineEdit` + "하위 1단계 포함" 토글
- 하단 **고정 판정 행**: 판정 칩(LOT/상위/?) + 사유 + `layer n · wafer n` 등폭
  > 원본은 4색 배너가 통째로 바뀜 → 색은 칩 하나에만
- 즐겨찾기 추가: 폴더 우클릭 → RoundMenu "즐겨찾기에 추가". Device 계층만 대상(LOT·Wafer 제외)
- `TeachingTip`으로 추가 방법 안내

계승: 한 단계만 `os.scandir`(성능), layer/wafer 폴더 선택 시 LOT로 자동 보정.

## 8. 원본 뷰어 (image_viewer.py)

- 헤더 52: 제목 + 메타 1줄 등폭(SLOT·die·Camtek·결함명) + 정보 복사 + ✕(hover danger)
  > 원본 4줄(경로 포함) → 1줄. 전체 경로는 정보 복사에만.
- 무대: 순검정 전면, 좌하단 µm 스케일바
- HUD(하단 중앙, 반투명 + blur): － 배율(등폭 6자) ＋ | 1:1 맞춤. 활성 항목 채움 표시
- **잡고 끌기 패닝**: 줌 상태에서 cursor grab→grabbing, 드래그 중 transition 없음, 놓으면 확정. 맞춤 = 원점 복귀
- 줌: 250ms OutQuint. 휠 줌은 커서 고정점 유지(원본 계승)

## 9. 로딩 · 알림 (splash.py, busy_overlay.py, notifications.py)

| 요소 | 재설계 |
|---|---|
| SplashScreen | 64px 아이콘(accentFill) + 제목 19/600 + 버전 + 등속 스피너 + 단계 문구. 퇴장 300ms |
| 스캔 진행 | 전면 상태: 36px 스피너 + 제목 + 6px 진행바 + 퍼센트 등폭 + `■ 중단` (원본 `btn_stop` 계승) |
| 매칭 중 | `StateToolTip` 상단 중앙: 16px 등속 스피너 + 제목 + 퍼센트. 하단 3px 진행바 |
| 알림 | `InfoBar` 우상단 스택 346px, 좌측 4px 톤 바 + 아이콘 + 제목/본문. 진입 200ms + translateX 14px, 3.4s 자동소멸 |

원본 계승: 비차단 인라인 배너 원칙(모달 금지). 원본의 면 전체 4색 → 좌측 바 + 연한 배경.

## 10. 빈 상태 · 오버레이

- **빈 상태(LOT 미선택)**: 56px 아이콘 틴트 + 제목 19/600 + 설명 + [LOT 폴더 선택(primary)][최근 폴더 ▾] + 단축키 힌트. 진입 300ms fadeSlideU
- **근접 클러스터**: 다이얼로그 660px. 대표 + 묶임 n장, 카드 hover accent 테두리, [전부 명세에 담기][닫기]
- **업데이트**: 440px. 아이콘 틴트 + v표기 + 변경점 3줄 + [지금 업데이트(primary)][나중에]
- **최근 폴더 RoundMenu**: LOT 버튼 우클릭. 항목 34px + 구분선 + "폴더 찾아보기…"
