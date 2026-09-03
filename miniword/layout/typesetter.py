# -*- coding: utf-8 -*-

"""
typeset_into_rect turns row records (as produced by
RowFactory.generate_rows) into a fixed-width RowsBox: row positions,
plus block shadings/borders (block_color/border, grouped via
rowfactory.block_key/BLOCK_KEYS, spaced apart by block_padding) as
shadings/borders on the box. It knows nothing about cells, padding or
backgrounds - callers turn its plain RowsBox into whatever concrete
box they need (e.g. tables.table_boxes.create_cell for a table cell).
"""

from .boxes import RowsBox
from .rowfactory import block_key


def typeset_into_rect(records, width, device):
    """Lay out row records into a fixed-width RowsBox. Each paragraph's
    own space_before/space_after (independent of neighbors) pushes rows
    apart; consecutive paragraphs sharing the same block style
    (block_color/padding/border) are additionally grouped into one
    shading/border rect instead of one per paragraph, with block_padding
    pushing rows apart at the start/end of such a group."""
    y = 0
    data = []
    row_info = []  # (y, height+depth) per row
    for row, parstyle, begins_par, ends_par, begins_block, ends_block \
            in records:
        color, padding, border = block_key(parstyle)
        if begins_par:
            y += parstyle.get('space_before', 0)
        if begins_par and begins_block:
            y += padding
        data.append((0, y, row))
        row_info.append((y, row.height + row.depth))
        y += row.height + row.depth
        if ends_par and ends_block:
            y += padding
        if ends_par:
            y += parstyle.get('space_after', 0)

    shadings, borders = [], []
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
                rect = (0, top, width, bottom_y + bottom_h + padding - top)
                if color is not None:
                    shadings.append(rect + (color,))
                if border is not None:
                    borders.append(rect + (border,))

    return RowsBox(data, width, y, 0, (0, 0), shadings, borders, device)


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
    "Same-style paragraphs merge into one shading"
    texel = _make_block_doc()
    factory = RowFactory(testsheet, TESTDEVICE, line_width=400)
    records = list(factory.generate_rows(texel, 0))
    assert len(records) == 3

    box = typeset_into_rect(records, 400, TESTDEVICE)
    assert type(box) is RowsBox

    # TESTDEVICE: every row has height=1, depth=0.
    assert box.height == 7  # 1+1+1 + 2 top padding (P0) + 2 bottom padding (P1)
    assert box.shadings == [(0, 0, 400, 6, '#eee')]
    assert box.borders == [(0, 6, 400, 1, 'thin')]

    solo = {'base': 'normal', 'block_color': '#eee', 'block_padding': 3}
    solo_texel = Group([Text('Solo'), _nl(solo, endmark=True)])
    solo_records = list(factory.generate_rows(solo_texel, 0))
    solo_box = typeset_into_rect(solo_records, 400, TESTDEVICE)
    assert solo_box.height == 7  # 1 row + 3 top padding + 3 bottom padding
    assert solo_box.shadings == [(0, 0, 400, 7, '#eee')]
    assert solo_box.data[0][1] == 3

    # padding_only: block_padding without block_color/block_border still
    # reserves space, even though there is nothing to draw.
    padding_only = {'base': 'normal', 'block_padding': 4}
    po_texel = Group([Text('Padded'), _nl(padding_only, endmark=True)])
    po_records = list(factory.generate_rows(po_texel, 0))
    po_box = typeset_into_rect(po_records, 400, TESTDEVICE)
    assert po_box.height == 9  # 1 row + 4 top padding + 4 bottom padding
    assert po_box.shadings == []
    assert po_box.data[0][1] == 4

    # A paragraph wrapping into several rows still gets exactly ONE
    # shading rect spanning the full paragraph height (not one per row).
    wrapped = {'base': 'normal', 'block_color': '#eee', 'block_padding': 2}
    wrap_texel = Group([Text('Aaa '), Text('Bbb '), Text('Ccc '), Text('Ddd '),
                         _nl(wrapped, endmark=True)])
    wrap_factory = RowFactory(testsheet, TESTDEVICE, line_width=8)
    wrap_records = list(wrap_factory.generate_rows(wrap_texel, 0))
    assert len(wrap_records) > 1  # must actually wrap
    wrap_box = typeset_into_rect(wrap_records, 8, TESTDEVICE)
    assert len(wrap_box.shadings) == 1
    n_rows = len(wrap_records)
    assert wrap_box.shadings == [(0, 0, 8, n_rows + 4, '#eee')]


def test_01():
    "space_before/space_after push rows apart"
    spaced = {'base': 'normal', 'space_before': 5, 'space_after': 3}
    plain = {'base': 'normal'}
    texel = Group([
        Text('One'), _nl(plain),
        Text('Two'), _nl(spaced, endmark=True),
    ])
    factory = RowFactory(testsheet, TESTDEVICE, line_width=400)
    records = list(factory.generate_rows(texel, 0))
    assert len(records) == 2

    box = typeset_into_rect(records, 400, TESTDEVICE)
    # TESTDEVICE: each row has height=1, depth=0.
    # P0 ("One"): plain, no spacing. P1 ("Two"): its own space_before
    # pushes it down; its own space_after adds trailing space after it.
    assert box.data[0][1] == 0          # P0 at y=0
    assert box.data[1][1] == 1 + 5      # P0 height(1) + P1's space_before(5)
    assert box.height == 1 + 5 + 1 + 3  # P0 + space_before + P1 + space_after

    # Combined with a block decoration: space_before/after stay OUTSIDE
    # the decoration rect, which only wraps the block-padded content.
    boxed = {'base': 'normal', 'block_color': '#eee', 'block_padding': 2,
             'space_before': 5, 'space_after': 3}
    boxed_texel = Group([Text('X'), _nl(boxed, endmark=True)])
    boxed_records = list(factory.generate_rows(boxed_texel, 0))
    boxed_box = typeset_into_rect(boxed_records, 400, TESTDEVICE)
    # y: space_before(5) + block_padding(2) = 7 before the row.
    assert boxed_box.data[0][1] == 7
    # Decoration rect spans only the block-padded content (y=5..10),
    # excluding both space_before (0..5) and space_after (10..13).
    assert boxed_box.shadings == [(0, 5, 400, 5, '#eee')]
    assert boxed_box.height == 5 + 2 + 1 + 2 + 3  # space_before+pad+row+pad+space_after
