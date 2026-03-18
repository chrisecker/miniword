"""Table: texel model + TableBox rendering for n×m grids."""

from .textmodel.texeltree import Container, NL, TAB, EMPTYSTYLE as EMPTY_TEXEL_STYLE, NewLine
from .wxtextview.boxes import Box, Row, TextBox, EMPTYSTYLE
from .wxtextview.testdevice import TESTDEVICE


# ---------------------------------------------------------------------------
# Texel model
# ---------------------------------------------------------------------------

class TableSep(NewLine):
    """Inter-cell separator in a Table texel.
    Identical to NewLine but text='\\t' and NL-weight=0,
    so get_text() stays readable and paragraph counts are unaffected.
    """
    weights = (0, 1, 0)
    text = u'\t'


class Table(Container):
    """n_rows × n_cols table texel. All children are mutable cell texels."""
    style = EMPTY_TEXEL_STYLE
    header_rows = 0
    break_level = 1
    col_widths = None  # list[float|None] or None (all auto)

    def __init__(self, n_rows, n_cols, cells):
        self.n_rows = n_rows
        self.n_cols = n_cols
        l = []
        l.append(TableSep())  # leading separator
        for i, row in enumerate(cells):
            assert len(row) == n_cols
            for j, cell in enumerate(row):
                l.append(cell)
                if j < n_cols - 1:
                    l.append(TableSep())  # inter-cell
                else:
                    l.append(NL)          # row-ending
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
    """Vertical stack of wrapped lines for a table cell."""
    def __init__(self, rows, device=None, hpad=0, vpad=0):
        if device is not None:
            self.device = device
        self._rows = rows
        self._lpad = hpad // 2
        self._tpad = vpad // 2
        total_h = sum(r.height + r.depth for r in rows)
        m = self.device.measure("M", {})[1]
        self.fill = max(0, m - total_h)
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


