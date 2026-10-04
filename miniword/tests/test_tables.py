# -*- coding: utf-8 -*-

"""
Tests for tables: building them (RowFactory.Table_handler), splitting
them across pages (RowStack.take), restarting, editing, saving. Follows
develnotes/tables_tests.md; each test's docstring starts with its ID.

Run with: python runtests.py miniword/tests/test_tables.py

A table texel's childs are [SEP, content, SEP, content, ..., SEP]; the
separator after a cell carries the cell's style in its parstyle.
TESTDEVICE measures every character 1 wide and every box 1 high.
"""

import os
import tempfile

import wx

from ..textmodel.textmodel import TextModel
from ..textmodel.texeltree import T, Group, grouped, NewLine, length, \
    iter_childs
from ..textmodel.submodel import Footnote, _get_text
from ..textmodel.texeltree import ENDMARK
from ..core.document import Document
from ..core.stylesheet import testsheet
from ..layout.testdevice import TESTDEVICE
from ..layout.rowfactory import State, RowFactory, Factory, generate_pages
from ..layout.boxes import Row, TextBox
from ..tables.tables import Table, from_strings
from ..tables.table_boxes import TableBox, CELL_HPAD, CELL_VPAD


# Helpers

def nl(**kw):
    return NewLine().set_parstyle(dict(base='normal', **kw))


def cell(*items):
    """Cell content: strings become Text; '\\n' separates paragraphs."""
    texels = []
    for item in items:
        if item == '\n':
            texels.append(nl())
        elif isinstance(item, str):
            texels.append(T(item))
        else:
            texels.append(item)
    return Group(texels) if texels else Group([])


def table(rows, styles=None, **kw):
    """Table from rows of cell contents (strings or cell(...))."""
    entries = []
    for r, row in enumerate(rows):
        for c, content in enumerate(row):
            if isinstance(content, str):
                content = cell(content)
            style = (styles or {}).get((r, c), {})
            entries.append((content, style))
    return Table(*entries, ncols=len(rows[0]), **kw)


def fnote(*items):
    return Footnote(grouped([T(i) if isinstance(i, str) else i
                             for i in items] + [ENDMARK]))


def doc_texel(*items):
    """A document texel: strings become Text, None a paragraph end."""
    texels = []
    for item in items:
        if item is None:
            texels.append(nl())
        elif isinstance(item, str):
            texels.append(T(item))
        else:
            texels.append(item)
    return grouped(texels)


def generate(texel, width=100):
    state = State(width)
    factory = RowFactory(state, testsheet, TESTDEVICE)
    return list(factory.generate(texel, 0)), state


def flat(paragraphs):
    return [record for par in paragraphs for record in par]


def table_boxes(paragraphs):
    return [box for record in flat(paragraphs) for box in record[0].childs
            if isinstance(box, TableBox)]


def box_of(tbl, width=100):
    """The TableBox RowFactory makes of tbl."""
    paragraphs, state = generate(doc_texel(tbl, None), width)
    box, = table_boxes(paragraphs)
    return box


def cell_rows(cellbox):
    """The Rows inside a CellBox."""
    rows = []
    def visit(box):
        if isinstance(box, Row):
            rows.append(box)
            return
        for _, _, child in getattr(box, 'data', ()):
            visit(child)
    visit(cellbox)
    return rows


def row_text(row):
    return ''.join(getattr(b, 'text', '') for b in row.childs
                   if isinstance(b, TextBox))


def cell_text(cellbox):
    return ' '.join(row_text(r).strip() for r in cell_rows(cellbox))


def small_memo(width=60, height=40):
    memo = State(width)
    memo.geometry = (width + 2, height + 2)
    memo.border = (1, 1, 1, 1)
    return memo


def pages_from(texel, memo, i1=0):
    return list(generate_pages(texel, i1, memo, testsheet, TESTDEVICE))


def page_tables(page):
    return [box for _, _, row in page.rows for box in row.childs
            if isinstance(box, TableBox)]


def page_sig(page):
    def box_sig(box):
        if isinstance(box, TableBox):
            return ('table', box.n_rows, box.row_offset, len(box),
                    [[cell_text(c) for c in row] for row in box.cells])
        return (type(box).__name__, getattr(box, 'text', ''))
    return (len(page), [[box_sig(b) for b in row.childs]
                        for _, _, row in page.rows])


def tall_table(n=12, **kw):
    return table([['r%d' % k, 'x'] for k in range(n)], **kw)


