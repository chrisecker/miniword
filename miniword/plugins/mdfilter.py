# Markdown import/export plugin for Miniword
#
# Install: copy to ~/.miniword/plugins/ or import at app startup:
#   from examples.mdfilter import *  (registers the filters)
#
# External dependency for richer import (optional):
#   pip install mistune
#
# Without mistune a built-in parser handles the common MD subset.

from miniword.io.importexport import register_import, register_export


# ---------------------------------------------------------------------------
# Export: Document → Markdown
# ---------------------------------------------------------------------------

def _save(doc, path):
    md = _doc_to_md(doc)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(md)


def _doc_to_md(doc):
    from miniword.textmodel.iterators import iter_paragraphs
    from miniword.textmodel.texeltree import get_text
    from miniword.textmodel.iterators import iter_leafes
    from miniword.textmodel.texeltree import NewLine
    from miniword.tables import Table as TableTexel
    from miniword.core.styles import style_default, updated

    texel    = doc.textmodel.get_xtexel()
    parts          = []
    prev_block_key = None
    in_pre         = False

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

        inline = _elems_to_inline(content)
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
        block_key = base if base == 'quote' else (ptype if ptype in ('list', 'numbered') else None)
        same_block = block_key is not None and prev_block_key == block_key
        if parts and not same_block:
            parts.append('')

        if base in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            level = int(base[1])
            parts.append('#' * level + ' ' + inline)
        elif base == 'quote':
            parts.append('> ' + inline)
        elif ptype == 'list':
            prefix = '  ' * indent + '- '
            parts.append(prefix + inline)
        elif ptype == 'numbered':
            prefix = '  ' * indent + '1. '
            parts.append(prefix + inline)
        else:
            parts.append(inline)

        prev_block_key = block_key

    close_pre()
    return '\n'.join(parts) + '\n'


