# HTML paste import for Miniword.
#
# Converts the HTML clipboard flavor (present alongside plain text when
# copying rendered rich content from a browser or an AI chat UI) into a
# texel fragment, insertable into an already-open document.
#
# Not a general-purpose HTML importer: covers the tag subset such sources
# actually produce -- paragraphs, headings, bold/italic, lists (incl.
# nesting), blockquote, pre/code, tables, links, strike, sup/sub,
# bold/italic/strike/sup/sub from CSS, images (data URIs embedded, else
# linked), footnotes (marked as DPUB-ARIA, EPUB or Markdown tools do,
# see note_area).

import re
from html.parser import HTMLParser
import codecs

from miniword.io.importexport import register_paste


from miniword.io.mdfilter import (
    _register_styles, _build_blocks, _adopt_existing_styles, image_run, _RULE,
    quoted)

_WHITESPACE_RE = re.compile(r'\s+')


def _positive_int(value, default=1):
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default

_HEADINGS = {'h1': 'h1', 'h2': 'h2', 'h3': 'h3', 'h4': 'h4', 'h5': 'h5', 'h6': 'h6'}
_BOLD_TAGS = {'strong', 'b'}
_ITALIC_TAGS = {'em', 'i'}
_STRIKE_TAGS = {'s', 'del', 'strike'}
_POSITIONS = {'sup': 'superscript', 'sub': 'subscript',
              'super': 'superscript'}  # tags and CSS vertical-align


def clipboard_html(data):
    """The clipboard's HTML flavor (bytes) as text: UTF-16 (Firefox on
    Linux: with a byte order mark or zero bytes) or UTF-8."""
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        text = data.decode('utf-16', errors='replace')
    elif b'\x00' in data[:200]:
        text = data.decode('utf-16-le', errors='replace')
    else:
        text = data.decode('utf-8', errors='replace')
    return text.rstrip('\x00')


def _length(value):
    """Pixels of an HTML length ('250', '250px'), else None (e.g. '50%')."""
    try:
        return float(value.strip().removesuffix('px'))
    except (AttributeError, ValueError):
        return None


def _css_props(style):
    """Char props from a CSS style attribute: bold, italic, strike,
    superscript/subscript."""
    props = {}
    for item in style.split(';'):
        key, _, value = (s.strip().lower() for s in item.partition(':'))
        if key == 'font-weight':
            props['bold'] = value in ('bold', 'bolder') or \
                (value.isdigit() and int(value) >= 600)
        elif key == 'font-style':
            props['italic'] = value in ('italic', 'oblique')
        elif key in ('text-decoration', 'text-decoration-line') \
                and 'line-through' in value:
            props['strike'] = True
        elif key == 'vertical-align' and value in _POSITIONS:
            props['vertical_position'] = _POSITIONS[value]
    return props
_BLOCK_TAGS = ({'p', 'blockquote', 'pre', 'li', 'table',
                'tr', 'th', 'td'} | set(_HEADINGS))


_INLINE_TAGS = _BOLD_TAGS | _ITALIC_TAGS | _STRIKE_TAGS | {
    'code', 'sup', 'sub', 'span', 'a', 'br', 'img', 'input'}
_AREA_TYPES = {'footnote', 'footnotes', 'endnote', 'endnotes',
               'rearnote', 'rearnotes'}   # epub:type
_NOTE_TYPES = {'footnote', 'endnote', 'rearnote'}


def note_area(attrs):
    """Whether an element's attrs mark footnotes: DPUB-ARIA roles, EPUB
    types, pandoc and markdown-it (class footnotes), GitHub
    (data-footnotes)."""
    return attrs.get('role') in ('doc-endnotes', 'doc-footnote',
                                 'doc-endnote') \
        or bool(_AREA_TYPES & set((attrs.get('epub:type') or '').split())) \
        or 'footnotes' in (attrs.get('class') or '').split() \
        or 'data-footnotes' in attrs


def single_note(attrs):
    """Whether a note area (see note_area) is one footnote, not a list."""
    return attrs.get('role') in ('doc-footnote', 'doc-endnote') \
        or bool(_NOTE_TYPES & set((attrs.get('epub:type') or '').split()))


def special(props):
    """Whether a run is an image, a <br>, ... (see mdfilter._special)."""
    return any(k.startswith('_') for k in props)


