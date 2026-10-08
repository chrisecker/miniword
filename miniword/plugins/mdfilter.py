# Markdown import/export plugin for Miniword
#
# Install: copy to ~/.miniword/plugins/ or import at app startup:
#   from examples.mdfilter import *  (registers the filters)
#
# Parses with mistune (a dependency of Miniword).

import base64
import html
import os
import re

from miniword.io.importexport import register_import, register_export, \
    register_paste_as

_BR = re.compile(r'<br\s*/?>', re.I)


# ---------------------------------------------------------------------------
# Export: Document → Markdown
# ---------------------------------------------------------------------------

_folder = ''  # folder of the file read or written (relative image paths)


def _save(doc, path):
    global _folder
    _folder = os.path.dirname(os.path.abspath(path))
    try:
        md = _doc_to_md(doc)
    finally:
        _folder = ''
    with open(path, 'w', encoding='utf-8') as f:
        f.write(md)


def _doc_to_md(doc):
    from miniword.textmodel.utils import iter_paragraphs
    from miniword.textmodel.texeltree import get_text
    from miniword.textmodel.utils import iter_leafes
    from miniword.textmodel.texeltree import NewLine
    from miniword.tables import Table as TableTexel
    from miniword.core.styles import style_default, updated

    texel          = doc.textmodel.get_xtexel()
    parts          = []
    footnotes      = []
    prev_block_key = None
    in_pre         = False
    markers        = []  # list markers of the items above, by level

    def close_pre():
        nonlocal in_pre
        if in_pre:
            parts.append('```')
            in_pre = False

    for i1, i2, elems in iter_paragraphs(texel, 0):
        nl = elems[-1]
        if not isinstance(nl, NewLine):
            close_pre()
            continue  # ENDMARK — skip

        content = elems[:-1]
        if len(content) == 1 and isinstance(content[0], TableTexel):
            close_pre()
            if parts:
                parts.append('')
            parts.extend(_table_to_md(content[0]))
            prev_block_key = None
            continue

        basestyle = doc.basestyles.get(nl.parstyle.get('base', 'normal')) or style_default
        ps     = updated(basestyle, nl.parstyle)
        base   = ps.get('base', 'normal')
        ptype  = ps.get('paragraph_type', 'normal')
        indent = nl.indent

        inline = _elems_to_inline(content, footnotes, plain=base == 'pre')
        if base != 'pre':
            inline = '\n'.join(map(_escape_start, inline.split('\n')))
        if not inline.strip():
            continue  # empty paragraph — skip

        if base == 'pre':
            if not in_pre:
                if parts:
                    parts.append('')
                parts.append('```')
                in_pre = True
            parts.append(inline)
            prev_block_key = 'pre'
            continue

        close_pre()

        # Blank line between block elements, but not between consecutive same-type blocks
        block_key = base if base == 'quote' else \
            ('list' if ptype in ('list', 'numbered') else None)  # one list
        same_block = block_key is not None and prev_block_key == block_key
        if parts and not same_block:
            parts.append('')
        elif same_block and base == 'quote':
            parts.append('>')  # else they'd join into one paragraph

        if base in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            level = int(base[1])
            parts.append('#' * level + ' ' + inline)
        elif base == 'quote':
            parts.append('> ' + inline)
        elif ptype in ('list', 'numbered'):
            marker = '- ' if ptype == 'list' else '1. '
            # indented by the width of the markers above (CommonMark)
            above = (markers + ['  '] * indent)[:indent]  # a gap: '- '
            markers = above + [marker]
            prefix = ' ' * sum(map(len, above)) + marker
            if ptype == 'list':  # task list "[ ] "/"[x] " stays as is
                inline = re.sub(r'^\\\[([ xX])\\\] ', r'[\1] ', inline)
            parts.append(prefix + inline)
        else:
            parts.append(inline)

        prev_block_key = block_key

    close_pre()
    if footnotes:
        from miniword.textmodel.texeltree import get_text
        parts.append('')
        for n, fn in enumerate(footnotes, 1):
            # content ends with an ENDMARK ('\n'); strip it for the inline definition
            parts.append('[^%d]: %s'
                         % (n, _escape(get_text(fn.content)[:-1])))
    return '\n'.join(parts) + '\n'


def _table_to_md(table):
    """Render a Table texel as Markdown table lines.

    MD requires exactly one header row. If nheader==0, an empty header row is
    inserted. If nheader>1, only the first row is treated as header (lossy).
    """
    n_rows, n_cols = table.nrows, table.ncols
    cell_texels = table.childs[1::2]
    grid = [[_cell_md(cell_texels[r * n_cols + c])
             for c in range(n_cols)]
            for r in range(n_rows)]
    if table.nheader == 0:
        grid = [[''] * n_cols] + grid
    widths = [max(max(len(grid[r][c]) for r in range(len(grid))), 3)
              for c in range(n_cols)]
    def fmt(cells):
        return '| ' + ' | '.join(c.ljust(w) for c, w in zip(cells, widths)) + ' |'
    lines = [fmt(grid[0]),
             '| ' + ' | '.join('-' * w for w in widths) + ' |']
    for row in grid[1:]:
        lines.append(fmt(row))
    return lines


def _cell_md(cell):
    """A table cell as Markdown inline (formatting, links, images): its
    paragraphs on one line, '|' escaped."""
    from miniword.textmodel.utils import iter_leafes
    from miniword.textmodel.texeltree import NewLine
    paragraphs = [[]]
    for *_, elem in iter_leafes(cell, 0):
        if isinstance(elem, NewLine):
            paragraphs.append([])
        else:
            paragraphs[-1].append(elem)
    return ' '.join(_elems_to_inline(p) for p in paragraphs if p) \
        .replace('|', '\\|').replace('\\\n', '<br>')


_SPECIAL = re.compile(r'([\\`*_\[\]<>~^])')
_ENTITY  = re.compile(r'&(?=#?\w+;)')


def _escape(text):
    """text with the Markdown characters escaped."""
    return _ENTITY.sub(r'\\&', _SPECIAL.sub(r'\\\1', text))


def _escape_start(line):
    """line with a leading block marker (# > - + = 1.) escaped."""
    if line[:1] and line[0] in '#>+-=':
        return '\\' + line
    return re.sub(r'^(\d+)([.)])', r'\1\\\2', line)


def _code_span(text):
    """text as inline code, fenced by more backticks than it contains."""
    n = max(map(len, re.findall('`+', text)), default=0) + 1
    pad = ' ' if text[:1] == '`' or text[-1:] == '`' else ''
    return '`' * n + pad + text + pad + '`' * n


