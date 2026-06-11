"""
TXL file format — load and save for Document objects.

File structure (all sections except [document] are optional):

    [basestyles]
    "h1" = {font_size=18, bold, name="Header 1", role="h1"}

    [blobs]
    "photo.png" = "base64encodeddata..."

    [document]
    PROPS({author="Ada"})
    T("Hello")
    NL({base="h1"})
    T("First item.")
    NL({indent=1, base="bullet"})
    ENDMARK
"""

import re
import base64
from ..core.document import Document
from ..textmodel.textmodel import TextModel
from .texeltreeformat import serialize, parse, serialize_style, _Parser
from ..core.styles import style_default, updated


def _style_diff(style):
    """Return only entries that differ from the built-in defaults.

    Tuple values are trimmed: trailing elements that match the default are
    removed so that only the meaningful prefix needs to be stored.
    """
    result = {}
    for k, v in style.items():
        if k not in style_default:
            result[k] = v
            continue
        default = style_default[k]
        if v == default:
            continue
        if isinstance(v, tuple) and isinstance(default, tuple) and len(v) == len(default):
            v = _trim_tuple(v, default)
        result[k] = v
    return result


def _trim_tuple(val, default):
    """Remove trailing elements of val that equal the corresponding default."""
    i = len(val)
    while i > 1 and val[i - 1] == default[i - 1]:
        i -= 1
    return val[:i]


def _extend_tuples(style):
    """Extend short tuple values to the length expected by structure_default."""
    result = {}
    for k, v in style.items():
        default = style_default.get(k)
        if (isinstance(v, tuple) and isinstance(default, tuple)
                and len(v) < len(default)):
            v = v + default[len(v):]
        result[k] = v
    return result


def save(doc, path):
    parts = []

    # basestyles section — only written when non-empty (beyond built-in 'normal')
    items = [(k, v) for k, v in doc.basestyles.items() if k != 'normal']
    if items:
        parts.append('[basestyles]')
        for key, style in items:
            diff = _style_diff(style)
            parts.append('"%s" = %s' % (key, serialize_style(diff) or '{}'))
        parts.append('')

    # Blobs section — only written when non-empty; unused blobs are dropped
    from ..images.images import collect_blob_ids
    used = collect_blob_ids(doc.textmodel.texel)
    blobs = {k: v for k, v in doc.blobs.items() if k in used}
    if blobs:
        parts.append('[blobs]')
        for key, data in blobs.items():
            parts.append('"%s" = "%s"' % (key, base64.b64encode(data).decode('ascii')))
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

    # basestyles — optional (charstyles/liststyles silently ignored for compat)
    if 'basestyles' in sections:
        for key, style in _parse_stylesheet(sections['basestyles']).items():
            doc.basestyles.set(key, updated(style_default, style))

    # Blobs — optional
    if 'blobs' in sections:
        doc.blobs = _parse_blobs(sections['blobs'])

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


def _parse_blobs(text):
    """Parse blobs section body into {key: bytes}."""
    p = _Parser(text)
    blobs = {}
    while not p.tok.at_end():
        key = p.parse_string()
        p.tok.consume('EQUALS')
        b64 = p.parse_string()
        blobs[key] = base64.b64decode(b64)
    return blobs


def _parse_stylesheet(text):
    """Parse stylesheet section body into {key: style_dict}."""
    p = _Parser(text)
    styles = {}
    while not p.tok.at_end():
        key = p.parse_string()
        p.tok.consume('EQUALS')
        styles[key] = _extend_tuples(p.parse_style())
    return styles


def _extract_nl(em):
    """Get the NewLine element from a potentially grouped ENDMARK."""
    if hasattr(em, 'parstyle'):
        return em
    from ..textmodel.texeltree import iter_childs
    for _, _, child in iter_childs(em):
        return child
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_00():
    "roundtrip"
    import tempfile, os
    from ..textmodel.texeltree import get_text

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
    "basestyles roundtrip"
    import tempfile, os

    doc = Document()
    doc.textmodel = TextModel("Hi")
    doc.basestyles.set('h1', {'font_size': 18, 'bold': True})

    with tempfile.NamedTemporaryFile(
            suffix='.txl', delete=False, mode='w') as f:
        path = f.name
    try:
        doc.save(path)
        doc2 = Document.load(path)
        assert doc2.basestyles.get('h1')['font_size'] == 18
        assert doc2.basestyles.get('h1')['bold'] == True
    finally:
        os.unlink(path)


def test_03():
    "load einstein.txl"
    import os
    from ..textmodel.texeltree import get_text
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(here, 'test', 'einstein.txl')
    doc = Document.load(path)
    h1 = doc.basestyles.get('h1')
    assert h1 is not None
    assert h1['bold'] == True
    assert h1['font_size'] == 18
    h2 = doc.basestyles.get('h2')
    assert h2 is not None
    assert h2['bold'] == True
    assert h2['font_size'] == 16
    text = get_text(doc.textmodel.get_xtexel())
    assert 'Albert Einstein' in text


def test_04():
    "blobs roundtrip: only blobs referenced by Image texels are kept"
    import tempfile, os
    from ..textmodel.texeltree import grouped
    from ..images.images import Image

    doc = Document()
    doc.textmodel = TextModel("Hello")
    doc.textmodel.texel = grouped([Image('photo.png'), doc.textmodel.texel])
    doc.blobs = {'photo.png': b'\x89PNG\r\nfakedata', 'logo.jpg': b'\xff\xd8fake'}

    with tempfile.NamedTemporaryFile(
            suffix='.txl', delete=False, mode='w') as f:
        path = f.name
    try:
        doc.save(path)
        doc2 = Document.load(path)
        assert doc2.blobs == {'photo.png': b'\x89PNG\r\nfakedata'}
    finally:
        os.unlink(path)


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
        assert '[basestyles]' not in open(path).read()
        doc2 = Document.load(path)
        assert doc2.basestyles.get('normal') is not None
        assert len(doc2.basestyles.items()) == 1
    finally:
        os.unlink(path)