class TableBox(Box):
    """A n_rows × n_cols table box."""
    prev = None
    next = None
    _source = None
    _orig = None         # full pre-split TableBox (set on fragments only)
    _base_offset = 0     # fragment start within the original table's index space
    _orig_rows = None    # list of original row indices stored in this fragment

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
        self._offsets = {}
        # Continuation fragments do not own the leading separator of the
        # Table texel (it belongs to the first fragment), so start at 0.
        i = 0 if is_continuation else 1
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
        res = self._resolve_cell_range(i1, i2)
        if res is None:
            return [(i1, i2)]
        ar, ac, cr, cc = res

        # Single cell: delegate for partial selection
        if ar == cr and ac == cc:
            r_local = self._row_local(ar)
            if r_local is None:
                return []
            ci1 = self._offsets[(r_local, ac)]
            cell = self.cells[r_local][ac]
            if self._orig is not None:
                orig_ci1 = self._orig._offsets[(ar, ac)]
                cell_i1 = self._base_offset + i1 - orig_ci1
                cell_i2 = self._base_offset + i2 - orig_ci1
            else:
                cell_i1, cell_i2 = i1 - ci1, i2 - ci1
            return [(r1 + ci1, r2 + ci1)
                    for r1, r2 in cell.get_ranges(cell_i1, cell_i2)]

        # Multi-cell rectangular selection
        r1, r2 = min(ar, cr), max(ar, cr)
        c1, c2 = min(ac, cc), max(ac, cc)
        orig_rows = (self._orig_rows if self._orig_rows is not None
                     else range(self.n_rows))
        return [(self._offsets[(r_local, c)],
                 self._offsets[(r_local, c)] + len(self.cells[r_local][c]))
                for r_local, r_orig in enumerate(orig_rows)
                if r1 <= r_orig <= r2
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

    def _resolve_cell_range(self, i1, i2):
        """Return (ar, ac, cr, cc) cell corners for selection [i1, i2].

        For fragments (_orig is set), maps local indices to the original
        table's coordinate space so cross-fragment column selections work.
        For non-fragmented boxes uses local offsets directly.
        Returns None if the selection is empty or entirely outside this box.
        """
        if self._orig is not None:
            orig = self._orig
            o1 = max(1, self._base_offset + i1)
            o2 = max(1, min(self._base_offset + i2, len(orig)))
            if o1 >= o2:
                return None
            ar, ac = orig._find_cell(o1)
            cr, cc = orig._find_cell(o2 - 1)
        else:
            ar, ac = self._find_cell(i1)
            cr, cc = self._find_cell(max(i1, i2 - 1))
        return ar, ac, cr, cc

    def _row_local(self, r_orig):
        """Map an original row index to a local row index in this fragment.
        Returns None when the row is not in this fragment.
        """
        if self._orig_rows is None:
            return r_orig if r_orig < self.n_rows else None
        for r_local, ro in enumerate(self._orig_rows):
            if ro == r_orig:
                return r_local
        return None

    def draw_selection(self, i1, i2, x0, y0, dc):
        res = self._resolve_cell_range(i1, i2)
        if res is None:
            return
        ar, ac, cr, cc = res

        # Single-cell partial selection?
        if ar == cr and ac == cc:
            r_local = self._row_local(ar)
            if r_local is not None:
                cell = self.cells[r_local][ac]
                ci1 = self._offsets[(r_local, ac)]
                ci2 = ci1 + len(cell)
                # Convert selection to cell-local coordinates
                if self._orig is not None:
                    orig_ci1 = self._orig._offsets[(ar, ac)]
                    sel_c1 = self._base_offset + i1 - orig_ci1
                    sel_c2 = self._base_offset + i2 - orig_ci1
                else:
                    sel_c1, sel_c2 = i1 - ci1, i2 - ci1
                if not (sel_c1 <= 0 and sel_c2 >= len(cell)):
                    cx = x0 + sum(self.col_widths[:ac])
                    cy = y0 + sum(self.row_heights[:r_local])
                    cell.draw_selection(sel_c1, sel_c2, cx, cy, dc)
                    return

        # Full-cell rectangular selection
        r1, r2 = min(ar, cr), max(ar, cr)
        c1, c2 = min(ac, cc), max(ac, cc)
        orig_rows = (self._orig_rows if self._orig_rows is not None
                     else range(self.n_rows))
        cy = y0
        for r_local, r_orig in enumerate(orig_rows):
            rh = self.row_heights[r_local]
            if r1 <= r_orig <= r2:
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
# Navigation helper
# ---------------------------------------------------------------------------

class _TableNavRow:
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
                return tb._offsets[(self._r, c)] + cell.get_index(x - cx, y)
            cx += cw
        return tb._offsets[(self._r, tb.n_cols - 1)]


# ---------------------------------------------------------------------------
# Build TableBox from Table texel
# ---------------------------------------------------------------------------

_CELL_HPAD = 8   # horizontal padding per column
_CELL_VPAD = 6   # vertical padding per row


def build_cell(cell_texel, sep, col_width, factory):
    """Build a CellBox for one cell, using parstyle from the following separator."""
    from .wxtextview.linewrap import simple_linewrap
    from .wxtextview.boxes import NewlineBox
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

    from .pagegen import Row as PageRow
    rows = [PageRow(line, device=factory.device) for line in all_lines]
    return CellBox(rows, factory.device, hpad=_CELL_HPAD, vpad=_CELL_VPAD)


def build_table_box(texel, factory, row_height=None):
    """Build a TableBox from a Table texel using factory to create cell boxes."""
    # separators at even positions; cells at odd positions
    # childs: [TableSep, cell00, TableSep, cell01, NL, cell10, ...]
    n_rows, n_cols = texel.n_rows, texel.n_cols

    # compute col_widths
    page_width = getattr(factory, 'line_width', 400)  # fallback
    if texel.col_widths:
        explicit = [w for w in texel.col_widths if w is not None]
        n_auto = sum(1 for w in texel.col_widths if w is None)
        auto_w = ((page_width - sum(explicit)) / n_auto) if n_auto else 0
        col_widths_px = [w if w is not None else auto_w
                         for w in texel.col_widths]
    else:
        col_widths_px = [page_width / n_cols] * n_cols

    cell_texels = texel.childs[1::2]   # cells at indices 1,3,5,...
    seps        = texel.childs[2::2]   # separators at indices 2,4,6,...

    grid = []
    for r in range(n_rows):
        row = []
        for c in range(n_cols):
            idx = r * n_cols + c
            cell_t = cell_texels[idx]
            sep    = seps[idx]
            cw     = col_widths_px[c]
            row.append(build_cell(cell_t, sep, cw, factory))
        grid.append(row)

    col_widths_out = [max(grid[r][c].width for r in range(n_rows))
                      for c in range(n_cols)]
    if row_height is None:
        row_heights = [max(grid[r][c].height + grid[r][c].depth
                          for c in range(n_cols))
                       for r in range(n_rows)]
    else:
        row_heights = [row_height] * n_rows

    box = TableBox(grid, col_widths_out, row_heights,
                   header_rows=texel.header_rows,
                   break_level=texel.break_level,
                   device=factory.device)
    box._source = texel
    return box


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _mk_box_table(texts, col_width=60, row_height=14, device=None):
    """Build a TableBox directly from strings (for box-level tests)."""
    dev = device or TESTDEVICE
    from .pagegen import Row as PageRow
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
    # structure: [TableSep, A, TableSep, B, NL, C, TableSep, D, NL] → 4 cells + 5 separators = 9
    assert length(table) == 9


def test_03():
    "build_table_box produces TableBox with correct length"
    from .wxtextview.builder import Factory
    texts = [['Hi', 'World'], ['Foo', 'Bar']]
    table = mk_table(texts)
    factory = Factory()
    box = build_table_box(table, factory, row_height=14)
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
    box = build_table_box(table, factory, row_height=14)

    # Select 2×2 sub-table: cells (1,0),(1,1),(2,0),(2,1)
    i1 = box._offsets[(1, 0)]
    i2 = box._offsets[(2, 1)] + len(box.cells[2][1])
    result = box.get_copy(i1, i2, model, 0)
    assert isinstance(result.texel, Table)
    assert result.texel.n_rows == 2
    assert result.texel.n_cols == 2
    # length = sum of selected cell lengths + 1 (leading TableSep of new sub-table)
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
    box = build_table_box(table, factory, row_height=14)

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
    box = build_table_box(table, factory, row_height=14)

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
