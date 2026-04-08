# -*- coding:utf-8-*-


# This file implements a "minimal" typesetting model:
# - greedy line breaking
# - no hyphenation
# - no flow around objects
#
# pagegen is designed in a way that it can be replaced with a more
# advanced layout model later implementing Knuth-Plass-Linebreaking.
#



from ..wxtextview.testdevice import TESTDEVICE
from ..wxtextview.boxes import TextBox
from ..textmodel.texeltree import length, NewLine, EMPTYSTYLE
from ..textmodel.iterators import iter_paragraphs
from ..wxtextview.linewrap import simple_linewrap
from ..core.units import mm, cm, pt
from ..core.styles import updated, n_levels
from ..core.papersizes import PAPER_SIZES
from ..core.document import settings_default
from .factory import Factory, ForceBreakBox
from .stretchable import justify_line
from .page import Row, Page
from .counters import format_number

from copy import copy as shallow_copy


# Needed for testing
A4 = 210 * mm, 297 * mm


class DraftNode:
    """
    Stack rows vertically (y grows downward).

    Adjusts row.height and row.depth so that:
    - rows are tightly stacked (no gaps, no overlap)
    - line_spacing factor is respected
    - hit-testing and selection work on box geometry
    """

    rows        = ()
    decorations = ()
    footnotes   = ()
    floats      = ()
    parent      = None
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
        max_y = self.geometry[1] - border_top - border_bottom
        return self.y + before + advance <= max_y

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
        """Create  an empty new page."""
        draft = self.create_child()
        draft.startspage = True
        draft.init_xy()
        draft.rows        = ()
        draft.decorations = ()
        draft.floats      = ()
        draft.footnotes   = ()
        return draft

    def fix_draft(self, device):
        """
        Finalise draft by converting it (and all parents) to
        pages.

        Returns the list of completed pages and a RestartMemo
        describing any spillover that did not fit on the last page.
        """
        # Collect draft nodes
        nodes = []
        draft = self
        while draft:
            nodes.insert(0, draft)
            draft = draft.parent

        pages = []
        memo = RestartMemo()
        if not nodes:
            return pages, memo

        # Generate Pages
        assert nodes[0].startspage
        for i, node in enumerate(nodes):
            if node.startspage:
                if i > 0:
                    # Flush the last page
                    page = Page(memo.rows, self.geometry, device)
                    page.decorations = memo.decorations
                    pages.append(page)
                memo = RestartMemo()
                memo.geometry = node.geometry
                memo.border = node.border
            memo.rows += node.rows
            memo.decorations += node.decorations
            memo.floats += node.floats
            memo.footnotes += node.footnotes
            memo.y = node.y

        return pages, memo


class RestartMemo:
    """Carries the state needed to resume page building after an interruption.

    Also used as the return value of fix_draft() to describe spillover
    content that did not fit on the last completed page.
    """
    rows        = ()
    decorations = ()
    footnotes   = ()
    floats      = ()
    parent      = None
    y           = None
    counters    = {}   # dict: numbering_style -> list[int] of length n_levels

    # defaults for testing
    geometry    = A4
    border      = 2*cm, 2*cm, 2*cm, 2*cm

    def get_length(self):
        n = 0
        for x, y, row in self.rows:
            n += len(row)
        return n

    def start_draft(self):
        node             = DraftNode()
        node.rows        = self.rows
        node.decorations = self.decorations
        node.floats      = self.floats
        node.footnotes   = self.footnotes
        node.geometry    = self.geometry
        node.border      = self.border
        node.init_xy()
        if self.y is not None:
            node.y = self.y
        return node

    def copy(self):
        r = shallow_copy(self)
        # counters contains mutable lists — deep copy required so that
        # future increments do not corrupt previously saved snapshots.
        r.counters = {k: list(v) for k, v in self.counters.items()}
        return r



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
    from ..tables import TableBox
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
    from ..tables.table_boxes import split_at_height
    row_offset = 0

    while box is not None and box.n_rows > box.header_rows:
        frag, box = split_at_height(box, draft.remaining_height())
        frag.row_offset = row_offset
        draft.add_row(Row([frag], left=draft.border[3], device=device), 1.0, 0)
        row_offset += frag.n_rows
        if box is not None:
            draft = draft.create_newpage()

    return draft


def generate_boxes(texel, i, factory):
    """Generator producing a stream of boxes."""
    for i1, i2, l in iter_paragraphs(texel, i):
        boxes = []
        # Iterating groups in reverse (the usual trick) is prevented
        # by the generator, so we set parstyle directly instead.
        nl = l[-1]
        factory.markerstyle  = getattr(l[0], 'style', EMPTYSTYLE)
        factory.parstyle     = nl.parstyle
        fixed = factory.mk_style({}).get('fixed_indent')
        factory.indent_level = fixed if fixed is not None else nl.indent
        for node in l:
            boxes.extend(factory.create_all(node))
        yield i1, i2, boxes


