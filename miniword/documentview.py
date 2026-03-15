from contextlib import contextmanager

from .wxtextview.wxtextview import WXTextView
from .textmodel.iterators import iter_newlines
from .builder import Factory, Builder
from .cairodevice import CairoDevice
from .annotation import highlight, squiggle
from .builder import trace

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
        
    def on_char(self, event):
        if event.GetKeyCode() == wx.WXK_RETURN and event.ShiftDown():
            self.insert_linebreak()
            return
        super().on_char(event)

    def insert_linebreak(self):
        from .texels import BR
        from .textmodel.texeltree import grouped
        model = self.model
        index = self.index
        style = model.get_style(index)
        tmp = model.create_textmodel()
        tmp.texel = grouped([BR(style)])
        self.insert(index, tmp)

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

    def _viewport_start(self):
        """Return the text index of the first character on the currently visible page."""
        rx, ry = getattr(self, '_scrollrate', (10, 10))
        _, sy = self.GetViewStart()
        scroll_y = sy * ry / self.zoom
        for p1, p2, px, py, page in self.layout.iter_boxes(0, 0, 0):
            if py + page.height + page.depth >= scroll_y:
                return p1
        return 0

    def _viewport_bottom_y(self):
        """Return the bottom coordinate of the currently visible viewport."""
        rx, ry = getattr(self, '_scrollrate', (10, 10))
        _, sy  = self.GetViewStart()
        ch     = self.GetClientSize()[1]
        return (sy * ry + ch) / self.zoom

    def ensure_viewport(self):
        """Safety net: build until viewport is covered (no dialog)."""
        layout = self.layout
        y = self._viewport_bottom_y()
        if layout.height + layout.depth < y and not layout.is_finished:
            import time
            t0 = time.time()
            print("ensure_viewport")
            self.builder.waitfor_y(y)
            print("y reached after", time.time()-t0)

    def on_paint(self, event):
        self.ensure_viewport()
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

        if wx.Window.FindFocus() is self and self.index <= len(layout):
            layout.draw_cursor(self.index, x, y, painter,
                               self.model.defaultstyle)
        for j1, j2 in self.get_selected():
            if j1 <= len(layout):
                layout.draw_selection(j1, min(j2, len(layout)), x, y, painter)
        dc = None
        painter = None

    # ------------------------------------------------------------------
    # Atomic style operations
    # ------------------------------------------------------------------

    _inhibit_depth = 0
    _pending_range = None  # (i1, i2, delta) accumulated while inhibited

    def _accumulate(self, i1, i2, delta=0):
        r = (i1, i2, delta)
        self._pending_range = accumulate(self._pending_range, r)

    @trace
    def rebuild_range(self, i1, i2, delta):
        """Marks the range from i1 to i2 as dirty. In an atomic
        context, updates are accumulated and deferred. Otherwise, the
        update is triggered immediately. The building will happen in
        the background. To enforce visibility the caller should use
        ensure_viewport oder builder.waitfor_*. No progress dialog is
        shown.
        """        
        if self._inhibit_depth > 0:
            self._accumulate(i1, i2, delta)
        else:
            self.builder.rebuild_range(i1, i2, delta)
            self.ensure_viewport()
            self.refresh()

    @trace
    def rebuild(self):
        """Start a rebuild of the complete document and wait until
        viewport is completed."""
        self.builder.rebuild()
        self.ensure_viewport()
        self.refresh()

    @contextmanager
    def atomic(self):
        """Group multiple model/stylesheet changes into one layout rebuild."""
        self.begin_undo_group()
        self._inhibit_depth += 1
        try:
            yield
        finally:
            self.end_undo_group()
            self._inhibit_depth -= 1
        if self._inhibit_depth == 0 and self._pending_range is not None:
            i1, i2, delta = self._pending_range
            self._pending_range = None
            self._rebuild_with_progress(i1, i2, delta)

    @trace
    def _rebuild_with_progress(self, i1, i2, delta):
        """Rebuild range and show progress dialog if viewport not yet covered."""
        print("rebuild range=", i1, i2, delta)
        self.builder.rebuild_range(i1, i2, delta)
        layout = self.builder.layout
        y = self._viewport_bottom_y()
        index = self.index
        total = max(1, len(self.model))
        if layout.height + layout.depth >= y and index < len(layout):
            print("conditions met, switching to background",
                  layout.height + layout.depth, ">=", y, index ,"<", len(layout))
            self.refresh()
            return
        print("showing progress")
        
        dlg = wx.ProgressDialog(
            "Building layout", "Please wait...",
            maximum=100, parent=self,
            style=wx.PD_AUTO_HIDE)
        def tick():
            dlg.Update(min(99, int(100 * len(layout) / total)))            
        try:
            self.builder.waitfor_y(y, tick)
            print("waiting for index", index)
            self.builder.waitfor_index(index, tick)
            print("finally reached without exception")
        finally:
            dlg.Destroy()
        self.refresh()

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
        if j1 is None:
            return
        self.clear_caches()
        if self._inhibit_depth > 0:
            self._accumulate(j1, j2)
        else:
            self._rebuild_with_progress(j1, j2, 0)

    @trace
    def settings_changed(self, *args, **kwds):
        self.builder.settings = self.document.settings
        self.builder.rebuild()
        self.ensure_viewport()
        self.refresh()

    @trace
    def style_removed(self, stylesheet, key):
        self.clear_caches()
        self.builder.rebuild()
        self.ensure_viewport()
        self.refresh()

    def create_builder(self):
        factory = Factory(self.document.basestyles, device=CairoDevice())
        factory.blobs = self.document.blobs
        builder = Builder(self.model, factory)
        builder.settings = self.document.settings
        return builder

    def set_index(self, index, extend=False, update=True):
        self.builder.device.reset_blink()
        self.builder.waitfor_index(index + 1)
        WXTextView.set_index(self, index, extend, update)

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

    def move_page_down(self, shift):
        index    = self.index
        layout   = self.layout
        x, y     = layout.get_rect(index, 0, 0).items()[:2]
        _, ch    = self.GetClientSize()
        target_y = y + ch / self.zoom
        last     = None
        for r1, r2, rx, ry, row in self.iter_rows():
            if ry >= target_y:
                i = row.get_index(x - rx, row.height)
                return self.set_index(r1 + i, shift)
            last = r1, r2, rx, ry, row
        if last:
            r1, r2, rx, ry, row = last
            self.set_index(r2 - 1, shift)  # end of last row

    def move_page_up(self, shift):
        index    = self.index
        layout   = self.layout
        x, y     = layout.get_rect(index, 0, 0).items()[:2]
        _, ch    = self.GetClientSize()
        target_y = y - ch / self.zoom
        prev     = None
        for r1, r2, rx, ry, row in self.iter_rows():
            if ry + row.height + row.depth > target_y:
                if prev is None:
                    return self.set_index(0, shift)
                r1, r2, rx, ry, row = prev
                i = row.get_index(x - rx, row.height)
                return self.set_index(r1 + i, shift)
            prev = r1, r2, rx, ry, row

    def handle_action(self, action, shift=False):
        if action == 'move_down':
            self.move_down(shift)
        elif action == 'move_up':
            self.move_up(shift)
        elif action == 'move_page_down':
            self.move_page_down(shift)
        elif action == 'move_page_up':
            self.move_page_up(shift)
        elif action == 'move_document_end':
            self.set_index(len(self.layout) - 1, shift)
        else:
            return WXTextView.handle_action(self, action, shift)



