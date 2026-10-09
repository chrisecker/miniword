# -*- coding: utf-8 -*-

"""
Tests for rowfactory.py, following develnotes/rowfactory_tests.md.
Each test's docstring starts with its ID from that list.

Run with: python runtests.py miniword/tests/test_rowfactory.py

TESTDEVICE measures every character as 1 wide, every box as 1 high
(depth 0) - all widths/heights below rely on that.
"""

from ..textmodel.texeltree import Text, NewLine, Group, Tabulator, length
from ..textmodel.submodel import Footnote
from ..textmodel.utils import iter_paragraphs
from ..core.texels import BR
from ..core.styles import n_levels
from ..core.stylesheet import testsheet
from ..footnotes.footnotes import FootnoteAnchorBox
from ..layout.boxes import TextBox, NewlineBox, EndBox, TabulatorBox, Row, \
    RowsBox
from ..layout.page import ForceBreakBox, FootnoteBox
from ..layout.testdevice import TESTDEVICE
from ..layout.rowfactory import State, state_from_settings, RowFactory, \
    RowStack, typeset_into_rect, clip_x, generate_pages, \
    block_key, FOOTNOTE_FRACTION, MIN_LABEL_INDENT, LABEL_GAP
from ..tables.table_boxes import TableBox


# ---------------------------------------------------------------------
# Helpers: documents
# ---------------------------------------------------------------------

def ps(**kw):
    """A parstyle based on 'normal'."""
    return dict(base='normal', **kw)


def nl(endmark=False, **kw):
    newline = NewLine().set_parstyle(ps(**kw))
    if endmark:
        newline.is_endmark = 1
    return newline


def par(*items, **kw):
    """A paragraph: items (strings become Text) plus its NewLine."""
    texels = [Text(item) if isinstance(item, str) else item for item in items]
    return texels + [nl(**kw)]


def doc(*pars):
    """A document from paragraphs (see par)."""
    return Group([texel for p in pars for texel in p])


def fn(*items):
    """A footnote whose content is one paragraph made of items."""
    texels = [Text(item) if isinstance(item, str) else item for item in items]
    return Footnote(Group(texels + [nl(endmark=True)]))


def numbered(level=0, **kw):
    return dict(paragraph_type='numbered', fixed_indent=level, **kw)


LEVELS = tuple(4 * k for k in range(n_levels))  # indent_levels for tests


# ---------------------------------------------------------------------
# Helpers: running the factory
# ---------------------------------------------------------------------

def generate(texel, width=100, i=0, state=None):
    """Run RowFactory over texel. Returns (paragraphs, state):
    paragraphs is a list of record lists, one per paragraph."""
    state = state or State(width)
    factory = RowFactory(state, testsheet, TESTDEVICE)
    return list(factory.generate(texel, i)), state


def flat(paragraphs):
    return [record for p in paragraphs for record in p]


def box_text(box):
    if isinstance(box, FootnoteAnchorBox):
        return '[%s]' % box.display
    if isinstance(box, (NewlineBox, EndBox, ForceBreakBox)):
        return ''
    return getattr(box, 'text', '')


def row_text(row):
    return ''.join(box_text(box) for box in row.childs)


def flags(record):
    return tuple(record[2:6])


def iter_rows(box):
    """All Rows inside box (descends into cells/data/childs)."""
    if isinstance(box, Row):
        yield box
        return
    if isinstance(box, list):  # a row of a TableBox's cells
        for child in box:
            yield from iter_rows(child)
        return
    for _, _, child in getattr(box, 'data', ()):
        yield from iter_rows(child)
    for child in getattr(box, 'cells', ()):
        yield from iter_rows(child)


def Table(cells, ncols):
    """A real table from cell contents written as paragraphs (Group
    ending with a NewLine): the cell's last NewLine becomes the
    separator after it."""
    from ..tables.tables import Table as RealTable
    from ..textmodel.utils import iter_leafes
    entries = []
    for cell in cells:
        leaves = [t for _, _, t in iter_leafes(cell, 0)]
        last = leaves.pop()
        assert isinstance(last, NewLine)
        content = Group(leaves) if leaves else Group([])
        entries.append((content, {}))
    return RealTable(*entries, ncols=ncols)


def find_boxes(paragraphs, cls):
    return [box for record in flat(paragraphs) for box in record[0].childs
            if isinstance(box, cls)]


# ---------------------------------------------------------------------
# Helpers: records for RowStack
# ---------------------------------------------------------------------

def mk_row(height=1, length=1):
    row = Row([TextBox('x' * length, device=TESTDEVICE)], device=TESTDEVICE)
    row.height = height
    row.depth = 0
    return row


def mk_records(*spec):
    """Records from (nrows, parstyle) pairs, one pair per paragraph;
    block flags derived from neighbouring parstyles like the factory
    does. Each row is 1 high."""
    records = []
    for k, (nrows, style) in enumerate(spec):
        prev = spec[k - 1][1] if k > 0 else None
        nxt = spec[k + 1][1] if k + 1 < len(spec) else None
        begins_block = prev is None or block_key(prev) != block_key(style)
        ends_block = nxt is None or block_key(nxt) != block_key(style)
        for j in range(nrows):
            records.append((mk_row(), style, j == 0, j == nrows - 1,
                            begins_block, ends_block))
    return records


def stack(buffer, width, max_height=None):
    """One RowStack.take on a fresh stack. Returns (data, height,
    shadings, borders)."""
    rowstack = RowStack(width)
    rowstack.take(buffer, max_height)
    return (rowstack.data(), rowstack.height) + rowstack.decorations()


# ---------------------------------------------------------------------
# Helpers: pages and memos
# ---------------------------------------------------------------------

def small_memo(width=20, height=5):
    """A fresh State for a small test page: text area width x height,
    border 1 on every side."""
    memo = State(width)
    memo.geometry = (width + 2, height + 2)
    memo.border = (1, 1, 1, 1)
    return memo


def pages_from(texel, memo, i1=0):
    return list(generate_pages(texel, i1, memo, testsheet, TESTDEVICE))


def footnote_rows(page):
    if page.footnotebox is None:
        return []
    return [row for _, _, row in page.footnotebox[2].data]


def page_sig(page):
    """What a page shows, independent of its position in index space."""
    return (len(page),
            [row_text(row) for _, _, row in page.rows],
            [row_text(row) for row in footnote_rows(page)])


def page_starts(pages):
    """i1 of every page."""
    starts, i = [], 0
    for page in pages:
        starts.append(i)
        i += len(page)
    return starts


def record_sig(record):
    row = record[0]
    boxes = [(type(box).__name__, box_text(box), box.width)
             for box in row.childs]
    return (len(row), boxes, row.height, row.depth, row.start, row.width,
            row.marker, record[1], flags(record))


def state_sig(state):
    """Content of a State, for comparing memos. Identity is not
    enough: rows are rebuilt on every restart."""
    return (state.width, state.geometry, state.border,
            {k: list(v) for k, v in state.counters.items()},
            state.footnote_counter,
            [record_sig(r) for r in state.rows],
            [record_sig(r) for r in state.footnotes],
            len(state.floats))


def same_state(a, b):
    return state_sig(a) == state_sig(b)


def long_doc(n=12, prefix='', fn_every=3, last_text=None):
    """n paragraphs of six words (3 rows each at width 20); every
    fn_every-th paragraph has a footnote. prefix is put in front of the
    first paragraph's text, last_text replaces the last paragraph's."""
    pars = []
    for k in range(n):
        text = ' '.join('w%d_%d' % (k, j) for j in range(6)) + ' '
        if k == 0:
            text = prefix + text
        if k == n - 1 and last_text is not None:
            text = last_text
        items = [text]
        if fn_every and k % fn_every == 0:
            items.append(fn('note %d' % k))
        pars.append(par(*items))
    return doc(*pars)


# ---------------------------------------------------------------------
# FAC - Factory and boxes
# ---------------------------------------------------------------------

