import wx
import wx.lib.wxcairo as wxcairo
import cairo
import time


from ..core.units import mm, cm, pt, inch
from ..wxtextview.cache import LRUCache


# Minimal set of properties required for the device to function
defaultstyle = dict(
    font_size=10, bgcolor='white', color='black',
    underline=False, font_family='Arial', italic=False, bold=False)


def filled(style, defaultstyle=defaultstyle):
    """Fill missing properties with default values."""
    new = defaultstyle.copy()
    new.update(style)
    return new


def set_font(ctx, style):
    slant = {
        False: cairo.FONT_SLANT_NORMAL,
        True:  cairo.FONT_SLANT_ITALIC,
    }[style['italic']]
    weight = {
        False: cairo.FONT_WEIGHT_NORMAL,
        True:  cairo.FONT_WEIGHT_BOLD,
    }[style['bold']]
    ctx.select_font_face(style['font_family'], slant, weight)
    ctx.set_font_size(style['font_size'])

    color = wx.Colour(style['color'])
    ctx.set_source_rgba(
        color.Red()   / 255,
        color.Green() / 255,
        color.Blue()  / 255,
        color.Alpha() / 255,
    )


class CairoDevice:
    zoom = 1.0
    buffering = True
    t0 = 0  # time since last movement

    def __init__(self):
        self._cache = LRUCache(1000)
        self._image_cache = {}   # id(blob_data) → (surface, w, h)
        self._temp_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        self._temp_ctx = cairo.Context(self._temp_surface)
        fo = cairo.FontOptions()
        fo.set_hint_style(cairo.HINT_STYLE_NONE)
        fo.set_hint_metrics(cairo.HINT_METRICS_OFF)
        self._temp_ctx.set_font_options(fo)
        self.reset_blink()

    def clear_caches(self):
        self._cache.clear()
        self._image_cache.clear()

    def reset_blink(self):
        self._blink_reference_time = time.time()

    def create_painter(self, dc):
        ctx = wxcairo.ContextFromDC(dc)

        if not ctx:
            raise RuntimeError("Failed to create Cairo context.")

        # Apply zoom scaling directly in Cairo
        ctx.scale(self.zoom, self.zoom)

        # Disable hinting for linear scaling
        fo = cairo.FontOptions()
        fo.set_hint_style(cairo.HINT_STYLE_NONE)
        fo.set_hint_metrics(cairo.HINT_METRICS_OFF)
        ctx.set_font_options(fo)
        return ctx

    def create_pdf_painter(self, filename, width, height):
        surface = cairo.PDFSurface(filename, width, height)
        context = cairo.Context(surface)
        return context

    def set_style(self, style, ctx):
        _style = filled(style)
        set_font(ctx, _style)
        self._current_underline = _style.get('underline', False)
        self._current_bgcolor = _style.get('bgcolor', 'white')

    def measure(self, text, style):
        key = (text, tuple(sorted(style.items())))
        try:
            return self._cache.get(key)
        except KeyError:
            pass

        ctx = self._temp_ctx
        _style = filled(style)
        set_font(ctx, _style)

        extents = ctx.text_extents(text)
        xb, yb, w, h, xa, ya = extents
        fe = ctx.font_extents()
        ascent  = fe[0]  # distance baseline -> top (positive value)
        descent = fe[1]  # distance baseline -> bottom (positive value)
        line_h  = fe[2]  # recommended line height (ascent + descent
                         # + internal leading)
        result = (xa, line_h, descent)

        self._cache.set(key, result)
        return result

    def measure_parts(self, text, style):
        """
        Measure partial text extents in PT.
        Returns list of cumulative widths for each character.
        """
        ctx = self._temp_ctx
        _style = filled(style)
        set_font(ctx, _style)
        widths = []
        for i in range(1, len(text) + 1):
            extents = ctx.text_extents(text[:i])
            widths.append(extents[4])
        return widths

    def intersects(self, ctx, rect):
        """
        Check if rect (in PT) intersects with the current Cairo clip region.
        """
        x1, y1, x2, y2 = rect.items()

        # clip_extents() returns (x1, y1, x2, y2) in current coordinates
        # (PT). Cairo already incorporates the ctx.scale(zoom) here.
        c_x1, c_y1, c_x2, c_y2 = ctx.clip_extents()

        # Check for overlap
        if (x2 < c_x1 or x1 > c_x2 or
                y2 < c_y1 or y1 > c_y2):
            return False

        return True

    def draw_underline(self, x, y, width, ctx):
        fe = ctx.font_extents()
        line_h  = fe[2]
        descent = fe[1]
        ul_y      = y + line_h + descent * 0.3
        thickness = max(0.5, descent * 0.1)
        ctx.rectangle(x, ul_y, width, thickness)
        ctx.fill()

    def draw_strings(self, strings, x, y, spacing, ctx):
        """Draw a list of strings at consecutive horizontal positions.

        strings: list of str
        spacing: horizontal gap between consecutive strings (PT)

        Renders bgcolor as one merged rectangle and underline as one
        continuous line across all strings and the gaps between them.
        """
        if not strings:
            return

        fe = ctx.font_extents()
        line_h  = fe[2]
        descent = fe[1]

        # Measure each string and compute starting x positions
        positions = []   # (text, tx, advance_width)
        cur_x = x
        for text in strings:
            xa = ctx.text_extents(text)[4]
            positions.append((text, cur_x, xa))
            cur_x += xa + spacing

        # Total span: covers all strings and the inter-string gaps,
        # but not a trailing gap after the last string.
        total_width = cur_x - spacing - x

        # 1. Draw bgcolor as one block
        bgcolor = getattr(self, '_current_bgcolor', 'white')
        if wx.Colour(bgcolor) != wx.WHITE:
            c = wx.Colour(bgcolor)
            ctx.save()
            ctx.set_source_rgba(
                c.Red()   / 255,
                c.Green() / 255,
                c.Blue()  / 255,
                c.Alpha() / 255,
            )
            ctx.rectangle(x, y, total_width, line_h + descent)
            ctx.fill()
            ctx.restore()

        # 2. Draw all text strings
        for text, tx, _ in positions:
            ctx.move_to(tx, y + line_h)
            ctx.show_text(text)

        # 3. Draw underline as one continuous line
        if getattr(self, '_current_underline', False):
            self.draw_underline(x, y, total_width, ctx)

    def draw_text(self, text, x, y, ctx):
        # Cairo draws text from the baseline upward.
        # If y is the top edge, y_bearing must be added.
        extents = ctx.text_extents(text)
        xb, yb, w, h, xa, ya = extents

        fe = ctx.font_extents()
        ascent  = fe[0]  # distance baseline -> top (positive value)
        descent = fe[1]  # distance baseline -> bottom (positive value)
        line_h  = fe[2]  # recommended line height (ascent + descent
                         # + internal leading)
        bgcolor = getattr(self, '_current_bgcolor', 'white')
        if wx.Colour(bgcolor) != wx.WHITE:
            c = wx.Colour(bgcolor)
            ctx.save()
            ctx.set_source_rgba(
                c.Red()   / 255,
                c.Green() / 255,
                c.Blue()  / 255,
                c.Alpha() / 255,
            )
            ctx.rectangle(x, y, xa, line_h + descent)
            ctx.fill()
            ctx.restore()

        ctx.move_to(x, y + line_h)
        ctx.show_text(text)
        if getattr(self, '_current_underline', False):
            self.draw_underline(x, y, xa, ctx)

    def draw_rect(self, x, y, w, h, ctx):
        ctx.set_source_rgb(0.7, 0.7, 0.7)
        ctx.set_line_width(1.0 / self.zoom)  # constant line width
                                             # regardless of zoom
        ctx.rectangle(x, y, w, h)
        ctx.stroke()

    def fill_rect(self, x, y, w, h, color, ctx):
        c = wx.Colour(color)
        ctx.set_source_rgba(
            c.Red()   / 255,
            c.Green() / 255,
            c.Blue()  / 255,
            c.Alpha() / 255,
        )
        ctx.rectangle(x, y, w, h)
        ctx.fill()

    def draw_line(self, x1, y1, x2, y2, width, ctx):
        ctx.set_source_rgb(0, 0, 0)
        ctx.set_line_width(width / self.zoom)
        ctx.move_to(x1, y1)
        ctx.line_to(x2, y2)
        ctx.stroke()

    def draw_blinkingrect(self, x, y, w, h, ctx):
        elapsed = time.time() - self._blink_reference_time
        if not int(elapsed * 2) % 2:
            color = wx.BLACK
        else:
            color = wx.WHITE
        c = wx.Colour(color)
        ctx.set_source_rgba(
            c.Red()   / 255,
            c.Green() / 255,
            c.Blue()  / 255,
            c.Alpha() / 255,
        )
        ctx.rectangle(x, y, w, h)
        ctx.fill()

    def invert_rect(self, x, y, w, h, ctx):
        """
        Draw a semi-transparent selection rectangle
        in PT coordinates using Cairo.
        """
        r, g, b, a = 83, 97, 220, 50
        ctx.set_source_rgba(r / 255.0, g / 255.0, b / 255.0, a / 255.0)
        ctx.rectangle(x, y, w, h)
        ctx.fill()

    def load_image(self, blob_data):
        """Decode blob_data → (cairo.ImageSurface, width, height).

        Returns (None, 0, 0) if decoding fails.
        Decoded surfaces are cached by object identity of blob_data.
        """
        key = id(blob_data)
        if key in self._image_cache:
            return self._image_cache[key]
        result = self._decode_image(blob_data)
        self._image_cache[key] = result
        return result

    def _decode_image(self, blob_data):
        import io
        # PNG: native pycairo support
        try:
            surface = cairo.ImageSurface.create_from_png(io.BytesIO(blob_data))
            return surface, surface.get_width(), surface.get_height()
        except Exception:
            pass
        # JPEG / other formats: via Pillow
        try:
            from PIL import Image as PILImage
            import numpy as np
            img = PILImage.open(io.BytesIO(blob_data)).convert('RGBA')
            w, h = img.size
            arr = np.array(img)
            # Cairo ARGB32 stores bytes as B, G, R, A (little-endian)
            bgra = np.ascontiguousarray(arr[:, :, [2, 1, 0, 3]])
            surface = cairo.ImageSurface.create_for_data(
                bytearray(bgra), cairo.FORMAT_ARGB32, w, h, w * 4)
            return surface, w, h
        except Exception:
            pass
        return None, 0, 0

    def draw_bitmap(self, bitmap, x, y, width, height, ctx):
        """Draw a cairo.ImageSurface scaled to (width, height) at (x, y)."""
        if bitmap is None:
            return
        src_w = bitmap.get_width()
        src_h = bitmap.get_height()
        if src_w == 0 or src_h == 0:
            return
        ctx.save()
        ctx.translate(x, y)
        ctx.scale(width / src_w, height / src_h)
        ctx.set_source_surface(bitmap, 0, 0)
        ctx.paint()
        ctx.restore()

    def crop_image_surface(self, surface, cx, cy, cw, ch):
        """Return a new ImageSurface containing only the (cx, cy, cw, ch) region."""
        import cairo
        dst = cairo.ImageSurface(cairo.FORMAT_ARGB32, cw, ch)
        ctx = cairo.Context(dst)
        ctx.set_source_surface(surface, -cx, -cy)
        ctx.paint()
        return dst


