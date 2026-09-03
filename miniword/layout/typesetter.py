# -*- coding: utf-8 -*-

"""
block_decorations groups row records sharing the same block style
(block_color/border, via rowfactory.block_key/BLOCK_KEYS) into
shading/border rects, one per group instead of one per record.

typeset_into_rect turns row records (as produced by
RowFactory.generate_rows) into a fixed-width RowsBox: row positions
(spaced apart by space_before/space_after and, at a block_decorations
group's start/end, by block_padding) plus the group's shadings/
borders. It knows nothing about cells, padding or backgrounds -
callers turn its plain RowsBox into whatever concrete box they need
(e.g. tables.table_boxes.create_cell for a table cell).

DraftNode/RestartMemo/finalize_draft (page building, below) reuse
block_decorations the same way, once a draft page's row records are
final - see finalize_draft.
"""

from copy import copy as shallow_copy

from .boxes import RowsBox
from .rowfactory import RowFactory, block_key
from .page import Page, FootnoteBox
from .counters import copy_counters
from ..core.units import mm, cm


def space_before(record):
    """Extra vertical space to reserve before this row: space_before
    (once per paragraph, at its first row) plus block_padding at a
    block_decorations group's start."""
    row, parstyle, begins_par, ends_par, begins_block, ends_block = record
    space = parstyle.get('space_before', 0) if begins_par else 0
    if begins_par and begins_block:
        space += block_key(parstyle)[1] or 0
    return space


def space_after(record):
    """Extra vertical space to reserve after this row: block_padding
    at a block_decorations group's end, plus space_after (once per
    paragraph, at its last row)."""
    row, parstyle, begins_par, ends_par, begins_block, ends_block = record
    space = (block_key(parstyle)[1] or 0) if (ends_par and ends_block) else 0
    if ends_par:
        space += parstyle.get('space_after', 0)
    return space


def block_decorations(placed_records, left, width):
    """Group placed_records ((x, y, record), ...) into shading/border
    rects: consecutive records sharing the same block style
    (block_color/padding/border) merge into one rect instead of one
    per record. The very first/last record always closes off a group,
    even if its own begins_block/ends_block says the block continues
    beyond placed_records - a box or a finalized page only ever
    decorates its own, self-contained portion."""
    shadings, borders = [], []
    n = len(placed_records)
    row_info = [(y, record[0].height + record[0].depth)
                for _, y, record in placed_records]
    group_start = None
    for idx, (x, y, record) in enumerate(placed_records):
        _, parstyle, begins_par, ends_par, begins_block, ends_block = record
        if idx == 0 or (begins_par and begins_block):
            group_start = idx
        if idx == n - 1 or (ends_par and ends_block):
            group_parstyle = placed_records[group_start][2][1]
            color, padding, border = block_key(group_parstyle)
            if color is not None or border is not None:
                top = row_info[group_start][0] - padding
                bottom_y, bottom_h = row_info[idx]
                rect = (left, top, width, bottom_y + bottom_h + padding - top)
                if color is not None:
                    shadings.append(rect + (color,))
                if border is not None:
                    borders.append(rect + (border,))
    return shadings, borders


def typeset_into_rect(records, width, device):
    """Lay out row records into a fixed-width RowsBox: stack them via
    space_before/space_after (see there), then group them into
    shadings/borders via block_decorations."""
    y = 0
    data = []
    placed_records = []  # [(x, y, record)] - for block_decorations
    for record in records:
        row = record[0]
        y += space_before(record)
        data.append((0, y, row))
        placed_records.append((0, y, record))
        y += row.height + row.depth
        y += space_after(record)

    shadings, borders = block_decorations(placed_records, 0, width)
    return RowsBox(data, width, y, 0, (0, 0), shadings, borders, device)


# ---------------------------------------------------------------------
# Page building
# ---------------------------------------------------------------------

# Needed for testing
A4 = 210 * mm, 297 * mm

FOOTNOTE_FRACTION = 0.10  # max fraction of page height reserved for footnotes


def position_footnotes(fn_records, memo, draw_separator=True):
    """Return a (x, y, FootnoteBox) tuple built from footnote row
    records ((x, y, record), ...), decorated via block_decorations the
    same way a page's own body is. Returns None if there are none.

    Normally the box is anchored above the bottom margin. If it fills
    the whole page (no separator, no other content), it starts at the
    top margin instead."""
    if not fn_records:
        return None
    border_top, _, border_bottom, border_left = memo.border
    width = memo.geometry[0] - memo.border[1] - memo.border[3]
    shadings, borders = block_decorations(fn_records, 0, width)
    rows = [record[0] for _, _, record in fn_records]
    box = FootnoteBox(rows, memo.geometry[0], draw_separator, rows[0].device,
                       shadings, borders)
    x = border_left
    if draw_separator:
        y = memo.geometry[1] - border_bottom - (box.height + box.depth)
    else:
        y = border_top
    return x, y, box


