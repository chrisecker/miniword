# Example import plugin: EPUB e-books
# Install: copy into the plugins directory (see docs/plugins.md).
#
# Reads the chapters of an EPUB 2 or 3 book in reading order with
# MiniWord's HTML import; each chapter starts on a new page, title and
# author become the document's settings. Uses only the standard library.
#
# From the book's style sheets only bold, italic, strike, superscript and
# subscript are taken, and only for simple selectors (".x", "p.x").
# Footnotes become MiniWord's, also from another file of the book, if the
# book marks them (EPUB 3, DPUB-ARIA, see htmlfilter.note_area).
# Not covered: other links within the book (dropped), books protected by
# DRM.

import base64
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from html import escape
from html.parser import HTMLParser
from urllib.parse import unquote

from miniword.io.importexport import register_import
from miniword.io.htmlfilter import note_area

PROPERTIES = ('font-weight', 'font-style', 'text-decoration',
              'text-decoration-line', 'vertical-align')
IMAGE_TYPES = ('image/jpeg', 'image/png', 'image/gif')  # MiniWord draws
VOID = {'img', 'br', 'hr', 'input', 'meta', 'link', 'col', 'wbr'}


def local(tag):
    """An XML tag without its namespace."""
    return tag.rsplit('}', 1)[-1]


def read_package(z):
    """(title, author, chapters, style sheets, media types by path) of
    the book in zip file z; chapters in reading order (the spine)."""
    container = ET.fromstring(z.read('META-INF/container.xml'))
    opf = next(e.get('full-path') for e in container.iter()
               if local(e.tag) == 'rootfile')
    package = ET.fromstring(z.read(opf))
    folder = posixpath.dirname(opf)
    title = author = ''
    items, types, spine = {}, {}, []
    for e in package.iter():
        tag = local(e.tag)
        if tag == 'title' and not title:
            title = (e.text or '').strip()
        elif tag == 'creator' and not author:
            author = (e.text or '').strip()
        elif tag == 'item':
            path = posixpath.normpath(
                posixpath.join(folder, unquote(e.get('href', ''))))
            items[e.get('id')] = path
            types[path] = e.get('media-type', '')
        elif tag == 'itemref':
            spine.append(e.get('idref'))
    chapters = [items[i] for i in spine if i in items]
    sheets = [p for p, t in types.items() if t == 'text/css']
    return title, author, chapters, sheets, types


def encrypted(z):
    """The paths that the book encrypts (DRM; also obfuscated fonts)."""
    if 'META-INF/encryption.xml' not in z.namelist():
        return set()
    root = ET.fromstring(z.read('META-INF/encryption.xml'))
    return {posixpath.normpath(unquote(e.get('URI', '')))
            for e in root.iter() if local(e.tag) == 'CipherReference'}


def css_rules(text):
    """{(tag, class): declarations} of the simple rules of a style sheet
    (".x" has tag ''), only with the PROPERTIES MiniWord's HTML import
    reads. Rules in @media blocks count as well."""
    rules = {}
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', text):
        declarations = [d.strip() for d in body.split(';')
                        if d.split(':')[0].strip().lower() in PROPERTIES]
        if not declarations:
            continue
        for selector in selectors.split(','):
            m = re.fullmatch(r'([a-zA-Z0-9]*)\.([\w-]+)', selector.strip())
            if m:
                key = (m.group(1).lower(), m.group(2))
                rules[key] = rules.get(key, '') + ';'.join(declarations) + ';'
    return rules