def eq(a, b, delta=1e-2):
    """Check whether float values a and b are equal within delta."""
    return abs(a - b) <= delta


def test_00():
    app = wx.App(False)
    device = CairoDevice()
    metrics = device.measure('M', defaultstyle)
    assert metrics == (8.330078125, 11.4990234375, 2.119140625)


def test_01():
    app = wx.App(False)
    dc = wx.MemoryDC()

    # MapMode should be 1 (MM_TEXT)
    assert dc.GetMapMode() == 1
    gc = wx.GraphicsContext.Create(dc)

    ppi_x, ppi_y = dc.GetPPI()
    if ppi_x == 0:
        ppi_x, ppi_y = wx.GetDisplayPPI()
    assert ppi_x == 96
    assert ppi_y == 96

    font = wx.Font(
        12, wx.FONTFAMILY_SWISS,
        wx.FONTSTYLE_NORMAL,
        wx.FONTWEIGHT_NORMAL,
    )

    gc = wx.GraphicsContext.Create(dc)
    gc.SetFont(font, wx.BLACK)

    CM_TO_POINTS = 72.0 / 2.54
    text = "Hello wxPrint (Points)"

    w, h, descent, ext_leading = gc.GetFullTextExtent(text)
    ascent = h - descent

    # Expected: w ≈ 163, h ≈ 23
    assert eq(w, 163)
    assert eq(h, 23)

    # Expected in cm: w ≈ 5.75, h ≈ 0.81
    assert eq(w / CM_TO_POINTS, 5.75)
    assert eq(h / CM_TO_POINTS, 0.81)