def generate_pages(texel, i, restartmemo, factory):
    """Generator producing a stream of pages."""
    from ..tables import TableBox
    device = factory.device

    # In this minimal model, state and RestartMemo are the same thing.
    state = restartmemo.copy()

    # Restore per-style counter arrays from the restart memo so that
    # numbered lists continue with the correct numbers after a restart.
    counters = {k: list(v) for k, v in state.counters.items()}

    # Shift the box-generator start position by the amount of row
    # material already present in the restart memo.
    j = i + restartmemo.get_length()

    margin          = state.border  # top right bottom left
    page_width      = state.geometry[0]
    container_left  = margin[3]
    container_right = page_width - margin[1]
    factory.line_width = container_right - container_left

    for i1, i2, boxlist in generate_boxes(texel, j, factory):
        draft = state.start_draft()

        # bad way to get filled parstyle
        r = factory.mk_style({})

        if r['page_break_before'] and not draft.is_empty():
            draft = draft.create_newpage()

        indent            = factory.indent_level
        first_line_indent = r['first_line_indent']
        indent_levels     = r['indent_levels']
        block_indent      = indent_levels[indent]
        alignment         = r['alignment']
        line_spacing      = r['line_spacing']
        space_before      = r['space_before']
        space_after       = r['space_after']

        line_left_rest   = container_left + block_indent
        line_left_first  = line_left_rest + first_line_indent
        line_right       = container_right
        line_width_first = line_right - line_left_first
        line_width_rest  = line_right - line_left_rest

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

                    if first and r['paragraph_type'] == 'list':
                        style = factory.mk_style(factory.markerstyle)
                        style['font_size'] *= style['marker_size'][indent]
                        style['color']      = style['marker_color'][indent]
                        row.set_marker(r['marker'][indent], r['marker_pos'][indent], style)

                    elif first and r['paragraph_type'] == 'numbered':
                        ns = r['numbering_style'][indent]
                        if ns is not None:
                            ckey = r['counter']
                            if ckey not in counters:
                                counters[ckey] = [0] * n_levels
                            sn = r.get('start_number')
                            if sn is not None:
                                counters[ckey][indent] = sn - 1
                            counters[ckey][indent] += 1
                            if ckey == 'section':
                                counters['item'] = [0] * n_levels
                            marker = format_number(counters[ckey], indent, ns)
                            style = factory.mk_style(factory.markerstyle)
                            style['font_size'] *= style['marker_size'][indent]
                            style['color']      = style['marker_color'][indent]
                            row.set_marker(marker, r['marker_pos'][indent], style)

                    if not draft.can_addrow(row, line_spacing, before):
                        draft = draft.create_newpage()

                    text_width = row.width
                    if alignment == 'left':
                        x = line_left
                    elif alignment == 'right':
                        x = line_left + (line_width - text_width)
                    elif alignment == 'center':
                        x = line_left + 0.5 * (line_width - text_width)
                    elif alignment == 'justify':
                        x = line_left
                    else:
                        assert False

                    row.start = (x, 0)
                    row.width = line_width + x
                    y_before  = draft.y
                    draft.add_row(row, line_spacing, before)
                    if r.get('block_color'):
                        pad = r.get('block_padding') or 0
                        draft.decorations += ((
                            container_left - pad, y_before - pad,
                            container_right - container_left + 2 * pad,
                            row.height + row.depth + 2 * pad,
                            r['block_color']),)
                    first  = False
                    before = 0

        if space_after:
            draft.y += space_after
            # XXX adjust depth of last row?

        pages, state = draft.fix_draft(device)
        state.counters = {k: list(v) for k, v in counters.items()}
        if pages:
            pages[0].restartmemo = restartmemo
            restartmemo = state.copy()
        for page in pages:
            yield page

    # Place any remaining spillover material onto a new page
    if state.rows:
        draft = state.start_draft()
        draft = draft.create_newpage()
        pages, _ = draft.fix_draft(device)
        for page in pages:
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
    pages, restartmemo = draft.fix_draft(TESTDEVICE)
    assert len(pages) > 0
    assert len(restartmemo.rows) > 0

    draft = restartmemo.start_draft()
    for i in range(10):
        row = TextBox("New row %i" % i)
        draft.add_row(row, 1.0, 0)

    pages2, restartmemo2 = draft.fix_draft(TESTDEVICE)
    # rows that fit on one page end up in restartmemo, not pages
    assert len(pages2) + len(restartmemo2.rows) > 0


def test_02():
    "generate_pages"

    import einstein
    from ..core.styles import testsheet
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

