"""
HTML of a text fragment, put on the clipboard with every copy (a copy
pasted into a mail program keeps its formatting): paragraphs, headings,
lists, quotes, tables, code, images and footnotes. Formatting as inline
CSS (mail programs drop style sheets), only where it differs from the
normal style, so the pasted text takes on the font of its new place.
"""

import base64
from html import escape
from itertools import groupby

from miniword.io.importexport import register_copy
from miniword.textmodel.styles import EMPTYSTYLE
from miniword.textmodel.texeltree import NewLine, get_text
from miniword.textmodel.utils import iter_leafes


HEADINGS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')
POSITIONS = {'superscript': 'super', 'subscript': 'sub'}
BORDERS = {'thin': '1px solid black', 'thick': '2px solid black',
           'double': '3px double black', 'none': 'none'}


def text_css(style, ref):
    """CSS declarations of the text properties of style (a full style)
    that differ from ref's."""
    def changed(*keys):
        return any(style[key] != ref[key] for key in keys)
    css = []
    if changed('font_family'):
        css.append("font-family:'%s'" % style['font_family'])
    if changed('font_size'):
        css.append('font-size:%gpt' % style['font_size'])
    if changed('bold'):
        css.append('font-weight:%s' % ('bold' if style['bold'] else 'normal'))
    if changed('italic'):
        css.append('font-style:%s'
                   % ('italic' if style['italic'] else 'normal'))
    if changed('underline', 'strike'):
        lines = []
        if style['underline']:
            lines.append('underline')
        if style['strike']:
            lines.append('line-through')
        css.append('text-decoration:%s' % (' '.join(lines) or 'none'))
    if changed('color'):
        css.append('color:%s' % style['color'])
    if changed('bgcolor'):
        css.append('background-color:%s' % style['bgcolor'])
    if changed('vertical_position'):
        css.append('vertical-align:%s'
                   % POSITIONS.get(style['vertical_position'], 'baseline'))
    return css


def par_css(ps, normal, indent, in_list):
    """CSS of a paragraph of the full style ps: its text properties
    (against normal), spacing, alignment, indents, ground."""
    css = text_css(ps, normal)
    left = 0
    if not in_list:
        levels = ps['indent_levels']
        left = levels[min(indent, len(levels) - 1)]
    css.append('margin:%gpt %gpt %gpt %gpt' % (
        ps['space_before'], ps['right_indent'], ps['space_after'], left))
    if ps['alignment'] != 'left':
        css.append('text-align:%s' % ps['alignment'])
    if ps['first_line_indent']:
        css.append('text-indent:%gpt' % ps['first_line_indent'])
    if ps['block_color']:
        css.append('background-color:%s' % ps['block_color'])
    return css


def attr(css):
    """The style attribute of the CSS declarations css, or ''. (Font
    names are in single quotes: those stay.)"""
    if not css:
        return ''
    return ' style="%s"' % escape(';'.join(css), quote=False) \
        .replace('"', '&quot;')


def paragraphs(texels):
    """The paragraphs of texels: lists of their leaves, each ending with
    its newline."""
    par = []
    for texel in texels:
        for _, _, elem in iter_leafes(texel, 0):
            par.append(elem)
            if isinstance(elem, NewLine):
                yield par
                par = []


def image_html(image):
    """An img element of image as shown: its data embedded (cropped: as
    PNG), else its path; its size as drawn."""
    from miniword.images.images import image_mime
    from miniword.images.imageio import decode_cached, content_of, png_of
    data = content_of(image)
    decoded = decode_cached(data) if data else None
    size = ''
    if decoded is not None:
        w, h = decoded.width_px, decoded.height_px
        if image.crop:
            cl, cr, ct, cb = image.crop
            w, h = w - cl - cr, h - ct - cb
            data = png_of(image)
        size = ' width="%d" height="%d"' % (  # 1 px is drawn as 1 pt
            round(w * image.scale_x), round(h * image.scale_y))
    if data:
        src = 'data:%s;base64,%s' % (
            image_mime(data), base64.b64encode(data).decode('ascii'))
    elif image.path:
        src = image.path
    else:
        return ''
    return '<img src="%s" alt="%s"%s>' % (
        escape(src), escape(image.alt), size)


