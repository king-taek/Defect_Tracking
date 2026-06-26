# Conder Scan Review Image Compare Viewer

반도체/패키지 공정의 **review defect 이미지 비교 뷰어**입니다.
기준 Layer 의 defect 위치를 기준으로 다른 Layer 에서 같은 위치의 defect 를 찾아 비교하고,
결과를 Excel 로 출력합니다.

> **최우선 원칙 — 원본 보호**
> 본 프로그램은 원본(LOT) 폴더를 **read-only** 로만 다룹니다. 원본 파일을
> 생성/복사/이동/이름변경/삭제/수정하지 않으며, 캐시·썸네일·Excel 결과물은
> 항상 원본 폴더 **밖**에만 저장합니다. (KLA 파일명도 실제로 바꾸지 않고 메모리에서만 변환)

---

## 주요 기능

- **LOT 폴더 선택** → layer / wafer 구조 자동 인식 (Section 8.1~8.2)
- **좌표 자동 추출/변환** (`col_row_x_y`) — 세 가지 출처 모두 지원
  - Camtek 파일명에 포함된 좌표 직접 추출
  - `ColorImageGrabingInfo.ini` 기반 Camtek 좌표 산출
  - KLA `.001` info 파일(TiffFileName/DefectList) 기반 변환
- **기준/비교 Layer 선택 + 허용 오차 설정** 후 같은 die·좌표 매칭 (Section 8.3)
- **RDL4/PI4 … 그리드 배치**, 기준 Layer 강조 (Section 8.4)
- **상단 썸네일 스트립** — 사진 중앙 10% 확대, 클릭 시 기준 전환 (Section 8.6)
- **이전/다음 탐색**, 기준 변경 시 비교 이미지 빠른 Fade 갱신 (Section 8.5)
- **Excel 결과 출력** — 이미지·wafer 정보·매칭 결과 포함 (Section 8.7)
- **다크 + 파란 네온 UI**, hover/pressed 시각 변화, 부드러운 전환 (Section 9)

---

## 실행 (소스)

```bash
pip install -r requirements.txt
python main.py
```

대상 환경은 Windows(네트워크 경로 `\\k5cifsn2\...`)입니다.

### 합성(가짜) 데이터로 체험하기

사내 네트워크 없이도 전체 워크플로를 시험할 수 있습니다.

```bash
python -m tools.make_sample_data            # 기본 위치(workspace/sample_source)에 생성
# 또는
python -m tools.make_sample_data ./_sample  # 지정 폴더에 생성
```

생성된 `... / 204. TB500INT.226 (WLW)` 폴더를 프로그램에서 LOT 폴더로 선택하세요.

---

## 빌드 (Windows .exe)

```bash
pip install -r requirements.txt pyinstaller
python build_exe.py        # -> dist/ConderCompare.exe
```

---

## 출력/캐시 위치 (원본 밖)

기본 작업공간: `%LOCALAPPDATA%\ConderCompare\`
- `cache/` — 썸네일 캐시
- `exports/` — Excel 결과
- `settings.json` — 사용자 설정(마지막 LOT, 허용 오차 등)

출력 경로가 원본 LOT 폴더와 같거나 그 하위이면 저장이 **차단**됩니다.

---

## 좌표 변환 규칙 (요약)

| 구분 | col | row | x | y |
|------|-----|-----|---|---|
| KLA | `XINDEX + 3` | `YINDEX + 3` | `Round(XREL)` | `Round(DiePitchY - YREL)` |
| Camtek INI | `Col - 2` | `7 - Row` | `X - Col×37247.7` | `Y - Row×44905.4` |

상수(pitch, package count, 그리드 배치)는 `app/config.py` 에서 제품별로 조정할 수 있습니다.

---

## 테스트

```bash
pytest -q
```

문서에 제시된 워크드 예시(KLA `3_4_4629_5351`, Camtek INI 5개 예시 등)를 그대로
단위 테스트로 고정 검증합니다.

---

## 구조

```
main.py                 진입점
app/
  config.py             상수 + 사용자 설정
  safety.py             원본 보호 게이트 (2중 보호)
  models.py             도메인 모델
  scanner.py            LOT 폴더 스캔 + 좌표 출처 판별
  matcher.py            die·좌표 tolerance 매칭
  layout.py             layer 정규화 + 그리드 배치
  thumbnails.py         중앙 10% 썸네일 캐시
  workers.py            백그라운드 스캔/썸네일
  parsers/              camtek_filename · camtek_ini · kla_info
  export/excel_report.py  Excel 출력
  ui/                   theme · main_window · thumbnail_strip · compare_grid · controls · export_dialog · widgets
tools/make_sample_data.py  합성 데이터 생성기
tests/                  pytest
```
