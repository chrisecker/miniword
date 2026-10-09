# -*- coding: utf-8 -*-

"""
Tests for code blocks (texel Code: a container like a table with one
cell; develnotes/code_block_concept.md). IDs CODE-n.

Run with: python runtests.py miniword/tests/test_code.py
"""

from ..mdelements.code import Code
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
    from ..mdelements.code import CodeBox
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
    from ..plugins.mdfilter import _register_styles
    app()
    document = Document()
    _register_styles(document)  # 'pre': the role of code lines
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
    from ..mdelements.code import CodeBox
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


def test_CODE_9():
    "CODE-9: Insert > Code Block: an empty block of its own, cursor in it"
    from ..mdelements.code import insert_code
    from ..core.document import Document
    from ..ui.mainwindow import MainFrame
    from .guitest import app, close
    app()
    document = Document()
    document.textmodel.insert_text(0, 'abcd')
    frame = MainFrame(document)
    try:
        frame.editor.set_index(2)
        insert_code(frame.editor)
        frame.editor.insert_text('x = 1')
        assert codes(document.textmodel.texel) == [('code', '', 'x = 1')]
        text = document.textmodel.get_text()
        assert text.startswith('ab\n') and text.endswith('\ncd')
    finally:
        close(frame)


def test_CODE_10():
    "CODE-10: what is pasted into code stays as it is (styles, paragraph "
    "styles), but shows as code: the factory ignores the styles"
    from ..layout.boxes import find_box_at
    from ..mdelements.code import CodeBox
    from .guitest import close
    frame = frame_with(code('x'))
    try:
        model = frame.document.textmodel
        frame.editor.set_index(model.get_text().index('x'))
        frame.editor.insert_texel(Group([
            Text('bold', dict(bold=True)), NL.set_parstyle({'base': 'h1'})]))
        frame.editor.insert_text('line')
        (kind, lang, text), = codes(model.texel)
        assert text == 'bold\nlinex'
        j = model.get_text().index('bold')
        assert model.get_style(j).get('bold')
        assert model.get_parstyle(j)['base'] == 'h1'
        canvas = frame.canvas
        canvas.builder.assure_index(len(model), 0)
        i = model.get_text().index('bold') - 1
        _, _, box = find_box_at(canvas.layout, i, CodeBox)
        styles = text_styles(box)
        assert len(styles) >= 3 and not styles[0].get('bold')
        assert all(style == styles[0] for style in styles)
        from ..textmodel import TextModel  # plain text, with an end mark
        frame.editor.insert_model(TextModel('p\nq'))
        assert codes(model.texel)[0][2] == 'bold\nlinep\nqx'
    finally:
        close(frame)


def text_styles(box):
    """The styles of the text boxes in box."""
    from ..layout.boxes import TextBox
    if isinstance(box, TextBox):
        return [box.style]
    return [style for _, _, child in box.iter_childs()
            for style in text_styles(child)]


HTML = '<div>\n  <b>x</b>\n</div>'


def test_CODE_12():
    "CODE-12: an HTML block collapses (RawHTML) and expands (Code)"
    from ..mdelements.rawhtml import RawHTML
    from ..mdelements.rawhtml import toggle_html
    from .guitest import close
    frame = frame_with(RawHTML(HTML))
    try:
        editor, model = frame.editor, frame.document.textmodel
        i = model.get_text().index(RawHTML.text)
        assert toggle_html(editor, i)  # expand
        assert codes(model.texel) == [('html', '', HTML)]
        editor.set_index(i + 3)  # in the code
        assert toggle_html(editor, editor.index)  # collapse
        assert codes(model.texel) == []
        assert RawHTML.text in model.get_text()
        editor.undo()
        assert codes(model.texel) == [('html', '', HTML)]
        assert not toggle_html(editor, 0)  # nothing there
    finally:
        close(frame)


def test_CODE_13():
    "CODE-13: an HTML block shows collapsed (icon, first line), inline not"
    from ..mdelements.rawhtml import RawHTML
    from ..mdelements.rawhtml import RawHTMLBox
    page = pages_from(doc(par(RawHTML(HTML)), par('a', RawHTML('<kbd>'))),
                      small_memo(width=400, height=400))[0]
    block, inline = [box for _, _, row in page.rows for box in row.childs
                     if isinstance(box, RawHTMLBox)]
    assert block.collapsed and len(block.lines) == 1 and block.icon_width
    assert not inline.collapsed


def test_CODE_14():
    "CODE-14: a double click on the icon toggles, collapsed and expanded"
    from ..mdelements.rawhtml import RawHTML
    from ..mdelements.rawhtml import RawHTMLBox
    from ..layout.boxes import find_box_at
    from ..mdelements.code import CodeBox
    from .guitest import close, double_click
    frame = frame_with(RawHTML(HTML))
    try:
        canvas, model = frame.canvas, frame.document.textmodel
        build = lambda: canvas.builder.assure_index(len(model), 0)
        i = model.get_text().index(RawHTML.text)
        _, (x, y), box = find_box_at(canvas.layout, i, RawHTMLBox)
        double_click(canvas, x + box.width - 2, y + 2)  # not the icon
        assert codes(model.texel) == []
        double_click(canvas, x + 2, y + 2)  # on the icon
        assert codes(model.texel) == [('html', '', HTML)]
        build()
        _, (x, y), box = find_box_at(canvas.layout, i + 1, CodeBox)
        double_click(canvas, x + box.width - 3, y + 3)
        assert codes(model.texel) == []
    finally:
        close(frame)


def test_CODE_15():
    "CODE-15: the Elements panel: language, expand/collapse, insert"
    from ..mdelements.rawhtml import RawHTML
    from .guitest import close, click_button, enter
    frame = frame_with(code('x = 1'))
    try:
        panel, editor = frame.elements_panel, frame.editor
        model = frame.document.textmodel
        editor.set_index(model.get_text().index('x') + 1)
        panel.update()
        assert panel.language.IsShown()
        enter(panel.language, 'python')
        assert codes(model.texel) == [('code', 'python', 'x = 1')]
        editor.set_index(0)
        panel.update()
        assert not panel.language.IsShown()
        click_button(panel.buttons['rule'])
        from ..mdelements.rule import Rule
        assert Rule.text in model.get_text()
    finally:
        close(frame)
    frame = frame_with(RawHTML(HTML))
    try:
        panel, editor = frame.elements_panel, frame.editor
        model = frame.document.textmodel
        editor.set_index(model.get_text().index(RawHTML.text))
        panel.update()
        assert panel.expand.IsShown()
        click_button(panel.expand)
        assert codes(model.texel) == [('html', '', HTML)]
    finally:
        close(frame)
