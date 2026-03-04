"""Table: texel model + TableBox rendering for n×m grids."""

from .textmodel.texeltree import Container, NL, TAB, EMPTYSTYLE as EMPTY_TEXEL_STYLE
from .wxtextview.boxes import Box, Row, TextBox, EMPTYSTYLE
from .wxtextview.testdevice import TESTDEVICE


# ---------------------------------------------------------------------------
# Texel model
# ---------------------------------------------------------------------------

class Table(Container):
    """n_rows × n_cols table texel. All children are mutable cell texels."""
    style = EMPTY_TEXEL_STYLE

    def __init__(self, n_rows, n_cols, cells):
        self.n_rows = n_rows
        self.n_cols = n_cols
        l = []
        for i, row in enumerate(cells):
            assert len(row) == n_cols
            if i == 0:
                l.append(TAB)  # leading separator so separators are at even positions
            for j, cell in enumerate(row):
                l.append(cell)
                l.append(TAB if j < n_cols - 1 else NL)
        self.childs = l
        self.compute_weights()

    def __repr__(self):
        return 'Table(%d\xd7%d)' % (self.n_rows, self.n_cols)


def mk_table(texts):
    """Create a Table texel from a 2D list of strings."""
    from .textmodel.texeltree import T, NL, G
    n_rows = len(texts)
    n_cols = max(len(row) for row in texts) if texts else 0
    cells = [[T(t) for t in row] for row in texts]
    return Table(n_rows, n_cols, cells)


# ---------------------------------------------------------------------------
# Box
# ---------------------------------------------------------------------------

class CellBox(Box):
    # A box which has one empty index position at the end to seperate
    # the content from the following boxes.
    def __init__(self, boxes, device=None):
        if device is not None:
            self.device = device
        content = self.content = Row(boxes, device=device)
        self.length = content.length+1
        m = self.device.measure("M", {})[1] # We use the capital
                                            # M as a reference
        self.fill = max(0, m-content.height)                                            
        self.height = self.fill+content.height
        self.depth = content.depth
        self.width = content.width

    def __len__(self):
        return self.length

    def get_index(self, x, y):
        return self.content.get_index(x, max(0, y - self.fill))

    def iter_boxes(self, i, x, y):
        yield 0, self.length-1, x, y+self.fill, self.content

        
class TableBox(Box):
    """A n_rows × n_cols table box with per-cell selection via get_ranges()."""

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
        self._offsets = {}
        i = 1  # offset 0 reserved for leading TAB in Table texel
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
        if ar == cr and ac == cc:
            ci1 = self._offsets[(ar, ac)]
            cell = self.cells[ar][ac]
            return [(r1 + ci1, r2 + ci1)
                    for r1, r2 in cell.get_ranges(i1 - ci1, i2 - ci1)]
        r1, r2 = min(ar, cr), max(ar, cr)
        c1, c2 = min(ac, cc), max(ac, cc)
        return [(self._offsets[(r, c)],
                 self._offsets[(r, c)] + len(self.cells[r][c]))
                for r in range(r1, r2 + 1)
                for c in range(c1, c2 + 1)]

    def get_copy(self, i1, i2, model, offset):
        """Return a TextModel for the selection [i1, i2] (relative to this box).

        For single-cell selections delegate to model.copy. For multi-cell
        rectangular selections build a new Table texel from the cell content.
        offset is the absolute position of this TableBox within model.
        """
        ar, ac = self._find_cell(i1)
        cr, cc = self._find_cell(max(i1, i2 - 1))
        if ar == cr and ac == cc:
            return model.copy(offset + i1, offset + i2)
        r1, r2 = min(ar, cr), max(ar, cr)
        c1, c2 = min(ac, cc), max(ac, cc)
        grid = []
        for r in range(r1, r2 + 1):
            row = []
            for c in range(c1, c2 + 1):
                ci1 = self._offsets[(r, c)]
                ci2 = ci1 + len(self.cells[r][c]) - 1  # content without separator
                row.append(model.copy(offset + ci1, offset + ci2).texel)
            grid.append(row)
        new_table = Table(r2 - r1 + 1, c2 - c1 + 1, grid)
        result = model.create_textmodel()
        result.texel = new_table
        return result

    def draw_selection(self, i1, i2, x0, y0, dc):
        ar, ac = self._find_cell(i1)
        cr, cc = self._find_cell(max(i1, i2 - 1))
        ci1 = self._offsets[(ar, ac)]
        cell = self.cells[ar][ac]
        if ar == cr and ac == cc and not (i1 == ci1 and i2 == ci1 + len(cell)):
            # partial selection within a single cell: draw text-level highlight
            Box.draw_selection(self, i1, i2, x0, y0, dc)
            return
        # full-cell selection (one or more cells): invert each cell's full rect
        r1, r2 = min(ar, cr), max(ar, cr)
        c1, c2 = min(ac, cc), max(ac, cc)
        cy = y0
        for r, rh in enumerate(self.row_heights):
            if r1 <= r <= r2:
                cx = x0
                for c, cw in enumerate(self.col_widths):
                    if c1 <= c <= c2:
                        self.device.invert_rect(cx, cy, cw, rh, dc)
                    cx += cw
            cy += rh

    def draw(self, x, y, dc):
        Box.draw(self, x, y, dc)
        cy = y
        for rh in self.row_heights:
            self.device.draw_rect(x, cy, self.width, rh, dc)
            cy += rh

    def draw_background(self, x, y, dc):
        pass


