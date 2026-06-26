"""좌표 파싱/변환 모듈 (문서 Section 13).

세 경로 모두 최종적으로 col_row_x_y 위치 정보를 만든다:
  - camtek_filename : Camtek 파일명에 이미 포함된 좌표 직접 추출
  - camtek_ini      : ColorImageGrabingInfo.ini 기반 좌표 산출
  - kla_info        : KLA .001 info 파일 기반 좌표 변환
"""
