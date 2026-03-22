import wx
from .editorbase import Editor
from .tables import Table, TableBox

_HIT_RADIUS = 5   # hit detection radius in screen pixels


def _find_table_at(layout, index):
    """Return (TableBox, cx, cy, ci1, ci2) for the box containing index, or None."""
    for p1, p2, px, py, page in layout.iter_boxes(0, 0, 0):
        if not (p1 <= index < p2):
            continue
        for r1, r2, rx, ry, row in page.iter_boxes(p1, px, py):
            if not (r1 <= index < r2):
                continue
            for ci1, ci2, cx, cy, child in row.iter_boxes(r1, rx, ry):
                if isinstance(child, TableBox) and ci1 < index < ci2:
                    return child, cx, cy, ci1, ci2
    return None


class TableEditor(Editor):
    """Resize table columns by dragging column separators.

    During drag only a preview line is drawn; the model is not touched.
    The change is committed to the texel on mouse-release.
    """

    _drag_col         = None
    _drag_orig_widths = None
    _preview_width    = None   # new width of dragged col while dragging

    def install(self, view, index):
        self._drag_handle = None
        self.view  = view
        self.index = index
        res = _find_table_at(view.layout, index)
        if res is None:
            self._table_box = None
            return
        self._table_box, self._tx, self._ty, self._ti1, self._ti2 = res

    def find_box(self):
        res = _find_table_at(self.view.layout, self.index)
        if res is None:
            return None
        tb, cx, cy, ci1, ci2 = res
        return tb, (cx, cy)

    def get_cursor(self, handle_id):
        return wx.CURSOR_SIZEWE

    def hit_test(self, x, y):
        """(x, y) in box-local coords (relative to table top-left)."""
        tb = self._table_box
        if tb is None:
            return None
        if not (0 <= y <= tb.height):
            return None
        hit_r = _HIT_RADIUS / self.view.zoom
        sep_x = 0
        for col, cw in enumerate(tb.col_widths):
            sep_x += cw
            if abs(x - sep_x) <= hit_r:
                return col
        return None

    def start_drag(self, handle, x, y):
        super().start_drag(handle, x, y)
        self._drag_col         = handle
        self._drag_orig_widths = list(self._table_box.col_widths)
        self._preview_width    = None
        self.view.refresh()

    def on_motion(self, event):
        if self._drag_col is None:
            return
        p = self.window_to_box(event.Position)
        self._total_dx = p[0] - self._drag_start[0]
        orig = self._drag_orig_widths
        self._preview_width = max(20, orig[self._drag_col] + self._total_dx)
        self.view.refresh()

    def draw_overlay(self, x0, y0, gc):
        res = self.find_box()
        if res is None:
            return
        tb, _ = res
        zoom = self.view.zoom
        lw = 2.0 / zoom
        gc.set_line_width(lw)
        # Draw separators; replace the dragged one with its preview position.
        x = 0
        for c, cw in enumerate(tb.col_widths):
            eff_w = (self._preview_width
                     if c == self._drag_col and self._preview_width is not None
                     else cw)
            x += eff_w
            draw_x = x0 + x
            if c == self._drag_col:
                gc.set_source_rgb(0.0, 0.4, 1.0)
            else:
                gc.set_source_rgb(0.45, 0.45, 0.45)
            gc.move_to(draw_x, y0)
            gc.line_to(draw_x, y0 + tb.height)
            gc.stroke()

    def commit(self):
        if self._preview_width is not None:
            tb    = self._table_box
            texel = tb._source if tb else None
            if texel is not None:
                widths = list(self._drag_orig_widths)
                widths[self._drag_col] = self._preview_width
                self.view.set_texel_attributes(self._ti1, Table, col_widths=widths)
                self.install(self.view, self.index)
                assert self._table_box is not None
        self._drag_col         = None
        self._drag_orig_widths = None
        self._preview_width    = None

    def get_handles(self):
        # TableEditor uses hit_test directly; no generic handles
        return iter([])


def demo_00():
    """TableEditor demo: drag column separators to resize columns."""
    import wx
    from .tables import mk_table
    from .document import Document
    from .documentview import DocumentView

    doc = Document()
    doc.textmodel.texel = mk_table([['Name',     'City',       'Country'],
                                    ['Einstein', 'Ulm',        'Germany'],
                                    ['Darwin',   'Shrewsbury', 'England']])

    app   = wx.App(False)
    frame = wx.Frame(None, title='TableEditor demo', size=(420, 300))
    view  = DocumentView(frame, doc)
    view.install_editor(TableEditor(), 1)
    frame.Show()
    app.MainLoop()
