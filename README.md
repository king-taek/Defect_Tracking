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
- **비동기 이미지 로딩 + LRU 캐시** — 네트워크 경로에서도 탐색 시 UI 멈춤 최소화 (Section 10)
- **진단 표시** — 좌표 추출 실패 건수/사유를 상태 표시줄 tooltip 으로 안내 (Section 11)
- **원본 확대 뷰어** — 그리드 이미지를 클릭하면 원본 전체 해상도로 보기(맞춤/실제·휠 줌·Esc)
- **키보드 탐색** — ←/→·PageUp/Down·Home/End, Ctrl+O(폴더)·Ctrl+E(출력)
- **비차단 알림 배너** — 오류/완료를 모달 없이 매끄럽게 안내(출력 완료 시 "폴더 열기" 액션)
- **매끄러운 사용성** — 조작이 현재 보던 위치를 리셋하지 않음, 화면 전환 페이드,
  세로 휠로 썸네일 좌우 스크롤(가로 휠 불필요), 비교 Layer 줄바꿈 + 전체/해제,
  창 크기·허용오차·선택 기억, 고DPI 선명도, 빠른 폴더 재선택 시 옛 결과 무시

---

## 실행 (소스)

```bash
python bootstrap.py     # 필요한 라이브러리 자동 점검/설치
python main.py
```

`bootstrap.py` 는 PySide6·Pillow·openpyxl 누락 여부를 확인하고 없으면 자동 설치합니다
(`python bootstrap.py --check` 는 점검만). 라이브러리가 없으면 `main.py` 도 친절한 안내를 출력합니다.

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

## 자동 업데이트

상단 **업데이트** 버튼으로 최신 메인 브랜치를 가져와 적용합니다. 프로그램을 켜면 백그라운드로
업데이트 여부를 확인하고, 새 버전이 있으면 물어본 뒤(동의 시) 업데이트하고 "다시 시작하세요"
안내 후 종료합니다(설정에서 끌 수 있음).

- 설치 형태 자동 감지: `git` 체크아웃이면 `git fetch + reset --hard origin/main`,
  아니면 GitHub ZIP 을 받아 설치 폴더에 덮어씁니다(사용자 작업공간은 건드리지 않음).
- 대상 저장소는 `app/config.py` 의 `UPDATE_OWNER/REPO/BRANCH` 로 설정합니다.
- 실행파일(.exe) 버전은 자동 업데이트 대상이 아니며 새 빌드로 교체합니다.

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
또한 LOT 폴더를 열 때 작업공간(캐시/결과)이 그 LOT 내부에 있으면 경고 후 작업을 막습니다.

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
main.py                 진입점 (의존성 가드)
bootstrap.py            의존성 점검·자동 설치
app/
  config.py             상수 + 사용자 설정 + 업데이트 대상
  updater.py            자동 업데이트(git/ZIP, 테스트가능)
  safety.py             원본 보호 게이트 (2중 보호)
  models.py             도메인 모델
  scanner.py            LOT 폴더 스캔 + 좌표 출처 판별
  matcher.py            die·좌표 tolerance 매칭
  layout.py             layer 정규화 + 그리드 배치
  thumbnails.py         중앙 10% 썸네일 캐시
  workers.py            백그라운드 스캔/썸네일
  parsers/              camtek_filename · camtek_ini · kla_info
  export/excel_report.py  Excel 출력
  ui/                   theme · main_window · thumbnail_strip · compare_grid · controls · export_dialog
                        widgets · image_loader · image_viewer · notifications · flow_layout · settings_dialog
tools/make_sample_data.py  합성 데이터 생성기
tests/                  pytest
```
