# -*- coding: utf-8 -*-

"""
Row and page generation.

RowFactory turns texels into row records, paragraph by paragraph:

    (row, parstyle, begins_par, ends_par, begins_block, ends_block)

begins_block/ends_block tell whether the paragraph starts/ends a block
of paragraphs sharing the same block style (BLOCK_KEYS) and indents;
they depend on the neighbouring paragraphs.

generate_pages() lays these records out on pages, in step with the
factory: it reads one paragraph, places that paragraph's footnotes,
then its rows, and only then reads the next paragraph. A footnote may
thus end up on a page before its text, but never with another
paragraph's text in between.

Side effects of texels (footnotes, counters, later floats or page
settings) are recorded in a State shared by RowFactory and
generate_pages: the buffers rows/footnotes/floats (lists), the list and
footnote counters, the text width. Footnotes, table cells: child
factories (create_child/update_from_child) with a copy of the state;
footnotes and the footnote counter flow back, other counters don't.

Restarting: each page carries a copy of the State as its restartmemo -
the state the page *ended* with. Never work on a memo itself, only on
memo.copy(). A memo holds no absolute index positions, as pages move in
index space when text is inserted or deleted before them; where to
continue is computed from the page's start plus the length of the rows
still buffered in the memo.

RowStack stacks records (spacing, block padding, block decorations) and
splits a table that doesn't fit at a row boundary - the rest stays in
the buffer, and so in the memo. Images are decoded via the
application-wide cache imageio.decode_cached.

Tests: miniword/tests/test_rowfactory.py (list in
develnotes/rowfactory_tests.md), test_tables.py, test_images.py,
test_footnotes.py.
"""

import os
from copy import copy as shallow_copy

from ..textmodel.texeltree import length, NL, grouped
from ..textmodel.utils import iter_paragraphs
from ..textmodel.textmodel import get_texel
from ..core.styles import n_levels
from ..core.units import mm, cm
from ..core.styles import updated
from ..core.papersizes import PAPER_SIZES
from ..core.document import settings_default
from .boxes import TextBox, NewlineBox, EndBox, TabulatorBox, Row, \
    RowsBox
from .page import ForceBreakBox, Page, FootnoteBox
from .testdevice import TESTDEVICE
from .counters import set_counter, inc_counter, format_number, copy_counters
from .linewrap import simple_linewrap
from ..hyphenation import get_hyphenator
from .stretchable import justify_line
from ..tables.table_boxes import TableBox, create_cell, split_at_height, \
    CELL_HPAD, CELL_VPAD


# Needed for testing
A4 = 210 * mm, 297 * mm

FOOTNOTE_FRACTION = 0.10  # max fraction of page height reserved for footnotes
MIN_LABEL_INDENT = 10  # minimum hanging indent for footnote label (pt)
LABEL_GAP = 3          # gap between label and content (pt)


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


def align_x(alignment, left, width, text_width):
    """x-position of a row's left edge for the given paragraph alignment."""
    if alignment in ('left', 'justify'):
        return left
    if alignment == 'right':
        return left + (width - text_width)
    if alignment == 'center':
        return left + 0.5 * (width - text_width)
    assert False



def trailing_space(line):
    """Width of the spaces ending a line (in its last box)."""
    box = line[-1]
    if not isinstance(box, TextBox):
        return 0
    n = len(box.text) - len(box.text.rstrip(' '))
    return box.measure(box.text[-n:])[0] if n else 0


def apply_line_spacing(row, line_spacing):
    """Line spacing as in the previous typesetter: extra leading of
    (height + depth) * (line_spacing - 1), at least -0.5, split evenly
    above and below the row.

    XXX Scales the leading of tall rows too (e.g. a formula with a
    large depth). Must be replaced by a TeX-like fixed baseline
    distance (plus a minimal gap for too tall rows) once there are
    formulas."""
    extra = max((row.height + row.depth) * (line_spacing - 1), -0.5)
    row.height += extra / 2
    row.depth += extra / 2


