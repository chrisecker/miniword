# -*- coding: utf-8 -*-

"""
Tests for HTML blocks (texel RawHTML): kept as their source, never
rendered (a passive document), written back unchanged; inline HTML see
test_tag.py, collapsing and expanding test_code.py. IDs HTML-n.

Run with: python runtests.py miniword/tests/test_rawhtml.py
"""

from ..mdelements.rawhtml import RawHTML
from ..textmodel.texeltree import Group, NL
from ..textmodel.utils import iter_leafes

BLOCK = '<div align="center">\n  <b>x</b>\n</div>'


def sources(texel):
    return [t.source for *_, t in iter_leafes(texel, 0, True)
            if isinstance(t, RawHTML)]


def test_HTML_1():
    "HTML-1: the file format keeps the source (lines, quotes)"
    from ..io.texeltreeformat import serialize, parse
    root, _, _ = parse(serialize(Group([RawHTML(BLOCK), NL])))
    assert sources(root) == [BLOCK]


def test_HTML_3():
    "HTML-3: Markdown: an HTML block comes back unchanged"
    from ..plugins.mdfilter import _load_mistune, _doc_to_md, _check_md
    md = 'Text\n\n' + BLOCK + '\n\nmore\n'
    document = _load_mistune(md)
    assert sources(document.textmodel.texel) == [BLOCK]
    assert _doc_to_md(document) == md
    assert _check_md(document) == []
