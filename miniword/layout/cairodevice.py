import sys
import wx
import wx.lib.wxcairo as wxcairo
try:
    import cairocffi as cairo
except ImportError:
    import cairo
import time
try:
    import uharfbuzz as hb
    _HB_AVAILABLE = True
except ImportError:
    _HB_AVAILABLE = False
    print(
        'Warning: uharfbuzz not found — complex-script shaping and font '
        'fallback disabled.  Install with: pip install uharfbuzz',
        file=sys.stderr,
    )


from ..core.units import mm, cm, pt, inch
from ..core.fontfinder import resolve_font_path, find_fallback_info, init_preload
from .cache import LRUCache

if _HB_AVAILABLE:
    init_preload()


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
    # On Windows, wx.BufferedDC is a memory DC and wxcairo.ContextFromDC()
    # cannot create a Cairo context from it.  Use the plain PaintDC instead
    # and rely on SetDoubleBuffered(True) on the widget for flicker-free drawing.
    buffering = sys.platform != 'win32'
    t0 = 0  # time since last movement

    def __init__(self):
        self._cache = LRUCache(1000)
        self._temp_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        self._temp_ctx = cairo.Context(self._temp_surface)
        self._temp_ctx.set_font_options(self._make_font_options())
        self._hb_fonts = {}
        self._fallback_fonts = {}  # (path, size) -> hb.Font
        self._current_style = defaultstyle
        self.reset_blink()

    @staticmethod
    def _make_font_options():
        fo = cairo.FontOptions()
        fo.set_hint_style(cairo.HINT_STYLE_NONE)
        fo.set_hint_metrics(cairo.HINT_METRICS_OFF)
        return fo

    def clear_caches(self):
        self._cache.clear()
        self._hb_fonts.clear()
        self._fallback_fonts.clear()

    def _get_hb_font(self, style):
        if not _HB_AVAILABLE:
            return None
        key = (style['font_family'], style['bold'], style['italic'], style['font_size'])
        if key in self._hb_fonts:
            return self._hb_fonts[key]
        path = resolve_font_path(style['font_family'], style['bold'], style['italic'])
        font = None
        if path:
            try:
                with open(path, 'rb') as f:
                    data = f.read()
                face = hb.Face(hb.Blob(data))
                font = hb.Font(face)
                font.scale = (int(style['font_size'] * 64), int(style['font_size'] * 64))
            except Exception:
                font = None
        self._hb_fonts[key] = font
        return font

    def _shape(self, text, hb_font):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(hb_font, buf)
        return buf.glyph_infos or [], buf.glyph_positions or []

    def _to_cairo_glyphs(self, infos, positions, x, y):
        glyphs = []
        cx, cy = x, y
        for info, pos in zip(infos, positions):
            glyphs.append((info.codepoint, cx + pos.x_offset / 64.0, cy - pos.y_offset / 64.0))
            cx += pos.x_advance / 64.0
            cy -= pos.y_advance / 64.0
        return glyphs

    def _get_fallback_hb_font(self, path, size):
        key = (path, size)
        if key in self._fallback_fonts:
            return self._fallback_fonts[key]
        try:
            with open(path, 'rb') as f:
                data = f.read()
            face = hb.Face(hb.Blob(data))
            font = hb.Font(face)
            font.scale = (int(size * 64), int(size * 64))
        except Exception:
            font = None
        self._fallback_fonts[key] = font
        return font

    def _shape_with_fallback(self, text, hb_font, size):
        """Shape text, replacing .notdef runs with glyphs from fallback fonts.

        Returns [(cairo_family_or_None, infos, positions), ...].
        cairo_family_or_None is None for the primary font, or the family name
        string for a fallback that needs a different Cairo font face.
        """
        infos, positions = self._shape(text, hb_font)
        if not any(info.codepoint == 0 for info in infos):
            return [(None, infos, positions)]

        runs = []   # [family_or_None, [infos], [positions]]
        n = len(infos)
        i = 0
        while i < n:
            if infos[i].codepoint != 0:
                j = i + 1
                while j < n and infos[j].codepoint != 0:
                    j += 1
                if runs and runs[-1][0] is None:
                    runs[-1][1].extend(infos[i:j])
                    runs[-1][2].extend(positions[i:j])
                else:
                    runs.append([None, list(infos[i:j]), list(positions[i:j])])
                i = j
            else:
                j = i + 1
                while j < n and infos[j].codepoint == 0:
                    j += 1
                text_start = infos[i].cluster
                text_end = infos[j].cluster if j < n else len(text)
                segment = text[text_start:text_end]

                family = None
                fb_infos, fb_pos = list(infos[i:j]), list(positions[i:j])
                if segment:
                    path, family = find_fallback_info(ord(segment[0]))
                    if path and family:
                        fb_font = self._get_fallback_hb_font(path, size)
                        if fb_font is not None:
                            fi, fp = self._shape(segment, fb_font)
                            fb_infos, fb_pos = list(fi), list(fp)
                        else:
                            family = None
                    else:
                        family = None

                if runs and runs[-1][0] == family:
                    runs[-1][1].extend(fb_infos)
                    runs[-1][2].extend(fb_pos)
                else:
                    runs.append([family, fb_infos, fb_pos])
                i = j

        return [(s, tuple(gi), tuple(gp)) for s, gi, gp in runs]

    def _render_runs(self, runs, x, baseline_y, ctx):
        cur_x = x
        for family, infos, pos in runs:
            if family is not None:
                ctx.save()
                set_font(ctx, {**self._current_style, 'font_family': family})
            glyphs = self._to_cairo_glyphs(infos, pos, cur_x, baseline_y)
            if glyphs:
                ctx.show_glyphs(glyphs)
            cur_x += sum(p.x_advance for p in pos) / 64.0
            if family is not None:
                ctx.restore()

    def reset_blink(self):
        self._blink_reference_time = time.time()

    def get_scale(self, dpi, zoom):
        if sys.platform == 'win32':
            return dpi / 72.0 * zoom
        return zoom

    def create_painter(self, dc, origin, zoom=1.0):
        ctx = wxcairo.ContextFromDC(dc)

        if not ctx:
            raise RuntimeError("Failed to create Cairo context.")

        # Apply scroll/centering offset in pixel space before scaling.
        # dc.SetDeviceOrigin() is ignored by Cairo on Windows (Win32 backend
        # renders directly into the pixel buffer, bypassing GDI transforms),
        # so the offset must be applied through Cairo's own transform.
        ox, oy = origin
        if ox or oy:
            ctx.translate(ox, oy)

        # On Windows, dc.GetPPI() returns the physical DPI and the app must
        # apply DPI scaling itself.  On Linux/macOS the display server already
        # applies physical scaling, so dc.GetPPI() returns the logical DPI (96)
        # and no extra factor is needed.
        if sys.platform == 'win32':
            _, ppi_y = dc.GetPPI()
            dpi = ppi_y if ppi_y > 0 else 96
            s = dpi / 72.0 * zoom
        else:
            s = zoom
        ctx.scale(s, s)

        ctx.set_font_options(self._make_font_options())
        if sys.platform == 'win32':
            ctx.set_antialias(cairo.ANTIALIAS_SUBPIXEL)
        return ctx

    def create_pdf_painter(self, filename, width, height):
        surface = cairo.PDFSurface(filename, width, height)
        context = cairo.Context(surface)
        return context

    def set_style(self, style, ctx):
        _style = filled(style)
        set_font(ctx, _style)
        set_font(self._temp_ctx, _style)
        self._current_underline = _style.get('underline', False)
        self._current_bgcolor = _style.get('bgcolor', 'white')
        self._current_style = _style

    def measure(self, text, style):
        key = (text, tuple(sorted(style.items())))
        try:
            return self._cache.get(key)
        except KeyError:
            pass

        ctx = self._temp_ctx
        _style = filled(style)
        set_font(ctx, _style)

        fe = ctx.font_extents()
        descent = fe[1]
        line_h  = fe[2]

        hb_font = self._get_hb_font(_style)
        if hb_font is not None:
            runs = self._shape_with_fallback(text, hb_font, _style['font_size'])
            xa = sum(sum(p.x_advance for p in pos) for _, _, pos in runs) / 64.0
        else:
            xa = ctx.text_extents(text)[4]

        result = (xa, line_h, descent)

        self._cache.set(key, result)
        return result

    def measure_parts(self, text, style):
        """Returns list of cumulative advance widths for each character prefix."""
        _style = filled(style)
        hb_font = self._get_hb_font(_style)
        if hb_font is not None:
            widths = []
            for i in range(1, len(text) + 1):
                runs = self._shape_with_fallback(text[:i], hb_font, _style['font_size'])
                widths.append(sum(sum(p.x_advance for p in pos) for _, _, pos in runs) / 64.0)
            return widths
        ctx = self._temp_ctx
        set_font(ctx, _style)
        return [ctx.text_extents(text[:i])[4] for i in range(1, len(text) + 1)]

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
        fe        = self._temp_ctx.font_extents()
        line_h    = fe[2]
        descent   = fe[1]
        ul_y      = y + line_h + descent * 0.3
        thickness = max(0.5, descent * 0.1)
        ctx.rectangle(x, ul_y, width, thickness)
        ctx.fill()

    def _snap_baseline(self, ctx, y):
        """Round y to the nearest device pixel (screen rendering only).

        On Windows, Cairo places glyphs at the exact (fractional) y position
        passed to move_to().  When the baseline falls at e.g. 5.3 px the
        anti-aliaser spreads the stroke across two rows with unequal weights,
        so thin horizontal strokes (top of 'T', crossbar of 'H', …) look
        thinner on some lines than on others.  Snapping to a whole pixel
        eliminates the inconsistency.

        Only applied on Windows and only for screen contexts (PDF surfaces are
        resolution-independent, so fractional positions are correct there).
        This does not affect any measurements or layout calculations.
        """
        if sys.platform != 'win32':
            return y
        _, dev_y = ctx.user_to_device(0, y)
        _, snapped = ctx.device_to_user(0, round(dev_y))
        return snapped

    def draw_strings(self, strings, x, y, spacing, ctx):
        """Draw a list of strings at consecutive horizontal positions.

        strings: list of str
        spacing: horizontal gap between consecutive strings (PT)

        Renders bgcolor as one merged rectangle and underline as one
        continuous line across all strings and the gaps between them.
        """
        if not strings:
            return

        fe      = self._temp_ctx.font_extents()
        line_h  = fe[2]
        descent = fe[1]

        hb_font = self._get_hb_font(self._current_style)
        size = self._current_style['font_size']

        segments = []   # (text, tx, xa, runs_or_None)
        cur_x = x
        for text in strings:
            if hb_font is not None:
                sruns = self._shape_with_fallback(text, hb_font, size)
                xa = sum(sum(p.x_advance for p in pos) for _, _, pos in sruns) / 64.0
            else:
                sruns = None
                xa = ctx.text_extents(text)[4]
            segments.append((text, cur_x, xa, sruns))
            cur_x += xa + spacing

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
        baseline_y = self._snap_baseline(ctx, y + line_h)
        for text, tx, _, sruns in segments:
            if sruns is not None:
                self._render_runs(sruns, tx, baseline_y, ctx)
            else:
                ctx.move_to(tx, baseline_y)
                ctx.show_text(text)

        # 3. Draw underline as one continuous line
        if getattr(self, '_current_underline', False):
            self.draw_underline(x, y, total_width, ctx)

    def draw_text(self, text, x, y, ctx):
        fe      = self._temp_ctx.font_extents()
        line_h  = fe[2]
        descent = fe[1]

        hb_font = self._get_hb_font(self._current_style)
        if hb_font is not None:
            runs = self._shape_with_fallback(text, hb_font, self._current_style['font_size'])
            xa = sum(sum(p.x_advance for p in pos) for _, _, pos in runs) / 64.0
        else:
            runs = None
            xa = ctx.text_extents(text)[4]

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

        baseline_y = self._snap_baseline(ctx, y + line_h)
        if runs is not None:
            self._render_runs(runs, x, baseline_y, ctx)
        else:
            ctx.move_to(x, baseline_y)
            ctx.show_text(text)

        if getattr(self, '_current_underline', False):
            self.draw_underline(x, y, xa, ctx)

    def draw_rect(self, x, y, w, h, ctx):
        ctx.set_source_rgb(0.7, 0.7, 0.7)
        # one device pixel wide, regardless of the context's scaling
        lw, _ = ctx.device_to_user_distance(1, 1)
        ctx.set_line_width(lw)
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
        # `width` device pixels wide, regardless of the context's scaling
        lw, _ = ctx.device_to_user_distance(width, width)
        ctx.set_line_width(lw)
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

    def draw_squiggle(self, x, y, width, color, ctx):
        """Draw zigzag line."""
        c = wx.Colour(color)
        ctx.set_source_rgb(c.Red() / 255, c.Green() / 255, c.Blue() / 255)
        ctx.set_line_width(0.5)
        step = 2.0
        amp  = 1.5
        ctx.move_to(x, y)
        i = 1
        while True:
            px = x + step * i
            py = y + (amp if i % 2 == 1 else -amp)
            if px >= x + width:
                ctx.line_to(x + width, py)
                break
            ctx.line_to(px, py)
            i += 1
        ctx.stroke()

    def invert_rect(self, x, y, w, h, ctx):
        """
        Draw a semi-transparent selection rectangle
        in PT coordinates using Cairo.
        """
        r, g, b, a = 83, 97, 220, 50
        ctx.set_source_rgba(r / 255.0, g / 255.0, b / 255.0, a / 255.0)
        ctx.rectangle(x, y, w, h)
        ctx.fill()

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


