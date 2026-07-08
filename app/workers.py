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

_log = logging.getLogger("defect_tracker.workers")

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
        self._cancelled = False

    def cancel(self) -> None:
        """협조적 취소 — 다음 wafer 처리 지점에서 스캔 루프가 멈춘다."""
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        try:
            def cb(msg: str, cur: int, total: int) -> None:
                self.signals.progress.emit(msg, cur, total)

            index: LotIndex = scanner.scan_lot(
                self.lot_path, progress=cb, cancel_check=lambda: self._cancelled
            )
            if self._cancelled:
                return  # 중단된 결과는 UI 로 보내지 않는다(토큰 게이트와 이중 안전)
            self.signals.finished.emit(index)
        except Exception as exc:  # noqa: BLE001 - 워커는 모든 예외를 UI 로 전달
            _log.exception("스캔 워커 실패: %s", self.lot_path)
            self.signals.error.emit(str(exc))


class ThumbnailSignals(QObject):
    ready = Signal(int, str)  # index, thumbnail path
    done = Signal()


class ThumbnailWorker(QRunnable):
    """기준 record 들의 중앙 crop 썸네일을 백그라운드에서 생성한다(확대율은 center_ratio)."""

    def __init__(self, cache, items: list[tuple[int, Path]], center_ratio: float | None = None):
        super().__init__()
        self.cache = cache
        self.items = items
        self.center_ratio = center_ratio
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
                if self.center_ratio is not None:
                    thumb = self.cache.get_center_thumbnail(path, self.center_ratio)
                else:
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


class MatchSignals(QObject):
    finished = Signal(object, object)  # matches(list[BaseDefectMatches]), offsets(dict)
    error = Signal(str)


class MatchWorker(QRunnable):
    """매칭(match_all_with_offsets + collapse_matches)을 백그라운드에서 수행한다.

    UI 스레드가 멈추지 않도록 무거운 2-패스 매칭 + 근접 클러스터링을 여기서 실행한다.
    die 인덱스(index/fail_index)는 UI 에서 만들어(캐시 재사용) 넘겨받는다.
    """

    def __init__(self, base_records, compare_layers, records_by_layer, tolerance,
                 index=None, fail_index=None, cluster_radius=None):
        super().__init__()
        self.base_records = base_records
        self.compare_layers = compare_layers
        self.records_by_layer = records_by_layer
        self.tolerance = tolerance
        self.index = index
        self.fail_index = fail_index
        self.cluster_radius = cluster_radius
        self.signals = MatchSignals()

    @Slot()
    def run(self) -> None:
        try:
            from app import matcher
            from app.clustering import collapse_matches

            all_matches, offsets = matcher.match_all_with_offsets(
                self.base_records, self.compare_layers, self.records_by_layer,
                self.tolerance, index=self.index, fail_index=self.fail_index,
            )
            if self.cluster_radius is not None:
                matches = collapse_matches(all_matches, self.cluster_radius)
            else:
                matches = collapse_matches(all_matches)
            self.signals.finished.emit(matches, offsets)
        except Exception as exc:  # noqa: BLE001 - 워커 예외는 UI 로 전달
            _log.exception("매칭 워커 실패")
            self.signals.error.emit(str(exc))


class AllLayersMatchSignals(QObject):
    progress = Signal(int, int)  # cur, total (layer 단위)
    finished = Signal(list)      # list[BaseDefectMatches]
    error = Signal(str)


class AllLayersMatchWorker(QRunnable):
    """모든 layer 를 각각 기준으로 매칭해, 어느 layer 에서든 매치된 defect 을 백그라운드에서 합친다.

    '기준 layer 없이 전체 매치'는 layer 수만큼 전체 매칭을 다시 도는 무거운 작업이라
    UI 스레드에서 돌리면 완료될 때까지 앱이 멈춘다 — MatchWorker 와 같은 이유로 백그라운드로 뺀다.
    """

    def __init__(self, layers, records_by_layer, records_for_layer, tolerance, wafer_filter=None):
        super().__init__()
        self.layers = layers
        self.records_by_layer = records_by_layer
        self.records_for_layer = records_for_layer
        self.tolerance = tolerance
        self.wafer_filter = wafer_filter
        self.signals = AllLayersMatchSignals()

    @Slot()
    def run(self) -> None:
        try:
            from app import matcher
            from app.clustering import collapse_matches

            total = len(self.layers)
            seen: set[str] = set()
            out = []
            for i, base_layer in enumerate(self.layers):
                self.signals.progress.emit(i, total)
                base_records = [r for r in self.records_for_layer(base_layer) if r.ok]
                if self.wafer_filter:
                    base_records = [r for r in base_records if r.wafer_id == self.wafer_filter]
                if base_records:
                    compare_layers = [lyr for lyr in self.layers if lyr != base_layer]
                    matches, _ = matcher.match_all_with_offsets(
                        base_records, compare_layers, self.records_by_layer, self.tolerance,
                    )
                    for m in collapse_matches(matches):
                        if any(r.is_match for r in m.results):
                            k = str(m.base.image_path)
                            if k not in seen:
                                seen.add(k)
                                out.append(m)
            self.signals.progress.emit(total, total)
            self.signals.finished.emit(out)
        except Exception as exc:  # noqa: BLE001 - 워커 예외는 UI 로 전달
            _log.exception("전체 layer 매치 워커 실패")
            self.signals.error.emit(str(exc))


class ExportSignals(QObject):
    progress = Signal(int, int)  # cur, total
    finished = Signal(str)       # output path
    error = Signal(str)


class ExportWorker(QRunnable):
    """Excel 출력을 백그라운드에서 수행한다(진행도 콜백 → progress 시그널)."""

    def __init__(self, kwargs: dict):
        super().__init__()
        self.kwargs = kwargs
        self.signals = ExportSignals()

    @Slot()
    def run(self) -> None:
        try:
            from app.export.excel_report import export_excel

            path = export_excel(
                progress=lambda c, t: self.signals.progress.emit(c, t), **self.kwargs
            )
            self.signals.finished.emit(str(path))
        except Exception as exc:  # noqa: BLE001 - 워커 예외는 UI 로 전달
            _log.exception("Excel 출력 워커 실패")
            self.signals.error.emit(str(exc))


class FullThumbSignals(QObject):
    ready = Signal(int)  # index (해당 썸네일 캐시 준비됨)
    done = Signal()


class FullThumbWorker(QRunnable):
    """전체 썸네일 캐시를 백그라운드에서 미리 굽는다(히트맵 상세 등 지연 로딩용).

    실제 QPixmap 세팅은 UI 스레드에서(ready 시그널 후), 여기서는 디코드+저장만 한다.
    """

    def __init__(self, thumb_cache, items):  # items: list[(index, image_path, px)]
        super().__init__()
        self.thumb_cache = thumb_cache
        self.items = items
        self.signals = FullThumbSignals()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        def _warm(item):
            i, path, px = item
            if self._cancelled:
                return None
            try:
                self.thumb_cache.get_full_thumbnail(path, max_size=px)
            except Exception:  # noqa: BLE001 - 개별 실패는 건너뛴다
                pass
            return i

        if self.items and self.thumb_cache is not None:
            workers = min(_THUMB_WORKERS, len(self.items))
            with ThreadPoolExecutor(max_workers=workers) as ex:
                for i in ex.map(_warm, self.items):
                    if self._cancelled:
                        break
                    if i is not None:
                        self.signals.ready.emit(i)
        self.signals.done.emit()
