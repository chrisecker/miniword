from .wxtextview.wxtextview import WXTextView
from .textmodel.iterators import iter_newlines
from .builder import Factory, Builder
from .styles import stylesheet
from .cairodevice import CairoDevice

import wx

class DocumentView(WXTextView):
    """Simple view for testing."""

    def style_changed(self, stylesheet, key):
        j1 = j2 = None
        for i1, i2, nl in iter_newlines(self.model.get_xtexel(), 0):
            if nl.parstyle.get('base', 'normal') == key:
                if j1 is None:
                    j1 = i1
                j2 = i2
        print("style changed", key, "range: %i - %i" % (j1, j2))
        self.clear_caches()
        self.builder.rebuild_dirty(j1, j2, 0) # klappt nicht!!!!
        #self.rebuild()
        self.builder.waitfor_finish() # XXX
        self.refresh()

    def style_removed(self, stylesheet, key):
        print("style removed", key)

    def create_builder(self):
        factory = Factory(stylesheet, device=CairoDevice())
        builder = Builder(self.model, factory)
        return builder

    def set_index(self, index, extend=False, update=True):
        self.builder.device.reset_blink()
        WXTextView.set_index(self, index, extend, update)

    def print(self):
        import printer
        printer.show_printdlg(self.builder.layout)

    def iter_rows(self):
        for p1, p2, px, py, page in self.layout.iter_boxes(0, 0, 0):
            for r1, r2, rx, ry, row in page.iter_boxes(p1, px, py):
                yield r1, r2, rx, ry, row

    def move_down(self, shift):
        index  = self.index
        layout = self.layout
        x, y   = layout.get_rect(index, 0, 0).items()[:2]
        for r1, r2, rx, ry, row in self.iter_rows():
            if ry > y:
                i = row.get_index(x - rx, row.height)
                return self.set_index(r1 + i, shift)

    def move_up(self, shift):
        index  = self.index
        layout = self.layout
        x, y   = layout.get_rect(index, 0, 0).items()[:2]
        prev   = None
        for r1, r2, rx, ry, row in self.iter_rows():
            if ry + row.height + row.depth >= y:
                if not prev:
                    return
                r1, r2, rx, ry, row = prev
                i = row.get_index(x - rx, row.height)
                return self.set_index(r1 + i, shift)
            prev = r1, r2, rx, ry, row

    def handle_action(self, action, shift=False):
        if action == 'move_down':
            self.move_down(shift)
        elif action == 'move_up':
            self.move_up(shift)
        else:
            return WXTextView.handle_action(self, action, shift)


def test_00():
    "modifying a basestyle"
    from einstein import get_einstein_model
    model = get_einstein_model()

    app   = wx.App(redirect=False)
    frame = wx.Frame(None)
    view  = DocumentView(frame, -1)
    view.model = model
    stylesheet.add_view(view)
    normal = stylesheet.get('normal').copy()
    normal['font_size'] = 8
    view.builder.nbefore = 0
    view.builder.nrest = 0
    
    stylesheet.set('normal', normal)
    stats = view.builder.get_updatestats()

    # are the styles updated?
    style = view.builder.factory.mk_style({})
    assert style['font_size'] == 8

    # is the layout updated?
    assert stats == (0, 1, 0)

    assert view.layout is view.builder.layout
    
    row = view.layout.childs[0].rows[0][-1]
    tb = row.childs[0]
    assert tb.style['font_size'] == 8

    
def demo_00():
    from einstein import get_einstein_model
    model = get_einstein_model()

    model.set_properties(0, 15, color='red')
    model.set_parproperties(0, 1000, paragraph_type='list')
    app   = wx.App(redirect=True)
    frame = wx.Frame(None)
    view  = DocumentView(frame, -1)
    view.model = model
    view.builder.device.zoom = 2
    stylesheet.add_view(view)
    frame.Show()

    if 1:
        from .inspector import Inspector
        inspector = Inspector(view, None)
        inspector.Show()
    if 1:
        from .wxtextview import testing
        l = locals()
        l.update(globals())
        testing.pyshell(l)
    app.MainLoop()