def strip_runs(runs):
    """Drop the whitespace (and a <br>) at the ends of runs."""
    drop_last_br(runs)
    while runs and not runs[0][0].strip() and not special(runs[0][1]):
        del runs[0]
    while runs and not runs[-1][0].strip() and not special(runs[-1][1]):
        del runs[-1]
    if runs:
        runs[0] = (runs[0][0].lstrip(), runs[0][1])
        runs[-1] = (runs[-1][0].rstrip(), runs[-1][1])


def drop_last_br(runs):
    """Drop a <br> at the end of a block (as a browser does): it gives an
    empty block its height, e.g. <p><br></p>, and breaks no line."""
    for i in range(len(runs) - 1, -1, -1):
        text, props = runs[i]
        if props.get('_br'):
            del runs[i]
            return
        if text.strip() or special(props):
            return  # text, an image, ... after it


class _HTMLBlockBuilder(HTMLParser):
    """Walks HTML and produces a block list: (ptype, indent, runs) or
    ('table', grid) tuples, fed into mdfilter._build_blocks()."""

    def __init__(self, load=False):
        super().__init__(convert_charrefs=True)
        self.load = load             # load web images now (paste)
        self.blocks = []
        self._runs = []              # current block's accumulated runs
        self._block_stack = [('normal', 0)]   # (ptype, indent), outermost first
        self._list_stack = []        # 'list' | 'numbered', outermost first
        self._items = []             # open <li>: [ptype, indent, first]
        self._quotes = 0             # open <blockquote>
        self._props_stack = [{}]     # current inline char-props
        self._in_pre = False
        self.lang = ''               # of <pre><code class="language-x">
        self._table = None           # grid being accumulated, or None
        self._row = None             # {col: text} for the current row, or None
        self._col = 0                # next column index to fill in the current row
        self._pending_rowspans = {}  # {col: rows still to skip}, from earlier rows
        self._rowspans_before_row = set()
        self._cell_text = None       # current cell's runs, or None
        self._cell_span = (1, 1)     # (colspan, rowspan) of the cell being read
        self._anchors = []   # [runs, start, end, target, id] of <a href="#x">
        self._area = None    # [tag, depth] of the open footnote area
        self._note = None    # [tag, depth, id, runs] of the footnote read
        self._notes = {}     # id: runs of the footnotes

    # --- helpers ---

    @property
    def _props(self):
        return self._props_stack[-1]

    def _flush_block(self):
        drop_last_br(self._runs)
        # whitespace only (e.g. around a browser's fragment): no block
        if any(t.strip() or p.get('_image') for t, p in self._runs):
            ptype, indent = self._block_stack[-1]
            if self._items and ptype in ('normal', self._items[-1][0]):
                ptype, indent = self._item_block()  # (a <p> in an <li>)
            if self._quotes and ptype == 'normal':
                ptype = 'quote'  # (a <p> in a <blockquote>)
            self._add((ptype, indent, self._runs))
        self._runs = []

    def _add(self, block):
        """Add block, as deep in quotes as the open <blockquote>."""
        for _ in range(self._quotes):
            block = quoted(block)
        self.blocks.append(block)

    def _item_block(self):
        """(ptype, indent) of a block in the open <li>: its first one is
        the item, further ones continue it."""
        item = self._items[-1]
        ptype, indent, first = item
        item[2] = False
        return (ptype if first else 'continued'), indent

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
        self._runs_here().append((text, dict(props or self._props)))

    def _runs_here(self):
        """Where runs go: the footnote being read, the current table cell,
        else the block; in a footnote area outside a footnote: nowhere."""
        if self._note is not None:
            return self._note[3]
        if self._area is not None:
            return []
        return self._runs if self._cell_text is None else self._cell_text

    def _area_start(self, tag, attrs):
        """A start tag in a footnote area: footnotes (elements with an id)
        are collected, the rest is dropped. False: handle tag as usual (an
        inline tag in a footnote)."""
        first = self._area is None
        if first:
            self._area = [tag, 0]
        if self._note is None and attrs.get('id') and \
                (single_note(attrs) or not first):
            self._note = [tag, 0, attrs['id'], []]
        if tag == self._area[0]:
            self._area[1] += 1
        note = self._note
        if note is None:
            return True
        if tag == note[0]:
            note[1] += 1
        if tag == 'p' and any(t.strip() for t, _ in note[3]):
            note[3].append(('', {'_br': True}))  # a second paragraph
        return tag not in _INLINE_TAGS

    def _area_end(self, tag):
        """An end tag in a footnote area (see _area_start)."""
        note = self._note
        inline = note is not None and tag in _INLINE_TAGS
        if note is not None and tag == note[0]:
            note[1] -= 1
            if not note[1]:
                self._notes[note[2]] = note[3]
                self._note = None
        if tag == self._area[0]:
            self._area[1] -= 1
            if not self._area[1]:
                self._area = None
        return not inline

    def _resolve_notes(self):
        """Links to footnotes become footnotes; the links back from them
        are dropped. Back to front, so the indices before stay valid."""
        notes = self._notes
        refs = {a[4] for a in self._anchors if a[3] in notes and a[4]}
        anchors = sorted(self._anchors, key=lambda a: -a[1])
        numbered = set()  # notes that start with a link back (pandoc: "1.")
        for runs, start, end, target, _ in anchors:
            if target in refs:  # a link back, e.g. "↩"
                del runs[start:end]
                if not ''.join(t for t, _ in runs[:start]).strip():
                    numbered.add(id(runs))
        for note in notes.values():  # after deleting by index
            strip_runs(note)
            if id(note) in numbered and note and note[0][0]:
                note[0] = (note[0][0].lstrip('.): '), note[0][1])
        for runs, start, end, target, _ in anchors:
            if notes.get(target):
                runs[start:end] = [('', {'_footnote': notes[target]})]

    # --- HTMLParser callbacks ---

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self._area is not None or note_area(attrs):
            if self._area_start(tag, attrs):
                return
        if tag in _HEADINGS:
            self._start_block(_HEADINGS[tag], 0)
        elif tag == 'blockquote':
            self._start_block('quote', 0)
            self._quotes += 1
        elif tag == 'pre':
            self._start_block('pre', 0)
            self._in_pre, self.lang = True, ''
        elif tag == 'code' and self._in_pre:
            m = re.search(r'language-(\S+)', attrs.get('class') or '')
            self.lang = m.group(1) if m else ''
        elif tag in ('ul', 'ol'):
            self._list_stack.append('numbered' if tag == 'ol' else 'list')
        elif tag == 'li':
            ptype = self._list_stack[-1] if self._list_stack else 'list'
            indent = max(0, len(self._list_stack) - 1)
            self._start_block(ptype, indent)
            self._items.append([ptype, indent, True])
        elif tag == 'p':
            self._start_block('normal', 0)
        elif tag == 'hr' and \
                'footnotes-sep' in (attrs.get('class') or '').split():
            pass  # markdown-it's, before the footnotes
        elif tag == 'hr':
            self._flush_block()
            self._add(_RULE)
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
        elif tag in ('sup', 'sub'):
            self._props_stack.append(dict(
                self._props, vertical_position=_POSITIONS[tag]))
        elif tag == 'span' or tag in _STRIKE_TAGS:
            props = dict(self._props, **_css_props(attrs.get('style', '')))
            if tag in _STRIKE_TAGS:
                props['strike'] = True
            self._props_stack.append(props)
        elif tag == 'a' and attrs.get('href'):
            self._props_stack.append(dict(self._props, href=attrs['href']))
            if attrs['href'].startswith('#'):  # maybe to a footnote
                runs = self._runs_here()
                self._anchors.append([runs, len(runs), None,
                                      attrs['href'][1:], attrs.get('id')])
        elif tag == 'br' and self._in_pre:
            self._append('\n')
        elif tag == 'br':  # a line break in the paragraph
            self._runs_here().append(('', {'_br': True}))
        elif tag == 'input' and attrs.get('type') == 'checkbox':
            self._runs_here().append(('', {'_checkbox': 'checked' in attrs}))
        elif tag == 'img' and attrs.get('src'):  # in a link: with its href
            size = _length(attrs.get('width')), _length(attrs.get('height'))
            text, image = image_run(
                attrs.get('alt') or '', attrs['src'], size, self.load)
            self._runs_here().append((text, dict(self._props, **image)))

    def handle_endtag(self, tag):
        if self._area is not None and self._area_end(tag):
            return
        if tag == 'a' and self._anchors and self._anchors[-1][2] is None:
            self._anchors[-1][2] = len(self._anchors[-1][0])
        if tag in _HEADINGS or tag == 'blockquote' or tag == 'li' or tag == 'p':
            self._end_block()
            if tag == 'li' and self._items:
                self._items.pop()
            if tag == 'blockquote':
                self._quotes = max(0, self._quotes - 1)
        elif tag == 'pre':  # a code block
            text = ''.join(t for t, _ in self._runs).rstrip('\n')
            block = ('code', text.split('\n'), self.lang)
            if self._items:  # more of a list item
                block += ('continued', self._item_block()[1])
            self._add(block)
            self._runs = []
            if len(self._block_stack) > 1:
                self._block_stack.pop()
            self._in_pre = False
        elif tag in ('ul', 'ol'):
            if self._list_stack:
                self._list_stack.pop()
        elif tag in ('td', 'th'):
            text = self._cell_text  # its runs
            drop_last_br(text)
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
        elif tag in _BOLD_TAGS or tag in _ITALIC_TAGS or tag == 'code' \
                or tag == 'a' or tag == 'span' or tag in _STRIKE_TAGS \
                or tag in ('sup', 'sub'):
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
            self._row[self._col] = self._cell_text
            self._cell_text = None
        if self._row is not None:
            self._end_row()
        if self._table is not None:
            self._flush_table()
        self._flush_block()
        for anchor in self._anchors:  # left open
            if anchor[2] is None:
                anchor[2] = len(anchor[0])
        self._resolve_notes()


