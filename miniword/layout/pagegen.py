# -*- coding:utf-8-*-


# This file implements a "minimal" typesetting model:
# - greedy line breaking
# - no hyphenation
# - no flow around objects
#
# pagegen is designed in a way that it can be replaced with a more
# advanced layout model later implementing Knuth-Plass-Linebreaking.
#


from types import SimpleNamespace

from .testdevice import TESTDEVICE
from .boxes import TextBox
from .linewrap import simple_linewrap
from .stretchable import justify_line
from .page import ForceBreakBox, Row, Page, FootnoteBox
from .counters import format_number, set_counter, inc_counter
from ..core.units import mm, cm, pt
from ..core.styles import updated, n_levels
from ..core.papersizes import PAPER_SIZES
from ..core.document import settings_default
from ..tables.table_boxes import TableBox, split_at_height
from ..footnotes.footnotes import FootnoteAnchorBox

from copy import copy as shallow_copy


# Needed for testing
A4 = 210 * mm, 297 * mm

FOOTNOTE_FRACTION = 0.10  # max fraction of page height reserved for footnotes

MIN_LABEL_INDENT = 10  # minimum hanging indent for footnote label (pt)
LABEL_GAP = 3          # gap between label and content (pt)

def copy_counters(counters):
    """Deep-copy a dict of mutable counter lists (style -> list[int])."""
    return {k: list(v) for k, v in counters.items()}


class DraftNode:
    """
    Stack rows vertically (y grows downward).

    Adjusts row.height and row.depth so that:
    - rows are tightly stacked (no gaps, no overlap)
    - line_spacing factor is respected
    - hit-testing and selection work on box geometry
    """

    rows = ()
    decorations = ()
    footnotes = ()
    footnote_height = 0
    floats = ()
    parent = None
    startspage = True
    x = y = None

    # defaults for testing:
    geometry = A4
    border = 2*cm, 2*cm, 2*cm, 2*cm

    def init_xy(self):
        self.x = self.border[-1]  # ignored in the minimal model
        self.y = self.border[0]

    def is_empty(self):
        return (len(self.rows) == 0
                and len(self.footnotes) == 0
                and len(self.floats) == 0)

    def can_addrow(self, row, line_spacing, before):
        """Can the current page hold row or do we need to create a new page?"""
        if not self.rows:
            # always accept first row even if oversized
            return True
        natural = row.height + row.depth
        advance = natural * line_spacing
        border_top, _, border_bottom, _ = self.border
        max_y = (self.geometry[1] - border_top - border_bottom
                 - self.footnote_height)
        return self.y + before + advance <= max_y

    def can_addfootnote(self, row, line_spacing=1.0, is_last_page=False):
        """Can this footnote row still fit within the footnote area?"""
        # Is the page full?
        if not self.can_addrow(row, line_spacing, 0):
            # XXX don we need 'before'?
            return False
        # Is the max footnote fraction reached?
        page_height = self.geometry[1] - self.border[0] - self.border[2]
        limit = (page_height if is_last_page
                 else page_height * FOOTNOTE_FRACTION)
        advance = (row.height + row.depth) * line_spacing
        return self.footnote_height + advance <= limit

    def add_footnote(self, row, line_spacing=1.0):
        """Reserve space and record a footnote row."""
        advance = (row.height + row.depth) * line_spacing
        self.footnote_height += advance
        self.footnotes += (row,)

    def add_row(self, row, line_spacing, before):
        """Add row to the draft page."""

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

        if self.rows:
            extra_top += before

        row.height += extra_top
        row.depth += extra_bottom

        self.rows += ((0, self.y, row),)
        self.y += row.height + row.depth

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
        draft.rows = ()
        draft.decorations = ()
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
                        memo.footnotes, memo, draw_separator=bool(memo.rows))
                    page = Page(memo.rows, self.geometry, footnotebox,
                                device=device)
                    page.decorations = memo.decorations
                    pages.append(page)
                memo = RestartMemo()
                memo.geometry = node.geometry
                memo.border = node.border
            memo.rows += node.rows
            memo.decorations += node.decorations
            memo.floats += node.floats
            memo.footnotes += node.footnotes
            memo.footnote_height = node.footnote_height
            memo.y = node.y

        return pages, memo


