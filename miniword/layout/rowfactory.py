# -*- coding: utf-8 -*-

"""
RowFactory turns a texel into row records, paragraph by paragraph.

generate_rows drives _iter_paragraphs_with_neighbors (built on
textmodel.utils.iter_paragraphs). For each paragraph, the leaf texels
are dispatched to box-building handlers (Text_handler, Footnote_handler,
Table_handler); _finish_paragraph wraps the boxes into lines and yields
row records: (row, parstyle, begins_par, ends_par, begins_block,
ends_block).

Footnote_handler collects footnote content in fn_sink; only the anchor
appears inline. Table_handler builds a child factory per cell
(create_child), lets it generate rows on its own, and merges
footnote_counter/fn_sink back into the parent (update_from_child).

_iter_paragraphs_with_neighbors also yields the parstyle of the
previous/next paragraph; _process_paragraph derives begins_block/
ends_block from it (block_key/BLOCK_KEYS), which typesetter.
typeset_into_rect uses to group block shadings/borders. Table_handler
only collects each cell's row records; turning them into cell boxes
is up to the TableBox it hands them to.

Texel types handled: Text, NewLine, Footnote, Table. Line wrapping via
simple_linewrap, alignment via align_x/justify_line, indentation via
_dims.
"""

from copy import copy as shallow_copy

from ..textmodel.texeltree import Text, NewLine, Container, \
    Group, length, iter_childs
from ..textmodel.utils import iter_paragraphs
from ..textmodel.textmodel import get_texel
from ..textmodel.submodel import Footnote  # used only by the tests below
from ..core.styles import testsheet, style_default, updated, n_levels
from .boxes import TextBox, NewlineBox, EndBox, Row
from .testdevice import TESTDEVICE
from .counters import set_counter, inc_counter, format_number, copy_counters
from .linewrap import simple_linewrap
from .stretchable import justify_line
from .pagegen import align_x


def mk_style(stylesheet, parstyle, style):
    basestyle = stylesheet.get(parstyle.get('base', 'normal')) or {}
    return updated(style_default, basestyle, parstyle, style)


def mk_parstyle(stylesheet, parstyle):
    basestyle = stylesheet.get(parstyle.get('base', 'normal')) or {}
    return updated(style_default, basestyle, parstyle)


