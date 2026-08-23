# REVIEW-02 · QUESTIONS-02 검토서

작성: Claude Design · 대상: `QUESTIONS-02.md` (라이트 테마 대비 게이트 미달 4쌍)
전제 확인: `PLAN-FINAL.md` 는 REVIEW-01 결정 14건 · 지적 5건을 전부 정확히 반영했습니다. 별도 지적 없음.

---

## 판정

**승인 + 값 확정.** 측정·검산 결과 제시된 수치 전부 정확합니다(`#FFFFFF`/`#0078D4` = 4.528 재확인).
strict xfail 로 남겨 몰래 완화하지 않은 처리는 정확한 판단입니다.

다만 **Q15는 A/B 어느 쪽도 그대로 채택하지 않습니다.** 질문에 빠진 변수가 하나 있습니다.

---

## 먼저: 고정 hex 답변이 성립하지 않는 이유

`accentPreset` 은 사용자가 `setThemeColor` 로 바꿀 수 있게 설계돼 있습니다(프로토타입 Tweaks에
프리셋 3종이 있고, 사용자는 실제로 `#009FAA` 를 골라 사용 중입니다). 측정하면:

| 프리셋 | 흰 글자 | near-black 글자 | 판정 |
|---|---|---|---|
| `#0078D4` Windows | **4.53** | 4.07 | 둘 다 미달 → 채움 조정 필요 |
| `#009FAA` QFluent | **3.21** | **5.73** | near-black 이면 통과 |
| `#8B5CF6` Violet | 4.24 | 4.35 | 둘 다 미달 → 채움 조정 필요 |

즉 `onAccent` 를 라이트=흰색으로 **고정한 것 자체가 버그**였습니다. 다크에서 near-black을 쓰는
이유(밝은 accent 위에 흰 글자는 안 읽힌다)는 **밝기의 문제이지 테마의 문제가 아닙니다.**
`#009FAA` 는 라이트 테마에서도 near-black 이 맞습니다.

---

## A15 → Q15 [BLOCKER] accent 채움 위 글자

- **결정**: **B 변형.** ① `onAccent` 를 **휘도로 결정하는 규칙**으로 바꾸고, ② 그래도 5.0에
  못 미치는 채움색은 **자동으로 조정(clamp)** 합니다. 기본 라이트 채움은 `#0067B8` 로 확정합니다.
- **이유**: A(4.5 예외)는 게이트를 무는 순간 다음 프리셋에서 3.21:1 이 통과됩니다 - 예외는 한 번
  열면 닫히지 않습니다. B(단일 hex 조정)는 `#0078D4` 만 고치고 나머지 프리셋을 방치합니다.
  규칙으로 바꾸면 사용자가 어떤 색을 고르든 게이트가 유지됩니다.
  `#0067B8` 은 Fluent 이전 세대 표준색이라 임의값이 아니고, 5.78로 여유가 있습니다
  (`#0071C7` 5.02는 알파 합성·감마 차이에서 다시 미달로 떨어집니다).
