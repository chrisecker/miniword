# XXX TODO: rewrite this

"""TableBox rendering for Table texels."""

from ..layout.boxes import Box, TextBox, EmptyTextBox, EMPTYSTYLE
from ..layout.testdevice import TESTDEVICE
from .tables import from_strings


# ---------------------------------------------------------------------------
# CellBox
# ---------------------------------------------------------------------------

class CellBox(Box):
    """Vertical stack of wrapped lines for a table cell."""
    def __init__(self, rows, device=None, hpad=0, vpad=0, style=None):
        if device is not None:
            self.device = device
        self.style = style or {}
        self._rows = rows
        self._lpad = hpad // 2
        self._tpad = vpad // 2
        total_h = sum(r.height + r.depth for r in rows)
        w, h, d = self.device.measure("M", self.style)
        self.fill = max(0, h + d - total_h)
        self.height = self.fill + total_h + vpad
        self.depth = 0
        self.width = (max((r.width for r in rows), default=0)
                      if rows else 0) + hpad
        # length = sum of row lengths + 1 for trailing separator
        self.length = sum(len(r) for r in rows) + 1

    def __len__(self):
        return self.length

    def get_index(self, x, y):
        y_rel = y - self.fill - self._tpad
        x_rel = x - self._lpad
        cy = 0
        offset = 0
        for row in self._rows:
            if y_rel <= cy + row.height + row.depth or row is self._rows[-1]:
                return offset + row.get_index(x_rel, y_rel - cy)
            cy += row.height + row.depth
            offset += len(row)
        return self.length - 1

    def iter_boxes(self, i, x, y):
        x0 = x + self._lpad
        y0 = y + self.fill + self._tpad
        j = i
        for row in self._rows:
            yield j, j + len(row), x0, y0, row
            y0 += row.height + row.depth
            j += len(row)


# ---------------------------------------------------------------------------
# TableBox
# ---------------------------------------------------------------------------

class TableBox(Box):
    """A n_rows × n_cols table box."""
    prev       = None  # previous fragment in page-split chain (None = first)
    next       = None  # next fragment in page-split chain (None = last)
    row_offset = 0     # index of first row in the original table

    def __init__(self, cells, col_widths, row_heights,
                 header_rows=0, break_level=0, device=None,
                 is_continuation=False):
        if device is not None:
            self.device = device
        self.cells       = cells
        self.col_widths  = col_widths
        self.row_heights = row_heights
        self.n_rows      = len(cells)
        self.n_cols      = len(cells[0]) if cells else 0
        self.header_rows = header_rows
        self.break_level = break_level
        self.width       = sum(col_widths)
        self.height      = sum(row_heights)
        self.depth       = 0
        self.offsets = {}
        # Continuation fragments do not own the leading separator of the
        # Table texel (it belongs to the first fragment), so start at 0.
        i = 0 if is_continuation else 1
        for r, row in enumerate(cells):
            for c, cell in enumerate(row):
                self.offsets[(r, c)] = i
                i += len(cell)
        self.length = i

    def get_texel_offset(self):
        box = self
        i = 0
        while box.prev:
            box = box.prev
            i -= len(box)
        return i
            
    def __len__(self):
        return self.length

    def iter_boxes(self, i0, x0, y0):
        y = y0
        for r, row in enumerate(self.cells):
            x = x0
            rh = self.row_heights[r]
            for c, cell in enumerate(row):
                ci1 = i0 + self.offsets[(r, c)]
                valign = cell.style.get('valign', 'top')
                content_h = cell.height + cell.depth
                if valign == 'middle':
                    oy = (rh - content_h) / 2
                elif valign == 'bottom':
                    oy = rh - content_h
                else:
                    oy = 0
                yield ci1, ci1 + len(cell), x, y + oy, cell
                x += self.col_widths[c]
            y += rh

    def get_index(self, x, y):
        cy = 0
        for r, rh in enumerate(self.row_heights):
            if y < cy + rh or r == self.n_rows - 1:
                cx = 0
                for c, cw in enumerate(self.col_widths):
                    if x < cx + cw or c == self.n_cols - 1:
                        cell = self.cells[r][c]
                        return self.offsets[(r, c)] + cell.get_index(x - cx, y - cy)
                    cx += cw
            cy += rh
        return self.length

    def draw_selection(self, i1, i2, x, y, dc):
        if i1 <= 0 and i2 >= len(self):
            self.device.invert_rect(x, y, self.width, self.height + self.depth, dc)
        else:
            Box.draw_selection(self, i1, i2, x, y, dc)

    def draw(self, x, y, dc):
        # _origin is used by MatrixEditor.draw_selection to locate this fragment
        # on screen. It is set here because draw() is the only moment a box
        # knows its own screen coordinates. draw() is called before
        # draw_selection() in every paint cycle, so the value is always fresh.
        # Fragments not currently visible are never drawn, so their _origin
        # stays unset — draw_selection skips them via getattr(..., None).
        self._origin = (x, y)
        # 1. cell backgrounds
        cy = y
        for r in range(self.n_rows):
            rh = self.row_heights[r]
            cx = x
            for c in range(self.n_cols):
                bgcolor = self.cells[r][c].style.get('cell_bgcolor')
                if bgcolor:
                    self.device.fill_rect(cx, cy, self.col_widths[c], rh, bgcolor, dc)
                cx += self.col_widths[c]
            cy += rh
        # 2. cell content
        Box.draw(self, x, y, dc)
        # 3. cell borders
        cy = y
        for r in range(self.n_rows):
            rh = self.row_heights[r]
            cx = x
            for c in range(self.n_cols):
                draw_cell_borders(self, r, c, cx, cy, self.col_widths[c], rh, dc)
                cx += self.col_widths[c]
            cy += rh

    def draw_background(self, x, y, dc):
        pass


