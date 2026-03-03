"""TableBox: a rectangular grid box with per-cell selection via get_ranges()."""

from .boxes import Box, VBox, HBox, TextBox, NewlineBox, calc_length, EMPTYSTYLE


class TableBox(Box):
    """A n_rows × n_cols table.

    cells       -- 2-D list [row][col] of Box
    col_widths  -- list of column widths
    row_heights -- list of row heights (height+depth per row)

    get_ranges(i1, i2) returns one (ci1, ci2) per cell in the
    rectangular selection between the anchor cell (containing i1)
    and the cursor cell (containing i2).
    """

    def __init__(self, cells, col_widths, row_heights, device=None):
        if device is not None:
            self.device = device
        self.cells       = cells
        self.col_widths  = col_widths
        self.row_heights = row_heights
        self.n_rows      = len(cells)
        self.n_cols      = len(cells[0]) if cells else 0
        self.width       = sum(col_widths)
        self.height      = sum(row_heights)
        self.depth       = 0
        # Precompute character offset to the start of each cell.
        self._offsets = {}   # (r, c) -> i1
        i = 0
        for r, row in enumerate(cells):
            for c, cell in enumerate(row):
                self._offsets[(r, c)] = i
                i += len(cell)
        self.length = i

    def __len__(self):
        return self.length

    def iter_boxes(self, i0, x0, y0):
        y = y0
        for r, row in enumerate(self.cells):
            x = x0
            for c, cell in enumerate(row):
                ci1 = i0 + self._offsets[(r, c)]
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
                        return self._offsets[(r, c)] + cell.get_index(x - cx, y - cy)
                    cx += cw
            cy += rh
        return self.length

    def _find_cell(self, i):
        """Return (r, c) of the cell containing character index i."""
        for r in range(self.n_rows):
            for c in range(self.n_cols):
                ci1 = self._offsets[(r, c)]
                ci2 = ci1 + len(self.cells[r][c])
                if ci1 <= i < ci2:
                    return r, c
        return self.n_rows - 1, self.n_cols - 1

    def get_ranges(self, i1, i2):
        ar, ac = self._find_cell(i1)
        cr, cc = self._find_cell(max(i1, i2 - 1))
        r1, r2 = min(ar, cr), max(ar, cr)
        c1, c2 = min(ac, cc), max(ac, cc)
        return [(self._offsets[(r, c)],
                 self._offsets[(r, c)] + len(self.cells[r][c]))
                for r in range(r1, r2 + 1)
                for c in range(c1, c2 + 1)]

    def draw(self, x, y, dc):
        Box.draw(self, x, y, dc)
        # Grid lines
        cy = y
        for rh in self.row_heights:
            self.device.draw_rect(x, cy, self.width, rh, dc)
            cy += rh

    def draw_background(self, x, y, dc):
        pass


# ---------------------------------------------------------------------------
# Helper: build a simple text-only table from a 2-D list of strings
# ---------------------------------------------------------------------------

def mk_table(texts, col_width=60, row_height=14, style=EMPTYSTYLE, device=None):
    """Create a TableBox from a 2-D list of strings."""
    from .boxes import TESTDEVICE
    dev = device or TESTDEVICE
    cells = []
    for row_texts in texts:
        row = []
        for text in row_texts:
            cell = VBox([TextBox(text, style, dev),
                         NewlineBox(style, dev)], dev)
            row.append(cell)
        cells.append(row)
    n_cols = max(len(r) for r in texts)
    n_rows = len(texts)
    return TableBox(cells,
                    col_widths  = [col_width]  * n_cols,
                    row_heights = [row_height] * n_rows,
                    device=dev)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_00():
    "get_ranges returns one range per cell in the rectangular selection"
    table = mk_table([['A', 'B', 'C'],
                      ['D', 'E', 'F'],
                      ['G', 'H', 'I']])

    # Every cell has 2 chars (letter + newline); total = 18
    assert len(table) == 18

    cell_len = 2  # letter + NL

    # Select from D (row1,col0) to E (row1,col1) → 1×2 rectangle
    i1 = table._offsets[(1, 0)]          # start of D
    i2 = table._offsets[(1, 1)] + cell_len  # end of E
    ranges = table.get_ranges(i1, i2)
    assert ranges == [(table._offsets[(1, 0)], table._offsets[(1, 0)] + cell_len),
                      (table._offsets[(1, 1)], table._offsets[(1, 1)] + cell_len)]

    # Select from A (0,0) to E (1,1) → 2×2 rectangle = 4 cells
    i1 = table._offsets[(0, 0)]
    i2 = table._offsets[(1, 1)] + cell_len
    ranges = table.get_ranges(i1, i2)
    assert len(ranges) == 4
    assert ranges[0] == (table._offsets[(0, 0)], table._offsets[(0, 0)] + cell_len)
    assert ranges[3] == (table._offsets[(1, 1)], table._offsets[(1, 1)] + cell_len)

    # Single cell: A (0,0) → 1 range
    i1 = table._offsets[(0, 0)]
    i2 = i1 + cell_len
    ranges = table.get_ranges(i1, i2)
    assert len(ranges) == 1


def test_01():
    "Box.get_ranges propagates into a TableBox child"
    from .boxes import VBox, TESTDEVICE
    table = mk_table([['X', 'Y'],
                      ['Z', 'W']])
    outer = VBox([table], TESTDEVICE)

    cell_len = 2
    # Select Z (1,0) to W (1,1)
    i1 = table._offsets[(1, 0)]
    i2 = table._offsets[(1, 1)] + cell_len
    ranges = outer.get_ranges(i1, i2)
    assert len(ranges) == 2


def demo_00():
    """Interactive table demo: click and shift-click to select cells."""
    import wx
    from ..textmodel.textmodel import TextModel
    from .wxtextview import WXTextView
    from .wxdevice import WxDevice
    from .builder import BuilderBase
    from .boxes import EndBox

    TEXTS = [['Name',     'City',       'Country'],
             ['Einstein', 'Ulm',        'Germany'],
             ['Darwin',   'Shrewsbury', 'England'],
             ['Curie',    'Warsaw',     'Poland' ]]

    def build(device):
        style = EMPTYSTYLE
        cells = []
        n_rows, n_cols = len(TEXTS), len(TEXTS[0])
        for r, row_texts in enumerate(TEXTS):
            row = []
            for c, text in enumerate(row_texts):
                is_last = (r == n_rows - 1 and c == n_cols - 1)
                tail = EndBox(style, device) if is_last else NewlineBox(style, device)
                row.append(VBox([TextBox(text, style, device), tail], device))
            cells.append(row)
        return TableBox(cells,
                        col_widths  = [120] * n_cols,
                        row_heights = [22]  * n_rows,
                        device      = device)

    # Model text matches table exactly: cells joined by '\n', no trailing '\n'
    # (the EndBox in the last cell accounts for the +1 the builder normally adds)
    model = TextModel('\n'.join(t for row in TEXTS for t in row))

    class TableBuilder(BuilderBase):
        def __init__(self, device):
            self._layout = build(device)
        def rebuild(self):      pass
        def clear_caches(self): pass
        def set_maxw(self, w):  pass

    class TableView(WXTextView):
        def create_builder(self):
            return TableBuilder(WxDevice())

    app   = wx.App(redirect=False)
    frame = wx.Frame(None, title='Table demo', size=(420, 140))
    view  = TableView(frame)
    view.set_model(model)
    frame.Show()
    from . import testing
    testing.pyshell(locals())
    app.MainLoop()