# ---------------------------------------------------------------------------
# Build TableBox from Table texel
# ---------------------------------------------------------------------------

def build_table_box(texel, factory, col_width=120, row_height=22):
    """Build a TableBox from a Table texel using factory to create cell boxes."""
    # cells at odd positions; TAB/NL separators at even positions
    cell_texels = texel.childs[1::2]
    n_rows, n_cols = texel.n_rows, texel.n_cols
    grid = []
    for r in range(n_rows):
        row = []
        for c in range(n_cols):
            boxes = list(factory.create_all(cell_texels[r * n_cols + c]))
            row.append(CellBox(boxes, factory.device))
        grid.append(row)
    return TableBox(grid, [col_width] * n_cols, [row_height] * n_rows,
                    device=factory.device)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _mk_box_table(texts, col_width=60, row_height=14, device=None):
    """Build a TableBox directly from strings (for box-level tests)."""
    dev = device or TESTDEVICE
    style = EMPTYSTYLE
    n_rows, n_cols = len(texts), max(len(r) for r in texts)
    cells = [[CellBox([TextBox(text, style, dev)], dev) for text in row]
             for row in texts]
    return TableBox(cells, [col_width] * n_cols, [row_height] * n_rows, device=dev)


def test_00():
    "get_ranges returns one range per cell in the rectangular selection"
    table = _mk_box_table([['A', 'B', 'C'],
                           ['D', 'E', 'F'],
                           ['G', 'H', 'I']])
    assert len(table) == 19
    cell_len = 2

    i1 = table._offsets[(1, 0)]
    i2 = table._offsets[(1, 1)] + cell_len
    ranges = table.get_ranges(i1, i2)
    assert ranges == [(table._offsets[(1, 0)], table._offsets[(1, 0)] + cell_len),
                      (table._offsets[(1, 1)], table._offsets[(1, 1)] + cell_len)]

    i1 = table._offsets[(0, 0)]
    i2 = table._offsets[(1, 1)] + cell_len
    ranges = table.get_ranges(i1, i2)
    assert len(ranges) == 4
    assert ranges[0] == (table._offsets[(0, 0)], table._offsets[(0, 0)] + cell_len)
    assert ranges[3] == (table._offsets[(1, 1)], table._offsets[(1, 1)] + cell_len)

    i1 = table._offsets[(0, 0)]
    i2 = i1 + cell_len
    ranges = table.get_ranges(i1, i2)
    assert len(ranges) == 1


def test_01():
    "Box.get_ranges propagates into a TableBox child"
    from .wxtextview.boxes import VBox as WVBox
    table = _mk_box_table([['X', 'Y'], ['Z', 'W']])
    outer = WVBox([table], TESTDEVICE)
    cell_len = 2
    i1 = table._offsets[(1, 0)]
    i2 = table._offsets[(1, 1)] + cell_len
    ranges = outer.get_ranges(i1, i2)
    assert len(ranges) == 2