- **정확한 값**:
  ```python
  # theme.py - accent_roles() 를 이 구현으로 교체
  ONACCENT_LIGHT = "#FFFFFF"
  ONACCENT_DARK  = "#16140F"
  ACCENT_GATE    = 5.0
  ACCENT_DEFAULT = "#0067B8"      # 라이트 기본 채움 (구 #0078D4 → 4.53 미달)

  def resolve_accent(base: str, dark: bool) -> dict[str, str]:
      """어떤 accent 를 받아도 게이트를 지키는 3역할을 돌려준다."""
      fill = QColor(base)
      # 1) 채움 위 글자는 휘도로 고른다 (테마가 아니라 밝기 기준)
      def best_on(c: QColor) -> tuple[str, float]:
          w = contrast(ONACCENT_LIGHT, c.name())
          b = contrast(ONACCENT_DARK, c.name())
          return (ONACCENT_LIGHT, w) if w >= b else (ONACCENT_DARK, b)

      on, ratio = best_on(fill)
      # 2) 그래도 미달이면 채움을 어둡게(라이트) / 밝게(다크) 조정
      guard = 0
      while ratio < ACCENT_GATE and guard < 24:
          fill = fill.lighter(106) if dark else fill.darker(106)
          on, ratio = best_on(fill)
          guard += 1

      return {
          "fill":     fill.name(),
          "hover":    fill.lighter(112).name() if dark else fill.darker(112).name(),
          "pressed":  fill.lighter(126).name() if dark else fill.darker(126).name(),
          "onAccent": on,
          "text":     fill.lighter(140).name() if dark else fill.darker(126).name(),
          "tint":     f"rgba({fill.red()},{fill.green()},{fill.blue()},{0.13 if dark else 0.09})",
      }
  ```
  기본 프리셋 3종의 해결값(회귀 테스트에 이 표를 박아 두세요):
  ```
  라이트
    #0078D4 → fill #0067B8 · onAccent #FFFFFF (5.78) · hover #005A9E · pressed #004C85 · text #005A9E
    #009FAA → fill #009FAA (조정 없음) · onAccent #16140F (5.73)
    #8B5CF6 → fill #7B3FE4 · onAccent #FFFFFF (5.72)
  다크
    #4CC2FF → fill #4CC2FF · onAccent #16140F (9.17, 조정 없음)
    #009FAA → fill 밝게 조정 후 onAccent #16140F
  ```
  `02-design-rules.md` §1.3 의 라이트 `accentFill #0078D4` / `onAccent #FFFFFF` 고정 표기는
  **이 규칙으로 대체**합니다. `accentText` 는 `#005A9E`(7.11) 유지.
- **타협 가능 여부**: **게이트** - 휘도 기반 `onAccent` 선택과 clamp 규칙.
  **권장** - 기본값 `#0067B8`(다른 5.0 이상 파랑으로 교체 가능).

## A16 → Q16 [BLOCKER] 상태색 3쌍

- **결정**: **B 채택, 여유값.** 글자만 어둡게, 배경 3색 유지.
- **이유**: Q15에서 여유를 택했으므로 같은 기준을 적용합니다(한 화면에 두 기준을 쓰지 않는다).
  최소변경값(5.01~5.03)은 상태 배경이 카드·InfoBar·배지에서 조금씩 달라질 때 다시 미달로 떨어집니다.
  이 세 색은 **판정을 나르는 색**이라 여유가 필요합니다.
- **정확한 값**:
  ```python
  # 라이트 - 글자만 교체
  PASS   = "#0B6A0B"   # 5.96  (구 #0F7B0F 4.76)
  WARN   = "#8A5200"   # 5.80  (구 #9D5D00 4.77)
  DANGER = "#B02218"   # 5.76  (구 #C42B1E 4.79)
  # 배경 유지
  PASS_BG   = "#DFF6DD"
  WARN_BG   = "#FFF4CE"
  DANGER_BG = "#FDE7E9"
  # 다크 - 변경 없음 (6.14 / 8.64 / 6.20 전부 통과)
  ```
  `02-design-rules.md` §1.4 의 라이트 3색을 위 값으로 교체합니다.
  `danger` 는 hover 파괴 액션(✕ 버튼, 전체 비우기)에도 쓰이므로 `#B02218` 로 통일하세요.
- **타협 가능 여부**: **게이트**(5.0 이상) / **권장**(정확한 hex - 5.7 이상 유지 조건에서 교체 가능).

## A17 → Q17 [확인] 게이트 적용 대상 정의

