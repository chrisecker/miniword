# -*- coding: utf-8 -*-

"""
typeset_into_rect turns row records (as produced by
RowFactory.generate_rows) into a fixed-width CellBox: row positions,
optional cell padding/background (hpad/vpad/style), and block
decorations (block_color/padding/border, grouped via
rowfactory.block_key/BLOCK_KEYS) as decorations/borders on the box.

Used by RowFactory.Table_handler (one call per table cell) and for
footnote content.
"""

from .boxes import RowsBox
from .rowfactory import block_key


class CellBox(RowsBox):
    """Stand-in for tables/table_boxes.py's CellBox, which is still
    Box-based (its own padded stacking, no decorations) rather than
    RowsBox-based.

    Adds borders on top of RowsBox.decorations (background fill):
    same tuple shape (dx, dy, dw, dh, color), drawn with draw_rect
    instead of fill_rect."""
    borders = ()

    def __init__(self, data, device=None, width=0, height=0,
                 decorations=(), borders=()):
        if device is not None:
            self.device = device
        self.data = data
        self.width = width
        self.height = height
        self.depth = 0
        self.decorations = decorations
        self.borders = borders

    def draw_decorations(self, x, y, gc):
        RowsBox.draw_decorations(self, x, y, gc)
        for dx, dy, dw, dh, color in self.borders:
            self.device.draw_rect(x + dx, y + dy, dw, dh, gc)


def typeset_into_rect(records, width, device, hpad=0, vpad=0, style=None):
    """Build a fixed-width CellBox from row records. Consecutive
    paragraphs sharing the same block style (block_color/padding/
    border) are grouped into one decoration rect instead of one per
    paragraph; block_padding pushes rows apart at the start/end of
    such a group.

    hpad/vpad/style mirror tables.table_boxes.CellBox: cell padding
    and cell background (style['cell_bgcolor']) - independent of, and
    on top of, the paragraphs' own block decorations."""
    style = style or {}
    lpad, tpad = hpad // 2, vpad // 2
    y = tpad
    data = []
    row_info = []  # (y, height+depth) per row
    for idx, (row, parstyle, begins_par, ends_par, begins_block, ends_block) \
            in enumerate(records):
        color, padding, border = block_key(parstyle)
        if begins_par and begins_block:
            y += padding
        data.append((lpad, y, row))
        row_info.append((y, row.height + row.depth))
        y += row.height + row.depth
        if ends_par and ends_block:
            y += padding
    y += tpad

    decorations, borders = [], []
    cell_bgcolor = style.get('cell_bgcolor')
    if cell_bgcolor is not None:
        decorations.append((0, 0, width + hpad, y, cell_bgcolor))

    group_start = None
    for idx, (row, parstyle, bp, ep, begins_block, ends_block) in \
            enumerate(records):
        if bp and begins_block:
            group_start = idx
        if ep and ends_block:
            color, padding, border = block_key(records[group_start][1])
            if color is not None or border is not None:
                top = row_info[group_start][0] - padding
                bottom_y, bottom_h = row_info[idx]
                rect = (lpad, top, width, bottom_y + bottom_h + padding - top)
                if color is not None:
                    decorations.append(rect + (color,))
                if border is not None:
                    borders.append(rect + (border,))

    return CellBox(data, device, width + hpad, y, decorations, borders)


# ---------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------

from ..core.styles import testsheet
from ..textmodel.texeltree import Text, NewLine, Group
from .testdevice import TESTDEVICE
from .rowfactory import RowFactory


def _nl(parstyle, endmark=False):
    nl = NewLine().set_parstyle(parstyle)
    if endmark:
        nl.is_endmark = 1
    return nl


def _make_block_doc():
    boxed = {'base': 'normal', 'block_color': '#eee', 'block_padding': 2}
    bordered = {'base': 'normal', 'block_border': 'thin'}
    return Group([
        Text('One'), _nl(boxed),
        Text('Two'), _nl(boxed),
        Text('Three'), _nl(bordered, endmark=True),
    ])