def test_02():
    """Computing text extent."""
    # Tests wx functionality. It is still unclear whether font size
    # measurement works reliably across all platforms. If this test
    # passes, behaviour is as expected.

    app = wx.App(False)

    dc = wx.MemoryDC()
    gc = wx.GraphicsContext.Create(dc)

    font = wx.Font(
        12, wx.FONTFAMILY_SWISS,
        wx.FONTSTYLE_NORMAL,
        wx.FONTWEIGHT_NORMAL,
    )

    gc = wx.GraphicsContext.Create(dc)
    gc.SetFont(font, wx.BLACK)

    CM_TO_POINTS = 72.0 / 2.54
    text = "0123456789" * 6

    width, totalheight, descent, ext_leading = gc.GetFullTextExtent(text)
    assert width == 540
    assert totalheight == 23
    assert descent == 5
    height = totalheight - descent

    width_cm  = width  / CM_TO_POINTS
    height_cm = height / CM_TO_POINTS
    assert eq(width_cm, 19.05)
    assert eq(height_cm, 0.635)

    device = CairoDevice()
    width, height, depth = device.measure(text, defaultstyle)
    assert abs(width  - 333.69) < 1e-2
    assert abs(height -  11.50) < 1e-2
    assert abs(depth  -   2.12) < 1e-2