def _elems_to_inline(elems, footnotes=None, plain=False):
    """Convert a list of leaf texels (excluding the NL) to Markdown inline;
    plain: text only, unescaped (code blocks). Images are embedded as data
    URIs - a document stays one file."""
    from miniword.textmodel.texeltree import get_text
    from miniword.images.images import Image as ImageTexel, image_mime
    from miniword.footnotes.footnotes import Footnote as FootnoteTexel
    from miniword.core.texels import BR
    segments = []
    for elem in elems:
        if isinstance(elem, BR):
            segments.append('\n' if plain else '\\\n')
            continue
        if isinstance(elem, FootnoteTexel):
            if footnotes is not None:
                footnotes.append(elem)
                segments.append('[^%d]' % len(footnotes))
            continue
        if isinstance(elem, ImageTexel):
            data = elem.content
            if data:
                b64  = base64.b64encode(data).decode('ascii')
                segments.append('![%s](data:%s;base64,%s)'
                                % (_escape(elem.alt), image_mime(data), b64))
            elif elem.path:  # linked
                from miniword.images.images import file_path
                segments.append('![%s](%s)'
                                % (_escape(elem.alt), file_path(elem, _folder)))
            continue
        text = get_text(elem)
        if not text:
            continue
        if plain:
            segments.append(text)
            continue
        props  = getattr(elem, 'style', {})
        bold   = props.get('bold',   False)
        italic = props.get('italic', False)
        strike = props.get('strike', False)
        href   = props.get('href',   '')
        vpos   = props.get('vertical_position', 'normal')
        code   = props.get('font_family', '').lower() in ('courier', 'courier new',
                                                           'monospace', 'consolas')
        if code:
            text = _code_span(text)
        else:
            text = _escape(text)
            mark = '***' if bold and italic else '**' if bold else \
                '*' if italic else ''
            text = mark + text + mark
        if strike:
            text = '~~' + text + '~~'
        if vpos == 'superscript':
            text = '^' + text + '^'
        elif vpos == 'subscript':
            text = '~' + text + '~'
        if href:
            text = '[%s](%s)' % (text, href)
        segments.append(text)
    return ''.join(segments)


# ---------------------------------------------------------------------------
# Import: Markdown → Document
# ---------------------------------------------------------------------------

def _load(path):
    global _folder
    with open(path, encoding='utf-8') as f:
        text = f.read()
    _folder = os.path.dirname(os.path.abspath(path))
    try:
        return _load_mistune(text)
    finally:
        _folder = ''


def image_run(alt, src, size=None, load=False):
    """The run of an image (Markdown, HTML): a data URI embedded, a path
    or URL linked; with load (paste) a URL is loaded now. size: display
    (width, height) in pixels, either may be None - becomes its scale
    if the image's pixel size is known."""
    from miniword.images import imageio
    from miniword.images.images import fetch_image, is_url, memory_path
    if src.startswith('data:'):
        data, path, relative = fetch_image(src), None, False
    else:
        data, (path, relative) = None, memory_path(src, _folder)
        if load and is_url(src) and src not in imageio.external:
            imageio.load_url(src)
    pixels = size and any(size) and imageio.pixel_size(
        data or (path and imageio.external_content(path)))
    return '', {'_image': (alt, data, path, _scale(size, pixels),
                           relative)}


def _image(alt, data, path, scale, relative):
    """The Image texel of an image run (see image_run)."""
    from miniword.images.images import Image
    return Image(data, *scale, alt=alt, path=path, relative=relative)


def _scale(size, pixels):
    """(scale_x, scale_y) for display size (width, height) of an image of
    pixels (width, height); one given keeps the proportions."""
    w, h = size or (None, None)
    if not pixels or not (w or h):
        return 1.0, 1.0
    sx, sy = w and w / pixels[0], h and h / pixels[1]
    return sx or sy, sy or sx


# --- builder: blocks -> document -------------------------------------------
#
# Markdown (mistune, see _md_blocks) and HTML (htmlfilter.py) are both
# turned into a flat list of blocks, like Miniword's paragraphs:
#
#   (ptype, indent, runs)       a paragraph; ptype 'normal', 'h1'..'h6',
#                               'list', 'numbered', 'quote' or 'pre'
#   ('table', grid[, nheader])  grid: rows of cells (runs or strings)
#
# runs: (text, props); special runs carry '_image' (see image_run),
# '_footnote' (its text) or '_br' (forced line break) instead of text.

def _build_blocks(doc, blocks):
    """Build blocks into a new doc.textmodel. Empty paragraphs separate
    tables, code (pre) and quotes from the text around them. Equal image
    data (e.g. the same data URI twice) ends up as one bytes object."""
    from miniword.textmodel.textmodel import TextModel
    from miniword.textmodel.texeltree import T, ENDMARK, grouped
    from miniword.footnotes.footnotes import Footnote
    from miniword.core.texels import BR
    text, runs, pars, marks = [], [], [], []
    size = 0
    interned = {}

    def add(s, props=None):
        nonlocal size
        if props:
            runs.append((size, size + len(s), props))
        text.append(s)
        size += len(s)

    def kind(block):
        return block and (block[0] if block[0] in ('table', 'pre', 'quote')
                          else 'text')

    for k, block in enumerate(blocks):
        prev = kind(blocks[k - 1]) if k else None
        if prev and (kind(block) != prev or prev == 'table'):
            pars.append((size, 'normal', 0))  # an empty paragraph between
            add('\n')
        if block[0] == 'table':
            marks.append((size, _table(*block[1:])))
            add('\n')  # the table's own NL
            continue
        ptype, indent, block_runs = block
        for run_text, props in block_runs:
            if props.get('_image'):
                alt, data, *rest = props['_image']
                data = interned.setdefault(data, data) if data else data
                marks.append((size, _image(alt, data, *rest)))
            elif props.get('_footnote'):
                marks.append((size, Footnote(grouped(
                    [T(props['_footnote']), ENDMARK]))))
            elif props.get('_br'):
                marks.append((size, BR()))
            else:
                add(run_text, props)
        pars.append((size, ptype, indent))
        add('\n')

    model = TextModel(''.join(text))
    for i, ptype, indent in pars:
        _apply_parstyle(model, i, ptype, indent)
    for i1, i2, props in runs:
        model.set_properties(i1, i2, **props)
    # zero-width marks, back to front: an insertion only shifts what
    # follows, and marks at the same place keep their order
    for i, texel in reversed(marks):
        piece = model.create_textmodel()
        piece.texel = texel if texel.is_container else grouped([texel])
        model.insert(i, piece)
    doc.textmodel = model