- **결정**: **제안 승인 + 2개 추가.**
- **이유**: 제안된 경계("읽어야 하는 텍스트 + 의미를 나르는 글리프")가 정확합니다. 빠진 것은
  ① 텍스트가 아니지만 조작에 필요한 요소(포커스 링·컨트롤 경계)와 ② 프리셋 검증입니다.
  경계선에 5.0을 요구하면 Fluent 룩이 깨지므로 **별도 하위 기준 3.0**을 둡니다(WCAG 비텍스트 기준).
- **정확한 값**:
  ```
  게이트 1 (≥ 5.0) 대상
    · txt1 / txt2 / txt3  × card / layer / win
    · onAccent × accentFill                  (A15 규칙 적용 후)
    · accentText × card / layer
    · pass / warn / danger × 각 상태 배경 + card
    · 상태 배지 글자, 하이퍼링크, 키캡 글자
    · 순검정 무대 위 텍스트 (별도 쌍 - 흰 62% 7.84 / 66% 8.83 / 55% 6.25 전부 통과)
    · 프리셋 검증: accentPreset 3종 × 라이트·다크 = 6조합의 onAccent × fill

  하위 기준 (≥ 3.0) 대상 - 비텍스트
    · 포커스 링 × 인접 배경
    · ctrlBd / ctrlBdBottom × ctrlBg          (컨트롤 경계 식별)
    · cardBorder × layer
    · 히트맵 선택 링 × 램프 최저·최고 채움 양쪽

  게이트 제외
    · txtDeco (구분자 / · 전용 - "구분자에만 쓰였는지" 정적 검사와 쌍으로만 허용)
    · disabled 상태 (의도적 약화)
    · 순수 장식 선·그림자·divider
    · 램프 중간 계조 (연속값이라 쌍 정의 불가 - 대신 최저/최고 채움만 검사)
  ```
- **타협 가능 여부**: **게이트**(대상·제외 목록) / **권장**(하위 기준 3.0 수치).

---

## 추가 지시

### AD6. `txtDeco` 오용 방지 정적 검사

게이트에서 빼는 대가로 사용처를 고정하세요.
```
허용: 구분자 "/" "·" , 수치 분모(" / 24 쌍"), 페이지 경계 라벨
금지: 그 외 전부. app/ui 에서 txtDeco 참조 라인을 grep 해 위 목록 밖이면 실패
```
(REVIEW-01 이후 실제로 이 오용이 한 번 발생했습니다 - `/ 8` 분모가 2.66:1까지 떨어진 적 있음)

### AD7. PLAN-FINAL 추가 발견 2건 확인

1. **`qfluentwidgets` import 시 stdout 홍보 문구** - 검증 결과(`print()` 는 `stdout=None` 에서
   조용히 무시) 그대로 수용합니다. 별도 억제 코드를 넣지 마세요(라이선스 고지 성격일 수 있습니다).
2. **핸드오프 폴더를 `_SKIP_DIRS` 에 등록** - **정확한 판단입니다.** 536KB 문서가 전 사용자
   업데이트에 실리는 것은 명백한 회귀였습니다. 회귀 테스트까지 붙인 처리를 승인합니다.
   `img/` 안의 합성 목업 10장도 같은 이유로 배포 대상이 아닙니다(폴더째 제외되므로 자동 해결).

---

## 다음 단계

1. **즉시**: A15 규칙 + A16 hex + A17 대상 목록을 `theme.py` / `tests/test_tokens.py` 에 반영,
   strict xfail 4건 제거. 프리셋 6조합 회귀도 같은 커밋에.
2. `02-design-rules.md` §1.3 / §1.4 는 위 결정으로 갱신된 것으로 간주하세요(문서 재발행 불요,
   이 REVIEW-02 가 상위 근거).
3. 커밋 ③ 이후는 여전히 **Q1(라이선스)** 대기입니다.
4. 다음 질의 시점 예상: 단계 2(판독대 12칸 실측 - 4열에서 카드 폭이 좁아 헤더 배지·Δ 수치가
   겹치는지), 단계 6(래스터 LOD 색 계조가 프리셋 변경 시에도 구분되는지).
