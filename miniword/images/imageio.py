"""Blob → ImageData decoding, independent of the rendering device."""
import io
import logging
from collections import OrderedDict

log = logging.getLogger(__name__)


def decode(blob_data):
    """Decode image bytes → ImageData. Returns None on failure."""
    from .images import ImageData
    import cairocffi as cairo
    try:
        surface = cairo.ImageSurface.create_from_png(io.BytesIO(blob_data))
        return ImageData(surface, surface.get_width(), surface.get_height())
    except Exception:
        pass
    try:
        import wx
        # Failure is handled here (None); without LogNull wx would pop up
        # an "Unknown image data format." dialog.
        with wx.LogNull():
            img = wx.Image(io.BytesIO(blob_data), type=wx.BITMAP_TYPE_ANY)
        if not img.IsOk():
            raise ValueError("wx.Image reported IsOk=False")
        w, h  = img.GetWidth(), img.GetHeight()
        rgb   = img.GetData()
        bgra  = bytearray(w * h * 4)
        bgra[0::4] = rgb[2::3]
        bgra[1::4] = rgb[1::3]
        bgra[2::4] = rgb[0::3]
        bgra[3::4] = b'\xff' * (w * h)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        surface.get_data()[:] = bgra
        surface.mark_dirty()
        return ImageData(surface, w, h)
    except Exception:
        log.warning("Failed to decode image", exc_info=True)
        return None


class DecodedCache:
    """Application-wide LRU cache of decoded images: {content (bytes):
    ImageData or None}. Bounded by memory, not by number: the decoded
    pixels (4 bytes each) plus the content, which the key keeps alive.
    The least recently used entries are dropped beyond limit; the newest
    entry always stays. Failed decodes are cached as None."""

    def __init__(self, limit):
        self.limit = limit
        self.entries = OrderedDict()
        self.size = 0

    @staticmethod
    def _size(content, data):
        pixels = 4 * data.width_px * data.height_px if data else 0
        return len(content) + pixels

    def get(self, content):
        try:
            data = self.entries[content]
        except KeyError:
            data = decode(content)  # module global: tests may patch it
            self.entries[content] = data
            self.size += self._size(content, data)
            while self.size > self.limit and len(self.entries) > 1:
                old, old_data = self.entries.popitem(last=False)
                self.size -= self._size(old, old_data)
        else:
            self.entries.move_to_end(content)
        return data

    def clear(self):
        self.entries.clear()
        self.size = 0


DECODED_LIMIT = 256 * 1024 * 1024
decoded_cache = DecodedCache(DECODED_LIMIT)


def decode_cached(content):
    """ImageData for image content via the application-wide LRU
    (decoded_cache), decoding on first use. Equal content in different
    bytes objects shares one entry (bytes compare by value). None for no
    content or content that can't be decoded."""
    if content is None:
        return None
    return decoded_cache.get(content)


def crop_surface(surface, cx, cy, cw, ch):
    """Return a new ImageSurface containing only the (cx, cy, cw, ch) region."""
    import cairocffi as cairo
    dst = cairo.ImageSurface(cairo.FORMAT_ARGB32, cw, ch)
    ctx = cairo.Context(dst)
    ctx.set_source_surface(surface, -cx, -cy)
    ctx.paint()
    return dst