def test_FAC_1():
    "FAC-1: every texel type gives the matching box"
    texel = doc(par('ab', BR(), 'cd', Tabulator(), fn('x')),
                par('end', endmark=True))
    paragraphs, state = generate(texel)
    types = [type(box) for record in flat(paragraphs)
             for box in record[0].childs]
    assert TextBox in types
    assert NewlineBox in types
    assert EndBox in types
    assert ForceBreakBox in types
    assert FootnoteAnchorBox in types
    assert TabulatorBox in types


def test_FAC_1_table():
    "FAC-1: a Table texel gives a TableBox"
    table = Table([Group(par('a', endmark=True)),
                   Group(par('b', endmark=True))], ncols=2)
    paragraphs, state = generate(doc(par(table)))
    assert len(find_boxes(paragraphs, TableBox)) == 1


def test_FAC_2():
    "FAC-2: an unknown texel type gives a clear error"
    class Unknown(Text):
        pass
    texel = doc(par(Unknown('x')))
    try:
        generate(texel)
    except Exception as e:
        assert 'Unknown' in str(e), str(e)
    else:
        assert False, 'no error for unknown texel'


def test_FAC_3():
    "FAC-3: per paragraph, row lengths add up to i2 - i1"
    texel = doc(par('Hello ', fn('a note'), Tabulator(), 'world'),
                par('one ', BR(), 'two ', fn('x'), fn('y')),
                par(),
                par('last', endmark=True))
    paragraphs, state = generate(texel, width=6)
    spans = list(iter_paragraphs(texel, 0))
    assert len(spans) == len(paragraphs)
    for (i1, i2, _), records in zip(spans, paragraphs):
        assert sum(len(r[0]) for r in records) == i2 - i1, (i1, i2)


def test_FAC_4():
    "FAC-4: all row lengths add up to the texel length"
    from einstein import get_einstein
    texel = get_einstein()  # extended texel, ends with ENDMARK
    paragraphs, state = generate(texel, width=80)
    assert sum(len(r[0]) for r in flat(paragraphs)) == length(texel)


# ---------------------------------------------------------------------
# WRAP - Line wrapping and alignment
# ---------------------------------------------------------------------

def test_WRAP_1():
    "WRAP-1: a paragraph wraps at state.width"
    texel = doc(par('aaa bbb ccc ddd eee fff ggg'))
    records = flat(generate(texel, width=10)[0])
    assert len(records) > 1
    for row, *_ in records:
        assert row.start[0] + row.width <= 10, row_text(row)


def test_WRAP_2():
    "WRAP-2: first_line_indent, positive and negative"
    text = 'aaa bbb ccc ddd eee fff ggg'
    records = flat(generate(doc(par(text, first_line_indent=2)),
                            width=10)[0])
    assert records[0][0].start[0] == 2
    assert all(r[0].start[0] == 0 for r in records[1:])
    assert records[0][0].start[0] + records[0][0].width <= 10

    style = dict(first_line_indent=-2, fixed_indent=1, indent_levels=LEVELS)
    records = flat(generate(doc(par(text, **style)), width=12)[0])
    assert records[0][0].start[0] == 2
    assert all(r[0].start[0] == 4 for r in records[1:])


def test_WRAP_3():
    "WRAP-3: indent_levels apply according to fixed_indent"
    text = 'aaa bbb ccc ddd eee fff ggg'
    style = dict(fixed_indent=2, indent_levels=LEVELS)
    records = flat(generate(doc(par(text, **style)), width=16)[0])
    for row, *_ in records:
        assert row.start[0] == 8
        assert row.start[0] + row.width <= 16


def test_WRAP_4():
    "WRAP-4: list_indent applies only to list/numbered paragraphs"
    def x(**kw):
        records = flat(generate(doc(par('ab', list_indent=3, **kw)))[0])
        return records[0][0].start[0]
    assert x() == 0
    assert x(paragraph_type='list', fixed_indent=0) == 3
    assert x(paragraph_type='numbered', fixed_indent=0) == 3


def test_WRAP_5():
    "WRAP-5: alignment left/right/center positions the row"
    def x(alignment):
        records = flat(generate(doc(par('ab', alignment=alignment)),
                                width=10)[0])
        return records[0][0].start[0]
    assert x('left') == 0
    assert x('right') == 8
    assert x('center') == 4


def test_WRAP_6():
    "WRAP-6: justify fills all lines but the last"
    text = 'aaa bb c dddd ee fff gg h iiii'
    records = flat(generate(doc(par(text, alignment='justify')),
                            width=12)[0])
    assert len(records) > 2
    for row, *_ in records[:-1]:
        # the trailing space (1 wide) is not counted
        assert abs(row.width - 1 - 12) < 1e-9, row.width
    last = records[-1][0]
    assert last.width == len(row_text(last))


def test_WRAP_7():
    "WRAP-7: BR forces a break; later lines keep width_rest's indent"
    style = dict(first_line_indent=2, fixed_indent=1, indent_levels=LEVELS)
    records = flat(generate(doc(par('ab', BR(), 'cd', **style)),
                            width=40)[0])
    assert [row_text(r[0]) for r in records] == ['ab', 'cd']
    assert records[0][0].start[0] == 6
    assert records[1][0].start[0] == 4


class SelectionDevice(type(TESTDEVICE)):
    """TESTDEVICE recording invert_rect; like real fonts it measures the
    newline character wider than a space."""
    def __init__(self):
        self.rects = []

    def measure(self, text, style):
        return 5 * text.count('\n') + len(text.replace('\n', '')), 1, 0

    def invert_rect(self, x, y, w, h, dc):
        self.rects.append((x, x + w))


def test_WRAP_13():
    "WRAP-13: a right aligned paragraph selected as a whole has a straight edge"
    device = SelectionDevice()
    texel = doc(par('aaa bbb ccc ddd eee fff ggg', alignment='right',
                    **INDENTED))
    factory = RowFactory(State(20), testsheet, device)
    records = [r for p in factory.generate(texel, 0) for r in p]
    assert len(records) > 2
    ends = []
    for row, *_ in records:
        device.rects.clear()
        row.draw_selection(0, len(row), 0, 0, None)
        ends.append(max(x2 for _, x2 in device.rects))
    assert ends == [19] * len(records)  # edge 18 plus a space


def test_WRAP_14():
    "WRAP-14: CJK text breaks after any character, without spaces"
    rows = flat(generate(doc(par('中文日本語中文日本語')), width=4)[0])
    assert [row_text(r[0]) for r in rows] == ['中文日本', '語中文日', '本語']


def test_WRAP_15():
    "WRAP-15: kinsoku - no line starts with closing punctuation"
    rows = flat(generate(doc(par('日本語。中文')), width=3)[0])
    texts = [row_text(r[0]) for r in rows]
    assert texts == ['日本', '語。中', '文']
    assert not any(t.startswith('。') for t in texts)


def test_WRAP_16():
    "WRAP-16: mixed Latin and CJK text breaks at spaces and after CJK"
    rows = flat(generate(doc(par('ab cd 中文日本')), width=7)[0])
    assert [row_text(r[0]) for r in rows] == ['ab cd 中', '文日本']


def test_WRAP_17():
    "WRAP-17: a line may break after a hyphen within a word"
    rows = flat(generate(doc(par('Der Hals-Nasen-Ohren-Arzt kommt')),
                         width=14)[0])
    assert [row_text(r[0]) for r in rows] == \
        ['Der Hals-', 'Nasen-Ohren-', 'Arzt kommt']


def test_WRAP_18():
    "WRAP-18: no break at a free-standing dash or between digits"
    from ..layout.linewrap import _BREAK_RE
    def breaks(text):
        return [m.start() for m in _BREAK_RE.finditer(text)]
    assert breaks('ab - cd') == [3, 5]       # after the spaces only
    assert breaks('2026-10-06') == []
    assert breaks('ab-cd') == [3]


def test_WRAP_8():
    "WRAP-8: an empty paragraph gives exactly one row"
    paragraphs, state = generate(doc(par('a'), par(), par('b')))
    assert [len(p) for p in paragraphs] == [1, 1, 1]
    assert isinstance(paragraphs[1][0][0].childs[0], NewlineBox)