def _table_to_md(table):
    """Render a Table texel as Markdown table lines.

    MD requires exactly one header row. If nheader==0, an empty header row is
    inserted. If nheader>1, only the first row is treated as header (lossy).
    """
    from miniword.textmodel.texeltree import get_text
    n_rows, n_cols = table.nrows, table.ncols
    cell_texels = table.childs[1::2]
    grid = [[get_text(cell_texels[r * n_cols + c])
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


def _elems_to_inline(elems):
    """Convert a list of leaf texels (excluding the NL) to Markdown inline."""
    from miniword.textmodel.texeltree import get_text
    segments = []
    for elem in elems:
        text = get_text(elem)
        if not text:
            continue
        props = getattr(elem, 'style', {})
        bold   = props.get('bold',   False)
        italic = props.get('italic', False)
        code   = props.get('font_family', '').lower() in ('courier', 'courier new',
                                                           'monospace', 'consolas')
        if code:
            text = '`' + text + '`'
        elif bold and italic:
            text = '***' + text + '***'
        elif bold:
            text = '**' + text + '**'
        elif italic:
            text = '*' + text + '*'
        segments.append(text)
    return ''.join(segments)


# ---------------------------------------------------------------------------
# Import: Markdown → Document
# ---------------------------------------------------------------------------

def _load(path):
    with open(path, encoding='utf-8') as f:
        text = f.read()
    try:
        import mistune
        return _load_mistune(text)
    except ImportError:
        return _load_builtin(text)


# --- built-in parser --------------------------------------------------------

import re

_ATX_RE    = re.compile(r'^(#{1,6})\s+(.*?)(?:\s+#+)?\s*$')
_UL_RE     = re.compile(r'^(\s*)[-*+]\s+(.*)')
_OL_RE     = re.compile(r'^(\s*)\d+\.\s+(.*)')
_QUOTE_RE  = re.compile(r'^>\s?(.*)')
_RULE_RE   = re.compile(r'^[-*_]{3,}\s*$')
_FENCE_RE  = re.compile(r'^```')



def _load_builtin(text):
    from miniword.core.document import Document
    from miniword.textmodel.textmodel import TextModel

    doc = Document()
    _register_styles(doc)
    doc.textmodel = TextModel('')

    def insert_nl():
        pos = len(doc.textmodel.get_text())
        doc.textmodel.insert(pos, doc.textmodel.create_textmodel('\n'))

    blocks = _parse_md_paragraphs(text)
    prev_btype = None

    for i, block in enumerate(blocks):
        btype = block[0]
        next_btype = blocks[i + 1][0] if i + 1 < len(blocks) else None

        # Blank line before table, pre run, and quote run
        if btype == 'table' and prev_btype is not None:
            insert_nl()
        elif btype == 'pre' and prev_btype != 'pre' and prev_btype is not None:
            insert_nl()
        elif btype == 'quote' and prev_btype != 'quote' and prev_btype is not None:
            insert_nl()

        if btype == 'table':
            _, grid = block
            _insert_table_block(doc, grid)
        else:
            ptype, indent, runs = block
            _insert_text_block(doc, ptype, indent, runs)

        # Blank line after table, pre run, and quote run
        if btype == 'table' and next_btype is not None:
            insert_nl()
        elif btype == 'pre' and next_btype != 'pre' and next_btype is not None:
            insert_nl()
        elif btype == 'quote' and next_btype != 'quote' and next_btype is not None:
            insert_nl()

        prev_btype = btype

    return doc


def _insert_text_block(doc, ptype, indent, runs):
    par_text = ''.join(t for t, _ in runs) + '\n'
    pos = len(doc.textmodel.get_text())
    doc.textmodel.insert(pos, doc.textmodel.create_textmodel(par_text))
    nl_pos = pos + len(par_text) - 1
    if ptype.startswith('h') or ptype in ('pre', 'list', 'numbered', 'quote'):
        base = ptype
    else:
        base = 'body'
    ps = {'base': base}
    if ptype in ('list', 'numbered'):
        ps['paragraph_type'] = ptype
    doc.textmodel.set_parstyle(nl_pos, ps)
    if indent:
        doc.textmodel.set_indent(nl_pos, indent)
    run_pos = pos
    for run_text, run_props in runs:
        if run_props:
            doc.textmodel.set_properties(run_pos, run_pos + len(run_text), **run_props)
        run_pos += len(run_text)


def _insert_table_block(doc, grid):
    from miniword.tables.tables import from_strings as mk_table
    tbl_model = doc.textmodel.create_textmodel()
    table = mk_table(grid)
    table = table.set_nheader(1)
    tbl_model.texel = table
    pos = len(doc.textmodel.get_text())
    doc.textmodel.insert(pos, tbl_model)
    pos2 = len(doc.textmodel.get_text())
    doc.textmodel.insert(pos2, doc.textmodel.create_textmodel('\n'))


_SEP_ROW_RE = re.compile(r'^:?-+:?$')


def _parse_table_row(line):
    # Replace escaped pipes before splitting, restore afterwards
    line = line.strip().strip('|').replace('\\|', '\x00')
    return [c.strip().replace('\x00', '|') for c in line.split('|')]


def _parse_table_lines(lines):
    grid = []
    for line in lines:
        cells = _parse_table_row(line)
        if all(_SEP_ROW_RE.match(c) for c in cells if c):
            continue  # skip separator row
        grid.append(cells)
    if not grid:
        return grid
    # Normalize: all rows must have the same number of columns
    n_cols = max(len(row) for row in grid)
    for row in grid:
        while len(row) < n_cols:
            row.append('')
    return grid


def _parse_md_paragraphs(text):
    """Parse MD text into list of blocks.

    Each block is either:
      (ptype, indent, runs)  — text paragraph
      ('table', grid)        — table (2-D list of strings)

    ptype: 'normal' | 'h1'..'h6' | 'list' | 'numbered' | 'pre'
    runs:  list of (text, charprops_dict)
    """
    lines = text.splitlines()
    paragraphs = []
    buf = []         # accumulated normal-paragraph lines
    table_buf = []   # accumulated table lines
    in_fence = False

    def flush_buf():
        if buf:
            combined = ' '.join(buf)
            paragraphs.append(('normal', 0, _parse_inline(combined)))
            buf.clear()

    def flush_table():
        if table_buf:
            grid = _parse_table_lines(table_buf)
            if grid:
                paragraphs.append(('table', grid))
            table_buf.clear()

    for line in lines:
        if _FENCE_RE.match(line):
            flush_buf()
            flush_table()
            in_fence = not in_fence
            continue
        if in_fence:
            flush_table()
            paragraphs.append(('pre', 0, [(line or ' ', {})]))
            continue
        if _RULE_RE.match(line):
            flush_buf()
            flush_table()
            continue

        if line.startswith('|'):
            flush_buf()
            table_buf.append(line)
            continue
        else:
            flush_table()

        m = _ATX_RE.match(line)
        if m:
            flush_buf()
            level = len(m.group(1))
            paragraphs.append(('h%d' % level, 0, _parse_inline(m.group(2))))
            continue

        m = _UL_RE.match(line)
        if m:
            flush_buf()
            indent = len(m.group(1)) // 2
            paragraphs.append(('list', indent, _parse_inline(m.group(2))))
            continue

        m = _OL_RE.match(line)
        if m:
            flush_buf()
            indent = len(m.group(1)) // 2
            paragraphs.append(('numbered', indent, _parse_inline(m.group(2))))
            continue

        m = _QUOTE_RE.match(line)
        if m:
            flush_buf()
            flush_table()
            paragraphs.append(('quote', 0, _parse_inline(m.group(1))))
            continue

        if line.strip() == '':
            flush_buf()
        elif (line.startswith(' ') and not _UL_RE.match(line)
              and not _OL_RE.match(line)
              and paragraphs and paragraphs[-1][0] in ('list', 'numbered')):
            # continuation line of a list item — append to previous
            prev = paragraphs[-1]
            extra = _parse_inline(line.strip())
            paragraphs[-1] = (prev[0], prev[1], prev[2] + [(' ', {})] + extra)
        else:
            buf.append(line)

    flush_buf()
    flush_table()
    return paragraphs


def _parse_inline(text):
    """Parse inline MD markup into list of (text, charprops)."""
    # Tokenize by splitting on bold/italic/code markers
    parts = []
    pos   = 0
    pattern = re.compile(
        r'(`[^`]+`)'                                     # code
        r'|(\*{3}[^\s*](?:[^*]*[^\s*])?\*{3})'         # bold+italic ***
        r'|(\*{2}[^\s*](?:[^*]*[^\s*])?\*{2})'         # bold **
        r'|(\*[^\s*](?:[^*]*[^\s*])?\*)'               # italic *  (single char: *a*)
        r'|(__[^\s_](?:[^_]*[^\s_])?__)'               # bold __
        r'|(_[^\s_](?:[^_]*[^\s_])?_)',                # italic _  (single char: _a_)
        re.DOTALL
    )
    for m in pattern.finditer(text):
        if m.start() > pos:
            parts.append((text[pos:m.start()], {}))
        raw = m.group(0)
        if raw.startswith('`'):
            parts.append((raw[1:-1], {'font_family': 'Courier New'}))
        elif raw.startswith('***') or raw.startswith('___'):
            parts.append((raw[3:-3], {'bold': True, 'italic': True}))
        elif raw.startswith('**') or raw.startswith('__'):
            parts.append((raw[2:-2], {'bold': True}))
        else:
            parts.append((raw[1:-1], {'italic': True}))
        pos = m.end()
    if pos < len(text):
        parts.append((text[pos:], {}))
    return [(t, p) for t, p in parts if t]


def _github_defs(size, mm):
    s = size / 12
    return {
        'body':     {'role': 'body',     'name': 'Body',      'font_size': size, 'space_after': round(4 * s)},
        'h1':       {'role': 'h1',       'name': 'Heading 1', 'font_size': round(24 * s), 'bold': True,
                     'space_before': round(12 * s),     'space_after': round(6 * s), 'fixed_indent': 0},
        'h2':       {'role': 'h2',       'name': 'Heading 2', 'font_size': round(18 * s), 'bold': True,
                     'space_before': 5 * mm * s, 'space_after': 5 * mm * s, 'fixed_indent':1},
        'h3':       {'role': 'h3',       'name': 'Heading 3', 'font_size': round(14 * s), 'bold': True,
                     'space_before': 4 * mm * s, 'space_after': 0.5 * mm * s, 'fixed_indent': 2},
        'h4':       {'role': 'h4',       'name': 'Heading 4', 'bold': True, 'italic': True, 'fixed_indent': 3},
        'h5':       {'role': 'h5',       'name': 'Heading 5', 'font_size': max(8, round(11 * s)), 'bold': True, 'fixed_indent': 4},
        'h6':       {'role': 'h6',       'name': 'Heading 6', 'font_size': max(8, round(10 * s)), 'italic': True, 'fixed_indent': 5},
        'pre':      {'role': 'pre',      'name': 'Code',      'font_size': max(8, round(10 * s)),
                     'font_family': 'Courier New',
                     'block_color': '#F6F8FA', 'block_padding': 2 * mm * s},
        'list':     {'role': 'list',     'name': 'List',      'font_size': size, 'space_after': 0, 'paragraph_type': 'list'},
        'numbered': {'role': 'numbered', 'name': 'Numbered',  'font_size': size, 'space_after': 0, 'paragraph_type': 'numbered'},
        'quote':    {'role': 'quote',    'name': 'Quote',     'font_size': size,
                     'block_color': '#F0F0F0', 'block_padding': 2 * mm * s},
    }


def _preset_defs(preset, mm):
    if preset == 'github_small':
        return _github_defs(10, mm)
    if preset == 'report':
        return {
            'body':     {'role': 'body',     'name': 'Body',      'font_family': 'Times New Roman', 'font_size': 12,
                         'alignment': 'justify', 'line_spacing': 1.3, 'first_line_indent': 12},
            'h1':       {'role': 'h1',       'name': 'Heading 1', 'font_family': 'Times New Roman', 'font_size': 18,
                         'bold': True, 'alignment': 'center', 'space_before': 24, 'space_after': 12, 'fixed_indent': 0},
            'h2':       {'role': 'h2',       'name': 'Heading 2', 'font_family': 'Times New Roman', 'font_size': 14,
                         'bold': True, 'space_before': 18, 'space_after': 6, 'fixed_indent': 1},
            'h3':       {'role': 'h3',       'name': 'Heading 3', 'font_family': 'Times New Roman', 'font_size': 12,
                         'bold': True, 'italic': True, 'space_before': 12, 'space_after': 3, 'fixed_indent': 2},
            'h4':       {'role': 'h4',       'name': 'Heading 4', 'font_family': 'Times New Roman', 'bold': True,
                         'italic': True, 'fixed_indent': 3},
            'h5':       {'role': 'h5',       'name': 'Heading 5', 'font_family': 'Times New Roman', 'font_size': 11,
                         'bold': True, 'fixed_indent': 4},
            'h6':       {'role': 'h6',       'name': 'Heading 6', 'font_family': 'Times New Roman', 'font_size': 10,
                         'italic': True, 'fixed_indent': 5},
            'pre':      {'role': 'pre',      'name': 'Code',      'font_size': 10, 'font_family': 'Courier New',
                         'block_color': '#F0F0F0', 'block_padding': 2 * mm},
            'list':     {'role': 'list',     'name': 'List',      'font_family': 'Times New Roman', 'font_size': 12,
                         'space_after': 0, 'paragraph_type': 'list'},
            'numbered': {'role': 'numbered', 'name': 'Numbered',  'font_family': 'Times New Roman', 'font_size': 12,
                         'space_after': 0, 'paragraph_type': 'numbered'},
            'quote':    {'role': 'quote',    'name': 'Quote',     'font_family': 'Times New Roman', 'italic': True,
                         'block_padding': 2 * mm},
        }
    if preset == 'compact':
        return {
            'body':     {'role': 'body',     'name': 'Body',      'font_size': 10, 'space_after': 2},
            'h1':       {'role': 'h1',       'name': 'Heading 1', 'font_size': 14, 'bold': True,  'space_before': 6,
                         'space_after': 2, 'fixed_indent': 0},
            'h2':       {'role': 'h2',       'name': 'Heading 2', 'font_size': 12, 'bold': True,  'space_before': 4,
                         'space_after': 1, 'fixed_indent': 1},
            'h3':       {'role': 'h3',       'name': 'Heading 3', 'font_size': 10, 'bold': True,  'space_before': 3,
                         'fixed_indent': 2},
            'h4':       {'role': 'h4',       'name': 'Heading 4', 'bold': True, 'italic': True,
                         'fixed_indent': 3},
            'h5':       {'role': 'h5',       'name': 'Heading 5', 'font_size': 9,  'bold': True,
                         'fixed_indent': 4},
            'h6':       {'role': 'h6',       'name': 'Heading 6', 'font_size': 9,  'italic': True,
                         'fixed_indent': 5},
            'pre':      {'role': 'pre',      'name': 'Code',      'font_size': 9,  'font_family': 'Courier New'},
            'list':     {'role': 'list',     'name': 'List',      'font_size': 10, 'space_after': 0, 'paragraph_type': 'list'},
            'numbered': {'role': 'numbered', 'name': 'Numbered',  'font_size': 10, 'space_after': 0, 'paragraph_type': 'numbered'},
            'quote':    {'role': 'quote',    'name': 'Quote',     'font_size': 10, 'italic': True},
        }
    # github (default, 12pt)
    return _github_defs(12, mm)


def _register_styles(doc, preset='github'):
    from miniword.core.styles import style_default, updated
    mm = 72 / 25.4
    n  = len(style_default['indent_levels'])
    heading_base = {'fixed_indent': 0, 'indent_levels': (0,) * n, 'counter': 'section'}
    for name, props in _preset_defs(preset, mm).items():
        base = heading_base if name.startswith('h') else {}
        style = updated(style_default, base, props)
        doc.basestyles.set(name, style)


def apply_md_style(view, preset):
    """Apply a named MD style preset to an already-loaded document (undo-able)."""
    from miniword.core.styles import style_default, updated
    mm = 72 / 25.4
    n  = len(style_default['indent_levels'])
    heading_base = {'fixed_indent': 0, 'indent_levels': (0,) * n, 'counter': 'section'}

    role_to_key = {
        view.document.basestyles.get(k).get('role'): k
        for k in view.document.basestyles.keys()
        if view.document.basestyles.get(k) and view.document.basestyles.get(k).get('role')
    }

    with view.atomic():
        for _key, props in _preset_defs(preset, mm).items():
            role = props.get('role')
            key  = role_to_key.get(role)
            if key is None:
                continue
            base      = heading_base if role.startswith('h') else {}
            new_style = updated(style_default, base, props)
            old       = view.document.basestyles.get(key)
            old_style = old.copy() if old else None
            view.add_undo((view._undo_stylesheet, key, old_style, new_style))
            view.document.basestyles.set(key, new_style)


def get_menus(doc):
    """Return plugin menus for doc. Only adds a Markdown menu for MD documents."""
    if getattr(doc, 'home_format', None) not in ('md', 'markdown'):
        return []
    return [("&Markdown", [
        ("GitHub",       lambda frame: apply_md_style(frame.textview, 'github')),
        ("GitHub Small", lambda frame: apply_md_style(frame.textview, 'github_small')),
        ("Report",       lambda frame: apply_md_style(frame.textview, 'report')),
        ("Compact",      lambda frame: apply_md_style(frame.textview, 'compact')),
    ])]


# --- mistune-based parser (richer, handles more edge cases) -----------------

def _load_mistune(text):
    """Import using mistune for more accurate MD parsing."""
    import mistune
    from miniword.core.document import Document
    from miniword.textmodel.textmodel import TextModel

    doc = Document()
    _register_styles(doc)

    tokens = mistune.create_markdown(renderer='ast')(text)
    builder = _DocBuilder(doc)
    builder.process(tokens)
    return doc


class _DocBuilder:
    """Converts a mistune AST into a miniword Document."""

    def __init__(self, doc):
        self.doc  = doc
        self.text = ''   # accumulated raw text
        self.runs = []   # (start, end, charprops)
        self.pars = []   # (start, end, parstyle, indent)
        self._cur_props  = {}
        self._cur_ptype  = 'normal'
        self._cur_indent = 0

    def process(self, nodes):
        for node in nodes:
            self._visit(node)
        self._finalize()

    def _visit(self, node):
        t = node.get('type') if isinstance(node, dict) else None
        if t in ('heading',):
            level = node.get('attrs', {}).get('level', 1)
            self._start_par('h%d' % level, 0)
            for child in node.get('children', []):
                self._visit(child)
            self._end_par()
        elif t == 'paragraph':
            self._start_par('normal', 0)
            for child in node.get('children', []):
                self._visit(child)
            self._end_par()
        elif t == 'list':
            ordered = node.get('attrs', {}).get('ordered', False)
            ptype   = 'numbered' if ordered else 'list'
            for item in node.get('children', []):
                self._visit_list_item(item, ptype, 0)
        elif t == 'block_code':
            self._start_par('normal', 0)
            self._end_par()
            for line in node.get('raw', '').splitlines():
                self._start_par('pre', 0)
                self._append(line or ' ', {})
                self._end_par()
            self._start_par('normal', 0)
            self._end_par()
        elif t == 'text' or t == 'raw_text':
            self._append(node.get('raw', ''), self._cur_props)
        elif t == 'strong':
            old = self._cur_props
            self._cur_props = dict(old, bold=True)
            for child in node.get('children', []):
                self._visit(child)
            self._cur_props = old
        elif t == 'emphasis':
            old = self._cur_props
            self._cur_props = dict(old, italic=True)
            for child in node.get('children', []):
                self._visit(child)
            self._cur_props = old
        elif t == 'codespan':
            self._append(node.get('raw', ''), {'font_family': 'Courier New'})
        elif t == 'softbreak' or t == 'linebreak':
            self._append(' ', self._cur_props)
        elif isinstance(node, list):
            for child in node:
                self._visit(child)

    def _visit_list_item(self, item, ptype, depth):
        for child in item.get('children', []):
            if child.get('type') == 'list':
                ordered  = child.get('attrs', {}).get('ordered', False)
                subptype = 'numbered' if ordered else 'list'
                for sub in child.get('children', []):
                    self._visit_list_item(sub, subptype, depth + 1)
            elif child.get('type') == 'paragraph':
                self._start_par(ptype, depth + 1)
                for c in child.get('children', []):
                    self._visit(c)
                self._end_par()
            else:
                self._start_par(ptype, depth + 1)
                self._visit(child)
                self._end_par()

    def _start_par(self, ptype, indent):
        self._cur_ptype  = ptype
        self._cur_indent = indent
        self._par_start  = len(self.text)

    def _end_par(self):
        start = self._par_start
        self.text += '\n'
        end = len(self.text)
        self.pars.append((start, end, self._cur_ptype, self._cur_indent))
        self._cur_ptype  = 'normal'
        self._cur_indent = 0

    def _append(self, text, props):
        if not text:
            return
        start = len(self.text)
        self.text += text
        if props:
            self.runs.append((start, len(self.text), props))

    def _finalize(self):
        from miniword.textmodel.textmodel import TextModel
        doc = self.doc
        doc.textmodel = TextModel(self.text)

        for start, end, ptype, indent in self.pars:
            # NL is at end-1 (the \n we appended)
            nl_pos = end - 1
            if ptype.startswith('h') or ptype in ('pre', 'list', 'numbered', 'quote'):
                base = ptype
            else:
                base = 'body'
            ps = {'base': base}
            if ptype in ('list', 'numbered'):
                ps['paragraph_type'] = ptype
            doc.textmodel.set_parstyle(nl_pos, ps)
            if indent:
                doc.textmodel.set_parproperties(
                    nl_pos, nl_pos + 1, indent=indent)

        for start, end, props in self.runs:
            doc.textmodel.set_properties(start, end, **props)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def _check_md(doc):
    """Return list of features that cannot be represented in Markdown."""
    from miniword.textmodel.iterators import iter_paragraphs
    from miniword.textmodel.texeltree import NewLine
    from miniword.tables.tables import Table as TableTexel
    from miniword.images.images import Image as ImageTexel

    _OK_BASES  = {'normal', 'body', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                  'pre', 'list', 'numbered', 'quote'}
    _OK_PTYPES = {'normal', 'list', 'numbered'}
    _OK_PAR    = {'base', 'paragraph_type'}
    _OK_CHAR   = {'bold', 'italic', 'font_family'}
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
        for elem in elems[:-1]:
            if isinstance(elem, (TableTexel, ImageTexel)):
                if isinstance(elem, ImageTexel):
                    issues.add("images")
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
register_export("Markdown", ["md", "markdown"], _save,
                lossless=False, check_fn=_check_md)


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _parse(md):
    """Parse a MD string and return list of (base, ptype, indent, runs).

    runs: list of (text, style_dict) for each leaf texel in the paragraph.
    """
    from miniword.textmodel.iterators import iter_paragraphs, iter_leafes
    from miniword.textmodel.texeltree import NewLine, get_text
    from miniword.core.styles import style_default, updated
    doc = _load_builtin(md)
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


def test_00():
    "normal paragraph"
    pars = _parse("Hello world\n")
    assert len(pars) == 1
    base, ptype, indent, runs = pars[0]
    assert base  == 'body'
    assert ptype == 'normal'
    assert ''.join(t for t, _ in runs) == 'Hello world'


def test_01():
    "headings h1–h3"
    pars = _parse("# Heading 1\n## Heading 2\n### Heading 3\n")
    assert pars[0][0] == 'h1'
    assert pars[1][0] == 'h2'
    assert pars[2][0] == 'h3'
    assert ''.join(t for t, _ in pars[0][3]) == 'Heading 1'
    assert ''.join(t for t, _ in pars[1][3]) == 'Heading 2'
    assert ''.join(t for t, _ in pars[2][3]) == 'Heading 3'


def test_02():
    "heading with continuation line (blank line before next)"
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


def test_12():
    "table import produces Table texel with correct dimensions and cell texts"
    from miniword.textmodel.iterators import iter_paragraphs
    from miniword.textmodel.texeltree import NewLine, get_text
    from miniword.tables import Table as TableTexel
    md = "| A | B |\n| --- | --- |\n| C | D |\n"
    doc = _load_builtin(md)
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


def test_13():
    "table export roundtrip preserves headers and data rows"
    md = "| Name | City |\n| --- | --- |\n| Einstein | Ulm |\n| Darwin | Shrewsbury |\n"
    doc = _load_builtin(md)
    out = _doc_to_md(doc)
    assert '| Name' in out
    assert '| ---' in out
    assert '| Einstein' in out
    assert '| Darwin' in out


def test_14():
    "blank NL paragraphs are inserted before and after table and pre blocks"
    from miniword.textmodel.iterators import iter_paragraphs
    from miniword.textmodel.texeltree import NewLine, get_text
    from miniword.tables import Table as TableTexel

    def bases(md):
        doc = _load_builtin(md)
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
                result.append('blank' if not text.strip() else nl.parstyle.get('base', 'normal'))
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
    pars = _parse("> First line\n> Second line\n")
    assert len(pars) == 2
    for base, ptype, indent, runs in pars:
        assert base == 'quote'
    assert ''.join(t for t, _ in pars[0][3]) == 'First line'
    assert ''.join(t for t, _ in pars[1][3]) == 'Second line'

    doc = _load_builtin("> Hello\n> World\n")
    out = _doc_to_md(doc)
    assert '> Hello' in out
    assert '> World' in out
    # consecutive quotes — no blank line between them
    lines = [l for l in out.splitlines() if l.startswith('>')]
    assert len(lines) == 2


def test_16():
    "blank NL paragraphs are inserted before and after quote blocks"
    from miniword.textmodel.iterators import iter_paragraphs
    from miniword.textmodel.texeltree import NewLine, get_text

    def bases(md):
        doc = _load_builtin(md)
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
    "check_md reports images as a loss"
    import tempfile, os
    from miniword.core.document import Document
    from miniword.images.images import Image as ImageTexel
    from miniword.textmodel.texeltree import grouped, Text, NL
    from miniword.io.txlio import save, load

    doc = Document()
    doc.blobs['photo.png'] = b'\x89PNG'
    img = ImageTexel('photo.png')
    doc.textmodel.texel = grouped([Text('before '), img, Text(' after'), NL])
    warnings = _check_md(doc)
    assert "images" in warnings


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
    "table with nheader=0 gets empty header row in MD output"
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
    "table with nheader=1 roundtrips correctly"
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
        from miniword.textmodel.iterators import iter_paragraphs
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