class Chapter(HTMLParser):
    """The body of a chapter as HTML for MiniWord's HTML import: classes
    resolved to style attributes (see css_rules), images embedded, links
    into the book only to footnotes and back.

    links: (footnotes, references) of the whole book, see load; None in
    the first pass, which finds them."""

    def __init__(self, z, path, rules, types, links=None):
        super().__init__()
        self.z, self.path, self.types = z, path, types
        self.names = set(z.namelist())
        self.rules = dict(rules)
        self.links = links
        self.out = []
        self.stack = []        # (tag, with an added span, id, start, in a
                               # footnote area)
        self.in_body = False
        self.skip = 0          # in script, style or svg (except image)
        self.sheet = None      # text of a <style> in the head
        self.notes = {}        # id: HTML of the footnotes found
        self.refs = set()      # ids of links into the book
        self.wanted = []       # (path, id) of footnotes in other files

    def link(self, href, own_id):
        """href of a link in the output, or None (dropped)."""
        if ':' in href:  # into the web
            return href
        name, _, fragment = href.partition('#')
        if not fragment:
            return None
        if own_id:
            self.refs.add(own_id)
        if self.links is None:
            return '#' + fragment
        target = self.resolve(name) if name else self.path
        notes, refs = self.links
        if (target, fragment) in notes:
            if target != self.path:
                self.wanted.append((target, fragment))
            return '#' + fragment
        if (target, fragment) in refs:  # back from a footnote
            return '#' + fragment
        return None

    def style_of(self, tag, attrs):
        css = ''
        for name in (attrs.get('class') or '').split():
            css += self.rules.get(('', name), '')
            css += self.rules.get((tag, name), '')
        return css

    def resolve(self, name):
        """The path in the book of a file name relative to the chapter."""
        return posixpath.normpath(posixpath.join(
            posixpath.dirname(self.path), unquote(name)))

    def image_src(self, src):
        """A data URI of an image of the book, or None."""
        path = self.resolve(src.split('#')[0])
        kind = self.types.get(path, '')
        if kind not in IMAGE_TYPES or path not in self.names:
            return None
        data = base64.b64encode(self.z.read(path)).decode('ascii')
        return 'data:%s;base64,%s' % (kind, data)

    def emit(self, tag, attrs, close=False):
        text = ''.join(' %s="%s"' % (k, escape(v or ''))
                       for k, v in attrs.items())
        self.out.append('<%s%s%s>' % (tag, text, '/' if close else ''))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'body':
            self.in_body = True
        elif tag == 'style' and not self.in_body:
            self.sheet = ''
        if not self.in_body or tag == 'body':
            return
        if tag == 'image' and self.skip:  # a cover page: <svg><image>
            src = attrs.get('xlink:href') or attrs.get('href') or ''
            src = self.image_src(src)
            if src:
                self.emit('img', {'src': src}, close=True)
            return
        if tag in ('script', 'style', 'svg') or self.skip:
            if tag not in VOID:
                self.skip += 1
            return
        css = self.style_of(tag, attrs)
        in_area = note_area(attrs) or any(e[4] for e in self.stack)
        if tag == 'img':
            src = self.image_src(attrs.get('src', ''))
            if src:
                attrs['src'] = src
                self.emit(tag, attrs, close=True)
            return
        if tag == 'a' and 'href' in attrs:
            href = self.link(attrs.pop('href') or '', attrs.get('id'))
            if href:
                attrs['href'] = href
        if tag in VOID:
            self.emit(tag, attrs, close=True)
            return
        span = bool(css) and tag != 'span'
        if css and not span:
            attrs['style'] = css + attrs.get('style', '')
        start = len(self.out)
        self.emit(tag, attrs)
        if span:
            self.out.append('<span style="%s">' % escape(css))
        self.stack.append((tag, span, attrs.get('id'), start, in_area))

    def handle_startendtag(self, tag, attrs):  # e.g. <p/>, <path/>
        self.handle_starttag(tag, attrs)
        if tag not in VOID and tag != 'image':
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == 'style' and self.sheet is not None:
            self.rules.update(css_rules(self.sheet))
            self.sheet = None
        if not self.in_body or tag in VOID:
            return
        if self.skip:
            if tag != 'image':  # (an image doesn't count, see above)
                self.skip -= 1
            return
        if not any(e[0] == tag for e in self.stack):
            return
        while self.stack:
            t, span, ident, start, in_area = self.stack.pop()
            if span:
                self.out.append('</span>')
            self.out.append('</%s>' % t)
            if ident and in_area:  # maybe a footnote
                self.notes[ident] = ''.join(self.out[start:])
            if t == tag:
                break

    def handle_data(self, data):
        if self.sheet is not None:
            self.sheet += data
        elif self.in_body and not self.skip:
            self.out.append(escape(data, quote=False))


def parse(z, path, rules, types, links=None):
    """The chapter at path, parsed (see Chapter)."""
    parser = Chapter(z, path, rules, types, links)
    parser.feed(z.read(path).decode('utf-8', errors='replace'))
    parser.close()
    return parser