def eq(a, b, delta=1e-2):
    """Check whether float values a and b are equal within delta."""
    return abs(a - b) <= delta


def test_00():
    # Exact metrics vary by platform and font renderer (Pango, HarfBuzz, …).
    # We only verify the API returns three positive numbers with height > depth.
    app = wx.App(False)
    device = CairoDevice()
    w, h, d = device.measure('M', defaultstyle)
    assert w > 0 and h > 0 and d >= 0
    assert h > d


def test_01():
    app = wx.App(False)
    bmp = wx.Bitmap(1, 1)
    dc = wx.MemoryDC(bmp)
    assert dc.GetMapMode() == 1

    font = wx.Font(12, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
    gc = wx.GraphicsContext.Create(dc)
    gc.SetFont(font, wx.BLACK)

    w, h, descent, ext_leading = gc.GetFullTextExtent("Hello wxPrint (Points)")
    assert w > 0 and h > 0 and descent >= 0


def test_02():
    """Computing text extent."""
    app = wx.App(False)
    bmp = wx.Bitmap(1, 1)
    dc = wx.MemoryDC(bmp)

    font = wx.Font(12, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
    gc = wx.GraphicsContext.Create(dc)
    gc.SetFont(font, wx.BLACK)

    text = "0123456789" * 6
    width, totalheight, descent, ext_leading = gc.GetFullTextExtent(text)
    assert width > 0 and totalheight > 0 and descent >= 0

    device = CairoDevice()
    w, h, d = device.measure(text, defaultstyle)
    assert w > 0 and h > 0 and d >= 0
    # longer text must be wider than a single character
    w1, _, _ = device.measure('M', defaultstyle)
    assert w > w1


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
        # dc already has the zoom applied via SetUserScale above
        painter = device.create_painter(dc, origin=(0, 0))
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


def demo_02():
    """Demo: Fallback fonts. Check that CJK and Greek render in /tmp/demo_fallback.png."""
    app = wx.App(False)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 700, 300)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()

    device = CairoDevice()
    style = {**defaultstyle, 'font_size': 24}
    device.set_style(style, ctx)

    samples = [
        "Mixed: Hello 中文 World",
        "Greek: α β γ δ ε",
        "Latin + CJK: office 会議 fiend",
    ]
    y = 20
    for text in samples:
        w, h, d = device.measure(text, style)
        device.draw_rect(10, y, w, h, ctx)
        device.draw_text(text, 10, y, ctx)
        print(f"{text!r:35s}  w={w:.1f}")
        y += h + d + 10

    path = "/tmp/demo_fallback.png"
    surface.write_to_png(path)
    print(f"Saved: {path}")


def demo_01():
    """Render ligature text via HarfBuzz to /tmp/demo_harfbuzz.png.

    Visually check that fi/fl/ffi/ffl appear as ligature glyphs,
    and that bounding boxes match the shaped advance widths.
    """
    app = wx.App(False)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 700, 260)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()

    device = CairoDevice()
    style = {**defaultstyle, 'font_size': 32}
    device.set_style(style, ctx)

    samples = [
        "fi fl ffi ffl",
        "office difficult affluent",
        "Albert Einstein",
    ]
    y = 10
    for text in samples:
        w, h, d = device.measure(text, style)
        device.draw_rect(10, y, w, h, ctx)
        device.draw_text(text, 10, y, ctx)
        print(f"{text!r:30s}  w={w:.1f}  h={h:.1f}  d={d:.1f}")
        y += h + d + 10

    path = "/tmp/demo_harfbuzz.png"
    surface.write_to_png(path)
    print(f"Saved: {path}")


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

