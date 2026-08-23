# 02 · 판단 기준 (토큰 · 모션 · 카피 · 게이트)

이 문서의 값은 **단일 출처**입니다. 화면에서 색·간격·duration을 새로 만들지 마세요.

## 0. 게이트 (타협 불가 4개)

1. **대비 게이트 ≥ 5.0** - 텍스트/배경 전 조합. 12px 이하 캡션은 특히 실측하세요.
2. **accent 3역할 분리** - 아래 §1.3. 하나의 색을 fill과 text에 같이 쓰지 마세요.
3. **미매칭은 회색 1단** - 사유·거리·적색 강조 없이 회색 채움 + "미매칭" 한 단어. (사용자 결정)
4. **판독대 12칸 보장** - layer 12개를 켜도 사진이 읽히는 크기 유지(최소 224px 셀) + 스크롤.

## 1. 색 토큰

### 1.1 라이트 (기본)
```
win          #F3F3F3   창 배경 (Mica)
layer        #F9F9F9   페이지 면
card         #FFFFFF   카드
cardHover    #F7F7F7
cardBorder   rgba(0,0,0,.058)
cardBorderH  rgba(0,0,0,.16)
txt1         rgba(0,0,0,.90)   본문·제목
txt2         rgba(0,0,0,.61)   보조 (5.97:1)
txt3         rgba(0,0,0,.62)   작은 내용 텍스트 (게이트 통과값)
txtDeco      rgba(0,0,0,.38)   장식 전용 (구분자 / · 만)
divider      rgba(0,0,0,.08)
ctrlBg       rgba(255,255,255,.70)
ctrlBgH      rgba(249,249,249,.50)
ctrlBgP      rgba(249,249,249,.30)
ctrlBd       rgba(0,0,0,.07)
ctrlBdBottom rgba(0,0,0,.16)   ← Fluent 컨트롤 하단 1px 진한 테두리
subtle       rgba(0,0,0,.03)
subtleH      rgba(0,0,0,.037)
```

### 1.2 다크
```
win #202020 · layer #272727 · card #2B2B2B · cardHover #313131
cardBorder rgba(255,255,255,.07) · cardBorderH rgba(255,255,255,.16)
txt1 rgba(255,255,255,.94) · txt2 rgba(255,255,255,.72) · txt3 rgba(255,255,255,.72)
txtDeco rgba(255,255,255,.42) · divider rgba(255,255,255,.09)
ctrlBg rgba(255,255,255,.06) · ctrlBgH rgba(255,255,255,.09) · ctrlBgP rgba(255,255,255,.04)
ctrlBd rgba(255,255,255,.09) · ctrlBdBottom rgba(255,255,255,.09)
subtle rgba(255,255,255,.04) · subtleH rgba(255,255,255,.06)
```

### 1.3 accent - 3역할 분리 (게이트)
```
                라이트        다크
accentFill      #0078D4      #4CC2FF     배경 채움 전용
accentHover     #106EBE      #4CC2FF
accentPressed   #005A9E      #3AA9E0
onAccent        #FFFFFF      #16140F     accent 채움 위의 글자 (다크는 near-black!)
accentText      #005A9E      #4CC2FF     글자·글리프로 쓰는 accent
accentTint      rgba(0,120,212,.09)  rgba(76,194,255,.13)
```
> 다크 테마에서 accent 채움 위에 흰 글자를 쓰면 2.01:1 입니다. `onAccent` 를 쓰세요.
> QFluentWidgets는 `setThemeColor()` 로 accent를 바꿉니다. 위 3역할을 각각 파생시키세요.

### 1.4 상태색
```
pass    #0F7B0F (다크 #6CCB70)   배경 #DFF6DD / rgba(15,123,15,.18)
warn    #9D5D00 (다크 #FFD68A)   배경 #FFF4CE / rgba(157,93,0,.20)
danger  #C42B1E (다크 #FF99A4)   배경 #FDE7E9 / rgba(196,43,30,.20)
info    accentText              배경 #F4F9FE / rgba(76,194,255,.14)
photo   #000000 - 사진 바탕은 두 테마 모두 순검정. 예외 없음.
```

## 2. 형태 · 타이포

```
radius   컨트롤 5 · 카드 7 · 시트/다이얼로그 8 · 칩 13(pill)
높이     컨트롤 32 · 주요버튼 32~36 · 행 21(표) / 60(명세행) · nav 항목 40 · 타이틀바 48
간격     페이지 패딩 22/28 · 카드 패딩 14~18 · gap 6/8/12/16
타이포   제목 26/600/-0.5px · 섹션 17/600 · 본문 12.5~13 · 캡션 11.5~12 · 라벨 11/600
수치     등폭 + tabular-nums 예외 없음 (Δ µm, 개수, 좌표, 배율, 진행률)
한글 라벨 nowrap
```

> **12px 이하 규칙**: 읽어야 하는 텍스트는 12px 이상 + `txt2`/`txt3`. 11px 이하는 장식·단위만.

## 3. 모션 규격

```
컨트롤 상태(hover/pressed/색)   120ms linear
진입(등장·펼침)                  250ms cubic-bezier(0,0,0,1)
퇴장(사라짐·접힘)                150ms cubic-bezier(.7,0,1,.5)
nav pill 인디케이터              300ms cubic-bezier(.1,.9,.2,1)   top/bottom/height
Flyout                          187ms 진입 / 120ms 퇴장 + translateY 8px
시트·다이얼로그                  스크림 200ms linear + 시트 250ms opacity/scale .96→1
InfoBar                         진입 200ms + translateX 14px, 자동소멸 3.4s
사진 교체                        220ms opacity + scale 1.012→1
조건부 행 펼침/접힘              250ms / 150ms + height
스피너                          등속 900ms linear 무한 (가감속 금지)
줌                              250ms cubic-bezier(0,0,0,1) transform
```