def test_WRAP_9():
    "WRAP-9: line_spacing is applied to the row, as before"
    def hd(line_spacing):
        texel = doc(par('ab', line_spacing=line_spacing))
        row = flat(generate(texel)[0])[0][0]
        return row.height, row.depth
    assert hd(1.0) == (1, 0)
    assert hd(1.5) == (1.25, 0.25)
    assert hd(0.2) == (0.75, -0.25)  # negative leading at most -0.5

    # applies to footnote content too, and stacks without further ado
    note = Footnote(Group([Text('note'), nl(endmark=True, line_spacing=2.0)]))
    paragraphs, state = generate(doc(par('a', note, line_spacing=1.5),
                                     par('b', line_spacing=1.5)))
    assert state.footnotes[0][0].height + state.footnotes[0][0].depth == 2
    rowstack = RowStack(100)
    rowstack.take(flat(paragraphs))
    assert [y for y, _ in rowstack.placed] == [0, 1.5]


INDENTED = dict(fixed_indent=1, indent_levels=LEVELS, first_line_indent=3,
                right_indent=2)  # width 20: lines 7..18, then 4..18


def visible(row):
    """x range of a row without its trailing spaces (each 1 wide)."""
    text = row_text(row)
    trailing = len(text) - len(text.rstrip(' '))
    return row.start[0], row.start[0] + row.width - trailing


def test_WRAP_10():
    "WRAP-10: right alignment ends every line at the right indent"
    text = 'aaa bbb ccc ddd eee fff ggg'
    records = flat(generate(doc(par(text, alignment='right', **INDENTED)),
                            width=20)[0])
    assert len(records) > 2
    assert row_text(records[0][0]).endswith(' ')  # the space hangs over
    assert [visible(r[0])[1] for r in records] == [18] * len(records)
    assert visible(records[0][0])[0] >= 7
    assert all(visible(r[0])[0] >= 4 for r in records[1:])


def test_WRAP_11():
    "WRAP-11: centered lines are centered between their indents"
    text = 'aaa bbb ccc ddd eee fff ggg'
    records = flat(generate(doc(par(text, alignment='center', **INDENTED)),
                            width=20)[0])
    centers = [sum(visible(r[0])) / 2 for r in records]
    assert centers == [(7 + 18) / 2] + [(4 + 18) / 2] * (len(records) - 1)


def test_WRAP_12():
    "WRAP-12: caret, selection and clicks follow the aligned row"
    text = 'aaa bbb ccc ddd eee fff ggg'
    for alignment in ('left', 'right', 'center'):
        records = flat(generate(
            doc(par(text, alignment=alignment, **INDENTED)), width=20)[0])
        row = records[0][0]
        x0 = row.start[0]
        for i in range(len(row)):
            assert row.get_rect(i, 0, 0).x1 == x0 + i, (alignment, i)
            assert row.get_index(x0 + i + 0.2, 0) == i, (alignment, i)


# ---------------------------------------------------------------------
# FLAG - Record flags
# ---------------------------------------------------------------------

def test_WRAP_19():
    "WRAP-19: a standalone box (e.g. a table) is a segment of its own"
    from ..layout.rowfactory import segments
    a, b, c = TextBox('a'), TextBox('b'), TextBox('c')
    box = TextBox('x')
    box.standalone = True
    assert segments([a, b, box, c]) == [[a, b], [box], [c]]
    assert segments([box]) == [[box]]
    assert TableBox.standalone and not TextBox.standalone


def test_FLAG_1():
    "FLAG-1: begins_par/ends_par on the first/last row"
    paragraphs, state = generate(doc(par('aaa bbb ccc ddd'), par('x')),
                                 width=4)
    long, short = paragraphs
    assert len(long) == 4
    assert [r[2] for r in long] == [True, False, False, False]
    assert [r[3] for r in long] == [False, False, False, True]
    assert short[0][2] and short[0][3]


def test_FLAG_2():
    "FLAG-2: same block_key as the neighbour - one continuous block"
    paragraphs, state = generate(doc(par('a', block_color='red'),
                                     par('b', block_color='red')))
    a, b = paragraphs[0][0], paragraphs[1][0]
    assert a[4] and not a[5]
    assert not b[4] and b[5]


def test_FLAG_3():
    "FLAG-3: different block_key - a block boundary"
    paragraphs, state = generate(doc(par('a', block_color='red'),
                                     par('b', block_color='blue')))
    a, b = paragraphs[0][0], paragraphs[1][0]
    assert a[4] and a[5]
    assert b[4] and b[5]


def test_FLAG_4():
    "FLAG-4: starting at i > 0 reads p_prev from the previous paragraph"
    first = par('a', block_color='red')
    texel = doc(first, par('b', block_color='red'))
    i = length(Group(first))
    paragraphs, state = generate(texel, i=i)
    assert row_text(paragraphs[0][0][0]) == 'b'
    assert not paragraphs[0][0][4]  # continues the block


# ---------------------------------------------------------------------
# CNT - Counters
# ---------------------------------------------------------------------

def markers(paragraphs):
    return [p[0][0].marker for p in paragraphs]


def test_CNT_1():
    "CNT-1: numbered paragraphs count up"
    paragraphs, state = generate(doc(par('a', **numbered()),
                                     par('b', **numbered()),
                                     par('c', **numbered())))
    assert markers(paragraphs) == ['1.', '2.', '3.']


def test_CNT_2():
    "CNT-2: start_number sets the counter"
    paragraphs, state = generate(doc(par('a', **numbered(start_number=5)),
                                     par('b', **numbered())))
    assert markers(paragraphs) == ['5.', '6.']


def test_CNT_3():
    "CNT-3: levels count separately"
    styles = ('1.', '1.1.', '1.1.1.') + ('1.',) * (n_levels - 3)
    def p(level):
        return par('x', **numbered(level, numbering_style=styles))
    paragraphs, state = generate(doc(p(0), p(1), p(1), p(0), p(1)))
    assert markers(paragraphs) == ['1.', '1.1.', '1.2.', '2.', '2.1.']


def test_CNT_4():
    "CNT-4: section resets item"
    def section():
        return par('s', **numbered(counter='section'))
    def item():
        return par('i', **numbered())
    paragraphs, state = generate(doc(section(), item(), item(),
                                     section(), item()))
    assert markers(paragraphs) == ['1.', '1.', '2.', '2.', '1.']


def test_CNT_5():
    "CNT-5: list markers don't change any counter"
    bullet = dict(paragraph_type='list', fixed_indent=0)
    paragraphs, state = generate(doc(par('a', **numbered()),
                                     par('b', **bullet),
                                     par('c', **numbered())))
    marker = testsheet.mk_parstyle(ps())['marker'][0]
    assert markers(paragraphs) == ['1.', marker, '2.']


def test_CNT_6():
    "CNT-6: counters in a footnote don't flow back"
    note = Footnote(Group(par('n1', **numbered())
                          + par('n2', endmark=True, **numbered())))
    paragraphs, state = generate(doc(par('a', note, **numbered()),
                                     par('b', **numbered())))
    assert markers(paragraphs) == ['1.', '2.']


def test_CNT_7():
    "CNT-7: an unnumbered section heading restarts the numbered items"
    head = dict(counter='section')
    paragraphs, state = generate(doc(par('a', **numbered()),
                                     par('b', **numbered()),
                                     par('Heading', **head),
                                     par('c', **numbered())))
    assert markers(paragraphs) == ['1.', '2.', None, '1.']


# ---------------------------------------------------------------------
# LEVEL - the paragraph's level: free (NL indent) or fixed_indent
# ---------------------------------------------------------------------

def par_at(level, *items, **kw):
    """A paragraph (see par) on free level level (its NewLine's indent)."""
    p = par(*items, **kw)
    p[-1] = p[-1].set_indent(level)
    return p


