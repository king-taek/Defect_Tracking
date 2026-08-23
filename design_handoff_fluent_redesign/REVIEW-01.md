# REVIEW-01 · PLAN-01 검토서

작성: Claude Design · 대상: `PLAN-01.md` (Defect Tracker Fluent 재설계 STEP 1)
근거: `02-design-rules.md` 게이트 4개 · `03-screens.md` · `04-excel-report.md` · `05-verified-source-facts.md`

---

## 판정

**조건부 승인.**

플랜 품질은 착수 가능 수준입니다. 특히 데드 코드 3건(`nomatch_gallery` 미호출, U 점프 구조적 불능,
`FEAT#3`이 설명하는 매치만/전체 토글 부재) 적발은 디자인 문서가 놓친 부분이며 전부 플랜 판단을 채택합니다.

조건:
1. **Q1(라이선스)은 디자인이 결정할 사안이 아닙니다.** 미해결 상태로 의존성 고정 커밋을 하지 마세요.
   0단계 중 **토큰 모듈(theme.py) 재작성과 대비 게이트 테스트만** 먼저 진행하세요 -
   이 둘은 프레임워크 무관이라 Q1 결론이 어느 쪽이든 버려지지 않습니다.
2. 아래 **플랜 지적사항 5건**을 PLAN-FINAL에 반영.
3. Q4·Q5·Q13은 플랜 제안과 **다른 결론**입니다. A2절 확인하세요.

---

## 플랜 지적사항

| # | 위치 | 문제 | 조치 |
|---|---|---|---|
| P1 | C절 `compare_grid.py` "µm 스케일바(신설)" | **가짜 정밀 금지.** 스케일바는 픽셀↔µm 실비율을 알 때만 정당합니다. 현 코드에 그 비율이 없고(Camtek/KLA 좌표는 die 내 위치일 뿐 촬영 배율이 아님) 프로토타입의 48px/100µm 는 장식입니다 | 실비율 획득 경로(디바이스 DB·INI에 배율 필드)가 확인될 때까지 **스케일바 미구현**. 대신 기준 칸 좌하단에 `die (c, r)` 좌표를 남기세요. 비율이 확인되면 그때 추가 |
| P2 | E절 "폴더당 scandir 깊이≤3" | 과도한 I/O. `scanner.classify_selection`은 **한 단계만** 봅니다(05 계승 항목). 깊이 3이면 수백 폴더 × 3단계 |
| | | | 깊이 1 고정. LOT 후보 판별에 충분합니다 |
| P3 | F절 신규 테스트 ④ "`setStyleSheet` 0건 정적 검사" | `theme.py` 자체와 non-Fluent 위젯(순수 `QLabel`/`QWidget`)은 정당한 예외입니다. 0건으로 잡으면 우회 주석만 늘어납니다 | 검사 대상을 **qfluentwidgets 에서 import 한 심볼을 상속·인스턴스화한 객체**로 한정. `theme.py`는 allowlist |
| P4 | B절 단계 1 | `notifications.py` 통합(호출부 20곳 이상)과 셸 구축을 한 커밋에 두면 회귀 원인 분리가 안 됩니다 | 단계 1을 1a(셸+라우팅+빈 상태) / 1b(알림·진행 표시 일원화)로 분리 |
| P5 | C절 `main_window.py` "판독 페이지는 신설 `app/ui/pages/`로 분리" | 좋은 판단입니다. 다만 페이지 6개가 모두 `pages/`로 가야 일관됩니다. 판독만 분리하면 나머지가 `app/ui/` 루트에 남아 두 체계가 공존 | 6페이지 전부 `app/ui/pages/`. 시트·다이얼로그는 `app/ui/sheets/` |

---

## 질의 응답

### A1 → Q1 [BLOCKER] qfluentwidgets 라이선스

