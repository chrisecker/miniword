# -*- coding: utf-8 -*-

"""
Tests for the horizontal rule (texel Rule, alone in its paragraph):
file format, layout, Markdown and HTML, inserting. IDs RULE-n.

Run with: python runtests.py miniword/tests/test_rule.py
"""

from ..core.texels import Rule
from ..textmodel.texeltree import Group, Text, NL
from ..textmodel.utils import iter_leafes
from .test_rowfactory import doc, par, pages_from, small_memo


def rules(texel):
    return [t for *_, t in iter_leafes(texel, 0) if isinstance(t, Rule)]


def test_RULE_1():
    "RULE-1: the file format keeps a rule"
    from ..io.texeltreeformat import serialize, parse
    out = serialize(Group([Text('a'), NL, Rule(), NL]))
    assert 'HR' in out
    root, _, _ = parse(out)
    assert len(rules(root)) == 1


def test_RULE_2():
    "RULE-2: a rule is as wide as its paragraph's text"
    from ..layout.rowfactory import RuleBox
    page = pages_from(doc(par('ab'), par(Rule())),
                      small_memo(width=40, height=100))[0]
    boxes = [box for _, _, row in page.rows for box in row.childs
             if isinstance(box, RuleBox)]
    assert len(boxes) == 1 and boxes[0].width == 40
    assert boxes[0].height > 0


def test_RULE_3():
    "RULE-3: Markdown --- becomes a rule in its own paragraph and back"
    from ..plugins.mdfilter import _load_mistune, _doc_to_md, _check_md
    md = 'a\n\n---\n\nb\n'
    document = _load_mistune(md)
    assert len(rules(document.textmodel.texel)) == 1
    model = document.textmodel
    i = model.get_text().index(Rule.text)
    assert model.get_parstyle(i).get('base') == 'rule'
    assert document.basestyles.get('rule')['role'] == 'rule'
    assert _doc_to_md(document) == md
    assert _check_md(document) == []


def test_RULE_4():
    "RULE-4: a rule within text can't be written as Markdown: reported"
    from ..plugins.mdfilter import _md_doc, _check_md
    document = _md_doc('')
    document.textmodel.texel = Group([Text('a'), Rule(), Text('b'), NL])
    assert any('rule' in w for w in _check_md(document))


def test_RULE_5():
    "RULE-5: HTML <hr> becomes a rule"
    from ..core.document import Document
    from ..plugins.htmlfilter import html_text_to_fragment
    texel = html_text_to_fragment('<p>a</p><hr><p>b</p>', Document())
    assert len(rules(texel)) == 1


def test_RULE_6():
    "RULE-6: inserting a rule puts it into a paragraph of its own"
    from ..core.document import Document
    from ..ui.mainwindow import MainFrame
    from .guitest import app, close
    app()
    document = Document()
    document.textmodel.insert_text(0, 'abcd')
    frame = MainFrame(document)
    try:
        frame.editor.set_index(2)  # ab|cd
        frame.insert_rule()
        assert document.textmodel.get_text() == 'ab\n%s\ncd' % Rule.text
        frame.editor.undo()
        assert document.textmodel.get_text() == 'abcd'
    finally:
        close(frame)