def load(path):
    from miniword.core.document import Document
    from miniword.io.htmlfilter import html_text_to_fragment
    from miniword.textmodel.textmodel import TextModel
    doc = Document()
    text = doc.textmodel
    with zipfile.ZipFile(path) as z:
        title, author, chapters, sheets, types = read_package(z)
        if encrypted(z) & set(chapters):
            raise ValueError("The book is protected (DRM).")
        names = set(z.namelist())
        rules = {}
        for sheet in sheets:
            if sheet in names:
                rules.update(css_rules(
                    z.read(sheet).decode('utf-8', errors='replace')))
        chapters = [name for name in chapters if name in names]
        notes, refs = {}, set()  # of the whole book: (path, id)
        for name in chapters:
            parser = parse(z, name, rules, types)
            notes.update(((name, k), v) for k, v in parser.notes.items())
            refs.update((name, k) for k in parser.refs)
        for name in chapters:
            parser = parse(z, name, rules, types, (notes, refs))
            html = ''.join(parser.out) + ''.join(  # footnotes from elsewhere
                '<section role="doc-endnotes">%s</section>' % notes[key]
                for key in dict.fromkeys(parser.wanted))
            chapter = TextModel()
            chapter.texel = html_text_to_fragment(html, doc)
            if not len(chapter):
                continue
            if len(text):
                end = chapter.next_newline(0) + 1  # its first paragraph
                chapter.set_parproperties(0, end, page_break_before=True)
            text.append(chapter)
    if len(text):  # no empty paragraph after the last chapter
        style = text.get_parstyle(len(text) - 1)
        text.remove(len(text) - 1, len(text))
        text.set_parstyle(len(text), style)
    if title:
        doc.set_setting('title', title)
    if author:
        doc.set_setting('author', author)
    return doc


register_import("EPUB", ["epub"], load, lossless=False)


# ---------------------------------------------------------------------------
# Tests (python runtests.py examples/epubfilter.py)
# ---------------------------------------------------------------------------

def make_epub(chapters, css='', images=None, encryption=None):
    """An EPUB file (in a temporary folder) of chapters: [(file name,
    body HTML)], with style sheet css and images {name: data}."""
    import os
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), 'book.epub')
    items = ''.join('<item id="c%d" href="text/%s" '
                    'media-type="application/xhtml+xml"/>' % (i, name)
                    for i, (name, _) in enumerate(chapters))
    items += '<item id="css" href="style.css" media-type="text/css"/>'
    for name in images or {}:
        items += ('<item id="%s" href="images/%s" media-type="image/png"/>'
                  % (name, name))
    spine = ''.join('<itemref idref="c%d"/>' % i
                    for i in range(len(chapters)))
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('mimetype', 'application/epub+zip')
        z.writestr('META-INF/container.xml',
            '<?xml version="1.0"?><container version="1.0" xmlns='
            '"urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
            '<rootfile full-path="OEBPS/content.opf" media-type='
            '"application/oebps-package+xml"/></rootfiles></container>')
        z.writestr('OEBPS/content.opf',
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/'
            'opf" version="3.0"><metadata xmlns:dc="http://purl.org/dc/'
            'elements/1.1/"><dc:title>The Book</dc:title><dc:creator>'
            'A. Author</dc:creator></metadata><manifest>%s</manifest>'
            '<spine>%s</spine></package>' % (items, spine))
        z.writestr('OEBPS/style.css', css)
        for name, data in (images or {}).items():
            z.writestr('OEBPS/images/' + name, data)
        for name, body in chapters:
            z.writestr('OEBPS/text/' + name,
                '<?xml version="1.0" encoding="utf-8"?><html xmlns='
                '"http://www.w3.org/1999/xhtml"><head><title>T</title>'
                '<link rel="stylesheet" href="../style.css"/></head>'
                '<body>%s</body></html>' % body)
        if encryption:
            z.writestr('META-INF/encryption.xml', encryption)
    return path


def paragraphs(doc):
    """[(text, parstyle)] of doc's paragraphs."""
    text = doc.textmodel
    result, i = [], 0
    while i <= len(text):
        j = text.next_newline(i) if i < len(text) else len(text)
        result.append((text.get_text(i, j), text.get_parstyle(i)))
        i = j + 1
    return result


def test_00():
    "chapters in spine order, each on a new page; title and author"
    doc = load(make_epub([('a.xhtml', '<h1>One</h1><p>First.</p>'),
                          ('b.xhtml', '<h1>Two</h1><p>Second.</p>')]))
    pars = paragraphs(doc)
    assert [t for t, _ in pars] == ['One', 'First.', 'Two', 'Second.'], pars
    assert pars[2][1].get('page_break_before') is True, pars
    assert not pars[0][1].get('page_break_before'), pars
    assert pars[3][1].get('base') == 'normal', pars  # the last keeps its style
    assert doc.settings['title'] == 'The Book'
    assert doc.settings['author'] == 'A. Author'