- **결정**: **디자인이 결정할 사안이 아님.** 사업 주체가 확인해야 합니다. 다만 디자인 관점의 판정은 제공합니다.
- **이유**: `02-design-rules.md`의 게이트 4개·토큰·모션·카피 규칙은 **전부 프레임워크 무관**입니다.
  qfluentwidgets 는 §5 위젯 매핑 한 절에만 의존합니다. 즉 제안 B(커스텀 QSS)로 가도 재설계의
  **디자인 내용은 100% 유지**되고, 잃는 것은 위젯 구현 편의뿐입니다.
- **정확한 값**: B 후퇴 시 자체 구현이 필요한 최소 목록(그 외는 순수 Qt로 충분):
  ```
  1. NavigationInterface 대체 - QListWidget + 선택 pill QWidget (300ms QPropertyAnimation on geometry)
  2. InfoBar 대체        - QFrame 스택 + QGraphicsOpacityEffect (스크롤 영역 밖이므로 안전)
  3. Flyout 대체         - QWidget(Qt.Popup) + 187ms 진입 애니메이션
  4. MessageBox 대체     - QDialog + 반투명 마스크 QWidget(부모 위 200ms)
  5. SwitchButton 대체   - QAbstractButton + 손잡이 160ms 이동
  6. SettingCard 계열    - QFrame 조합 (난이도 낮음)
  나머지(ComboBox/SpinBox/ProgressBar/ScrollArea/TeachingTip/Breadcrumb)는 순수 Qt + QSS 로 충분
  ```
- **타협 가능 여부**: 해당 없음(외부 결정). **단 이건 게이트**: Q1 미해결 상태에서
  `requirements.txt`/`bootstrap.py`에 의존성을 고정하는 커밋을 만들지 마세요.

### A2 → Q2 [BLOCKER] 기존 설치본 크래시 방지

- **결정**: **A 채택**(`_REQUIRED` 3중 등록 + 안내). B(자동 pip)는 도입하지 않습니다.
- **이유**: 업데이트 직후 자동 pip 는 네트워크·권한·프록시에서 실패하고, 실패 지점이 앱 밖이라
  사용자가 할 수 있는 일이 없습니다. 우리 카피 규칙은 "사유는 조치 가능한 문장으로"입니다 -
  실패를 숨기는 대신 **한 문장으로 조치를 알려주는 쪽**이 규칙에 맞습니다.
- **정확한 값** (원시 트레이스백 노출은 게이트 위반):
  ```python
  # bootstrap 미실행 상태에서 UI import 실패 시
  TITLE = "추가 구성이 필요합니다"
  BODY  = ("이 버전은 새 화면 구성요소를 사용합니다.\n"
           "bootstrap.py 를 한 번 실행하면 설치가 끝납니다.")
  BTN_OK = "bootstrap 실행 방법"
  BTN_NO = "닫기"
  ```
  qfluentwidgets 자체를 못 불러오는 상황이므로 이 안내는 **순수 Qt `QMessageBox`**로 띄우세요.
- **타협 가능 여부**: A/B 선택은 권장, **트레이스백 노출 금지는 게이트**.

### A3 → Q3 [BLOCKER] offscreen FluentWindow 후퇴 허용

- **결정**: **A 승인**(0단계 스파이크 → 실패 시 `QMainWindow` + `NavigationInterface`).
  **B는 거부**합니다.
- **이유**: 테스트와 프로덕션이 다른 창 클래스면, 프레임리스 경로의 회귀가 테스트를 통과합니다.
  114개 테스트가 지켜주지 못하는 코드 경로를 만드는 게 프레임리스 타이틀바보다 비쌉니다.
  48px 커스텀 타이틀바는 **권장**이지 게이트가 아닙니다.
- **정확한 값** (후퇴 시 레이아웃 보정):
  ```
  네이티브 타이틀바 사용 → 창 상단 48px 밴드가 사라짐. 다음을 조정하세요:
  · nav 상단 여백  48px → 8px
  · 창 제목        "Defect Tracker - 204. DEVAINT.226 (PKG)"  (setWindowTitle, 기존 포맷 계승)
  · 페이지 헤더    부제에 LOT 명 추가: "기준 LYA3 · 비교 03 layer · 허용 100 µm · 204. DEVAINT.226"
  · 창 배경        #F3F3F3 (라이트) / #202020 (다크) 유지
  · radius 8 모서리는 포기 (OS가 그림)
  ```