def _apply_parstyle(model, nl_pos, ptype, indent):
    if ptype.startswith('h') or ptype in ('pre', 'list', 'numbered', 'quote'):
        base = ptype
    else:
        base = 'body'
    ps = {'base': base}
    if ptype in ('list', 'numbered'):
        ps['paragraph_type'] = ptype
    model.set_parstyle(nl_pos, ps)
    if indent:
        model.set_indent(nl_pos, indent)


def _table(grid, nheader=1):
    """A Table texel from a 2-D list of cells (see _cell_texel)."""
    from miniword.tables.tables import Table
    table = Table(*[(_cell_texel(cell), {}) for row in grid for cell in row],
                  ncols=len(grid[0]))
    return table.set_nheader(nheader) if nheader else table


_INLINE_PROPS = {'strong': {'bold': True}, 'emphasis': {'italic': True},
                 'strikethrough': {'strike': True},
                 'superscript': {'vertical_position': 'superscript'},
                 'subscript': {'vertical_position': 'subscript'}}


def _inline_runs(nodes, props={}, notes={}):
    """Runs (text, props) of mistune inline nodes; notes: the footnotes'
    texts by key."""
    runs = []
    for node in nodes:
        t, children = node.get('type'), node.get('children', [])
        if t in ('text', 'raw_text'):
            runs.append((html.unescape(node.get('raw', '')), props))
        elif t == 'softbreak':
            runs.append((' ', props))
        elif t == 'linebreak' or t == 'inline_html' \
                and _BR.fullmatch(node.get('raw', '')):
            runs.append(('', {'_br': True}))
        elif t == 'footnote_ref':
            key = node.get('raw')
            runs.append(('', {'_footnote': notes.get(key, key)}))
        elif t == 'codespan':
            runs.append((node.get('raw', ''),
                         dict(props, font_family='Courier New')))
        elif t == 'image':
            alt = ''.join(text for text, _ in _inline_runs(children))
            runs.append(image_run(alt, node['attrs'].get('url', '')))
        elif t == 'link':
            runs += _inline_runs(children,
                                 dict(props, href=node['attrs'].get('url')),
                                 notes)
        else:
            runs += _inline_runs(children,
                                 dict(props, **_INLINE_PROPS.get(t, {})),
                                 notes)
    return runs


def _cell_texel(cell):
    """The content of a table cell: a string, or runs (text with props,
    images; see image_run)."""
    from miniword.textmodel.textmodel import TextModel
    from miniword.textmodel.texeltree import Text, grouped
    if isinstance(cell, str):
        return Text(cell)
    model = TextModel('')
    for text, props in cell:
        pos = len(model)
        if props.get('_image') or props.get('_br'):
            from miniword.core.texels import BR
            piece = model.create_textmodel()
            piece.texel = grouped([_image(*props['_image'])
                                   if props.get('_image') else BR()])
            model.insert(pos, piece)
        elif text:
            model.insert_text(pos, text)
            if props:
                model.set_properties(pos, pos + len(text), **props)
    return model.texel


def _register_styles(doc, preset='github', overwrite=True, skip=()):
    """Register the MD paragraph styles (h1..h6, body, list, numbered,
    quote, pre) on doc.basestyles.

    overwrite=False skips any name doc already defines, instead of
    replacing it -- used when pasting into an already-open document, whose
    existing styles of the same name (if any) should win.
    skip: names to never touch -- used for roles _adopt_existing_styles
    already resolved to one of doc's own (differently-named) styles, so a
    second, disconnected style under the parser's canonical name doesn't
    also get added.
    """
    from miniword.plugins.mdstyles import preset as md_preset
    styles, _ = md_preset(preset)
    for name, style in styles.items():
        if name in skip:
            continue
        if not overwrite and (doc.basestyles.contains(name)
                              or name not in _CANONICAL_ROLES):
            continue  # pasting: no header/footer styles
        doc.basestyles.set(name, style)


_CANONICAL_ROLES = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'body',
                     'list', 'numbered', 'quote', 'pre'}


def _adopt_existing_styles(textmodel, doc):
    """Rename textmodel's paragraph styles to whatever name doc's own
    basestyles already uses for the same role (e.g. its own 'h1'-tagged
    heading style, however it's actually named), so pasted content matches
    the target document's look instead of introducing a second,
    disconnected style under the parser's canonical name.

    Returns the set of canonical role names doc already had a match for --
    the caller should skip registering a fallback style for those (see
    _register_styles's skip= parameter).
    """
    from miniword.textmodel.utils import iter_paragraphs
    from miniword.textmodel.texeltree import NewLine
    from miniword.plugins.mdstyles import role_keys

    role_to_key = role_keys(doc)
    remap = {role: key for role, key in role_to_key.items()
             if role in _CANONICAL_ROLES and key != role}

    if remap:
        for i1, i2, elems in iter_paragraphs(textmodel.get_xtexel(), 0):
            nl = elems[-1]
            if not isinstance(nl, NewLine):
                continue
            base = nl.parstyle.get('base')
            if base in remap:
                textmodel.set_parstyle(i2 - 1, dict(nl.parstyle, base=remap[base]))

    return set(role_to_key) & _CANONICAL_ROLES


def md_text_to_fragment(text, target_doc):
    """Parse Markdown text into a texel fragment for insertion into an
    already-open document (e.g. via Editor.insert_texel()).

    Paragraphs whose role (heading, list, ...) target_doc already has a
    style for adopt that style's name (see _adopt_existing_styles); any
    other roles get the standard MD styles registered as a fallback (see
    _register_styles(..., overwrite=False)). Embedded images carry their
    data in the Image texels. No new Document is created.
    """
    from types import SimpleNamespace
    from miniword.textmodel.textmodel import TextModel

    shim = SimpleNamespace(textmodel=TextModel(''))
    _build_mistune(shim, text)

    covered = _adopt_existing_styles(shim.textmodel, target_doc)
    _register_styles(target_doc, overwrite=False, skip=covered)
    return shim.textmodel.texel


def get_menus(doc):
    """Return plugin menus for doc. Only adds a Markdown menu for MD documents."""
    from miniword.plugins.mdstyles import menu_items
    if getattr(doc, 'home_format', None) not in ('md', 'markdown'):
        return []
    return [("&Markdown", menu_items())]


# --- parser (mistune) ---------------------------------------------------------

def _load_mistune(text):
    """Import using mistune for more accurate MD parsing."""
    from miniword.core.document import Document

    doc = Document()
    _register_styles(doc)
    _build_mistune(doc, text)
    return doc


