# -*- coding:utf-8-*-

# pagegen.py provides:
# - def generate_pages(texel, i, restartmemo)
# - class RestartMemo  (creates an empty RestartMemo; page geometry
#   parameters are accepted)
#
# The interface is deliberately minimal so that alternative algorithms
# can be swapped in through the same API. Each implementation decides
# how paragraphs are broken, how pages are composed, and how figures
# and footnotes are placed. Switching from a Word-style layout to a
# TeX-style layout would require replacing only this one small file.


from .wxtextview.boxes import Box, VBox, TextBox, select_i_by_x, \
    select_i_by_y
from .wxtextview.testdevice import TESTDEVICE
from .wxtextview.builder import BuilderBase
from .wxtextview.boxes import get_text
from .textmodel.texeltree import length, NewLine
from .wxtextview.linewrap import simple_linewrap
from .styles import mm, cm, pt, updated, n_levels
from .factory import Factory, ForceBreakBox
from .stretchable import justify_line

import wx
from copy import copy as shallow_copy


class Row(Box):
    """Box representing a single typeset line.

    Extends boxes.Row with optional padding (top, bottom, left, right)
    and an optional bullet marker (decoration).
    """
    marker = None
    offset = 0

    def __init__(self, childs, left=0, right=0, top=0, bottom=0,
                 device=TESTDEVICE):
        if device is not None:
            self.device = device
        self.start  = left, top
        self.childs = childs
        assert childs
        self.length = sum(len(child) for child in childs)
        self.width  = sum(child.width for child in childs) + left + right
        self.height = max(child.height for child in childs) + top
        self.depth  = max(child.depth  for child in childs) + bottom

    def __len__(self):
        return self.length

    def iter_boxes(self, i, x, y):
        left, top = self.start
        height = self.height
        y += top
        x += left
        j1 = i
        for child in self.childs:
            j2 = j1 + len(child)
            yield j1, j2, x, y + height - child.height, child
            x  += child.width
            j1  = j2

    def set_marker(self, marker, offset, style):
        self.marker = marker
        self.offset = offset
        self.style  = style

    def draw(self, x, y, gc):
        Box.draw(self, x, y, gc)
        if not self.marker:
            return
        device = self.device
        self.device.set_style(self.style, gc)
        left, top = self.start

        # When scaling we adjust y so the marker baseline matches the
        # row baseline. This looks fine for moderate scale factors
        # (< 1.3). For larger factors it may be better to keep the
        # glyph centre point constant instead.
        markerheight = self.device.measure(self.marker, self.style)[1]
        dy = self.height - markerheight
        device.draw_text(self.marker, x + self.offset + left, y + top + dy, gc)

    def get_index(self, x, y):
        items = self.iter_boxes(0, 0, 0)
        return select_i_by_x(x, y, items)


class Page(Box):
    pagenum    = 0
    margin     = (2 * cm,) * 4  # XXX
    page       = 0
    height     = 0
    restartmemo = None

    def __init__(self, rowdata, geometry, device=TESTDEVICE):
        if device is not None:
            self.device = device
        self.rows = rowdata[:]
        n = 0
        for x, y, row in rowdata:
            n += len(row)
        self.length = n
        self.width, self.height = geometry

    def __len__(self):
        return self.length

    def adjust(self, pagenum):
        """Update page properties that do not affect layout.

        Currently used only for the page number. Could also be used
        for section numbering and list numbering (as long as layout is
        unaffected).
        """
        self.pagenum = pagenum

    def draw_background(self, x, y, gc):
        """Fill the page with its background color."""
        self.device.fill_rect(x, y, self.width, self.height, 'white', gc)

    def draw(self, x, y, gc):
        Box.draw(self, x, y, gc)
        self.device.draw_rect(x, y, self.width, self.height, gc)
        margin = self.margin
        self.device.set_style({}, gc)  # XXX
        self.device.draw_text(
            "Page %i" % self.pagenum,
            x + margin[3], y + self.height - margin[2], gc)

    def iter_boxes(self, i, x, y):
        j1 = i
        for x_, y_, row in self.rows:
            j2 = j1 + len(row)
            yield j1, j2, x + x_, y + y_, row
            j1 = j2

    def get_index(self, x, y):
        items = self.iter_boxes(0, 0, 0)
        return select_i_by_y(x, y, items)
    