def test_LEVEL_1():
    "LEVEL-1: the free level selects indent_levels, for all lines"
    texel = doc(par_at(2, 'aaa bbb ccc ddd', indent_levels=LEVELS))
    records = flat(generate(texel, width=16)[0])
    assert len(records) > 1
    assert all(r[0].start[0] == 8 for r in records)


def test_LEVEL_2():
    "LEVEL-2: fixed_indent wins over the free level"
    texel = doc(par_at(2, 'ab', fixed_indent=1, indent_levels=LEVELS))
    assert flat(generate(texel)[0])[0][0].start[0] == 4


def test_LEVEL_3():
    "LEVEL-3: markers and counters follow the free level"
    for kind in (dict(paragraph_type='numbered'),
                 dict(paragraph_type='list')):
        levels = [0, 1, 1, 0]
        free = doc(*[par_at(k, 'x', **kind) for k in levels])
        fixed = doc(*[par('x', fixed_indent=k, **kind) for k in levels])
        p_free, _ = generate(free)
        p_fixed, _ = generate(fixed)
        assert markers(p_free) == markers(p_fixed)
        assert [p[0][0].offset for p in p_free] == \
            [p[0][0].offset for p in p_fixed]
    assert markers(p_free)[0] != markers(p_free)[1]  # list: per level


def test_LEVEL_4():
    "LEVEL-4: blocks and their decoration follow the free level"
    red = dict(block_color='red', indent_levels=LEVELS)
    texel = doc(par_at(0, 'a', **red), par_at(1, 'b', **red))
    records = flat(generate(texel, width=20)[0])
    assert [r[4] for r in records] == [True, True]  # two blocks
    data, height, shadings, borders = stack(records, 20)
    assert [x for x, *_ in shadings] == [0, 4]


# ---------------------------------------------------------------------
# FN - Footnotes
# ---------------------------------------------------------------------

def test_FN_1():
    "FN-1: the anchor is a FootnoteAnchorBox of length 1, label = counter"
    paragraphs, state = generate(doc(par('a', fn('x'), 'b', fn('y'))))
    anchors = find_boxes(paragraphs, FootnoteAnchorBox)
    assert [len(a) for a in anchors] == [1, 1]
    assert [a.display for a in anchors] == ['1', '2']
    assert state.footnote_counter == 2


def test_FN_2():
    "FN-2: an explicit label replaces the number"
    paragraphs, state = generate(doc(par('a', fn('x').set_label('*'))))
    anchors = find_boxes(paragraphs, FootnoteAnchorBox)
    assert [a.display for a in anchors] == ['*']
    assert state.footnotes[0][0].marker == '*'


def test_FN_3():
    "FN-3: footnote content lands in state.footnotes, wrapped narrower"
    text = 'aaa bbb ccc ddd eee fff ggg hhh'
    paragraphs, state = generate(doc(par('a', fn(text))), width=30)
    indent = max(MIN_LABEL_INDENT, 1 + LABEL_GAP)
    rows = [r[0] for r in state.footnotes]
    assert len(rows) > 1
    assert ''.join(row_text(row) for row in rows).strip() == text
    for row in rows:
        assert row.start[0] + row.width <= 30 - indent
    assert rows[0].marker == '1'
    assert rows[0].offset == -(1 + LABEL_GAP)


def test_FN_4():
    "FN-4: several footnotes stay in document order"
    texel = doc(par('a', fn('one'), 'b', fn('two')),
                par('c', fn('three')))
    paragraphs, state = generate(texel)
    assert [row_text(r[0]).strip() for r in state.footnotes] == \
        ['one', 'two', 'three']


def test_FN_5():
    "FN-5: nested footnotes in order F1, F2, F3 with rising numbers"
    f3 = fn('three')
    f2 = fn('two', f3)
    f1 = fn('one', f2)
    paragraphs, state = generate(doc(par('a', f1, 'b', fn('four'))))
    texts = [row_text(r[0]).strip() for r in state.footnotes]
    assert texts == ['one[2]', 'two[3]', 'three', 'four'], texts
    assert [r[0].marker for r in state.footnotes] == ['1', '2', '3', '4']


def test_FN_6():
    "FN-6: a footnote in a table cell reaches the parent's state"
    table = Table([Group(par('cell', fn('in cell'), endmark=True)),
                   Group(par('x', endmark=True))], ncols=2)
    texel = doc(par('before', fn('one')), par(table),
                par('after', fn('three')))
    paragraphs, state = generate(texel, width=100)
    assert [row_text(r[0]).strip() for r in state.footnotes] == \
        ['one', 'in cell', 'three']
    assert [r[0].marker for r in state.footnotes] == ['1', '2', '3']


def test_FN_7():
    "FN-7: the footnote flow matches footnotes.iter_footnotes"
    from ..footnotes.footnotes import iter_footnotes
    from ..textmodel.texeltree import get_text
    f3 = fn('three')
    f2 = fn('two', f3)
    f1 = fn('one', f2, ' more')
    cell = Group(par('cell', fn('in cell'), endmark=True))
    table = Table([cell, Group(par('x', endmark=True))], ncols=2)
    texel = doc(par('a', f1, 'b', fn('four')), par(table),
                par('c', fn('five'), endmark=True))
    paragraphs, state = generate(texel, width=60)
    flow = [record[0] for record in state.footnotes]
    expected = list(iter_footnotes(texel))
    assert sum(len(row) for row in flow) == \
        sum(length(chain[-1][1].content) for _, chain, _ in expected)
    # every footnote starts with a labelled row at its offset
    starts, i = [], 0
    for row in flow:
        if row.marker is not None:
            starts.append(i)
        i += len(row)
    assert starts == [offset for offset, _, _ in expected]


# ---------------------------------------------------------------------
# TAB - Tables
# ---------------------------------------------------------------------

def test_TAB_1():
    "TAB-1: every cell wraps at col_width"
    text = 'aaa bbb ccc ddd eee'
    table = Table([Group(par(text, endmark=True)),
                   Group(par(text, endmark=True))], ncols=2)
    paragraphs, state = generate(doc(par(table)), width=20)
    tablebox = find_boxes(paragraphs, TableBox)[0]
    for cell in tablebox.cells:
        rows = list(iter_rows(cell))
        assert len(rows) > 1
        for row in rows:
            assert row.start[0] + row.width <= 10, row_text(row)


def test_TAB_2():
    "TAB-2: footnotes and their counter flow back from cells, counters don't"
    cell = Group(par('c', fn('in cell'), **numbered())
                 + par('d', endmark=True, **numbered()))
    table = Table([cell, Group(par('x', endmark=True))], ncols=2)
    texel = doc(par('a', fn('one'), **numbered()), par(table),
                par('b', fn('two'), **numbered()))
    paragraphs, state = generate(texel, width=100)
    assert markers(paragraphs)[0] == '1.'
    assert markers(paragraphs)[2] == '2.'
    assert state.footnote_counter == 3
    assert [r[0].marker for r in state.footnotes] == ['1', '2', '3']


def test_TAB_3():
    "TAB-3: a table mid-document has the right length"
    table = Table([Group(par('a', endmark=True)),
                   Group(par('b', endmark=True))], ncols=2)
    texel = doc(par('before'), par(table), par('after'))
    paragraphs, state = generate(texel, width=40)
    spans = list(iter_paragraphs(texel, 0))
    for (i1, i2, _), records in zip(spans, paragraphs):
        assert sum(len(r[0]) for r in records) == i2 - i1, (i1, i2)
    assert row_text(paragraphs[2][0][0]) == 'after'


# ---------------------------------------------------------------------
# STATE - State
# ---------------------------------------------------------------------

def test_STATE_1():
    "STATE-1: copy() is independent of the original"
    state = State(20)
    state.rows.append('r')
    state.footnotes.append('f')
    state.floats.append('x')
    state.counters['item'] = [1] * n_levels
    clone = state.copy()
    clone.rows.append('r2')
    clone.footnotes.append('f2')
    clone.floats.append('x2')
    clone.counters['item'][0] = 99
    clone.counters['section'] = [5] * n_levels
    assert state.rows == ['r']
    assert state.footnotes == ['f']
    assert state.floats == ['x']
    assert state.counters == {'item': [1] * n_levels}


