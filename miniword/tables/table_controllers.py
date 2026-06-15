"""We define two controllers for tables. Default is CursorController, which
is only valid when the selection is inside one table cell. When several
cells are included in the selection, the editor switches to MatrixController.

When the selection is inside one cell both controllers match. This
ambiguity is solved by the preference (CursorController registers first
and therefore has the heigher priority) or by the user (there will be
a selection-button in the editor panel. The selected controller remains as
long as it matches.

"""


import wx
from ..texteditor.boxcontroller import BoxController
from ..texteditor.actions import create_ctx
from .tables import Table, from_cells
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
    font_size = 12  * px
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




def is_multi_cell(texel, i1, i2):
    """Return True if the range [i1, i2) spans more than one cell.

    i1 and i2 are texel-local indices.
    """
    r1, c1, r2, c2 = texel.get_rect(i1, i2)
    return r1 != r2 or c1 != c2


class TableControllerBase(BoxController):
    """Base class for table controllers. """

    _drag_orig_widths = None
    _preview_widths   = None

    def find_box(self):
        """
        Return (ci1, (cx, cy), TableBox) for the box containing index.
        ci1 is a local index (like self.i1).

        Raises: IndexError when no Box is found.
        """
        editor = self.editor
        layout = editor.canvas.layout
        index = editor.abs_idx(editor.index)

        def visit(p1, p2, x, y, box):
            if not (p1 <= index < p2):
                return None
            if isinstance(box, TableBox):
                if editor.abs_idx(self.i1) == p1 + box.get_texel_offset():
                    return editor.local_idx(p1), (x, y), box
            for c1, c2, cx, cy, child in box.iter_boxes(p1, x, y):
                result = visit(c1, c2, cx, cy, child)
                if result:
                    return result
            return None

        for p1, p2, px, py, page in layout.iter_boxes(editor.flow):
            result = visit(p1, p2, px, py, page)
            if result:
                return result

        raise IndexError(index)

    def get_cursor(self, handle_id):
        return wx.CURSOR_SIZEWE

    def hit_test(self, x, y):
        tb = self.box
        if tb is None:
            return None
        if not (0 <= y <= tb.height):
            return None
        hit_r = _HIT_RADIUS / self.editor.canvas.zoom
        sep_x = 0
        for col, cw in enumerate(tb.col_widths):
            sep_x += cw
            if abs(x - sep_x) <= hit_r:
                return col
        return None

    def start_drag(self, handle, x, y):
        self._drag_orig_widths = list(self.box.col_widths)
        self._preview_widths   = None
        super().start_drag(handle, x, y)

    def clear_drag(self):
        super().clear_drag()
        self._drag_orig_widths = None
        self._preview_widths   = None

    def _compute_preview_widths(self, dx, shift, ctrl):
        orig = self._drag_orig_widths
        col  = self._drag_handle
        n    = len(orig)
        widths = list(orig)

        if shift and col + 1 < n:
            max_dx = orig[col + 1] - 20
            min_dx = -(orig[col] - 20)
            delta  = max(min_dx, min(max_dx, dx))
            widths[col]     = orig[col]     + delta
            widths[col + 1] = orig[col + 1] - delta

        elif ctrl and col + 1 < n:
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

    def drag_handle(self, handle, dx, dy, shift, ctrl):
        self._preview_widths = self._compute_preview_widths(dx, shift, ctrl)

    def draw_overlay(self, gc):
        tb = self.box
        bx, by = self.box_origin
        widths = self._preview_widths if self._preview_widths is not None else \
            tb.col_widths
        orig   = self._drag_orig_widths or tb.col_widths
        zoom   = self.editor.canvas.zoom
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
                _draw_dimension(gc, bx+x_col, bx+x, by-8/zoom, widths[c], zoom)

    def commit(self):
        widths = self._preview_widths
        if widths is not None:
            self.editor.set_texel_attributes(
                self.i1, self.texel, col_widths=widths)

    def get_handles(self):
        return iter([])