def inline_html(elems, nl, basestyles, notes):
    """HTML of a paragraph's elems (without its newline nl): runs of
    one style a span with what differs from the paragraph, links an a.
    Footnotes are added to notes, shown by their number."""
    from miniword.images.images import Image
    from miniword.textmodel.submodel import Footnote
    from miniword.core.texels import BR
    from miniword.mdelements.checkbox import Checkbox
    from miniword.mdelements.raw import Raw, RawIcon
    runs = []  # (html, style)
    for elem in elems:
        style = getattr(elem, 'style', EMPTYSTYLE)
        if isinstance(elem, Footnote):
            notes.append(elem)
            runs.append(('<sup>%d</sup>' % len(notes), EMPTYSTYLE))
        elif isinstance(elem, Image):
            runs.append((image_html(elem), style))
        elif isinstance(elem, BR):
            runs.append(('<br>', style))
        elif isinstance(elem, Checkbox):
            runs.append((elem.text + ' ', style))
        elif isinstance(elem, (Raw, RawIcon)):  # in the text
            runs.append((raw_html(elem), EMPTYSTYLE))
        else:
            text = escape(get_text(elem), quote=False)
            runs.append((text.replace('\t', ' '), style))
    ps = basestyles.mk_parstyle(nl.parstyle)
    html = []
    for style, group in groupby(runs, key=lambda run: run[1]):
        text = ''.join(run[0] for run in group)
        full = basestyles.mk_style(nl.parstyle, style)
        css = attr(text_css(full, ps))
        if css:
            text = '<span%s>%s</span>' % (css, text)
        if full['href']:
            text = '<a href="%s">%s</a>' % (escape(full['href']), text)
        html.append(text)
    return ''.join(html)


def border(style, key):
    """CSS of a cell's line key ('border_top', ...): missing ones thin."""
    return BORDERS.get(style.get(key, 'thin') or 'none', BORDERS['thin'])


def cell_css(styles, r, c):
    """CSS of cell r, c (styles: the cells' full styles by row): ground
    and lines as the table draws them - between two cells the right or
    lower one's, so a cell has its top and left line only at the edge."""
    style = styles[r][c]
    css = ['padding:2pt 4pt', 'vertical-align:' + style.get('valign', 'top')]
    if r == 0:
        css.append('border-top:' + border(style, 'border_top'))
    if c + 1 < len(styles[r]):
        css.append('border-right:' + border(styles[r][c + 1], 'border_left'))
    else:
        css.append('border-right:' + border(style, 'border_right'))
    if r + 1 < len(styles):
        css.append('border-bottom:' + border(styles[r + 1][c], 'border_top'))
    else:
        css.append('border-bottom:' + border(style, 'border_bottom'))
    if c == 0:
        css.append('border-left:' + border(style, 'border_left'))
    if style.get('cell_bgcolor'):
        css.append('background-color:%s' % style['cell_bgcolor'])
    return css


def table_html(table, basestyles, notes):
    """A table; header rows th."""
    cells, seps = table.childs[1::2], table.childs[2::2]
    n = table.ncols
    styles = [[basestyles.mk_parstyle(sep.parstyle) for sep in seps[i:i + n]]
              for i in range(0, len(seps), n)]
    rows = []
    for r in range(table.nrows):
        tag = 'th' if r < table.nheader else 'td'
        row = []
        for c in range(n):
            k = r * n + c
            content = blocks_html(paragraphs([cells[k], seps[k]]),
                                  basestyles, notes)
            row.append('<%s%s>%s</%s>'
                       % (tag, attr(cell_css(styles, r, c)), content, tag))
        rows.append('<tr>%s</tr>' % ''.join(row))
    return '<table style="border-collapse:collapse">%s</table>' \
        % ''.join(rows)