def app():
    if wx.App.Get() is None:
        wx.App(False)


# TBL - building tables

def test_TBL_1():
    "TBL-1: a table gives an n_rows x n_cols TableBox in a row of its own"
    tbl = from_strings([['A', 'B', 'C'], ['D', 'E', 'F']])
    paragraphs, state = generate(doc_texel('before', tbl, 'after', None))
    rows = [record[0] for record in flat(paragraphs)]
    kinds = [[type(b).__name__ for b in row.childs] for row in rows]
    assert ['TableBox'] in kinds
    assert all(len(k) == 1 for k in kinds if 'TableBox' in k)
    box, = table_boxes(paragraphs)
    assert (box.n_rows, box.n_cols) == (2, 3)
    assert [[cell_text(c) for c in row] for row in box.cells] == \
        [['A', 'B', 'C'], ['D', 'E', 'F']]


def test_TBL_2():
    "TBL-2: lengths: table, cells (+1 separator), rows per paragraph"
    from ..textmodel.utils import iter_paragraphs
    tbl = table([['ab', 'c'], [cell('d', '\n', 'ef'), '']])
    box = box_of(tbl)
    assert len(box) == length(tbl)
    contents = tbl.childs[1::2]
    assert [len(c) for row in box.cells for c in row] == \
        [length(t) + 1 for t in contents]
    texel = doc_texel('x', tbl, 'y', None, 'z', None)
    paragraphs, state = generate(texel)
    for (i1, i2, _), records in zip(iter_paragraphs(texel, 0), paragraphs):
        assert sum(len(r[0]) for r in records) == i2 - i1


def test_TBL_3():
    "TBL-3: cell offsets match the cells' positions in the texel"
    tbl = table([['ab', 'c'], ['def', '']])
    box = box_of(tbl)
    positions = [j1 for j1, j2, child in iter_childs(tbl)][1::2]
    offsets = [box.offsets[(r, c)] for r in range(2) for c in range(2)]
    assert offsets == positions


def test_TBL_4():
    "TBL-4: column widths: equal, explicit, the rest shared"
    assert box_of(from_strings([['a', 'b']]), 100).col_widths == [50, 50]
    tbl = table([['a', 'b', 'c']], col_widths=[20, None, None])
    assert box_of(tbl, 100).col_widths == [20, 40, 40]
    tbl = table([['a', 'b']], col_widths=[30, 25])
    assert box_of(tbl, 100).col_widths == [30, 25]


def test_TBL_5():
    "TBL-5: cells wrap at column width minus padding; row heights"
    tbl = table([['aaa bbb ccc ddd eee', 'x']])
    box = box_of(tbl, 40)  # columns 20 wide, content 20 - CELL_HPAD
    long, short = box.cells[0]
    rows = cell_rows(long)
    assert len(rows) > 1
    for row in rows:
        assert row.start[0] + row.width <= 20 - CELL_HPAD
    assert long.height == len(rows) + CELL_VPAD
    assert box.row_heights == [max(long.height, short.height)]


def test_TBL_6():
    "TBL-6: cell style comes from the separator after the cell"
    styles = {(0, 1): {'cell_bgcolor': 'red', 'border_left': 'none'}}
    box = box_of(table([['a', 'b']], styles))
    assert box.cells[0][1].style.get('cell_bgcolor') == 'red'
    assert box.cells[0][1].style.get('border_left') == 'none'
    assert box.cells[0][0].style.get('cell_bgcolor') is None


def test_TBL_7():
    "TBL-7: header rows and break level come from the texel"
    box = box_of(table([['h', 'h'], ['a', 'b']], nheader=1, breaklevel=0))
    assert (box.header_rows, box.break_level) == (1, 0)


def test_TBL_8():
    "TBL-8: multi-paragraph and empty cells"
    box = box_of(table([[cell('one', '\n', 'two'), '']]))
    multi, empty = box.cells[0]
    assert [row_text(r).strip() for r in cell_rows(multi)] == \
        ['one', 'two']
    assert len(cell_rows(empty)) == 1


def test_TBL_9():
    "TBL-9: footnotes in cells reach the page state in order, numbered on"
    tbl = table([[cell('c', fnote('in cell')),
                  cell('d', fnote('outer ', fnote('nested')))]])
    texel = doc_texel('a', fnote('first'), None, tbl, None,
                      'b', fnote('last'), None)
    paragraphs, state = generate(texel, width=200)
    assert [row_text(r[0]).strip() for r in state.footnotes] == \
        ['first', 'in cell', 'outer', 'nested', 'last']
    assert [r[0].marker for r in state.footnotes] == \
        ['1', '2', '3', '4', '5']