def test_STATE_2():
    "STATE-2: create_child doesn't change the parent's width"
    factory = RowFactory(State(20), testsheet, TESTDEVICE)
    child = factory.create_child(7)
    assert child.state.width == 7
    assert factory.state.width == 20


def test_STATE_3():
    "STATE-3: children start with empty buffers, update_from_child appends"
    state = State(20)
    state.footnotes.append('a')
    state.floats.append('fa')
    state.counters['item'] = [1] + [0] * (n_levels - 1)
    factory = RowFactory(state, testsheet, TESTDEVICE)
    child = factory.create_child(10)
    assert child.state.footnotes == [] and child.state.floats == []
    child.state.footnotes.append('b')
    child.state.floats.append('fb')
    child.state.footnote_counter = 7
    child.state.counters['item'][0] = 42
    factory.update_from_child(child)
    assert state.footnotes == ['a', 'b']
    assert state.floats == ['fa', 'fb']
    assert state.footnote_counter == 7
    assert state.counters['item'][0] == 1


def test_STATE_4():
    "STATE-4: state_from_settings takes paper size and margins"
    from ..core.units import mm, cm
    state = state_from_settings({})
    assert state.geometry == (210 * mm, 297 * mm)
    assert state.border == (2.5 * cm,) * 4
    assert abs(state.width - (210 * mm - 5 * cm)) < 1e-9
    assert state.rows == [] and state.counters == {}

    state = state_from_settings({'paper': 'custom', 'paper_width': 100,
                                 'paper_height': 200, 'margin_left': 10,
                                 'margin_right': 20, 'margin_top': 5,
                                 'margin_bottom': 6})
    assert state.geometry == (100, 200)
    assert state.border == (5, 20, 6, 10)
    assert state.width == 70


# ---------------------------------------------------------------------
# STACK - RowStack
# ---------------------------------------------------------------------

def ys(data):
    return [y for _, y, _ in data]


def test_STACK_1():
    "STACK-1: without max_height everything is taken"
    buffer = mk_records((2, ps()), (3, ps()))
    data, height, shadings, borders = stack(buffer, 10)
    assert len(data) == 5 and buffer == []
    assert height == 5


def test_STACK_2():
    "STACK-2: with max_height exactly the fitting records are taken"
    buffer = mk_records((5, ps()))
    rest = buffer[3:]
    data, height, shadings, borders = stack(buffer, 10, 3)
    assert len(data) == 3 and height == 3
    assert buffer == rest


def test_STACK_3():
    "STACK-3: at least one record is always taken"
    buffer = mk_records((2, ps()))
    buffer[0][0].height = 10
    data, height, shadings, borders = stack(buffer, 10, 3)
    assert len(data) == 1 and height == 10
    assert len(buffer) == 1


def test_STACK_4():
    "STACK-4: space_before/space_after only between paragraphs"
    style = ps(space_before=2, space_after=3)
    buffer = mk_records((1, style), (1, style))
    data, height, shadings, borders = stack(buffer, 10)
    assert ys(data) == [0, 1 + 3 + 2]
    assert height == 7


def test_STACK_5():
    "STACK-5: block_offset is reserved above and below, not sideways"
    buffer = mk_records((1, ps(block_color='red', block_offset=2)))
    data, height, shadings, borders = stack(buffer, 10)
    assert ys(data) == [2]
    assert height == 5
    assert shadings == [(-2, 0, 14, 5, 'red')]


def test_STACK_6():
    "STACK-6: consecutive paragraphs of the same block give one rect"
    style = ps(block_color='red', block_offset=1)
    buffer = mk_records((1, style), (1, style))
    data, height, shadings, borders = stack(buffer, 10)
    assert ys(data) == [1, 2]
    assert shadings == [(-1, 0, 12, 4, 'red')]


def test_STACK_7():
    "STACK-7: different blocks give separate rects"
    buffer = mk_records((1, ps(block_color='red')),
                        (1, ps(block_color='blue')))
    data, height, shadings, borders = stack(buffer, 10)
    assert shadings == [(0, 0, 10, 1, 'red'), (0, 1, 10, 1, 'blue')]


def test_STACK_8():
    "STACK-8: no rect without color and border width"
    buffer = mk_records((2, ps(block_offset=1)))
    data, height, shadings, borders = stack(buffer, 10)
    assert shadings == [] and borders == []

    buffer = mk_records((2, ps(block_border_width=1)))
    data, height, shadings, borders = stack(buffer, 10)
    assert shadings == []
    assert borders == [(-1, 0, 12, 4, ('black', 1, 'tblr'))]


def test_STACK_9():
    "STACK-9: a block cut off by max_height closes at the last placed row"
    buffer = mk_records((4, ps(block_color='red', block_offset=1)))
    data, height, shadings, borders = stack(buffer, 10, 3)
    assert ys(data) == [1, 2]
    assert shadings == [(-1, 0, 12, 3, 'red')]
    assert len(buffer) == 2


def test_STACK_10():
    "STACK-10: a stack starting mid-block has no top offset"
    buffer = mk_records((4, ps(block_color='red', block_offset=1)))
    stack(buffer, 10, 3)  # takes the first two rows
    data, height, shadings, borders = stack(buffer, 10)
    assert ys(data) == [0, 1]
    assert shadings == [(-1, 0, 12, 3, 'red')]  # bottom offset only


def test_STACK_11():
    "STACK-11: typeset_into_rect gives a RowsBox and leaves records alone"
    # its decorations are cut at the sides (see BLOCK-9)
    style = ps(block_color='red', block_offset=1, space_after=2,
               block_border_width=1)
    records = mk_records((2, style), (1, ps()))
    expected = stack(list(records), 10)
    box = typeset_into_rect(records, 10, TESTDEVICE)
    assert isinstance(box, RowsBox)
    assert len(records) == 3
    assert box.data == expected[0]
    assert box.height == expected[1]
    assert box.shadings == clip_x(expected[2], 10)
    assert box.borders == clip_x(expected[3], 10)
    assert box.shadings[0][0] == 0 and box.shadings[0][2] == 10


def test_STACK_12():
    "STACK-12: continuing a stack equals stacking at once"
    style = ps(block_color='red', block_offset=1, space_before=2,
               space_after=3)
    records = mk_records((2, style), (1, style), (2, ps()), (1, style))
    expected = stack(list(records), 10)
    rowstack = RowStack(10)
    for k in range(len(records)):
        rowstack.take([records[k]])
    assert (rowstack.data(), rowstack.height) + rowstack.decorations() \
        == expected


def test_STACK_13():
    "STACK-13: with force=False nothing oversized is taken"
    buffer = mk_records((1, ps()))
    rowstack = RowStack(10)
    rowstack.take(buffer, 0.5, force=False)
    assert rowstack.placed == [] and len(buffer) == 1


# ---------------------------------------------------------------------
# BLOCK - right indent, block offset and border lines
# (develnotes/padding_concept.md: the text stays at its indents, the
# decoration grows outward)
# ---------------------------------------------------------------------

def test_BLOCK_1():
    "BLOCK-1: right_indent narrows the lines and moves right alignment"
    text = 'aaa bbb ccc ddd eee fff ggg'
    records = flat(generate(doc(par(text, right_indent=2)), width=10)[0])
    assert len(records) > 1
    for row, *_ in records:
        assert row.start[0] + row.width <= 8, row_text(row)
    records = flat(generate(doc(par('ab', right_indent=2,
                                    alignment='right')), width=10)[0])
    assert records[0][0].start[0] == 6


def test_BLOCK_2():
    "BLOCK-2: the block offset doesn't change the line breaks"
    text = 'aaa bbb ccc ddd eee fff ggg'
    plain = flat(generate(doc(par(text)), width=10)[0])
    boxed = flat(generate(doc(par(text, block_color='red', block_offset=3,
                                  block_border_width=1)), width=10)[0])
    assert [(row_text(r[0]), r[0].start) for r in boxed] == \
        [(row_text(r[0]), r[0].start) for r in plain]


