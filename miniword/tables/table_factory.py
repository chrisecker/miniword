"""Build TableBox and CellBox from Table texels.

Kept separate from table_boxes.py to avoid a circular import:
  table_boxes <- table_factory <- layout.rowfactory <- tables.table_boxes
"""

from ..layout.testdevice import TESTDEVICE
from ..textmodel.texeltree import length as texel_length, Group, NewLine
from .table_boxes import CellBox, TableBox, CELL_HPAD, CELL_VPAD, create_cell


def build_cell(cell_texel, sep, col_width, factory, footnotes=None):
    """Build a CellBox for one cell; cell style comes from the following
    separator. The content is set by a RowFactory of its own, wrapped at
    col_width minus the cell padding.

    footnotes: list to collect the row records of footnotes anchored
    inside this cell, so the caller can hand them up to the enclosing
    page. (Their numbering starts afresh in every cell - the new
    pipeline numbers them through RowFactory.Table_handler.)
    """
    from ..layout.rowfactory import RowFactory, State  # circular import

    # Use sep's parstyle and indent as the paragraph delimiter.
    # Must be a plain NewLine - the factory has no Separator_handler.
    nl = NewLine()
    nl.parstyle = sep.parstyle
    nl.indent   = getattr(sep, 'indent', 0)
    content = Group([cell_texel, nl])

    state = State(col_width - CELL_HPAD)
    rowfactory = RowFactory(state, factory.stylesheet, factory.device)
    records = [record for par in rowfactory.generate(content, 0)
               for record in par]
    if footnotes is not None:
        footnotes.extend(state.footnotes)

    cell = create_cell(records, col_width, factory.device, hpad=CELL_HPAD,
                       vpad=CELL_VPAD, style=getattr(sep, 'parstyle', {}))
    # sep is counted as part of the paragraph but belongs to the table
    # structure; cell.length must equal texel_length(cell_texel) + 1
    # (the separator slot).
    cell.length = texel_length(cell_texel) + 1
    return cell


def build_table_box(texel, factory, row_height=None):
    """Build a TableBox from a Table texel using factory to create cell boxes."""
    n_rows, n_cols = texel.nrows, texel.ncols

    page_width = getattr(factory, 'line_width', None) or 400
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

    footnotes = []
    grid = []
    for r in range(n_rows):
        row = []
        for c in range(n_cols):
            idx = r * n_cols + c
            row.append(build_cell(cell_texels[idx], seps[idx], col_widths_px[c],
                                   factory, footnotes=footnotes))
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

    table_box = TableBox(grid, col_widths_out, row_heights,
                         header_rows=texel.nheader,
                         break_level=texel.breaklevel,
                         device=factory.device)
    # Footnotes anchored inside a cell belong to the enclosing page, not
    # to the cell's own (otherwise discarded) nested draft -- see
    # build_cell's footnotes param.
    table_box.footnotes = footnotes
    return table_box


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_03():
    "build_table_box produces TableBox with correct length"
    from ..layout.rowfactory import Factory
    from ..core.styles import testsheet
    from .tables import from_strings
    texts = [['Hi', 'World'], ['Foo', 'Bar']]
    table = from_strings(texts)
    factory = Factory(testsheet, TESTDEVICE)
    box = build_table_box(table, factory)
    assert isinstance(box, TableBox)
    assert len(box) == texel_length(table)