def test_TBL_10():
    "TBL-10: list counters in cells don't flow back"
    numbered = dict(paragraph_type='numbered', fixed_indent=0)
    tbl = table([[cell('x', NewLine().set_parstyle(
        dict(base='normal', **numbered)), 'y'), 'z']])
    texel = grouped([T('a'), nl(**numbered), tbl, nl(),
                     T('b'), nl(**numbered)])
    paragraphs, state = generate(texel)
    markers = [p[0][0].marker for p in paragraphs]
    assert markers[0] == '1.' and markers[-1] == '2.'


def test_TBL_11():
    "TBL-11: a table nested in a cell"
    inner = from_strings([['i1', 'i2']])
    box = box_of(table([[cell('outer'), cell(inner)]]), 200)
    nested = [b for r in cell_rows(box.cells[0][1]) for b in r.childs
              if isinstance(b, TableBox)]
    assert len(nested) == 1
    assert [[cell_text(c) for c in row] for row in nested[0].cells] == \
        [['i1', 'i2']]
    assert len(box) == length(table([[cell('outer'), cell(inner)]]))


def test_TBL_12():
    "TBL-12: footnotes in a cell are set at the page's text width"
    words = ' '.join('w%02d' % k for k in range(15))  # 59 characters
    tbl = table([[cell('c', fnote(words)), 'x']])
    paragraphs, state = generate(doc_texel(tbl, None), width=100)
    rows = [r[0] for r in state.footnotes]
    # cell: 50 - CELL_HPAD - label indent = 32 would need two rows;
    # page: 100 - label indent = 90 needs one
    assert len(rows) == 1
    assert row_text(rows[0]).strip() == words


# SPLIT - splitting across pages

def test_SPLIT_1():
    "SPLIT-1: a tall table is split across pages, nothing lost"
    tbl = tall_table(12)
    texel = doc_texel('before', None, tbl, None, 'after', None)
    pages = pages_from(texel, small_memo(height=40))
    parts = [b for p in pages for b in page_tables(p)]
    assert len(parts) > 1
    assert sum(b.n_rows for b in parts) == 12
    assert sum(len(b) for b in parts) == length(tbl)
    assert sum(len(p) for p in pages) == length(texel)
    names = [cell_text(row[0]) for b in parts for row in b.cells]
    assert names == ['r%d' % k for k in range(12)]
    for page in pages:
        bottom = max(y + r.height + r.depth for _, y, r in page.rows)
        assert bottom <= 1 + 40


def test_SPLIT_2():
    "SPLIT-2: break level 0: the table is not split"
    tbl = tall_table(4, breaklevel=0)
    texel = grouped([T('l%d' % k) if j == 0 else nl()
                     for k in range(30) for j in range(2)] + [tbl, nl()])
    pages = pages_from(texel, small_memo(height=40))
    parts = [b for p in pages for b in page_tables(p)]
    assert len(parts) == 1 and parts[0].n_rows == 4

    # taller than a page: placed anyway, pages progress
    big = tall_table(12, breaklevel=0)
    pages = pages_from(doc_texel(big, None), small_memo(height=40))
    parts = [b for p in pages for b in page_tables(p)]
    assert len(parts) == 1 and parts[0].n_rows == 12


def test_SPLIT_3():
    "SPLIT-3: the parts are chained (prev/next) and know their row_offset"
    pages = pages_from(doc_texel(tall_table(12), None), small_memo())
    parts = [b for p in pages for b in page_tables(p)]
    assert parts[0].prev is None and parts[-1].next is None
    for a, b in zip(parts, parts[1:]):
        assert a.next is b and b.prev is a
        assert b.row_offset == a.row_offset + a.n_rows


def test_SPLIT_4():
    "SPLIT-4: text after the table follows its last part"
    texel = doc_texel(tall_table(12), None, 'after', None)
    pages = pages_from(texel, small_memo())
    last = [k for k, p in enumerate(pages) if page_tables(p)][-1]
    texts = [row_text(r) for _, _, r in pages[last].rows] + \
        [row_text(r) for p in pages[last + 1:] for _, _, r in p.rows]
    assert 'after' in texts


