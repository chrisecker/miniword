# -*- coding: utf-8 -*-

# annotation.py – drawing annotations on top of a box tree.
#
# Both functions walk the box tree the same way as Box.draw_selection:
# index-range overlap test, viewport clipping via device.intersects(),
# and drawing at the TextBox leaves.
#
# Typical paint-event usage:
#
#     layout.draw_background(x, y, gc)   # 1. white page fills
#     highlight(gc, layout, i1, i2, x, y)# 2. colored backgrounds (before text)
#     layout.draw(x, y, gc)              # 3. text (no page-fill any more)
#     squiggle(gc, layout, i1, i2, x, y) # 4. lines on top of text

from .wxtextview.boxes import _TextBoxBase
from .wxtextview.rect import Rect
from .stretchable import StretchableText


def _iter_textboxes(dc, box, i1, i2, x, y):
    """Yield (x1, y1, px1, px2, child) for every text leaf that overlaps
    [i1, i2] and lies inside the current clipping region.

    px1, px2 are pixel offsets *within* child at the start and end of the
    [i1, i2] range.  Handles both _TextBoxBase and StretchableText leaves.
    """
    device = box.device
    for j1, j2, x1, y1, child in box.iter_boxes(0, x, y):
        if not (i1 < j2 and j1 < i2):
            continue
        r = Rect(x1, y1, x1 + child.width, y1 + child.height + child.depth)
        if not device.intersects(dc, r):
            continue
        if isinstance(child, _TextBoxBase):
            k1 = max(0, i1 - j1)
            k2 = min(len(child.text), i2 - j1)
            px1 = child.measure(child.text[:k1])[0]
            px2 = child.measure(child.text[:k2])[0]
            yield x1, y1, px1, px2, child
        elif isinstance(child, StretchableText):
            k1 = max(0, i1 - j1)
            k2 = min(len(child), i2 - j1)
            px1 = child.find_x(k1)
            px2 = child.find_x(k2)
            yield x1, y1, px1, px2, child
        else:
            yield from _iter_textboxes(dc, child, i1 - j1, i2 - j1, x1, y1)


def highlight(dc, box, i1, i2, x=0, y=0, color='yellow'):
    """Draw a colored background behind all characters in [i1, i2].

    Uses device.fill_rect() so the fill is opaque.  Must be called
    *after* layout.draw_background() and *before* layout.draw() so that
    the text is rendered on top of the highlight.

    Args:
        dc:         Drawing context (wx.GraphicsContext or Cairo context).
        box:        Root box (typically the layout object).
        i1, i2:     Index range to annotate (document positions).
        x, y:       Absolute pixel offset of *box* — same values
                    passed to box.draw().
        color:      Fill color accepted by device.fill_rect().
    """
    for x1, y1, px1, px2, child in _iter_textboxes(dc, box, i1, i2, x, y):
        hx1 = x1 + px1
        hx2 = x1 + px2
        if hx2 > hx1:
            child.device.fill_rect(
                hx1, y1, hx2 - hx1, child.height + child.depth, color, dc)


def _squiggle_wx(gc, x, y, width, color):
    """Draw zigzag on a wx.GraphicsContext."""
    import wx
    step = 2.0
    amp  = 1.5
    pen  = gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(color)).Width(1))
    gc.SetPen(pen)
    gc.SetBrush(wx.TRANSPARENT_BRUSH)
    path = gc.CreatePath()
    path.MoveToPoint(x, y)
    i = 1
    while True:
        px = x + step * i
        py = y + (amp if i % 2 == 1 else -amp)
        if px >= x + width:
            path.AddLineToPoint(x + width, py)
            break
        path.AddLineToPoint(px, py)
        i += 1
    gc.StrokePath(path)


def _squiggle_cairo(ctx, x, y, width, color):
    """Draw zigzag on a Cairo context."""
    import wx
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


def squiggle(dc, box, i1, i2, x=0, y=0, color='red'):
    """Draw a wavy underline beneath all characters in [i1, i2].

    Draws a zigzag path directly onto dc. Supports both wx.GraphicsContext
    (WxDevice) and Cairo context (CairoDevice) — detected via duck typing.
    The wave sits on the text baseline (y + height), with a step of 2 PT
    and an amplitude of 1.5 PT.  Call *after* layout.draw().

    Args:
        dc:         Drawing context (wx.GraphicsContext or Cairo context).
        box:        Root box (typically the layout object).
        i1, i2:     Index range to annotate (document positions).
        x, y:       Absolute pixel offset of *box* — same values
                    passed to box.draw().
        color:      Line color, any string accepted by wx.Colour.
    """
    draw = _squiggle_wx if hasattr(dc, 'CreatePath') else _squiggle_cairo
    for x1, y1, px1, px2, child in _iter_textboxes(dc, box, i1, i2, x, y):
        hx1 = x1 + px1
        hx2 = x1 + px2
        if hx2 > hx1:
            draw(dc, hx1, y1 + child.height, hx2 - hx1, color)