def test_BLOCK_3():
    "BLOCK-3: the border line lies outside the offset, also vertically"
    style = ps(block_color='red', block_offset=1, block_border_width=1,
               block_border_color='blue')
    buffer = mk_records((1, style))
    data, height, shadings, borders = stack(buffer, 10)
    assert ys(data) == [2]
    assert height == 5
    assert shadings == [(-1, 1, 12, 3, 'red')]
    assert borders == [(-2, 0, 14, 5, ('blue', 1, 'tblr'))]


def test_BLOCK_4():
    "BLOCK-4: block_border_sides selects the lines; space stays the same"
    style = ps(block_border_width=1, block_border_sides='tb')
    data, height, shadings, borders = stack(mk_records((1, style)), 10)
    assert ys(data) == [1] and height == 3
    assert borders == [(-1, 0, 12, 3, ('black', 1, 'tb'))]


def test_BLOCK_5():
    "BLOCK-5: the decoration follows the paragraph's indents"
    style = ps(block_color='red', level=1, indent_levels=LEVELS,
               right_indent=2)
    data, height, shadings, borders = stack(mk_records((1, style)), 20)
    assert shadings == [(4, 0, 14, 1, 'red')]
    style = dict(style, block_offset=1)
    data, height, shadings, borders = stack(mk_records((1, style)), 20)
    assert shadings == [(3, 0, 16, 3, 'red')]


def test_BLOCK_6():
    "BLOCK-6: a hanging first line and list markers lie inside"
    style = ps(block_color='red', level=1, indent_levels=LEVELS,
               first_line_indent=-2)
    data, height, shadings, borders = stack(mk_records((1, style)), 20)
    assert shadings == [(2, 0, 18, 1, 'red')]
    style = ps(block_color='red', paragraph_type='list', level=1,
               indent_levels=LEVELS, list_indent=3)
    data, height, shadings, borders = stack(mk_records((1, style)), 20)
    assert shadings == [(4, 0, 16, 1, 'red')]  # without list_indent


def test_BLOCK_7():
    "BLOCK-7: paragraphs with different indents are separate blocks"
    red = ps(block_color='red', block_offset=1)
    indented = dict(red, right_indent=2)
    data, height, shadings, borders = stack(
        mk_records((1, red), (1, indented)), 10)
    assert ys(data) == [1, 4]
    assert shadings == [(-1, 0, 12, 3, 'red'), (-1, 3, 10, 3, 'red')]


def test_BLOCK_8():
    "BLOCK-8: on the page the decoration reaches into the margin"
    texel = doc(par('aaa', block_color='red', block_offset=1,
                    block_border_width=1), par('plain'))
    memo = small_memo(width=20, height=10)
    memo.border = (2, 1, 1, 3)
    memo.geometry = (24, 13)
    page = pages_from(texel, memo)[0]
    assert page.shadings == [(2, 3, 22, 3, 'red')]
    assert page.borders == [(1, 2, 24, 5, ('black', 1, 'tblr'))]
    assert page.rows[0][:2] == (3, 4)


def test_BLOCK_9():
    "BLOCK-9: a table cell's decoration stays inside the cell"
    cell = Group([Text('ab'), nl(block_color='red', block_offset=5),
                  Text('c'), nl()])  # Table drops the last nl's style
    texel = Group([Table([cell], 1), nl()])
    paragraphs, state = generate(texel, width=10)
    cellbox = find_boxes(paragraphs, TableBox)[0].cells[0][0]
    dx, dy = cellbox.offset  # the cell padding
    content = cellbox.data[0][2]
    assert len(content.shadings) == 1
    x, y, w, h, color = content.shadings[0]
    assert dx + x >= 0 and dx + x + w <= cellbox.width
    assert dy + y >= 0 and dy + y + h <= cellbox.height


# ---------------------------------------------------------------------
# PAGE - generate_pages
# ---------------------------------------------------------------------

def body_bottom(page):
    return max((y + row.height + row.depth for _, y, row in page.rows),
               default=0)


def test_PAGE_1():
    "PAGE-1: a document of just ENDMARK gives exactly one page"
    pages = pages_from(doc([nl(endmark=True)]), small_memo())
    assert len(pages) == 1
    assert len(pages[0].rows) == 1 and pages[0].footnotebox is None


def test_PAGE_2():
    "PAGE-2: nothing is lost or set twice"
    texel = long_doc()
    pages = pages_from(texel, small_memo())
    assert sum(len(p) for p in pages) == length(texel)
    paragraphs, state = generate(texel, width=20)
    assert [row_text(r) for p in pages for _, _, r in p.rows] == \
        [row_text(r[0]) for r in flat(paragraphs)]
    assert [row_text(r) for p in pages for r in footnote_rows(p)] == \
        [row_text(r[0]) for r in state.footnotes]


def test_PAGE_3():
    "PAGE-3: no page exceeds the available height"
    memo = small_memo(height=5)
    for page in pages_from(long_doc(), memo):
        if len(page.rows) > 1:
            assert body_bottom(page) <= 1 + 5
        if page.footnotebox is not None:
            x, y, box = page.footnotebox
            assert y + box.height <= 1 + 5


def test_PAGE_4():
    "PAGE-4: the footnote area takes at most FOOTNOTE_FRACTION of the page"
    notes = [fn('note %d' % k) for k in range(8)]
    texel = doc(par('text ', *notes), *[par('more text') for k in range(40)])
    memo = small_memo(height=20)
    pages = pages_from(texel, memo)
    checked = 0
    for page in pages:
        rows = footnote_rows(page)
        if page.rows and len(rows) > 1:
            assert page.footnotebox[2].height <= FOOTNOTE_FRACTION * 20
            checked += 1
    assert checked  # the condition above must actually occur


def test_PAGE_5():
    "PAGE-5: footnotes that don't fit move on, in order"
    notes = [fn('note %d' % k) for k in range(8)]
    texel = doc(par('text ', *notes), *[par('more text') for k in range(40)])
    pages = pages_from(texel, small_memo(height=20))
    texts = [row_text(r).strip() for p in pages for r in footnote_rows(p)]
    assert texts == ['note %d' % k for k in range(8)]
    assert len([p for p in pages if footnote_rows(p)]) > 1


def test_PAGE_6():
    "PAGE-6: footnote-only pages have no separator and start at the top"
    notes = [fn('note %d' % k) for k in range(30)]
    pages = pages_from(doc(par('text ', *notes)), small_memo(height=5))
    fn_only = [p for p in pages if not p.rows and p.footnotebox]
    assert fn_only
    for page in fn_only:
        x, y, box = page.footnotebox
        assert not box.draw_separator
        assert y == 1


def test_PAGE_7():
    "PAGE-7: an oversized footnote is still placed"
    words = ' '.join('w%d' % k for k in range(60))
    texel = doc(par('text ', fn(words)), par('after'))
    pages = pages_from(texel, small_memo(height=5))
    placed = ''.join(row_text(r) for p in pages for r in footnote_rows(p))
    assert placed.strip() == words


def test_PAGE_8():
    "PAGE-8: rows and decorations are shifted by the border"
    texel = doc(par('aaa bbb ccc', block_color='red'), par('plain'))
    memo = small_memo(width=20, height=10)
    memo.border = (2, 1, 1, 3)
    memo.geometry = (24, 13)
    page = pages_from(texel, memo)[0]
    assert len(page.shadings) == 1
    x, y, w, h, color = page.shadings[0]
    assert x == 3 and y == 2 and color == 'red'
    assert all(rx == 3 for rx, _, _ in page.rows)  # left border
    assert all(ry >= 2 for _, ry, _ in page.rows)  # top border
    red_rows = [(ry, row) for _, ry, row in page.rows
                if row_text(row) != 'plain']
    for ry, row in red_rows:
        assert y <= ry and ry + row.height <= y + h


def lines(name, n):
    """Items for a paragraph of exactly n rows name0, name1, ..."""
    items = []
    for k in range(n):
        items += [BR(), name + str(k)] if k else [name + '0']
    return items


