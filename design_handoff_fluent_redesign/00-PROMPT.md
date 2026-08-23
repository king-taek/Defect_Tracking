# 00 · Claude Code 착수 프롬프트

> 아래 블록을 그대로 Claude Code에 붙여 넣으세요.
> 핸드오프 폴더는 저장소 루트에 두고, 폴더째 컨텍스트로 주면 됩니다.

---

```
너는 PySide6 데스크톱 앱을 다루는 시니어 엔지니어다.
이 저장소(Defect_Tracking)의 UI 전체를 QFluentWidgets(PySide6-Fluent-Widgets) 기반
Fluent Design으로 재설계한 디자인 핸드오프를 받았다.

핸드오프 위치: ./design_handoff_fluent_redesign/

## 반드시 이 순서로 진행한다

1. README.md → 01-PROTOCOL.md → 02-design-rules.md → 03-screens.md
   → 04-excel-report.md → 05-verified-source-facts.md 를 모두 읽는다.
2. HTML 프로토타입 2개를 브라우저로 열어 직접 조작해 본다.
   (Fluent 프로토타입.dc.html 이 주 산출물. 좌측 nav로 6페이지, 상단 버튼으로 빈 상태·스캔·업데이트·Splash)
3. 저장소 현재 코드를 읽는다. 특히 app/ui/*.py 21개, app/export/excel_report.py,
   tests/test_ui_smoke.py, tests/test_new_features.py.
4. 06-PLAN-TEMPLATE.md 를 복사해 PLAN-01.md 를 채운다.
5. **여기서 멈춘다.** PLAN-01.md 를 출력하고 사용자에게 전달한다.
   Claude Design의 REVIEW-01.md 를 받기 전에는 코드를 한 줄도 수정하지 않는다.
6. REVIEW-01.md 를 받으면 PLAN-FINAL.md 를 쓰고, 승인 후 구현한다.

## PLAN-01.md 작성 규칙

- 06-PLAN-TEMPLATE.md 의 모든 절(A~H)을 채운다. 빈 칸을 남기지 않는다.
- 환경 실측(A)은 추측하지 말고 실제로 실행해 확인한다:
  python -c "import qfluentwidgets; print(qfluentwidgets.__version__)"
  pip list | grep -i fluent
- 위젯 매핑(A 표)은 실제 import 를 시도해 존재를 확인한다. 없는 위젯은 대체안을 쓴다.
- 질의(G)는 8~20개. 01-PROTOCOL.md 의 질의 형식을 반드시 지킨다.
  각 질의에 [BLOCKER]/[택1]/[확인] 우선순위를 붙인다.
  "어떻게 하죠?"가 아니라 "A와 B 중 무엇? 나는 A를 제안한다. 이유는..." 형태로 쓴다.
  코드 라인을 인용한다. 추측으로 묻지 않는다.

## 질의해야 하는 것 (예시 - 실제 코드를 보고 직접 찾아라)

- 02-design-rules.md 의 게이트 4개를 못 지키는 지점
- qfluentwidgets 버전에 없는 위젯
- 프로토타입 동작이 현재 코드 동작과 모순되는 지점
- CSS transition → Qt 애니메이션 번역이 애매한 지점
  (특히 widgets.py 에 기록된 QScrollArea + QGraphicsOpacityEffect 렌더 버그)
- 수천 die 히트맵, 599장 썸네일의 성능 한계
- 기존 테스트가 대량으로 깨지는 범위와 갱신 방침
- 05-verified-source-facts.md 의 "계승 필수" 항목과 재설계가 충돌하는 지점

## 묻지 않고 결정해도 되는 것

- 프로토타입 글리프 → FluentIcon 매핑 (단, PLAN 표에 확정안을 적어라)
- Qt 레이아웃 관용구 선택 (QVBoxLayout stretch 등)
- 변수·함수·클래스 이름, 파일 분할
- 프로토타입 웹폰트 → 시스템 폰트 대체

## 절대 지켜야 하는 것

- 원본 이미지는 read-only. 썸네일 캐시 경유만.
- assert_output_safe 게이트 유지 (출력 경로가 원본 폴더 내부면 차단).
- 모든 서브 인터페이스에 고유 setObjectName().
- Fluent 위젯에 setStyleSheet() 직접 호출 금지 → setCustomStyleSheet(w, light, dark).
- setTheme()은 위젯 생성 전(QApplication 직후).
- Fluent 패키지는 1개만 설치.
- HTML/CSS를 그대로 옮기지 말 것. 디자인 레퍼런스일 뿐이다.
- img/def01~10.jpg 는 합성 목업이다. 코드에 넣지 말 것.

## 구현 중 막히면

플랜 전체를 다시 쓰지 말고 QUESTIONS-<번호>.md 에 질의 형식만 써서 사용자에게 전달한다.
그 파일을 Claude Design이 받아 답한다.

## 완료 시

DONE-<범위>.md 에 화면별 대조표(화면 | 구현 파일 | 명세 준수 | 미준수 항목 | 이유)를 쓴다.
미준수를 숨기지 않는다.

지금 1~5단계를 수행하고 PLAN-01.md 를 제시하라.
```

---

## Claude Design에게 검토 요청할 때 쓰는 문구

PLAN-01.md 를 받은 뒤, Claude Design 대화에 이렇게 전달하세요:

```
Claude Code가 작성한 PLAN-01.md 를 첨부합니다.
design_handoff_fluent_redesign/01-PROTOCOL.md STEP 2 형식으로 REVIEW-01.md 를 작성해 주세요.

- 플랜 지적사항: 표로
- 질의 응답: 질의 번호별로 결정 / 이유 / 정확한 값(복붙 가능한 리터럴) / 게이트·권장 표시
- 코드 예시는 Python + qfluentwidgets 로
- 마지막에 판정(승인 | 조건부 승인 | 재작성 필요)과 착수 승인 범위
```

구현 중 질의(`QUESTIONS-<번호>.md`)를 받았을 때도 같은 형식으로 답해 주세요.
