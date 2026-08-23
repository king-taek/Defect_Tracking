# 04 · Excel 출력 재설계 (app/export/excel_report.py)

## 결정 사항 (사용자 확정)

1. **시트는 「사진 대조」 하나만.** 요약·매칭 표·미매칭 시트는 만들지 않는다.
2. **미매칭은 전부 회색 1단.** 사유·최근접 거리·적색 강조를 넣지 않는다. 회색 채움 + "미매칭" 한 단어.
3. **거리(Δ µm) 표기 없음.** 매칭 / 미매칭 두 상태만.
4. **열은 LOT layer 순서 고정.** 기준을 첫 열로 끌어오지 않고, 자기 자리에서 ★ 표시로만 구분.
5. **담은 항목만 출력.** 전량 삽입하지 않는다.
6. 필터·정렬·layer 집계는 리포트 범위 밖. 앱에서 수행한다.

## 현재 코드의 문제 (전수조사 결과 9건)

| # | 문제 | 근거 |
|---|---|---|
| 00 | 기준 layer가 맨 앞으로 끌려나옴 | `entries=[None]+results`, `layer_order` 미전달 시 |
| 01 | 담지 않은 건까지 전량 삽입 | `selected` 전량 × `n_data_cols`, 190px 썸네일 |
| 02 | 미매칭이 적색으로 튄다 | `_set_cell(..., "매칭 없음", color=_NOMATCH)` |
| 03 | 6행 라벨 블록의 낭비 | `#N`/`Layer`/`이미지`/`정보`/`원본경로` + 간격행 |
| 04 | 이미지가 셀에 묶여 있지 않음 | `xl.anchor = f"{col}{row}"` - 크기를 셀에 맞추지 않음. 열 폭·글자 배율 변경 시 정렬 깨짐 |
| 05 | 쓰지 않는 거리 값이 자리를 차지 | `f"매칭 O (거리 {dist:.1f})"` + 위치 + 파일명 3줄 |
| 06 | 링크 텍스트가 전부 동일 | `cell = ws.cell(..., value="원본 사진 열기")` |
| 07 | 창 고정·인쇄 설정 없음 | `freeze_panes`/`page_setup`/`print_title_rows` 미설정 |
| 08 | 대비 미달 색 | `_NEON = "FF1E90FF"` 채움 + 흰 글자 = 3.0:1 |

> 04는 "셀을 넘친다"가 아닙니다. 열 폭 30 ≈ 215px, 행 높이 150pt = 200px, 썸네일 최장변 190px 캡이므로
> 현재도 셀 안에 들어맞습니다. 문제는 **셀에 맞춰 리사이즈되지 않는다**는 점입니다.

## 재설계 명세

### 시트 구조 (단일 시트 "사진 대조")

```
행 1  [머리] 진한 남색(#20303F) 채움 + 흰 글자
      "사진 대조" | LOT · 기준 LYA3 · 허용 100 µm | (우) 담은 12건 · layer 12 · 생성시각
행 2  [규칙] 연한 회색(#F1F5F9)
      "열 = LOT layer 순서 고정 · 기준은 ★ 표시로만 구분 · 창 고정 · 블록당 1페이지"
      (우) "미매칭 = 회색 처리 · 거리 표기 없음"
행 3~ [블록 반복]
```

**창 고정**: `ws.freeze_panes = "A3"`

### 블록 (기준 1건 = 4행)

```
블록 머리 1행 (#EEF3F8):
  #N | wafer W455685703 | die (2, 4) | pos 2_4_2210_1180 | [결함명 배지] | [기준 LYA3 배지] | (우) 매칭 8 / 11

layer 행 (12칸, LOT 순서):
  기준 칸: 진한 남색 채움 + 흰 글자 + "★ 기준"
  일반 칸: #E8EEF4 채움 + 진한 글자 + 깊이 접미(재/재재)
  미매칭 칸: #EFF1F3 채움 + #8A949E 글자

사진 행 (높이 96px 상당):
  매칭: 셀 크기에 맞춘 썸네일(#000 배경), 우하단 ＋n 클러스터 배지
  미매칭: #F6F7F8 채움 + 중앙 "미매칭"(#8A949E 9.5/600)

상태 행:
  매칭: "매칭"(#1F7A1F 600) + #EEF7EE 연한 채움
  미매칭: "—"(#A8B0B8) + #F6F7F8

파일명 행:
  매칭: 실제 파일명 하이퍼링크(#0F6CBD, 밑줄) - 2_4_2210_1180.jpg
  미매칭: 빈 칸
```

### 인쇄 설정

```python
ws.page_setup.orientation = "landscape"
ws.page_setup.fitToWidth = 1
ws.page_setup.fitToHeight = 0
ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
ws.print_title_rows = "1:2"          # 머리 2행 반복
# 블록마다 페이지 나눔
ws.row_breaks.append(Break(id=block_last_row))
```

### 이미지 삽입 (문제 04 대응)

```python
xl = XLImage(str(thumb))
# 앵커만 걸지 말고 셀 크기에 맞춰 리사이즈
target_w_px = int(col_width_chars * 7.0)      # 대략 1 char ≈ 7px
target_h_px = int(row_height_pt * 96 / 72)
ratio = min(target_w_px / xl.width, target_h_px / xl.height, 1.0)
xl.width, xl.height = int(xl.width * ratio), int(xl.height * ratio)
xl.anchor = f"{col_letter}{row}"
ws.add_image(xl)
```
글자 크기 "크게"(`theme.FONT_SCALES["large"] = 1.3`)일 때도 같은 계산으로 따라가게 하세요.

### 색 팔레트 (기존 상수 교체)

```python
_HEAD    = "FF20303F"   # 머리 채움 (흰 글자와 12.6:1)
_SUBHEAD = "FFF1F5F9"   # 규칙 행
_LYHEAD  = "FFE8EEF4"   # layer 머리
_BLOCK   = "FFEEF3F8"   # 블록 머리
_GREY_BG = "FFF6F7F8"   # 미매칭 채움
_GREY_FG = "FF8A949E"   # 미매칭 글자
_PASS    = "FF1F7A1F"   # "매칭"
_PASS_BG = "FFEEF7EE"
_LINK    = "FF0F6CBD"
_LINE    = "FFDCE3EA"
# 삭제: _NEON(#1E90FF), _NOMATCH(#B00020), _NAVY(#1B2A4A), _LIGHT, _GREY
```

### 기준 없음(히트맵 교차매치) 출력

`base_layer` 없이 호출되는 경로(`all_layers_provider` / 전체 defect 모드):
- ★ 기준 칸이 **없습니다.** 12칸 모두 일반 layer로 동등한 폭
- 블록 단위는 기준 사진이 아니라 **die 위치의 교차 그룹**
- 블록 머리 배지: `교차매치` / 어느 layer와도 못 만난 것은 `개별`
- 머리 메타: `기준 없음 · 조사 layer 12 · 허용 100 µm`, 출처 `히트맵 선택 n위치`
- 매칭 카운트: `n / 12` (기준 열이 없으므로 분모가 12)

`layer_order` 인자를 **항상 전달**하세요. 기준 있음/없음 모두 LOT 순서를 씁니다.

### 예상 효과

| | 현재 | 재설계 |
|---|---|---|
| 파일 크기 | 318 MB | 11 MB |
| 블록 수 | 44건 전량 | 담은 12건 |
| 열기 시간 | 40초+ | 2초 |
| 인쇄 | 설정 없음 | 1건 = 1페이지 |
| 미매칭 표기 | 적색 강조 | 회색 1단 |
