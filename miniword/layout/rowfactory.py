# -*- coding: utf-8 -*-

"""
Ein Entwurf für die Datei rowfactory.py 18.09.2026

Grundsätzliches Vorgehen von RowFactory und Zusammenhang mit der
Seitengenerierung:

Rowfactory generiert absatzweise Row-Records nach der Vorlage in
Texel, ab der Position i. Dabei ist i der Anfang eines Absatzes.

Der Pagebreaker arbeitet auch absatzweise. Dabei ist er mit der
Rowfactory synchron: Der Pagebreaker bekommt eine Liste mit
Row-Records und arbeitet sie ab. Erst wenn diese Rows gesetzt sind,
fordert er das nächste Paket mit Records an.

Texel enthalten nicht nur row-Material, sondern können auch
Nebeneffekte haben, beispielsweise die Zähler für die
Abschnittnummerierungen ändern oder zu setzendes Fußnotenmaterial,
Floats in die Puffer speichern. Denkbar ist auch dass,
Seiteneigenschaften (Größe, Ausrichtung, Rand, Nummerierung)
umgestellt wird.

Diese Nebeneffekte werden während des Satzes des Absatzes (genauer: am
Anfang davon) umgesetzt. Diese absatzweise bearbeitung ist einfach,
führt aber natürlich zu einer Unschärfe: die Seite auf der eine
Fußnote erscheint ist unabhängig von der genauen Position des
Fußnotenankers in dem Absatz, relevant ist vielmehr der Absatz.

Der Prozess der Seitengenerierung soll an Seitengrenzen fortgesetzt
werden können. Dazu enthalten Seiten (üblicherweise) ein Restartmemo,
das Informationen zum Neustarten enthält. Die wichtigste Zustandsgröße
ist das Tupel "rows". Aus der Länge des gepufferten (noch nicht
gesetzten)-Row-Material folgt der Index (relativ zum Seitenanfang) von
dem als nächstes Rows generiert werden müssen. Der Rows-Puffer ist
daher im Restartmemo enthalten. Auch die anderen Puffer (Floats,
Fußnoten, ...) werden in dem Memo gespeichert.

Weiter sind Zustandswerte des Typesettingprozesses enthalten,
beispielsweise Abschnitts- und Fußnotenzähler. Es gibt aber nicht nur
Zustandswerte des Typesetters, auch die Factory hat Zustandswerte, die
abgelegt werden. Das ist insbesondere die Zeilenbreite, die Factory
kennen muss um die Boxen in Zeilen zu portionieren.

Es wird daher ein State-Objekt verwendet, in das sowohl Typesetter als
auch RowFactory die Positionsabhängigen-State Variablen einträgt. Da
RowFactory immer absatzweise arbeitet, brauchen wir von ihr nur solche
Werte eintragen die über den Absatz hinaus bestand haben. Werte die
ohnehin für jeden neuen Absatz neu gesetzt werden (beispielsweise
Styles) brauchen nicht abgelegt zu werden, da die Factory immer nur an
Absatzgrenzen neu gestartet wird.

Das Memo gibt immer den Zustand mit dem eine Seite *aufgehört*
hat. Achtung: in früheren Versionen haben wir in dem Memo den
Anfangszustnd vor der Seite gespeichert. Der Endzustand hat aber
Vorteile.
"""

from copy import copy as shallow_copy

from ..textmodel.texeltree import Text, NewLine, Container, \
    Group, length, iter_childs
from ..textmodel.utils import iter_paragraphs
from ..textmodel.textmodel import get_texel
from ..textmodel.submodel import Footnote  # used only by the tests below
from ..core.styles import testsheet, style_default, n_levels
from ..core.units import mm, cm
from .boxes import TextBox, NewlineBox, EndBox, Row, RowsBox
from .page import ForceBreakBox, Page, FootnoteBox
from .testdevice import TESTDEVICE
from .counters import set_counter, inc_counter, format_number, copy_counters
from .linewrap import simple_linewrap
from .stretchable import justify_line


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
        self.rows = []       # row records generated, but not yet placed
        self.footnotes = []  # footnote row records, in document order
        self.floats = []
        self.counters = {}
        self.footnote_counter = 0

    def copy(self):
        clone = shallow_copy(self)
        clone.rows = list(self.rows)
        clone.footnotes = list(self.footnotes)
        clone.floats = list(self.floats)
        clone.counters = copy_counters(self.counters)
        return clone

    