def test_01():
    "classes of the style sheet become formatting; head and links dropped"
    css = ('/* c */ .it { font-style: italic; margin: 0 } p.b { font-weight:'
           ' bold } @media screen { .up { vertical-align: super } }')
    doc = load(make_epub([('a.xhtml',
        '<p>x <span class="it">italic</span> y <a href="b.xhtml#n1" '
        'class="up">1</a></p><p class="b">bold</p>')], css))
    text = doc.textmodel
    assert text.get_text() == 'x italic y 1\nbold', repr(text.get_text())
    assert text.get_style(3).get('italic') is True
    assert text.get_style(11).get('vertical_position') == 'superscript'
    assert 'href' not in text.get_style(11)
    assert text.get_style(13).get('bold') is True
    assert not text.get_style(0).get('italic')


def test_02():
    "images of the book are embedded, also from an SVG cover page"
    import io
    import wx
    from miniword.images.images import Image
    from miniword.images.imageio import content_of
    from miniword.textmodel.utils import iter_leafes
    wx.App()
    stream = io.BytesIO()
    wx.Bitmap(4, 3).ConvertToImage().SaveFile(stream, wx.BITMAP_TYPE_PNG)
    png = stream.getvalue()
    doc = load(make_epub([
        ('cover.xhtml', '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink='
         '"http://www.w3.org/1999/xlink"><rect/><image xlink:href='
         '"../images/c.png"/></svg><p>Cover</p>'),
        ('a.xhtml', '<p>A <img src="../images/c.png" alt="pic"/> b</p>')],
        images={'c.png': png}))
    images = [t for *_, t in iter_leafes(doc.textmodel.texel, 0)
              if isinstance(t, Image)]
    assert len(images) == 2, images
    assert 'Cover' in doc.textmodel.get_text()  # text after the SVG
    assert all(content_of(image) == png for image in images)


def test_03():
    "a book with encrypted chapters is refused"
    encryption = ('<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:'
                  'container" xmlns:enc="http://www.w3.org/2001/04/xmlenc#">'
                  '<enc:EncryptedData><enc:CipherData><enc:CipherReference '
                  'URI="OEBPS/text/a.xhtml"/></enc:CipherData>'
                  '</enc:EncryptedData></encryption>')
    path = make_epub([('a.xhtml', '<p>x</p>')], encryption=encryption)
    try:
        load(path)
    except ValueError:
        pass
    else:
        assert False, "no error"


def test_04():
    "css_rules: simple selectors only, only properties MiniWord reads"
    rules = css_rules('.a, span.b { font-style: italic; color: red }'
                      ' div p.c { font-weight: bold } .d { color: blue }')
    assert rules == {('', 'a'): 'font-style: italic;',
                     ('span', 'b'): 'font-style: italic;'}, rules


def test_05():
    "footnotes: from an endnotes file and in the chapter; other links dropped"
    from miniword.footnotes.footnotes import Footnote
    from miniword.textmodel.textmodel import TextModel
    from miniword.textmodel.utils import iter_leafes
    from miniword.textmodel.texeltree import get_text
    doc = load(make_epub([
        ('toc.xhtml', '<p><a href="a.xhtml#start">Chapter</a></p>'),
        ('a.xhtml', '<p id="start">A<a href="endnotes.xhtml#note-1" '
         'id="noteref-1" epub:type="noteref">1</a> and B<a href="#fn2" '
         'id="ref2" epub:type="noteref">2</a>.</p><aside id="fn2" '
         'epub:type="footnote"><p>Second.</p></aside>'),
        ('endnotes.xhtml', '<section epub:type="endnotes" role="doc-endnotes">'
         '<h2>Endnotes</h2><ol><li id="note-1" epub:type="endnote"><p>The '
         '<i>first</i>. <a href="a.xhtml#noteref-1" epub:type="backlink">'
         '\u21a9</a></p></li></ol></section>')]))
    notes = [t for *_, t in iter_leafes(doc.textmodel.texel, 0)
             if isinstance(t, Footnote)]
    texts = []
    for note in notes:
        model = TextModel()
        model.set_xtexel(note.content)
        texts.append(model)
    assert [m.get_text() for m in texts] == ['The first.', 'Second.'], \
        [m.get_text() for m in texts]
    assert texts[0].get_style(5).get('italic') is True
    mark = get_text(notes[0])  # a footnote's character in the text
    text = doc.textmodel.get_text()  # without the endnotes chapter
    assert text == 'Chapter\nA%s and B%s.' % (mark, mark), repr(text)
    assert doc.textmodel.get_style(0).get('href') is None  # the contents