# ---------------------------------------------------------------------------
# Border drawing helpers
# ---------------------------------------------------------------------------

BORDER_PEN = {
    'thin':  (0.5, (0, 0, 0)),
    'thick': (1.5, (0, 0, 0)),
}

DOUBLE_GAP  = 2.0   # gap between the two lines in pt
DOUBLE_WIDTH = 0.5


def draw_cell_borders(tbox, r, c, cx, cy, cw, rh, dc):
    for side, x1, y1, x2, y2 in [
        ('top',    cx,      cy,      cx + cw, cy),
        ('bottom', cx,      cy + rh, cx + cw, cy + rh),
        ('left',   cx,      cy,      cx,      cy + rh),
        ('right',  cx + cw, cy,      cx + cw, cy + rh),
    ]:
        if side == 'top' and r > 0:
            continue  # top neighbor's bottom draws this line
        if side == 'left' and c > 0:
            continue  # left neighbor's right draws this line

        style = tbox.cells[r][c].style
        border = style.get('border_' + side, 'thin')

        if side == 'right' and c + 1 < tbox.n_cols:
            border = tbox.cells[r][c + 1].style.get('border_left', 'thin')
        elif side == 'bottom' and r + 1 < tbox.n_rows:
            border = tbox.cells[r + 1][c].style.get('border_top', 'thin')

        if border == 'none' or border is None:
            continue

        if border == 'double':
            g = DOUBLE_GAP / 2
            if y1 == y2:  # horizontal
                tbox.device.draw_line(x1, y1 - g, x2, y2 - g, DOUBLE_WIDTH, dc)
                tbox.device.draw_line(x1, y1 + g, x2, y2 + g, DOUBLE_WIDTH, dc)
            else:          # vertical
                tbox.device.draw_line(x1 - g, y1, x2 - g, y2, DOUBLE_WIDTH, dc)
                tbox.device.draw_line(x1 + g, y1, x2 + g, y2, DOUBLE_WIDTH, dc)
        else:
            pen_info = BORDER_PEN.get(border, BORDER_PEN['thin'])
            tbox.device.draw_line(x1, y1, x2, y2, pen_info[0], dc)


# ---------------------------------------------------------------------------
# Split helpers
# ---------------------------------------------------------------------------

def split_at_height(box, height):
    """Split box so that the first fragment fits within height.

    Returns (frag, rest). rest is None if everything fits.
    """
    header_h   = sum(box.row_heights[:box.header_rows])
    space      = height - header_h
    body_start = box.header_rows
    used, nfit = 0, 0
    for r in range(body_start, box.n_rows):
        rh = box.row_heights[r]
        if used + rh > space and nfit > 0:
            break
        nfit += 1
        used += rh
    split_at = body_start + nfit
    if split_at >= box.n_rows:
        return box, None
    return split_table_box(box, split_at)


def split_table_box(tablebox, nrows):
    """Split tablebox after nrows rows. Returns (box1, box2).

    box1 contains the first nrows rows; box2 the remainder as a continuation
    (no leading separator in its length). prev/next are set on both boxes.
    """
    box1 = TableBox(
        tablebox.cells[:nrows],
        tablebox.col_widths,
        tablebox.row_heights[:nrows],
        header_rows = min(tablebox.header_rows, nrows),
        break_level = tablebox.break_level,
        device      = tablebox.device,
        is_continuation = tablebox.prev is not None
    )
    box2 = TableBox(
        tablebox.cells[nrows:],
        tablebox.col_widths,
        tablebox.row_heights[nrows:],
        header_rows     = 0,
        break_level     = tablebox.break_level,
        device          = tablebox.device,
        is_continuation = True,
    )
    box1.prev = tablebox.prev
    box1.next = box2
    box2.prev = box1
    box2.next = tablebox.next
    if tablebox.prev is not None:
        tablebox.prev.next = box1
    if tablebox.next is not None:
        tablebox.next.prev = box2
    return box1, box2


# ---------------------------------------------------------------------------
# Navigation helper
# ---------------------------------------------------------------------------

