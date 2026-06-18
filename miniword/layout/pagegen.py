# -*- coding:utf-8-*-


# This file implements a "minimal" typesetting model:
# - greedy line breaking
# - no hyphenation
# - no flow around objects
#
# pagegen is designed in a way that it can be replaced with a more
# advanced layout model later implementing Knuth-Plass-Linebreaking.
#


from .testdevice import TESTDEVICE
from .boxes import TextBox
from .linewrap import simple_linewrap
from ..core.units import mm, cm, pt
from ..core.styles import updated, n_levels
from ..core.papersizes import PAPER_SIZES
from ..core.document import settings_default
from .stretchable import justify_line
from .page import ForceBreakBox, Row, Page, FootnoteBox
from .counters import format_number, set_counter, inc_counter
from ..tables.table_boxes import TableBox, split_at_height
from ..footnotes.footnotes import FootnoteAnchorBox

from copy import copy as shallow_copy


# Needed for testing
A4 = 210 * mm, 297 * mm

MAX_FOOTNOTE_AREA_FRACTION = 0.10  # max fraction of page height reserved for footnotes


def _copy_counters(counters):
    """Deep-copy a dict of mutable counter lists (numbering_style -> list[int])."""
    return {k: list(v) for k, v in counters.items()}


class DraftNode:
    """
    Stack rows vertically (y grows downward).

    Adjusts row.height and row.depth so that:
    - rows are tightly stacked (no gaps, no overlap)
    - line_spacing factor is respected
    - hit-testing and selection work on box geometry
    """

    rows            = ()
    decorations     = ()
    footnotes       = ()
    footnote_height = 0
    floats          = ()
    parent          = None
    startspage  = True
    x = y = None

    # defaults for testing:
    geometry   = A4
    border     = 2*cm, 2*cm, 2*cm, 2*cm

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
        max_y = self.geometry[1] - border_top - border_bottom - self.footnote_height
        return self.y + before + advance <= max_y

    def can_addfootnote(self, row, line_spacing=1.0, is_last_page=False):
        """Can this footnote row still fit within the footnote area?"""
        # Is the page full?
        if not self.can_addrow(row, line_spacing, 0):
            # XXX don we need 'before'?
            return False
        # Is the max footnote fraction reached?
        page_height = self.geometry[1] - self.border[0] - self.border[2]
        limit = page_height if is_last_page else page_height * MAX_FOOTNOTE_AREA_FRACTION
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

        extra_top    = extra * 0.5
        extra_bottom = extra * 0.5

        if self.rows:
            extra_top += before
            
        row.height += extra_top
        row.depth  += extra_bottom

        self.rows += ((0, self.y, row),)
        self.y += row.height + row.depth

    def remaining_height(self):
        """Free vertical space from current y to bottom margin."""
        border_top, _, border_bottom, _ = self.border
        return self.geometry[1] - border_top - border_bottom - self.y

    def create_child(self):
        """Create a child node. Can be used to fork or to append a new page. """
        r = shallow_copy(self)
        r.parent = self
        return r

    def create_newpage(self):
        """Create an empty new page."""
        draft = self.create_child()
        draft.startspage    = True
        draft.init_xy()
        draft.rows          = ()
        draft.decorations   = ()
        draft.floats        = ()
        draft.footnotes     = ()
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
                    footnotebox = _position_footnotes(
                        memo.footnotes, memo, draw_separator=bool(memo.rows))
                    page = Page(memo.rows, self.geometry, footnotebox, device=device)
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
    rows            = ()
    decorations     = ()
    footnotes       = ()
    footnote_height = 0
    floats          = ()
    parent          = None
    y               = None
    counters        = {}   # dict: numbering_style -> list[int] of length n_levels

    # defaults for testing
    geometry    = A4
    border      = 2*cm, 2*cm, 2*cm, 2*cm

    def get_length(self):
        n = 0
        for x, y, row in self.rows:
            n += len(row)
        return n

    def start_draft(self):
        node                 = DraftNode()
        node.rows            = self.rows
        node.decorations     = self.decorations
        node.floats          = self.floats
        node.footnotes       = self.footnotes
        node.footnote_height = self.footnote_height
        node.geometry        = self.geometry
        node.border          = self.border
        node.init_xy()
        if self.y is not None:
            node.y = self.y
        return node

    def copy(self):
        new = shallow_copy(self)
        # counters contains mutable lists — deep copy required so that
        # future increments do not corrupt previously saved snapshots.
        new.counters = _copy_counters(self.counters)
        return new



