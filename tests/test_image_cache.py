import asyncio
import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from PIL import Image

import core.cache as cache


class _AsyncResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def read(self):
        image_bytes = io.BytesIO()
        Image.new("RGB", (12, 12), (1, 2, 3)).save(image_bytes, format="PNG")
        return image_bytes.getvalue()


class _Twitch:
    def __init__(self):
        self.calls = 0

    def request(self, method, url):
        self.calls += 1
        return _AsyncResponse()


class _Manager:
    def __init__(self):
        self._root = object()
        self._twitch = _Twitch()


class _BrokenCachedImage:
    size = (12, 12)

    def load(self):
        raise OSError("truncated cached image")


class _BrokenResizeImage:
    size = (8, 8)

    def resize(self, size, resample):
        raise OSError("broken image data")


class ImageCacheTests(unittest.TestCase):
    def test_corrupt_cached_image_is_refetched(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            manager = _Manager()

            real_open = cache.Image_module.open

            def open_image(path_or_stream):
                if isinstance(path_or_stream, io.BytesIO):
                    return real_open(path_or_stream)
                return _BrokenCachedImage()

            captured = []

            with (
                mock.patch.object(cache, "CACHE_PATH", temp_path),
                mock.patch.object(cache, "CACHE_DB", temp_path / "cache.json"),
                mock.patch.object(cache.Image_module, "open", side_effect=open_image),
                mock.patch.object(
                    cache,
                    "PhotoImage",
                    side_effect=lambda master, image: captured.append(image) or image,
                ),
            ):
                image_cache = cache.ImageCache(manager)
                img_hash = cache.ImageHash("cached.png")
                image_cache._hashes["https://example.test/image.png"] = {
                    "hash": img_hash,
                    "expires": datetime.now(timezone.utc),
                }
                (temp_path / img_hash).write_bytes(b"not real image data")

                result = asyncio.run(
                    image_cache.get("https://example.test/image.png")
                )

            self.assertEqual(manager._twitch.calls, 1)
            self.assertIs(result, captured[0])
            self.assertNotIsInstance(captured[0], _BrokenCachedImage)

    def test_resize_error_uses_blank_placeholder(self):
        image_cache = object.__new__(cache.ImageCache)
        image_cache._root = object()
        image_cache._twitch = _Twitch()
        image_cache._lock = asyncio.Lock()
        image_cache._photos = {}
        image_cache._altered = False

        img_hash = cache.ImageHash("broken.png")
        image_cache._hashes = {
            "https://example.test/broken.png": {
                "hash": img_hash,
                "expires": datetime.now(timezone.utc),
            }
        }
        image_cache._images = {img_hash: _BrokenResizeImage()}
        blank = Image.new("RGB", (16, 16), (255, 255, 255))
        captured = []

        with (
            mock.patch.object(cache.Image_module, "new", return_value=blank),
            mock.patch.object(
                cache,
                "PhotoImage",
                side_effect=lambda master, image: captured.append(image) or image,
            ),
        ):
            result = asyncio.run(
                image_cache.get("https://example.test/broken.png", (16, 16))
            )

        self.assertIs(result, blank)
        self.assertEqual(captured, [blank])


if __name__ == "__main__":
    unittest.main()
