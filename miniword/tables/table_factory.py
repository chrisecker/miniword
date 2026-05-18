"""Build TableBox and CellBox from Table texels.

Kept separate from table_boxes.py to avoid a circular import:
  table_boxes <- table_factory <- layout.pagegen <- tables.table_boxes
"""

from ..layout.boxes import EmptyTextBox
from ..layout.testdevice import TESTDEVICE
from ..textmodel.texeltree import length as texel_length, Group, NewLine
from .table_boxes import CellBox, TableBox, CELL_HPAD, CELL_VPAD


def build_cell(cell_texel, sep, col_width, factory):
    """Build a CellBox for one cell; cell style comes from the following separator."""
    from ..layout.pagegen import generate_pages, RestartMemo, Row as PageRow

    memo = RestartMemo()
    memo.geometry = (col_width, 10**9)
    memo.border   = (CELL_VPAD // 2, CELL_HPAD // 2,
                     CELL_VPAD // 2, CELL_HPAD // 2)

    # Use sep's parstyle and indent as the paragraph delimiter.
    # Must be a plain NewLine — the Factory has no Separator_handler.
    nl = NewLine()
    nl.parstyle = sep.parstyle
    nl.indent   = getattr(sep, 'indent', 0)
    content = Group([cell_texel, nl])

    # Save factory state modified by generate_pages so the outer caller
    # (generate_pages for the page) is not corrupted.
    saved = {k: getattr(factory, k, None)
             for k in ('line_width', 'parstyle', 'markerstyle', 'indent_level')}

    page = None
    for page in generate_pages(content, 0, memo, factory, allow_page_breaks=False):
        pass  # expect exactly one page

    for k, v in saved.items():
        if v is not None:
            setattr(factory, k, v)

    rows = [row for _, _, row in page.rows] if page else []

    if not rows:
        line = EmptyTextBox(style=factory.mk_style({}), device=factory.device)
        rows = [PageRow([line], device=factory.device)]

    cell = CellBox(rows, factory.device, hpad=0, vpad=0,
                   style=getattr(sep, 'parstyle', {}))
    cell._tpad  = CELL_VPAD // 2
    cell.width  = col_width
    if page and page.rows:
        _, y_last, last_row = page.rows[-1]
        cell.height = y_last + last_row.height + last_row.depth + CELL_VPAD // 2
    else:
        cell.height = cell.fill + CELL_VPAD
    # sep is counted as part of the paragraph but belongs to the table structure;
    # cell.length must equal texel_length(cell_texel) + 1 (the separator slot).
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

def test_03():
    "build_table_box produces TableBox with correct length"
    from ..layout.factory import Factory
    from ..core.styles import testsheet
    from .tables import from_strings
    texts = [['Hi', 'World'], ['Foo', 'Bar']]
    table = from_strings(texts)
    factory = Factory(testsheet, TESTDEVICE)
    box = build_table_box(table, factory)
    assert isinstance(box, TableBox)
    assert len(box) == texel_length(table)
