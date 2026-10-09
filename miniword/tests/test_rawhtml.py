# -*- coding: utf-8 -*-

"""
Tests for raw HTML (texel RawHTML): shown as its source, never rendered
(a passive document), written back unchanged. IDs HTML-n.

Run with: python runtests.py miniword/tests/test_rawhtml.py
"""

from ..mdelements.rawhtml import RawHTML
from contextlib import contextmanager
from ..textmodel.texeltree import Group, Text, NL
from ..textmodel.utils import iter_leafes
from .test_rowfactory import doc, par, pages_from, small_memo

BLOCK = '<div align="center">\n  <b>x</b>\n</div>'


@contextmanager
def answering(answer):
    """The HTML dialog replaced: answer (source -> new one or None)."""
    from ..mdelements import rawhtml
    ask_html = rawhtml.ask_html
    rawhtml.ask_html = lambda parent, source='': answer(source)
    try:
        yield
    finally:
        rawhtml.ask_html = ask_html


def sources(texel):
    return [t.source for *_, t in iter_leafes(texel, 0, True)
            if isinstance(t, RawHTML)]


def test_HTML_1():
    "HTML-1: the file format keeps the source (lines, quotes)"
    from ..io.texeltreeformat import serialize, parse
    root, _, _ = parse(serialize(Group([RawHTML(BLOCK), NL])))
    assert sources(root) == [BLOCK]


def test_HTML_2():
    "HTML-2: inline HTML is shown as its source: its lines, one index"
    from ..mdelements.rawhtml import RawHTMLBox
    page = pages_from(doc(par('a', RawHTML(BLOCK)), par('a', RawHTML('<kbd>'))),
                      small_memo(width=400, height=400))[0]
    block, inline = [box for _, _, row in page.rows for box in row.childs
                     if isinstance(box, RawHTMLBox)]
    assert len(block) == len(inline) == 1
    assert len(block.lines) == 3 and len(inline.lines) == 1
    assert block.height + block.depth > 2 * (inline.height + inline.depth)


def test_HTML_3():
    "HTML-3: Markdown: an HTML block comes back unchanged"
    from ..plugins.mdfilter import _load_mistune, _doc_to_md, _check_md
    md = 'Text\n\n' + BLOCK + '\n\nmore\n'
    document = _load_mistune(md)
    assert sources(document.textmodel.texel) == [BLOCK]
    assert _doc_to_md(document) == md
    assert _check_md(document) == []


def test_HTML_4():
    "HTML-4: Markdown: inline HTML (tags) comes back unchanged"
    from ..plugins.mdfilter import _load_mistune, _doc_to_md
    md = 'press <kbd>Ctrl</kbd> now\n'
    document = _load_mistune(md)
    assert sources(document.textmodel.texel) == ['<kbd>', '</kbd>']
    assert _doc_to_md(document) == md


def test_HTML_5():
    "HTML-5: inline HTML in a table cell"
    from ..plugins.mdfilter import _load_mistune, _doc_to_md
    md = '| a          |\n| ---------- |\n| <kbd>b</kbd> |\n'
    document = _load_mistune(md)
    from ..tables.tables import Table
    table, = [t for t in document.textmodel.texel.childs
              if isinstance(t, Table)]
    assert sources(table) == ['<kbd>', '</kbd>']


def test_HTML_6():
    "HTML-6: a double click on inline HTML edits it (one undo step)"
    from ..core.document import Document
    from ..mdelements.rawhtml import RawHTMLBox
    from ..layout.boxes import find_box_at
    from ..ui.mainwindow import MainFrame
    from .guitest import app, close, double_click
    app()
    document = Document()
    frame = MainFrame(document)
    try:
        frame.editor.insert_texel(Group([Text('a'), RawHTML(BLOCK), NL]))
        canvas, model = frame.canvas, document.textmodel
        build = lambda: canvas.builder.assure_index(len(model), 0)
        build()
        _, (x, y), box = find_box_at(canvas.layout, 1, RawHTMLBox)
        with answering(lambda source: 'never'):
            double_click(canvas, x + box.width + 5, y + 2)
        assert sources(model.texel) == [BLOCK]
        with answering(lambda source: source + '<hr>'):
            double_click(canvas, x + 2, y + 2)
        assert sources(model.texel) == [BLOCK + '<hr>']
        frame.editor.undo()
        assert sources(model.texel) == [BLOCK]
        build()
        with answering(lambda source: None):  # cancelled
            double_click(canvas, x + 2, y + 2)
        assert sources(model.texel) == [BLOCK]
    finally:
        close(frame)


def test_HTML_7():
    "HTML-7: Insert > HTML: one line at the cursor, a block on its own"
    from ..mdelements.rawhtml import insert_html
    from ..core.document import Document
    from ..ui.mainwindow import MainFrame
    from .guitest import app, close
    app()
    document = Document()
    document.textmodel.insert_text(0, 'abcd')
    frame = MainFrame(document)
    try:
        model = document.textmodel
        frame.editor.set_index(2)
        with answering(lambda source: '<kbd>'):
            insert_html(frame.editor, frame)
        assert model.get_text() == 'ab%scd' % RawHTML.text
        with answering(lambda source: BLOCK):
            insert_html(frame.editor, frame)
        assert model.get_text() == 'ab%s\n%s\ncd' % ((RawHTML.text,) * 2)
        assert sources(model.texel) == ['<kbd>', BLOCK]
    finally:
        close(frame)