def html_text_to_fragment(html, target_doc, load=False):
    """Parse an HTML clipboard flavor into a texel fragment for insertion
    into an already-open document (e.g. via Editor.insert_texel()).

    Paragraphs whose role (heading, list, ...) target_doc already has a
    style for adopt that style's name (see mdfilter._adopt_existing_styles),
    so HTML-paste matches the target document's own look instead of a
    second, disconnected style under the parser's canonical name; any
    other roles get the standard styles registered as a fallback (mirrors
    md_text_to_fragment, so HTML-paste and Markdown-paste converge on the
    same style vocabulary). Embedded (data-URI) images carry their data
    in the Image texels (equal data interned, see mdfilter._build_blocks).
    """
    from types import SimpleNamespace
    from miniword.textmodel.textmodel import TextModel

    builder = _HTMLBlockBuilder(load)
    builder.feed(html)
    builder.close()

    shim = SimpleNamespace(textmodel=TextModel(''))
    _build_blocks(shim, builder.blocks)

    covered = _adopt_existing_styles(shim.textmodel, target_doc)
    _register_styles(target_doc, overwrite=False, skip=covered)
    return shim.textmodel.texel


def html_clipboard_fragment(data, document):
    """Paste of the clipboard's HTML flavor (bytes, see clipboard_html);
    web images are loaded now (their size gives their scale)."""
    return html_text_to_fragment(clipboard_html(data), document, load=True)


