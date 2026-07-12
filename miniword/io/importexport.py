"""
Import/export filter registry.

Built-in filters (Plain Text) are registered at module load time.
Plugins can register additional filters via register_import / register_export.

Filter tuples:
  _import_filters: (name, [ext, ...], load_fn, lossless)
  _export_filters: (name, [ext, ...], save_fn, lossless, check_fn)
"""

_import_filters = []
_export_filters = []


def register_import(name, extensions, fn, lossless=False):
    _import_filters.append((name, extensions, fn, lossless))


def register_export(name, extensions, fn, lossless=False, check_fn=None):
    _export_filters.append((name, extensions, fn, lossless, check_fn))


def find_import_filter(path):
    entry = _find_entry(path, _import_filters)
    return entry[2] if entry else None


def find_export_filter(path):
    entry = _find_entry(path, _export_filters)
    return entry[2] if entry else None


def check_export(path, doc):
    """Return list of warnings for exporting doc to path. Empty = lossless."""
    entry = _find_entry(path, _export_filters)
    if entry is None:
        return []
    _name, _exts, _fn, lossless, check_fn = entry
    if lossless:
        return []
    if check_fn is not None:
        return check_fn(doc)
    return ["This format may not preserve all document features."]


def open_file(path):
    """Load or import path based on extension. Sets doc.home_format.

    Before using the extension-based filter, the file content is sniffed.
    If the content looks like TXL format, the TXL loader is used regardless
    of the file extension. This handles misnamed files (e.g. .md with TXL
    content saved by an older version of the save dialog).

    Raises ValueError if no filter is found for the extension.
    """
    import os
    ext = os.path.splitext(path)[1].lstrip('.').lower()

    if _sniff_txl(path):
        from .txlio import load
        doc = load(path)
        doc.home_format = 'txl'
        return doc

    if ext == 'txl':
        from .txlio import load
        doc = load(path)
        doc.home_format = 'txl'
        return doc

    fn = find_import_filter(path)
    if fn is None:
        raise ValueError("No import filter for '.%s' files." % ext)
    doc = fn(path)
    doc.home_format = ext
    return doc


def _sniff_txl(path):
    """Return True if file content looks like TXL format."""
    import re
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            head = f.read(512)
        return bool(re.match(
            r'^\[(?:document|basestyles|charstyles|liststyles|blobs)\]',  # compat
            head.lstrip()))
    except Exception:
        return False


def open_wildcard():
    """Wildcard for Open dialog: all supported files (default), then TXL,
    then each registered import format individually."""
    all_exts = ['txl'] + [e for _n, extensions, _fn, _l in _import_filters for e in extensions]
    all_pattern = ';'.join('*.' + e for e in all_exts)
    parts = ['All supported files (%s)|%s' % (all_pattern, all_pattern),
             "TXL files (*.txl)|*.txl"]
    for name, extensions, _fn, _lossless in _import_filters:
        pattern = ';'.join('*.' + e for e in extensions)
        parts.append('%s (%s)|%s' % (name, pattern, pattern))
    parts.append('All files (*.*)|*.*')
    return '|'.join(parts)


def saveas_wildcard():
    """Wildcard for Save As dialog: TXL + all registered export formats."""
    parts = ["TXL files (*.txl)|*.txl"]
    for name, extensions, _fn, _lossless, _check in _export_filters:
        pattern = ';'.join('*.' + e for e in extensions)
        parts.append('%s (%s)|%s' % (name, pattern, pattern))
    parts.append('All files (*.*)|*.*')
    return '|'.join(parts)


def import_wildcard():
    return _build_wildcard(_import_filters, all_supported=True)


def export_wildcard():
    return _build_wildcard(_export_filters)


def saveas_default_ext(filter_index):
    """Return the default extension for a saveas_wildcard filter index, or None."""
    exts = ['txl'] + [e[1][0] for e in _export_filters] + [None]
    return exts[filter_index] if filter_index < len(exts) else None


def export_default_ext(filter_index):
    """Return the default extension for an export_wildcard filter index, or None."""
    exts = [e[1][0] for e in _export_filters] + [None]
    return exts[filter_index] if filter_index < len(exts) else None