def show_page(page):
    """Dump the contents of a page."""
    memo = page.restartmemo
    if memo:
        print("RestartMemo present")
        for x, y, row in memo.rows:
            print("--", x, y, get_text(row))

    for i1, i2, x, y, row in page.iter_boxes(0, 0, 0):
        print(x, y, repr(get_text(row)))
    print()


A4 = 210 * mm, 297 * mm


class DraftNode:
    """
    Stack rows vertically (y grows downward).

    Adjusts row.height and row.depth so that:
    - rows are tightly stacked (no gaps, no overlap)
    - line_spacing factor is respected
    - hit-testing and selection work on box geometry
    """

    rows      = ()
    footnotes = ()
    floats    = ()
    parent    = None
    startspage = True
    geometry   = A4
    border     = 2 * cm, 2 * cm, 2 * cm, 2 * cm
    x = y = None

    def init_xy(self):
        self.x = self.border[-1]  # ignored in the minimal model
        self.y = self.border[0]

    def is_empty(self):
        return (len(self.rows) == 0
                and len(self.footnotes) == 0
                and len(self.floats) == 0)

    def place_row(self, row, x, y):
        self.rows += (x, y, row)

    def can_addrow(self, row, line_spacing, before):
        if not self.rows:
            return True  # always accept first row even if oversized
        border_top, border_right, border_bottom, border_left = self.border
        natural = row.height + row.depth
        advance = natural * line_spacing
        max_y = self.geometry[1] - border_top - border_bottom
        return self.y + before + advance <= max_y

    def add_row(self, row, line_spacing, before):
        border_top, border_right, border_bottom, border_left = self.border

        # Natural box height
        natural = row.height + row.depth

        # Desired baseline advance
        advance = natural * line_spacing

        # Extra leading
        extra = advance - natural
        if extra < 0:
            extra = 0  # defensive

        # Distribute symmetrically
        extra_top    = extra * 0.5
        extra_bottom = extra * 0.5

        if self.rows:
            extra_top += before

        # Adjust box parameters (critical!)
        row.height += extra_top
        row.depth  += extra_bottom

        # Position row
        self.rows += ((0, self.y, row),)

        # Advance y for next row
        self.y += row.height + row.depth

    def create_child(self):
        r = shallow_copy(self)
        r.parent = self
        return r

    def create_newpage(self):
        draft = self.create_child()
        draft.startspage = True
        draft.init_xy()
        draft.rows      = ()
        draft.floats    = ()
        draft.footnotes = ()
        return draft

    def fix_draft(self):
        """Finalise a draft.

        Returns the completed pages and a RestartMemo describing any
        spillover that did not fit on the last page.
        """
        nodes = []
        draft = self
        while draft:
            nodes.insert(0, draft)
            draft = draft.parent

        pages = []
        info  = RestartMemo()
        if not nodes:
            return pages, info
        assert nodes[0].startspage
        for i, node in enumerate(nodes):
            if node.startspage:
                if i > 0:
                    # XXX where to get device from?
                    page = Page(rows, self.geometry, rows[0][-1].device)
                    pages.append(page)
                rows      = ()
                floats    = ()
                footnotes = ()
                geometry  = node.geometry
                border    = node.border
            rows      += node.rows
            floats    += node.floats
            footnotes += node.footnotes
            x = node.x
            y = node.y

        # Page is not yet complete — convert to a RestartMemo.
        info           = RestartMemo()
        info.geometry  = geometry
        info.border    = border
        info.rows      = rows
        info.floats    = floats
        info.footnotes = footnotes
        info.x         = x
        info.y         = y
        return pages, info


