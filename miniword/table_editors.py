import wx
from .editorbase import Editor
from .tables import Table
from .table_boxes import TableBox

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
    """Draw  ◄── 7.2 cm ──►  dimension annotation at document y-coordinate y."""
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

    for tx in (x_left, x_right):
        gc.move_to(tx, y - tick_h)
        gc.line_to(tx, y + tick_h)
        gc.stroke()

    gc.set_font_size(font_size)
    te = gc.text_extents(label)
    tw = te[4]
    text_dy = -te[1] - te[3] / 2

    if span >= tw + 2 * (arr_len + gap):
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


def is_multi_cell(texel, i1, i2):
    """Return True if the range [i1, i2) spans more than one cell.

    i1 and i2 are texel-local indices.
    """
    try:
        r1, c1, r2, c2 = texel.get_rect(i1, i2)
    except (IndexError, TypeError):
        return False
    return r1 != r2 or c1 != c2


class TableEditorBase(Editor):
    """Base class for table editors. Provides column-resize drag for both modes."""

    _drag_col         = None
    _drag_orig_widths = None
    _preview_widths   = None

    def install(self, view, index):
        self._drag_handle = None
        self.view  = view
        self.index = index
        res = _find_table_at(view.layout, index)
        if res is None:
            self._table_box = None
            return
        self._table_box, tx, ty, self._ti1, self._ti2 = res
        self.box_index   = self._ti1
        self.texel_index = self._ti1 - self._table_box.base_offset
        self.position = tx, ty

    def find_box(self):
        res = _find_table_at(self.view.layout, self.index)
        if res is None:
            return None
        tb, cx, cy, ci1, ci2 = res
        return tb, (cx, cy)

    def get_cursor(self, handle_id):
        return wx.CURSOR_SIZEWE

    def hit_test(self, x, y):
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
            max_dx = orig[col + 1] - 20
            min_dx = -(orig[col] - 20)
            delta  = max(min_dx, min(max_dx, dx))
            widths[col]     = orig[col]     + delta
            widths[col + 1] = orig[col + 1] - delta

        elif event.ControlDown() and col + 1 < n:
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
        if self._table_box is None:
            return
        tb = self._table_box
        bx, by = self.position
        widths = self._preview_widths if self._preview_widths is not None else tb.col_widths
        orig   = self._drag_orig_widths or tb.col_widths
        zoom   = self.view.zoom
        x      = 0
        for c, cw in enumerate(widths):
            x_col = x
            x    += cw
            changed = self._preview_widths is not None and widths[c] != orig[c]
            gc.set_line_width(2.0 / zoom)
            if changed:
                gc.set_source_rgb(0.0, 0.4, 1.0)
            else:
                gc.set_source_rgb(0.45, 0.45, 0.45)
            gc.move_to(bx + x, by)
            gc.line_to(bx + x, by + tb.height)
            gc.stroke()
            if changed:
                _draw_dimension(gc, bx + x_col, bx + x, by - 8 / zoom, widths[c], zoom)

    def commit(self):
        if self._preview_widths is not None:
            self.view.set_texel_attributes(self._ti1, Table, col_widths=self._preview_widths)
            self.install(self.view, self.index)
            assert self._table_box is not None
        self._drag_col         = None
        self._drag_orig_widths = None
        self._preview_widths   = None

    def get_handles(self):
        return iter([])


class CursorEditor(TableEditorBase):
    """Active while cursor is inside a table cell (text-editing mode).

    Uses default draw() — cursor + selection + column-separator overlay.
    """

    @staticmethod
    def condition(view, index_texels, sel_texels):
        res = _find_table_at(view.layout, view.index)
        if res is None:
            return False
        sel = view.selection
        if sel is None:
            return True
        tb, cx, cy, ci1, ci2 = res
        texel_index = ci1 - tb.base_offset
        abs_s1, abs_s2 = sorted(sel)
        return not is_multi_cell(tb.texel, abs_s1 - texel_index, abs_s2 - texel_index)


class MatrixEditor(TableEditorBase):
    """Active when the selection spans multiple table cells (structure mode).

    Overrides draw() to suppress the text cursor and render rectangular
    cell-block highlights; column-resize drag is inherited from TableEditorBase.
    """

    @staticmethod
    def condition(view, index_texels, sel_texels):
        res = _find_table_at(view.layout, view.index)
        if res is None:
            return False
        sel = view.selection
        if sel is None:
            return False
        tb, cx, cy, ci1, ci2 = res
        texel_index = ci1 - tb.base_offset
        abs_s1, abs_s2 = sorted(sel)
        return is_multi_cell(tb.texel, abs_s1 - texel_index, abs_s2 - texel_index)

    def draw(self, gc):
        """No text cursor; rectangular cell-block selection + column-separator overlay."""
        res = _find_table_at(self.view.layout, self.index)
        if res is None:
            return
        tb, bx, by, ci1, ci2 = res
        sel = self.view.selection
        if sel is not None:
            abs_s1, abs_s2 = sorted(sel)
            tb.draw_matrix_selection(abs_s1 - ci1, abs_s2 - ci1, bx, by, gc)
        self.draw_overlay(gc)
        self.draw_handles(gc)


def demo_00():
    """CursorEditor demo: drag column separators to resize columns."""
    from .tables import from_strings
    from .document import Document
    from .documentview import DocumentView

    doc = Document()
    doc.textmodel.texel = from_strings([['Name',     'City',       'Country'],
                                        ['Einstein', 'Ulm',        'Germany'],
                                        ['Darwin',   'Shrewsbury', 'England']])

    app   = wx.App(False)
    frame = wx.Frame(None, title='CursorEditor demo', size=(420, 300))
    view  = DocumentView(frame, doc)
    view.install_editor(CursorEditor(), 1)
    frame.Show()
    app.MainLoop()
