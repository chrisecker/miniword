# -*- coding: utf-8 -*-

"""
Tests for Raw (collapsed: texel RawIcon): kept as its source, never
rendered (a passive document), written back unchanged by the export of
its language; alone in its paragraph or in the text (an HTML block or
inline HTML); collapsing and expanding test_code.py. IDs HTML-n.

Run with: python runtests.py miniword/tests/test_raw.py
"""

import re
from ..mdelements.raw import Raw, RawIcon
from ..textmodel.texeltree import Group, Text, NL, grouped
from ..textmodel.utils import iter_leafes

BLOCK = '<div align="center">\n  <b>x</b>\n</div>'


def sources(texel):
    return [t.source for *_, t in iter_leafes(texel, 0, True)
            if isinstance(t, RawIcon)]


def test_HTML_1():
    "HTML-1: the file format keeps the source (lines, quotes)"
    from ..io.texeltreeformat import serialize, parse
    root, _, _ = parse(serialize(Group([RawIcon(BLOCK), NL])))
    assert sources(root) == [BLOCK]


def test_HTML_3():
    "HTML-3: Markdown: an HTML block comes back unchanged"
    from ..io.mdfilter import _load_mistune, _doc_to_md, _check_md
    md = 'Text\n\n' + BLOCK + '\n\nmore\n'
    document = _load_mistune(md)
    assert sources(document.textmodel.texel) == [BLOCK]
    assert _doc_to_md(document) == md
    assert _check_md(document) == []


def test_HTML_4():
    "HTML-4: Markdown: inline HTML becomes Raw HTML in the text and comes "
    "back unchanged, also in a table cell"
    from ..io.mdfilter import _load_mistune, _doc_to_md
    for md in ('press <kbd>Ctrl</kbd> now\n',
               '| a            |\n| ------------ |\n| <kbd>b</kbd> |\n'):
        document = _load_mistune(md)
        assert sources(document.textmodel.texel) == ['<kbd>', '</kbd>']
        assert _doc_to_md(document) == md


def test_HTML_5():
    "HTML-5: collapsed, Raw is an icon in the text, in the row of the "
    "text beside it"
    from ..mdelements.raw import RawIconBox
    from .test_rowfactory import doc, par, pages_from, small_memo
    page = pages_from(doc(par('a', RawIcon('<kbd>'), 'b', RawIcon('</kbd>'),
                              'c')),
                      small_memo(width=400, height=400))[0]
    (_, _, row), = page.rows
    icons = [box for box in row.childs if isinstance(box, RawIconBox)]
    assert len(icons) == 2 and not RawIconBox.standalone


def test_HTML_6():
    "HTML-6: in the text, collapsed or expanded, Raw is written where it "
    "is: Markdown inline, HTML in the paragraph; alone in its paragraph "
    "a block (HTML: without <p>)"
    from ..io.mdfilter import _load_mistune, _doc_to_md
    from ..io.htmlexport import html_of

    def html(model):  # without the paragraphs' style
        return re.sub(' style="[^"]*"', '', html_of(model))

    for raw in (RawIcon('<b>'), Raw.from_text('<b>')):
        document = _load_mistune('')
        model = document.textmodel
        model.texel = grouped([Text('a '), raw, Text('x'), NL])
        assert _doc_to_md(document) == 'a <b>x\n'
        assert html(model) == '<p>a <b>x</p>'
        model.texel = grouped([Text('a'), NL, raw, NL])
        assert _doc_to_md(document) == 'a\n\n<b>\n'
        assert html(model) == '<p>a</p><b>'


def test_HTML_7():
    "HTML-7: Markdown: a blank line in Raw in the text is a reduction "
    "(it would end the paragraph); alone in its paragraph it is none"
    from ..io.mdfilter import _load_mistune, _check_md
    document = _load_mistune('')
    model = document.textmodel
    raw = RawIcon('<div>\n\n</div>')
    model.texel = grouped([Text('a'), raw, NL])
    assert _check_md(document) == ['raw with a blank line within text']
    model.texel = grouped([raw, NL])
    assert _check_md(document) == []


def test_HTML_8():
    "HTML-8: Insert > Raw HTML: an empty expanded Raw at the cursor, in "
    "the text, the cursor in it; collapsed it stays there"
    from ..core.document import Document
    from ..mdelements.raw import insert_raw, toggle_raw
    from ..ui.mainwindow import MainFrame
    from .guitest import app, close
    from .test_code import codes
    app()
    document = Document()
    document.textmodel.insert_text(0, 'abcd')
    frame = MainFrame(document)
    try:
        editor, model = frame.editor, document.textmodel
        editor.set_index(2)
        insert_raw(editor)
        editor.insert_text('<b>')
        assert codes(model.texel) == [('raw', 'html', '<b>')]
        assert toggle_raw(editor, editor.index)
        assert model.get_text() == 'ab' + RawIcon.text + 'cd'
        assert sources(model.texel) == ['<b>']
    finally:
        close(frame)
