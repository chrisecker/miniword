# -*- coding: utf-8 -*-

"""
Tests for the checkbox (texel Checkbox, e.g. at the start of a task list
item): file format, layout, clicking, Markdown and HTML, inserting.
IDs CB-n.

Run with: python runtests.py miniword/tests/test_checkbox.py
"""

from ..core.texels import Checkbox
from ..textmodel.texeltree import Group, Text, NL
from ..textmodel.utils import iter_leafes
from .test_rowfactory import doc, par, pages_from, small_memo


def checkboxes(texel):
    return [t.checked for *_, t in iter_leafes(texel, 0)
            if isinstance(t, Checkbox)]


def test_CB_1():
    "CB-1: the file format keeps checkboxes and their state"
    from ..io.texeltreeformat import serialize, parse
    out = serialize(Group([Checkbox(), Text('a'), NL,
                           Checkbox().set_checked(True), Text('b'), NL]))
    root, _, _ = parse(out)
    assert checkboxes(root) == [False, True]


def test_CB_2():
    "CB-2: a checkbox is a box of the text's size, before the text"
    from ..layout.boxes import CheckboxBox
    page = pages_from(doc(par(Checkbox(), 'todo')),
                      small_memo(width=100, height=100))[0]
    (_, _, row), = page.rows
    box = row.childs[0]
    assert isinstance(box, CheckboxBox) and box.width > box.size > 0


def test_CB_3():
    "CB-3: Markdown task lists: checkboxes and back"
    from ..plugins.mdfilter import _load_mistune, _doc_to_md, _check_md
    md = '- [ ] todo\n- [x] done\n'
    document = _load_mistune(md)
    assert checkboxes(document.textmodel.texel) == [False, True]
    assert 'todo' in document.textmodel.get_text()
    assert _doc_to_md(document) == md
    assert _check_md(document) == []


def test_CB_4():
    "CB-4: a checkbox outside a list item's start is reported"
    from ..plugins.mdfilter import _md_doc, _check_md
    document = _md_doc('')
    document.textmodel.texel = Group([Text('a '), Checkbox(), NL])
    assert any('checkbox' in w for w in _check_md(document))


def test_CB_5():
    "CB-5: HTML <input type=checkbox> becomes a checkbox"
    from ..core.document import Document
    from ..plugins.htmlfilter import html_text_to_fragment
    texel = html_text_to_fragment(
        '<ul><li><input type="checkbox" checked> a</li>'
        '<li><input type="checkbox"> b</li></ul>', Document())
    assert checkboxes(texel) == [True, False]


def test_CB_6():
    "CB-6: a click into the box toggles it (one undo step), next to it "
    "not; the hand cursor shows where"
    from ..core.document import Document
    from ..layout.boxes import CheckboxBox, find_box_at
    from ..ui.mainwindow import MainFrame
    from .guitest import app, close
    app()
    document = Document()
    frame = MainFrame(document)
    try:
        frame.editor.insert_texel(Group([Checkbox(), Text('todo')]))
        builder = frame.canvas.builder
        builder.assure_index(len(document.textmodel), 0)
        _, (x, y), box = find_box_at(frame.canvas.layout, 0, CheckboxBox)
        model = document.textmodel
        canvas = frame.canvas
        assert canvas.checkbox_at(x + 2, y + 2) is not None  # hand cursor
        assert canvas.checkbox_at(x + box.width + 5, y + 2) is None
        assert not frame.canvas.toggle_checkbox(x + box.width + 5, y + 2)
        assert frame.canvas.toggle_checkbox(x + 2, y + 2)
        assert checkboxes(model.texel) == [True]
        frame.editor.undo()
        assert checkboxes(model.texel) == [False]
    finally:
        close(frame)


def test_CB_7():
    "CB-7: Insert > Checkbox inserts one at the cursor"
    from ..core.document import Document
    from ..ui.mainwindow import MainFrame
    from .guitest import app, close
    app()
    document = Document()
    document.textmodel.insert_text(0, 'todo')
    frame = MainFrame(document)
    try:
        frame.editor.set_index(0)
        frame.insert_checkbox()
        assert checkboxes(document.textmodel.texel) == [False]
        assert document.textmodel.get_text().endswith('todo')
    finally:
        close(frame)