class Factory:
    # A simple factory which creates the basic boxes from their texels
    
    def __init__(self, stylesheet, device):
        self.stylesheet = stylesheet
        self.device = device

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
        p_prev = get_texel(texel, i - 1).parstyle if i > 0 else None
        if p_prev is not None:
            p_prev = self.stylesheet.mk_parstyle(p_prev)
        buffered = None  # (i1, i2, texels, p)

        for i1, i2, texels in iter_paragraphs(texel, i):
            p = self.stylesheet.mk_parstyle(texels[-1].parstyle)
            if buffered is not None:
                b_i1, b_i2, b_texels, b_p = buffered
                yield b_i1, b_i2, b_texels, p_prev, b_p, p
                p_prev = b_p
            buffered = i1, i2, texels, p

        if buffered is not None:
            i1, i2, texels, p = buffered
            yield i1, i2, texels, p_prev, p, None

    def _process_paragraph(self, i1, i2, texels, p_prev, p, p_next):
        boxes = [self.create_box(elem, p) for elem in texels]
        begins_block = not _is_same_block(p, p_prev)
        ends_block = not _is_same_block(p, p_next)
        
        level = p.get('fixed_indent') or 0

        marker = self._update_counters(p)
        left_first, left_rest, width_first, width_rest = \
            self._dims(p, level)
        alignment = p['alignment']
        # A forced line break (BR/ForceBreakBox) always ends its own
        # line, even if more would still fit - each segment after one
        # is wrapped on its own, continuing (never restarting) the
        # paragraph's hanging indent (only the very first segment gets
        # width_first/left_first).
        lines = []
        for segment in split_at_breaks(boxes):
            w_first = width_first if not lines else width_rest
            lines.extend(simple_linewrap(segment, w_first, width_rest))
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
            row.start = (align_x(alignment, left, width, row.width), 0)
            apply_line_spacing(row, p['line_spacing'])
            if is_first and marker is not None:
                row.set_marker(marker, p['marker_pos'][level], p)
            r.append((row, p, is_first, is_last, begins_block, ends_block))
        return r

    # ---- Line dimensions (indentation) ----------------------------------

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
        width_rest = self.state.width - block_indent
        width_first = width_rest - first_line_indent
        return left_first, left_rest, width_first, width_rest

    # ---- Numbering -------------------------------------------------------

    def _update_counters(self, parstyle):
        ptype = parstyle.get('paragraph_type', 'normal')
        if ptype == 'normal':
            return None
        level = parstyle.get('fixed_indent') or 0
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
        return format_number(counter, level, parstyle['numbering_style'][level])

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

        child = self.create_child(self.state.width - indent)
        fn_records = [record for par in child.generate(texel.content, 0)
                      for record in par]
        if fn_records:
            fn_records[0][0].set_marker(label, -(label_w + LABEL_GAP), label_style)
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
        ncols = texel.ncols
        col_width = self.state.width / ncols
        cells = []
        for j1, j2, cell_texel in iter_childs(texel):
            child = self.create_child(col_width)
            records = [record for par in child.generate(cell_texel, 0)
                       for record in par]
            self.update_from_child(child)
            cells.append(records)
        return TableBox(cells, ncols, col_width, self.device, length(texel))

    
BLOCK_KEYS = ('block_color', 'block_padding', 'block_border')


def block_key(parstyle):
    return tuple(parstyle.get(k) for k in BLOCK_KEYS)


def _is_same_block(style_a, style_b):
    if style_a is None or style_b is None:
        return False
    return block_key(style_a) == block_key(style_b)


# ---------------------------------------------------------------------
# Stand-ins (until tables are ported to the new factory)
# ---------------------------------------------------------------------

class Table(Container):
    """Table texel stand-in for the tests: childs are the cell
    contents (row by row, ncols per table row)."""

    def __init__(self, cell_texels, ncols):
        self.ncols = ncols
        self.childs = list(cell_texels)
        self.compute_weights()