class DraftNode:
    """Stacks row records vertically (y grows downward) while a page
    is being filled. Decorations are not computed here - see
    finalize_draft, which groups a completed page's own records via
    block_decorations once the page is known to be full.

    Adjusts row.height/row.depth so that:
    - rows are tightly stacked (no gaps, no overlap)
    - line_spacing factor is respected
    - hit-testing and selection work on box geometry
    """

    records = ()  # [(x, y, record), ...] - record = RowFactory row record
    footnotes = ()
    footnote_height = 0
    floats = ()
    parent = None
    startspage = True
    x = y = None

    # defaults for testing:
    geometry = A4
    border = 2 * cm, 2 * cm, 2 * cm, 2 * cm

    def init_xy(self):
        self.x = self.border[-1]  # ignored in the minimal model
        self.y = self.border[0]

    def is_empty(self):
        return (len(self.records) == 0
                and len(self.footnotes) == 0
                and len(self.floats) == 0)

    def _fits(self, row, line_spacing, before):
        """Would row (plus before, extra space reserved ahead of it)
        still fit before the bottom margin/footnote area?"""
        if not self.records:
            # always accept first row even if oversized
            return True
        advance = (row.height + row.depth) * line_spacing
        border_top, _, border_bottom, _ = self.border
        max_y = (self.geometry[1] - border_top - border_bottom
                 - self.footnote_height)
        return self.y + before + advance <= max_y

    def can_addrow(self, record, line_spacing):
        """Can the current page hold record or do we need a new page?"""
        return self._fits(record[0], line_spacing, space_before(record))

    def can_addfootnote(self, record, line_spacing=1.0, is_last_page=False):
        """Can this footnote row record still fit within the footnote
        area?"""
        row = record[0]
        if not self._fits(row, line_spacing, 0):
            return False
        page_height = self.geometry[1] - self.border[0] - self.border[2]
        limit = (page_height if is_last_page
                 else page_height * FOOTNOTE_FRACTION)
        before = space_before(record) if self.footnotes else 0
        advance = (row.height + row.depth) * line_spacing
        return self.footnote_height + before + advance + space_after(record) <= limit

    def add_footnote(self, record, line_spacing=1.0):
        """Add a footnote row record (row, parstyle, begins_par,
        ends_par, begins_block, ends_block) to the footnote area."""
        row = record[0]
        before = space_before(record) if self.footnotes else 0
        y = self.footnote_height + before
        self.footnotes += ((0, y, record),)
        advance = (row.height + row.depth) * line_spacing
        self.footnote_height = y + advance + space_after(record)

    def add_row(self, record, line_spacing):
        """Add a row record (row, parstyle, begins_par, ends_par,
        begins_block, ends_block) to the draft page."""
        row = record[0]

        # Natural box height
        natural = row.height + row.depth

        # Desired baseline advance
        advance = natural * line_spacing

        # Extra leading
        extra = advance - natural
        if extra < -0.5:
            # we allow negative leading, but not too much
            extra = -0.5

        extra_top = extra * 0.5
        extra_bottom = extra * 0.5

        if self.records:
            extra_top += space_before(record)

        row.height += extra_top
        row.depth += extra_bottom

        self.records += ((0, self.y, record),)
        self.y += row.height + row.depth + space_after(record)

    def remaining_height(self):
        """Free vertical space from current y to bottom margin."""
        border_top, _, border_bottom, _ = self.border
        return self.geometry[1] - border_top - border_bottom - self.y

    def create_child(self):
        """Create a child node. Can be used to fork or append a new page."""
        r = shallow_copy(self)
        r.parent = self
        return r

    def create_newpage(self):
        """Create an empty new page."""
        draft = self.create_child()
        draft.startspage = True
        draft.init_xy()
        draft.records = ()
        draft.floats = ()
        draft.footnotes = ()
        draft.footnote_height = 0
        return draft

    def finalize_draft(self, device):
        """
        Finalise draft by converting it (and all parents) to
        pages.

        Returns the list of completed pages and a RestartMemo
        describing any spillover that did not fit on the last page.
        """
        # Collect draft nodes — self is always included, so nodes is
        # never empty.
        nodes = []
        draft = self
        while draft:
            nodes.insert(0, draft)
            draft = draft.parent

        pages = []

        # Generate Pages
        assert nodes[0].startspage
        for i, node in enumerate(nodes):
            if node.startspage:
                if i > 0:
                    # Flush the completed page
                    footnotebox = position_footnotes(
                        memo.footnotes, memo, draw_separator=bool(memo.records))
                    rowdata = [(x, y, record[0]) for x, y, record in memo.records]
                    page = Page(rowdata, self.geometry, footnotebox,
                                device=device)
                    left = memo.border[3]
                    width = memo.geometry[0] - memo.border[1] - memo.border[3]
                    page.shadings, page.borders = block_decorations(
                        memo.records, left, width)
                    pages.append(page)
                memo = RestartMemo()
                memo.geometry = node.geometry
                memo.border = node.border
            memo.records += node.records
            memo.floats += node.floats
            memo.footnotes += node.footnotes
            memo.footnote_height = node.footnote_height
            memo.y = node.y

        return pages, memo