class RestartMemo:
    """Carries the state needed to resume page building after an interruption.

    Also used as the return value of finalize_draft() to describe spillover
    content that did not fit on the last completed page.
    """
    rows = ()
    decorations = ()
    footnotes = ()
    footnote_height = 0
    floats = ()
    parent = None
    y = None
    counters = {}   # dict: numbering_style -> list[int] of length n_levels

    # defaults for testing
    geometry = A4
    border = 2*cm, 2*cm, 2*cm, 2*cm

    def get_length(self):
        n = 0
        for _, _, row in self.rows:
            n += len(row)
        return n

    def start_draft(self):
        node = DraftNode()
        node.rows = self.rows
        node.decorations = self.decorations
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
        # counters contains mutable lists — deep copy required so that
        # future increments do not corrupt previously saved snapshots.
        new.counters = copy_counters(self.counters)
        return new



def restartmemo_from_settings(settings):
    """Convert document settings to a RestartMemo with geometry/border."""
    props = updated(settings_default, settings)
    paper = props['paper']
    if paper in PAPER_SIZES:
        w, h = PAPER_SIZES[paper]
    else:
        w, h = props['paper_width'], props['paper_height']
    memo = RestartMemo()
    memo.geometry = (w, h)
    memo.border = (props['margin_top'], props['margin_right'],
                   props['margin_bottom'], props['margin_left'])
    return memo



def split_at_breaks(boxlist):
    """Split boxlist at ForceBreakBox markers; each marker ends its segment."""

    segments, current = [], []
    for box in boxlist:
        current.append(box)
        if isinstance(box, ForceBreakBox):
            segments.append(current)
            current = []
    if current:
        segments.append(current)
    return segments


def split_at_tables(boxlist):
    """Split boxlist at TableBox boundaries.
    Each TableBox becomes its own single-element segment."""
    segments, current = [], []
    for box in boxlist:
        if isinstance(box, TableBox):
            if current:
                segments.append(current)
                current = []
            segments.append([box])
        else:
            current.append(box)
    if current:
        segments.append(current)
    return segments




def place_longtable(box, draft, device):
    """Place a break_level>=1 TableBox as one or more fragments onto drafts."""
    row_offset = 0

    while box is not None and box.n_rows > box.header_rows:
        frag, box = split_at_height(box, draft.remaining_height())
        frag.row_offset = row_offset
        draft.add_row(Row([frag], left=draft.border[3], device=device), 1.0, 0)
        row_offset += frag.n_rows
        if box is not None:
            draft = draft.create_newpage()

    return draft



def position_footnotes(fn_rows, memo, draw_separator=True):
    """Return a (x, y, FootnoteBox) tuple with the footnote rows.

    Normally the box is anchored above the bottom margin. If it fills the
    whole page (no separator, no other content), it starts at the top
    margin instead. Returns None if there are no footnotes.
    """
    if not fn_rows:
        return None
    border_top, _, border_bottom, border_left = memo.border
    box = FootnoteBox(list(fn_rows), memo.geometry[0], draw_separator,
                       device=fn_rows[0].device)
    x = border_left
    if draw_separator:
        y = memo.geometry[1] - border_bottom - (box.height + box.depth)
    else:
        y = border_top
    return x, y, box