register_paste('html', html_clipboard_fragment)


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
        basestyle = doc.basestyles.base_style(nl.parstyle) or style_default
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
    assert base == 'normal'  # body text: the document's normal style
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
    "a pre block becomes a code block (Code) of its lines"
    from miniword.core.document import Document
    from miniword.io.mdfilter import code_texts
    texel = html_text_to_fragment("<pre>line one\nline two</pre>",
                                  Document())
    assert code_texts(texel) == [('', 'line one\nline two')]


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
    from miniword.images.images import iter_images

    html = '<p>Before <img src="data:image/png;base64,%s" alt="photo.png"> after</p>' % b64
    doc = Document()
    texel = html_text_to_fragment(html, doc)
    images = list(iter_images(texel))
    assert [(image.content, image.alt) for image in images] == \
        [(doc_data, 'photo.png')]


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
    assert bases['Body text.'] == 'normal'
    assert not doc.basestyles.contains('h1')


def test_18():
    "an image in a link keeps its link"
    from miniword.core.document import Document
    from miniword.images.images import Image
    from miniword.textmodel.utils import iter_leafes
    texel = html_text_to_fragment(
        '<p><a href="http://x/ci"><img src="http://x/b.png" alt="b"></a></p>',
        Document())
    images = [t for *_, t in iter_leafes(texel, 0) if isinstance(t, Image)]
    assert [image.style.get('href') for image in images] == ['http://x/ci']


def test_19():
    "sup and sub, as tags and as CSS vertical-align (as htmlexport writes)"
    pars = _parse('<p>x<sup>2</sup> H<sub>3</sub>O'
                  ' a<span style="vertical-align:super">b</span>'
                  ' c<span style="vertical-align:sub">d</span></p>')
    styles = {t: s for t, s in pars[0][3]}
    assert styles['2'].get('vertical_position') == 'superscript', pars
    assert styles['3'].get('vertical_position') == 'subscript', pars
    assert styles['b'].get('vertical_position') == 'superscript', pars
    assert styles['d'].get('vertical_position') == 'subscript', pars
    assert 'vertical_position' not in styles['O a'], pars