class State:
    """State shared by RowFactory and generate_pages. A copy of it is
    stored as a page's restartmemo. The buffers are lists (RowStack.take
    takes from their front): never work on a stored memo itself, only
    on memo.copy().

    Holds no absolute index positions - pages can move in index space
    (inserting/deleting before them). Where to continue is computed
    from the page start plus the length of rows (see generate_pages)."""

    # defaults for testing
    geometry = A4
    border = 2 * cm, 2 * cm, 2 * cm, 2 * cm

    def __init__(self, width):
        self.width = width
        # Footnotes are shown in the page's footnote area, so their
        # content is set at the page's text width - also when the anchor
        # sits in a narrower table cell. Children (create_child) keep it.
        self.footnote_width = width
        self.rows = []       # row records generated, but not yet placed
        self.footnotes = []  # footnote row records, in document order
        self.floats = []
        self.counters = {}
        self.footnote_counter = 0
        self.chapter = ''  # the running heads in effect (role h1, h2)
        self.section = ''
        self.settings = settings_default

    def copy(self):
        clone = shallow_copy(self)
        clone.rows = list(self.rows)
        clone.footnotes = list(self.footnotes)
        clone.floats = list(self.floats)
        clone.counters = copy_counters(self.counters)
        return clone


def state_from_settings(settings):
    """Initial State for document settings: paper size, margins and
    the resulting text width."""
    props = updated(settings_default, settings)
    paper = props['paper']
    if paper in PAPER_SIZES:
        w, h = PAPER_SIZES[paper]
    else:
        w, h = props['paper_width'], props['paper_height']
    border = (props['margin_top'], props['margin_right'],
              props['margin_bottom'], props['margin_left'])
    state = State(w - border[1] - border[3])
    state.geometry = (w, h)
    state.border = border
    state.settings = props
    return state

    
class Factory:
    # A simple factory which creates the basic boxes from their texels
    
    base_dir = ''  # folder of the document: relative image paths

    def __init__(self, stylesheet, device=TESTDEVICE):
        self.stylesheet = stylesheet
        self.device = device

    def clear_caches(self):
        self.device.clear_caches()

    def create_box(self, texel, parstyle):
        handler = getattr(self, texel.__class__.__name__ + '_handler')
        return handler(texel, parstyle)
        
    def Text_handler(self, texel, parstyle):
        return TextBox(texel.text,
            self.stylesheet.mk_style(parstyle, texel.style),
            self.device)

    def NewLine_handler(self, texel, parstyle):
        style = self.stylesheet.mk_style(parstyle, texel.style)
        cls = EndBox if texel.is_endmark else NewlineBox
        return cls(style, self.device)

    def BR_handler(self, texel, parstyle):
        # A forced line break (Shift-Enter) within a paragraph - ends
        # its line even if more text would still fit. The box itself
        # is built here; _finish_paragraph (via split_at_breaks) is
        # what actually forces the break when wrapping.
        style = self.stylesheet.mk_style(parstyle, texel.style)
        return ForceBreakBox(style, self.device)

    def Tabulator_handler(self, texel, parstyle):
        style = self.stylesheet.mk_style(parstyle, texel.style)
        return TabulatorBox(style, self.device)

    def Image_handler(self, texel, parstyle):
        # Decoded images come from the application-wide LRU
        # (imageio.decode_cached), linked ones from the cache for
        # external images; else a placeholder, with the file name or URL
        # of a linked image.
        from ..images.images import ImageBox, ErrorPlaceholderBox
        from ..images.imageio import decode_cached, crop_surface, \
            content_of
        data = decode_cached(content_of(texel, self.base_dir))
        if data is None and texel.path:
            name = os.path.basename(texel.path.rstrip('/'))
            return ErrorPlaceholderBox(200, 150, self.device, name)
        if data is None:
            return ErrorPlaceholderBox(50, 50, self.device)
        bitmap = data.bitmap
        w, h = data.width_px, data.height_px
        if texel.crop:
            cl, cr, ct, cb = texel.crop
            w, h = w - cl - cr, h - ct - cb
            bitmap = crop_surface(bitmap, cl, ct, w, h)
        return ImageBox(bitmap, w * texel.scale_x, h * texel.scale_y, data,
                        self.device)

    