def block_html(block, basestyles, notes):
    """HTML of a block (see blocks)."""
    from miniword.mdelements.raw import Raw
    Table, Rule, RawIcon, Code = blocks()
    if isinstance(block, Table):
        return table_html(block, basestyles, notes)
    if isinstance(block, Rule):
        return '<hr>'
    if isinstance(block, (Raw, RawIcon)):
        return raw_html(block)
    return blocks_html(paragraphs(block.childs[1:]), basestyles, notes)


def raw_html(raw):
    """Raw (Raw, RawIcon) in HTML: as it is if its language is HTML,
    else nothing."""
    if raw.lang == 'html':
        return raw.source
    return ''


def frames_of(ps, nl, stack):
    """The open elements a paragraph of the full style ps belongs in,
    outermost first: quotes, then a list per indent level. A frame is
    (key, opening tag, closing tag); key: ('quote' / 'ul' / 'ol', level)."""
    frames = []
    for level in range(ps['quote_level']):
        frames.append((('quote', level),
                       '<blockquote style="margin:0 0 0 %gpt;padding-left:'
                       '%gpt;border-left:%gpx solid %s">'
                       % (ps['quote_indent'], ps['quote_indent'],
                          ps['quote_bar_width'], ps['quote_bar_color']),
                       '</blockquote>'))
    lists = [frame for frame in stack if frame[0][0] != 'quote']
    ptype = ps['paragraph_type']
    if ptype == 'continued':  # stays in the list above, if there is one
        return frames + lists[:nl.indent + 1]
    if ptype not in ('list', 'numbered'):
        return frames
    frames += lists[:nl.indent]  # the outer levels stay as they are
    tag = 'ol' if ptype == 'numbered' else 'ul'
    for level in range(len(frames) - ps['quote_level'], nl.indent + 1):
        start = ''
        if tag == 'ol' and level == nl.indent and ps['start_number']:
            start = ' start="%d"' % ps['start_number']
        frames.append(((tag, level),
                       '<%s style="margin:0"%s>' % (tag, start),
                       '</%s>' % tag))
    return frames


def blocks_html(pars, basestyles, notes):
    """HTML of the paragraphs pars (see paragraphs)."""
    from miniword.io.mdfilter import beside_blocks
    normal = basestyles.mk_parstyle(EMPTYSTYLE)
    html = []
    stack = []  # the open frames (see frames_of)
    pre = []    # the lines of a code block in 'pre' paragraphs
    pre_css = []

    def close_pre():
        if pre:
            html.append('<pre%s>%s</pre>' % (attr(pre_css), '\n'.join(pre)))
            pre.clear()

    def enter(frames):  # closes and opens frames as needed
        n = 0
        while n < min(len(stack), len(frames)) \
                and stack[n][0] == frames[n][0]:
            n += 1
        html.extend(frame[2] for frame in reversed(stack[n:]))
        html.extend(frame[1] for frame in frames[n:])
        stack[n:] = frames[n:]

    for elems in (part for par in pars for part in beside_blocks(
            par, blocks())):
        *content, nl = elems
        ps = basestyles.mk_parstyle(nl.parstyle)
        if ps['role'] == 'pre':
            if not pre:  # the block's look: its first line's
                pre_css[:] = text_css(ps, normal) + ['padding:4pt']
                if ps['block_color']:
                    pre_css.append('background-color:%s' % ps['block_color'])
            pre.append(inline_html(content, nl, basestyles, notes))
            continue
        if not content and getattr(nl, 'is_endmark', False):
            continue  # the end of a copy: no paragraph of its own
        close_pre()
        enter(frames_of(ps, nl, stack))
        if len(content) == 1 and isinstance(content[0], blocks()):
            html.append(block_html(content[0], basestyles, notes))
            continue
        in_list = bool(stack) and stack[-1][0][0] != 'quote'
        css = par_css(ps, normal, nl.indent, in_list)
        if ps['role'] in HEADINGS:
            tag = ps['role']
        elif in_list:
            tag = 'li'
        else:
            tag = 'p'
        if in_list and ps['paragraph_type'] == 'continued':
            css.append('list-style:none')
        text = inline_html(content, nl, basestyles, notes) or '<br>'
        html.append('<%s%s>%s</%s>' % (tag, attr(css), text, tag))
    close_pre()
    enter([])
    return ''.join(html)


