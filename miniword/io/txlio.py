"""
TXL file format — load and save for Document objects.

File structure (all sections except [document] are optional):

    [basestyles]
    "h1" = {font_size=18, bold, name="Header 1", role="h1"}

    [document]
    PROPS({author="Ada"})
    T("Hello")
    NL({base="h1"})
    T("First item.")
    NL({indent=1, base="bullet"})
    ENDMARK

    [blobs]
    "photo.png" = "base64encodeddata..."

Sections are found by name; files before 2026-11 have [blobs] before
[document] and are read as well.
"""

import re
import base64
import os
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

    # Document section — always written
    parts.append('[document]')
    endmark = _extract_nl(doc.textmodel.ENDMARK)
    settings = doc.settings if doc.settings else None
    parts.append(serialize(doc.textmodel.texel, endmark, settings,
                           os.path.dirname(os.path.abspath(path))))

    blobs = blobs_section(doc.textmodel.texel)  # last: long base64 data
    if blobs:
        parts += [''] + blobs

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(parts) + '\n')


def blobs_section(texel):
    """Lines of the [blobs] section for the images in texel, [] if there
    are none. Keyed by blob_key: equal data is written once, and there
    are no unused blobs."""
    from ..images.images import iter_images, blob_key
    blobs = {}
    for image in iter_images(texel):
        if image.content:
            blobs[blob_key(image.content)] = image.content
    if not blobs:
        return []
    lines = ['[blobs]']
    for key, data in blobs.items():
        lines.append('"%s" = "%s"' % (key, base64.b64encode(data).decode('ascii')))
    lines.append('')
    return lines


def dumps(model):
    """A copied part of a text (a TextModel) as TXL text, for the
    clipboard: [document] without ENDMARK and settings, then [blobs].
    Image paths stay absolute."""
    parts = ['[document]', serialize(model.texel)]
    blobs = blobs_section(model.texel)
    if blobs:
        parts += [''] + blobs
    return '\n'.join(parts) + '\n'


def loads(text):
    """The TextModel of TXL text from dumps. Raises ParseError (or
    ValueError) for anything else."""
    sections = _split_sections(text)
    if 'document' not in sections:
        raise ValueError("Missing [document] section")
    blobs = {}
    if 'blobs' in sections:
        blobs = _parse_blobs(sections['blobs'])
    root, endmark, settings = parse(sections['document'], blobs)
    model = TextModel()
    model.texel = root
    return model


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

    # Blobs — optional; they hydrate the Image texels (one bytes object
    # per blob, shared by all texels using it)
    blobs = {}
    if 'blobs' in sections:
        blobs = _parse_blobs(sections['blobs'])

    # Document content
    root, endmark, settings = parse(
        sections['document'], blobs, os.path.dirname(os.path.abspath(path)))
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
    "blobs roundtrip: one blob per image data, keyed by blob_key"
    import tempfile, os
    from ..textmodel.texeltree import grouped
    from ..images.images import Image, iter_images, blob_key

    data = b'\x89PNG\r\n\x1a\nfakedata'
    doc = Document()
    doc.textmodel = TextModel("Hello")
    doc.textmodel.texel = grouped(
        [Image(data, alt='Photo'), doc.textmodel.texel, Image(data)])

    with tempfile.NamedTemporaryFile(
            suffix='.txl', delete=False, mode='w') as f:
        path = f.name
    try:
        doc.save(path)
        with open(path) as f:
            text = f.read()
        assert text.count('"%s" = ' % blob_key(data)) == 1
        doc2 = Document.load(path)
        images = list(iter_images(doc2.textmodel.texel))
        assert [image.content for image in images] == [data, data]
        assert images[0].content is images[1].content
        assert images[0].alt == 'Photo'
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


def test_05():
    "old files: block_padding in basestyles and paragraphs -> block_offset"
    import tempfile, os
    from ..textmodel.texeltree import Group, Text, NewLine

    doc = Document()
    doc.textmodel.texel = Group([
        Text('code'), NewLine().set_parstyle({'base': 'code',
                                              'block_offset': 2})])
    doc.basestyles.set('code', dict(style_default, block_color='#eee',
                                    block_offset=4))

    with tempfile.NamedTemporaryFile(
            suffix='.txl', delete=False, mode='w') as f:
        path = f.name
    try:
        doc.save(path)
        text = open(path).read()
        assert text.count('block_offset') == 2
        open(path, 'w').write(text.replace('block_offset', 'block_padding'))
        doc2 = Document.load(path)
        code = doc2.basestyles.get('code')
        assert code['block_offset'] == 4 and 'block_padding' not in code
        nl = doc2.textmodel.texel.childs[-1]
        assert nl.parstyle.get('block_offset') == 2
        assert 'block_padding' not in nl.parstyle
    finally:
        os.unlink(path)


def test_06():
    "clipboard: dumps/loads keep text, styles, paragraphs and images"
    from ..textmodel.texeltree import Group, Text, NewLine, get_text
    from ..textmodel.styles import create_style
    from ..images import Image
    from ..images.images import iter_images
    style = create_style(bold=True)
    img = Image(b'\x89PNG data', alt='Photo', path='/tmp/a.png',
                relative=True)
    model = TextModel()
    model.texel = Group([Text('ab', style), img,
                         NewLine().set_parstyle({'base': 'h1'}),
                         Text('cd')])
    model2 = loads(dumps(model))
    assert get_text(model2.texel) == get_text(model.texel)
    assert model2.texel.childs[0].style is style
    assert model2.get_parstyle(0)['base'] == 'h1'
    img2, = iter_images(model2.texel)
    assert img2.content == img.content and img2.alt == 'Photo'
    assert img2.path == '/tmp/a.png' and img2.relative


def test_07():
    "clipboard: loads rejects text that is not from dumps"
    from .texeltreeformat import ParseError
    for text in ['', 'hello', '[document]\nos.system("x")',
                 '[document]\nT(']:
        try:
            loads(text)
        except (ValueError, ParseError):
            pass
        else:
            assert False, text


def test_08():
    "[blobs] is written after [document]; the old order is read as well"
    import tempfile
    from ..textmodel.texeltree import Group, Text, ENDMARK
    from ..images import Image
    from ..images.images import iter_images
    doc = Document()
    doc.textmodel.texel = Group([Text('a'), Image(b'\x89PNG data'), ENDMARK])
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, 'new.txl')
        save(doc, path)
        text = open(path, encoding='utf-8').read()
        assert text.index('[document]') < text.index('[blobs]')
        document, blobs = text.split('\n[blobs]\n')
        old = os.path.join(folder, 'old.txl')
        with open(old, 'w', encoding='utf-8') as f:
            f.write('[blobs]\n' + blobs + '\n' + document)
        for p in (path, old):
            img, = iter_images(load(p).textmodel.texel)
            assert img.content == b'\x89PNG data'
