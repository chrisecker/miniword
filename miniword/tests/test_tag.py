# -*- coding: utf-8 -*-

"""
Tests for inline HTML (texel Tag: one tag, e.g. <kbd>, a container
[<, content, >] edited in the text, never rendered, written back
unchanged). IDs TAG-n.

Run with: python runtests.py miniword/tests/test_tag.py
"""

from ..mdelements.tag import Tag, TagBox
from ..textmodel.texeltree import Group, Text, NL, length
from .test_rowfactory import doc, par, pages_from, small_memo


def tags(texel):
    """The sources of the tags in texel, also in containers."""
    if isinstance(texel, Tag):
        return [texel.source]
    return [s for child in getattr(texel, 'childs', ()) for s in tags(child)]


def test_TAG_1():
    "TAG-1: a tag is its source in the text, the brackets separators; "
    "the file format keeps it"
    from ..io.texeltreeformat import serialize, parse
    source = '<img src="a.png" width="50">'
    tag = Tag(source)
    assert tag.source == source and length(tag) == len(source)
    assert Tag().source == '<>'
    out = serialize(Group([Text('a'), tag, NL]))
    assert 'TAG(' in out
    root, _, _ = parse(out)
    assert tags(root) == [source]


def test_TAG_2():
    "TAG-2: a tag is a chip in the text, showing its source (one index "
    "per character)"
    page = pages_from(doc(par('a', Tag('<kbd>'), 'b', Tag('</kbd>'), 'c')),
                      small_memo(width=400, height=400))[0]
    (_, _, row), = page.rows
    chips = [box for box in row.childs if isinstance(box, TagBox)]
    assert [''.join(b.text for b in box.childs) for box in chips] == \
        ['<kbd>', '</kbd>']
    assert [len(box) for box in chips] == [5, 6]


def test_TAG_3():
    "TAG-3: typing between the brackets changes the tag; Enter is a "
    "line break in its source, shown as a space; deleting a bracket "
    "deletes the tag"
    from ..layout.boxes import find_box_at
    from .test_code import frame_with
    from .guitest import close
    frame = frame_with(Tag('<kbd>'))
    try:
        editor, model = frame.editor, frame.document.textmodel
        i = model.get_text().index('<kbd>')
        editor.set_index(i + 1)
        model.get_parstyle(i + 1)  # in the tag: the paragraph functions
        assert model.lineend(i + 1) == i + 4  # the '>'
        editor.insert_text('x')
        editor.set_index(i + 5)  # before '>'
        editor.insert_text('y')
        assert tags(model.texel) == ['<xkbdy>']
        editor.set_index(i + 2)
        editor.insert_newline()
        assert tags(model.texel) == ['<x\nkbdy>']
        frame.canvas.builder.assure_index(len(model), 0)
        _, _, box = find_box_at(frame.canvas.layout, i, TagBox)
        assert ''.join(b.text for b in box.childs) == '<x kbdy>'
        for _ in range(3):
            editor.undo()
        assert tags(model.texel) == ['<kbd>']
        editor.selection = (i, i + 1)  # the '<'
        editor.remove()
        assert tags(model.texel) == [] and '<' not in model.get_text()
    finally:
        close(frame)


def test_TAG_4():
    "TAG-4: Markdown: inline HTML becomes tags and comes back unchanged, "
    "also in a table cell"
    from ..plugins.mdfilter import _load_mistune, _doc_to_md
    md = 'press <kbd>Ctrl</kbd> now\n'
    document = _load_mistune(md)
    assert tags(document.textmodel.texel) == ['<kbd>', '</kbd>']
    assert _doc_to_md(document) == md
    md = '| a            |\n| ------------ |\n| <kbd>b</kbd> |\n'
    document = _load_mistune(md)
    assert tags(document.textmodel.texel) == ['<kbd>', '</kbd>']
    assert _doc_to_md(document) == md


def test_TAG_5():
    "TAG-5: Insert > HTML Tag: an empty tag <> at the cursor, the cursor "
    "between the brackets; Insert > HTML Block: an empty expanded block"
    from ..core.document import Document
    from ..mdelements.tag import insert_tag
    from ..mdelements.rawhtml import insert_html
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
        insert_tag(editor)
        assert model.get_text() == 'ab<>cd'
        editor.insert_text('b')
        assert tags(model.texel) == ['<b>']
        editor.set_index(len(model))
        insert_html(editor)
        editor.insert_text('<div>')
        assert codes(model.texel) == [('html', '', '<div>')]
    finally:
        close(frame)
