"""썸네일 생성/캐시 (문서 Section 8.6, 10).

상단 썸네일은 사진 중앙 일부 구간(기본 10%)만 잘라 확대한 형태로 보여준다.
생성된 썸네일은 output workspace 내 cache 폴더에만 저장하며, 원본 폴더에는 쓰지 않는다.
캐시 키는 (원본 경로 + 크기 + mtime) 해시로 만들어 원본 변경 시 자동 갱신된다.

원본 이미지는 read-only 로만 읽는다.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Optional

from PIL import Image

from app import config
from app.safety import read_only_bytes


def _cache_key(path: Path, size: int, center_ratio: float, full: bool) -> str:
    try:
        stat = path.stat()
        sig = f"{path}|{stat.st_size}|{int(stat.st_mtime)}|{size}|{center_ratio}|{full}"
    except OSError:
        sig = f"{path}|{size}|{center_ratio}|{full}"
    return hashlib.sha1(sig.encode("utf-8")).hexdigest()


def _center_crop(img: Image.Image, ratio: float) -> Image.Image:
    """중앙 ratio 비율 영역을 잘라낸다 (사진 중앙 N% 확대용)."""
    w, h = img.size
    cw = max(1, int(w * ratio))
    ch = max(1, int(h * ratio))
    left = (w - cw) // 2
    top = (h - ch) // 2
    return img.crop((left, top, left + cw, top + ch))


class ThumbnailCache:
    """썸네일을 디스크 캐시에 저장하고 재사용한다."""

    def __init__(self, cache_dir: Path, size: int = config.THUMBNAIL_SIZE):
        self.cache_dir = Path(cache_dir)
        self.size = size
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.png"

    def get_center_thumbnail(
        self,
        image_path: str | Path,
        center_ratio: float = config.THUMBNAIL_CENTER_RATIO,
    ) -> Optional[Path]:
        """중앙 center_ratio 영역을 확대한 썸네일 경로를 반환(없으면 생성)."""
        return self._get(image_path, center_ratio=center_ratio, full=False)

    def get_full_thumbnail(
        self, image_path: str | Path, max_size: Optional[int] = None
    ) -> Optional[Path]:
        """이미지 전체를 축소한 미리보기 썸네일(Excel/그리드용)."""
        return self._get(image_path, center_ratio=1.0, full=True, max_size=max_size)

    def _get(
        self,
        image_path: str | Path,
        center_ratio: float,
        full: bool,
        max_size: Optional[int] = None,
    ) -> Optional[Path]:
        path = Path(image_path)
        target = max_size or self.size
        key = _cache_key(path, target, center_ratio, full)
        out = self._cache_path(key)
        if out.exists():
            return out
        try:
            data = read_only_bytes(path)
            with Image.open(io.BytesIO(data)) as img:
                img = img.convert("RGB")
                if not full and center_ratio < 1.0:
                    img = _center_crop(img, center_ratio)
                img.thumbnail((target, target), Image.LANCZOS)
                img.save(out, format="PNG")
            return out
        except (OSError, ValueError):
            return None