def render_footnote_rows(fn_texel, factory, line_width, label=None):
    """Render a Footnote texel's content into a list of Row objects.

    Reuses generate_pages with allow_page_breaks=False, the same way
    table_factory.build_cell() renders a table cell's content into rows.
    """
    memo = RestartMemo()
    memo.geometry = (line_width, 10**9)
    memo.border = (0, 0, 0, 0)

    label_style = {}
    label_w = 0
    indent = MIN_LABEL_INDENT
    if label is not None:
        outer = factory.mk_style({})
        label_style = {**outer, 'vertical_position': 'superscript'}
        label_w = factory.device.measure(label, label_style)[0]
        indent = max(MIN_LABEL_INDENT, label_w + LABEL_GAP)
        memo.border = (0, 0, 0, indent)

    saved = {k: getattr(factory, k, None)
             for k in ('line_width', 'parstyle', 'markerstyle', 'indent_level',
                       'footnote_counter')}

    # fn_texel.content must end with an ENDMARK so that iter_paragraphs()
    # yields it, and so that len(content) matches the rows' total length.
    page = None
    for page in generate_pages(fn_texel.content, 0, memo, factory,
                                allow_page_breaks=False, footnotes=[]):
        pass  # expect exactly one page

    for k, v in saved.items():
        if v is not None:
            setattr(factory, k, v)

    rows = [row for _, _, row in page.rows] if page else []
    if rows and label is not None:
        rows[0].set_marker(label, -(label_w + LABEL_GAP), label_style)
        if indent > MIN_LABEL_INDENT:
            extra = indent - MIN_LABEL_INDENT
            for row in rows[1:]:
                row.start = (row.start[0] - extra, row.start[1])
                row.width -= extra
    return rows


def place_pending_footnotes(fn_rows, draft, is_last_page=False):
    """Place as many footnote rows as fit onto draft; return unplaced rows.

    Stops at the first row that doesn't fit — placing a later row ahead of
    an earlier one that's still pending would put the footnote boxes out
    of document order.
    """
    remaining = []
    for row in fn_rows:
        fits = draft.can_addfootnote(row, is_last_page=is_last_page)
        if not remaining and fits:
            draft.add_footnote(row)
        else:
            remaining.append(row)
    return remaining


def line_dims(s, level, margin, line_width):
    """Left edge and width for a paragraph's first line and other lines."""
    in_any_list = s.paragraph_type in ('list', 'numbered')
    list_indent = s.list_indent if in_any_list else 0
    block_indent = s.indent_levels[level] + list_indent
    left_rest = margin[3] + block_indent
    left_first = left_rest + s.first_line_indent
    width_rest = line_width - block_indent
    width_first = width_rest - s.first_line_indent
    return SimpleNamespace(
        in_any_list=in_any_list,
        left_rest=left_rest, left_first=left_first,
        width_rest=width_rest, width_first=width_first)


def make_marker(s, factory, level, counters, row):
    """Compute and attach the list/numbering marker for row's first line."""
    sm = factory.mk_style(factory.markerstyle)  # sm: style of the marker glyph
    sm['font_size'] *= sm['marker_size'][level]
    sm['color'] = sm['marker_color'][level]
    pos = s.marker_pos[level]

    if s.paragraph_type == 'list':
        marker = s.marker[level]
    else:  # 'numbered'
        ns = s.numbering_style[level]
        ckey = s.counter
        if ckey not in counters:
            counters[ckey] = [0] * n_levels
        counter = counters[ckey]
        sn = s.start_number
        if sn is not None:
            set_counter(level, counter, sn)
        else:
            inc_counter(level, counter)
        if ckey == 'section':
            # a section count clears the item counter
            counters['item'] = [0] * n_levels
        marker = format_number(counters[ckey], level, ns)

    row.set_marker(marker, pos, sm)


def align_x(alignment, left, width, text_width):
    """x-position of a row's left edge for the given paragraph alignment."""
    if alignment in ('left', 'justify'):
        return left
    if alignment == 'right':
        return left + (width - text_width)
    if alignment == 'center':
        return left + 0.5 * (width - text_width)
    assert False


def place_anchors(line, factory, width, draft, pending):
    """Render and place any footnote anchors found in line.

    Once a row didn't fit, every later row (same footnote or a later
    one) must also defer — placing a later footnote ahead of an
    earlier pending one would put the footnote boxes out of document
    order.
    """
    for box in line:
        if not isinstance(box, FootnoteAnchorBox):
            continue
        for fn_row in render_footnote_rows(
                box.fn_texel, factory, width, label=box.display):
            if not pending and draft.can_addfootnote(fn_row):
                draft.add_footnote(fn_row)
            else:
                pending.append(fn_row)