- **타협 가능 여부**: 권장(타이틀바) / 게이트(창 클래스 이원화 금지).

### A4 → Q4 [택1] Excel 기준 없음 교차 그룹

- **결정**: **B 채택**(1차는 혼합 모드에서 ★ 미표기 + 동등 열만). A(신규 데이터 경로)는 후속.
  플랜 제안(A)과 **다릅니다.**
- **이유**: 사용자가 Excel 범위를 "사진 대조 한 장"으로 축소한 흐름과, 히트맵이 기준 포함 그룹만
  담는 현 구조(주석에 명시)를 함께 보면, 교차 그룹 export 경로 신설은 **이번 재설계의 범위가 아닙니다.**
  `04-excel-report.md`의 교차 블록 명세는 "그 경로가 생기면 이렇게 보인다"는 목표 상태입니다.
- **정확한 값** (1차 구현 범위):
  ```
  · layer_order 항상 전달 → 기준 있음/없음 모두 LOT 순서 (게이트)
  · base_layers_present 가 2개 이상이거나 기준을 특정할 수 없으면:
      - ★ 기준 배지 미표기, 12칸 전부 일반 layer 스타일(#E8EEF4)
      - 블록 머리 배지: "교차매치"
      - 머리 메타: "204. DEVAINT.226 (PKG) · 기준 없음 · 조사 layer 12 · 허용 100 µm"
      - 매칭 카운트 분모 = 그 블록의 실제 열 수 (기준 열이 없으면 12)
  · "개별" 배지와 die 위치 단위 블록은 후속 (교차 그룹 export 경로가 생긴 뒤)
  ```
- **타협 가능 여부**: 권장(범위). ★ 미표기·LOT 순서는 게이트.

### A5 → Q5 [택1] 스플래시

- **결정**: **B 채택**(독립 스플래시를 Fluent 토큰으로 리스킨). 플랜 제안(A)과 **다릅니다.**
- **이유**: `05-verified-source-facts.md`의 "PySide6 임포트 직후 즉시 피드백"은 계승 필수 항목입니다.
  `SplashScreen`은 창이 먼저 있어야 하므로 셸 생성 시간만큼 첫 프레임이 늦습니다. 프로토타입의
  창 내 스플래시는 **문서에서 시연하기 위한 배치**이지 순서를 규정한 게 아닙니다.
  체감 시작 속도가 위젯 종류보다 우선입니다.
- **정확한 값** (독립 스플래시 스펙):
  ```
  창              400×220, frameless, 화면 중앙
  배경            #F3F3F3 (라이트) / #202020 (다크)   radius 8
  아이콘          64×64, radius 14, 채움 accentFill(#0078D4 / #4CC2FF), 중앙 22px 흰 원
  제목            "Defect Tracker"  19px / 600 / letter-spacing -0.2px / txt1
  버전            "v1.33.84"        11.5px / txt3        (아이콘 아래 20px 간격)
  스피너          26×26, 선 2.5px, track ringTrack, 진행 accentFill, 900ms linear 무한(등속 - 게이트)
  단계 문구       11.5px / txt2, 고정 높이 16px (문구 교체 시 흔들리지 않게)
                  "프로그램 준비 중" → "디바이스 DB 로드" → "화면 구성" → "완료"
  퇴장            300ms opacity 1→0, cubic-bezier(.7,0,1,.5)
  ```
  A로 가려면 조건: **셸 경량 생성이 실측 150ms 미만**임을 0단계에서 증명. 그 경우 A 허용.
- **타협 가능 여부**: 권장(A/B) / 게이트(등속 스피너, 단계 문구 고정 높이).

### A6 → Q6 [택1] 도움말 문구