class RestartMemo:
    """Carries the state needed to resume page building after an interruption.

    Also used as the return value of fix_draft() to describe spillover
    content that did not fit on the last completed page.
    """
    rows      = ()
    footnotes = ()
    floats    = ()
    parent    = None
    geometry  = 210 * mm, 297 * mm  # A4
    border    = 2 * cm, 2 * cm, 2 * cm, 2 * cm
    y         = None
    counters  = {}   # dict: numbering_style -> list[int] of length n_levels

    def get_length(self):
        n = 0
        for x, y, row in self.rows:
            n += len(row)
        return n

    def start_draft(self):
        node           = DraftNode()
        node.rows      = self.rows
        node.floats    = self.floats
        node.footnotes = self.footnotes
        node.geometry  = self.geometry
        node.border    = self.border
        node.init_xy()
        # x is not needed in the minimal model
        if self.y is not None:
            node.y = self.y
        return node

    def copy(self):
        r = shallow_copy(self)
        # counters contains mutable lists — deep copy required so that
        # future increments do not corrupt previously saved snapshots.
        r.counters = {k: list(v) for k, v in self.counters.items()}
        return r


PAPER_SIZES = {
    'A4':     (210 * mm, 297 * mm),
    'Letter': (215.9 * mm, 279.4 * mm),
}


def restartmemo_from_settings(settings):
    """Convert a document settings dict to a RestartMemo with geometry/border."""
    from .document import settings_default
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


# Could be moved to texeltree
def iter_leafes(texel, i):
    """Iterate through all leaf elements starting at position i.

    Note: i must be a valid start position.
    """
    l  = [[texel]]
    i1 = 0
    while 1:
        while l and not l[-1]:
            l.pop()
        if not l:
            break
        ll   = l[-1]
        elem = ll[0]
        del ll[0]
        n = length(elem)
        if i1 + n <= i:
            i1 = i1 + n
        elif elem.is_group:  # do not descend into containers
            l.append(list(elem.childs))
        else:
            i2 = i1 + n
            yield i1, i2, elem
            i1 = i2


# Could also be moved to texeltree
def iter_paragraphs(texel, i):
    l  = []
    i1 = 0
    for j1, j2, elem in iter_leafes(texel, i):
        l.append(elem)
        if isinstance(elem, NewLine):
            yield i1, j2, l
            l  = []
            i1 = j2
    try:
        assert len(l) == 0
    except:
        from .textmodel.texeltree import dump
        dump(texel)
        raise

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


import re as _re


def _to_roman(n):
    """Convert positive integer to lowercase Roman numeral string."""
    val  = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syms = ['m', 'cm', 'd', 'cd', 'c', 'xc', 'l', 'xl', 'x', 'ix', 'v', 'iv', 'i']
    result = ''
    for v, s in zip(val, syms):
        while n >= v:
            result += s
            n -= v
    return result or 'i'


def format_number(arr, level, style):
    """Format a numbered-list marker from a counter array.

    Each occurrence of ``1``, ``a``, ``A``, ``i``, or ``I`` in *style* is
    replaced by the counter at the corresponding nesting depth (left to right,
    starting at depth 0).  Everything else is literal text.

    Examples::

        format_number([3, 0, ...], 0, "1.")   → "3."
        format_number([2, 4, ...], 1, "1.1.") → "2.4."
        format_number([5, 0, ...], 0, "a.")   → "e."
        format_number([3, 0, ...], 0, "i.")   → "iii."
    """
    parts    = _re.split(r'([1aAiI])', style)
    n_tokens = (len(parts) - 1) // 2
    result   = parts[0]
    # Single-token styles ("1.", "a.", …) display the counter at the
    # current indent level.  Composite styles ("1.1.") start at level 0
    # so the full hierarchy is shown.
    lev = level if n_tokens == 1 else 0
    for k in range(1, len(parts), 2):
        typ = parts[k]
        n   = arr[lev] if lev < len(arr) else 0
        lev += 1
        if typ == '1':
            result += str(n)
        elif typ == 'a':
            result += chr(ord('a') + (n - 1) % 26) if n > 0 else 'a'
        elif typ == 'A':
            result += chr(ord('A') + (n - 1) % 26) if n > 0 else 'A'
        elif typ == 'i':
            result += _to_roman(n) if n > 0 else 'i'
        else:  # 'I'
            result += _to_roman(n).upper() if n > 0 else 'I'
        if k + 1 < len(parts):
            result += parts[k + 1]
    return result


