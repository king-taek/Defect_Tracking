# Defect Tracker — 개발 지침

반도체 defect 이미지 비교 뷰어(PySide6 데스크톱 앱). 기준 layer 의 defect 위치를 기준으로
다른 layer 에서 같은 위치의 defect 를 찾아 비교하고 결과를 Excel 로 출력한다.

## 절대 원칙
- **원본 read-only**: 스캔 대상(자재/LOT) 폴더에는 어떤 것도 쓰지 않는다. 모든 산출물
  (캐시·결과·로그·세션·진단)은 워크스페이스(`AppSettings.workspace`, 기본
  `%LOCALAPPDATA%\DefectTracker` / `~/DefectTracker`)에만 저장한다.
- 순수 로직(파서/매처/정합/진단/버전)은 UI 와 분리하고 단위 테스트로 못 박는다.

## 버전 규칙 (중요 — 세션이 바뀌어도 반드시 지킬 것)
`app/__init__.py` 의 `__version__` 은 **손으로 고정하지 말고** git 이력에서 계산한다.
규칙: `1.{MINOR}.{PATCH}` — MINOR = 변경 라인 ≥200 인 "큰 커밋" 수, PATCH = 전체 커밋 수
(+워킹트리 변경 시 1, 곧 만들 커밋 반영).

**app 코드(`app/`, `main.py`)를 변경해 커밋하기 직전에 반드시 실행한다:**

```
python tools/compute_version.py --write
```

그 결과로 갱신된 `app/__init__.py` 를 같은 커밋에 포함한다. (런타임에 git 을 호출하지
않으므로 시작 속도에 영향 없음. 자동 업데이트는 커밋 SHA 로 비교하므로 버전 표기 형식은
업데이트 로직과 무관하다.) 계산 로직은 `tools/compute_version.py` 참고.

## 테스트
```
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q
```
UI 는 오프스크린 스모크, 순수 로직은 단위 테스트로 검증한다. 새 동작은 회귀 테스트 동반.

## Git 워크플로
- **현재 체크아웃된 작업 브랜치**(세션/작업마다 다름)에서 개발 → 테스트 통과 후 `main` 으로
  fast-forward 머지 → push. 기능 단위로 커밋한다. (브랜치 이름을 여기 고정하지 않는다 —
  새 브랜치로 옮겨도 이 규칙이 그대로 적용되도록.)
- 기밀(고객 디바이스 좌표가 담긴 `Origin/*.xlsx`, `*.xlsm`)은 커밋 금지(.gitignore 유지).
  외부 `AOIDeviceDB.xlsx` 는 런타임에만 읽고 저장소에 포함하지 않는다.