def _build_mistune(doc, text):
    """Parse text as Markdown and build it into doc.textmodel; doc only
    needs that attribute (paste: a stand-in, see md_text_to_fragment)."""
    import mistune
    nodes = mistune.create_markdown(
        renderer='ast',
        plugins=['footnotes', 'strikethrough', 'table',
                 'superscript', 'subscript'])(text)
    _build_blocks(doc, _md_blocks(nodes))


def _md_blocks(nodes):
    """The blocks (see _build_blocks) of a mistune AST."""
    notes = {item['attrs']['key']: _plain_text(item.get('children', []))
             for node in nodes if node.get('type') == 'footnotes'
             for item in node.get('children', [])}
    blocks = []

    def runs(node):
        return _inline_runs(node.get('children', []), notes=notes)

    def visit(node, quote=False):
        t = node.get('type')
        if t == 'heading':
            level = node.get('attrs', {}).get('level', 1)
            blocks.append(('h%d' % level, 0, runs(node)))
        elif t == 'paragraph':
            blocks.append(('quote' if quote else 'normal', 0, runs(node)))
        elif t == 'list':
            visit_list(node, 0)
        elif t == 'block_code':
            for line in node.get('raw', '').splitlines():
                blocks.append(('pre', 0, [(line or ' ', {})]))
        elif t == 'table':
            grid, nheader = _table_grid(node)
            if grid:
                blocks.append(('table', grid, nheader))
        elif t == 'block_quote':
            for child in node.get('children', []):
                visit(child, quote=True)
        elif t == 'block_html':  # its text, without the tags
            text = html.unescape(re.sub(r'<[^>]*>', '', node.get('raw', '')))
            for line in filter(None, map(str.strip, text.splitlines())):
                blocks.append(('normal', 0, [(line, {})]))

    def visit_list(node, depth):
        ordered = node.get('attrs', {}).get('ordered', False)
        ptype = 'numbered' if ordered else 'list'
        for item in node.get('children', []):
            for child in item.get('children', []):
                if child.get('type') == 'list':
                    visit_list(child, depth + 1)
                elif child.get('type') in ('paragraph', 'block_text'):
                    blocks.append((ptype, depth, runs(child)))
                else:
                    visit(child)

    for node in nodes:
        visit(node)
    return blocks


def _plain_text(nodes):
    """The text of mistune nodes, without formatting (a footnote's)."""
    parts = []
    for node in nodes:
        t = node.get('type')
        if t in ('text', 'raw_text'):
            parts.append(html.unescape(node.get('raw', '')))
        elif t == 'codespan':
            parts.append(node.get('raw', ''))
        elif t in ('softbreak', 'linebreak'):
            parts.append(' ')
        else:
            parts.append(_plain_text(node.get('children', [])))
    return ''.join(parts)


def _table_grid(node):
    """2-D list of cells (runs, see _inline_runs) of a mistune table, and
    the number of header rows."""
    grid, nheader = [], 0
    for child in node.get('children', []):
        if child.get('type') == 'table_head':
            grid.append([_inline_runs(c.get('children', []))
                         for c in child.get('children', [])])
            nheader = 1
        elif child.get('type') == 'table_body':
            for tr in child.get('children', []):
                grid.append([_inline_runs(c.get('children', []))
                             for c in tr.get('children', [])])
    return grid, nheader


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def _check_md(doc):
    """Return list of features that cannot be represented in Markdown."""
    from miniword.textmodel.utils import iter_paragraphs
    from miniword.textmodel.texeltree import NewLine
    from miniword.tables.tables import Table as TableTexel
    from miniword.images.images import Image as ImageTexel

    _OK_BASES  = {'normal', 'body', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                  'pre', 'list', 'numbered', 'quote'}
    _OK_PTYPES = {'normal', 'list', 'numbered'}
    _OK_PAR    = {'base', 'paragraph_type'}
    _OK_CHAR   = {'bold', 'italic', 'font_family', 'href', 'strike', 'vertical_position'}
    _MONO      = {'courier', 'courier new', 'monospace', 'consolas',
                  'lucida console'}

    issues = set()
    texel = doc.textmodel.get_xtexel()

    for _i1, _i2, elems in iter_paragraphs(texel, 0):
        nl = elems[-1]
        if not isinstance(nl, NewLine):
            continue
        ps = nl.parstyle
        if ps.get('base', 'normal') not in _OK_BASES:
            issues.add("custom paragraph style")
        if ps.get('paragraph_type', 'normal') not in _OK_PTYPES:
            issues.add("paragraph type '%s'" % ps.get('paragraph_type'))
        for key in ps:
            if key not in _OK_PAR:
                issues.add("paragraph attribute '%s'" % key)
        from miniword.footnotes.footnotes import Footnote as FootnoteTexel
        for elem in elems[:-1]:
            if isinstance(elem, FootnoteTexel):
                continue
            if isinstance(elem, (TableTexel, ImageTexel)):
                if isinstance(elem, ImageTexel):
                    if elem.scale_x != 1.0 or elem.scale_y != 1.0:
                        issues.add("image size/scale")
                    if elem.crop is not None:
                        issues.add("image crop")
                elif isinstance(elem, TableTexel):
                    if elem.nheader == 0:
                        issues.add("tables without header row (empty header added)")
                    elif elem.nheader > 1:
                        issues.add("tables with multiple header rows")
                continue
            style = getattr(elem, 'style', {})
            for key, val in style.items():
                if key == 'font_family':
                    if str(val).lower() not in _MONO:
                        issues.add("custom font")
                elif key not in _OK_CHAR:
                    issues.add("character attribute '%s'" % key)

    return sorted(issues)


register_import("Markdown", ["md", "markdown"], _load, lossless=False)
register_paste_as("Paste from &Markdown", md_text_to_fragment)
register_export("Markdown", ["md", "markdown"], _save,
                lossless=False, check_fn=_check_md)


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _extract_pars(doc):
    """Extract list of (base, ptype, indent, runs) from a loaded Document.

    runs: list of (text, style_dict) for each leaf texel in the paragraph.
    """
    from miniword.textmodel.utils import iter_paragraphs
    from miniword.textmodel.texeltree import NewLine, get_text
    from miniword.core.styles import style_default, updated
    result = []
    for i1, i2, elems in iter_paragraphs(doc.textmodel.get_xtexel(), 0):
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


def _parse(md):
    """Parse a MD string; see _extract_pars."""
    return _extract_pars(_load_mistune(md))