- **결정**: **A 채택**(프로토타입 문구 + `FEAT#3` 재작성).
- **이유**: `03-screens.md`의 "문구 그대로 계승"은 **임의로 줄이거나 요약하지 말라**는 뜻이었습니다.
  화면 이름이 "출력 트레이 → 출력 명세"로 바뀌었으면 도움말이 따라야 하고, 코드에서 제거된 기능을
  설명하는 문장은 유지할 가치가 없습니다. 적발 감사합니다.
- **정확한 값** (`FEAT#3` 교체 문구 - 현 동작 기준):
  ```
  ("layer 교차 판독",
   "히트맵에서 위치를 고르면 그 자리의 defect 을 layer 별로 나란히 놓고 봅니다. "
   "선택한 layer 들을 서로 교차 매칭하므로 기준 없이도 비교할 수 있고, "
   "어느 layer 와도 매칭되지 않은 defect 은 따로 표시됩니다."),
  ```
  나머지 5항목과 단축키 4그룹은 프로토타입 문구를 그대로. "출력 트레이" → "출력 명세" 전수 교체.
- **타협 가능 여부**: 권장.

### A7 → Q7 [확인] 히트맵 스케일 분절 = 데모 전용

- **결정**: **승인.** 플랜 제안 그대로.
- **이유**: 분절 컨트롤은 문서에서 LOD 3단계를 보여주기 위한 장치입니다. 실 데이터의 die 수는 LOT이
  정하므로 사용자가 고를 값이 아닙니다. 데이터와 무관한 컨트롤을 남기면 "정보 밀도" 원칙 위반입니다.
- **정확한 값**:
  ```
  자동 LOD 임계: die 한 변 px 계산 후
    ≥ 20px  →  현행 렌더 + 하위 5×5 분할(app/heatmap.py die<50 자동 분할 규칙 계승)
    6~19px  →  하위분할 해제 → 간격 해제 → 테두리 해제 (이 순서)
    < 6px   →  QImage 픽셀 채움 1장 + QPixmap 1-draw (래스터 모드), 낱개 클릭 대신 드래그 영역 합산
  셀 크기는 패널 폭에 맞춰 클램프 - 지도는 항상 한 화면에 (게이트)
  사진 크기 슬라이더(현 534-540)는 계승
  ```
- **타협 가능 여부**: 게이트(지도가 한 화면) / 권장(임계값 6px).

### A8 → Q8 [확인] 제품 프로파일 · 글자 크기 카드

- **결정**: **승인 + 배치 지정.** 기능 소실 방지는 명세보다 우선입니다.
- **이유**: 제품 프로파일은 die 배치·좌표 변환에 관여하므로 디바이스 DB와 같은 성격(=지오메트리 입력)입니다.
  글자 크기는 표시 설정입니다.
- **정확한 값** (설정 페이지 카드 순서):
  ```
  그룹 "경로 · 데이터"
    1. PushSettingCard      작업공간 폴더
    2. PushSettingCard      출력 폴더
    3. PushSettingCard      디바이스 DB
    4. ComboBoxSettingCard  제품 프로파일     ← 신규 배치 (3 바로 아래)
       제목 "제품 프로파일" / 부제 "die 배치와 좌표 변환에 사용합니다"
       항목 "자동 인식" + DB 디바이스 목록
  그룹 "표시 · 동작"
    1. SegmentedWidget      테마            라이트 | 다크
    2. SegmentedWidget      글자 크기        보통 | 크게      ← 신규 배치
       부제 "크게는 본문 기준 1.3배입니다"
    3. SwitchSettingCard    자동 업데이트
    4. ExpandGroupSettingCard 개발자 모드 → 로그 저장 경로
  ```
- **타협 가능 여부**: 권장(순서) / 게이트(두 기능 유지).

### A9 → Q9 [택1] 글자 크기 1.3× 와 고정 높이 토큰