class TableNavRow:
    """Proxy for one row of a TableBox used by DocumentView.iter_rows.

    Behaves like a row box for the purpose of up/down cursor navigation:
    get_index returns a local index within the parent TableBox.
    """
    depth = 0

    def __init__(self, table, r):
        self._table = table
        self._r     = r
        self.height = table.row_heights[r]

    def get_index(self, x, y):
        tb = self._table
        cx = 0
        for c, cw in enumerate(tb.col_widths):
            if x < cx + cw or c == tb.n_cols - 1:
                cell = tb.cells[self._r][c]
                return tb.offsets[(self._r, c)] + cell.get_index(x - cx, y)
            cx += cw
        return tb.offsets[(self._r, tb.n_cols - 1)]


# ---------------------------------------------------------------------------
# Constants used by table_factory.py
# ---------------------------------------------------------------------------

CELL_HPAD = 8   # horizontal padding per column
CELL_VPAD = 6   # vertical padding per row


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def mk_box_table(texts, col_width=60, row_height=14, device=None):
    """Build a TableBox directly from strings (for box-level tests)."""
    dev = device or TESTDEVICE
    from ..layout.pagegen import Row as PageRow
    cells = []
    for row_texts in texts:
        row = []
        for text in row_texts:
            rows = [PageRow([TextBox(text, EMPTYSTYLE, dev)], device=dev)]
            row.append(CellBox(rows, dev))
        cells.append(row)
    n_rows = len(cells)
    n_cols = len(cells[0]) if cells else 0
    return TableBox(cells, [col_width] * n_cols, [row_height] * n_rows, device=dev)


def test_11():
    "split_table_box divides rows, preserves total length, links prev/next"
    table = mk_box_table([['A', 'B'], ['C', 'D'], ['E', 'F']])
    b1, b2 = split_table_box(table, 2)
    assert b1.n_rows == 2
    assert b2.n_rows == 1
    assert len(b1) + len(b2) == len(table)
    assert b1.next is b2
    assert b2.prev is b1


def test_07():
    "navigation: TableNavRow.get_index selects the cell matching x at y=row_height"
    table = mk_box_table([['A', 'B', 'C'],
                          ['D', 'E', 'F']])
    nav = TableNavRow(table, 1)

    for x, expected_col in [(10, 0), (90, 1), (150, 2)]:
        i = nav.get_index(x, nav.height)
        ci1 = table.offsets[(1, expected_col)]
        ci2 = ci1 + len(table.cells[1][expected_col])
        assert ci1 <= i < ci2, f"x={x}: expected col {expected_col} [{ci1},{ci2}), got {i}"


def test_08():
    "navigation: for a multi-line cell, get_index at y=height lands in the last row"
    from ..layout.pagegen import Row as PageRow
    dev = TESTDEVICE
    row1 = PageRow([TextBox('top',    EMPTYSTYLE, dev)], device=dev)
    row2 = PageRow([TextBox('bottom', EMPTYSTYLE, dev)], device=dev)
    cell = CellBox([row1, row2], dev)

    i = cell.get_index(0, cell.height)
    assert i >= len(row1), f"expected index in row2 (>={len(row1)}), got {i}"


def test_09():
    "navigation: Up from top of row r lands at bottom of multi-line cells in row r-1"
    from ..layout.pagegen import Row as PageRow
    dev = TESTDEVICE

    def make_cell(*texts):
        rows = [PageRow([TextBox(t, EMPTYSTYLE, dev)], device=dev) for t in texts]
        return CellBox(rows, dev)

    row0 = [make_cell('line1', 'line2'), make_cell('lineA', 'lineB')]
    row1 = [make_cell('X'),              make_cell('Y')]

    col_widths  = [100, 100]
    row_heights = [max(c.height + c.depth for c in row) for row in [row0, row1]]
    table = TableBox([row0, row1], col_widths, row_heights, device=dev)

    nav0 = TableNavRow(table, 0)

    for x, col in [(20, 0), (120, 1)]:
        i = nav0.get_index(x, nav0.height)
        ci1 = table.offsets[(0, col)]
        ci2 = ci1 + len(table.cells[0][col])
        assert ci1 <= i < ci2, f"x={x}: expected col {col} [{ci1},{ci2}), got {i}"

        len_first_row = len(row0[col]._rows[0])
        assert i - ci1 >= len_first_row, (
            f"x={x}: expected bottom row (offset>={len_first_row}), got {i - ci1}"
        )



# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_00():
    """Interactive demo: click and shift-click to select cells."""
    import wx
    from ..core.document import Document
    from ..texteditor import TextEditor

    TEXTS = [['Name',     'City',       'Country'],
             ['Einstein', 'Ulm',        'Germany'],
             ['Darwin',   'Shrewsbury', 'England'],
             ['Curie',    'Warsaw',     'Poland'],
             ['', '', '']] # empty last row!

    doc = Document()
    doc.textmodel.texel = from_strings(TEXTS)

    app   = wx.App(redirect=False)
    frame = wx.Frame(None, title='Table demo', size=(420, 420))
    view  = TextEditor(frame, doc)
    frame.Show()
    from ..wxtextview import testing
    testing.pyshell(locals())
    app.MainLoop()