def test_PAGE_9():
    "PAGE-9: no other paragraph's text between a footnote and its text"
    # Page 20 high, footnotes may take 2. After A (12 rows) B's
    # footnote still fits, B itself (space_before 2) doesn't: B's
    # footnote comes first - allowed, nothing in between. C must not
    # put its footnote on that page as well: B's text would be in
    # between.
    texel = doc(par(*lines('a', 12)),
                par(*lines('b', 3) + [fn('note b')], space_before=2),
                par(*lines('c', 6) + [fn('note c')]),
                *[par(*lines('d%d_' % k, 4)) for k in range(6)])
    pages = pages_from(texel, small_memo(width=30, height=20))
    order = []  # reading order: body rows of a page, then its footnotes
    for p in pages:
        order += [('row', row_text(r)) for _, _, r in p.rows]
        order += [('note', row_text(r).strip()) for r in footnote_rows(p)]
    early = 0
    for name in 'bc':
        note = order.index(('note', 'note ' + name))
        first = order.index(('row', name + '0'))
        if note < first:
            early += 1
            between = [text for kind, text in order[note:first]
                       if kind == 'row']
            assert between == [], (name, between)
    assert early  # the situation must actually occur


def test_PAGE_10():
    "PAGE-10: page_break_before starts a new page, but not an empty one"
    def body(pages):
        return [[row_text(r) for _, _, r in p.rows] for p in pages]
    memo = small_memo(height=20)

    pages = pages_from(doc(par('a'), par('b', page_break_before=True),
                           par('c')), memo)
    assert body(pages) == [['a'], ['b', 'c']]

    # at the very top, and twice in a row: no empty pages
    pages = pages_from(doc(par('a', page_break_before=True),
                           par('b', page_break_before=True),
                           par('c', page_break_before=True)), memo)
    assert body(pages) == [['a'], ['b'], ['c']]

    # the paragraph's footnote goes with it
    pages = pages_from(doc(par('a'), par('b', fn('note b'),
                                         page_break_before=True)), memo)
    assert body(pages) == [['a'], ['b[1]']]
    assert footnote_rows(pages[0]) == []
    assert [row_text(r).strip() for r in footnote_rows(pages[1])] == \
        ['note b']

    # restarting from the first page gives the same
    texel = doc(par('a'), par('b', page_break_before=True), par('c'))
    pages = pages_from(texel, memo)
    again = pages_from(texel, pages[0].restartmemo, len(pages[0]))
    assert [page_sig(p) for p in again] == [page_sig(p) for p in pages[1:]]


# ---------------------------------------------------------------------
# ORPH - orphans and widows
# ---------------------------------------------------------------------

def page_lines(texel, height, width=20):
    """Body row texts per page, for a page height rows high."""
    pages = pages_from(texel, small_memo(width=width, height=height))
    return [[row_text(row) for _, _, row in page.rows] for page in pages]


def test_ORPH_1():
    "ORPH-1: a paragraph's first line alone at the page bottom moves on"
    texel = doc(par(*lines('a', 4)), par(*lines('b', 3)))
    assert page_lines(texel, 5) == [['a0', 'a1', 'a2', 'a3'],
                                    ['b0', 'b1', 'b2']]


def test_ORPH_2():
    "ORPH-2: a paragraph's last line alone at the page top takes one along"
    texel = doc(par(*lines('a', 2)), par(*lines('b', 4)))
    assert page_lines(texel, 5) == [['a0', 'a1', 'b0', 'b1'],
                                    ['b2', 'b3']]


def test_ORPH_3():
    "ORPH-3: switched off, a paragraph breaks at any line"
    off = dict(widow_orphan_control=False)
    texel = doc(par(*lines('a', 4)), par(*lines('b', 3), **off))
    assert page_lines(texel, 5) == [['a0', 'a1', 'a2', 'a3', 'b0'],
                                    ['b1', 'b2']]
    texel = doc(par(*lines('a', 2)), par(*lines('b', 4), **off))
    assert page_lines(texel, 5) == [['a0', 'a1', 'b0', 'b1', 'b2'],
                                    ['b3']]


def test_ORPH_4():
    "ORPH-4: a two-line paragraph is not split at all"
    texel = doc(par(*lines('a', 4)), par(*lines('b', 2)))
    assert page_lines(texel, 5) == [['a0', 'a1', 'a2', 'a3'],
                                    ['b0', 'b1']]


def test_ORPH_5():
    "ORPH-5: a three-line paragraph that can't keep two lines each moves"
    texel = doc(par(*lines('a', 3)), par(*lines('b', 3)))
    assert page_lines(texel, 5) == [['a0', 'a1', 'a2'],
                                    ['b0', 'b1', 'b2']]


def test_ORPH_6():
    "ORPH-6: within one long paragraph the last page gets two lines"
    texel = doc(par(*lines('a', 6)))
    assert page_lines(texel, 5) == [['a0', 'a1', 'a2', 'a3'],
                                    ['a4', 'a5']]


def test_ORPH_6b():
    "ORPH-6b: a paragraph over three pages; the middle page is all of it"
    texel = doc(par(*lines('a', 2)), par(*lines('b', 7)))
    pages = page_lines(texel, 3)
    assert sum(pages, []) == ['a0', 'a1'] + ['b%d' % k for k in range(7)]
    assert all(len([t for t in p if t.startswith('b')]) != 1
               for p in pages)


def test_ORPH_7():
    "ORPH-7: never an empty page - one-line pages stay as they are"
    texel = doc(par(*lines('a', 3)))
    assert page_lines(texel, 1) == [['a0'], ['a1'], ['a2']]
    texel = doc(par(*lines('a', 3)), par(*lines('b', 2)))
    pages = page_lines(texel, 2)
    assert sum(pages, []) == ['a0', 'a1', 'a2', 'b0', 'b1']
    assert all(pages)


def test_ORPH_8():
    "ORPH-8: restarting from every page reproduces the pages"
    texel = doc(*[par(*lines('p%d_' % k, 2 + k % 4)) for k in range(12)])
    pages = pages_from(texel, small_memo(width=20, height=5))
    starts = page_starts(pages)
    for k in range(len(pages) - 1):
        again = pages_from(texel, pages[k].restartmemo, starts[k + 1])
        assert [page_sig(p) for p in again] == \
            [page_sig(p) for p in pages[k + 1:]], k
    for page in pages:  # and no first line alone at a page bottom
        texts = [row_text(r) for _, _, r in page.rows]
        assert not (len(texts) > 1 and texts[-1].endswith('_0'))


# ---------------------------------------------------------------------
# KEEP - keep_with_next
# ---------------------------------------------------------------------

KEEP = dict(keep_with_next=True)


def test_KEEP_1():
    "KEEP-1: a paragraph with keep_with_next moves on with the next one"
    texel = doc(par(*lines('a', 4)), par('H', **KEEP), par(*lines('b', 3)))
    assert page_lines(texel, 5) == [['a0', 'a1', 'a2', 'a3'],
                                    ['H', 'b0', 'b1', 'b2']]


def test_KEEP_2():
    "KEEP-2: several such paragraphs in a row move together"
    texel = doc(par(*lines('a', 3)), par('H', **KEEP), par('I', **KEEP),
                par(*lines('b', 3)))
    assert page_lines(texel, 5) == [['a0', 'a1', 'a2'],
                                    ['H', 'I', 'b0', 'b1', 'b2']]


def test_KEEP_3():
    "KEEP-3: never an empty page"
    texel = doc(par('H', **KEEP), par('I', **KEEP), par(*lines('b', 3)))
    pages = page_lines(texel, 2)
    assert pages[0] == ['H', 'I']
    assert sum(pages, []) == ['H', 'I', 'b0', 'b1', 'b2']