class RowFactory(Factory):
    # A factory which generates rows.

    def __init__(self, state, stylesheet, device):
        Factory.__init__(self, stylesheet, device)
        self.state = state

    def generate(self, texel, i):
        for i1, i2, texels, p_prev, p, p_next in \
                self._iter_paragraphs_with_neighbors(texel, i):
            yield self._process_paragraph(i1, i2, texels, p_prev, p, p_next)

    def _iter_paragraphs_with_neighbors(self, texel, i):
        # helper: iterate pragraphs, also yield prev and next parstyle
        p_prev = self.paragraph_style(get_texel(texel, i - 1)) \
            if i > 0 else None
        buffered = None  # (i1, i2, texels, p)

        for i1, i2, texels in iter_paragraphs(texel, i):
            p = self.paragraph_style(texels[-1])
            if buffered is not None:
                b_i1, b_i2, b_texels, b_p = buffered
                yield b_i1, b_i2, b_texels, p_prev, b_p, p
                p_prev = b_p
            buffered = i1, i2, texels, p

        if buffered is not None:
            i1, i2, texels, p = buffered
            yield i1, i2, texels, p_prev, p, None

    def paragraph_style(self, newline):
        """The full parstyle of the paragraph ended by newline, with its
        level: fixed_indent, or else the newline's (free) indent."""
        p = self.stylesheet.mk_parstyle(newline.parstyle)
        fixed = p.get('fixed_indent')
        p['level'] = fixed if fixed is not None \
            else getattr(newline, 'indent', 0)
        return p

    def _process_paragraph(self, i1, i2, texels, p_prev, p, p_next):
        boxes = [self.create_box(elem, p) for elem in texels]
        begins_block = not _is_same_block(p, p_prev)
        ends_block = not _is_same_block(p, p_next)
        
        level = p['level']

        marker = self._update_counters(p)
        left_first, left_rest, width_first, width_rest = \
            self._dims(p, level)
        alignment = p['alignment']
        # A forced line break (BR/ForceBreakBox) always ends its own
        # line, even if more would still fit - each segment after one
        # is wrapped on its own, continuing (never restarting) the
        # paragraph's hanging indent (only the very first segment gets
        # width_first/left_first).
        # A table gets a row of its own (not wrapped), so that
        # RowStack.take can split it across pages.
        hyphenate = self._hyphenate(p)
        lines = []
        for segment in split_at_tables(boxes):
            if isinstance(segment[0], TableBox):
                lines.append(segment)
                continue
            for sub in split_at_breaks(segment):
                w_first = width_first if not lines else width_rest
                lines.extend(simple_linewrap(sub, w_first, width_rest,
                                             hyphenate=hyphenate))
        n = len(lines)

        # Must be set before the first yield: code after a yield only
        # runs on the next next() call.
        #self.restartmemo = (i2, copy_counters(self.counters),
        #                     self.footnote_counter)

        r = []
        for k, line in enumerate(lines):
            is_first, is_last = k == 0, k == n - 1
            width, left = (width_first, left_first) if is_first \
                else (width_rest, left_rest)
            if alignment == 'justify' and not is_last:
                line = justify_line(line, width)
            row = Row(line, device=self.device)
            # spaces ending the line hang over the right edge
            text_width = row.width - trailing_space(line)
            row.start = (align_x(alignment, left, width, text_width), 0)
            apply_line_spacing(row, p['line_spacing'])
            if is_first and marker is not None:
                row.set_marker(marker, p['marker_pos'][level], p)
            r.append((row, p, is_first, is_last, begins_block, ends_block))
        if p.get('role') in ('h1', 'h2'):  # for the running heads
            text = ''.join(getattr(t, 'text', '') for t in texels)
            r[0][0].heading = p['role'], text.strip()
        return r

    def _hyphenate(self, parstyle):
        """The hyphenation function (word -> pieces) for a paragraph:
        None if switched off in the document or the paragraph style, or
        without patterns for the document's language."""
        settings = self.state.settings
        if not settings['hyphenation'] or not parstyle['hyphenate']:
            return None
        hyphenator = get_hyphenator(settings['language'])
        return hyphenator.hyphenate if hyphenator else None

    def _dims(self, parstyle, level):
        """Compute left_first/left_rest/width_first/width_rest:
        list_indent applies only for list/numbered paragraphs, plus
        indent_levels[level] and first_line_indent (can be negative -
        hanging indent)."""
        in_list = parstyle['paragraph_type'] in ('list', 'numbered')
        list_indent = parstyle['list_indent'] if in_list else 0
        block_indent = parstyle['indent_levels'][level] + list_indent
        first_line_indent = parstyle['first_line_indent']
        left_rest = block_indent
        left_first = left_rest + first_line_indent
        width_rest = self.state.width - block_indent \
            - parstyle['right_indent']
        width_first = width_rest - first_line_indent
        return left_first, left_rest, width_first, width_rest

    def _update_counters(self, parstyle):
        ptype = parstyle.get('paragraph_type', 'normal')
        if ptype != 'numbered' and parstyle.get('counter') == 'section':
            # Every section paragraph clears the item counter - also an
            # unnumbered heading, which doesn't count itself.
            self.state.counters['item'] = [0] * n_levels
        if ptype == 'normal':
            return None
        level = parstyle['level']
        if ptype == 'list':
            return parstyle['marker'][level]
        # 'numbered'
        ckey = parstyle.get('counter', 'item')
        counter = self.state.counters.setdefault(ckey, [0] * n_levels)
        sn = parstyle.get('start_number')
        if sn is not None:
            set_counter(level, counter, sn)
        else:
            inc_counter(level, counter)
        if ckey == 'section':
            self.state.counters['item'] = [0] * n_levels
        style = parstyle['numbering_style'][level]
        return format_number(counter, level, style)

    def create_child(self, width):
        """Child factory for a sub-layout (e.g. a table cell or a
        footnote's content), width wide. Shares stylesheet/device via
        shallow_copy, but works on its own copy of the state - starting
        with empty footnote/float buffers, so that afterwards these
        hold exactly what the child added (see update_from_child)."""
        child = shallow_copy(self)
        child.state = self.state.copy()
        child.state.width = width
        child.state.footnotes = []
        child.state.floats = []
        return child

    def update_from_child(self, child):
        """Take over what isn't local to the child: its footnotes and
        floats (appended, so they stay in document order) and the
        footnote counter. Its counters and width stay local."""
        self.state.footnotes += child.state.footnotes
        self.state.floats += child.state.floats
        self.state.footnote_counter = child.state.footnote_counter

    def Footnote_handler(self, texel, parstyle):
        from ..footnotes.footnotes import FootnoteAnchorBox, format_fn_label
        self.state.footnote_counter += 1
        label = texel.label or format_fn_label(self.state.footnote_counter,
                                               texel.numbering)

        # Reserve a hanging indent for the label, wide enough to fit it
        # (MIN_LABEL_INDENT at least): render the content narrower by
        # that much, then hang the label off the first row's left edge
        # and pull continuation rows back to just MIN_LABEL_INDENT (a
        # wide label only pushes its own first row's text, not every
        # line of the footnote).
        outer_style = self.stylesheet.mk_style(parstyle, {})
        label_style = {**outer_style, 'vertical_position': 'superscript'}
        label_w = self.device.measure(label, label_style)[0]
        indent = max(MIN_LABEL_INDENT, label_w + LABEL_GAP)

        child = self.create_child(self.state.footnote_width - indent)
        fn_records = [record for par in child.generate(texel.content, 0)
                      for record in par]
        if fn_records:
            fn_records[0][0].set_marker(label, -(label_w + LABEL_GAP),
                                        label_style)
            extra = indent - MIN_LABEL_INDENT
            if extra:
                for later_record in fn_records[1:]:
                    row = later_record[0]
                    row.start = (row.start[0] - extra, row.start[1])
                    row.width -= extra

        # Append this footnote's own records before the child's
        # footnotes (any footnotes nested inside it) - document order
        # requires the parent to precede its own nested footnotes.
        self.state.footnotes += fn_records
        self.update_from_child(child)
        style = self.stylesheet.mk_style(parstyle, texel.style)
        return FootnoteAnchorBox(texel, label, style, self.device)

    def Table_handler(self, texel, parstyle):
        """A TableBox for a Table texel: childs are [SEP, content, SEP,
        content, ..., SEP], the separator after a cell carries its style
        (borders, background, alignment) in its parstyle. Each cell is set
        by a child factory, so the footnote counter and footnotes flow on
        through the cells."""
        ncols, nrows = texel.ncols, texel.nrows
        col_widths = table_col_widths(texel.col_widths, ncols,
                                      self.state.width)
        cell_texels = texel.childs[1::2]
        seps = texel.childs[2::2]
        grid = []
        for r in range(nrows):
            row = []
            for c in range(ncols):
                k = r * ncols + c
                sep = seps[k]
                # The separator ends the cell's last paragraph.
                nl = NL.set_parstyle(sep.parstyle)
                nl = nl.set_indent(getattr(sep, 'indent', 0))
                content = grouped([cell_texels[k], nl])
                child = self.create_child(col_widths[c] - CELL_HPAD)
                records = [record for par in child.generate(content, 0)
                           for record in par]
                self.update_from_child(child)
                cell = create_cell(records, col_widths[c], self.device,
                                   CELL_HPAD, CELL_VPAD, sep.parstyle or {})
                # the separator slot belongs to the table structure
                cell.length = length(cell_texels[k]) + 1
                row.append(cell)
            grid.append(row)
        row_heights = [max(cell.height + cell.depth for cell in row)
                       for row in grid]
        return TableBox(grid, col_widths, row_heights,
                        header_rows=texel.nheader,
                        break_level=texel.breaklevel, device=self.device)

    