class CursorController(TableControllerBase):
    """
    Controller for selections inside a cell. 
    """

    @classmethod
    def match(cls, view, path):
        e = None
        for depth, (i1, i2, texel) in enumerate(path):
            if isinstance(texel, Table):
                sel = view.selection
                if sel is None or sel[0] == sel[1]:
                    e = cls(view, texel, i1, i2, depth)
                else:
                    s1, s2 = sorted(sel)
                    if s1 <= i1 or i2 <= s2:
                        e = None  # selection not inside cell area
                    elif not is_multi_cell(texel, s1-i1, s2-i1):
                        e = cls(view, texel, i1, i2, depth)
                    else:
                        e = None
        return e

    def handle_action(self, action, shift):
        if action not in ('move_up', 'move_down'):
            return super().handle_action(action, shift)
        editor = self.editor
        ctx = create_ctx(editor)
        flow = editor.flow
        i = ctx.aindex
        texel = self.texel
        row, col = texel.get_coord(ctx.index - self.i1)
        cells = texel.get_cells()

        if action == 'move_up':
            prev = ctx.layout.prev_row(i, flow)
            if prev is not None and prev[0] >= ctx.model.get_start(i):
                editor.move_up(shift)
                return True
            if row == 0:
                return False
            row -= 1
            target_i = self.i1 + cells[row][col].i2 - 2  # last content pos in cell above
        else:
            nxt = ctx.layout.next_row(i, flow)
            if nxt is not None and nxt[1] <= ctx.model.get_end(i):
                editor.move_down(shift)
                return True
            if row == texel.nrows - 1:
                return False
            row += 1
            target_i = self.i1 + cells[row][col].i1  # first content pos in cell below

        x = ctx.layout.get_rect(i, flow).x1
        row_info = ctx.layout.find_row(editor.abs_idx(target_i), flow)
        if row_info is None:
            return False
        r1, r2, rx, ry, row_box = row_info
        j = r1 + row_box.get_index(x - rx, row_box.height)
        editor.set_index(editor.local_idx(j), shift)
        return True

    
