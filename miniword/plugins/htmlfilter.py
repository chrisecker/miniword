# HTML paste import for Miniword.
#
# Converts the HTML clipboard flavor (present alongside plain text when
# copying rendered rich content from a browser or an AI chat UI) into a
# texel fragment, insertable into an already-open document.
#
# Not a general-purpose HTML importer: covers the tag subset such sources
# actually produce -- paragraphs, headings, bold/italic, lists (incl.
# nesting), blockquote, pre/code, tables, links, data-URI images. Not
# covered (Markdown-paste-only for now): footnotes, sup/sub/strike.

import re
from html.parser import HTMLParser
from base64 import b64decode

from miniword.plugins.mdfilter import (
    _register_styles, _build_blocks, _adopt_existing_styles)

_WHITESPACE_RE = re.compile(r'\s+')


def _positive_int(value, default=1):
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default

_HEADINGS = {'h1': 'h1', 'h2': 'h2', 'h3': 'h3', 'h4': 'h4', 'h5': 'h5', 'h6': 'h6'}
_BOLD_TAGS = {'strong', 'b'}
_ITALIC_TAGS = {'em', 'i'}
_BLOCK_TAGS = ({'p', 'blockquote', 'pre', 'li', 'table',
                'tr', 'th', 'td'} | set(_HEADINGS))