def _find_entry(path, filters):
    import os
    ext = os.path.splitext(path)[1].lstrip('.').lower()
    for entry in filters:
        if ext in entry[1]:
            return entry
    return None


def _build_wildcard(filters, all_supported=False):
    parts = []
    if all_supported:
        all_exts = [e for _name, extensions, *_rest in filters for e in extensions]
        pattern = ';'.join('*.' + e for e in all_exts)
        parts.append('All supported files (%s)|%s' % (pattern, pattern))
    for entry in filters:
        name, extensions = entry[0], entry[1]
        pattern = ';'.join('*.' + e for e in extensions)
        parts.append('%s (%s)|%s' % (name, pattern, pattern))
    parts.append('All files (*.*)|*.*')
    return '|'.join(parts)


# ---------------------------------------------------------------------------
# Built-in: Plain Text
# ---------------------------------------------------------------------------

def _load_txt(path):
    from ..core.document import Document
    from ..textmodel.textmodel import TextModel
    with open(path, encoding='utf-8') as f:
        text = f.read()
    doc = Document()
    doc.textmodel = TextModel(text)
    return doc


def _save_txt(doc, path):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(doc.textmodel.get_text())


def _check_txt(doc):
    from ..textmodel.utils import iter_paragraphs
    from ..textmodel.texeltree import NewLine
    issues = set()
    texel = doc.textmodel.get_xtexel()
    for _i1, _i2, elems in iter_paragraphs(texel, 0):
        nl = elems[-1]
        if not isinstance(nl, NewLine):
            continue
        ps = nl.parstyle
        if ps.get('base', 'normal') != 'normal':
            issues.add("paragraph styles (headings, code blocks)")
        if ps.get('paragraph_type', 'normal') != 'normal':
            issues.add("list formatting")
        for elem in elems[:-1]:
            style = getattr(elem, 'style', {})
            if style.get('bold') or style.get('italic'):
                issues.add("bold/italic formatting")
            if any(k not in ('bold', 'italic') for k in style):
                issues.add("character formatting (fonts, colors, etc.)")
    return sorted(issues)


register_import("Plain Text", ["txt"], _load_txt, lossless=False)
register_export("Plain Text", ["txt"], _save_txt, lossless=False, check_fn=_check_txt)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_00():
    "roundtrip plain text"
    import tempfile, os
    from ..core.document import Document
    from ..textmodel.textmodel import TextModel

    doc = Document()
    doc.textmodel = TextModel("Hello world")

    with tempfile.NamedTemporaryFile(
            suffix='.txt', delete=False, mode='w') as f:
        path = f.name
    try:
        _save_txt(doc, path)
        doc2 = _load_txt(path)
        assert doc2.textmodel.get_text() == "Hello world"
    finally:
        os.unlink(path)


def test_01():
    "find_filter by extension"
    assert find_import_filter("readme.txt") is _load_txt
    assert find_export_filter("out.txt") is _save_txt
    assert find_import_filter("file.xyz") is None


def test_02():
    "wildcard contains Plain Text"
    wc = import_wildcard()
    assert "Plain Text" in wc
    assert "*.txt" in wc


def test_03():
    "open_wildcard includes TXL"
    wc = open_wildcard()
    assert "*.txl" in wc
    assert "Plain Text" in wc


def test_03b():
    "open_wildcard and import_wildcard default to 'All supported files'"
    for wc in (open_wildcard(), import_wildcard()):
        first = wc.split('|')[0]
        assert first.startswith("All supported files")

    # export/saveas are unaffected -- no combined "all supported" entry
    for wc in (export_wildcard(), saveas_wildcard()):
        assert "All supported files" not in wc


def test_04():
    "check_export plain text warns about formatting"
    from ..core.document import Document
    from ..textmodel.textmodel import TextModel
    doc = Document()
    doc.textmodel = TextModel("Hello")
    # plain text with no styling → no warnings
    warns = check_export("out.txt", doc)
    assert warns == []


def test_05():
    "check_export unknown format returns empty list"
    from ..core.document import Document
    doc = Document()
    warns = check_export("out.xyz", doc)
    assert warns == []