def final_pages(state, pending_fn_rows, device, allow_page_breaks):
    """Yield the final page(s) after generate_pages' main loop ends.

    With page breaks allowed: flush the trailing body rows together with
    whatever footnotes still fit, then keep emitting footnote-only pages
    as long as footnotes remain unplaced. Without page breaks (e.g. inside
    a table cell), everything must already fit on the single page built.
    """
    if not allow_page_breaks:
        if state.rows:
            footnotebox = position_footnotes(state.footnotes, state)
            page = Page(state.rows, state.geometry, footnotebox, device=device)
            page.decorations = state.decorations
            yield page
        return

    if not (state.rows or pending_fn_rows):
        return

    empty_state = RestartMemo()
    empty_state.geometry = state.geometry
    empty_state.border = state.border

    body_state = state
    while body_state is not None or pending_fn_rows:
        draft = (body_state or empty_state).start_draft()
        remaining = place_pending_footnotes(
            pending_fn_rows, draft, is_last_page=True)
        if (body_state is None and pending_fn_rows
                and remaining == pending_fn_rows):
            # a single footnote row taller than the page: place it
            # anyway to avoid an infinite loop.
            draft.add_footnote(pending_fn_rows[0])
            remaining = pending_fn_rows[1:]
        pending_fn_rows = remaining
        body_state = None
        draft = draft.create_newpage()
        pages, _ = draft.finalize_draft(device)
        yield from pages


def generate_pages(texel, i, restartmemo, factory,
                   footnotes=None, floats=None, allow_page_breaks=True):
    """Generator producing a stream of pages.

    footnotes, floats: if provided, collected items are appended to these
    lists instead of being handled internally. Useful for container content
    where footnotes/floats belong to the enclosing page.
    allow_page_breaks: set to False for containers that must not insert
    page breaks (all content stays on one 'page').
    """
    device = factory.device

    # In this minimal model, state and RestartMemo are the same thing.
    state = restartmemo.copy()

    # Restore per-style counter arrays from the restart memo so that
    # numbered lists continue with the correct numbers after a restart.
    counters = copy_counters(state.counters)

    # Shift the box-generator start position by the amount of row
    # material already present in the restart memo.
    j = i + restartmemo.get_length()

    margin = state.border  # top right bottom left
    page_width = state.geometry[0]
    factory.line_width = page_width - margin[1] - margin[3]
    factory.footnote_counter = 0

    pending_fn_rows = []

    for _, _, boxlist in factory.generate_boxes(texel, j):
        draft = state.start_draft()

        # bad way to get filled parstyle
        s = SimpleNamespace(**factory.mk_style({}))

        if allow_page_breaks and s.page_break_before and not draft.is_empty():
            draft = draft.create_newpage()

        level = factory.indent_level
        dims = line_dims(s, level, margin, factory.line_width)
        # read once per paragraph, not per line: avoids repeated attribute
        # lookups in the line loop below, which can run many times over
        alignment = s.alignment
        line_spacing = s.line_spacing

        first = True
        before = s.space_before

        for seg in split_at_tables(boxlist):
            if (len(seg) == 1
                    and isinstance(seg[0], TableBox)
                    and seg[0].break_level >= 1):
                draft = place_longtable(seg[0], draft, device)
                first = False
                before = 0
                continue

            for sub in split_at_breaks(seg):
                w = dims.width_first if first else dims.width_rest
                lines = simple_linewrap(sub, w, dims.width_rest)
                n = len(lines)
                for idx, line in enumerate(lines):
                    line_width = dims.width_first if first else dims.width_rest
                    line_left = dims.left_first if first else dims.left_rest

                    if alignment == 'justify' and idx < n - 1:
                        line = justify_line(line, line_width)
                    row = Row(line, device=device)

                    if first and dims.in_any_list:
                        make_marker(s, factory, level, counters, row)

                    if not draft.can_addrow(row, line_spacing, before):
                        draft = draft.create_newpage()
                        pending_fn_rows = place_pending_footnotes(
                            pending_fn_rows, draft)

                    x = align_x(alignment, line_left, line_width, row.width)
                    row.start = (x, 0)
                    row.width = line_width + x
                    y_before = draft.y
                    draft.add_row(row, line_spacing, before)
                    place_anchors(
                        line, factory, dims.width_rest, draft, pending_fn_rows)
                    if s.block_color:
                        pad = s.block_padding or 0
                        draft.decorations += ((
                            margin[3] - pad, y_before - pad,
                            factory.line_width + 2 * pad,
                            row.height + row.depth + 2 * pad,
                            s.block_color),)
                    first = False
                    before = 0

        if s.space_after:
            draft.y += s.space_after
            # XXX adjust depth of last row?

        pages, state = draft.finalize_draft(device)
        state.counters = copy_counters(counters)
        if footnotes is not None:
            footnotes.extend(state.footnotes)
        if floats is not None:
            floats.extend(state.floats)
        if pages:
            pages[0].restartmemo = restartmemo
            restartmemo = state.copy()
        for page in pages:
            yield page

    yield from final_pages(state, pending_fn_rows, device, allow_page_breaks)


