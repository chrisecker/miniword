import wx
from .editorbase import Editor
from .tables import Table, TableBox

_HIT_RADIUS = 5          # hit detection radius in screen pixels
_CM         = 72.0 / 2.54  # 1 cm in pt


def _draw_arrowhead(gc, tip_x, y, direction, length, half_h):
    """Filled triangle arrowhead. direction: +1 = points right, -1 = points left."""
    base_x = tip_x - direction * length
    gc.move_to(tip_x, y)
    gc.line_to(base_x, y - half_h)
    gc.line_to(base_x, y + half_h)
    gc.close_path()
    gc.fill()


def _draw_dimension(gc, x_left, x_right, y, width_pt, zoom):
    """Draw  ◄── 7.2 cm ──►  dimension annotation at document y-coordinate y.

    All sizes are pixel-constant (divided by zoom so Cairo's scale does the rest).
    If the label does not fit inside the column, arrows point outward and the
    label is placed to the right of the right edge.
    """
    label     = f'{width_pt / _CM:.1f} cm'
    px        = 1.0 / zoom
    arr_len   = 6  * px
    arr_h     = 3  * px
    tick_h    = 4  * px
    font_size = 8  * px
    gap       = 2  * px
    span      = x_right - x_left

    gc.set_source_rgba(0.0, 0.35, 0.9, 1.0)
    gc.set_line_width(px)

    # Vertical end ticks
    for tx in (x_left, x_right):
        gc.move_to(tx, y - tick_h)
        gc.line_to(tx, y + tick_h)
        gc.stroke()

    # Measure label
    gc.set_font_size(font_size)
    te = gc.text_extents(label)
    tw = te[4]                        # x-advance
    # baseline offset to visually center text on y
    text_dy = -te[1] - te[3] / 2

    if span >= tw + 2 * (arr_len + gap):
        # Label fits inside: inward arrows, line interrupted for text
        _draw_arrowhead(gc, x_left,  y, +1, arr_len, arr_h)
        _draw_arrowhead(gc, x_right, y, -1, arr_len, arr_h)
        text_x = x_left + (span - tw) / 2
        gc.move_to(x_left  + arr_len, y)
        gc.line_to(text_x  - gap, y)
        gc.stroke()
        gc.move_to(text_x  + tw + gap, y)
        gc.line_to(x_right - arr_len, y)
        gc.stroke()
        gc.move_to(text_x, y + text_dy)
    else:
        # Column too narrow: outward arrows, full line, label to the right
        _draw_arrowhead(gc, x_left,  y, -1, arr_len, arr_h)
        _draw_arrowhead(gc, x_right, y, +1, arr_len, arr_h)
        gc.move_to(x_left, y)
        gc.line_to(x_right, y)
        gc.stroke()
        gc.move_to(x_right + 3 * gap, y + text_dy)

    gc.show_text(label)


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

    Modifier keys during drag:
      plain  — only the left column changes; total table width varies.
      Shift  — left and right column exchange width; total stays constant.
      Ctrl   — left column changes, all columns to the right scale
               proportionally; total stays constant.
    """

    _drag_col         = None
    _drag_orig_widths = None
    _preview_widths   = None   # full width list while dragging

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
        self._preview_widths   = None
        self.view.refresh()

    def _compute_preview_widths(self, dx, event):
        orig = self._drag_orig_widths
        col  = self._drag_col
        n    = len(orig)
        widths = list(orig)

        if event.ShiftDown() and col + 1 < n:
            # Shift: only left + right column change; total width stays constant.
            max_dx = orig[col + 1] - 20   # right can shrink to min
            min_dx = -(orig[col] - 20)    # left can shrink to min
            delta  = max(min_dx, min(max_dx, dx))
            widths[col]     = orig[col]     + delta
            widths[col + 1] = orig[col + 1] - delta

        elif event.ControlDown() and col + 1 < n:
            # Ctrl: left column changes, all columns to the right scale proportionally.
            new_left    = max(20, orig[col] + dx)
            delta       = new_left - orig[col]
            total_right = sum(orig[col + 1:])
            new_total   = total_right - delta
            min_total   = (n - col - 1) * 20
            if new_total < min_total:
                new_total = min_total
                new_left  = orig[col] + (total_right - new_total)
            widths[col] = new_left
            factor = new_total / total_right if total_right > 0 else 1.0
            for i in range(col + 1, n):
                widths[i] = max(20, orig[i] * factor)

        else:
            widths[col] = max(20, orig[col] + dx)

        return widths

    def on_motion(self, event):
        if self._drag_col is None:
            return
        p  = self.window_to_box(event.Position)
        dx = p[0] - self._drag_start[0]
        self._preview_widths = self._compute_preview_widths(dx, event)
        self.view.refresh()

    def draw_overlay(self, gc):
        res = self.find_box()
        if res is None:
            return
        tb, _ = res
        widths = self._preview_widths if self._preview_widths is not None else tb.col_widths
        orig   = self._drag_orig_widths or tb.col_widths
        zoom   = self.view.zoom
        x      = 0
        for c, cw in enumerate(widths):
            x_col = x
            x    += cw
            changed = self._preview_widths is not None and widths[c] != orig[c]
            gc.set_line_width(2.0 / zoom)
            gc.set_source_rgb(0.0, 0.4, 1.0) if changed else gc.set_source_rgb(0.45, 0.45, 0.45)
            gc.move_to(x, 0)
            gc.line_to(x, tb.height)
            gc.stroke()
            if changed:
                _draw_dimension(gc, x_col, x, -8 / zoom, widths[c], zoom)

    def commit(self):
        if self._preview_widths is not None:
            self.view.set_texel_attributes(self._ti1, Table, col_widths=self._preview_widths)
            self.install(self.view, self.index)
            assert self._table_box is not None
        self._drag_col         = None
        self._drag_orig_widths = None
        self._preview_widths   = None

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