BLOCK_KEYS = ('block_color', 'block_offset', 'block_border_width',
              'block_border_color', 'block_border_sides', 'right_indent')


def block_key(parstyle):
    """Consecutive paragraphs with equal keys form one block: equal
    block style and indents."""
    return tuple(parstyle.get(k) for k in BLOCK_KEYS) \
        + (block_left(parstyle),)


def block_left(parstyle):
    """Left text edge of a paragraph's block: its indent, including a
    hanging first line; list markers lie inside (no list_indent)."""
    levels = parstyle.get('indent_levels')
    left = levels[parstyle.get('level', 0)] if levels else 0
    return left + min(0, parstyle.get('first_line_indent', 0))


def block_space(parstyle):
    """Space reserved above and below a block: offset plus line width."""
    return (parstyle.get('block_offset') or 0) \
        + (parstyle.get('block_border_width') or 0)


def _is_same_block(style_a, style_b):
    if style_a is None or style_b is None:
        return False
    return block_key(style_a) == block_key(style_b)


def table_col_widths(col_widths, ncols, width):
    """Column widths: explicit ones as given, the rest (None) share what
    is left of width; without col_widths all columns are equal."""
    if col_widths:
        explicit = [w for w in col_widths if w is not None]
        n_auto = sum(1 for w in col_widths if w is None)
        auto_w = (width - sum(explicit)) / n_auto if n_auto else 0
        return [w if w is not None else auto_w for w in col_widths]
    return [width / ncols] * ncols