class TableBox:
    """Turns each cell's row records into a box (typeset_into_rect) at
    col_width. Width = ncols * col_width, height = sum of per-table-row
    heights (each row's height is the max over its cells)."""

    def __init__(self, cells, ncols, col_width, device, length_):
        self.cells = [typeset_into_rect(records, col_width, device)
                      for records in cells]
        self.ncols = ncols
        self.col_width = col_width
        self.device = device
        self.length = length_
        self.width = ncols * col_width

        nrows = -(-len(self.cells) // ncols)  # ceil division
        row_heights = []
        for r in range(nrows):
            cells_in_row = self.cells[r * ncols:(r + 1) * ncols]
            row_heights.append(max(
                (c.height + c.depth for c in cells_in_row), default=0))
        self.height = sum(row_heights)
        self.depth = 0

    def __len__(self):
        return self.length


def _row_bottom(y, record):
    """Bottom of a record placed at y, incl. its block's closing padding."""
    row, parstyle, begins_par, ends_par, begins_block, ends_block = record
    bottom = y + row.height + row.depth
    if ends_par and ends_block:
        bottom += block_key(parstyle)[1] or 0
    return bottom


class RowStack:
    """Stacks row records top-down (placed: [(y, record), ...]). Used
    for a page's body and footnotes and for table cells. Stacking can
    be continued, e.g. paragraph by paragraph, by calling take again.

    space_before/space_after apply only between paragraphs, never at
    the stack's top. block_padding is reserved at a block's start and
    end and covered by its decoration."""

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
        for record in buffer:
            row, parstyle, begins_par, ends_par, begins_block, ends_block = record
            y = self.height
            if self.placed and begins_par:
                y += self.placed[-1][1][1].get('space_after', 0) \
                    + parstyle.get('space_before', 0)
            if begins_par and begins_block:
                y += block_key(parstyle)[1] or 0
            if max_height is not None and not (force and n == 0) \
                    and _row_bottom(y, record) > max_height:
                break
            self.placed.append((y, record))
            n += 1
        del buffer[:n]

    def data(self):
        return [(0, y, record[0]) for y, record in self.placed]

    def decorations(self):
        """Block shadings/borders. A block cut off at either end of
        the stack is closed off there."""
        shadings, borders = [], []
        top = None
        for k, (y, record) in enumerate(self.placed):
            row, parstyle, begins_par, ends_par, begins_block, ends_block = record
            color, padding, border = block_key(parstyle)
            if top is None:
                opens = begins_par and begins_block
                top = y - (padding or 0) if opens else y
            if (ends_par and ends_block) or k == len(self.placed) - 1:
                rect = (0, top, self.width, _row_bottom(y, record) - top)
                if color is not None:
                    shadings.append(rect + (color,))
                if border is not None:
                    borders.append(rect + (border,))
                top = None
        return shadings, borders

    def create_box(self, device, cls=RowsBox, **kw):
        shadings, borders = self.decorations()
        return cls(data=self.data(), width=self.width, height=self.height,
                   shadings=shadings, borders=borders, device=device, **kw)


def typeset_into_rect(records, width, device):
    """Lay out row records into a fixed-width RowsBox (see RowStack)."""
    stack = RowStack(width)
    stack.take(list(records))
    return stack.create_box(device)


SEPARATOR_GAP = 2 * mm  # space above the footnote box for its separator


def shift(rects, dx, dy):
    return [(x + dx, y + dy, w, h, c) for x, y, w, h, c in rects]


def generate_pages(texel, i1, memo, stylesheet, device):
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
    rows yet."""
    state = memo.copy()
    factory = RowFactory(state, stylesheet, device)
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

        if not body.placed and not notes.placed:
            return  # nothing left: the generator just ends
        footnotebox = None
        if notes.placed:
            box = notes.create_box(device, FootnoteBox,
                                   draw_separator=bool(body.placed))
            y = geometry[1] - bottom - notes.height if body.placed else top
            footnotebox = (left, y, box)
        page = Page([(x, top + y, row) for x, y, row in body.data()],
                    geometry, footnotebox, device=device)
        shadings, borders = body.decorations()
        page.shadings = shift(shadings, left, top)
        page.borders = shift(borders, left, top)
        page.restartmemo = state.copy()
        yield page

        if exhausted and not state.rows and not state.footnotes:
            break


def test_00():
    "Factory"
    from einstein import get_einstein_model    
    factory = Factory(testsheet, TESTDEVICE)
    model = get_einstein_model()
    l = []
    for i1, i2, texels in iter_paragraphs(model.texel, 0):
        p = texels[-1].parstyle
        for texel in texels:            
            l.append(factory.create_box(texel, p))

def test_01():
    "RowFactory"
    from einstein import get_einstein_model
    state = State(width=80)
    factory = RowFactory(state, testsheet, TESTDEVICE)
    model = get_einstein_model()
    for x in factory.generate(model.texel, 0):
        print(x)
    