class MatrixController(TableControllerBase):
    """
    Controller for matrix like selections which can span several cells.
    """

    @classmethod
    def match(cls, view, path):
        sel = view.selection
        if sel is None:
            return None
        s1, s2 = sorted(sel)
        e = None
        for depth, (i1, i2, texel) in enumerate(path):
            if isinstance(texel, Table):
                if s1 <= i1 or i2 <= s2:
                    e = None  # selection not inside cell area
                elif is_multi_cell(texel, s1-i1, s2-i1):
                    e = cls(view, texel, i1, i2, depth)
        return e

    def draw_cursor(self, gc):
        # Do not draw the cursor!
        pass

    def draw_selection(self, gc):
        """Highlight the rectangular cell block covered by the selection."""
        if not self.editor.has_selection():
            return
        s1, s2 = sorted(self.editor.selection)
        try:
            r1, c1, r2, c2 = self.texel.get_rect(s1 - self.i1, s2 - self.i1)
        except IndexError:
            return

        # Walk to the first fragment, then forward through the chain.
        # _origin is only set on fragments that were drawn in this paint
        # cycle (i.e. currently visible) — skip the rest.
        frag = self.box
        while frag.prev is not None:
            frag = frag.prev
        while frag is not None:
            origin = getattr(frag, '_origin', None)
            if origin is not None:
                self._draw_frag_selection(frag, r1, r2, c1, c2, origin, gc)
            frag = frag.next

    def _draw_frag_selection(self, frag, r1, r2, c1, c2, origin, gc):
        bx, by    = origin
        device    = frag.device
        cy = by
        for r_local in range(frag.n_rows):
            r_orig = frag.row_offset + r_local
            rh = frag.row_heights[r_local]
            if r1 <= r_orig <= r2:
                cx = bx
                for c, cw in enumerate(frag.col_widths):
                    if c1 <= c <= c2:
                        device.invert_rect(cx, cy, cw, rh, gc)                        
                    cx += cw
            cy += rh

    def selected(self, s1, s2):
        i1, i2 = s1 - self.i1, s2 - self.i1
        # While MatrixController is active, the selection must lie inside
        # the table (cell-range), excluding the boundary markers.
        assert 1 <= i1 and i2 < self.i2 - self.i1
        r1, c1, r2, c2 = self.texel.get_rect(i1, i2)
        return [(self.i1 + a, self.i1 + b)
                for a, b in self.texel.get_cell_ranges(r1, c1, r2, c2)]

    def copy(self):
        """Rectangular cell copy for multi-cell selections."""
        if not self.editor.has_selection():
            return
        s1, s2 = sorted(self.editor.selection)
        ci1   = self.i0_box
        model = self.editor.target
        i1, i2 = s1 - ci1, s2 - ci1

        r1, c1, r2, c2 = self.texel.get_rect(i1, i2)
        if r1 == r2 and c1 == c2:
            self.editor.canvas.to_clipboard(model.copy(ci1 + i1, ci1 + i2))
            return

        cells    = self.texel.get_cells()
        sub_grid = [cells[r][c1:c2 + 1] for r in range(r1, r2 + 1)]
        result   = model.create_textmodel()
        result.texel = from_cells(sub_grid)
        self.editor.canvas.to_clipboard(result)

    def handle_action(self, action, shift):
        ctx = create_ctx(self.editor)
        i = ctx.index
        texel = self.texel
        row, col = texel.get_coord(i-self.i1)
        if action == 'move_up':
            if row > 0:
                row -= 1
        elif action == 'move_down':
            if row < texel.nrows-1:
                row += 1
        elif action == 'move_left':
            if col > 0:
                col -= 1
        elif action == 'move_right':
            if col < texel.ncols-1:
                col += 1
        else:
            return False
        cells = texel.get_cells()        
        i = self.i1+cells[row][col].i1
        self.editor.set_index(i, shift)
        return True
        


### Register controllers

from ..texteditor.editor import Editor
Editor.controller_registry.append(CursorController)
Editor.controller_registry.append(MatrixController)


def test_00():
    "_draw_frag_selection calls invert_rect once per selected cell"
    from .table_boxes import mk_box_table
    from .tables import from_strings
    from ..layout.testdevice import TestDevice
    calls = []
    class CountingDevice(TestDevice):
        def invert_rect(self, x, y, w, h, dc):
            calls.append((x, y, w, h))

    texts = [['A', 'B', 'C'], ['D', 'E', 'F'], ['G', 'H', 'I']]
    table = mk_box_table(texts, device=CountingDevice())
    texel = from_strings(texts)

    class FakeLayout:
        def iter_boxes(self, flow):
            yield 0, len(table), 0, 0, table

    class FakeCanvas:
        layout = FakeLayout()

    class FakeView:
        canvas = FakeCanvas()
        index  = 0
        flow   = 0
        def abs_idx(self, i): return i
        def local_idx(self, i): return i

    controller = MatrixController(FakeView(), texel, 0, len(table), 0)

    # rows 0-1, cols 0-1 → 4 cells
    controller._draw_frag_selection(table, 0, 1, 0, 1, (0, 0), None)
    assert len(calls) == 4

    calls.clear()
    # single cell (1,2)
    controller._draw_frag_selection(table, 1, 1, 2, 2, (0, 0), None)
    assert len(calls) == 1