def split_at_tables(boxes):
    """Split boxes at tables: each TableBox becomes a segment of its own."""
    segments, current = [], []
    for box in boxes:
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


def split_table_record(record, height):
    """Split a record whose row is a table (break_level >= 1) so that
    the first part fits into height. Returns (first, rest) records or
    None if the row is no splittable table or can't be split. The first
    part keeps begins_par, the rest ends_par; both keep the row's extra
    leading."""
    row, parstyle, begins_par, ends_par, begins_block, ends_block = record
    box = row.childs[0]
    if len(row.childs) != 1 or not isinstance(box, TableBox) \
            or box.break_level < 1:
        return None
    top, bottom = row.height - box.height, row.depth - box.depth
    frag, rest = split_at_height(box, height - top - bottom)
    if rest is None:
        return None
    frag.row_offset = box.row_offset
    rest.row_offset = box.row_offset + frag.n_rows

    def table_row(part, marker):
        new = shallow_copy(row)
        new.childs = [part]
        new.length, new.width = len(part), part.width
        new.height, new.depth = part.height + top, part.depth + bottom
        new.marker = marker
        return new

    return ((table_row(frag, row.marker), parstyle, begins_par, False,
             begins_block, ends_block),
            (table_row(rest, None), parstyle, False, ends_par,
             begins_block, ends_block))


