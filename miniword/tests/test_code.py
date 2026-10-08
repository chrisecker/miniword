# -*- coding: utf-8 -*-

"""
Tests for code blocks (texel Code: a container like a table with one
cell; develnotes/code_block_concept.md). IDs CODE-n.

Run with: python runtests.py miniword/tests/test_code.py
"""

from ..core.texels import Code
from ..textmodel.texeltree import Group, Text, NL, grouped, length
from .test_rowfactory import doc, par, pages_from, small_memo


def code(*lines, **kw):
    """A Code texel of lines (its last newline is the closing SEP)."""
    texels = []
    for line in lines:
        texels += [Text(line), NL.set_parstyle({'base': 'pre'})]
    return Code(grouped(texels[:-1]), **kw)


def test_CODE_1():
    "CODE-1: a code block is a box of its own row, as wide as the text"
    from ..tables.table_boxes import CodeBox
    texel = code('x = 1', 'y = 2')
    page = pages_from(doc(par('a'), par(texel), par('b')),
                      small_memo(width=300, height=300))[0]
    boxes = [(row, box) for _, _, row in page.rows for box in row.childs
             if isinstance(box, CodeBox)]
    (row, box), = boxes
    assert row.childs == [box] and len(box) == length(texel)
    assert box.width == 300


def test_CODE_2():
    "CODE-2: kind and language are kept; a copy keeps them"
    texel = code('x', kind='html', lang='')
    assert (texel.kind, texel.lang) == ('html', '')
    texel = code('x', lang='python')
    assert texel.set_childs(texel.childs).lang == 'python'


def frame_with(texel):
    from ..core.document import Document
    from ..ui.mainwindow import MainFrame
    from .guitest import app
    app()
    document = Document()
    frame = MainFrame(document)
    frame.editor.insert_texel(Group([Text('a'), NL, texel, NL]))
    frame.canvas.builder.assure_index(len(document.textmodel), 0)
    return frame


def test_CODE_3():
    "CODE-3: typing inside a code block, undo"
    from .guitest import close
    frame = frame_with(code('x = 1'))
    try:
        model = frame.document.textmodel
        i = model.get_text().index('x')
        frame.editor.set_index(i + 1)
        frame.editor.insert_text('y')
        assert 'xy = 1' in model.get_text()
        frame.editor.undo()
        assert 'x = 1' in model.get_text()
    finally:
        close(frame)


def test_CODE_4():
    "CODE-4: a click into the box puts the cursor into the code"
    from ..tables.table_boxes import CodeBox
    from ..layout.boxes import find_box_at
    from .guitest import close
    frame = frame_with(code('x = 1', 'y = 2'))
    try:
        layout, model = frame.canvas.layout, frame.document.textmodel
        start = model.get_text().index('x')
        i1, (x, y), box = find_box_at(layout, start, CodeBox)
        i = layout.get_index(x + box.width / 2, y + box.height - 2, 0)
        assert model.get_text()[model.linestart(i)] == 'y'  # 2nd line
    finally:
        close(frame)


def codes(texel):
    """(kind, lang, text) of each code block in texel."""
    from ..textmodel.texeltree import get_text
    if isinstance(texel, Code):
        return [(texel.kind, texel.lang, get_text(texel.childs[1]))]
    return [c for child in getattr(texel, 'childs', ()) for c in codes(child)]


def test_CODE_5():
    "CODE-5: the file format keeps a code block, its kind and language"
    from ..io.texeltreeformat import serialize, parse
    texel = Group([code('x = 1', '', 'y', lang='python'), NL,
                   code('<b>', kind='html'), NL])
    root, _, _ = parse(serialize(texel))
    assert codes(root) == codes(texel) == [
        ('code', 'python', 'x = 1\n\ny'), ('html', '', '<b>')]


def test_CODE_6():
    "CODE-6: Markdown code blocks (with a language or not) and back"
    from ..plugins.mdfilter import _load_mistune, _doc_to_md, _check_md
    md = 'Text\n\n```python\nx = 1\n\ny = 2\n```\n\n```\nplain\n```\n'
    document = _load_mistune(md)
    assert codes(document.textmodel.texel) == [
        ('code', 'python', 'x = 1\n\ny = 2'), ('code', '', 'plain')]
    assert _doc_to_md(document) == md
    assert _check_md(document) == []


def test_CODE_7():
    "CODE-7: a fence longer than the backticks in the code"
    from ..plugins.mdfilter import _load_mistune, _doc_to_md
    md = '````\n```\nnot the end\n```\n````\n'
    document = _load_mistune(md)
    assert codes(document.textmodel.texel) == [
        ('code', '', '```\nnot the end\n```')]
    assert _doc_to_md(document) == md


def test_CODE_8():
    "CODE-8: HTML <pre><code class=language-x> becomes a code block"
    from ..core.document import Document
    from ..plugins.htmlfilter import html_text_to_fragment
    texel = html_text_to_fragment(
        '<p>a</p><pre><code class="language-python">x = 1\n'
        'y</code></pre>', Document())
    assert codes(texel) == [('code', 'python', 'x = 1\ny')]
