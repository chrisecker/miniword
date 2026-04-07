# XXX TODO: rewrite this

"""TableBox rendering for Table texels."""

from ..wxtextview.boxes import Box, TextBox, EmptyTextBox, NewlineBox, EMPTYSTYLE
from ..wxtextview.linewrap import simple_linewrap
from ..wxtextview.testdevice import TESTDEVICE
from ..textmodel.texeltree import length as texel_length
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
    prev      = None   # previous fragment in page-split chain (None = first)
    next      = None   # next fragment in page-split chain (None = last)
    orig_rows = None   # list of original row indices (set on fragments only)

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

    def __len__(self):
        return self.length

    def iter_boxes(self, i0, x0, y0):
        y = y0
        for r, row in enumerate(self.cells):
            x = x0
            for c, cell in enumerate(row):
                ci1 = i0 + self.offsets[(r, c)]
                yield ci1, ci1 + len(cell), x, y, cell
                x += self.col_widths[c]
            y += self.row_heights[r]

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
    'thin':   (0.5, (0, 0, 0)),
    'thick':  (1.5, (0, 0, 0)),
    'double': (0.5, (0, 0, 0)),
}


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

        pen_info = BORDER_PEN.get(border, BORDER_PEN['thin'])
        tbox.device.draw_line(x1, y1, x2, y2, pen_info[0], dc)


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
# Build TableBox from Table texel
# ---------------------------------------------------------------------------

CELL_HPAD = 8   # horizontal padding per column
CELL_VPAD = 6   # vertical padding per row


def build_cell(cell_texel, sep, col_width, factory):
    """Build a CellBox for one cell; cell style comes from the following separator."""
    if texel_length(cell_texel) == 0:
        line = EmptyTextBox(style=factory.mk_style({}), device=factory.device)
        return CellBox([line], factory.device, hpad=CELL_HPAD, vpad=CELL_VPAD,
                   style=getattr(sep, 'parstyle', {}))

    else:
        boxes = list(factory.create_all(cell_texel))

    # Split at NewlineBox (NL or BR inside the cell) so each segment is
    # wrapped independently, giving a real line break within the cell.
    segments, current = [], []
    for box in boxes:
        current.append(box)
        if isinstance(box, NewlineBox):
            segments.append(current)
            current = []
    if current:
        segments.append(current)

    all_lines = []
    for seg in segments:
        all_lines.extend(simple_linewrap(seg, col_width))

    from ..layout.pagegen import Row as PageRow
    rows = [PageRow(line, device=factory.device) for line in all_lines]
    return CellBox(rows, factory.device, hpad=CELL_HPAD, vpad=CELL_VPAD,
                   style=getattr(sep, 'parstyle', {}))


def build_table_box(texel, factory, row_height=None):
    """Build a TableBox from a Table texel using factory to create cell boxes."""
    n_rows, n_cols = texel.nrows, texel.ncols

    page_width = getattr(factory, 'line_width', 400)
    if texel.col_widths:
        explicit = [w for w in texel.col_widths if w is not None]
        n_auto = sum(1 for w in texel.col_widths if w is None)
        auto_w = ((page_width - sum(explicit)) / n_auto) if n_auto else 0
        col_widths_px = [w if w is not None else auto_w
                         for w in texel.col_widths]
    else:
        col_widths_px = [page_width / n_cols] * n_cols

    cell_texels = texel.childs[1::2]
    seps        = texel.childs[2::2]

    grid = []
    for r in range(n_rows):
        row = []
        for c in range(n_cols):
            idx = r * n_cols + c
            row.append(build_cell(cell_texels[idx], seps[idx], col_widths_px[c], factory))
        grid.append(row)

    col_widths_out = [max(col_widths_px[c],
                          max(grid[r][c].width for r in range(n_rows)))
                      for c in range(n_cols)]
    if row_height is None:
        row_heights = [max(grid[r][c].height + grid[r][c].depth
                          for c in range(n_cols))
                       for r in range(n_rows)]
    else:
        row_heights = [row_height] * n_rows

    return TableBox(grid, col_widths_out, row_heights,
                    header_rows=texel.nheader,
                    break_level=texel.breaklevel,
                    device=factory.device)


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


def test_03():
    "build_table_box produces TableBox with correct length"
    from ..wxtextview.builder import Factory
    texts = [['Hi', 'World'], ['Foo', 'Bar']]
    table = from_strings(texts)
    factory = Factory()
    box = build_table_box(table, factory, row_height=14)
    assert isinstance(box, TableBox)
    assert len(box) == texel_length(table)


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



def test_10():
    "extend_range snaps to full table when touching leading separator"
    table = mk_box_table([['A', 'B'], ['C', 'D']])
    n = len(table)
    # position 0 is the leading separator — snaps to full table
    assert table.extend_range(0, 1) == (0, n)
    # position 1 is inside the first cell — no snap
    assert table.extend_range(1, 2) == (1, 2)
    # overshooting also snaps (overshoot is preserved, start clamps to 0)
    assert table.extend_range(1, n + 1) == (0, n + 1)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_00():
    """Interactive demo: click and shift-click to select cells."""
    import wx
    from ..core.document import Document
    from ..ui.documentview import DocumentView

    TEXTS = [['Name',     'City',       'Country'],
             ['Einstein', 'Ulm',        'Germany'],
             ['Darwin',   'Shrewsbury', 'England'],
             ['Curie',    'Warsaw',     'Poland'],
             ['', '', '']] # empty last row!

    doc = Document()
    doc.textmodel.texel = from_strings(TEXTS)

    app   = wx.App(redirect=False)
    frame = wx.Frame(None, title='Table demo', size=(420, 420))
    view  = DocumentView(frame, doc)
    frame.Show()
    from ..wxtextview import testing
    testing.pyshell(locals())
    app.MainLoop()