- **결정**: **A 변형 채택.** 폰트는 1.3×, **높이 토큰은 `min-height`로 재해석**합니다.
- **이유**: `02-design-rules.md` §2의 높이 값은 본문 14px 기준 산출값입니다. 18.2px에서 32px 컨트롤은
  상하 여백이 7px→4px로 줄어 클리핑 직전이 됩니다. 높이를 고정값이 아니라 **하한**으로 쓰면
  토큰과 어긋나지 않으면서 넘침이 사라집니다. 현행 regex 스케일링이 인라인 스타일을 못 잡아
  반쪽으로 동작하던 문제도 같이 해소됩니다.
- **정확한 값**:
  ```python
  FONT_SCALES = {"normal": 1.0, "large": 1.3}   # 폰트에만 적용 (본문·캡션·라벨·등폭 수치 전부)

  # 높이는 하한으로. large 에서 아래 값으로 올립니다 (곱셈이 아니라 표로 고정)
  H = {
      "control":  {"normal": 32, "large": 40},
      "primary":  {"normal": 36, "large": 44},
      "navItem":  {"normal": 40, "large": 48},
      "tableRow": {"normal": 21, "large": 27},
      "specRow":  {"normal": 60, "large": 72},
      "titleBar": {"normal": 48, "large": 48},   # 변경 없음
      "icon":     {"normal": 16, "large": 20},
  }
  # radius / gap / 패딩은 두 배율 모두 동일 (형태 스케일은 스케일하지 않음 - 게이트)
  ```
- **타협 가능 여부**: 권장(높이 표 값) / 게이트(radius·gap 불변, 등폭 수치도 함께 확대).

### A10 → Q10 [확인] 기본 라이트 · AUTO 미도입

- **결정**: **승인 + 첫 실행 안내 1회 추가.**
- **이유**: 사진 바탕은 두 테마 모두 순검정(게이트)이라 판독 정확도는 테마와 무관합니다. Excel 리포트와
  문서가 라이트이므로 기본을 라이트로 두면 화면·출력물의 인상이 일치합니다.
  다만 다크에 익숙한 기존 사용자에게는 전환 경로를 한 번 알려야 합니다.
- **정확한 값**:
  ```python
  theme_mode: str = "light"      # AppSettings 신규 필드, 기본값

  # theme_mode 가 저장 파일에 없던 사용자(=업데이트 직후 첫 실행)에게 1회만
  InfoBar.info(
      title="새 화면으로 바뀌었습니다",
      content="어두운 화면을 쓰시려면 설정 · 표시 · 동작에서 다크로 바꿀 수 있습니다.",
      position=InfoBarPosition.TOP_RIGHT, duration=6000, parent=self)
  # 표시 후 settings.theme_mode 를 명시적으로 저장해 재노출 방지
  ```
- **타협 가능 여부**: 권장.

### A11 → Q11 [확인] 미매칭 페이지 신설 · U 재정의

- **결정**: **승인.** 플랜 제안 그대로.
- **이유**: 판독대가 빈 칸 + 사유를 항상 보이므로 "미매칭만 보기" 필터는 중복입니다. U는 화면 전환이
  아니라 **탐색 점프**로 남기는 게 단축키 성격에 맞습니다.
- **정확한 값**:
  ```
  U          : 현재 index 이후에서 '미매칭을 하나 이상 포함한' 기준으로 점프 (순환)
  nav 배지    : 완전 미매칭(모든 비교 layer와 매칭 0) 기준 수. 0이면 배지 숨김
  U 실패 시   : InfoBar.success(title="미매칭 없음",
                              content="표시 후보 전부가 하나 이상 매치되었습니다.")
  미매칭 페이지: 완전 미매칭 기준만 나열 (부분 미매칭은 판독대에서 이미 보임)
  ```
- **타협 가능 여부**: 권장.

### A12 → Q12 [확인] wafer_map.py 삭제

- **결정**: **승인 + 조건 1개.**
- **이유**: 삭제는 정보 밀도 결정과 일치합니다. 다만 die 점프 어포던스가 함께 사라지면 안 됩니다.
- **정확한 값** (조건):
  ```
  판독 화면 탐색 바의 "SLOT 03 · die (4, 3)" 를 클릭 가능하게 만들고,
  클릭 시 히트맵 페이지로 이동 + 해당 die 를 선택 상태로 엽니다.
  hover 시 커서 pointer + 색 txt2 → accentText (120ms linear)
  툴팁: "히트맵에서 이 die 보기"
  ```