def test_00():
    "normal paragraph"
    pars = _parse("Hello world\n")
    assert len(pars) == 1
    base, ptype, indent, runs = pars[0]
    assert base  == 'body'
    assert ptype == 'normal'
    assert ''.join(t for t, _ in runs) == 'Hello world'


def test_01(load=_load_mistune):
    "headings h1–h3"
    pars = _extract_pars(load("# Heading 1\n## Heading 2\n### Heading 3\n"))
    assert pars[0][0] == 'h1'
    assert pars[1][0] == 'h2'
    assert pars[2][0] == 'h3'
    assert ''.join(t for t, _ in pars[0][3]) == 'Heading 1'
    assert ''.join(t for t, _ in pars[1][3]) == 'Heading 2'
    assert ''.join(t for t, _ in pars[2][3]) == 'Heading 3'


def test_01b(load=_load_mistune):
    "indented ATX headings (up to 3 leading spaces) are still recognized"
    pars = _extract_pars(load("## Section\n   ### Sub A\n   ### Sub B\n"))
    assert pars[0][0] == 'h2'
    assert pars[1][0] == 'h3'
    assert pars[2][0] == 'h3'
    assert ''.join(t for t, _ in pars[1][3]) == 'Sub A'
    assert ''.join(t for t, _ in pars[2][3]) == 'Sub B'


def test_02():
    "heading with continuation line"
    pars = _parse("# Title\n\nParagraph text.\n")
    assert pars[0][0] == 'h1'
    assert ''.join(t for t, _ in pars[0][3]) == 'Title'
    assert pars[1][0] == 'body'


def test_03():
    "bold and italic"
    pars = _parse("Normal **bold** *italic* end\n")
    assert len(pars) == 1
    runs = pars[0][3]
    texts  = [t for t, _ in runs]
    styles = {t: s for t, s in runs}
    assert 'bold'   in texts
    assert 'italic' in texts
    assert styles['bold'].get('bold') == True
    assert styles['bold'].get('italic') != True
    assert styles['italic'].get('italic') == True
    assert styles['italic'].get('bold') != True


def test_03b():
    "single-character italic and bold"
    pars = _parse("*a* and **b**\n")
    runs = pars[0][3]
    styles = {t: s for t, s in runs}
    assert 'a' in styles, f"runs: {runs}"
    assert styles['a'].get('italic') == True
    assert 'b' in styles
    assert styles['b'].get('bold') == True


def test_04():
    "bold+italic combined"
    pars = _parse("***both***\n")
    runs = pars[0][3]
    assert len(runs) == 1
    text, style = runs[0]
    assert text == 'both'
    assert style.get('bold')   == True
    assert style.get('italic') == True


def test_05():
    "inline code"
    pars = _parse("Use `print()` here\n")
    runs = pars[0][3]
    styles = {t: s for t, s in runs}
    assert 'print()' in styles
    fam = styles['print()'].get('font_family', '')
    assert 'Courier' in fam or 'courier' in fam.lower() or 'mono' in fam.lower()


def test_06():
    "unordered list — top-level items have indent 0"
    pars = _parse("- Alpha\n- Beta\n")
    assert len(pars) == 2
    for base, ptype, indent, runs in pars:
        assert ptype  == 'list'
        assert indent == 0
    assert ''.join(t for t, _ in pars[0][3]) == 'Alpha'
    assert ''.join(t for t, _ in pars[1][3]) == 'Beta'


def test_07():
    "ordered list — top-level items have indent 0"
    pars = _parse("1. First\n2. Second\n")
    assert len(pars) == 2
    for base, ptype, indent, runs in pars:
        assert ptype  == 'numbered'
        assert indent == 0


def test_08():
    "nested list — deeper indent"
    pars = _parse("- Top\n  - Nested\n")
    assert pars[0][2] < pars[1][2]   # nested has higher indent


def test_08b():
    "list uniformly indented by 2 spaces (e.g. under a lead-in paragraph) is still top-level"
    pars = _parse("  - Alpha\n  - Beta\n  - Gamma\n")
    assert len(pars) == 3
    for base, ptype, indent, runs in pars:
        assert ptype  == 'list'
        assert indent == 0


def test_08c():
    "nesting inside a uniformly-indented list is still relative, not absolute"
    pars = _parse("  - Top\n    - Nested\n  - Top again\n")
    assert [indent for base, ptype, indent, runs in pars] == [0, 1, 0]


def test_08d(load=_load_mistune):
    "three-level nested list (with continuation line) ends up in NewLine.indent"
    md = ("- Top\n  continued.\n"
          "  - Level 1\n"
          "    - Level 2a\n"
          "    - Level 2b\n"
          "  - Level 1 again\n")
    pars = _extract_pars(load(md))
    assert [indent for base, ptype, indent, runs in pars] == [0, 1, 2, 2, 1]


def test_09():
    "list item with continuation line"
    pars = _parse("- First line\n  continues here\n- Second\n")
    assert len(pars) == 2
    text0 = ''.join(t for t, _ in pars[0][3])
    assert 'First line' in text0
    assert 'continues here' in text0
    assert pars[1][2] == 0


def test_10():
    "fenced code block uses pre basestyle"
    pars = _parse("```\nfirst line\nsecond line\n```\n")
    assert len(pars) == 2
    for base, ptype, indent, runs in pars:
        assert base == 'pre'
    assert ''.join(t for t, _ in pars[0][3]) == 'first line'
    assert ''.join(t for t, _ in pars[1][3]) == 'second line'


def test_11():
    "export roundtrip: headings, lists and code block"
    import tempfile, os
    md = "# Title\n\nNormal text.\n\n- Item one\n- Item two\n\n```\ncode here\n```\n"
    with tempfile.NamedTemporaryFile(suffix='.md', delete=False,
                                     mode='w', encoding='utf-8') as f:
        f.write(md)
        path = f.name
    try:
        doc = _load(path)
        out = _doc_to_md(doc)
        assert '# Title'     in out
        assert 'Normal text' in out
        assert '- Item one'  in out
        assert '- Item two'  in out
        assert '```'         in out
        assert 'code here'   in out
    finally:
        os.unlink(path)


def test_12(load=_load_mistune):
    "table import"
    from miniword.textmodel.utils import iter_paragraphs
    from miniword.textmodel.texeltree import NewLine, get_text
    from miniword.tables import Table as TableTexel
    md = "| A | B |\n| --- | --- |\n| C | D |\n"
    doc = load(md)
    table = None
    for i1, i2, elems in iter_paragraphs(doc.textmodel.get_xtexel(), 0):
        content = elems[:-1]
        if content and isinstance(content[0], TableTexel):
            table = content[0]
            break
    assert table is not None
    assert table.nrows == 2
    assert table.ncols == 2
    cells = table.childs[1::2]
    assert [get_text(c) for c in cells] == ['A', 'B', 'C', 'D']


