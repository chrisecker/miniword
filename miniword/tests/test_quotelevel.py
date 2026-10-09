# -*- coding: utf-8 -*-

"""
Tests for the quote level (paragraph property quote_level: the depth of
a quote, independent of the style; a bar per level;
develnotes/quote_level_concept.md). IDs QL-n.

Run with: python runtests.py miniword/tests/test_quotelevel.py
"""

from ..core.styles import style_default
from ..layout.rowfactory import RowStack
from .test_rowfactory import doc, par, generate, flat

Q = style_default['quote_indent']
LIST = style_default['list_indent']


def stack(*pars, width=100):
    """A RowStack of the paragraphs, all taken."""
    records = flat(generate(doc(*pars), width=width)[0])
    result = RowStack(width)
    result.take(records)
    return result


def bars(stack):
    """(x, top, bottom) of the quote bars (lines on the left only)."""
    return sorted((x, y, y + h) for x, y, w, h, (color, width, sides)
                  in stack.decorations()[1] if sides == 'l')


def test_QL_1():
    "QL-1: quote_level n: the text n steps in, a bar per level; the "
    "inner bar only over the deeper paragraphs"
    s = stack(par('a', quote_level=1), par('b', quote_level=2),
              par('c', quote_level=1), par('d'))
    rows = [record[0] for _, record in s.placed]
    assert [row.start[0] for row in rows] == [Q, 2 * Q, Q, 0]
    (y, _), (yb, _), (yc, _), (yd, _) = [(y, r) for y, r in s.placed]
    (x0, top0, bottom0), (x1, top1, bottom1) = bars(s)
    assert (x0, x1) == (0, Q)
    assert top0 == y and bottom0 <= yd  # a to c, not d
    assert top1 == yb and bottom1 <= yc  # b only


def test_QL_2():
    "QL-2: a list item in a quote: its text inside the bar, after the "
    "list indent"
    s = stack(par('item', paragraph_type='list', quote_level=1))
    (_, record), = s.placed
    assert record[0].start[0] == Q + LIST
    assert [x for x, _, _ in bars(s)] == [0]


def test_QL_3():
    "QL-3: the Markdown style 'Quote' gives quote_level 1 (its base "
    "style); without it there is no quote"
    from ..plugins.mdfilter import _load_mistune
    document = _load_mistune('> a\n\nb\n')
    sheet = document.basestyles
    assert sheet.get('quote')['quote_level'] == 1
    assert style_default['quote_level'] == 0
    for key in ('note', 'warning'):
        assert sheet.get(key)['quote_level'] == 1


MD = '''> Outer quote
>
> > Inner quote
>
> Back to outer
>
> - item in quote
> - second
>
> ```python
> x = 1
> ```

After
'''


def levels(document):
    """(text, quote_level, paragraph_type) of each paragraph - the
    level with the base style's."""
    from ..textmodel.utils import iter_paragraphs
    from ..textmodel.texeltree import get_text
    sheet = document.basestyles
    result = []
    for *_, elems in iter_paragraphs(document.textmodel.texel, 0):
        ps = sheet.mk_parstyle(elems[-1].parstyle)
        text = ''.join(get_text(e) for e in elems[:-1]).strip()
        result.append((text, ps['quote_level'], ps['paragraph_type']))
    return result


def test_QL_4():
    "QL-4: Markdown import: each block in a quote gets its depth - "
    "paragraphs, nested quotes, list items, code"
    from ..plugins.mdfilter import _load_mistune
    found = [entry for entry in levels(_load_mistune(MD)) if entry[0]]
    assert found == [('Outer quote', 1, 'normal'),
                     ('Inner quote', 2, 'normal'),
                     ('Back to outer', 1, 'normal'),
                     ('item in quote', 1, 'list'), ('second', 1, 'list'),
                     ('x = 1', 1, 'normal'), ('After', 0, 'normal')]


def test_QL_5():
    "QL-5: Markdown export: it comes back unchanged (> per level, before "
    "markers and fences); no loss reported; alerts as before"
    from ..plugins.mdfilter import _load_mistune, _doc_to_md, _check_md
    alert = '> [!NOTE]\n> Useful.\n>\n> More.\n'
    for md in (MD, alert):
        document = _load_mistune(md)
        assert _doc_to_md(document) == md
        assert _check_md(document) == []
