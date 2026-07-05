# Defect Tracker

반도체/패키지 공정의 **review defect 이미지 비교 뷰어**입니다.
기준 Layer 의 defect 위치를 기준으로 다른 Layer 에서 같은 위치의 defect 를 찾아 비교하고,
결과를 Excel 로 출력합니다.

> **최우선 원칙 — 원본 보호**
> 본 프로그램은 원본(LOT) 폴더를 **read-only** 로만 다룹니다. 원본 파일을
> 생성/복사/이동/이름변경/삭제/수정하지 않으며, 캐시·썸네일·Excel 결과물은
> 항상 원본 폴더 **밖**에만 저장합니다. (KLA 파일명도 실제로 바꾸지 않고 메모리에서만 변환)

---

## 주요 기능

- **자재(LOT) 폴더 선택** → layer / wafer 구조 자동 인식. 상위(device)·하위(layer/wafer)
  폴더를 골라도 자동으로 자재 폴더로 보정하거나 재선택을 안내(비차단 배너).
- **좌표 자동 추출/변환** (`col_row_x_y`) — 세 가지 출처 모두 지원
  - Camtek 파일명 직접 추출 — 실제 AOI 스키마(`…_col_row_Name_x_y_DXSize_DYSize_DArea`,
    정수 x/y + 결함 크기/면적)까지 견고하게 처리
  - `ColorImageGrabingInfo.ini` 기반 Camtek 좌표 산출
  - KLA `.001` info 파일(TiffFileName/DefectList) 기반 변환
- **좌측 사이드바**에서 자재 폴더·기준 Layer·비교 Layer·허용 오차를 한 곳에서 선택.
  기준으로 고른 layer 는 비교에서 자동 제외되며 체크 상태는 보존된다.
- **비교 매칭(개선됨)** — 같은 wafer·die(±1 허용)·좌표 거리 매칭에 더해, **layer 간
  전역 정합오차(median offset)를 자동 추정·보정**한다(두 스캔 사이 계통적 위치 이동이
  허용오차를 넘어도 매칭). 추정된 정합오차는 사이드바 요약 tooltip 으로 표시.
- **실시간 매칭 요약** + 매칭 실패 사유 진단(같은 die 사진 없음 / 좌표 추출 실패 / 허용오차
  초과·최근접 거리 / 동률 후보).
- **디바이스 DB 일반화** — 외부 `AOIDeviceDB.xlsx`(시트=디바이스)를 읽어 제품별 package
  count·die pitch·die 배치를 자동 구성. **DEVA 외 모든 디바이스 지원**(설정에서 DB·디바이스
  선택). 미지정 시 내장 DEVA 으로 폴백.
- **웨이퍼 맵 네비게이터** — 현재 wafer 의 die 격자를 매칭 상태로 색칠(디바이스 DB 가 있으면
  실제 디바이스 모양으로), die 클릭 시 해당 기준으로 이동.
- **리뷰어 도구** — 매칭/미매칭 필터·미매칭 점프(U), 세션 마킹/메모(별·메모, Excel 반영),
  썸네일 상태 점, 우클릭 메뉴(경로 복사·파일/폴더 열기), 최근 폴더.
- **겹쳐 보기/블링크** — 기준+비교 layer 합성, 검은 여백 자동 크롭·중앙 정렬·배율/이동
  미세조정·블링크(Space)로 층간 위치/크기 변화 감지.
- **상단 썸네일 스트립** — 사진 중앙 10% 확대, 부드러운 가로 스크롤, 클릭 시 기준 전환.
- **Excel 결과 출력** — 이미지·wafer 정보·매칭 결과·메모 포함.
- **원본 확대 뷰어** — 그리드 이미지 클릭 시 원본 전체 해상도(맞춤/실제·휠 줌·Esc).
- **키보드 단축키** — ←/→·PageUp/Down·Home/End, U(미매칭)·M(마킹)·O(겹쳐보기)·
  Ctrl+A/D(비교 전체/해제)·Ctrl+O(폴더)·Ctrl+E(출력)·F5(재스캔)·**F1(도움말)**.
- **성능** — wafer 병렬 스캔·썸네일 병렬화·인접 이미지 프리페치·매칭 인덱스 캐시,
  비동기 이미지 로딩 + LRU 캐시(네트워크 경로 탐색 시 UI 멈춤 최소화).
- **관측성/안정성** — 파일 로깅(`workspace/logs/defect_tracker.log`), 설정 원자적 저장,
  스캔 접근오류(권한/네트워크) 비차단 안내, 시작 시 스플래시(로딩 표시).
- **부드러운 다크 UI** — 저채도 슬레이트 테마, 비차단 알림 배너, 창 크기·허용오차·선택 기억,
  고DPI 선명도, 빠른 폴더 재선택 시 옛 결과 무시.

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