def test_13(load=_load_mistune):
    "table export"
    md = "| Name | City |\n| --- | --- |\n| Einstein | Ulm |\n| Darwin | Shrewsbury |\n"
    doc = load(md)
    out = _doc_to_md(doc)
    assert '| Name' in out
    assert '| ---' in out
    assert '| Einstein' in out
    assert '| Darwin' in out


def test_14(load=_load_mistune):
    "blank NL paragraphs around table & pre"
    from miniword.textmodel.utils import iter_paragraphs
    from miniword.textmodel.texeltree import NewLine, get_text
    from miniword.tables import Table as TableTexel

    def bases(md):
        doc = load(md)
        result = []
        for _i1, _i2, elems in iter_paragraphs(doc.textmodel.get_xtexel(), 0):
            nl = elems[-1]
            if not isinstance(nl, NewLine):
                continue
            content = elems[:-1]
            if content and isinstance(content[0], TableTexel):
                result.append('table')
            else:
                text = ''.join(get_text(e) for e in content)
                result.append('blank' if not text.strip() else \
                              nl.parstyle.get('base', 'normal'))
        return result

    # table surrounded by text → blank before and after
    bs = bases("Before.\n\n| A | B |\n| - | - |\n| C | D |\n\nAfter.\n")
    assert 'blank' in bs
    ti = bs.index('table')
    assert bs[ti - 1] == 'blank'
    assert bs[ti + 1] == 'blank'

    # pre block surrounded by text → blank before and after
    bs = bases("Before.\n\n```\ncode\n```\n\nAfter.\n")
    pi = bs.index('pre')
    assert bs[pi - 1] == 'blank'
    assert bs[pi + 1] == 'blank'


def test_15():
    "blockquote import and export roundtrip"
    pars = _parse("> First line\n> Second line\n")  # one paragraph
    assert [(base, runs[0][0]) for base, _, _, runs in pars] == \
        [('quote', 'First line Second line')]

    doc = _load_mistune("> Hello\n>\n> World\n")  # two paragraphs
    out = _doc_to_md(doc)
    assert out == "> Hello\n>\n> World\n"  # one quote, kept apart
    pars = _extract_pars(_load_mistune(out))
    assert [runs[0][0] for *_, runs in pars] == ['Hello', 'World']


def test_16(load=_load_mistune):
    "blank NL paragraphs inserted around quote blocks"
    from miniword.textmodel.utils import iter_paragraphs
    from miniword.textmodel.texeltree import NewLine, get_text

    def bases(md):
        doc = load(md)
        result = []
        for _i1, _i2, elems in iter_paragraphs(doc.textmodel.get_xtexel(), 0):
            nl = elems[-1]
            if not isinstance(nl, NewLine):
                continue
            text = ''.join(get_text(e) for e in elems[:-1])
            base = nl.parstyle.get('base', 'normal')
            result.append('blank' if not text.strip() else base)
        return result

    bs = bases("Before.\n\n> Quote line\n\nAfter.\n")
    qi = bs.index('quote')
    assert bs[qi - 1] == 'blank'
    assert bs[qi + 1] == 'blank'


def test_17():
    "image export"
    from miniword.core.document import Document
    from miniword.images.images import Image as ImageTexel
    from miniword.textmodel.texeltree import grouped, Text, NL

    doc = Document()

    # default scale — no warnings
    img = ImageTexel(b'\x89PNG\r\n\x1a\n', alt='photo.png')
    doc.textmodel.texel = grouped([Text('before '), img, Text(' after'), NL])
    warnings = _check_md(doc)
    assert "images" not in warnings
    assert "image size/scale" not in warnings
    md = _doc_to_md(doc)
    assert '![photo.png](data:image/png;base64,' in md
    assert 'before' in md and 'after' in md

    # non-default scale — warns
    img_scaled = img.set_scale_x(0.5).set_scale_y(0.5)
    doc.textmodel.texel = grouped([img_scaled, NL])
    warnings = _check_md(doc)
    assert "image size/scale" in warnings

    # crop set — warns
    img_cropped = img.set_crop((10, 10, 100, 100))
    doc.textmodel.texel = grouped([img_cropped, NL])
    warnings = _check_md(doc)
    assert "image crop" in warnings


def test_18():
    "check_md warns about tables without header row"
    from miniword.core.document import Document
    from miniword.tables.tables import from_strings as mk_table
    from miniword.textmodel.texeltree import grouped, NL

    doc = Document()
    table = mk_table([['A', 'B'], ['1', '2']])  # nheader=0 by default
    doc.textmodel.texel = grouped([table, NL])
    warnings = _check_md(doc)
    assert any("without header" in w for w in warnings)


def test_19():
    "table with nheader=0"
    from miniword.core.document import Document
    from miniword.tables.tables import from_strings as mk_table
    from miniword.textmodel.texeltree import grouped, NL

    doc = Document()
    table = mk_table([['A', 'B'], ['1', '2']])  # nheader=0
    doc.textmodel.texel = grouped([table, NL])
    md = _doc_to_md(doc)
    lines = [l for l in md.splitlines() if l.startswith('|')]
    assert lines[0].replace('|', '').strip() == ''   # empty header
    assert '---' in lines[1]                          # separator
    assert 'A' in lines[2]                            # first data row


def test_20():
    "table with nheader=1 roundtrip"
    from miniword.core.document import Document
    from miniword.tables.tables import from_strings as mk_table
    from miniword.textmodel.texeltree import grouped, NL

    doc = Document()
    table = mk_table([['Name', 'Age'], ['Alice', '30']])
    table = table.set_nheader(1)
    doc.textmodel.texel = grouped([table, NL])
    warnings = _check_md(doc)
    assert not any("header" in w for w in warnings)
    md = _doc_to_md(doc)
    lines = [l for l in md.splitlines() if l.startswith('|')]
    assert 'Name' in lines[0]
    assert '---' in lines[1]
    assert 'Alice' in lines[2]


