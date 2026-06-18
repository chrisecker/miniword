"""Blob → ImageData decoding, independent of the rendering device."""
import io
import logging

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


def crop_surface(surface, cx, cy, cw, ch):
    """Return a new ImageSurface containing only the (cx, cy, cw, ch) region."""
    import cairocffi as cairo
    dst = cairo.ImageSurface(cairo.FORMAT_ARGB32, cw, ch)
    ctx = cairo.Context(dst)
    ctx.set_source_surface(surface, -cx, -cy)
    ctx.paint()
    return dst
