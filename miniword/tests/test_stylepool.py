# -*- coding: utf-8 -*-

"""
Tests that styles and paragraph styles are Styles (textmodel.texeltree),
never plain dicts: equal styles are one object from the pool, and
id(style) can be a cache key. Texels assert it on creation; the flows
here also catch styles that bypass that (e.g. class attributes).
IDs POOL-n.

Run with: python runtests.py miniword/tests/test_stylepool.py
"""

from types import SimpleNamespace

from ..textmodel.texeltree import Text, NL, NewLine, grouped, EMPTYSTYLE
from ..textmodel.textmodel import TextModel
from ..textmodel.styles import Style
from ..textmodel.utils import iter_leafes

MARKDOWN = """# Title

Some **bold** and *italic* text with a footnote.[^1]

- item
  1. numbered

> quote

> [!NOTE]
> an alert

| a | b |
|:--|--:|
| 1 | 2 |

```python
def f(x):  # comment
    return 'text'
```

---

[^1]: The note.
"""


def unpooled(texel):
    """The styles and paragraph styles in texel (also in containers)
    that are not Styles."""
    found = []
    for i1, i2, leaf in iter_leafes(texel, 0, descend_containers=True):
        styles = [getattr(leaf, 'style', EMPTYSTYLE)]
        if isinstance(leaf, NewLine):
            styles.append(leaf.parstyle)
        found += [s for s in styles if not isinstance(s, Style)]
    return found


def editor_with_roles(model, roles):
    """An editor on model whose stylesheet has the styles {key: role}."""
    from ..core.stylesheet import StyleSheet
    from ..texteditor.editor import Editor
    sheet = StyleSheet()
    for key, role in roles.items():
        sheet.set(key, dict(role=role))
    editor = Editor(model)
    editor.canvas = SimpleNamespace(
        builder=SimpleNamespace(stylesheet=sheet), reset_blink=lambda: None,
        adjust_viewport=lambda: None, refresh=lambda: None)
    return editor


def raises(exception, fn, *args):
    try:
        fn(*args)
    except exception:
        return True
    return False


def test_POOL_1():
    "POOL-1: a Style is pooled and can't be changed; texels take no dicts"
    import copy
    import pickle
    from ..tables.tables import Table
    s = Style(bold=True, size=10)
    assert s is Style(size=10, bold=True) and s == dict(bold=True, size=10)
    assert copy.copy(s) is s and pickle.loads(pickle.dumps(s)) is s
    assert type(s.copy()) is dict  # a copy is for changing
    assert raises(TypeError, s.__setitem__, 'bold', False)
    assert raises(TypeError, s.update, dict(size=12))
    assert unpooled(grouped([Text('a', s), NL])) == []
    assert raises(AssertionError, Text, 'a', {'bold': True})
    assert raises(AssertionError, NL.set_parstyle, {'base': 'h1'})
    assert raises(AssertionError, Table, (Text('x'), {'alignment': 'r'}))


def test_POOL_2():
    "POOL-2: Markdown import (headings, lists, alerts, tables, code)"
    from ..io.mdfilter import _load_mistune
    assert unpooled(_load_mistune(MARKDOWN).textmodel.texel) == []


def test_POOL_3():
    "POOL-3: Markdown pasted into a document with its own styles"
    from ..core.document import Document
    from ..io.mdfilter import md_text_to_fragment
    doc = Document()
    doc.basestyles.set('Kapitel', dict(role='h1'))
    doc.basestyles.set('Liste', dict(role='list'))
    assert unpooled(md_text_to_fragment(MARKDOWN, doc)) == []


def test_POOL_4():
    "POOL-4: Enter at the end of a heading, a rule, a code block"
    from ..mdelements.rule import insert_rule
    from ..mdelements.code import insert_code
    model = TextModel('Titel\n')
    model.set_parstyle(0, Style(base='Kapitel'))
    editor = editor_with_roles(model, dict(Kapitel='h1', Text='normal',
                                           Linie='rule'))
    editor.index = 5
    editor.insert_newline()
    insert_rule(editor)
    insert_code(editor)
    assert unpooled(model.texel) == []


def test_POOL_5():
    "POOL-5: new tables; a code block as shown (colored)"
    from ..tables.tables import empty_table, from_strings
    from ..mdelements.code import Code, shown
    assert unpooled(empty_table(2, 2)) == []
    assert unpooled(from_strings([['a', 'b']])) == []
    code = Code.from_text("x = 'a'  # comment\nprint(x)", lang='python')
    assert unpooled(code) == []
    assert unpooled(shown(code.childs[1], Style(base='pre'), 'python')) == []