def test_21(load=_load_mistune):
    "footnote import"
    from miniword.textmodel.utils import iter_paragraphs
    from miniword.textmodel.texeltree import NewLine, get_text
    from miniword.footnotes.footnotes import Footnote
    md = "Hello[^1] world.\n\n[^1]: Footnote text.\n"
    doc = load(md)
    fns = [e for _i1, _i2, elems in iter_paragraphs(doc.textmodel.get_xtexel(), 0)
           for e in elems if isinstance(e, Footnote)]
    assert len(fns) == 1
    # content ends with an ENDMARK ('\n')
    assert get_text(fns[0].content) == 'Footnote text.\n'


def test_22():
    "footnote export"
    from miniword.core.document import Document
    from miniword.textmodel.textmodel import TextModel
    from miniword.textmodel.texeltree import grouped, T, ENDMARK
    from miniword.footnotes.footnotes import Footnote
    doc = Document()
    _register_styles(doc)
    doc.textmodel = TextModel('Hello world.\n')
    fn = Footnote(grouped([T('Note text.'), ENDMARK]))
    fn_model = doc.textmodel.create_textmodel()
    fn_model.texel = grouped([fn])
    doc.textmodel.insert(5, fn_model)
    md = _doc_to_md(doc)
    assert '[^1]' in md
    assert '[^1]: Note text.' in md


def test_23(load=_load_mistune):
    "footnote roundtrip"
    md = "Text with footnote[^a].\n\n[^a]: The note.\n"
    doc = load(md)
    out = _doc_to_md(doc)
    assert '[^1]' in out
    assert '[^1]: The note.' in out


def test_24(load=_load_mistune):
    "image import: data from URI"
    from miniword.images.images import iter_images

    data = b'\x89PNG\r\n\x1a\nfakedata'
    b64 = base64.b64encode(data).decode('ascii')
    md = "Before.\n\n![photo.png](data:image/png;base64,%s)\n\nAfter.\n" % b64
    doc = load(md)

    images = list(iter_images(doc.textmodel.texel))
    assert [(image.content, image.alt) for image in images] == \
        [(data, 'photo.png')]

    out = _doc_to_md(doc)
    assert '![photo.png](data:image/png;base64,%s)' % b64 in out


def test_25(load=_load_mistune):
    "load test/tesla.md"
    import os
    from miniword.images.images import iter_images

    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(here, 'test', 'tesla.md')
    with open(path, encoding='utf-8') as f:
        doc = load(f.read())

    images = list(iter_images(doc.textmodel.texel))
    assert [image.alt for image in images] == ['teslasmall.jpg']
    assert images[0].content
    # the huge base64 data must not end up as plain text in the model
    assert len(doc.textmodel) < 2000


def test_26(load=_load_mistune):
    "load test/footnotes.md: roundtrip"
    import os

    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(here, 'test', 'footnotes.md')
    with open(path, encoding='utf-8') as f:
        doc = load(f.read())

    out = _doc_to_md(doc)
    for n in range(1, 8):
        assert '[^%d]' % n in out
        assert '[^%d]:' % n in out


def test_27(load=_load_mistune):
    "strikethrough import and export roundtrip"
    md_in = "Normal ~~struck~~ text.\n"
    doc   = load(md_in)
    md_out = _doc_to_md(doc)
    assert '~~struck~~' in md_out


def test_28(load=_load_mistune):
    "superscript and subscript import and export roundtrip"
    md_in = "H^2^O and CO~2~.\n"
    doc   = load(md_in)
    md_out = _doc_to_md(doc)
    assert '^2^' in md_out
    assert '~2~' in md_out


def test_29(load=_load_mistune):
    "hyperlink import and export roundtrip"
    md_in = "Visit [Python](https://python.org) today.\n"
    doc   = load(md_in)
    md_out = _doc_to_md(doc)
    assert '[Python](https://python.org)' in md_out


def test_30(load=_load_mistune):
    "load test/hyperlinks.md: roundtrip preserves key markup"
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(here, 'test', 'hyperlinks.md')
    with open(path, encoding='utf-8') as f:
        doc = load(f.read())
    out = _doc_to_md(doc)
    assert '[Python-Homepage](https://www.python.org)' in out
    assert '~~' in out
    assert '^' in out
    assert '[^1]' in out and '[^1]:' in out


def test_31():
    "_md_blocks (mistune AST): top-level list items have indent 0"
    # A minimal mistune-style AST by hand: exercises the adapter alone.
    nodes = [
        {'type': 'list', 'attrs': {'ordered': False}, 'children': [
            {'children': [
                {'type': 'paragraph', 'children': [{'type': 'text', 'raw': 'Alpha'}]},
                {'type': 'list', 'attrs': {'ordered': False}, 'children': [
                    {'children': [{'type': 'paragraph',
                                   'children': [{'type': 'text', 'raw': 'Nested'}]}]},
                ]},
            ]},
            {'children': [{'type': 'paragraph', 'children': [{'type': 'text', 'raw': 'Beta'}]}]},
        ]},
    ]
    indents = [(ptype, indent, runs[0][0])
               for ptype, indent, runs in _md_blocks(nodes)]
    assert indents == [('list', 0, 'Alpha'), ('list', 1, 'Nested'), ('list', 0, 'Beta')]


def test_32():
    "md_text_to_fragment: builds an insertable texel without creating a Document"
    from miniword.core.document import Document
    from miniword.textmodel.textmodel import TextModel
    from miniword.textmodel.utils import iter_paragraphs
    from miniword.textmodel.texeltree import NewLine, get_text

    doc = Document()
    texel = md_text_to_fragment("# Title\n\nBody text.\n", doc)

    model = TextModel()
    model.texel = texel
    assert model.get_text() == 'Title\nBody text.\n'

    bases = []
    for i1, i2, elems in iter_paragraphs(model.get_xtexel(), 0):
        nl = elems[-1]
        text = ''.join(get_text(e) for e in elems[:-1])
        if isinstance(nl, NewLine) and text:
            bases.append(nl.parstyle.get('base', 'normal'))
    assert bases == ['h1', 'body']

    # the fragment only renders correctly if the styles it references
    # (h1, body, ...) actually got registered on the target document
    assert doc.basestyles.contains('h1')
    assert doc.basestyles.contains('body')


def test_33():
    "md_text_to_fragment doesn't clobber a document's own existing style"
    from miniword.core.document import Document

    doc = Document()
    custom_h1 = {'font_size': 99}
    doc.basestyles.set('h1', custom_h1)

    md_text_to_fragment("# Title\n", doc)
    assert doc.basestyles.get('h1') == custom_h1

    # calling it again (e.g. a second paste) stays idempotent
    md_text_to_fragment("# Title again\n", doc)
    assert doc.basestyles.get('h1') == custom_h1