def blocks():
    """The texels set as blocks of their own, also with text beside (Raw
    only alone in its paragraph, see beside_blocks)."""
    from miniword.tables import Table
    from miniword.mdelements.rule import Rule
    from miniword.mdelements.raw import RawIcon
    from miniword.mdelements.code import Code  # also Raw
    return Table, Rule, RawIcon, Code


def fragment_to_html(textmodel, basestyles):
    """HTML of textmodel (e.g. copied text) with the styles of
    basestyles; its footnotes at the end."""
    notes = []  # grows while their contents are set (notes in notes)
    html = blocks_html(paragraphs([textmodel.get_xtexel()]),
                       basestyles, notes)
    if notes:
        html += '<hr>'
    for i, note in enumerate(notes):
        html += '<div><sup>%d</sup> %s</div>' % (i + 1, blocks_html(
            paragraphs([note.content]), basestyles, notes))
    return '<html><head><meta http-equiv="content-type" ' \
        'content="text/html; charset=utf-8"></head><body>%s</body></html>' \
        % html


register_copy('html', fragment_to_html)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def html_of(textmodel, styles=None):
    from miniword.core.stylesheet import StyleSheet
    from miniword.core.styles import normal, h0
    basestyles = StyleSheet()
    basestyles.set('normal', normal)
    basestyles.set('h1', h0)
    for key, style in (styles or {}).items():
        basestyles.set(key, style)
    html = fragment_to_html(textmodel, basestyles)
    return html[html.index('<body>') + 6:html.index('</body>')]


def test_00():
    "Plain paragraphs: escaped, no text CSS"
    from miniword.textmodel import TextModel
    html = html_of(TextModel('a<b\nc'))
    assert html.count('<p ') == 2, html
    assert 'a&lt;b' in html
    assert 'font' not in html and 'color' not in html


def test_01():
    "Color, bold and links of runs; headings by their role"
    from miniword.textmodel import TextModel
    from miniword.textmodel.styles import Style
    model = TextModel('Title\nred bold link')
    model.set_parstyle(0, Style(base='h1'))
    model.set_properties(6, 9, color='red')
    model.set_properties(10, 14, bold=True)
    model.set_properties(15, 19, href='http://x.org')
    html = html_of(model)
    assert html.startswith('<h1 style="font-size:18pt;font-weight:bold'), \
        html
    assert '<span style="color:red">red</span>' in html, html
    assert '<span style="font-weight:bold">bold</span>' in html, html
    assert '<a href="http://x.org">link</a>' in html, html


def test_02():
    "Lists nest by indent; numbered ones are ol"
    from miniword.textmodel import TextModel
    from miniword.textmodel.styles import Style
    model = TextModel('a\nb\nc\nd')
    for i in (0, 2, 4):
        model.set_parstyle(i, Style(paragraph_type='list'))
    model.set_parstyle(4, Style(paragraph_type='numbered'))
    model.set_indent(4, 1)
    html = html_of(model)
    assert html.index('<ul') < html.index('<li') < html.index('<ol'), html
    assert html.count('<li') == 3 and html.count('</ul>') == 1, html
    assert '</ol></ul><p' in html, html