def test_20():
    "<br> breaks the line in a paragraph, a cell and code; not at the end"
    from miniword.core.document import Document
    from miniword.core.texels import BR
    from miniword.io.mdfilter import code_texts
    from miniword.textmodel.utils import iter_leafes
    texel = html_text_to_fragment(
        '<p>Roses are red,<br>violets blue.<br> </p><p><br></p><p>End</p>',
        Document())
    brs = [t for *_, t in iter_leafes(texel, 0) if isinstance(t, BR)]
    assert len(brs) == 1, brs  # not the one at the end
    assert len(_parse('<p>a<br>b</p><p><br></p><p>End</p>')) == 2  # as before
    builder = _HTMLBlockBuilder()
    builder.feed('<table><tr><td>a<br>b<br></td></tr></table>')
    builder.close()
    cell = builder.blocks[0][1][0][0]
    assert cell == [('a', {}), ('', {'_br': True}), ('b', {})], cell
    assert code_texts(html_text_to_fragment('<pre>x<br>y</pre>',
                                            Document())) == [('', 'x\ny')]


def test_21():
    "footnotes as pandoc, markdown-it, EPUB and GitHub write them"
    from miniword.core.document import Document
    from miniword.footnotes.footnotes import Footnote
    from miniword.textmodel.textmodel import TextModel
    from miniword.textmodel.utils import iter_leafes
    from miniword.textmodel.texeltree import get_text
    html = (
        # pandoc
        '<p>A<a href="#fn1" class="footnote-ref" id="fnref1" role='
        '"doc-noteref"><sup>1</sup></a> and <a href="#sec">a link</a>.</p>'
        '<section id="footnotes" class="footnotes" role="doc-endnotes"><hr/>'
        '<ol>\n<li id="fn1">\n<p>The <em>first</em> note.<a href="#fnref1" '
        'class="footnote-back" role="doc-backlink">\u21a9\ufe0e</a></p></li>'
        '</ol></section>'
        # markdown-it
        '<p>B<sup class="footnote-ref"><a href="#mfn1" id="mfnref1">[1]</a>'
        '</sup></p><hr class="footnotes-sep"><section class="footnotes"><ol>'
        '<li id="mfn1"><p>Second <a href="#mfnref1">\u21a9</a></p></li></ol>'
        '</section>'
        # pandoc's EPUB: the number is the link back
        '<p>P<a href="#pfn1" id="pfnref1" epub:type="noteref">1</a></p>'
        '<section epub:type="footnotes"><aside epub:type="footnote" id="pfn1">'
        '\n<p><a href="#pfnref1" role="doc-backlink">1</a>. Pandoc.</p>'
        '</aside></section>'
        # EPUB, a note of two paragraphs
        '<p>C<a epub:type="noteref" href="#n1">1</a></p><aside id="n1" '
        'epub:type="footnote"><p>Third,</p><p>two paragraphs.</p></aside>'
        # GitHub
        '<p>D<sup><a href="#gfn-1" id="gfnref-1" data-footnote-ref>1</a>'
        '</sup></p><section data-footnotes class="footnotes"><h2 id="label">'
        'Footnotes</h2><ol><li id="gfn-1"><p>Fourth <a href="#gfnref-1" '
        'data-footnote-backref>\u21a9</a></p></li></ol></section>')
    model = TextModel()
    model.texel = html_text_to_fragment(html, Document())
    notes = [t for *_, t in iter_leafes(model.texel, 0)
             if isinstance(t, Footnote)]

    def text(note):
        m = TextModel()
        m.set_xtexel(note.content)
        return m

    assert [text(n).get_text() for n in notes] == [
        'The first note.', 'Second', 'Pandoc.', 'Third,\x0btwo paragraphs.',
        'Fourth'], [text(n).get_text() for n in notes]
    assert text(notes[0]).get_style(4).get('italic') is True
    t = model.get_text()
    mark = get_text(notes[0])  # a footnote's character in the text
    assert t == 'A%s and a link.\nB%s\nP%s\nC%s\nD%s\n' % ((mark,) * 5), \
        repr(t)
    link = model.get_style(t.index('a link'))
    assert link.get('href') == '#sec', link  # not to a footnote: kept