def test_00():
    "Block decorations: adjacent paragraphs sharing a block style merge into one rect"
    texel = _make_block_doc()
    factory = RowFactory(testsheet, TESTDEVICE, line_width=400)
    records = list(factory.generate_rows(texel, 0))
    assert len(records) == 3

    box = typeset_into_rect(records, 400, TESTDEVICE)

    # TESTDEVICE: every row has height=1, depth=0.
    assert box.height == 7  # 1+1+1 + 2 top padding (P0) + 2 bottom padding (P1)
    assert box.decorations == [(0, 0, 400, 6, '#eee')]
    assert box.borders == [(0, 6, 400, 1, 'thin')]

    solo = {'base': 'normal', 'block_color': '#eee', 'block_padding': 3}
    solo_texel = Group([Text('Solo'), _nl(solo, endmark=True)])
    solo_records = list(factory.generate_rows(solo_texel, 0))
    solo_box = typeset_into_rect(solo_records, 400, TESTDEVICE)
    assert solo_box.height == 7  # 1 row + 3 top padding + 3 bottom padding
    assert solo_box.decorations == [(0, 0, 400, 7, '#eee')]
    assert solo_box.data[0][1] == 3

    # padding_only: block_padding without block_color/block_border still
    # reserves space, even though there is nothing to draw.
    padding_only = {'base': 'normal', 'block_padding': 4}
    po_texel = Group([Text('Padded'), _nl(padding_only, endmark=True)])
    po_records = list(factory.generate_rows(po_texel, 0))
    po_box = typeset_into_rect(po_records, 400, TESTDEVICE)
    assert po_box.height == 9  # 1 row + 4 top padding + 4 bottom padding
    assert po_box.decorations == []
    assert po_box.data[0][1] == 4

    # A paragraph wrapping into several rows still gets exactly ONE
    # decoration rect spanning the full paragraph height (not one per row).
    wrapped = {'base': 'normal', 'block_color': '#eee', 'block_padding': 2}
    wrap_texel = Group([Text('Aaa '), Text('Bbb '), Text('Ccc '), Text('Ddd '),
                         _nl(wrapped, endmark=True)])
    wrap_factory = RowFactory(testsheet, TESTDEVICE, line_width=8)
    wrap_records = list(wrap_factory.generate_rows(wrap_texel, 0))
    assert len(wrap_records) > 1  # must actually wrap
    wrap_box = typeset_into_rect(wrap_records, 8, TESTDEVICE)
    assert len(wrap_box.decorations) == 1
    n_rows = len(wrap_records)
    assert wrap_box.decorations == [(0, 0, 8, n_rows + 4, '#eee')]


def test_01():
    "typeset_into_rect: cell padding/background (hpad/vpad/style) and block decoration coexist"
    boxed = {'base': 'normal', 'block_color': '#f00', 'block_padding': 1}
    texel = Group([Text('X'), _nl(boxed, endmark=True)])
    factory = RowFactory(testsheet, TESTDEVICE, line_width=400)
    records = list(factory.generate_rows(texel, 0))

    box = typeset_into_rect(records, 10, TESTDEVICE, hpad=4, vpad=2,
                             style={'cell_bgcolor': '#eee'})

    # Cell background covers the whole cell including padding.
    assert box.width == 14  # 10 + hpad
    assert box.height == 5  # 1 (row) + 2*block_padding + vpad
    assert box.decorations[0] == (0, 0, 14, 5, '#eee')

    # Block color only around the paragraph group, inside the cell
    # padding (lpad=2), fully contained within the cell background.
    assert box.decorations[1] == (2, 1, 10, 3, '#f00')

    # The row itself is shifted by lpad/tpad.
    assert box.data[0][0] == 2  # lpad
    assert box.data[0][1] == 2  # tpad(1) + block_padding(1)