def test_04():
    "MatrixController.copy"
    from .table_factory import build_table_box
    from .tables import from_strings, Table
    from ..textmodel.textmodel import TextModel
    from ..textmodel.texeltree import length as texel_length
    from ..layout.factory import Factory
    from ..core.styles import testsheet
    from ..layout.testdevice import TESTDEVICE

    texts = [['A', 'B', 'C'], ['D', 'E', 'F'], ['G', 'H', 'I']]
    table = from_strings(texts)
    model = TextModel()
    model.texel = table
    factory = Factory(testsheet, TESTDEVICE)
    box = build_table_box(table, factory, row_height=14)

    copied_model = []
    class FakeLayout:
        def iter_boxes(self, flow):
            yield 0, len(box), 0, 0, box

    class FakeCanvas:
        layout = FakeLayout()
        def to_clipboard(self, m):
            copied_model.append(m)

    class FakeEditor:
        index     = 0
        flow      = 0
        selection = None
        target    = model
        canvas    = FakeCanvas()
        def has_selection(self):
            return self.selection is not None and self.selection[0] != self.selection[1]
        def abs_idx(self, i): return i
        def local_idx(self, i): return i

    controller = MatrixController(FakeEditor(), table, 0, texel_length(table), 0)

    s1 = box.offsets[(1, 0)]
    s2 = box.offsets[(2, 1)] + len(box.cells[2][1]) - 1
    controller.editor.selection = (s1, s2)

    controller.copy()
    assert len(copied_model) == 1
    result = copied_model[0]
    assert isinstance(result.texel, Table)
    assert result.texel.nrows == 2
    assert result.texel.ncols == 2


def test_05():
    "MatrixController.selected returns absolute positions"
    from .tables import from_strings
    from ..textmodel.texeltree import length as texel_length

    texts = [['A', 'B'], ['C', 'D']]
    table = from_strings(texts)
    offset = 5  # table does NOT start at position 0

    # find_box() needs a real layout to locate the table's box; selected()
    # itself only depends on texel and i1, so a canned find_box keeps this
    # test focused without building a full layout.
    class FakeController(MatrixController):
        def find_box(self):
            return self.i1, (0, 0), None

    class FakeView:
        selection = None

    controller = FakeController(FakeView(), table, offset, offset + texel_length(table), 0)

    # select the full table (both rows, both cols)
    s1, s2 = offset + 1, offset + texel_length(table) - 1
    ranges = controller.selected(s1, s2)
    # all returned positions must be >= offset
    for a, b in ranges:
        assert a >= offset, f"relative position leaked: {a} < offset {offset}"
        assert b >= offset, f"relative position leaked: {b} < offset {offset}"


def _setup_demo(frame, doc):
    from ..core.styles import testsheet
    from ..layout.factory import Factory
    from ..layout.cairodevice import CairoDevice
    from ..layout.pagebuilder import PageBuilder
    from ..texteditor.editor import Editor
    from ..texteditor.textcanvas import TextCanvas

    factory = Factory(testsheet, device=CairoDevice())
    builder = PageBuilder(doc.textmodel, factory)
    builder.rebuild()

    editor = Editor(doc.textmodel)
    canvas = TextCanvas(frame, doc.textmodel, builder, editor)
    editor.canvas = canvas
    return editor, canvas


def demo_00():
    """CursorEditor"""
    from .tables import from_strings
    from ..core.document import Document

    doc = Document()
    doc.textmodel.texel = from_strings([['Name',     'City',       'Country'],
                                        ['Einstein', 'Ulm',        'Germany'],
                                        ['Darwin',   'Shrewsbury', 'England']])

    app   = wx.App(True)
    frame = wx.Frame(None, title='CursorEditor demo', size=(420, 300))
    _setup_demo(frame, doc)
    frame.Show()
    app.MainLoop()


def demo_01():
    """Nested table: outer 2×2 with an inner table in cell (0, 1)."""
    from ..textmodel.texeltree import Text
    from .tables import Table, from_strings
    from ..core.document import Document

    inner = from_strings([['A', 'B'], ['C', 'D']])
    outer = Table(
        (Text('outer (0,0)'), {}), (inner,             {}),
        (Text('outer (1,0)'), {}), (Text('outer (1,1)'), {}),
        ncols=2,
    )

    doc = Document()
    doc.textmodel.texel = outer

    app   = wx.App(True)
    frame = wx.Frame(None, title='Nested table demo', size=(500, 300))
    _setup_demo(frame, doc)
    frame.Show()
    app.MainLoop()