def _row_bottom(y, record):
    """Bottom of a record placed at y, incl. its block's closing padding."""
    row, parstyle, begins_par, ends_par, begins_block, ends_block = record
    bottom = y + row.height + row.depth
    if ends_par and ends_block:
        bottom += block_space(parstyle)
    return bottom


class RowStack:
    """Stacks row records top-down (placed: [(y, record), ...]). Used
    for a page's body and footnotes and for table cells. Stacking can
    be continued, e.g. paragraph by paragraph, by calling take again.

    space_before/space_after apply only between paragraphs, never at
    the stack's top. block_space is reserved at a block's start and
    end and covered by its decoration, which also grows sideways by the
    same amount (into the page margin)."""

    def __init__(self, width):
        self.width = width
        self.placed = []

    @property
    def height(self):
        return _row_bottom(*self.placed[-1]) if self.placed else 0

    def take(self, buffer, max_height=None, force=None):
        """Move as many records from the front of buffer as fit into
        max_height. With force (default: the stack is empty) the first
        one is taken even if it doesn't fit."""
        if force is None:
            force = not self.placed
        n = 0
        while n < len(buffer):
            record = buffer[n]
            (row, parstyle, begins_par, ends_par,
             begins_block, ends_block) = record
            y = self.height
            if self.placed and begins_par:
                y += self.placed[-1][1][1].get('space_after', 0) \
                    + parstyle.get('space_before', 0)
            if begins_par and begins_block:
                y += block_space(parstyle)
            forced = force and n == 0
            if max_height is not None \
                    and _row_bottom(y, record) > max_height:
                # A table that doesn't fit is split at a row boundary:
                # the first part goes here, the rest stays in buffer.
                parts = split_table_record(record, max_height - y)
                if parts is not None:
                    first, rest = parts
                    if forced or _row_bottom(y, first) <= max_height:
                        self.placed.append((y, first))
                        buffer[n] = rest
                        break
                if not forced:
                    break
            self.placed.append((y, record))
            n += 1
        del buffer[:n]

    def data(self):
        return [(0, y, record[0]) for y, record in self.placed]

    def decorations(self):
        """Block shadings (x, y, w, h, color) and border lines (x, y, w,
        h, (color, width, sides)), the rect being the line's outer edge.
        A block cut off at either end of the stack is closed off there."""
        shadings, borders = [], []
        top = None
        for k, (y, record) in enumerate(self.placed):
            (row, parstyle, begins_par, ends_par,
             begins_block, ends_block) = record
            if top is None:
                opens = begins_par and begins_block
                top = y - block_space(parstyle) if opens else y
            if not ((ends_par and ends_block) or k == len(self.placed) - 1):
                continue
            bottom = _row_bottom(y, record)
            space = block_space(parstyle)
            x1 = block_left(parstyle) - space
            x2 = self.width - (parstyle.get('right_indent') or 0) + space
            line = parstyle.get('block_border_width') or 0
            color = parstyle.get('block_color')
            if color is not None:
                shadings.append((x1 + line, top + line, x2 - x1 - 2 * line,
                                 bottom - top - 2 * line, color))
            if line:
                style = (parstyle.get('block_border_color', 'black'), line,
                         parstyle.get('block_border_sides', 'tblr'))
                borders.append((x1, top, x2 - x1, bottom - top, style))
            top = None
        return shadings, borders

    def create_box(self, device, cls=RowsBox, **kw):
        shadings, borders = self.decorations()
        return cls(data=self.data(), width=self.width, height=self.height,
                   shadings=shadings, borders=borders, device=device, **kw)