생성된 `... / 204. DEVAINT.226 (PKG)` 폴더를 프로그램에서 LOT 폴더로 선택하세요.

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
python build_exe.py        # -> dist/Defect Tracker.exe
```

---

## 단일 파일 배포본 (읽을 수 있는 하나의 `.py`)

프로그램 전체(모든 `app/` 모듈 + `main.py`)를 **읽을 수 있는 단일 파일** 하나로 합쳐,
구조와 기능을 한 파일로 열람·공유할 수 있습니다.

```bash
python tools/build_single_file.py     # -> single_file/defect_tracker.py 생성
python bootstrap.py                    # 라이브러리 설치(최초 1회)
python single_file/defect_tracker.py   # 실행
```

- **산출물이지 소스가 아닙니다.** 소스의 진실은 계속 `app/` + `main.py` 이며, 단일 파일은
  자동 생성됩니다. 단일 파일을 직접 고치지 말고 `app/` 를 고친 뒤 재생성하세요.
- 파일 맨 위에 모듈 맵(목차)과 위상순서 구획이 있어 구조가 한눈에 보입니다.
- **실행 요건**: PySide6 GUI 데스크톱 앱이므로 실행에는 여전히 Python + PySide6 가 필요합니다
  (`bootstrap.py` 로 설치). 브라우저 "웹 파이썬"(Pyodide 등)에서는 Qt 를 못 불러와 실행 불가.
- 번들 `data/AOIDeviceDB.xlsx` 는 선택 사항이며 함께 배포되지 않습니다(없으면 내장 폴백).
- **자동 업데이트**: 단일 파일은 레포 전체 ZIP 을 전개하지 않고, GitHub `main` 의
  `single_file/defect_tracker.py` 를 받아 **자기 자신만 원자적으로 교체**합니다. 최신 여부는
  파일 옆 `version.json`(`{"commit": <sha>}`)의 커밋 SHA 로 판정합니다. 배포 시 정확한 감지를
  위해 커밋·push 직후 `python tools/build_single_file.py --stamp-version` 로 `version.json` 을
  함께 만들어 배포하세요(없으면 첫 실행에서 한 번 "업데이트 있음"으로 뜬 뒤, 업데이트하면 자동 기록).
- 배포 구성: `defect_tracker.py` + `bootstrap.py`(+ 선택 `version.json`).
- **버전 갱신 순서**(app 코드 변경 시): `python tools/compute_version.py --write` →
  `python tools/build_single_file.py` → `app/__init__.py` + 산출물을 같은 커밋에 포함.
  `python tools/build_single_file.py --check` 는 커밋본이 최신인지만 확인합니다(테스트에서 강제).

---

## 출력/캐시 위치 (원본 밖)

기본 작업공간: `%LOCALAPPDATA%\DefectTracker\`
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

상수(pitch, package count, 그리드 배치)는 `app/config.py` 의 제품 프로파일에서 조정하거나,
외부 **`AOIDeviceDB.xlsx`** (시트 1개 = 디바이스 1개; `Package Info` X/Y/X1/Y1 + `Map`)를
설정에서 지정해 디바이스별로 자동 구성할 수 있습니다(DEVA 외 전제품).

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
main.py                 진입점 (의존성 가드 + 스플래시 + 디바이스 DB 로드)
bootstrap.py            의존성 점검·자동 설치
app/
  config.py             상수 + 제품 프로파일(ProductConfig/PRODUCTS) + 사용자 설정
  device_db.py          외부 AOIDeviceDB.xlsx 로더(디바이스별 package/pitch/die map)
  logging_config.py     파일/콘솔 로깅
  session.py            세션 마킹/메모(작업공간 JSON)
  updater.py            자동 업데이트(git/ZIP, 테스트가능)
  safety.py             원본 보호 게이트 (2중 보호)
  models.py             도메인 모델
  scanner.py            폴더 스캔 + 좌표 출처 판별 + 폴더 레벨 분류(classify_selection)
  matcher.py            die(±1)·좌표 매칭 + layer 간 정합오차(median) 보정
  layout.py             layer 정규화 + 그리드 배치
  thumbnails.py         중앙 10% 썸네일 캐시
  workers.py            백그라운드 스캔/썸네일(병렬)
  parsers/              camtek_filename · camtek_ini · kla_info
  export/excel_report.py  Excel 출력(메모 포함)
  ui/                   theme · main_window · thumbnail_strip · compare_grid · controls
                        widgets · image_loader · image_viewer · notifications · settings_dialog
                        wafer_map · compare_overlay · help_dialog · splash · flow_layout
tools/make_sample_data.py  합성 데이터 생성기
tools/build_single_file.py 단일 파일 배포본 생성기(app/ + main.py → single_file/defect_tracker.py)
single_file/            생성된 단일 파일 배포본(산출물)
tests/                  pytest
```