def test_34():
    "md_text_to_fragment adopts an existing role-tagged style under a different name"
    from miniword.core.document import Document
    from miniword.textmodel.textmodel import TextModel
    from miniword.textmodel.utils import iter_paragraphs
    from miniword.textmodel.texeltree import NewLine, get_text

    doc = Document()
    # doc already has a heading style for role 'h1', just not named 'h1'
    doc.basestyles.set('MyHeading', {'role': 'h1', 'font_size': 42})

    texel = md_text_to_fragment("# Title\n\nBody text.\n", doc)
    model = TextModel()
    model.texel = texel

    bases = {}
    for i1, i2, elems in iter_paragraphs(model.get_xtexel(), 0):
        nl = elems[-1]
        if isinstance(nl, NewLine):
            text = ''.join(get_text(e) for e in elems[:-1])
            if text:
                bases[text] = nl.parstyle.get('base')

    assert bases['Title'] == 'MyHeading'         # adopted, not the canonical 'h1'
    assert bases['Body text.'] == 'body'          # no role='body' match -> fallback
    assert not doc.basestyles.contains('h1')      # no disconnected extra style added
    assert doc.basestyles.get('MyHeading') == {'role': 'h1', 'font_size': 42}


if __name__ == '__main__':
    import tempfile, os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    sample = """\
# Heading 1

Normal paragraph with **bold** and *italic* text.

## Heading 2

- First item
- Second item
  - Nested item

1. Ordered first
2. Ordered second

### Heading 3

Code: `print("hello")` inline.
"""

    with tempfile.NamedTemporaryFile(suffix='.md', delete=False, mode='w',
                                     encoding='utf-8') as f:
        f.write(sample)
        path = f.name

    try:
        doc = _load(path)
        print("Import OK, paragraphs:")
        from miniword.textmodel.utils import iter_paragraphs
        from miniword.textmodel.texeltree import get_text, NewLine
        for i1, i2, elems in iter_paragraphs(doc.textmodel.get_xtexel(), 0):
            nl = elems[-1]
            if isinstance(nl, NewLine):
                text = get_text(elems[0]) if len(elems) > 1 else ''
                print('  [%s] %r' % (nl.parstyle.get('base', 'normal'),
                                     text[:40]))

        with tempfile.NamedTemporaryFile(suffix='.md', delete=False, mode='w',
                                         encoding='utf-8') as f2:
            out_path = f2.name
        _save(doc, out_path)
        with open(out_path, encoding='utf-8') as f2:
            print("\nExport:")
            print(f2.read())
        os.unlink(out_path)
    finally:
        os.unlink(path)


def _md_doc(text, **props):
    """A document with text (in props) for export tests."""
    from miniword.core.document import Document
    doc = Document()
    _register_styles(doc)
    doc.textmodel.insert_text(0, text)
    if props:
        doc.textmodel.set_properties(0, len(text), **props)
    return doc


def _mistune_roundtrip(doc):
    """doc saved as Markdown and loaded again."""
    return _load_mistune(_doc_to_md(doc))


def test_35():
    "export escapes Markdown characters: text comes back unchanged"
    text = 'a *b* _c_ [d](e) `f` <g> ~h~ ^i^ \\ &amp; j\n' \
           '# not a heading\n- not a list\n1. not numbered\n> no quote\n'
    doc = _mistune_roundtrip(_md_doc(text))
    assert doc.textmodel.get_text() == text
    pars = _extract_pars(doc)
    assert {(base, ptype) for base, ptype, _, _ in pars} == \
        {('body', 'normal')}
    assert not [style for *_, runs in pars for _, style in runs if style]


def test_36():
    "hard line breaks are imported as BR and exported as backslash"
    from miniword.core.texels import BR
    for md in ('one  \ntwo\n', 'one\\\ntwo\n', 'one<br>two\n'):
        doc = _load_mistune(md)
        assert doc.textmodel.get_text() == 'one\x0btwo\n', md
        assert _doc_to_md(doc) == 'one\\\ntwo\n', md
    doc = _mistune_roundtrip(_load_mistune('one  \ntwo\n'))
    assert doc.textmodel.get_text() == 'one\x0btwo\n'
    from miniword.textmodel.utils import iter_leafes
    assert any(isinstance(t, BR)
               for *_, t in iter_leafes(doc.textmodel.texel, 0))


def test_37():
    "entities are decoded on import"
    doc = _load_mistune('a &amp; b &copy; &#65;\n')
    assert doc.textmodel.get_text() == 'a & b © A\n'


def test_38():
    "an HTML block keeps its text (without the tags)"
    doc = _load_mistune('<div>x <b>y</b> &amp; z</div>\n\nb\n')
    assert [runs[0][0] for *_, runs in _extract_pars(doc)] == \
        ['x y & z', 'b']


def test_39():
    "inline code with backticks comes back unchanged"
    for code in ('x ` y', '`a`', 'a``b'):
        doc = _mistune_roundtrip(_md_doc(code, font_family='Courier New'))
        assert doc.textmodel.get_text() == code + '\n', code


def test_40():
    "task list items (kept as text) come back as task list items"
    md = '- [ ] todo\n- [x] done\n'
    assert _doc_to_md(_load_mistune(md)) == md


def test_41():
    "inline code in bold stays bold"
    pars = _parse("a **`code`** b\n")
    styles = {text: style for text, style in pars[0][3]}
    assert styles['code'].get('bold') is True
    assert styles['code'].get('font_family') == 'Courier New'


def test_42():
    "an empty body paragraph separates code, quotes and tables from text"
    from miniword.textmodel.utils import iter_paragraphs
    doc = _load_mistune("Text\n\n```\nx\n```\n\n> quote\n")
    pars = [(elems[-1].parstyle.get('base'), i2 - i1)  # style, length
            for i1, i2, elems in iter_paragraphs(doc.textmodel.texel, 0)
            if elems[-1].text == '\n']
    assert pars == [('body', 5), ('body', 1), ('pre', 2), ('body', 1),
                    ('quote', 6)]  # no empty paragraph at start or end


def test_43():
    "nested lists: indented by the width of the marker above, one list"
    for md in ('1. a\n   - b\n1. c\n',
               '- a\n  1. b\n     - c\n- d\n'):
        doc = _load_mistune(md)
        out = _doc_to_md(doc)
        assert out == md, out
        assert _extract_pars(_load_mistune(out)) == _extract_pars(doc)
    pars = _parse('1. a\n   - b\n1. c\n')
    assert [(ptype, indent) for _, ptype, indent, _ in pars] == \
        [('numbered', 0), ('list', 1), ('numbered', 0)]