# --- Tests ---

def test_highlight():
    from .wxtextview.boxes import TextBox, VBox
    from .wxtextview.testdevice import TestDevice

    calls = []

    class RecordingDevice(TestDevice):
        def fill_rect(self, x, y, w, h, color, dc):
            calls.append((x, y, w, h, color))

    device = RecordingDevice()
    t1 = TextBox('01234', device=device)
    t2 = TextBox('56789', device=device)
    par = VBox([t1, t2])

    # '234' (indices 2..5) lies entirely in the first TextBox
    highlight(None, par, 2, 5)
    assert len(calls) == 1
    x, y, w, h, color = calls[0]
    assert x == 2        # measure('01') == 2  (TestDevice: 1 pt per char)
    assert w == 3        # measure('234') == 3
    assert color == 'yellow'

    # Range spanning both boxes: '34' + '567' (indices 3..8)
    calls.clear()
    highlight(None, par, 3, 8)
    assert len(calls) == 2


def test_iter_textboxes():
    # Tests the shared iteration core used by both highlight and squiggle.
    from .wxtextview.boxes import TextBox, VBox, HBox
    from .stretchable import create_stretchtext

    t1 = TextBox('01234')
    t2 = TextBox('56789')
    par = VBox([t1, t2])

    # Single box, partial range: px1/px2 are pixel offsets (TestDevice: 1pt/char)
    results = list(_iter_textboxes(None, par, 2, 5, 0, 0))
    assert len(results) == 1
    x1, y1, px1, px2, child = results[0]
    assert child is t1
    assert px1 == 2 and px2 == 5

    # Range spanning both boxes
    results = list(_iter_textboxes(None, par, 3, 8, 0, 0))
    assert len(results) == 2
    assert results[0][4] is t1
    assert results[1][4] is t2

    # Nested: HBox inside VBox
    h = HBox([TextBox('abc'), TextBox('def')])
    outer = VBox([h])
    results = list(_iter_textboxes(None, outer, 1, 5, 0, 0))
    assert len(results) == 2   # both inner TextBoxes

    # StretchableText leaf: highlights must not be silently dropped
    tb = TextBox('Hello world')
    st = create_stretchtext(tb, is_last=False)
    st.set_stretch(10)
    row = VBox([st])
    results = list(_iter_textboxes(None, row, 0, len(st), 0, 0))
    assert len(results) == 1
    x1, y1, px1, px2, child = results[0]
    assert child is st
    assert px1 == 0                      # start of first character
    assert px2 == st.find_x(len(st))    # end of last character


# --- Demo ---

def demo_00():
    """Show highlight and squiggle annotations in a real DocumentView.

    Opens the Einstein text.  The first six long words found in the
    text are annotated: the first three with yellow highlight, the
    next three with a red squiggle underline.

    A Python shell opens so that view.highlights and view.squiggles
    can be edited interactively and view.Refresh() called to redraw.

    Annotation format: list of (i1, i2) or (i1, i2, color).
    """
    import re
    import wx
    from einstein import get_einstein_model
    from .document import Document
    from .documentview import DocumentView
    from .styles import stylesheet

    app = wx.App(True)
    doc = Document()
    doc.textmodel = get_einstein_model()
    doc.basestyles = stylesheet

    frame = wx.Frame(None, title='Annotation Demo', size=(900, 600))
    view  = DocumentView(frame, doc)
    view.highlights = []
    view.squiggles  = []
    view.SetBackgroundColour('light grey')

    # Seed example annotations from the first six long words in the text.
    text  = doc.textmodel.get_text()
    words = list(dict.fromkeys(re.findall(r'\b\w{6,}\b', text)))[:6]
    for word in words[:3]:
        i = text.find(word)
        view.highlights.append((i, i + len(word)))
    for word in words[3:6]:
        i = text.find(word)
        view.squiggles.append((i, i + len(word)))

    frame.Show()

    from .wxtextview import testing
    l = locals()
    l.update(globals())
    testing.pyshell(l)

    app.MainLoop()