class RestartMemo:
    """Carries the state needed to resume page building after an interruption.

    Also used as the return value of finalize_draft() to describe spillover
    content that did not fit on the last completed page.

    row_restart is RowFactory's own restart tuple (j, counters,
    footnote_counter): j is always a paragraph start, never mid-
    paragraph. records may already contain the tail of a paragraph
    that was cut off by a page break - those records are carried along
    as already-finished data, not regenerated; RowFactory is only ever
    asked to continue from j, the next paragraph boundary."""
    records = ()  # [(x, y, record), ...]
    footnotes = ()
    footnote_height = 0
    floats = ()
    parent = None
    y = None
    row_restart = None  # RowFactory (j, counters, footnote_counter)

    # defaults for testing
    geometry = A4
    border = 2 * cm, 2 * cm, 2 * cm, 2 * cm

    def get_length(self):
        n = 0
        for _, _, record in self.records:
            n += len(record[0])
        return n

    def start_draft(self):
        node = DraftNode()
        node.records = self.records
        node.floats = self.floats
        node.footnotes = self.footnotes
        node.footnote_height = self.footnote_height
        node.geometry = self.geometry
        node.border = self.border
        node.init_xy()
        if self.y is not None:
            node.y = self.y
        return node

    def copy(self):
        new = shallow_copy(self)
        if self.row_restart is not None:
            j, counters, footnote_counter = self.row_restart
            # counters contains mutable lists — deep copy required so
            # that future increments do not corrupt previously saved
            # snapshots.
            new.row_restart = (j, copy_counters(counters), footnote_counter)
        return new


# ---------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------

from ..core.styles import testsheet
from ..textmodel.texeltree import Text, NewLine, Group
from .testdevice import TESTDEVICE
from .boxes import TextBox


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


def _rec(row, parstyle=None):
    "Minimal single-row-paragraph record for DraftNode tests."
    return (row, parstyle or {}, True, True, True, True)


def test_02():
    "DraftNode/RestartMemo: fill, finalize, resume"
    memo = RestartMemo()
    memo.geometry = (100, 10)
    memo.border = 1, 1, 1, 1
    draft = memo.start_draft()

    for i in range(20):
        row = TextBox("Row %i" % i)
        record = _rec(row)
        if not draft.can_addrow(record, 1.0):
            draft = draft.create_newpage()
        draft.add_row(record, 1.0)
    pages, restartmemo = draft.finalize_draft(TESTDEVICE)
    assert len(pages) > 0
    assert len(restartmemo.records) > 0

    draft = restartmemo.start_draft()
    for i in range(10):
        row = TextBox("New row %i" % i)
        draft.add_row(_rec(row), 1.0)

    pages2, restartmemo2 = draft.finalize_draft(TESTDEVICE)
    # rows that fit on one page end up in restartmemo, not pages
    assert len(pages2) + len(restartmemo2.records) > 0


def test_03():
    "block_decorations: page edges close an open group"
    boxed = {'base': 'normal', 'block_color': '#eee', 'block_padding': 2}
    # Simulate a block run split across a page break: row0 doesn't
    # begin the block (it continues from a previous page), row1
    # doesn't end it (it continues onto the next page) - but as the
    # only rows collected for THIS page, block_decorations must still
    # close a group around them.
    row0, row1 = TextBox("a"), TextBox("b")
    placed_records = [
        (0, 0, (row0, boxed, True, False, False, False)),
        (0, 1, (row1, boxed, False, True, False, False)),
    ]
    shadings, borders = block_decorations(placed_records, left=0, width=10)
    # top/height extend by block_padding(2) around both rows (height 1
    # each), even though neither row's own begins_block/ends_block
    # would normally trigger that on its own.
    assert shadings == [(0, -2, 10, 6, '#eee')]
    assert borders == []


def _texts(row):
    return ''.join(box.text for box in row.childs if isinstance(box, TextBox))


def test_04():
    "add_footnote/can_addfootnote work with records"
    memo = RestartMemo()
    memo.geometry = (100, 50)
    memo.border = 1, 1, 1, 1
    draft = memo.start_draft()
    draft.add_row(_rec(TextBox("body")), 1.0)  # page no longer empty

    normal = {'base': 'normal'}
    fn = Group([Text('Note.'), _nl(normal, endmark=True)])
    factory = RowFactory(testsheet, TESTDEVICE, line_width=50)
    record = list(factory.generate_rows(fn, 0))[0]

    assert draft.can_addfootnote(record)
    draft.add_footnote(record)
    assert len(draft.footnotes) == 1
    x, y, stored = draft.footnotes[0]
    assert (x, y) == (0, 0)
    assert stored is record
    assert draft.footnote_height == record[0].height + record[0].depth

    # Force finalize_draft to actually flush a page (a single node
    # never does, since it never crosses a startspage boundary).
    draft = draft.create_newpage()
    pages, restartmemo = draft.finalize_draft(TESTDEVICE)
    assert len(pages) == 1
    assert pages[0].footnotebox is not None