def test_SPLIT_5():
    "SPLIT-5: restarting in the middle of a table reproduces the pages"
    texel = doc_texel('before', None, tall_table(15), None, 'after', None)
    pages = pages_from(texel, small_memo())
    assert len(pages) > 2
    start = 0
    for k in range(len(pages) - 1):
        start += len(pages[k])
        again = pages_from(texel, pages[k].restartmemo, start)
        assert [page_sig(p) for p in again] == \
            [page_sig(p) for p in pages[k + 1:]], k


def test_SPLIT_6():
    "SPLIT-6: a single table row taller than a page is still placed"
    tall_cell = cell(*sum([['w%d' % k, '\n'] for k in range(60)], [])[:-1])
    tbl = table([['a', 'b'], [tall_cell, 'c'], ['d', 'e']])
    texel = doc_texel(tbl, None, 'after', None)
    pages = pages_from(texel, small_memo(height=40))
    assert sum(len(p) for p in pages) == length(texel)


def test_SPLIT_7():
    "SPLIT-7: header rows stay together with at least one body row"
    tbl = table([['head', 'h']] + [['r%d' % k, 'x'] for k in range(12)],
                nheader=1)
    pages = pages_from(doc_texel(tbl, None), small_memo())
    first = [b for p in pages for b in page_tables(p)][0]
    assert first.header_rows == 1 and first.n_rows >= 2


# EDIT - editing tables in the PageBuilder

def mk_builder(model):
    from ..layout.pagebuilder import PageBuilder
    builder = PageBuilder(model, Factory(testsheet, TESTDEVICE))
    builder.settings = {
        'paper': 'custom', 'paper_width': 62, 'paper_height': 42,
        'margin_top': 1, 'margin_right': 1, 'margin_bottom': 1,
        'margin_left': 1,
    }
    builder.rebuild()
    builder.assure_finished()
    return builder


def test_EDIT_1():
    "EDIT-1: typing in a cell of a split table updates like a rebuild"
    from ..texteditor.editor import Editor
    app()
    model = TextModel()
    model.texel = doc_texel('before', None, tall_table(15), None,
                            'after', None)
    builder = mk_builder(model)
    model.add_view(builder)
    editor = Editor(model)
    # type into the cell 'r12' (on a later page)
    i = model.get_text().index('r12')
    editor.index = i
    editor.insert_text('XY')
    builder.assure_finished()
    expected = [page_sig(p) for p in mk_builder(model)._layout.childs]
    assert [page_sig(p) for p in builder._layout.childs] == expected
    editor.undo()
    builder.assure_finished()
    expected = [page_sig(p) for p in mk_builder(model)._layout.childs]
    assert [page_sig(p) for p in builder._layout.childs] == expected


# FILE - saving and loading

def roundtrip(texel):
    doc = Document()
    doc.textmodel.texel = texel
    with tempfile.NamedTemporaryFile(suffix='.txl', delete=False) as f:
        path = f.name
    try:
        doc.save(path)
        return Document.load(path).textmodel.texel
    finally:
        os.unlink(path)


def find_table(texel):
    from ..textmodel.utils import iter_leafes
    return [t for _, _, t in iter_leafes(texel, 0)
            if isinstance(t, Table)][0]


def test_FILE_1():
    "FILE-1: a table survives saving and loading with its properties"
    styles = {(0, 0): {'cell_bgcolor': 'red'},
              (1, 1): {'border_bottom': 'none'}}
    tbl = table([['a', 'b'], [cell('c', '\n', 'd'), '']], styles,
                col_widths=[30, None], nheader=1, breaklevel=0)
    loaded = find_table(roundtrip(doc_texel('x', None, tbl, None)))
    assert (loaded.nrows, loaded.ncols, loaded.nheader,
            loaded.breaklevel) == (2, 2, 1, 0)
    assert list(loaded.col_widths) == [30, None]
    assert _get_text(loaded) == _get_text(tbl)
    seps = loaded.childs[2::2]
    assert seps[0].parstyle.get('cell_bgcolor') == 'red'
    assert seps[3].parstyle.get('border_bottom') == 'none'


def test_FILE_2():
    "FILE-2: footnotes and images in cells survive saving and loading"
    import io
    import cairocffi as cairo
    from ..images.images import Image, iter_images
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 3, 2)
    buf = io.BytesIO()
    surface.write_to_png(buf)
    data = buf.getvalue()
    tbl = table([[cell('c', fnote('note')), cell(Image(data))]])
    loaded = roundtrip(doc_texel(tbl, None))
    assert _get_text(find_table(loaded)) == _get_text(tbl)
    assert [image.content for image in iter_images(loaded)] == [data]