def restartmemo_from_settings(settings):
    """Convert a document settings dict to a RestartMemo with geometry/border."""
    props = updated(settings_default, settings)
    paper = props['paper']
    if paper in PAPER_SIZES:
        w, h = PAPER_SIZES[paper]
    else:
        w, h = props['paper_width'], props['paper_height']
    memo = RestartMemo()
    memo.geometry = (w, h)
    memo.border   = (props['margin_top'],    props['margin_right'],
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



def _position_footnotes(fn_rows, memo, draw_separator=True):
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


_MIN_LABEL_INDENT = 10   # minimum hanging indent for footnote label (pt)
_LABEL_GAP        = 3    # gap between label and content (pt)


def render_footnote_rows(fn_texel, factory, line_width, label=None):
    """Render a Footnote texel's content into a list of Row objects.

    Reuses generate_pages with allow_page_breaks=False, the same way
    table_factory.build_cell() renders a table cell's content into rows.
    """
    memo = RestartMemo()
    memo.geometry = (line_width, 10**9)
    memo.border   = (0, 0, 0, 0)

    label_style = {}
    label_w     = 0
    indent      = _MIN_LABEL_INDENT
    if label is not None:
        outer = factory.mk_style({})
        label_style = {**outer, 'vertical_position': 'superscript'}
        label_w = factory.device.measure(label, label_style)[0]
        indent  = max(_MIN_LABEL_INDENT, label_w + _LABEL_GAP)
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
        rows[0].set_marker(label, -(label_w + _LABEL_GAP), label_style)
        if indent > _MIN_LABEL_INDENT:
            extra = indent - _MIN_LABEL_INDENT
            for row in rows[1:]:
                row.start = (row.start[0] - extra, row.start[1])
                row.width -= extra
    return rows


def place_pending_footnotes(fn_rows, draft, is_last_page=False):
    """Place as many footnote rows as possible onto draft; return unplaced rows.

    Stops at the first row that doesn't fit — placing a later row ahead of
    an earlier one that's still pending would put the footnote boxes out
    of document order.
    """
    remaining = []
    for row in fn_rows:
        if not remaining and draft.can_addfootnote(row, is_last_page=is_last_page):
            draft.add_footnote(row)
        else:
            remaining.append(row)
    return remaining


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
    counters = _copy_counters(state.counters)

    # Shift the box-generator start position by the amount of row
    # material already present in the restart memo.
    j = i + restartmemo.get_length()

    margin     = state.border  # top right bottom left
    page_width = state.geometry[0]
    factory.line_width = page_width - margin[1] - margin[3]
    factory.footnote_counter = 0

    pending_fn_rows = []

    for i1, i2, boxlist in factory.generate_boxes(texel, j):
        draft = state.start_draft()

        # bad way to get filled parstyle
        r = factory.mk_style({})

        if allow_page_breaks and r['page_break_before'] and not draft.is_empty():
            draft = draft.create_newpage()

        indent            = factory.indent_level
        first_line_indent = r['first_line_indent']
        indent_levels     = r['indent_levels']
        in_any_list       = r['paragraph_type'] in ('list', 'numbered')
        list_indent       = r['list_indent'] if in_any_list else 0
        block_indent      = indent_levels[indent] + list_indent
        alignment         = r['alignment']
        line_spacing      = r['line_spacing']
        space_before      = r['space_before']
        space_after       = r['space_after']

        line_left_rest   = margin[3] + block_indent
        line_left_first  = line_left_rest + first_line_indent
        line_width_rest  = factory.line_width - block_indent
        line_width_first = line_width_rest - first_line_indent

        first  = True
        before = space_before

        for seg in split_at_tables(boxlist):
            if (len(seg) == 1
                    and isinstance(seg[0], TableBox)
                    and seg[0].break_level >= 1):
                draft  = place_longtable(seg[0], draft, device)
                first  = False
                before = 0
                continue

            for sub in split_at_breaks(seg):
                w     = line_width_first if first else line_width_rest
                lines = simple_linewrap(sub, w, line_width_rest)
                n     = len(lines)
                for idx, line in enumerate(lines):
                    line_width = line_width_first if first else line_width_rest
                    line_left  = line_left_first  if first else line_left_rest

                    if alignment == 'justify' and idx < n - 1:
                        line = justify_line(line, line_width)
                    row = Row(line, device=device)

                    if first and in_any_list:
                        marker_style = factory.mk_style(factory.markerstyle)
                        marker_style['font_size'] *= marker_style['marker_size'][indent]
                        marker_style['color'] = marker_style['marker_color'][indent]
                        pos = r['marker_pos'][indent]

                        if r['paragraph_type'] == 'list':
                            marker = r['marker'][indent]
                            row.set_marker(marker, pos, marker_style)

                        else:  # 'numbered'
                            ns = r['numbering_style'][indent]
                            ckey = r['counter']
                            if ckey not in counters:
                                counters[ckey] = [0] * n_levels
                            counter = counters[ckey]
                            sn = r.get('start_number')
                            if sn is not None:
                                set_counter(indent, counter, sn)
                            else:
                                inc_counter(indent, counter)
                            if ckey == 'section':
                                # a section count clears the item counter
                                counters['item'] = [0] * n_levels
                            marker = format_number(counters[ckey], indent, ns)
                            row.set_marker(marker, pos, marker_style)

                    if not draft.can_addrow(row, line_spacing, before):
                        draft = draft.create_newpage()
                        pending_fn_rows = place_pending_footnotes(
                            pending_fn_rows, draft)

                    text_width = row.width
                    if alignment in ('left', 'justify'):
                        x = line_left
                    elif alignment == 'right':
                        x = line_left + (line_width - text_width)
                    elif alignment == 'center':
                        x = line_left + 0.5 * (line_width - text_width)
                    else:
                        assert False

                    row.start = (x, 0)
                    row.width = line_width + x
                    y_before  = draft.y
                    draft.add_row(row, line_spacing, before)
                    for box in line:
                        if isinstance(box, FootnoteAnchorBox):
                            for fn_row in render_footnote_rows(
                                    box.fn_texel, factory, line_width_rest,
                                    label=box.display):
                                # Once a row didn't fit, every later row (same
                                # footnote or a later one) must also defer —
                                # placing a later footnote ahead of an earlier
                                # pending one would put the footnote boxes out
                                # of document order.
                                if not pending_fn_rows and draft.can_addfootnote(fn_row):
                                    draft.add_footnote(fn_row)
                                else:
                                    pending_fn_rows.append(fn_row)
                    if r.get('block_color'):
                        pad = r.get('block_padding') or 0
                        draft.decorations += ((
                            margin[3] - pad, y_before - pad,
                            factory.line_width + 2 * pad,
                            row.height + row.depth + 2 * pad,
                            r['block_color']),)
                    first  = False
                    before = 0

        if space_after:
            draft.y += space_after
            # XXX adjust depth of last row?

        pages, state = draft.finalize_draft(device)
        state.counters = _copy_counters(counters)
        if footnotes is not None:
            footnotes.extend(state.footnotes)
        if floats is not None:
            floats.extend(state.floats)
        if pages:
            pages[0].restartmemo = restartmemo
            restartmemo = state.copy()
        for page in pages:
            yield page

    # Yield remaining content as the final page(s): first the trailing body
    # rows together with whatever footnotes still fit, then — as long as
    # footnotes remain unplaced — dedicated footnote-only pages.
    if allow_page_breaks:
        if state.rows or pending_fn_rows:
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
                for page in pages:
                    yield page
    elif state.rows:
        footnotebox = _position_footnotes(state.footnotes, state)
        page = Page(state.rows, state.geometry, footnotebox, device=device)
        page.decorations = state.decorations
        yield page


# --- Tests ---

def test_00():
    w_pt = A4[0] / pt
    h_pt = A4[1] / pt
    assert abs(w_pt - 595.276) < 1e-2
    assert abs(h_pt - 841.890) < 1e-2

    w_cm = A4[0] / cm
    h_cm = A4[1] / cm
    assert abs(w_cm - 21)   < 1e-2
    assert abs(h_cm - 29.7) < 1e-2


def test_01():
    "start and fix draft"

    # Walk through the process manually
    info          = RestartMemo()
    info.geometry = (100, 10)
    info.border   = 1, 1, 1, 1
    draft         = info.start_draft()

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
    model   = einstein.get_einstein_model()
    texel   = model.get_xtexel()
    device  = TESTDEVICE
    factory = Factory(testsheet, device)

    info          = RestartMemo()
    info.geometry = (100, 10)
    info.border   = 1, 1, 1, 1

    allpages = []
    for page in generate_pages(texel, 0, info, factory):
        allpages.append(page)

    assert len(allpages) > 0


def test_03():
    "place_pending_footnotes must not let a later, smaller row jump ahead of a still-pending one"

    class FakeRow:
        def __init__(self, height):
            self.height = height
            self.depth  = 0

    info          = RestartMemo()
    info.geometry = (100, 50)
    info.border   = 1, 1, 1, 1
    draft         = info.start_draft()
    draft.add_row(TextBox("body"), 1.0, 0)  # page is no longer empty

    tall  = FakeRow(1000)  # taller than the page: never fits
    short = FakeRow(1)     # would easily fit on its own

    remaining = place_pending_footnotes([tall, short], draft)
    assert remaining == [tall, short]
    assert draft.footnotes == ()