def test_03():
    "Table cells: lines as drawn (none set: thin), valign, header rows th"
    from miniword.textmodel import TextModel
    from miniword.textmodel.styles import Style
    from miniword.textmodel.texeltree import Text, grouped
    from miniword.tables import Table
    table = Table(*[(Text(t), Style()) for t in 'abc'],
                  (Text('d'), Style(valign='middle')), ncols=2, nheader=1)
    model = TextModel()
    model.set_texel(grouped([table]))
    html = html_of(model)
    assert html.count('<th') == 2 and html.count('<td') == 2, html
    assert 'border-top:1px solid black' in html
    # inner lines once: a cell's right and bottom ones
    assert html.count('border-left') == 2, html
    assert html.count('vertical-align:top') == 3, html
    assert 'vertical-align:middle' in html, html


def test_04():
    "A code block: one pre, escaped, with its style's ground"
    from miniword.textmodel import TextModel
    from miniword.mdelements.code import Code
    from miniword.textmodel.texeltree import grouped
    from miniword.core.styles import updated, normal
    model = TextModel()
    model.set_texel(grouped([Code.from_text('a < b\nc')]))
    pre = updated(normal, dict(name='Pre', role='pre',
                               font_family='Courier New',
                               block_color='#eee'))
    html = html_of(model, {'pre': pre})
    assert html.startswith("<pre style=\"font-family:'Courier New';"), html
    assert 'background-color:#eee">a &lt; b\nc</pre>' in html, html


def test_05():
    "Footnotes: numbered in the text, their text at the end"
    from miniword.textmodel import TextModel
    from miniword.textmodel.submodel import Footnote
    from miniword.textmodel.texeltree import Text, NL, ENDMARK, grouped
    note = Footnote(grouped([Text('note'), ENDMARK]))
    model = TextModel()
    model.set_texel(grouped([Text('text'), note, NL]))
    html = html_of(model)
    assert 'text<sup>1</sup></p><hr><div><sup>1</sup> <p' in html, html
    assert '>note</p></div>' in html, html


def test_06():
    "Quotes: a blockquote per level, around lists too"
    from miniword.textmodel import TextModel
    from miniword.textmodel.styles import Style
    model = TextModel('a\nb\nc')
    model.set_parstyle(0, Style(quote_level=1))
    model.set_parstyle(2, Style(quote_level=2, paragraph_type='list'))
    html = html_of(model)
    assert html.count('<blockquote') == 2, html
    assert '</li></ul></blockquote></blockquote><p' in html, html


def test_07():
    "A cropped image: only its part (a PNG), at the size drawn"
    import io
    import cairocffi as cairo
    from miniword.textmodel import TextModel
    from miniword.textmodel.texeltree import NL, grouped
    from miniword.images.images import Image
    from miniword.images.imageio import pixel_size
    stream = io.BytesIO()
    cairo.ImageSurface(cairo.FORMAT_ARGB32, 10, 8).write_to_png(stream)
    image = Image(stream.getvalue(), scale_x=2, scale_y=2, crop=(1, 2, 3, 1))
    model = TextModel()
    model.set_texel(grouped([image, NL]))
    html = html_of(model)
    assert 'width="14" height="8"' in html, html
    src = html[html.index('base64,') + 7:]
    png = base64.b64decode(src[:src.index('"')])
    assert pixel_size(png) == (7, 4), pixel_size(png)


def test_08():
    "A table beside text in one paragraph: a block of its own"
    from miniword.textmodel import TextModel
    from miniword.textmodel.styles import Style
    from miniword.textmodel.texeltree import Text, NL, grouped
    from miniword.tables import Table
    table = Table((Text('cell'), Style()), ncols=1)
    model = TextModel()
    model.set_texel(grouped([Text('before'), table, Text('after'), NL]))
    html = html_of(model)
    assert '>before</p><table' in html, html
    assert '</table><p' in html and '>after</p>' in html, html
