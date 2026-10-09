# -*- coding: utf-8 -*-

"""
Tests for continued paragraphs in lists (paragraph_type 'continued': a
further paragraph or code block of a list item, aligned with its text,
without a marker; develnotes/list_continuation_concept.md). IDs LC-n.

Run with: python runtests.py miniword/tests/test_listcont.py
"""

from .test_rowfactory import doc, par, generate, markers, numbered


def continued(level=0, **kw):
    return dict(paragraph_type='continued', fixed_indent=level, **kw)


def test_LC_1():
    "LC-1: a continued paragraph is aligned with the item's text, "
    "without a marker"
    paragraphs, _ = generate(doc(par('a', **numbered()),
                                 par('b', **continued())))
    item, cont = [p[0][0] for p in paragraphs]
    assert cont.marker is None
    assert cont.start[0] == item.start[0] > 0


def test_LC_2():
    "LC-2: numbering goes on across a continued paragraph"
    paragraphs, _ = generate(doc(par('a', **numbered()),
                                 par('b', **continued()),
                                 par('c', **numbered())))
    assert markers(paragraphs) == ['1.', None, '2.']


MD = '1. First\n\n   More of it.\n\n   ```python\n   x = 1\n   ```\n' \
    '2. Second\n'


def test_LC_3():
    "LC-3: Markdown import: an item's further paragraph and code block "
    "are continued, on its level"
    from ..plugins.mdfilter import _load_mistune
    from ..textmodel.utils import iter_paragraphs
    document = _load_mistune(MD)
    found = [(elems[-1].parstyle.get('paragraph_type'), elems[-1].indent,
              type(elems[0]).__name__)
             for *_, elems in iter_paragraphs(document.textmodel.texel, 0)]
    assert found == [('numbered', 0, 'Text'), ('continued', 0, 'Text'),
                     ('continued', 0, 'Code'), ('numbered', 0, 'Text')]


def test_LC_4():
    "LC-4: Markdown export: the item comes back unchanged, also nested; "
    "no loss reported"
    from ..plugins.mdfilter import _load_mistune, _doc_to_md, _check_md
    for md in (MD, '- a\n  1. b\n\n     more b\n- c\n'):
        document = _load_mistune(md)
        assert _doc_to_md(document) == md
        assert _check_md(document) == []


def test_LC_5():
    "LC-5: a continued paragraph without an item before it is written as "
    "a normal paragraph"
    from ..plugins.mdfilter import _load_mistune, _doc_to_md
    from ..textmodel.texeltree import Text, NL, grouped
    document = _load_mistune('')
    document.textmodel.texel = grouped([
        Text('text'), NL.set_parstyle({'base': 'body'}),
        Text('more'), NL.set_parstyle({'base': 'body',
                                       'paragraph_type': 'continued'})])
    assert _doc_to_md(document) == 'text\n\nmore\n'