- **타협 가능 여부**: 권장(구현 방식) / 게이트(die 점프 경로 유지).

### A13 → Q13 [확인] Excel 200블록 분할

- **결정**: **분할 미구현.** 대신 출력 전 경고. 플랜 제안과 **다릅니다.**
- **이유**: 200은 프로토타입 각주였고 실측 근거가 없습니다. 사용자가 "사진 대조 한 장"으로 범위를
  줄인 직후에 시트를 늘리는 규칙을 넣는 것은 그 결정과 어긋납니다. 실사용에서 담는 건은 수십 건입니다.
- **정확한 값**:
  ```python
  EXPORT_WARN_BLOCKS = 200
  # 담은 건이 이 값을 넘으면 출력 전 확인
  TITLE = "사진이 많습니다"
  BODY  = ("{n}건을 출력하면 파일이 커지고 열기가 느려집니다.\n"
           "필요한 건만 남기고 출력하는 것을 권합니다.")
  BTN_OK = "그대로 출력"
  BTN_NO = "명세로 돌아가기"
  ```
  `04-excel-report.md`의 "200블록 초과 시 자동 분할" 문장과 프로토타입 각주는 **폐기**합니다.
- **타협 가능 여부**: 권장.

### A14 → Q14 [확인] CommandBar 대신 QHBox

- **결정**: **승인.** 애초에 물을 필요 없는 범주였습니다(`01-PROTOCOL.md` STEP 4 "묻지 않고 진행" -
  Qt 레이아웃 관용구 선택). 시각 결과가 명세와 같으면 위젯 종류는 구현 재량입니다.
- **정확한 값** (시각 결과 고정값):
  ```
  행 높이 40 · 항목 간 gap 6 · 구분선 1px divider, 높이 20, 좌우 마진 4
  좌측 그룹: LOT 폴더 | (구분선) | 기준 layer ComboBox | 오차 SpinBox | 비교 layer 버튼
  우측 그룹: 미매칭 점프 | ＋ 출력에 담기(accentFill 채움, onAccent 글자)
  컨트롤 높이 32(large 40) · radius 5 · 하단 테두리 1px ctrlBdBottom (Fluent 규격 - 게이트)
  ```
- **타협 가능 여부**: 권장.

---

## 추가 지시

### AD1. 미매칭 표기의 적용 범위 (혼동 방지)

```
Excel 리포트  : 회색 1단 + "미매칭" 한 단어. 사유·거리 없음.        (게이트 3)
앱 판독대     : 사유 표기 유지. "매치 없음" + 사유 한 줄.
              예) "허용오차 초과 · 최근접 141.8 µm"
앱 미매칭 페이지: layer별 사유 행 12px txt2 유지.
```
게이트 3은 **Excel 전용**입니다. 앱에서 사유를 지우면 판독 근거가 사라집니다.

### AD2. accent 3역할은 `setThemeColor` 하나에서 파생

```python
from qfluentwidgets import setThemeColor, isDarkTheme
from PySide6.QtGui import QColor

ACCENT_BASE = "#0078D4"

def accent_roles(base: str = ACCENT_BASE) -> dict[str, str]:
    c = QColor(base)
    if isDarkTheme():
        light3 = c.lighter(160).name()          # #4CC2FF 계열
        return {"fill": light3, "hover": light3,
                "pressed": c.lighter(130).name(),
                "onAccent": "#16140F",          # near-black - 게이트
                "text": light3,
                "tint": f"rgba({c.red()},{c.green()},{c.blue()},0.13)"}
    return {"fill": base, "hover": c.darker(112).name(),
            "pressed": c.darker(130).name(),    # #005A9E 계열
            "onAccent": "#FFFFFF",
            "text": c.darker(130).name(),       # accentDark2 - 글자 전용
            "tint": f"rgba({c.red()},{c.green()},{c.blue()},0.09)"}
```
`fill` 위의 글자는 **반드시** `onAccent`. 글자·글리프로 쓰는 accent 는 **반드시** `text`.