def draw_testimage(device, gc, verbose=False):
    if verbose:
        debug = print
    else:
        def debug(*args):
            pass

    style = {
        'font_family': 'Arial', 'font_size': 8, 'bold': False,
        'italic': False, 'underline': False, 'strike': False,
        'color': 'black',
    }
    device.set_style(style, gc)

    CM_TO_PT = 72.0 / 2.54
    text = " -23456789" * 6

    # Full text metrics
    w, h, d = device.measure(text, style)
    debug("Extent in pt:", w, h)

    # Start position (points, relative to page)
    x = 0.2 * 72
    baseline_y = 200
    top = baseline_y - h

    # Text + bounding box
    device.draw_rect(x, top, w, h, gc)
    device.draw_text(text, x, top, gc)

    text = (
        'Albert Einstein was a German-born theoretical physicist who'
        ' developed the theory'
    )
    w, h, d = device.measure(text, style)
    debug("w=", w)
    x = 0.2 * 72
    y = 100
    device.draw_text(text, x, y, gc)
    device.draw_rect(x, y, w, h + d, gc)

    # 5 x 10 cm box
    box_w = 5  * CM_TO_PT
    box_h = 10 * CM_TO_PT
    x = 72  # 1-inch margin
    y = 72
    label = "5 x 10 cm"
    device.draw_rect(x, y, box_w, box_h, gc)
    device.draw_text(label, x, y, gc)

    # Text metric
    text = 'joy Albert'
    style = style.copy()
    style['font_size'] = 32
    w, h, d = device.measure(text, style)
    x = 0.2 * 72
    y = 10 * CM_TO_PT  # ≈ 566 pt
    device.set_style(style, gc)
    device.draw_text(text, x, y, gc)
    device.draw_rect(x, y,     w, h, gc)
    device.draw_rect(x, y + h, w, d, gc)


