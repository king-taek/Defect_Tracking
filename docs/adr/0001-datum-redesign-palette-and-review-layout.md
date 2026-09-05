# ADR-0001: Datum 팔레트와 판독 화면 재배치(시안 DefectTracker-Redesign 채택)

## Status
Accepted

## Date
2026-09-06

## Context
2026-08 의 Fluent 재설계(`design_handoff_fluent_redesign/`)는 Windows 11 중립 회색 팔레트
(win #F3F3F3 / accent #0067B8)와 200px 라벨 nav, "제목 26px + 부제" 페이지 머리, 기준과 비교를
한 격자(2/3/4열)에 섞은 판독대를 확정했다. 그 뒤 Claude Design 프로젝트
(`Compare.dc.html` = 원본 다크 판독 화면 ↔ `DefectTracker-Redesign.dc.html`)에서 두 가지가
다시 정해졌다.

1. 색: king-taek/coding 의 도면(Datum) 팔레트로 통일한다. 따뜻한 회백색 바탕(#ECE9E2 /
   #F5F3ED / #FBFAF7)에 잉크 파랑 accent(#2C5A86), 불투명 경계선(#D9D4C7).
2. 배치: nav 는 48px 아이콘 레일, 페이지 머리는 44px 한 줄(제목 15px + 조건·행동), 판독 화면은
   `조건 행 44 / 판독대 / 하단 바 112`. 판독대는 기준 카드가 왼쪽 절반(1.15fr)을 쓰고 비교
   카드는 오른쪽 2열로 흐른다.

기존 게이트(대비 5.0, accent 3역할, Excel 회색 1단, 판독대 12칸 224px)는 그대로 유효하다.

## Decision
시안을 채택한다. 구현은 토큰 교체 + 레이아웃 재배치이며 qfluentwidgets 는 그대로 쓴다.

- `theme.FLUENT_LIGHT` / `ACCENT_LIGHT` / `STATUS_LIGHT` 를 Datum 값으로 바꾼다. 다크 토큰은
  시안이 값을 주지 않았으므로 02 §1.2 중립 회색을 유지한다.
- accent 채움 위 글자(onAccent)는 순백이 아니라 시안의 종이색 #F5F3ED 다(6.5:1).
- accent 글자용(text)은 채움과 눈으로 같은 파랑이지만 한 단계 진한 #28527A 다. 게이트 2
  (fill != text)를 지키기 위한 것이며, 시안이 두 역할에 같은 #2C5A86 을 쓴 것과 시각 차이는 없다.
- 상태 배경은 시안의 알파 틴트(.12 / .10)를 카드 면 위에 합성한 불투명 값이고, 판정을 나르는
  색이라 5.7 이상을 유지하도록 한 단계 밝혔다(pass #E7ECE5, warn #F3ECE4).
- radius 는 컨트롤 6 · 카드 9 (시안). 고정 높이 `HEADER_ROW_PX=44`, `BOTTOM_BAR_PX=112`,
  `NAV_RAIL_PX=48` 을 토큰으로 둔다.
- nav 레일은 `NavigationInterface.setMinimumExpandWidth(10**6)` 로 항상 접힌 상태를 만든다.
  ☰ 을 누르면 qfluentwidgets 의 MENU 모드로 200px 메뉴가 페이지 위에 겹쳐 뜬다.
- 창 바탕과 페이지 면은 `setCustomBackgroundColor` / `setCustomStyleSheet(stackedWidget)` 로
  칠한다(Fluent 위젯에 setStyleSheet 직접 호출 금지 규칙 유지).
- 판독대(`CompareGrid`)는 기준 칸 하나를 만들어 계속 쓰고(기준 layer 가 바뀌면 이름만 교체),
  비교 칸만 다시 만든다. SLOT·die 링크(A12)는 기준 카드 머리에 있다. 열 수 규칙
  `columns_for` 는 항상 2 다.
- 옮긴 것: 상태 문구(`set_status`)는 조건 행(`SideBar`)으로, ＋ 출력에 담기는 하단 바(`NavBar`)로,
  보기 수 `lbl_view` 는 조건 행 오른쪽으로. 빈 상태의 "최근 폴더" 버튼은 최근 LOT 목록으로.
- 미매칭·히트맵·출력 명세는 공용 `PageHeader`(44px) 한 줄을 쓰고, 도움말은 단축키 | 기능 안내
  두 열이다. 설정은 시안과 이미 같아 손대지 않았다.

## Alternatives Considered

### 시안대로 허용오차를 슬라이더 + 프리셋 팝오버로 바꾸기
- Pros: 시안 충실도. 팝오버 안에 "결과: 매칭 n/m 쌍" 이 붙어 튜닝 피드백이 가깝다.
- Cons: 현장에서는 값을 직접 타이핑한다(0.0 같은 정확 일치 포함). 슬라이더 step 10 은 그 입력을
  막는다. 기존 배선·테스트(`spn_tol.setValue`)도 스핀박스 계약이다.
- 결정: 스핀박스를 조건 행에 그대로 둔다(이탈로 기록). 매칭 요약은 같은 행 오른쪽에 있어 튜닝
  피드백은 유지된다.

### 커스텀 48px 레일 위젯을 새로 만들기
- Pros: 시안의 배지 위치·인디케이터 모션을 픽셀 단위로 맞출 수 있다.
- Cons: `FluentWindow` 라우팅·`InfoBadge`·접힘/펼침을 다시 구현해야 한다(수백 줄).
- Rejected: qfluentwidgets 의 접힘(COMPACT) 모드가 시안과 같은 48px 아이콘 레일이다.

### 다크 팔레트도 Datum 계열(따뜻한 어두운 회색)로 새로 만들기
- Pros: 두 테마의 인상이 같아진다.
- Cons: 시안에 값이 없다. 임의로 만들면 대비 게이트 검증을 새로 다 돌려야 하고 근거가 없다.
- Deferred: 시안이 다크 값을 주면 그때 ADR 을 이어 쓴다.

### 본문 서체 NanumSquare 를 Fluent 라벨까지 강제하기
- Cons: qfluentwidgets 라벨은 `setFont(getFont(...))` 로 자기 글꼴 목록을 박는다. 전부 덮으려면
  위젯마다 다시 setFont 를 걸어야 한다.
- 결정: `QApplication.setFont` 로 순수 Qt 위젯에만 적용한다(없는 환경에서는 Segoe UI /
  Malgun Gothic 으로 내려간다). 부분 적용으로 기록한다.

## Consequences
- 팔레트가 바뀐 뒤에도 `tests/test_tokens.py` 의 전 조합 대비 게이트가 그대로 통과한다
  (최저 5.07 = onAccent on accentHover).
- 옛 기본 accent(#0067B8 / #0078D4)는 프리셋으로 남아 있어 설정에서 고를 수 있다.
- `SideBar.set_layers(..., counts=)` 로 layer 별 사진 장수가 비교 Flyout 행 끝에 보인다.
- 필름스트립 카드에 '담김' 표식이 붙고, 하단 바 버튼은 현재 사진이 담겨 있으면 "✓ 담김 (n)"
  으로 바뀐다(`MainWindow._update_add_export_button`).
- 이 결정을 되돌리려면 `theme.py` 의 라이트 토큰 3개 딕셔너리와 `RADIUS` 를 되돌리고
  `MainWindow._paint_shell` 과 `setMinimumExpandWidth` 호출을 지우면 된다. 레이아웃(판독대·머리
  행)은 되돌릴 이유가 색과 독립적이므로 별도 ADR 로 다룬다.