class RowFactory:

    def __init__(self, stylesheet, device=TESTDEVICE, line_width=400):
        self.stylesheet = stylesheet
        self.device = device
        self.line_width = line_width
        self.counters = {}
        self.footnote_counter = 0
        self.fn_sink = []  # [(label, content_texel), ...]
        self.restartmemo = (0, {}, 0)  # (i, counters, footnote_counter)

    # ---- Row generation --------------------------------------------

    def generate_rows(self, texel, i=0, restartmemo=None):
        """Yield row records (row, parstyle, begins_par, ends_par,
        begins_block, ends_block) for texel[i:]. Starts fresh at i, or
        resumes from restartmemo (position, counters, footnote_counter)."""
        if restartmemo is not None:
            i, counters, self.footnote_counter = restartmemo
            self.counters = copy_counters(counters)
        else:
            self.counters = {}
            self.footnote_counter = 0
        self.fn_sink = []
        self.restartmemo = (i, copy_counters(self.counters),
                             self.footnote_counter)
        for i1, i2, texels, p_prev, p, p_next in \
                self._iter_paragraphs_with_neighbors(texel, i):
            yield from self._process_paragraph(i1, i2, texels, p_prev, p, p_next)

    # ---- Child factory for self-contained sub-layouts ---------------

    def create_child(self):
        """Child factory for a sub-layout (e.g. a table cell). Shares
        caches/stylesheet/device/line_width via shallow_copy."""
        return shallow_copy(self)

    def update_from_child(self, child):
        """Merges footnote_counter and fn_sink from the child. The
        child's counters/position stay local to the child."""
        self.footnote_counter = child.footnote_counter
        self.fn_sink.extend(child.fn_sink)

    # ---- Paragraph lookahead -----------------------------------------

    def _iter_paragraphs_with_neighbors(self, texel, i):
        """Yield (i1, i2, texels, p_prev, p, p_next) per paragraph in
        texel[i:]: i1/i2/texels as in iter_paragraphs (paragraph start/
        end, leaf texel list), p the resolved parstyle of the paragraph
        itself, p_prev/p_next that of the previous/next paragraph (None
        at the start/end of texel[i:]).

        For i>0, p_prev for the first yielded paragraph is looked up
        via the texel at position i-1 (the previous paragraph's
        NewLine) instead of assumed to be None."""
        p_prev = get_texel(texel, i - 1).parstyle if i > 0 else None
        if p_prev is not None:
            p_prev = mk_parstyle(self.stylesheet, p_prev)
        buffered = None  # (i1, i2, texels, p)

        for i1, i2, texels in iter_paragraphs(texel, i):
            p = mk_parstyle(self.stylesheet, texels[-1].parstyle)
            if buffered is not None:
                b_i1, b_i2, b_texels, b_p = buffered
                yield b_i1, b_i2, b_texels, p_prev, b_p, p
                p_prev = b_p
            buffered = i1, i2, texels, p

        if buffered is not None:
            i1, i2, texels, p = buffered
            yield i1, i2, texels, p_prev, p, None

    # ---- Paragraph processing -----------------------------------------

    def _process_paragraph(self, i1, i2, texels, p_prev, p, p_next):
        boxes = [self.create_boxes(elem, p) for elem in texels]
        begins_block = not _is_same_block(p, p_prev)
        ends_block = not _is_same_block(p, p_next)
        yield from self._finish_paragraph(boxes, i1, i2, p, begins_block, ends_block)

    def create_boxes(self, texel, parstyle):
        handler = getattr(self, texel.__class__.__name__ + '_handler')
        return handler(texel, parstyle)

    # ---- Leaf handlers: texel, paragraph's parstyle -> Box -------------

    def Text_handler(self, texel, parstyle):
        return TextBox(texel.text,
                        mk_style(self.stylesheet, parstyle, texel.style),
                        self.device)

    def Footnote_handler(self, texel, parstyle):
        from ..footnotes.footnotes import format_fn_label
        self.footnote_counter += 1
        label = texel.label or format_fn_label(self.footnote_counter, texel.numbering)
        self.fn_sink.append((label, texel.content))
        style = mk_style(self.stylesheet, parstyle, texel.style)
        return TextBox(label, style, self.device)

    def Table_handler(self, texel, parstyle):
        ncols = texel.ncols
        col_width = self.line_width / ncols
        cells = []
        for j1, j2, cell_texel in iter_childs(texel):
            child = self.create_child()
            child.line_width = col_width
            seed = (0, {}, self.footnote_counter)
            records = list(child.generate_rows(cell_texel, restartmemo=seed))
            self.update_from_child(child)
            cells.append(records)
        return TableBox(cells, ncols, col_width, self.device, length(texel))

    def NewLine_handler(self, texel, parstyle):
        style = mk_style(self.stylesheet, parstyle, texel.style)
        cls = EndBox if texel.is_endmark else NewlineBox
        return cls(style, self.device)

    # ---- Finishing a paragraph -----------------------------------------

    def _finish_paragraph(self, boxes, i1, i2, parstyle, begins_block, ends_block):
        level = parstyle.get('fixed_indent') or 0

        marker = self._update_counters(parstyle)
        left_first, left_rest, width_first, width_rest = \
            self._dims(parstyle, level)
        alignment = parstyle['alignment']
        lines = simple_linewrap(boxes, width_first, width_rest)
        n = len(lines)

        # Must be set before the first yield: code after a yield only
        # runs on the next next() call.
        self.restartmemo = (i2, copy_counters(self.counters),
                             self.footnote_counter)

        for k, line in enumerate(lines):
            is_first, is_last = k == 0, k == n - 1
            width, left = (width_first, left_first) if is_first \
                else (width_rest, left_rest)
            if alignment == 'justify' and not is_last:
                line = justify_line(line, width)
            row = Row(line, device=self.device)
            row.start = (align_x(alignment, left, width, row.width), 0)
            if is_first and marker is not None:
                row.set_marker(marker, parstyle['marker_pos'][level], parstyle)
            yield (row, parstyle, is_first, is_last, begins_block, ends_block)

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
        width_rest = self.line_width - block_indent
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
        counter = self.counters.setdefault(ckey, [0] * n_levels)
        sn = parstyle.get('start_number')
        if sn is not None:
            set_counter(level, counter, sn)
        else:
            inc_counter(level, counter)
        if ckey == 'section':
            self.counters['item'] = [0] * n_levels
        return format_number(counter, level, parstyle['numbering_style'][level])