class TestPrintout(wx.Printout):
    def __init__(self):
        super().__init__("wxPython Point Print Test")

    def OnPrintPage(self, page):
        dc = self.GetDC()
        if not dc:
            return False
        draw_testimage(dc)
        return True

    def HasPage(self, page):
        return page == 1

    def GetPageInfo(self):
        return (1, 1, 1, 1)


class TestPanel(wx.ScrolledWindow):
    def __init__(self, parent):
        super().__init__(parent)
        self.zoom = 1.0
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_MOUSEWHEEL, self.on_mousewheel)

        # A4 page in pixels at 96 dpi
        width_cm, height_cm = 21, 29.7
        dpi = 96
        self.base_width  = int(width_cm  / 2.54 * dpi)
        self.base_height = int(height_cm / 2.54 * dpi)

        # Set initial virtual size
        self.update_virtual_size()
        self.SetScrollRate(20, 20)

    def update_virtual_size(self):
        """Adjust virtual size to current zoom level."""
        self.SetVirtualSize((
            int(self.base_width  * self.zoom),
            int(self.base_height * self.zoom),
        ))

    def on_paint(self, evt):
        dc = wx.PaintDC(self)
        self.PrepareDC(dc)
        dc.Clear()
        print("Zoom:", self.zoom)
        dc.SetUserScale(self.zoom, self.zoom)
        device = CairoDevice()
        painter = device.create_painter(dc)
        draw_testimage(device, painter)

    def on_mousewheel(self, evt):
        rotation = evt.GetWheelRotation()
        if rotation > 0:
            self.zoom *= 1.1
        else:
            self.zoom /= 1.1
        # Clamp zoom to allowed range
        self.zoom = max(0.1, min(5.0, self.zoom))
        self.update_virtual_size()
        self.Refresh()
        self.Update()


class TestFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="wxPython Print Test", size=(400, 300))

        btn = wx.Button(self, label="Print…")
        btn.Bind(wx.EVT_BUTTON, self.on_print)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(btn, 0, wx.ALL | wx.CENTER, 20)

        panel = TestPanel(self)
        sizer.Add(panel, 1, wx.EXPAND | wx.ALL | wx.CENTER, 20)

        self.SetSizer(sizer)

    def on_print(self, event):
        # Render to PDF via Cairo
        device = CairoDevice()
        gc = device.create_pdf_painter("output.pdf", 595, 842)
        draw_testimage(device, gc)
        print("print done")


class TestApp(wx.App):
    def OnInit(self):
        frame = TestFrame()
        frame.Show()
        return True


def demo_00():
    # Goals:
    # - Verify that internal and external coordinates match.
    # - Verify that internal coordinates are self-consistent
    #   (box size vs. font size).
    #
    # Procedure:
    # - Print the output.
    # - Check that the digit sequence is tightly enclosed in its box.
    # - Check that the other box measures 5 x 10 cm.
    # - The digit box should be approx. 19.05 cm wide (see test_02).

    app = TestApp(True)
    printer = wx.Printer()
    printout = TestPrintout()
    app.MainLoop()

