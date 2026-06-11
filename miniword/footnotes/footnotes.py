from ..textmodel.submodel import Footnote
from ..textmodel.texeltree import EMPTYSTYLE
from ..layout.boxes import NewlineBox
from ..layout.testdevice import TESTDEVICE

SUPERSCRIPTS = str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹')


def to_superscript(n):
    return str(n).translate(SUPERSCRIPTS)


class FootnoteAnchorBox(NewlineBox):
    """Inline superscript number marking a footnote anchor in the text flow."""
    text = '\x00'  # length 1; display is separate to keep length == 1

    def __init__(self, fn_texel, number, style=EMPTYSTYLE, device=None):
        self.fn_texel = fn_texel
        self.number = number
        self.display = to_superscript(number)
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
    import cairo
    app = wx.App(False)

    from ..textmodel.textmodel import TextModel
    from ..textmodel.texeltree import grouped, T, ENDMARK
    from ..layout.cairodevice import CairoDevice
    from ..layout.pagegen import generate_pages, RestartMemo
    from ..layout.factory import Factory
    from ..core.styles import testsheet
    from ..core.units import cm

    model = TextModel('Miniword ist ein freies Textsatzsystem.\n')
    fn = Footnote(grouped([T('Ein leichtgewichtiges Satzsystem, geschrieben in Python.'), ENDMARK]))
    fn_model = model.create_textmodel()
    fn_model.texel = grouped([fn])
    model.insert(7, fn_model)   # Anker nach "Miniword"

    device  = CairoDevice()
    factory = Factory(testsheet, device)
    memo    = RestartMemo()
    memo.geometry = (595, 842)  # A4 in pt
    memo.border   = (2*cm, 2*cm, 2*cm, 2*cm)

    pages = list(generate_pages(model.get_xtexel(), 0, memo, factory))
    page  = pages[0]

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 595, 842)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()
    page.draw_for_print(0, 0, ctx)
    path = '/tmp/footnote_demo.png'
    surface.write_to_png(path)
    print('Saved:', path)


def test_00():
    from ..textmodel.texeltree import G, T, grouped, ENDMARK
    note = Footnote(grouped([T('Hi Chris.'), ENDMARK]))
    text = G([T('Hello world!'), note])
    
