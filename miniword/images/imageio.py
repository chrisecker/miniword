"""Blob → ImageData decoding, independent of the rendering device."""
import io
import logging
import os
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


# Application-wide LRU cache of decoded images, oldest entry first:
# {content (bytes): ImageData or None}. Bounded by memory, not by number:
# the decoded pixels (4 bytes each) plus the content the key keeps alive.
DECODED_LIMIT = 256 * 1024 * 1024
decoded = OrderedDict()


def _entry_size(content, data):
    return len(content) + (4 * data.width_px * data.height_px if data else 0)


def decode_cached(content):
    """ImageData for image content via the application-wide LRU (decoded),
    decoding on first use. Equal content in different bytes objects shares
    one entry. None for no content or content that can't be decoded (cached
    as well). Beyond DECODED_LIMIT the least recently used entries are
    dropped; the newest one always stays."""
    if content is None:
        return None
    if content in decoded:
        decoded.move_to_end(content)
        return decoded[content]
    data = decoded[content] = decode(content)  # module global: tests patch it
    size = sum(_entry_size(c, d) for c, d in decoded.items())
    while size > DECODED_LIMIT and len(decoded) > 1:
        size -= _entry_size(*decoded.popitem(last=False))
    return data


# Application-wide cache of external images (linked by path or URL):
# {(absolute path, mtime) or URL: bytes}. Local files are read on demand
# (a changed file anew), URLs only by load_url - never while laying out.
external = {}


def external_content(path, base_dir=''):
    """The data of a linked image: a local file (relative to base_dir),
    read on demand, or a URL loaded before (load_url); else None."""
    from .images import fetch_image
    if path.startswith(('http://', 'https://')):
        return external.get(path)
    path = os.path.join(base_dir, path)
    try:
        key = os.path.abspath(path), os.path.getmtime(path)
    except OSError:
        return None
    if key not in external:
        external[key] = fetch_image(path)
    return external[key]


def load_url(url):
    """Load an image from the web into the cache; whether it worked."""
    from .images import fetch_image
    data = fetch_image(url)
    if data:
        external[url] = data
    return bool(data)


def crop_surface(surface, cx, cy, cw, ch):
    """Return a new ImageSurface containing only the (cx, cy, cw, ch) region."""
    import cairocffi as cairo
    dst = cairo.ImageSurface(cairo.FORMAT_ARGB32, cw, ch)
    ctx = cairo.Context(dst)
    ctx.set_source_surface(surface, -cx, -cy)
    ctx.paint()
    return dst
