# 05 · 원본 코드 실측값 (전수조사 결과)

BEFORE 재현의 근거입니다. **구현 시 계승 여부 판단에 쓰세요.**
`king-taek/Defect_Tracking` @ `main` (`542301e05d41`) 기준.

## theme.py

```
BG #11151c · BG_PANEL #171c26 · BG_ELEV #1f2632
NEON #5b8db8 · NEON_DIM #456b8f · NEON_SOFT #2c343f
TEXT #dde3ec · TEXT_DIM #8b95a4
MATCH #6ec59a · NOMATCH #d98a8a · BASE_GLOW #7fa8cc · WARN #d8b773
OVERLAY_BG rgba(17,21,28,0.62)
font: 'Segoe UI', 'Malgun Gothic'
FONT_SCALES = {"normal": 1.0, "large": 1.3}
```
- panel/sidebar: 1px NEON_SOFT, radius 14
- QPushButton: BG_ELEV / 1px NEON_SOFT / radius 10 / padding 8px 16px / 12px
  - hover: NEON_SOFT 배경 + NEON 테두리 / pressed: NEON_DIM 배경 + NEON 테두리
  - `#primary`: NEON_DIM + NEON + 700, hover NEON, pressed NEON_DIM
  - `#mini`: padding 3px 10px, 11px, radius 8, checked = NEON_DIM + 700
  - `#zoomGlyph`: 20px 700
- 입력(Combo/Spin/LineEdit): BG_ELEV / 1px NEON_SOFT / radius 8 / padding 6px 10px / min-height 22
- QCheckBox indicator: 16px, radius 5, checked = NEON 채움
- QListWidget item: padding 10, radius 8, min-height 30
- QProgressBar: height 16, radius 8, chunk NEON_DIM radius 7
- 콤보/스핀 화살표는 런타임 PNG 생성(`_make_arrow`) - QSS 삼각형 트릭 회피
- `QComboBox:hover::down-arrow` 규칙은 Qt에서 화살표 이중 렌더 버그 유발 → 사용 금지 (주석에 기록됨)

## wafer_map.py
`_CELL = 16`, `_GAP = 2`. matched만 `MATCH` 채움, 나머지 `BG_ELEV`. 테두리 1px `NEON_SOFT`.
현재 die = 2px `BASE_GLOW` 사각. **row 0이 화면 맨 아래**(왼쪽아래 원점). `paintEvent` 기반 - hover 상태 없음.

## heatmap_dialog.py
`_DIE_PX = 20`, `_SUBCELL_PX = 9`, `_GAP = 3`. 분할 시 die 한 변 = `SUB_COLS × 9`.
선택 표시 = `QPen(QColor("#39ff14"), 1)` **1px 외곽선만**(채움 없음). 러버밴드 = 같은 색 `Qt.DashLine`.
드래그 사각 선택은 멀티 모드와 무관하게 **항상 가능**. `_multi`는 클릭=토글/박스=합집합 여부만 좌우.
`paintEvent` 기반 - hover 없음.

## thumbnail_strip.py
`setFixedHeight(120)`, margins 8, spacing 8.
스크롤 애니메이션 220ms `OutCubic`. **세로 휠 → 가로 스크롤** 매핑(연타 누적 처리 포함).
툴팁: `"세로 휠로 좌우 스크롤 · 클릭하면 기준 사진 변경"`

## widgets.py
- `ClickableThumb`: 96×96, img 84×62(radius 6), caption 9px, dot 10px(NOMATCH, radius 5, 위치 (70,4))
  - 선택: NEON_DIM 배경 + 2px BASE_GLOW / 비선택: BG_ELEV + 1px NEON_SOFT, **hover NEON 테두리**
  - `Qt.PointingHandCursor`
- `FadeImageLabel`: **fade 제거됨**. 주석: "QScrollArea 안에서 QGraphicsOpacityEffect를 쓰면
  스크롤 시 위젯이 엉뚱한 위치에 그려지거나 사라지는 Qt 렌더 버그" → 즉시 교체
- `ImageLoader` 비동기 로드, 지난 요청 결과 무시(`_pending_id`)

## controls.py
- `SideBar`: `btn_open` = `"📁  LOT 폴더 선택"`(공백 2개), `lbl_lot` 기본 `"선택된 LOT 없음"`
- `lbl_match`(sidebar 소속) 포맷: `f"매칭 {matched}/{total} 쌍 · 기준 {bases}/{len} 장"`
- 비교 layer 버튼: `재리뷰` / `전체` / `해제` (전부 `#mini`)
- 푸터: `"⚙ 설정"`(mini, maxHeight 30) + `"결과 출력"`(primary)
- 크레딧 2줄: `config.CREDITS.replace(", ", "\n")`
- `NavBar`: `"◀  이전"` / `"다음  ▶"`, `lbl_index` `"0 / 0"` (13px 600, minWidth 90), `lbl_status`
- `NoScrollDoubleSpinBox` / `NoScrollComboBox`: 휠로 값 변경 방지 (실수 방지) - **계승할 것**

## main_window.py
- `btn_heatmap` = `"히트맵\n보기"`, `setFixedSize(96, 96)`
- `btn_add_export` = `"＋ 출력에 추가"` / 담긴 수 있으면 `f"＋ 출력에 추가 ({n})"`
- `btn_stop` = `"■ 중단"` (mini, 스캔 중에만 표시)
- 단축키 전량:
  `← → PageUp PageDown Home End` / `Ctrl+O` 폴더 / `Ctrl+E` 출력 / `F5` 재스캔 /
  `Ctrl+A` 비교 전체 / `Ctrl+D` 해제 / `U` 미매칭 점프 / `A` 담기 / `F1` 도움말
- LOT 버튼 우클릭 → 최근 폴더 `QMenu`
- 디바이스 DB 미설정 시 `QMessageBox.Warning` 안내

## nomatch_gallery.py
`_COLUMNS = 4`. 사유 우선순위 `OVER_TOLERANCE` → `COORD_FAIL` → `NO_DIE_PHOTO`.
`_REASON_META`: 허용오차 초과(WARN) / 좌표 추출 실패(NOMATCH) / 같은 die 사진 없음(TEXT_DIM).
셀 폭 128, 썸네일 `max_size=120`, `set_status("none")` 로 빨간 dot 강제, 요약 라벨 9px 폭 120.

## help_dialog.py
`_SHORTCUT_GROUPS` 4그룹(탐색/선택/출력/파일·도움말), `_FEATURES` 6항목.
**문구를 그대로 계승하세요.** 최소 크기 560×560.

## excel_report.py
`_IMG_COL_WIDTH = 30` / `_IMG_PX = 190` / `_IMG_ROW_HEIGHT = 150`
행 높이: 블록머리 18 · layer 18 · 이미지 150 · 정보 60 · 경로 24 + 간격 1행
`layer_order` 인자가 있으면 기준을 첫 열에 고정하지 않고 LOT 순서로 정렬 (**이 경로를 항상 쓰세요**)
`assert_output_safe` 게이트: 출력 경로가 원본 폴더 내부면 차단 - **반드시 유지**

## 기타 계승 필수
- 원본 이미지는 read-only. 썸네일 캐시 경유만.
- 캐시·결과는 항상 원본 밖. 작업공간이 LOT 내부면 저장 차단.
- `main.py`: PySide6 임포트 직후 스플래시 표시(무거운 MainWindow 구성 전 즉시 피드백)
