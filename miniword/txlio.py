"""
TXL file format — load and save for Document objects.

File structure (all sections except [document] are optional):

    [basestyles]
    "h1" = {font_size=18, bold, name="Header 1", role="h1"}

    [charstyles]
    "em" = {bold, name="Emphasis"}

    [liststyles]
    "bullet" = {name="Bullet list", marker="•"}

    [document]
    PROPS({author="Ada"})
    T("Hello")
    NL({base="h1"})
    T("First item.")
    NL({indent=1, base="bullet"})
    ENDMARK
"""

import re
from .document import Document
from .textmodel.textmodel import TextModel
from .texeltreeformat import serialize, parse, serialize_style, _Parser
from .styles import style_default, updated


def _style_diff(style):
    """Return only entries that differ from the built-in defaults."""
    return {k: v for k, v in style.items()
            if k not in style_default or style_default[k] != v}


def save(doc, path):
    parts = []

    # Stylesheet sections — only written when non-empty
    for name in ('charstyles', 'basestyles', 'liststyles'):
        ss = getattr(doc, name)
        items = ss.items()
        if items:
            parts.append('[%s]' % name)
            for key, style in items:
                diff = _style_diff(style)
                parts.append('"%s" = %s' % (key, serialize_style(diff) or '{}'))
            parts.append('')

    # Document section — always written
    parts.append('[document]')
    endmark = _extract_nl(doc.textmodel.ENDMARK)
    settings = doc.settings if doc.settings else None
    parts.append(serialize(doc.textmodel.texel, endmark, settings))

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(parts) + '\n')


def load(path):
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()

    sections = _split_sections(text)

    if 'document' not in sections:
        raise ValueError("Missing [document] section in %r" % path)

    doc = Document()

    # Stylesheets — all optional
    for attr in ('charstyles', 'basestyles', 'liststyles'):
        if attr in sections:
            for key, style in _parse_stylesheet(sections[attr]).items():
                getattr(doc, attr).set(key, updated(style_default, style))

    # Document content
    root, endmark, settings = parse(sections['document'])
    doc.settings = settings
    doc.textmodel.texel = root
    if endmark is not None:
        doc.textmodel.ENDMARK = endmark

    return doc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r'^\[(\w+)\]\s*$', re.MULTILINE)


def _split_sections(text):
    """Split file content into {section_name: body} dict."""
    parts = _SECTION_RE.split(text)
    # parts = [preamble, name1, body1, name2, body2, ...]
    sections = {}
    it = iter(parts[1:])  # skip preamble (comments before first section)
    for name in it:
        sections[name] = next(it, '').strip()
    return sections


def _parse_stylesheet(text):
    """Parse stylesheet section body into {key: style_dict}."""
    p = _Parser(text)
    styles = {}
    while not p.tok.at_end():
        key = p.parse_string()
        p.tok.consume('EQUALS')
        styles[key] = p.parse_style()
    return styles


def _extract_nl(em):
    """Get the NewLine element from a potentially grouped ENDMARK."""
    if hasattr(em, 'parstyle'):
        return em
    from .textmodel.texeltree import iter_childs
    for _, _, child in iter_childs(em):
        return child
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_00():
    "roundtrip"
    import tempfile, os
    from .textmodel.texeltree import get_text

    doc = Document()
    doc.textmodel = TextModel("Hello world")
    doc.settings = {'author': 'Ada', 'paper': 'Letter'}

    with tempfile.NamedTemporaryFile(
            suffix='.txl', delete=False, mode='w') as f:
        path = f.name
    try:
        doc.save(path)
        doc2 = Document.load(path)
        assert get_text(doc2.textmodel.get_xtexel()) == \
               get_text(doc.textmodel.get_xtexel())
        assert doc2.settings == {'author': 'Ada', 'paper': 'Letter'}
    finally:
        os.unlink(path)


def test_01():
    "stylesheets roundtrip"
    import tempfile, os

    doc = Document()
    doc.textmodel = TextModel("Hi")
    doc.basestyles.set('h1', {'font_size': 18, 'bold': True})
    doc.charstyles.set('em', {'italic': True})

    with tempfile.NamedTemporaryFile(
            suffix='.txl', delete=False, mode='w') as f:
        path = f.name
    try:
        doc.save(path)
        doc2 = Document.load(path)
        assert doc2.basestyles.get('h1')['font_size'] == 18
        assert doc2.basestyles.get('h1')['bold'] == True
        assert doc2.charstyles.get('em')['italic'] == True
    finally:
        os.unlink(path)


def test_03():
    "load einstein.txl"
    import os
    from .textmodel.texeltree import get_text
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, 'test', 'einstein.txl')
    doc = Document.load(path)
    assert doc.basestyles.get('normal') is not None
    style = doc.basestyles.get('normal')
    # Non-default values must be present
    assert abs(style['space_after'] - 14.17) < 0.1
    assert abs(style['first_line_indent'] - 17.01) < 0.1
    assert style['alignment'] == 'justify'
    # In-memory styles are complete: defaults are present too
    assert style['bold'] == False
    assert style['underline'] == False
    assert 'font_size' in style
    text = get_text(doc.textmodel.get_xtexel())
    assert 'Albert Einstein' in text


def test_02():
    "missing sections"
    import tempfile, os

    doc = Document()
    doc.textmodel = TextModel("Minimal")

    with tempfile.NamedTemporaryFile(
            suffix='.txl', delete=False, mode='w') as f:
        path = f.name
    try:
        doc.save(path)
        doc2 = Document.load(path)
        assert doc2.basestyles.items() == []
    finally:
        os.unlink(path)
