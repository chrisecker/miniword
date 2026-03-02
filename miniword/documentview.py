from contextlib import contextmanager

from .wxtextview.wxtextview import WXTextView
from .textmodel.iterators import iter_newlines
from .builder import Factory, Builder
from .cairodevice import CairoDevice
from .annotation import highlight, squiggle

import wx

class DocumentView(WXTextView):

    highlights = []  # list of (i1, i2) or (i1, i2, color)
    squiggles  = []  # list of (i1, i2) or (i1, i2, color)

    min_zoom = 0.2
    max_zoom = 5.0
    zoom_step = 0.1
    
    def __init__(self, parent, document):
        self.document = document
        super().__init__(parent)
        self.Bind(wx.EVT_MOUSEWHEEL, self.on_mousewheel)
        self.set_model(document.textmodel)
        self.add_model(document.charstyles)
        self.add_model(document.liststyles)
        self.add_model(document.basestyles)
        self.add_model(document)
        
    def on_mousewheel(self, event):
        if not event.ControlDown():
            return event.Skip()  # scroll
        old_zoom = self.zoom
        factor = 1.1 if event.GetWheelRotation() > 0 else 1 / 1.1
        new_zoom = max(0.2, min(5.0, old_zoom * factor))

        cw, ch = self.GetClientSize()
        rx, ry = getattr(self, '_scrollrate', (10, 10))
        sx, sy = self.GetViewStart()
        scroll_x = sx * rx
        scroll_y = sy * ry

        # Content-center in old zoom
        cx_content = (scroll_x + cw / 2) / old_zoom
        cy_content = (scroll_y + ch / 2) / old_zoom

        # new scroll so that content-center does not change
        new_scroll_x = cx_content * new_zoom - cw / 2
        new_scroll_y = cy_content * new_zoom - ch / 2

        self.set_zoom(new_zoom)

        # VirtualSize must be updateted before Scroll()
        layout = self.layout
        self.SetVirtualSize((int(layout.width * new_zoom), int(layout.height * new_zoom)))
        self.SetScrollRate(rx, ry)

        self.Scroll(max(0, int(new_scroll_x / rx)),
                    max(0, int(new_scroll_y / ry)))        

    def on_paint(self, event):
        self._update_scroll()
        self.keep_cursor_on_screen()

        pdc = wx.PaintDC(self)
        pdc.SetAxisOrientation(True, False)
        device = self.builder.get_device()
        if device.buffering:
            dc = wx.BufferedDC(pdc)
            if not dc.IsOk():
                return
        else:
            dc = pdc
        dc.SetBackgroundMode(wx.SOLID)
        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.Clear()
        region = self.GetUpdateRegion()
        rx, ry, rw, rh = region.Box
        dc.SetClippingRegion(rx - 1, ry - 1, rw + 2, rh + 2)
        painter = device.create_painter(dc)

        zoom = self.zoom
        layout = self.layout
        cw, ch = self.GetClientSize()
        vw = int(layout.width * zoom)
        vh = int(layout.height * zoom)

        px, py = self.CalcScrolledPosition((0, 0))
        if vw < cw:
            px = (cw - vw) // 2
        if vh < ch:
            py = (ch - vh) // 2
        x = px / zoom
        y = py / zoom

        layout.draw_background(x, y, painter)          # 1. white page fills

        for entry in self.highlights:
            i1, i2 = entry[:2]
            c = entry[2] if len(entry) > 2 else 'yellow'
            highlight(painter, layout, i1, i2, x, y, c)  # 2. colored backgrounds

        layout.draw(x, y, painter)                      # 3. text on top

        for entry in self.squiggles:
            i1, i2 = entry[:2]
            c = entry[2] if len(entry) > 2 else 'red'
            squiggle(painter, layout, i1, i2, x, y, c)   # 4. lines on top

        if wx.Window.FindFocus() is self:
            layout.draw_cursor(self.index, x, y, painter,
                               self.model.defaultstyle)
        for j1, j2 in self.get_selected():
            layout.draw_selection(j1, j2, x, y, painter)
        dc = None
        painter = None

    # ------------------------------------------------------------------
    # Atomic style operations
    # ------------------------------------------------------------------

    @contextmanager
    def atomic(self):
        """Group rebuild and undo into one atomic operation.

        Both the rebuild (via builder.inhibit/resume) and the undo entries
        (via begin/end_undo_group) are coalesced.  After the context exits,
        the layout is built to completion and the view is refreshed.
        """
        self.begin_undo_group()
        self.builder.inhibit_rebuilds()
        try:
            yield
        finally:
            self.end_undo_group()
            self.builder.resume_rebuilds()  # fires one merged rebuild
        self.builder.waitfor_finish()
        self.Refresh()

    def _undo_stylesheet(self, name, restore_to, after_redo):
        """Undo/redo a stylesheet change.

        restore_to: style dict to restore, or None to delete the style.
        after_redo: style dict for the redo direction (or None to delete).
        Returns the complementary redo/undo entry.
        """
        if restore_to is None:
            self.document.basestyles.delete(name)
        else:
            self.document.basestyles.set(name, restore_to)
        return (self._undo_stylesheet, name, after_redo, restore_to)

    # ------------------------------------------------------------------
    # Stylesheet observer
    # ------------------------------------------------------------------

    def style_changed(self, stylesheet, key):
        j1 = j2 = None
        for i1, i2, nl in iter_newlines(self.model.get_xtexel(), 0):
            if nl.parstyle.get('base', 'normal') == key:
                if j1 is None:
                    j1 = i1
                j2 = i2
        self.clear_caches()
        if j1 is None:
            return
        # Enqueue instead of rebuilding immediately so that a surrounding
        # atomic() context can merge this rebuild with further changes.
        self.builder._enqueue_rebuild(j1, j2)
        if not self.builder._inhibit_depth:
            # Outside an atomic context: finish and repaint synchronously.
            self.builder.waitfor_finish()
            self.refresh()

    def settings_changed(self, *args, **kwds):
        self.builder.settings = self.document.settings
        self.builder.rebuild()
        self.refresh()

    def style_removed(self, stylesheet, key):
        self.clear_caches()
        self.builder.rebuild()
        self.refresh()

    def create_builder(self):
        factory = Factory(self.document.basestyles, device=CairoDevice())
        builder = Builder(self.model, factory)
        return builder

    def set_index(self, index, extend=False, update=True):
        self.builder.device.reset_blink()
        WXTextView.set_index(self, index, extend, update)

    def print(self):
        import printer
        printer.show_printdlg(self.builder.layout)

    def export_pdf(self, path):
        import cairo
        self.builder.waitfor_finish()
        pages = self.layout.childs
        if not pages:
            return
        device = self.builder.get_device()
        w, h = pages[0].width, pages[0].height
        surface = cairo.PDFSurface(path, w, h)
        ctx = cairo.Context(surface)
        for page in pages:
            page.draw_background(0, 0, ctx)
            page.draw(0, 0, ctx)
            ctx.show_page()
        surface.finish()

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
            if ry + row.height + row.depth > y:
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
    "modifying a basestyle updates the layout"
    import io
    from contextlib import redirect_stdout
    from einstein import get_einstein_model
    from .document import Document
    from .styles import style_default

    model = get_einstein_model()
    doc   = Document()
    doc.textmodel = model
    doc.basestyles.set('normal', dict(style_default))

    with redirect_stdout(io.StringIO()):
        app   = wx.App(redirect=False)
        frame = wx.Frame(None)
        view  = DocumentView(frame, doc)
        view.builder.nbefore = 0
        view.builder.nrest = 0

        new_normal = doc.basestyles.get('normal').copy()
        new_normal['font_size'] = 8
        doc.basestyles.set('normal', new_normal)
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
    from .styles import testsheet
    model = get_einstein_model()

    model.set_properties(0, 15, color='red')
    model.set_parproperties(0, 1000, paragraph_type='list')
    app   = wx.App(redirect=True)
    frame = wx.Frame(None)
    view  = DocumentView(frame, -1)
    view.model = model
    view.builder.device.zoom = 2
    testsheet.add_view(view)
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