def generate_boxes(texel, i, factory):
    for i1, i2, l in iter_paragraphs(texel, i):
        boxes = []
        # Iterating groups in reverse (the usual trick) is prevented
        # by the generator, so we set parstyle directly instead.
        nl = l[-1]
        factory.markerstyle  = l[0].style
        factory.parstyle     = nl.parstyle
        factory.indent_level = nl.indent  # XXX does not work for NLs
                                          # inside containers, but is
                                          # not needed there either.
        for node in l:
            boxes.extend(factory.create_all(node))
        yield i1, i2, boxes


def generate_pages(texel, i, restartmemo, factory):
    device = factory.device

    # In this minimal model, state and RestartMemo are the same thing.
    state = restartmemo.copy()

    # Restore per-style counter arrays from the restart memo so that
    # numbered lists continue with the correct numbers after a restart.
    counters = {k: list(v) for k, v in state.counters.items()}

    # Shift the box-generator start position by the amount of row
    # material already present in the restart memo.
    j = i + restartmemo.get_length()

    # XXX insets are really container properties and should be moved.
    inset_left  = 0
    inset_right = 0

    margin          = state.border  # top right bottom left
    page_width      = state.geometry[0]
    page_left       = margin[3]
    page_right      = page_width - margin[1]
    container_left  = page_left  + inset_left
    container_right = page_right + inset_right

    for i1, i2, boxlist in generate_boxes(texel, j, factory):
        draft = state.start_draft()

        # XXX bad way to get filled parstyle
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

        segments = split_at_breaks(boxlist)
        lines = []
        for seg in segments:
            w = line_width_first if not lines else line_width_rest
            lines.extend(simple_linewrap(seg, w, line_width_rest))
        line_width = line_width_first
        line_left  = line_left_first
        first      = True
        before     = space_before
        n          = len(lines)

        for idx, line in enumerate(lines):
            if alignment == 'justify' and idx < n - 1:
                line = justify_line(line, line_width)
            row = Row(line, device=device)

            if first and r['paragraph_type'] == 'list':
                style = factory.mk_style(factory.markerstyle)
                style['font_size'] *= style['marker_size'][indent]
                style['color']      = style['marker_color'][indent]
                row.set_marker(
                    r['marker'][indent],
                    r['marker_pos'][indent],
                    style,
                )

            elif first and r['paragraph_type'] == 'numbered':
                ns = r['numbering_style'][indent]
                if ns is not None:
                    if ns not in counters:
                        counters[ns] = [0] * n_levels
                    sn = r.get('start_number')
                    if sn is not None:
                        counters[ns][indent] = sn - 1
                    counters[ns][indent] += 1
                    marker = format_number(counters[ns], indent, ns)
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

            row.start  = (x, 0)
            row.width  = line_width + x
            draft.add_row(row, line_spacing, before)
            line_width = line_width_rest
            line_left  = line_left_rest
            first      = False
            before     = 0

        if space_after:
            draft.y += space_after
            # XXX adjust depth of last row?

        pages, state = draft.fix_draft()
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
        pages, _ = draft.fix_draft()
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
    pages, restartmemo = draft.fix_draft()
    assert len(pages) > 0
    assert len(restartmemo.rows) > 0

    draft = restartmemo.start_draft()
    for i in range(10):
        row = TextBox("New row %i" % i)
        draft.add_row(row, 1.0, 0)

    pages2, restartmemo2 = draft.fix_draft()
    # rows that fit on one page end up in restartmemo, not pages
    assert len(pages2) + len(restartmemo2.rows) > 0


def test_02():
    """Page generation driven by a texel with a given geometry."""

    import einstein
    from .styles import testsheet
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