# --- Tests ---

def test_00():
    w_pt = A4[0] / pt
    h_pt = A4[1] / pt
    assert abs(w_pt - 595.276) < 1e-2
    assert abs(h_pt - 841.890) < 1e-2

    w_cm = A4[0] / cm
    h_cm = A4[1] / cm
    assert abs(w_cm - 21) < 1e-2
    assert abs(h_cm - 29.7) < 1e-2


def test_01():
    "start and fix draft"

    # Walk through the process manually
    memo = RestartMemo()
    memo.geometry = (100, 10)
    memo.border = 1, 1, 1, 1
    draft = memo.start_draft()

    for i in range(20):
        row = TextBox("Row %i" % i)
        if not draft.can_addrow(row, 1.0, 0):
            draft = draft.create_newpage()
        draft.add_row(row, 1.0, 0)
    pages, restartmemo = draft.finalize_draft(TESTDEVICE)
    assert len(pages) > 0
    assert len(restartmemo.rows) > 0

    draft = restartmemo.start_draft()
    for i in range(10):
        row = TextBox("New row %i" % i)
        draft.add_row(row, 1.0, 0)

    pages2, restartmemo2 = draft.finalize_draft(TESTDEVICE)
    # rows that fit on one page end up in restartmemo, not pages
    assert len(pages2) + len(restartmemo2.rows) > 0


def test_02():
    "generate_pages"

    import einstein
    from ..core.styles import testsheet
    from .factory import Factory
    model = einstein.get_einstein_model()
    texel = model.get_xtexel()
    device = TESTDEVICE
    factory = Factory(testsheet, device)

    memo = RestartMemo()
    memo.geometry = (100, 10)
    memo.border = 1, 1, 1, 1

    allpages = []
    for page in generate_pages(texel, 0, memo, factory):
        allpages.append(page)

    assert len(allpages) > 0


def test_03():
    "place_pending_footnotes: a later, smaller row must not jump a pending one"

    class FakeRow:
        def __init__(self, height):
            self.height = height
            self.depth = 0

    memo = RestartMemo()
    memo.geometry = (100, 50)
    memo.border = 1, 1, 1, 1
    draft = memo.start_draft()
    draft.add_row(TextBox("body"), 1.0, 0)  # page is no longer empty

    tall = FakeRow(1000)  # taller than the page: never fits
    short = FakeRow(1)    # would easily fit on its own

    remaining = place_pending_footnotes([tall, short], draft)
    assert remaining == [tall, short]
    assert draft.footnotes == ()