def accumulate(r1, r2):
    """Combine two consecutive update ranges into one.

    r1 = (i1, i2, delta) in original model coordinates.
    r2 = (b1, b2, d2)    in model coordinates after r1 was applied.

    Returns a merged (i1, i2, delta) in original model coordinates that
    covers both changes and carries the combined delta.
    """
    if r1 is None:
        return r2
    elif r2 is None:
        return r1
    
    pi1, pi2, pd = r1
    b1,  b2,  d2 = r2

    pi2_m0  = pi2 + max(0, -pd)   # M0 end: includes deleted chars if pd<0
    pi1_m1  = pi1 + max(0,  pd)   # first M1 position after the change

    if b1 > pi1_m1:                # r2 entirely after r1
        b1o = b1 - pd
        b2o = b2 - pd
    elif b2 < pi1:                 # r2 entirely before r1
        b1o = b1
        b2o = b2
    else:                          # overlap — conservative
        b1o = min(b1, pi1)
        b2o = max(b2 - pd, pi2_m0)

    return (min(pi1, b1o), max(pi2_m0, b2o), pd + d2)


def test_accumulate():
    "accumulate: combining two update ranges"
    # --- delta=0: property changes ---

    # r2 after r1, no overlap
    assert accumulate((2, 5, 0), (8, 12, 0)) == (2, 12, 0)

    # r2 before r1, no overlap
    assert accumulate((8, 12, 0), (2, 5, 0)) == (2, 12, 0)

    # r2 overlaps r1
    assert accumulate((2, 8, 0), (5, 12, 0)) == (2, 12, 0)

    # --- insertion (pd > 0) ---

    # r2 after r1: positions shift by pd (user's example)
    # insert 1 at 5, then insert 1 at 10-in-M1 (= 9 in M0)
    assert accumulate((5, 5, 1), (10, 10, 1)) == (5, 9, 2)

    # r2 before r1: no shift needed
    # insert 1 at 10, then insert 1 at 3-in-M1 (before change)
    assert accumulate((10, 10, 1), (3, 3, 1)) == (3, 10, 2)

    # r2 within inserted region (overlap)
    # insert 3 at 5; property change at pos 6-in-M1 (inside insertion)
    assert accumulate((5, 5, 3), (6, 6, 0)) == (5, 5, 3)

    # --- deletion (pd < 0) ---

    # r2 after deletion: shift right by |pd|, pi2_m0 covers deleted region
    # delete 3 at 5 (removes M0 positions 5-7); property change at 7-in-M1 (=10 in M0)
    assert accumulate((5, 5, -3), (7, 7, 0)) == (5, 10, -3)

    # r2 before deletion: pi2_m0 must include the deleted region
    # delete 3 at 5; property change at 2-3 in M1 (before deletion)
    assert accumulate((5, 5, -3), (2, 3, 0)) == (2, 8, -3)

    # insertion then deletion
    # insert 2 at 3; delete 4 at 8-in-M1 (= 6 in M0)
    assert accumulate((3, 3, 2), (8, 8, -4)) == (3, 6, -2)

    # --- straddle: b1 before, b2 after — only b2 needs shifting ---

    # insert 2 at 5; property change [3, 10] in M1 (b1 before, b2 after insert)
    # b1=3 → no shift; b2=10 → shift: 10-2=8
    assert accumulate((5, 5, 2), (3, 10, 0)) == (3, 8, 2)

    # delete 3 at 5; property change [3, 7] in M1 (b1 before, b2 after delete)
    # b1=3 → no shift; b2=7 → shift: 7+3=10; pi2_m0=8 → max(10,8)=10
    assert accumulate((5, 5, -3), (3, 7, 0)) == (3, 10, -3)


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
        view.builder.waitfor_finish()
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

    
def test_01():
    "progress dialog is shown when viewport is not yet covered"
    import io
    from contextlib import redirect_stdout
    from unittest.mock import patch
    #from einstein import get_einstein_model as get_model
    from moby import get_moby_model as get_model
    from .document import Document
    from .styles import style_default

    with redirect_stdout(io.StringIO()):
        app  = wx.App(redirect=False)
        frame = wx.Frame(None)
        doc  = Document()
        doc.textmodel = get_model()
        doc.basestyles.set('normal', dict(style_default))
        view = DocumentView(frame, doc)
        view.builder.waitfor_finish()

    # Pretend the viewport extends far below the built layout so the
    # dialog condition is always triggered.
    view._viewport_bottom_y = lambda: float('inf')

    dialogs = []
    ticks = []
    class TrackingDialog(wx.ProgressDialog):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            dialogs.append(self)
        def Update(self, x):
            super().Update(x)
            ticks.append(x)
            return True, False

    with patch('miniword.documentview.wx.ProgressDialog', TrackingDialog):
        with view.atomic():
            view.properties_changed(view.model, 0, 100)

    assert len(ticks)
    assert len(dialogs) > 0, "progress dialog should have been shown"

    view.index = len(view.model)
    del ticks[:]
    del dialogs[:]
    with patch('miniword.documentview.wx.ProgressDialog', TrackingDialog):
        with view.atomic():
            view.index = len(view.model)
            view.properties_changed(view.model, 0, len(view.model))
    
    print("ticks=", ticks)


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