**금지**: `blur()` 애니메이션, 무한회전에 가감속, 100개 이상 동시 애니메이션, 재정렬 즉시 점프.

**Qt 번역**
| CSS | Qt |
|---|---|
| `transition: 120ms linear` (색) | QSS `:hover`/`:pressed` (즉시) 또는 `QVariantAnimation` on palette |
| `cubic-bezier(0,0,0,1)` | `QEasingCurve.OutQuint` (근사) 또는 `QEasingCurve.BezierSpline` |
| `cubic-bezier(.7,0,1,.5)` | `QEasingCurve.InQuart` |
| `cubic-bezier(.1,.9,.2,1)` | `QEasingCurve.OutQuart` |
| `opacity` 전이 | `QGraphicsOpacityEffect` + `QPropertyAnimation` |
| `transform: scale()` | `QPropertyAnimation` on `geometry` 또는 `QGraphicsScale` |
| `translateY(1px)` pressed | QSS `:pressed { padding-top: 1px; padding-bottom: -1px }` 또는 `move()` |
| `height` 전이 | `QPropertyAnimation` on `maximumHeight` |
| `backdrop-filter: blur` | `qfluentwidgets` AcrylicBrush / `WindowEffect` |

> **주의**: `QScrollArea` 안에서 `QGraphicsOpacityEffect`를 쓰면 스크롤 시 위젯이 엉뚱한 위치에
> 그려지는 Qt 렌더 버그가 있습니다(원본 `widgets.py` 주석에 기록됨). 그리드 이미지 fade는
> `QStackedWidget` 2장 교차 또는 `QPixmap` 알파 합성으로 대체하세요.

## 4. 카피 규칙

- em-dash(—) 사용 금지. 하이픈(-) 또는 문장 분리.
- 정상은 무표기, 예외만 태그. ("교차매치" 태그를 매 행에 반복하지 않기)
- 이모지 금지 (원본의 📁 🗂 📌 ☆ 🏠 💾 🌐 ↻ 전부 제거 대상)
- 수치에는 단위. `거리 12.4`(X) → `Δ 12.4 µm`(O)
- 사유는 조치 가능한 문장으로. `매칭 없음`(X) → `허용오차 초과 · 최근접 141.8 µm`(O)
  - 단, **Excel 리포트에서는 사용자 결정에 따라 회색 "미매칭" 한 단어**(§0 게이트 3)
- 버튼은 동사. `확인`(X) → `이 폴더 선택`, `Excel 출력`(O)
- 강조는 한 화면에 하나. 주요 액션만 accent 채움.

## 5. 위젯 매핑 (STEP 1에서 실제 클래스명으로 확정)

| 프로토타입 요소 | qfluentwidgets 후보 |
|---|---|
| 창 + 타이틀바 | `FluentWindow` (또는 `MSFluentWindow`) |
| 좌측 nav + pill | `NavigationInterface` / `addSubInterface` |
| nav 배지 | `InfoBadge` |
| 상단 툴바 | `CommandBar` |
| 기준 layer 선택 | `ComboBox` |
| 오차 입력 | `DoubleSpinBox` / `CompactDoubleSpinBox` |
| 비교 layer 팝업 | `Flyout` + `FlyoutViewBase` (`FlyoutAnimationType.DROP_DOWN`) |
| 판독 카드 | `SimpleCardWidget` / `CardWidget` |
| 스케일 분절 | `SegmentedWidget` / `Pivot` |
| 스위치 | `SwitchButton` |
| 설정 카드 | `SettingCardGroup`, `PushSettingCard`, `ComboBoxSettingCard`, `SwitchSettingCard`, `ExpandGroupSettingCard` |
| 알림 | `InfoBar` + `InfoBarPosition.TOP_RIGHT` |
| 진행 표시 | `StateToolTip`, `ProgressBar`, `IndeterminateProgressRing` |
| 확인 대화 | `MessageBox` |
| 안내 팁 | `TeachingTip` (`TeachingTipTailPosition`) |
| 우클릭 메뉴 | `RoundMenu` |
| 경로 탐색 | `BreadcrumbBar` |
| 검색 | `SearchLineEdit` |
| 시작 화면 | `SplashScreen` |
| 스크롤 | `SmoothScrollArea` / `ScrollArea` |
| 툴팁 | `ToolTipFilter` (지연 300ms) |

**필수 규칙 (qfluentwidgets)**
- 모든 서브 인터페이스에 `setObjectName()` 필수 - 없으면 `ValueError`, 중복이면 라우팅 파괴
- Fluent 위젯에 `setStyleSheet()` 금지 → `setCustomStyleSheet(w, light, dark)`
- `setTheme()` 는 위젯 생성 **전에** (QApplication 직후)
- Fluent 위젯과 raw Qt 위젯을 섞지 마세요 (테마 전환 시 일부만 남습니다)
- 팝업(`InfoBar`/`Flyout`/`MessageBox`)에 실제 parent 전달 필수
- Fluent 패키지는 **1개만** 설치 (여러 개면 `qfluentwidgets` 모듈이 서로를 가립니다)