def typeset_into_rect(records, width, device):
    """Lay out row records into a fixed-width RowsBox (see RowStack).
    Block decorations are cut at the sides to stay inside the rect."""
    stack = RowStack(width)
    stack.take(list(records))
    box = stack.create_box(device)
    box.shadings = clip_x(box.shadings, width)
    box.borders = clip_x(box.borders, width)
    return box


def clip_x(rects, width):
    return [(max(x, 0), y, min(x + w, width) - max(x, 0), h, c)
            for x, y, w, h, c in rects]


SEPARATOR_GAP = 2 * mm  # space above the footnote box for its separator


def shift(rects, dx, dy):
    return [(x + dx, y + dy, w, h, c) for x, y, w, h, c in rects]


def adjust_page_break(placed, buffer):
    """Avoid orphans and widows: at a page break inside a paragraph
    (placed: the page's (y, record) list, buffer: the records that
    follow), keep at least 2 lines of the paragraph on each side, as far
    as its widow_orphan_control allows, by moving records from the
    end of placed back to the front of buffer. Never empties the page;
    tables are left alone."""
    if not placed or not buffer or buffer[0][2]:  # no break inside
        return
    style = buffer[0][1]
    k = 0  # the paragraph's lines on this page
    while k < len(placed):
        k += 1
        if placed[-k][1][2]:  # begins_par
            break
    r = 0  # its lines on the next page
    while True:
        r += 1
        if buffer[r - 1][3]:  # ends_par
            break
    records = [rec for _, rec in placed[-k:]] + buffer[:r]
    if not style.get('widow_orphan_control', True) or \
            any(isinstance(rec[0].childs[0], TableBox) for rec in records):
        return
    move = max(0, 2 - r)  # widow: take a line along
    if 0 < k - move < 2:  # orphan: the whole paragraph moves
        move = k
    if 0 < move < len(placed):
        buffer[:0] = [rec for _, rec in placed[-move:]]
        del placed[-move:]


def page_style(stylesheet, role):
    """The style for headers or footers: the basestyle with this role
    ('header'/'footer'), else normal."""
    base = next((key for key, style in stylesheet.items()
                 if style.get('role') == role), 'normal')
    return stylesheet.mk_parstyle({'base': base})


def keep_with_next(placed, buffer):
    """At a page break between paragraphs: move the paragraphs with
    keep_with_next at the end of placed (the page) to the front of buffer
    (the next page), e.g. headings. Never empties the page."""
    if not placed or not buffer or not buffer[0][2]:  # break inside
        return
    k = len(placed)
    while k > 0 and placed[k - 1][1][1].get('keep_with_next'):
        k -= 1
        while k > 0 and not placed[k][1][2]:  # to the paragraph's start
            k -= 1
    if 0 < k < len(placed):
        buffer[:0] = [record for _, record in placed[k:]]
        del placed[k:]