def test_02():
    "mk_table creates Table texel with correct length"
    texts = [['A', 'B'], ['C', 'D']]
    table = mk_table(texts)
    assert table.n_rows == 2
    assert table.n_cols == 2
    from .textmodel.texeltree import length
    # structure: [TAB, A, TAB, B, NL, C, TAB, D, NL] → 4 cells + 5 separators = 9
    assert length(table) == 9


def test_03():
    "build_table_box produces TableBox with correct length"
    from .wxtextview.builder import Factory
    texts = [['Hi', 'World'], ['Foo', 'Bar']]
    table = mk_table(texts)
    factory = Factory()
    box = build_table_box(table, factory, col_width=60, row_height=14)
    assert isinstance(box, TableBox)
    from .textmodel.texeltree import length
    assert len(box) == length(table)


def test_04():
    "get_copy builds a sub-Table texel for rectangular multi-cell selections"
    from .wxtextview.builder import Factory
    from .textmodel.textmodel import TextModel
    from .textmodel.texeltree import length
    texts = [['A', 'B', 'C'], ['D', 'E', 'F'], ['G', 'H', 'I']]
    table = mk_table(texts)
    model = TextModel()
    model.texel = table
    factory = Factory()
    box = build_table_box(table, factory, col_width=60, row_height=14)

    # Select 2×2 sub-table: cells (1,0),(1,1),(2,0),(2,1)
    i1 = box._offsets[(1, 0)]
    i2 = box._offsets[(2, 1)] + len(box.cells[2][1])
    result = box.get_copy(i1, i2, model, 0)
    assert isinstance(result.texel, Table)
    assert result.texel.n_rows == 2
    assert result.texel.n_cols == 2
    # length = sum of selected cell lengths + 1 (leading TAB of new sub-table)
    selected = [(1,0),(1,1),(2,0),(2,1)]
    assert length(result.texel) == sum(len(box.cells[r][c]) for r,c in selected) + 1


def test_05():
    "get_copy for a single-cell selection returns plain model slice"
    from .wxtextview.builder import Factory
    from .textmodel.textmodel import TextModel
    texts = [['Hello', 'World'], ['Foo', 'Bar']]
    table = mk_table(texts)
    model = TextModel()
    model.texel = table
    factory = Factory()
    box = build_table_box(table, factory, col_width=60, row_height=14)

    # Cursors land within content only (not on immutable separators)
    i1 = box._offsets[(0, 0)]
    content_len = len(box.cells[0][0]) - 1  # exclude separator
    i2 = i1 + content_len
    result = box.get_copy(i1, i2, model, 0)
    assert not isinstance(result.texel, Table)
    assert result.get_text() == 'Hello'


def test_06():
    "copy/paste: copied sub-table can be inserted into another model"
    from .wxtextview.builder import Factory
    from .textmodel.textmodel import TextModel
    from .textmodel.texeltree import length, get_text
    texts = [['A', 'B', 'C'], ['D', 'E', 'F'], ['G', 'H', 'I']]
    table = mk_table(texts)
    model = TextModel()
    model.texel = table
    factory = Factory()
    box = build_table_box(table, factory, col_width=60, row_height=14)

    i1 = box._offsets[(0, 0)]
    i2 = box._offsets[(1, 1)] + len(box.cells[1][1])
    copied = box.get_copy(i1, i2, model, 0)
    assert isinstance(copied.texel, Table)
    assert copied.texel.n_rows == 2
    assert copied.texel.n_cols == 2

    dest = TextModel()
    dest.insert(0, copied)
    assert get_text(dest.texel) == '\tA\tB\nD\tE\n'
    assert length(dest.texel) == length(copied.texel)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_00():
    """Interactive demo: click and shift-click to select cells."""
    import wx
    from .document import Document
    from .documentview import DocumentView

    TEXTS = [['Name',     'City',       'Country'],
             ['Einstein', 'Ulm',        'Germany'],
             ['Darwin',   'Shrewsbury', 'England'],
             ['Curie',    'Warsaw',     'Poland']]

    doc = Document()
    doc.textmodel.texel = mk_table(TEXTS)

    app   = wx.App(redirect=True)
    frame = wx.Frame(None, title='Table demo', size=(420, 420))
    view  = DocumentView(frame, doc)
    frame.Show()
    from .wxtextview import testing
    testing.pyshell(locals())
    app.MainLoop()