BLOCK_KEYS = ('block_color', 'block_padding', 'block_border')


def block_key(parstyle):
    return tuple(parstyle.get(k) for k in BLOCK_KEYS)


def _is_same_block(style_a, style_b):
    if style_a is None or style_b is None:
        return False
    return block_key(style_a) == block_key(style_b)


# ---------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------


class Table(Container):
    """Table texel stand-in for the tests: childs are the cell
    contents (row by row, ncols per table row)."""

    def __init__(self, cell_texels, ncols):
        self.ncols = ncols
        self.childs = list(cell_texels)
        self.compute_weights()


class TableBox:
    """Turns each cell's row records into a box (create_cell) at
    col_width. Width = ncols * col_width, height = sum of per-table-row
    heights (each row's height is the max over its cells)."""

    def __init__(self, cells, ncols, col_width, device, length_):
        from ..tables.table_boxes import create_cell
        self.cells = [create_cell(records, col_width, device)
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


def _nl(parstyle, endmark=False):
    nl = NewLine().set_parstyle(parstyle)
    if endmark:
        nl.is_endmark = 1
    return nl


def _make_doc():
    normal = {'base': 'normal'}
    numbered = {'base': 'normal', 'paragraph_type': 'numbered',
                'fixed_indent': 0, 'list_indent': 2}

    # P0: plain paragraph. P1/P2: numbered ("1."/"2."). P3: several
    # short words (wraps at line_width=20). P4: numbered (endmark).
    return Group([
        Text('Hello '), Text('World'), _nl(normal),
        Text('First item'), _nl(numbered),
        Text('Second item'), _nl(numbered),
        Text('This '), Text('paragraph '), Text('has '), Text('several '),
        Text('short '), Text('words.'), _nl(normal),
        Text('Third item'), _nl(numbered, endmark=True),
    ])


def _texts(row):
    return ''.join(box.text for box in row.childs if isinstance(box, TextBox))


def _rows(box):
    "Row list of a RowsBox/CellBox, recursively unpacked from .data (x, y, row)."
    rows = []
    for _, _, child in box.data:
        if isinstance(child, Row):
            rows.append(child)
        else:
            rows.extend(_rows(child))
    return rows


def test_00():
    "Basic pass: lines, wrapping, numbering"
    texel = _make_doc()
    factory = RowFactory(testsheet, TESTDEVICE, line_width=20)
    records = list(factory.generate_rows(texel, 0))

    rows = [r[0] for r in records]
    assert _texts(rows[0]) == 'Hello World'

    assert rows[1].marker == '1.'
    assert _texts(rows[1]) == 'First item'
    assert rows[2].marker == '2.'
    assert _texts(rows[2]) == 'Second item'

    p3_rows = rows[3:-1]
    assert len(p3_rows) > 1
    assert ''.join(_texts(r) for r in p3_rows) == \
        'This paragraph has several short words.'
    for r in p3_rows:
        assert r.width <= 20

    assert rows[-1].marker == '3.'
    assert _texts(rows[-1]) == 'Third item'


def test_01():
    "Restart at a paragraph boundary matches full run"
    texel = _make_doc()

    full_factory = RowFactory(testsheet, TESTDEVICE, line_width=20)
    full_records = list(full_factory.generate_rows(texel, 0))

    partial_factory = RowFactory(testsheet, TESTDEVICE, line_width=20)
    gen = partial_factory.generate_rows(texel, 0)
    first_three = [next(gen) for _ in range(3)]
    memo = partial_factory.restartmemo

    # Row objects are distinct instances (no __eq__), so compare text.
    assert [_texts(r[0]) for r in first_three] == \
        [_texts(full_records[i][0]) for i in range(3)]
    assert memo[1]['item'][0] == 2

    resumed_factory = RowFactory(testsheet, TESTDEVICE, line_width=20)
    resumed_records = list(resumed_factory.generate_rows(texel, restartmemo=memo))

    resumed_texts = [_texts(r[0]) for r in resumed_records]
    full_tail_texts = [_texts(r[0]) for r in full_records[3:]]
    assert resumed_texts == full_tail_texts
    assert resumed_records[-1][0].marker == '3.'


def _make_footnote_doc():
    normal = {'base': 'normal'}
    numbered = {'base': 'normal', 'paragraph_type': 'numbered', 'fixed_indent': 0}

    fn1_content = Group([Text('First footnote text.'), _nl(normal, endmark=True)])
    fn2_content = Group([
        Text('Numbered inside footnote.'), _nl(numbered, endmark=True)])

    # P0: "See<anchor>here" (footnote 1). P1: "And<anchor>again" (footnote 2, endmark).
    return Group([
        Text('See'), Footnote(fn1_content), Text(' here'), _nl(normal),
        Text('And'), Footnote(fn2_content), Text(' again'),
        _nl(normal, endmark=True),
    ])


def test_02():
    "Footnotes: anchor inline, counter survives reset"
    texel = _make_footnote_doc()
    factory = RowFactory(testsheet, TESTDEVICE, line_width=400)

    drained = []
    records = []
    for record in factory.generate_rows(texel, 0):
        records.append(record)
        if record[3]:  # ends_par
            drained.extend(factory.fn_sink)
            factory.fn_sink.clear()

    assert len(records) == 2
    assert _texts(records[0][0]) == 'See1 here'
    assert _texts(records[1][0]) == 'And2 again'
    assert [label for label, _ in drained] == ['1', '2']

    partial = RowFactory(testsheet, TESTDEVICE, line_width=400)
    gen = partial.generate_rows(texel, 0)
    next(gen)
    memo = partial.restartmemo
    assert memo[2] == 1  # footnote_counter
    assert [label for label, _ in partial.fn_sink] == ['1']

    resumed = RowFactory(testsheet, TESTDEVICE, line_width=400)
    resumed_records = list(resumed.generate_rows(texel, restartmemo=memo))
    assert _texts(resumed_records[0][0]) == 'And2 again'
    assert [label for label, _ in resumed.fn_sink] == ['2']

    from .typesetter import typeset_into_rect
    label, content = drained[1]
    fn_factory = RowFactory(testsheet, TESTDEVICE, line_width=400)
    fn_records = list(fn_factory.generate_rows(content, 0))
    fn_box = typeset_into_rect(fn_records, 400, TESTDEVICE)
    assert _rows(fn_box)[0].marker == '1.'


def _make_table_doc():
    normal = {'base': 'normal'}
    fn_before = Group([Text('Note before table.'), _nl(normal, endmark=True)])
    fn_cell = Group([Text('Note inside cell.'), _nl(normal, endmark=True)])
    fn_after = Group([Text('Note after table.'), _nl(normal, endmark=True)])

    cell0 = Group([
        Text('This '), Text('cell '), Text('wraps '), Text('at '),
        Text('twenty.'), _nl(normal, endmark=True)])
    cell1 = Group([
        Text('Cell two'), Footnote(fn_cell), _nl(normal, endmark=True)])
    table = Table([cell0, cell1], ncols=2)

    # P0 before the table: footnote "1". Cell 1: footnote "2". P1
    # after the table: footnote "3".
    return Group([
        Text('Before'), Footnote(fn_before), _nl(normal),
        table, _nl(normal),
        Text('After'), Footnote(fn_after), _nl(normal, endmark=True),
    ])


def test_03():
    "Tables: per-cell child factory, fn_sink flows up"
    texel = _make_table_doc()
    factory = RowFactory(testsheet, TESTDEVICE, line_width=40)  # col_width=20
    records = list(factory.generate_rows(texel, 0))

    assert len(records) == 3  # P0 row, table row, P1 row
    assert _texts(records[0][0]) == 'Before1'
    assert _texts(records[2][0]) == 'After3'

    table_row = records[1][0]
    table_box = table_row.childs[0]
    assert isinstance(table_box, TableBox)

    assert table_box.width == 40
    assert table_box.col_width == 20

    cell0 = table_box.cells[0]
    assert cell0.width == 20

    assert len(_rows(cell0)) > 1
    for row in _rows(cell0):
        assert row.width <= 20
    assert ''.join(_texts(r) for r in _rows(cell0)) == \
        'This cell wraps at twenty.'

    assert _texts(_rows(table_box.cells[1])[0]) == 'Cell two2'
    assert [label for label, _ in factory.fn_sink] == ['1', '2', '3']


def _make_layout_doc():
    indented = {'base': 'normal', 'fixed_indent': 1,
                'indent_levels': (0, 5, 10), 'first_line_indent': -3}
    centered = {'base': 'normal', 'alignment': 'center'}
    right = {'base': 'normal', 'alignment': 'right'}
    justify = {'base': 'normal', 'alignment': 'justify'}

    # P0: hanging indent, 5 equal-width words (wraps after 4 words at
    # width_first=18). P1: centered. P2: right-aligned. P3: justified.
    return Group([
        Text('Aaa '), Text('Bbb '), Text('Ccc '), Text('Ddd '), Text('Eee '),
        _nl(indented),
        Text('Centered'), _nl(centered),
        Text('Right aligned'), _nl(right),
        Text('This '), Text('is '), Text('justified '), Text('text.'),
        _nl(justify, endmark=True),
    ])


def test_04():
    "Indentation and alignment (all 4 modes)"
    texel = _make_layout_doc()
    factory = RowFactory(testsheet, TESTDEVICE, line_width=20)
    rows = [r[0] for r in factory.generate_rows(texel, 0)]

    assert _texts(rows[0]) == 'Aaa Bbb Ccc Ddd '
    assert rows[0].start[0] == 2
    assert _texts(rows[1]) == 'Eee '
    assert rows[1].start[0] == 5

    centered_row = rows[2]
    assert _texts(centered_row) == 'Centered'
    assert centered_row.start[0] == 0.5 * (20 - centered_row.width)

    right_row = rows[3]
    assert _texts(right_row) == 'Right aligned'
    assert right_row.start[0] == 20 - right_row.width

    justified_rows = rows[4:]
    assert len(justified_rows) == 2
    assert justified_rows[0].width > 18
    assert justified_rows[1].width == 5  # 'text.' + EndBox


def test_05():
    "begins_block/ends_block, not just alias of par"
    boxed = {'base': 'normal', 'block_color': '#eee'}
    plain = {'base': 'normal'}
    texel = Group([
        Text('One'), _nl(boxed),
        Text('Two'), _nl(boxed),
        Text('Three'), _nl(plain, endmark=True),
    ])
    factory = RowFactory(testsheet, TESTDEVICE, line_width=400)
    records = list(factory.generate_rows(texel, 0))
    assert len(records) == 3

    # (row, parstyle, begins_par, ends_par, begins_block, ends_block)
    assert records[0][4:6] == (True, False)
    assert records[1][4:6] == (False, True)
    assert records[2][4:6] == (True, True)
    assert all(r[2:4] == (True, True) for r in records)