class _HTMLBlockBuilder(HTMLParser):
    """Walks HTML and produces the same block list shape as
    mdfilter._parse_md_paragraphs: a list of (ptype, indent, runs) or
    ('table', grid) tuples, fed into mdfilter._build_blocks()."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self._runs = []              # current block's accumulated runs
        self._block_stack = [('normal', 0)]   # (ptype, indent), outermost first
        self._list_stack = []        # 'list' | 'numbered', outermost first
        self._props_stack = [{}]     # current inline char-props
        self._in_pre = False
        self._table = None           # grid being accumulated, or None
        self._row = None             # {col: text} for the current row, or None
        self._col = 0                # next column index to fill in the current row
        self._pending_rowspans = {}  # {col: rows still to skip}, from earlier rows
        self._rowspans_before_row = set()
        self._cell_text = None       # current cell's accumulated text, or None
        self._cell_span = (1, 1)     # (colspan, rowspan) of the cell being read
        self._img_count = 0

    # --- helpers ---

    @property
    def _props(self):
        return self._props_stack[-1]

    def _flush_block(self):
        if self._runs:
            ptype, indent = self._block_stack[-1]
            self.blocks.append((ptype, indent, self._runs))
        self._runs = []

    def _start_block(self, ptype, indent):
        """Flush whatever the enclosing block had accumulated so far (e.g.
        an outer <li>'s lead-in text before a nested <ul>), then push the
        new block context."""
        self._flush_block()
        self._block_stack.append((ptype, indent))

    def _end_block(self):
        self._flush_block()
        if len(self._block_stack) > 1:
            self._block_stack.pop()

    def _flush_table(self):
        if self._table:
            # normalize to a rectangular grid -- a source table copied
            # incomplete (e.g. missing trailing cells), or one using
            # colspan/rowspan (which miniword's Table model has no concept
            # of), would otherwise build a ragged Table texel and corrupt
            # layout downstream. Cells "covered" by a span are approximated
            # as blank, since there is no merged-cell representation to
            # degrade to instead.
            n_cols = max(len(row) for row in self._table)
            for row in self._table:
                while len(row) < n_cols:
                    row.append('')
            self.blocks.append(('table', self._table))
        self._table = None

    def _skip_reserved_columns(self):
        """Advance self._col past any column still reserved by a rowspan
        that started in an earlier row of this table."""
        while self._pending_rowspans.get(self._col, 0) > 0:
            self._col += 1

    def _start_row(self):
        self._row = {}
        self._col = 0
        # remember which reservations were already active when this row
        # started, so _end_row only decays those -- a reservation a cell
        # in *this* row just created must survive untouched into the row
        # after this one, not this one's own end
        self._rowspans_before_row = set(self._pending_rowspans)

    def _end_row(self):
        if self._row:
            width = max(self._row) + 1
            self._table.append([self._row.get(c, '') for c in range(width)])
        self._row = None
        self._col = 0
        for c in self._rowspans_before_row:
            if c not in self._pending_rowspans:
                continue
            self._pending_rowspans[c] -= 1
            if self._pending_rowspans[c] <= 0:
                del self._pending_rowspans[c]

    def _append(self, text, props=None):
        if not text:
            return
        if self._cell_text is not None:
            self._cell_text.append(text)
            return
        self._runs.append((text, dict(props or self._props)))

    # --- HTMLParser callbacks ---

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in _HEADINGS:
            self._start_block(_HEADINGS[tag], 0)
        elif tag == 'blockquote':
            self._start_block('quote', 0)
        elif tag == 'pre':
            self._start_block('pre', 0)
            self._in_pre = True
        elif tag in ('ul', 'ol'):
            self._list_stack.append('numbered' if tag == 'ol' else 'list')
        elif tag == 'li':
            ptype = self._list_stack[-1] if self._list_stack else 'list'
            indent = max(0, len(self._list_stack) - 1)
            self._start_block(ptype, indent)
        elif tag == 'p':
            self._start_block('normal', 0)
        elif tag == 'table':
            self._table = []
            self._pending_rowspans = {}
        elif tag == 'tr':
            self._start_row()
        elif tag in ('td', 'th'):
            self._skip_reserved_columns()
            self._cell_text = []
            self._cell_span = (_positive_int(attrs.get('colspan')),
                                _positive_int(attrs.get('rowspan')))
        elif tag in _BOLD_TAGS:
            self._props_stack.append(dict(self._props, bold=True))
        elif tag in _ITALIC_TAGS:
            self._props_stack.append(dict(self._props, italic=True))
        elif tag == 'code':
            self._props_stack.append(dict(self._props, font_family='Courier New'))
        elif tag == 'a' and attrs.get('href'):
            self._props_stack.append(dict(self._props, href=attrs['href']))
        elif tag == 'br':
            self._append(' ')
        elif tag == 'img':
            src = attrs.get('src', '')
            if 'base64,' in src:
                self._img_count += 1
                blob_id = attrs.get('alt') or 'pasted_image_%d.png' % self._img_count
                data = b64decode(src.split('base64,', 1)[1])
                self._runs.append(('', {'_image': (blob_id, data)}))

    def handle_endtag(self, tag):
        if tag in _HEADINGS or tag == 'blockquote' or tag == 'li' or tag == 'p':
            self._end_block()
        elif tag == 'pre':
            for line in ''.join(t for t, _ in self._runs).splitlines() or ['']:
                self.blocks.append(('pre', 0, [(line or ' ', {})]))
            self._runs = []
            if len(self._block_stack) > 1:
                self._block_stack.pop()
            self._in_pre = False
        elif tag in ('ul', 'ol'):
            if self._list_stack:
                self._list_stack.pop()
        elif tag in ('td', 'th'):
            text = ''.join(self._cell_text)
            self._cell_text = None
            colspan, rowspan = self._cell_span
            for i in range(colspan):
                self._row[self._col] = text if i == 0 else ''
                if rowspan > 1:
                    self._pending_rowspans[self._col] = (
                        self._pending_rowspans.get(self._col, 0) + rowspan - 1)
                self._col += 1
        elif tag == 'tr':
            self._end_row()
        elif tag == 'table':
            self._flush_table()
        elif tag in _BOLD_TAGS or tag in _ITALIC_TAGS or tag == 'code' or tag == 'a':
            if len(self._props_stack) > 1:
                self._props_stack.pop()

    def handle_data(self, data):
        if not self._in_pre:
            # collapse runs of HTML whitespace to a single space, like a
            # browser would, but don't drop a whitespace-only text node
            # entirely -- that's the only content of e.g. Safari's
            # <span class="Apple-converted-space"> </span>, and dropping
            # it would fuse two words together
            data = _WHITESPACE_RE.sub(' ', data)
        if data:
            self._append(data)

    def close(self):
        super().close()
        # defensively close any table/row/cell left open by truncated
        # source markup (e.g. an incomplete clipboard selection), instead
        # of silently dropping it
        if self._cell_text is not None:
            self._row[self._col] = ''.join(self._cell_text)
            self._cell_text = None
        if self._row is not None:
            self._end_row()
        if self._table is not None:
            self._flush_table()
        self._flush_block()


def html_text_to_fragment(html, target_doc):
    """Parse an HTML clipboard flavor into a texel fragment for insertion
    into an already-open document (e.g. via Editor.insert_texel()).

    Paragraphs whose role (heading, list, ...) target_doc already has a
    style for adopt that style's name (see mdfilter._adopt_existing_styles),
    so HTML-paste matches the target document's own look instead of a
    second, disconnected style under the parser's canonical name; any
    other roles get the standard styles registered as a fallback (mirrors
    md_text_to_fragment, so HTML-paste and Markdown-paste converge on the
    same style vocabulary). Embedded (data-URI) images are routed into
    target_doc's own blob store.
    """
    from types import SimpleNamespace
    from miniword.textmodel.textmodel import TextModel

    builder = _HTMLBlockBuilder()
    builder.feed(html)
    builder.close()

    shim = SimpleNamespace(textmodel=TextModel(''), blobs=target_doc.blobs)
    _build_blocks(shim, builder.blocks)

    covered = _adopt_existing_styles(shim.textmodel, target_doc)
    _register_styles(target_doc, overwrite=False, skip=covered)
    return shim.textmodel.texel


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _parse(html):
    """Parse an HTML string and return list of (base, ptype, indent, runs),
    mirroring mdfilter.py's own _parse() test helper."""
    from miniword.core.document import Document
    from miniword.textmodel.textmodel import TextModel
    from miniword.textmodel.utils import iter_paragraphs
    from miniword.textmodel.texeltree import NewLine, get_text
    from miniword.core.styles import style_default, updated

    doc = Document()
    texel = html_text_to_fragment(html, doc)
    model = TextModel()
    model.texel = texel

    result = []
    for i1, i2, elems in iter_paragraphs(model.get_xtexel(), 0):
        nl = elems[-1]
        if not isinstance(nl, NewLine):
            continue
        basestyle = doc.basestyles.get(nl.parstyle.get('base', 'normal')) or style_default
        ps     = updated(basestyle, nl.parstyle)
        base   = ps.get('base', 'normal')
        ptype  = ps.get('paragraph_type', 'normal')
        indent = nl.indent
        runs   = [(get_text(e), dict(getattr(e, 'style', {})))
                  for e in elems[:-1]
                  if get_text(e)]
        if runs:
            result.append((base, ptype, indent, runs))
    return result


def test_00():
    "normal paragraph"
    pars = _parse("<p>Hello world</p>")
    assert len(pars) == 1
    base, ptype, indent, runs = pars[0]
    assert base == 'body'
    assert ''.join(t for t, _ in runs) == 'Hello world'


def test_01():
    "headings h1-h3"
    pars = _parse("<h1>Title</h1><h2>Sub</h2><h3>Sub sub</h3>")
    assert [p[0] for p in pars] == ['h1', 'h2', 'h3']
    assert ''.join(t for t, _ in pars[0][3]) == 'Title'


def test_02():
    "bold and italic"
    pars = _parse("<p>Normal <strong>bold</strong> <em>italic</em> end</p>")
    runs = pars[0][3]
    styles = {t: s for t, s in runs}
    assert styles['bold'].get('bold') == True
    assert styles['italic'].get('italic') == True


def test_03():
    "inline code"
    pars = _parse("<p>Use <code>print()</code> here</p>")
    styles = {t: s for t, s in pars[0][3]}
    assert 'Courier' in styles['print()'].get('font_family', '')


def test_04():
    "unordered list, top-level items have indent 0"
    pars = _parse("<ul><li>Alpha</li><li>Beta</li></ul>")
    assert len(pars) == 2
    for base, ptype, indent, runs in pars:
        assert ptype == 'list'
        assert indent == 0
    assert ''.join(t for t, _ in pars[0][3]) == 'Alpha'


def test_05():
    "nested list has deeper indent"
    pars = _parse("<ul><li>Top<ul><li>Nested</li></ul></li></ul>")
    indents = [p[2] for p in pars]
    assert indents == sorted(indents)
    assert indents[-1] > indents[0]


def test_06():
    "ordered list"
    pars = _parse("<ol><li>First</li><li>Second</li></ol>")
    for base, ptype, indent, runs in pars:
        assert ptype == 'numbered'


def test_07():
    "blockquote"
    pars = _parse("<blockquote>Quoted text</blockquote>")
    assert pars[0][0] == 'quote'
    assert ''.join(t for t, _ in pars[0][3]) == 'Quoted text'


def test_08():
    "pre block, one paragraph per line"
    pars = _parse("<pre>line one\nline two</pre>")
    assert len(pars) == 2
    for base, ptype, indent, runs in pars:
        assert base == 'pre'
    assert ''.join(t for t, _ in pars[0][3]) == 'line one'
    assert ''.join(t for t, _ in pars[1][3]) == 'line two'


def test_09():
    "table import"
    from miniword.core.document import Document
    from miniword.textmodel.utils import iter_paragraphs
    from miniword.textmodel.texeltree import get_text
    from miniword.tables import Table as TableTexel
    from miniword.textmodel.textmodel import TextModel

    html = ("<table><thead><tr><th>A</th><th>B</th></tr></thead>"
            "<tbody><tr><td>C</td><td>D</td></tr></tbody></table>")
    doc = Document()
    texel = html_text_to_fragment(html, doc)
    model = TextModel()
    model.texel = texel

    table = None
    for i1, i2, elems in iter_paragraphs(model.get_xtexel(), 0):
        content = elems[:-1]
        if content and isinstance(content[0], TableTexel):
            table = content[0]
    assert table is not None
    assert table.nrows == 2
    assert table.ncols == 2
    cells = table.childs[1::2]
    assert [get_text(c) for c in cells] == ['A', 'B', 'C', 'D']


def test_10():
    "hyperlink"
    pars = _parse('<p>Visit <a href="https://python.org">Python</a> today</p>')
    styles = {t: s for t, s in pars[0][3]}
    assert styles['Python'].get('href') == 'https://python.org'


def test_11():
    "data-URI image"
    doc_data = b'\x89PNG\r\nfakedata'
    import base64
    b64 = base64.b64encode(doc_data).decode('ascii')
    from miniword.core.document import Document
    from miniword.images.images import collect_blob_ids

    html = '<p>Before <img src="data:image/png;base64,%s" alt="photo.png"> after</p>' % b64
    doc = Document()
    texel = html_text_to_fragment(html, doc)
    assert doc.blobs.get('photo.png') == doc_data
    assert collect_blob_ids(texel) == {'photo.png'}


def test_12():
    "html_text_to_fragment doesn't clobber a document's own existing style"
    from miniword.core.document import Document

    doc = Document()
    custom_h1 = {'font_size': 99}
    doc.basestyles.set('h1', custom_h1)
    html_text_to_fragment("<h1>Title</h1>", doc)
    assert doc.basestyles.get('h1') == custom_h1


def _table_grid(html):
    """Parse html and return the first table's cell texts as a 2-D list,
    or None if there's no table. Shared by the span/ragged-table tests."""
    from miniword.core.document import Document
    from miniword.textmodel.textmodel import TextModel
    from miniword.textmodel.utils import iter_paragraphs
    from miniword.textmodel.texeltree import get_text
    from miniword.tables import Table as TableTexel

    doc = Document()
    texel = html_text_to_fragment(html, doc)
    model = TextModel()
    model.texel = texel
    for i1, i2, elems in iter_paragraphs(model.get_xtexel(), 0):
        content = elems[:-1]
        if content and isinstance(content[0], TableTexel):
            t = content[0]
            cells = [get_text(c) for c in t.childs[1::2]]
            return [cells[i:i + t.ncols] for i in range(0, len(cells), t.ncols)]
    return None


def test_13():
    "incomplete/ragged table (a real copy-paste case: source had a missing cell)"
    grid = _table_grid("<table><tr><td>A</td><td>B</td></tr><tr><td>C</td></tr></table>")
    assert grid == [['A', 'B'], ['C', '']]


def test_14():
    "colspan: the spanned columns are approximated as blank (no merge support)"
    grid = _table_grid(
        "<table><tr><th colspan='2'>Header</th></tr>"
        "<tr><td>A</td><td>B</td></tr></table>")
    assert grid == [['Header', ''], ['A', 'B']]


def test_15():
    "rowspan: the column is reserved (blank) in the rows it spans into"
    grid = _table_grid(
        "<table><tr><td rowspan='2'>R</td><td>A</td></tr>"
        "<tr><td>B</td></tr></table>")
    assert grid == [['R', 'A'], ['', 'B']]


def test_16():
    "combined rowspan+colspan, followed by an unaffected normal row"
    grid = _table_grid(
        "<table><tr><td rowspan='2' colspan='2'>RC</td><td>X</td></tr>"
        "<tr><td>Y</td></tr>"
        "<tr><td>Z1</td><td>Z2</td><td>Z3</td></tr></table>")
    assert grid == [['RC', '', 'X'], ['', '', 'Y'], ['Z1', 'Z2', 'Z3']]


def test_17():
    "html_text_to_fragment adopts an existing role-tagged style under a different name"
    from miniword.core.document import Document
    from miniword.textmodel.textmodel import TextModel
    from miniword.textmodel.utils import iter_paragraphs
    from miniword.textmodel.texeltree import NewLine, get_text

    doc = Document()
    doc.basestyles.set('MyHeading', {'role': 'h1', 'font_size': 42})

    texel = html_text_to_fragment("<h1>Title</h1><p>Body text.</p>", doc)
    model = TextModel()
    model.texel = texel

    bases = {}
    for i1, i2, elems in iter_paragraphs(model.get_xtexel(), 0):
        nl = elems[-1]
        if isinstance(nl, NewLine):
            text = ''.join(get_text(e) for e in elems[:-1])
            if text:
                bases[text] = nl.parstyle.get('base')

    assert bases['Title'] == 'MyHeading'
    assert bases['Body text.'] == 'body'
    assert not doc.basestyles.contains('h1')
