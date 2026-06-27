"""백그라운드 작업 (문서 Section 10 성능 요구사항).

스캔/썸네일 생성은 QThreadPool 워커에서 수행하여 UI 멈춤을 최소화한다.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app import scanner
from app.scanner import LotIndex

_log = logging.getLogger("conder.workers")

# 썸네일 생성 병렬 워커 수(이미지 디코드+I/O 혼합).
_THUMB_WORKERS = max(2, min(8, (os.cpu_count() or 4)))


class ScanSignals(QObject):
    progress = Signal(str, int, int)  # message, current, total
    finished = Signal(object)  # LotIndex
    error = Signal(str)


class ScanWorker(QRunnable):
    """LOT 폴더를 백그라운드에서 스캔한다."""

    def __init__(self, lot_path: str | Path):
        super().__init__()
        self.lot_path = lot_path
        self.signals = ScanSignals()

    @Slot()
    def run(self) -> None:
        try:
            def cb(msg: str, cur: int, total: int) -> None:
                self.signals.progress.emit(msg, cur, total)

            index: LotIndex = scanner.scan_lot(self.lot_path, progress=cb)
            self.signals.finished.emit(index)
        except Exception as exc:  # noqa: BLE001 - 워커는 모든 예외를 UI 로 전달
            _log.exception("스캔 워커 실패: %s", self.lot_path)
            self.signals.error.emit(str(exc))


class ThumbnailSignals(QObject):
    ready = Signal(int, str)  # index, thumbnail path
    done = Signal()


class ThumbnailWorker(QRunnable):
    """기준 record 들의 중앙 10% 썸네일을 백그라운드에서 생성한다."""

    def __init__(self, cache, items: list[tuple[int, Path]]):
        super().__init__()
        self.cache = cache
        self.items = items
        self.signals = ThumbnailSignals()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        def _make(item: tuple[int, Path]):
            index, path = item
            if self._cancelled:
                return None
            try:
                thumb = self.cache.get_center_thumbnail(path)
            except Exception:  # noqa: BLE001 - 개별 실패는 건너뛴다
                _log.exception("썸네일 생성 실패: %s", path)
                return None
            return (index, thumb)

        if self.items:
            workers = min(_THUMB_WORKERS, len(self.items))
            with ThreadPoolExecutor(max_workers=workers) as ex:
                for result in ex.map(_make, self.items):
                    if self._cancelled:
                        break
                    if result is not None and result[1] is not None:
                        self.signals.ready.emit(result[0], str(result[1]))
        self.signals.done.emit()