def test_KEEP_4():
    "KEEP-4: off by default; a break within the next paragraph is kept"
    texel = doc(par(*lines('a', 4)), par('H'), par(*lines('b', 3)))
    assert page_lines(texel, 5)[0] == ['a0', 'a1', 'a2', 'a3', 'H']
    # the next paragraph starts on the page: H stays with it
    texel = doc(par(*lines('a', 2)), par('H', **KEEP), par(*lines('b', 4)))
    assert page_lines(texel, 5) == [['a0', 'a1', 'H', 'b0', 'b1'],
                                    ['b2', 'b3']]


def test_KEEP_5():
    "KEEP-5: restarting from every page reproduces the pages"
    texel = doc(*[p for k in range(8) for p in
                  (par('H%d' % k, **KEEP), par(*lines('p%d_' % k, 2 + k % 3)))])
    pages = pages_from(texel, small_memo(width=20, height=5))
    starts = page_starts(pages)
    for k in range(len(pages) - 1):
        again = pages_from(texel, pages[k].restartmemo, starts[k + 1])
        assert [page_sig(p) for p in again] == \
            [page_sig(p) for p in pages[k + 1:]], k
    for page in pages:  # no heading alone at a page bottom
        texts = [row_text(r) for _, _, r in page.rows]
        assert not (len(texts) > 1 and texts[-1].startswith('H')), texts


# ---------------------------------------------------------------------
# RESTART - pages from a memo
# ---------------------------------------------------------------------

def test_RESTART_1():
    "RESTART-1: restarting from every page reproduces the following pages"
    texel = long_doc()
    pages = pages_from(texel, small_memo())
    assert len(pages) > 3
    starts = page_starts(pages)
    for k in range(len(pages) - 1):
        again = pages_from(texel, pages[k].restartmemo, starts[k + 1])
        assert [page_sig(p) for p in again] == \
            [page_sig(p) for p in pages[k + 1:]], k


def test_RESTART_2():
    "RESTART-2: text inserted before a page - old memo, i1 + n"
    old = long_doc()
    new = long_doc(prefix='inserted ')
    n = len('inserted ')
    pages = pages_from(old, small_memo())
    starts = page_starts(pages)
    for k in range(1, len(pages) - 1):
        again = pages_from(new, pages[k].restartmemo, starts[k + 1] + n)
        assert [page_sig(p) for p in again] == \
            [page_sig(p) for p in pages[k + 1:]], k


def test_RESTART_3():
    "RESTART-3: text deleted before a page - old memo, i1 - n"
    old = long_doc(prefix='deleted ')
    new = long_doc()
    n = len('deleted ')
    pages = pages_from(old, small_memo())
    starts = page_starts(pages)
    for k in range(1, len(pages) - 1):
        again = pages_from(new, pages[k].restartmemo, starts[k + 1] - n)
        assert [page_sig(p) for p in again] == \
            [page_sig(p) for p in pages[k + 1:]], k


def test_RESTART_4():
    "RESTART-4: a change behind the memo's range matches a full rebuild"
    old = long_doc(n=20)
    new = long_doc(n=20, last_text='changed text at the end ')
    pages = pages_from(old, small_memo())
    starts = page_starts(pages)
    memo = pages[0].restartmemo
    covered = starts[1] + sum(len(r[0]) for r in memo.rows)
    changed_at = length(old) - len(par('x')) - 40
    assert changed_at > covered  # the test is only valid then
    again = pages_from(new, memo, starts[1])
    full = pages_from(new, small_memo())
    assert [page_sig(p) for p in again] == [page_sig(p) for p in full[1:]]


def first_page(pages, condition):
    for k, page in enumerate(pages[:-1]):
        if condition(page.restartmemo):
            return k
    assert False, 'no page with the required memo'


def restart_matches(texel, pages, k):
    starts = page_starts(pages)
    again = pages_from(texel, pages[k].restartmemo, starts[k + 1])
    return [page_sig(p) for p in again] == \
        [page_sig(p) for p in pages[k + 1:]]


def test_RESTART_5():
    "RESTART-5: restart with a partial paragraph in memo.rows"
    texel = long_doc()
    pages = pages_from(texel, small_memo())
    k = first_page(pages, lambda m: m.rows and not m.rows[0][2])
    assert restart_matches(texel, pages, k)


def test_RESTART_6():
    "RESTART-6: restart with footnotes still waiting in memo.footnotes"
    notes = [fn('note %d' % k) for k in range(8)]
    texel = doc(par('text ', *notes), *[par('more text') for k in range(40)])
    pages = pages_from(texel, small_memo(height=20))
    k = first_page(pages, lambda m: m.footnotes)
    assert restart_matches(texel, pages, k)


def numbered_doc():
    return doc(*[par('item %d with some words' % k, **numbered())
                 for k in range(12)])


def test_RESTART_7():
    "RESTART-7: restart continues the numbering"
    texel = numbered_doc()
    pages = pages_from(texel, small_memo())
    k = first_page(pages, lambda m: m.counters.get('item', [0])[0] > 0)
    starts = page_starts(pages)
    again = pages_from(texel, pages[k].restartmemo, starts[k + 1])
    def marks(pages):
        return [row.marker for p in pages for _, _, row in p.rows]
    assert marks(again) == marks(pages[k + 1:])
    assert any(m for m in marks(again))


def test_RESTART_8():
    "RESTART-8: starting from a fresh State is a start from scratch"
    texel = long_doc()
    memo = small_memo()
    before = state_sig(memo)
    first = pages_from(texel, memo)
    second = pages_from(texel, memo)
    assert [page_sig(p) for p in first] == [page_sig(p) for p in second]
    assert state_sig(memo) == before


def test_RESTART_9():
    "RESTART-9: restarting from the last page's memo yields no page"
    for texel in (doc([nl(endmark=True)]), long_doc()):
        pages = pages_from(texel, small_memo())
        end = sum(len(p) for p in pages)
        assert pages_from(texel, pages[-1].restartmemo, end) == []


# ---------------------------------------------------------------------
# MEMO - Memos
# ---------------------------------------------------------------------

def test_MEMO_1():
    "MEMO-1: restarting reproduces the following pages' memos"
    texel = long_doc()
    pages = pages_from(texel, small_memo())
    starts = page_starts(pages)
    for k in range(len(pages) - 1):
        again = pages_from(texel, pages[k].restartmemo, starts[k + 1])
        for a, b in zip(again, pages[k + 1:]):
            assert same_state(a.restartmemo, b.restartmemo), k


def test_MEMO_2():
    "MEMO-2: after inserting before a page, the end memos are the same"
    old = long_doc()
    new = long_doc(prefix='inserted ')
    n = len('inserted ')
    pages = pages_from(old, small_memo())
    starts = page_starts(pages)
    for k in range(1, len(pages) - 1):
        again = pages_from(new, pages[k].restartmemo, starts[k + 1] + n)
        for a, b in zip(again, pages[k + 1:]):
            assert same_state(a.restartmemo, b.restartmemo), k


def test_MEMO_3():
    "MEMO-3: memos with partial paragraph, footnotes, counters"
    notes = [fn('note %d' % k) for k in range(6)]
    texel = doc(par('item with notes ', *notes, **numbered()),
                *[par('item %d with some words' % k, **numbered())
                  for k in range(30)])
    pages = pages_from(texel, small_memo(height=12))
    starts = page_starts(pages)
    for condition in (lambda m: m.rows and not m.rows[0][2],
                      lambda m: m.footnotes,
                      lambda m: m.counters.get('item', [0])[0] > 0):
        k = first_page(pages, condition)
        again = pages_from(texel, pages[k].restartmemo, starts[k + 1])
        for a, b in zip(again, pages[k + 1:]):
            assert same_state(a.restartmemo, b.restartmemo), k


def test_MEMO_4():
    "MEMO-4: a memo stays unchanged by restarts from it"
    texel = long_doc()
    pages = pages_from(texel, small_memo())
    starts = page_starts(pages)
    for k in range(len(pages) - 1):
        memo = pages[k].restartmemo
        before = state_sig(memo)
        pages_from(texel, memo, starts[k + 1])
        pages_from(texel, memo, starts[k + 1])
        assert state_sig(memo) == before, k
