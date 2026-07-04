"""애플리케이션 로깅 설정 (관측성).

실데이터 환경(네트워크 경로, 다양한 자재 폴더)에서 발생하는 문제를 사후에 진단할 수
있도록 파일 로그를 남긴다. 로그는 항상 지정된 로그 디렉터리(원본 폴더 밖)에만 기록한다.

  - 콘솔: WARNING 이상(개발/터미널 실행 시)
  - 파일: DEBUG 이상, `<log_dir>/conder.log` (회전: 25MB×5)

원본 보호 원칙에 따라 로그 파일은 절대 원본 LOT 폴더에 쓰지 않는다.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_CONFIGURED = False
_ROOT_NAME = "conder"
_MAX_LOG_SIZE = 25 * 1024 * 1024  # 25 MB


def get_logger(name: str = _ROOT_NAME) -> logging.Logger:
    """`conder.*` 네임스페이스 로거를 반환한다."""
    if name == _ROOT_NAME or name.startswith(_ROOT_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_ROOT_NAME}.{name}")


def setup_logging(log_dir: Optional[Path] = None, level: int = logging.DEBUG) -> logging.Logger:
    """루트 `conder` 로거를 1회 구성한다(중복 핸들러 방지).

    log_dir 이 주어지고 쓰기 가능하면 회전 파일 핸들러를 그 디렉터리에 바로 추가한다
    (하위에 별도 "logs" 폴더를 만들지 않음 — 호출자가 최종 로그 디렉터리를 넘긴다).
    파일 핸들러 설치에 실패해도(권한 등) 콘솔 로깅은 유지하며 예외를 던지지 않는다.
    """
    global _CONFIGURED
    logger = logging.getLogger(_ROOT_NAME)
    logger.setLevel(level)
    logger.propagate = False

    if not _CONFIGURED:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.WARNING)
        console.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
        logger.addHandler(console)
        _CONFIGURED = True

    if log_dir is not None:
        _attach_file_handler(logger, Path(log_dir))

    return logger


def _has_file_handler(logger: logging.Logger) -> bool:
    return any(isinstance(h, RotatingFileHandler) for h in logger.handlers)


def _attach_file_handler(logger: logging.Logger, log_dir: Path) -> None:
    if _has_file_handler(logger):
        return
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / "conder.log",
            maxBytes=_MAX_LOG_SIZE,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(handler)
        logger.info("로깅 시작 (log_dir=%s)", log_dir)
    except OSError:
        # 파일 로깅 실패는 치명적이지 않다(콘솔 로깅 유지).
        logger.warning("로그 파일 핸들러를 설치하지 못했습니다: %s", log_dir)
