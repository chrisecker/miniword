from ..textmodel.submodel import Footnote
from ..textmodel.texeltree import EMPTYSTYLE
from ..layout.boxes import NewlineBox, RowsBox
from ..layout.testdevice import TESTDEVICE

def iter_footnotes(texel):
    """Yield (offset, chain, anchor) for every footnote in texel, in
    the order of the footnote flow - the order RowFactory lays them
    out in: a footnote, then the footnotes nested in its content, then
    the next one.

    offset: where the footnote's content starts in the footnote flow.
    chain: [(position, footnote), ...] from the outermost footnote down
    to this one; position is relative to the enclosing texel (texel
    itself, or the content of the footnote one level up).
    anchor: (flow, index) of the footnote's anchor - (0, i) in the
    main text, (1, i) in the footnote flow for a nested footnote."""
    from ..textmodel.utils import iter_leafes
    from ..textmodel.texeltree import length
    offset = 0

    def visit(texel, chain, flow, base):
        nonlocal offset
        for i1, i2, child in iter_leafes(texel, 0, True):
            if not isinstance(child, Footnote):
                continue
            link = chain + [(i1, child)]
            start = offset
            yield start, link, (flow, base + i1)
            offset += length(child.content)
            yield from visit(child.content, link, 1, start)

    return visit(texel, [], 0, 0)


def footnote_anchored_at(texel, flow, i):
    """Offset (in the footnote flow) of the footnote whose anchor is
    at index i of flow, or None."""
    for offset, chain, anchor in iter_footnotes(texel):
        if anchor == (flow, i):
            return offset
    return None


def format_fn_label(n, style='numbers'):
    if style == 'letters':
        return chr(ord('a') + (n - 1) % 26)
    if style == 'roman':
        from ..layout.counters import to_roman
        return to_roman(n)
    return str(n)


class FootnoteBox(RowsBox):
    """
    A footnotebox is a rectangular region at the bottom of a page containing footnote
    rows. A separator line can be drawn at the top of the box.
    """
    def __init__(self, rows, width, draw_separator=True, device=None):
        if device is not None:
            self.device = device
        self.draw_separator = draw_separator

        positioned = []
        y = 0
        for row in rows:
            positioned.append((0, y, row))
            y += row.height + row.depth
        self.rows = tuple(positioned)

        self.width = max(width, max((row.width for row in rows), default=0))
        self.height = y
        self.depth = 0

    def draw(self, x, y, gc):
        if self.draw_separator:
            sep_y = y - 4   # 4pt gap above the line
            self.device.draw_line(x, sep_y, x + self.width * 0.3, sep_y,
                                   0.5, gc)
        RowsBox.draw(self, x, y, gc)
    



    
class FootnoteAnchorBox(NewlineBox):
    """Inline superscript number marking a footnote anchor in the text flow."""
    text = '\x00'  # length 1; display is separate to keep length == 1

    def __init__(self, fn_texel, label, style=EMPTYSTYLE, device=None):
        self.fn_texel = fn_texel
        self.display = label
        NewlineBox.__init__(self, style, device)

    def layout(self):
        w, h, d = self.measure(self.display)
        self.width = w
        self.height = h
        self.depth = d

    def __repr__(self):
        return 'FNA(%s)' % self.display

    def draw(self, x, y, dc):
        self.device.set_style(self.style, dc)
        self.device.draw_text(self.display, x, y, dc)


def demo_00():
    """Render a short document with a footnote to /tmp/footnote_demo.png."""
    import wx
    import cairocffi as cairo
    app = wx.App(False)

    from ..textmodel.textmodel import TextModel
    from ..textmodel.texeltree import grouped, T, ENDMARK
    from ..layout.cairodevice import CairoDevice
    from ..layout.rowfactory import generate_pages, state_from_settings
    from ..core.stylesheet import testsheet

    model = TextModel('Miniword ist ein freies Textsatzsystem.\n')
    fn = Footnote(grouped([T('Ein leichtgewichtiges Satzsystem, geschrieben in Python.'), ENDMARK]))
    fn_model = model.create_textmodel()
    fn_model.texel = grouped([fn])
    model.insert(7, fn_model)   # Anker nach "Miniword"

    device = CairoDevice()
    memo   = state_from_settings({})  # A4

    pages = list(generate_pages(model.get_xtexel(), 0, memo, testsheet,
                                device))
    page  = pages[0]

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 595, 842)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()
    page.draw_for_print(0, 0, ctx)
    path = '/tmp/footnote_demo.png'
    surface.write_to_png(path)
    print('Saved:', path)


def _nested_doc():
    """Main text 'ab[F1]cd[F3]' where F1 = 'xy[F2]z', F2 = 'uv',
    F3 = 'w' (each content ends with ENDMARK)."""
    from ..textmodel.texeltree import G, T, grouped, ENDMARK
    f2 = Footnote(grouped([T('uv'), ENDMARK]))
    f1 = Footnote(grouped([T('xy'), f2, T('z'), ENDMARK]))
    f3 = Footnote(grouped([T('w'), ENDMARK]))
    return G([T('ab'), f1, T('cd'), f3, ENDMARK]), f1, f2, f3


def test_01():
    "iter_footnotes: footnote flow order, offsets, chains and anchors"
    texel, f1, f2, f3 = _nested_doc()
    result = list(iter_footnotes(texel))
    assert [chain[-1][1] for _, chain, _ in result] == [f1, f2, f3]
    # F1 content: x y [F2] z END = 5, F2: u v END = 3
    assert [offset for offset, _, _ in result] == [0, 5, 8]
    assert [[p for p, _ in chain] for _, chain, _ in result] == \
        [[2], [2, 2], [5]]
    assert [anchor for _, _, anchor in result] == [(0, 2), (1, 2), (0, 5)]

    assert footnote_anchored_at(texel, 0, 2) == 0
    assert footnote_anchored_at(texel, 1, 2) == 5
    assert footnote_anchored_at(texel, 0, 5) == 8
    assert footnote_anchored_at(texel, 0, 3) is None
    assert footnote_anchored_at(texel, 1, 0) is None


def test_00():
    from ..textmodel.texeltree import G, T, grouped, ENDMARK
    note = Footnote(grouped([T('Hi Chris.'), ENDMARK]))
    text = G([T('Hello world!'), note])
    