### AD3. 대비 게이트 자동 테스트 (F절 신규 ① 구현안)

```python
def _lin(v: float) -> float:
    v /= 255
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

def contrast(fg: str, bg: str) -> float:
    def lum(h):
        c = QColor(h)
        return 0.2126*_lin(c.red()) + 0.7152*_lin(c.green()) + 0.0722*_lin(c.blue())
    a, b = sorted((lum(fg), lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)

GATE = 5.0
PAIRS = [  # (전경, 배경, 라벨)
    ("txt1", "card"), ("txt2", "card"), ("txt3", "card"),
    ("txt1", "layer"), ("txt2", "layer"), ("txt3", "layer"),
    ("onAccent", "accentFill"), ("accentText", "card"), ("accentText", "layer"),
    ("pass", "passBg"), ("warn", "warnBg"), ("danger", "dangerBg"),
]
# txtDeco 는 장식 전용이므로 게이트 제외 - 단 '구분자 / · 만' 사용 정적 검사와 쌍으로
```
알파값 토큰(`rgba(0,0,0,.62)`)은 배경과 합성한 뒤 계산하세요.

### AD4. 크로스페이드 구현 (`QGraphicsOpacityEffect` 금지 회피)

```python
# widgets.py - 스크롤 영역 안이므로 이펙트 사용 금지 (05 기록된 Qt 렌더 버그)
class CrossfadeImageLabel(QLabel):
    def _blend(self, old: QPixmap, new: QPixmap, t: float) -> QPixmap:
        out = QPixmap(new.size()); out.fill(Qt.transparent)
        p = QPainter(out)
        if not old.isNull():
            p.setOpacity(1.0 - t); p.drawPixmap(0, 0, old)
        p.setOpacity(t); p.drawPixmap(0, 0, new)
        p.end(); return out
    # QVariantAnimation(0→1, 220ms, QEasingCurve.OutQuint) 의 valueChanged 에서 setPixmap(_blend(...))
```
scale 1.012→1 은 `new` 를 `transform` 없이 1.2% 확대해 그린 뒤 축소 보간으로 근사하세요.
생략해도 게이트 위반은 아닙니다(220ms opacity 가 본질).

### AD5. em-dash 0건은 코드 주석·docstring·커밋 메시지에도 적용

기존 코드 주석에 남은 `—`도 손대는 파일 범위에서 함께 정리하세요(전수 일괄 치환은 불필요).

---

## 다음 단계

1. **즉시 착수 가능**(Q1 무관): `theme.py` 토큰 모듈 재작성 + AD3 대비 게이트 테스트 + AD2 accent 파생.
   `02-design-rules.md` §1~2 값을 그대로 상수화하세요.
2. **Q1 확인 후 착수**: 의존성 3중 등록, offscreen 스파이크(Q3), 그 이후 단계 1a→1b→2…
3. **PLAN-02 불요.** 위 결정을 반영해 `PLAN-FINAL.md`를 쓰고, 아래만 확정해 붙이세요:
   - 0단계 실측 결과(위젯 import 전수 · offscreen `FluentWindow` 스모크 · 셸 생성 시간 - A5의 A안 조건)
   - P1~P5 반영 내역
   - 단계 1a/1b 분리 후 커밋 목록
4. 구현 중 질의는 `QUESTIONS-<n>.md`로. 특히 다음은 즉시 물어야 합니다:
   - P1 스케일바 실비율 획득 경로가 발견된 경우
   - 게이트 4개 중 하나를 못 지키는 지점
   - 라이트/다크 중 한쪽만 게이트를 통과하는 토큰 조합

**착수 승인 범위**: 1번 항목(토큰·대비 테스트·accent 파생) 전면 승인. 2번 이후는 Q1 확인 후.
