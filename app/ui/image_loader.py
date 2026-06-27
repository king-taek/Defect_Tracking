"""비동기 이미지 로더 (문서 Section 10 — UI 멈춤 최소화).

비교 그리드의 원본 이미지를 네트워크 경로에서 동기로 읽으면 탐색 시 UI 가 멈춘다.
이 로더는 QThreadPool 워커에서 이미지를 읽어 디스플레이 크기로 축소한 뒤, 메모리 LRU
캐시에 보관한다. 같은 이미지를 다시 볼 때(이전/다음 왕복)는 캐시에서 즉시 표시된다.

원본 이미지는 QImageReader 의 읽기 전용 접근으로만 읽으며 원본을 수정하지 않는다.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Optional

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QImage, QImageReader


class _LoadSignals(QObject):
    done = Signal(int, str, object)  # request_id, path, QImage|None


class _LoadTask(QRunnable):
    def __init__(self, request_id: int, path: str, max_dim: int):
        super().__init__()
        self.request_id = request_id
        self.path = path
        self.max_dim = max_dim
        self.signals = _LoadSignals()

    @Slot()
    def run(self) -> None:
        image: Optional[QImage] = None
        try:
            reader = QImageReader(self.path)
            reader.setAutoTransform(True)
            size = reader.size()
            # 큰 이미지는 디코드 단계에서 축소하여 메모리/시간을 절약한다.
            if size.isValid() and max(size.width(), size.height()) > self.max_dim:
                scaled = size.scaled(
                    QSize(self.max_dim, self.max_dim), Qt.KeepAspectRatio
                )
                reader.setScaledSize(scaled)
            img = reader.read()
            if not img.isNull():
                image = img
        except Exception:  # noqa: BLE001 - 로드 실패는 placeholder 로 처리
            image = None
        self.signals.done.emit(self.request_id, self.path, image)


class ImageLoader(QObject):
    """비동기 이미지 로더 + LRU 캐시."""

    loaded = Signal(int, object)  # request_id, QImage|None

    def __init__(
        self,
        max_dim: int = 600,
        cache_size: int = 128,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._max_dim = max_dim
        self._cache_size = cache_size
        self._cache: "OrderedDict[str, QImage]" = OrderedDict()
        self._next_id = 0
        self._pool = QThreadPool.globalInstance()

    def request(self, path: str) -> int:
        """이미지 로드를 요청하고 request_id 를 반환. 결과는 loaded 시그널로 전달."""
        self._next_id += 1
        rid = self._next_id
        cached = self._cache.get(path)
        if cached is not None:
            self._cache.move_to_end(path)
            # 캐시 적중도 비동기로 통일 (호출 측이 동일 경로로 처리)
            QTimer.singleShot(0, lambda: self.loaded.emit(rid, cached))
            return rid
        task = _LoadTask(rid, path, self._max_dim)
        task.signals.done.connect(self._on_done)
        self._pool.start(task)
        return rid

    def prefetch(self, paths: list[str]) -> None:
        """탐색 체감 향상을 위해 인접 이미지를 미리 디코드해 캐시에 채운다.

        이미 캐시에 있으면 건너뛴다. 결과는 캐시에만 적재되고 loaded 시그널 소비자는
        request_id 로 자신과 무관한 결과를 무시하므로 UI 에 영향이 없다.
        """
        for path in paths:
            if not path or path in self._cache:
                continue
            task = _LoadTask(-1, path, self._max_dim)
            task.signals.done.connect(self._on_prefetched)
            self._pool.start(task)

    @Slot(int, str, object)
    def _on_prefetched(self, rid: int, path: str, image: object) -> None:
        if isinstance(image, QImage) and not image.isNull():
            self._cache[path] = image
            self._cache.move_to_end(path)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)

    @Slot(int, str, object)
    def _on_done(self, rid: int, path: str, image: object) -> None:
        if isinstance(image, QImage) and not image.isNull():
            self._cache[path] = image
            self._cache.move_to_end(path)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        self.loaded.emit(rid, image)

    def clear_cache(self) -> None:
        self._cache.clear()