def running_heads(placed, state):
    """(chapter, section) of a page with the rows placed: the first
    heading with role h1/h2 on it, else the one in effect before; a new
    h1 clears the section. Updates state to the headings in effect at
    the page's end."""
    old_chapter, old_section = state.chapter, state.section
    chapter = section = None
    for y, record in placed:
        role, text = getattr(record[0], 'heading', (None, None))
        if role == 'h1':
            if chapter is None:
                chapter = text
            state.chapter, state.section = text, ''
        elif role == 'h2':
            if section is None:
                section = text
            state.section = text
    if section is None:
        section = old_section if chapter is None else ''
    return (old_chapter if chapter is None else chapter), section


def generate_pages(texel, i1, memo, stylesheet, device, base_dir=''):
    """Yield pages for texel, the first one starting at index i1 and
    continuing from memo (the state the previous page ended with).
    Works on memo.copy(), never on memo itself. Each page carries its
    own end state as page.restartmemo. Only pages with content are
    yielded: restarting from the last page's memo yields none.

    Works paragraph by paragraph: a paragraph is only read once the
    previous one is placed, then its footnotes are placed, then its
    rows. A footnote may thus end up before its text, but never with
    another paragraph's text in between. A paragraph with
    page_break_before starts a new page, unless the page has no body
    rows yet. base_dir: the document's folder (linked images)."""
    state = memo.copy()
    factory = RowFactory(state, stylesheet, device)
    factory.base_dir = base_dir
    # memo holds no absolute positions: the factory continues right
    # after the rows still buffered from the previous page.
    source = factory.generate(texel, i1 + sum(len(r[0]) for r in state.rows))
    geometry = state.geometry
    top, right, bottom, left = state.border
    avail = geometry[1] - top - bottom
    exhausted = False

    while True:
        body, notes = RowStack(state.width), RowStack(state.width)
        while True:
            if not state.rows and not exhausted:
                par = next(source, None)
                if par is None:
                    exhausted = True
                else:
                    state.rows.extend(par)
            if body.placed and state.rows and state.rows[0][2] \
                    and state.rows[0][1].get('page_break_before'):
                break  # the paragraph (and its footnotes) start a new page
            last = exhausted and not state.rows
            # Footnotes: at most FOOTNOTE_FRACTION of the page (all of
            # it once no body rows are left), never over the body.
            limit = avail if last else avail * FOOTNOTE_FRACTION
            if body.placed:
                limit = min(limit, avail - body.height - SEPARATOR_GAP)
            notes.take(state.footnotes, limit, force=not body.placed
                       and not notes.placed)
            gap = SEPARATOR_GAP if notes.placed else 0
            body.take(state.rows, avail - notes.height - gap)
            if state.rows or last:
                break

        if state.rows:  # the page is full: avoid orphans and widows
            adjust_page_break(body.placed, state.rows)
            keep_with_next(body.placed, state.rows)
        if not body.placed and not notes.placed:
            return  # nothing left: the generator just ends
        footnotebox = None
        if notes.placed:
            box = notes.create_box(device, FootnoteBox,
                                   draw_separator=bool(body.placed))
            y = geometry[1] - bottom - notes.height if body.placed else top
            footnotebox = (left, y, box)
        page = Page([(left + x, top + y, row) for x, y, row in body.data()],
                    geometry, footnotebox, device=device)
        shadings, borders = body.decorations()
        page.shadings = shift(shadings, left, top)
        page.borders = shift(borders, left, top)
        page.margin = state.border
        page.settings = state.settings
        page.header_style = page_style(stylesheet, 'header')
        page.footer_style = page_style(stylesheet, 'footer')
        page.chapter, page.section = running_heads(body.placed, state)
        page.restartmemo = state.copy()
        yield page

        if exhausted and not state.rows and not state.footnotes:
            break
