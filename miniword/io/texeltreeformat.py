# -*- coding: utf-8 -*-
"""
TexelTree Canonical Format - Parser and Serializer

All element parameters — structural and stylistic — go in a single {…}
property block.  There are no positional arguments other than the element
type string and slot contents.

    T("text")                           -- Text with empty style
    T("text", {bold, color="red"})      -- Text with style
    NL                                  -- NewLine, indent=0, base="normal"
    NL({base="h1"})                     -- NewLine with basestyle
    NL({indent=2, base="bullet"})       -- NewLine with indent and basestyle
    TAB                                 -- Tabulator
    S("-")                              -- Other Single (char only)
    S("-", {color="red"})               -- Other Single with style
    C("frac",                           -- Container (no properties)
      [T("a")],
      [T("b")]
    )
    C("table", {ncols=2},              -- Table: ncols structural, rest style
      [T("cell1")],
      [T("cell2")]
    )

    FN(                                 -- Footnote: its content like a
      T("note")                            document, ending with ENDMARK
      ENDMARK
    )
    FN({label="*", numbering="roman"},  -- Footnote with properties
      T("note")
      ENDMARK({base="footnote"})
    )

Document format:
    PROPS({author="...", paper="A4"})   -- optional document properties
    TEXELS...
    ENDMARK({base="h1"})
"""

import ast
import re
from ..textmodel.texeltree import (
    Text, Single, Group, Container, NewLine, Tabulator,
    NL, TAB, ENDMARK, EMPTYSTYLE,
    as_style, grouped, join, length, depth,
    iter_childs, takeout
)
from ..core.texels import BR
from ..textmodel.submodel import Footnote


# ---------------------------------------------------------------------------
# Serializer: TexelTree -> str
# ---------------------------------------------------------------------------

def serialize_style(style, indent=0):
    """Serialize a style dict to {key, key="value"} notation."""
    if not style:
        return ''
    parts = []
    for k, v in sorted(style.items()):
        if v is True:
            parts.append(k)
        elif isinstance(v, str):
            parts.append('%s="%s"' % (k, v))
        elif isinstance(v, dict):
            parts.append('%s=%s' % (k, serialize_style(v)))
        else:
            parts.append('%s=%r' % (k, v))
    return '{%s}' % ', '.join(parts)


def _flatten(texel):
    """Yield leaf/container texels with Groups dissolved."""
    if texel.is_group:
        for child in texel.childs:
            yield from _flatten(child)
    else:
        yield texel


def serialize_texel(texel, indent=0):
    """Serialize a single texel (non-Group) to canonical string."""
    pad = '  ' * indent

    if texel.is_text:
        s = serialize_style(texel.style)
        if s:
            return '%sT(%r, %s)' % (pad, texel.text, s)
        else:
            return '%sT(%r)' % (pad, texel.text)

    elif texel.is_single:
        if isinstance(texel, NewLine):
            parts = {}
            if texel.indent:
                parts['indent'] = texel.indent
            if texel.parstyle:
                ps = {k: v for k, v in texel.parstyle.items()
                      if not (k == 'base' and v == 'normal')}
                parts.update(ps)
            if texel.style:
                parts['_style'] = texel.style  # rare, stored separately
            s = serialize_style(parts) if parts else ''
            if s:
                return '%sNL(%s)' % (pad, s)
            return '%sNL' % pad

        elif isinstance(texel, Tabulator):
            s = serialize_style(texel.style) if texel.style else ''
            if s:
                return '%sTAB(%s)' % (pad, s)
            return '%sTAB' % pad

        elif isinstance(texel, BR):
            s = serialize_style(texel.style) if texel.style else ''
            if s:
                return '%sBR(%s)' % (pad, s)
            return '%sBR' % pad

        elif isinstance(texel, Footnote):
            return serialize_footnote(texel, indent)

        else:
            from ..images import Image as _Image
            if isinstance(texel, _Image):
                parts = {}
                if texel.scale_x != 1.0:
                    parts['scale_x'] = texel.scale_x
                if texel.scale_y != 1.0:
                    parts['scale_y'] = texel.scale_y
                if not texel.proportional:
                    parts['proportional'] = False
                if texel.crop:
                    parts['crop_x'] = texel.crop[0]
                    parts['crop_y'] = texel.crop[1]
                    parts['crop_w'] = texel.crop[2]
                    parts['crop_h'] = texel.crop[3]
                if texel.alt:
                    parts['alt'] = texel.alt
                s = serialize_style(parts) if parts else ''
                # The data itself goes to the [blobs] section (txlio),
                # the texel refers to it by its key ('' for no data).
                from ..images.images import blob_key
                key = blob_key(texel.content) if texel.content else ''
                if s:
                    return '%sIMG(%r, %s)' % (pad, key, s)
                return '%sIMG(%r)' % (pad, key)

            s = serialize_style(texel.style) if texel.style else ''
            if s:
                return '%sS(%r, %s)' % (pad, texel.text, s)
            return '%sS(%r)' % (pad, texel.text)

    elif texel.is_container:
        return serialize_container(texel, indent)

    raise ValueError("Unknown texel type: %r" % texel)


def serialize_footnote(texel, indent=0):
    """Serialize a Footnote: FN([{props},] texels... ENDMARK). The content
    is written like a document, so its ENDMARK (with the parstyle of the
    last line) survives; nested footnotes are written recursively."""
    pad = '  ' * indent
    props = {}
    if texel.numbering != Footnote.numbering:
        props['numbering'] = texel.numbering
    if texel.label is not None:
        props['label'] = texel.label
    if texel.style != Footnote.style:
        props['_style'] = texel.style
    lines = ['%sFN(%s' % (pad, serialize_style(props) + ',' if props else '')]
    content = texel.content
    n = length(content)
    body, endmark = takeout(content, n - 1, n)
    for t in _flatten(grouped(body)):
        lines.append(serialize_texel(t, indent + 1))
    lines.append(_serialize_endmark(grouped(endmark), indent + 1))
    lines.append('%s)' % pad)
    return '\n'.join(lines)


def _serialize_endmark(endmark, indent=0):
    """ENDMARK, with its indent and parstyle (base "normal" omitted)."""
    pad = '  ' * indent
    parts = {}
    if endmark.indent:
        parts['indent'] = endmark.indent
    if endmark.parstyle:
        ps = {k: v for k, v in endmark.parstyle.items()
              if not (k == 'base' and v == 'normal')}
        parts.update(ps)
    s = serialize_style(parts) if parts else ''
    if s:
        return '%sENDMARK(%s)' % (pad, s)
    return '%sENDMARK' % pad


def _serialize_slot(content, slot_style, indent):
    """Serialize a slot as [texel, ..., {style}]."""
    pad = '  ' * indent
    flat = list(_flatten(content))
    parts = [serialize_texel(t, indent=0).strip() for t in flat]
    if slot_style:
        parts.append(serialize_style(slot_style))
    return '%s[%s]' % (pad, ', '.join(parts))


_CELL_ATTRS = ('border_left', 'border_right', 'border_top', 'border_bottom',
               'cell_halign', 'cell_valign', 'cell_bgcolor')
_CELL_DEFAULTS = {'border_left': 'thin', 'border_right': 'thin',
                  'border_top': 'thin', 'border_bottom': 'thin',
                  'cell_halign': None, 'cell_valign': 'top', 'cell_bgcolor': None}


def _sep_slot_style(sep):
    """Build slot_style dict from separator, including cell-style attrs."""
    # New API: cell attrs live in sep.parstyle
    if hasattr(sep, 'parstyle') and sep.parstyle:
        return {k: v for k, v in sep.parstyle.items()
                if k in _CELL_ATTRS and v != _CELL_DEFAULTS.get(k)}
    # Old API fallback: attrs as properties on the separator
    base = dict(sep.style) if hasattr(sep, 'style') and sep.style else {}
    for attr in _CELL_ATTRS:
        val = getattr(sep, attr, _CELL_DEFAULTS.get(attr))
        if val != _CELL_DEFAULTS.get(attr):
            base[attr] = val
    return base


def serialize_container(texel, indent=0):
    """Serialize a Container with hidden separators."""
    pad = '  ' * indent
    inner = '  ' * (indent + 1)

    ctype = texel.__class__.__name__

    # Table: each slot carries its own trailing separator's cell-style attrs.
    # This avoids the "last sep lost" problem of the generic preceding-sep convention.
    from ..tables import Table as _Table
    if isinstance(texel, _Table):
        has_n_cols = True
        ncols = texel.ncols
        props = {'ncols': ncols}
        if getattr(texel, 'nheader', 0) != 0:
            props['nheader'] = texel.nheader
        if getattr(texel, 'breaklevel', 1) != 1:
            props['breaklevel'] = texel.breaklevel
        if getattr(texel, 'col_widths', None) is not None:
            props['col_widths'] = tuple(texel.col_widths)
        cells = texel.childs[1::2]
        lines = ['%sC("Table",' % pad, '%s%s,' % (inner, serialize_style(props))]
        for i, cell in enumerate(cells):
            trailing_sep = texel.childs[2 * i + 2]
            slot_style = _sep_slot_style(trailing_sep)
            is_last = (i == len(cells) - 1)
            comma = '' if is_last else ','
            lines.append(_serialize_slot(cell, slot_style, indent + 1) + comma)
        lines.append('%s)' % pad)
        return '\n'.join(lines)

    mutable = texel.get_mutability()
    slots = []
    sep_style = EMPTYSTYLE

    for k, (i1, i2, child) in enumerate(iter_childs(texel)):
        if not mutable[k]:
            sep_style = child.style if hasattr(child, 'style') else EMPTYSTYLE
        else:
            slots.append((sep_style, child))
            sep_style = EMPTYSTYLE

    if not slots:
        return '%sC("%s")' % (pad, ctype)

    leading_sep_style = slots[0][0]
    has_n_cols = hasattr(texel, 'n_cols')
    ncols = texel.n_cols if has_n_cols else getattr(texel, '_ncols', 1)
    props = dict(leading_sep_style) if leading_sep_style else {}
    if ncols != 1 or has_n_cols:
        props['ncols'] = ncols

    lines = ['%sC("%s",' % (pad, ctype)]
    if props:
        lines.append('%s%s,' % (inner, serialize_style(props)))

    for i, (sep_s, content) in enumerate(slots):
        is_last = (i == len(slots) - 1)
        comma = '' if is_last else ','
        slot_style = sep_s if i > 0 else EMPTYSTYLE
        lines.append(_serialize_slot(content, slot_style, indent + 1) + comma)

    lines.append('%s)' % pad)
    return '\n'.join(lines)


def serialize(root, endmark=None, properties=None):
    """Serialize a TexelTree root to canonical string.

    Args:
        root:       the root Texel
        endmark:    optional NewLine endmark (carries parStyle of last paragraph)
        properties: optional document-properties dict (only non-default values)

    Returns:
        str in canonical format
    """
    lines = []

    if properties:
        lines.append('PROPS(%s)' % serialize_style(properties))

    for texel in _flatten(root):
        lines.append(serialize_texel(texel, indent=0))

    if endmark is not None:
        lines.append(_serialize_endmark(endmark))

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Parser: str -> TexelTree
# ---------------------------------------------------------------------------

class ParseError(Exception):
    pass


class _Tokenizer:
    """Simple tokenizer for the canonical format."""
    
    # Token types
    IDENT    = 'IDENT'
    STRING   = 'STRING'
    NUMBER   = 'NUMBER'
    LPAREN   = 'LPAREN'
    RPAREN   = 'RPAREN'
    LBRACE   = 'LBRACE'
    RBRACE   = 'RBRACE'
    LBRACKET = 'LBRACKET'
    RBRACKET = 'RBRACKET'
    COMMA    = 'COMMA'
    COLON    = 'COLON'
    EQUALS   = 'EQUALS'
    NEWLINE  = 'NEWLINE'
    EOF      = 'EOF'

    TOKEN_RE = re.compile(
        r'(?P<COMMENT>\#[^\n]*)'
        r'|(?P<STRING>"(?:[^"\\]|\\.)*")'
        r"|(?P<STRING2>'(?:[^'\\]|\\.)*')"
        r'|(?P<NUMBER>-?\d+(?:\.\d+)?)'
        r'|(?P<IDENT>[A-Za-z_][A-Za-z0-9_]*)'
        r'|(?P<LPAREN>\()'
        r'|(?P<RPAREN>\))'
        r'|(?P<LBRACE>\{)'
        r'|(?P<RBRACE>\})'
        r'|(?P<LBRACKET>\[)'
        r'|(?P<RBRACKET>\])'
        r'|(?P<COMMA>,)'
        r'|(?P<COLON>:)'
        r'|(?P<EQUALS>=)'
        r'|(?P<WHITESPACE>[ \t\r\n]+)'
    )

    def __init__(self, text):
        self.tokens = []
        self.pos = 0
        for m in self.TOKEN_RE.finditer(text):
            kind = m.lastgroup
            value = m.group()
            if kind in ('WHITESPACE', 'COMMENT'):
                continue
            if kind == 'STRING2':
                kind = 'STRING'
            self.tokens.append((kind, value))
        self.tokens.append((self.EOF, ''))

    def peek(self):
        return self.tokens[self.pos]

    def consume(self, expected_kind=None):
        tok = self.tokens[self.pos]
        if expected_kind and tok[0] != expected_kind:
            raise ParseError("Expected %s but got %s (%r) at token %d"
                             % (expected_kind, tok[0], tok[1], self.pos))
        self.pos += 1
        return tok

    def at_end(self):
        return self.tokens[self.pos][0] == self.EOF


class _Parser:

    def __init__(self, text, blobs=None):
        self.tok = _Tokenizer(text)
        self.blobs = blobs or {}  # {key: bytes} for IMG texels

    def parse_document(self):
        """Parse full document: optional PROPS + texels + optional ENDMARK."""
        texels = []
        endmark = None
        properties = {}

        while not self.tok.at_end():
            kind, value = self.tok.peek()
            if kind == 'IDENT' and value == 'PROPS':
                properties = self.parse_props()
            elif kind == 'IDENT' and value == 'ENDMARK':
                endmark = self.parse_endmark()
            else:
                texels.append(self.parse_texel())

        root = grouped(join(texels)) if texels else Group([])
        return root, endmark, properties

    def parse_props(self):
        self.tok.consume('IDENT')  # PROPS
        self.tok.consume('LPAREN')
        props = self.parse_style()
        self.tok.consume('RPAREN')
        return props

    def parse_texel(self):
        """Parse one texel: T, NL, TAB, S, or C."""
        kind, value = self.tok.peek()

        if kind != 'IDENT':
            raise ParseError("Expected texel type, got %r" % value)

        if value == 'T':
            return self.parse_text()
        elif value == 'NL':
            return self.parse_newline()
        elif value == 'TAB':
            return self.parse_tab()
        elif value == 'BR':
            return self.parse_br()
        elif value == 'S':
            return self.parse_single()
        elif value == 'C':
            return self.parse_container()
        elif value == 'IMG':
            return self.parse_img()
        elif value == 'FN':
            return self.parse_footnote()
        else:
            raise ParseError("Unknown texel type: %r" % value)

    def parse_text(self):
        self.tok.consume('IDENT')  # T
        self.tok.consume('LPAREN')
        text = self.parse_string()
        style = EMPTYSTYLE
        if self.tok.peek()[0] == 'COMMA':
            self.tok.consume('COMMA')
            style = as_style(self.parse_style())
        self.tok.consume('RPAREN')
        return Text(text, style)

    def parse_newline(self):
        self.tok.consume('IDENT')  # NL
        parstyle = EMPTYSTYLE
        indent = 0
        nl_style = None
        if self.tok.peek()[0] == 'LPAREN':
            self.tok.consume('LPAREN')
            if self.tok.peek()[0] == 'LBRACE':
                d = self.parse_style()
                indent = d.pop('indent', 0)
                nl_style = d.pop('_style', None)
                parstyle = as_style(d)
            self.tok.consume('RPAREN')
        nl = NL.set_parstyle(parstyle)
        nl = nl.set_indent(indent)
        if nl_style:
            nl = nl.set_style(as_style(nl_style))
        return nl

    def parse_tab(self):
        self.tok.consume('IDENT')  # TAB
        style = EMPTYSTYLE
        if self.tok.peek()[0] == 'LPAREN':
            self.tok.consume('LPAREN')
            style = as_style(self.parse_style())
            self.tok.consume('RPAREN')
        tab = TAB
        if style:
            tab = tab.set_style(style)
        return tab

    def parse_br(self):
        self.tok.consume('IDENT')  # BR
        style = EMPTYSTYLE
        if self.tok.peek()[0] == 'LPAREN':
            self.tok.consume('LPAREN')
            if self.tok.peek()[0] == 'LBRACE':
                style = as_style(self.parse_style())
            self.tok.consume('RPAREN')
        return BR(style or None)

    def parse_single(self):
        self.tok.consume('IDENT')  # S
        self.tok.consume('LPAREN')
        char = self.parse_string()
        style = EMPTYSTYLE
        if self.tok.peek()[0] == 'COMMA':
            self.tok.consume('COMMA')
            style = as_style(self.parse_style())
        self.tok.consume('RPAREN')
        s = Single(style)
        s.text = char
        return s

    def parse_img(self):
        self.tok.consume('IDENT')  # IMG
        self.tok.consume('LPAREN')
        key = self.parse_string()
        scale_x = 1.0
        scale_y = 1.0
        proportional = True
        crop = None
        alt = ''
        if self.tok.peek()[0] == 'COMMA':
            self.tok.consume('COMMA')
            d = self.parse_style()
            legacy = d.get('scale', 1.0)   # backward compat: old single scale
            scale_x = d.get('scale_x', legacy)
            scale_y = d.get('scale_y', legacy)
            proportional = d.get('proportional', True)
            if 'crop_w' in d:
                crop = (d.get('crop_x', 0), d.get('crop_y', 0), d['crop_w'], d['crop_h'])
            alt = d.get('alt', '')
        self.tok.consume('RPAREN')
        from ..images import Image
        # Hydrate from the [blobs] section: all IMGs with the same key
        # share one bytes object. A missing blob gives no content.
        return Image(self.blobs.get(key), scale_x, scale_y, proportional,
                     crop, alt)

    def parse_container(self):
        self.tok.consume('IDENT')  # C
        self.tok.consume('LPAREN')
        ctype = self.parse_string()
        self.tok.consume('COMMA')

        # Optional property block: {ncols=N, style...}
        sep0_style = EMPTYSTYLE
        ncols = 1
        has_ncols = False
        if self.tok.peek()[0] == 'LBRACE':
            d = self.parse_style()
            has_ncols = 'ncols' in d
            ncols = d.pop('ncols', 1)
            sep0_style = as_style(d) if d else EMPTYSTYLE
            if self.tok.peek()[0] == 'COMMA':
                self.tok.consume('COMMA')

        # Slots: [content..., {optional_style}]
        # slot_style is the style of the separator preceding that slot (i>0)
        slots = []  # list of (slot_style, content)
        while self.tok.peek()[0] == 'LBRACKET':
            self.tok.consume('LBRACKET')
            children = []
            slot_style = EMPTYSTYLE
            while self.tok.peek()[0] != 'RBRACKET':
                if self.tok.peek()[0] == 'LBRACE':
                    slot_style = as_style(self.parse_style())
                else:
                    children.append(self.parse_texel())
                if self.tok.peek()[0] == 'COMMA':
                    self.tok.consume('COMMA')
            self.tok.consume('RBRACKET')
            content = grouped(children) if children else Group([])
            slots.append((slot_style, content))
            if self.tok.peek()[0] == 'COMMA':
                self.tok.consume('COMMA')

        self.tok.consume('RPAREN')

        if ctype == 'Table' and has_ncols:
            from ..tables import Table
            d = dict(sep0_style) if sep0_style else {}
            # support both old (header_rows/break_level) and new (nheader/breaklevel) keys
            nheader = d.pop('nheader', d.pop('header_rows', 0))
            breaklevel = d.pop('breaklevel', d.pop('break_level', 1))
            col_widths = d.pop('col_widths', None)

            entries = []
            for slot_s, content in slots:
                cell_attrs = {k: v for k, v in slot_s.items() if k in _CELL_ATTRS} if slot_s else {}
                entries.append((content, as_style(cell_attrs)))
            table = Table(*entries, ncols=ncols,
                          nheader=nheader, breaklevel=breaklevel,
                          col_widths=list(col_widths) if col_widths is not None else None)
            return table

        # Reconstruct childs: [SEP0, content0, SEP1, content1, ..., trailing_TAB]
        # SEP0.style = sep0_style
        # SEP_i (i>0).style = slots[i][0] (style at end of slot i)
        childs = [TAB.set_style(sep0_style) if sep0_style else TAB]
        for i, (slot_style, content) in enumerate(slots):
            childs.append(content)
            if i < len(slots) - 1:
                next_style = slots[i + 1][0]
                childs.append(TAB.set_style(next_style) if next_style else TAB)
            else:
                childs.append(TAB)  # trailing separator

        c = _make_container(ctype, childs)
        if ncols != 1:
            c._ncols = ncols
        return c

    def parse_footnote(self):
        self.tok.consume('IDENT')  # FN
        self.tok.consume('LPAREN')
        props = {}
        if self.tok.peek()[0] == 'LBRACE':
            props = self.parse_style()
            if self.tok.peek()[0] == 'COMMA':
                self.tok.consume('COMMA')
        texels = []
        endmark = None
        while self.tok.peek()[0] != 'RPAREN':
            kind, value = self.tok.peek()
            if kind == 'IDENT' and value == 'ENDMARK':
                endmark = self.parse_endmark()
            else:
                texels.append(self.parse_texel())
        self.tok.consume('RPAREN')
        content = grouped(join(texels + [endmark or ENDMARK]))
        fn = Footnote(content)
        if 'numbering' in props:
            fn = fn.set_numbering(props['numbering'])
        if 'label' in props:
            fn = fn.set_label(props['label'])
        if '_style' in props:
            fn = fn.set_style(as_style(props['_style']))
        return fn

    def parse_endmark(self):
        self.tok.consume('IDENT')  # ENDMARK
        parstyle = EMPTYSTYLE
        indent = 0
        if self.tok.peek()[0] == 'LPAREN':
            self.tok.consume('LPAREN')
            if self.tok.peek()[0] == 'LBRACE':
                d = self.parse_style()
                indent = d.pop('indent', 0)
                parstyle = as_style(d)
            self.tok.consume('RPAREN')
        em = ENDMARK.set_parstyle(parstyle)
        em = em.set_indent(indent)
        return em

    def _parse_tuple(self):
        """Parse a (v, v, ...) tuple of numbers or strings."""
        self.tok.consume('LPAREN')
        items = []
        while self.tok.peek()[0] != 'RPAREN':
            kind, val = self.tok.peek()
            if kind == 'NUMBER':
                self.tok.consume()
                items.append(float(val) if '.' in val else int(val))
            elif kind == 'STRING':
                self.tok.consume()
                items.append(val[1:-1])
            elif kind == 'IDENT':
                self.tok.consume()
                # None/True/False are written as bare words (e.g. an
                # automatic column in col_widths)
                items.append({'None': None, 'True': True,
                              'False': False}.get(val, val))
            else:
                raise ParseError("Unexpected token in tuple: %r" % val)
            if self.tok.peek()[0] == 'COMMA':
                self.tok.consume('COMMA')
        self.tok.consume('RPAREN')
        return tuple(items)

    def parse_style(self):
        """Parse a {key, key="value", key=number} block. Returns dict."""
        self.tok.consume('LBRACE')
        d = {}
        while self.tok.peek()[0] != 'RBRACE':
            k_kind, k_val = self.tok.consume('IDENT')
            if self.tok.peek()[0] == 'EQUALS':
                self.tok.consume('EQUALS')
                v_kind, v_val = self.tok.peek()
                if v_kind == 'STRING':
                    self.tok.consume()
                    d[k_val] = v_val[1:-1]  # strip quotes
                elif v_kind == 'NUMBER':
                    self.tok.consume()
                    d[k_val] = float(v_val) if '.' in v_val else int(v_val)
                elif v_kind == 'IDENT':
                    self.tok.consume()
                    if v_val == 'True':
                        d[k_val] = True
                    elif v_val == 'False':
                        d[k_val] = False
                    elif v_val == 'None':
                        d[k_val] = None
                    else:
                        d[k_val] = v_val
                elif v_kind == 'LPAREN':
                    d[k_val] = self._parse_tuple()
                elif v_kind == 'LBRACE':
                    d[k_val] = self.parse_style()
                else:
                    raise ParseError("Expected style value, got %r" % v_val)
            else:
                d[k_val] = True  # bare flag

            if self.tok.peek()[0] == 'COMMA':
                self.tok.consume('COMMA')
        self.tok.consume('RBRACE')
        if 'block_padding' in d:  # files before block_offset (2026-10)
            d.setdefault('block_offset', d.pop('block_padding'))
        return d

    def parse_string(self):
        kind, value = self.tok.consume('STRING')
        return ast.literal_eval(value)  # decode escape sequences (e.g. \' \" \\)


def _make_container(ctype, childs):
    """Create a Container instance with a given type name."""
    c = Container.__new__(Container)
    c.is_container = 1
    c.childs = list(childs)
    c.compute_weights()
    c._ctype = ctype
    # Override repr
    c.__class__ = type(str(ctype), (Container,), {
        '__repr__': lambda self: 'C("%s", %r)' % (ctype, self.childs)
    })
    return c


def parse(text, blobs=None):
    """Parse canonical TexelTree format. blobs ({key: bytes}, from a
    file's [blobs] section) provides the data of IMG texels.

    Returns:
        (root, endmark, properties)
        where endmark may be None and properties may be {}
    """
    p = _Parser(text, blobs)
    return p.parse_document()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_00():
    "Roundtrip: Text with style"
    from ..textmodel.texeltree import as_style, get_text
    s = as_style({'color': 'red', 'bold': True})
    t = Text("Hello", s)
    root = Group([t])
    out = serialize(root)
    assert "T('Hello'" in out
    root2, em, _ = parse(out)
    assert get_text(root2) == "Hello"


def test_01():
    "Roundtrip: NewLine with parStyle and indent"
    from ..textmodel.texeltree import as_style, get_text
    s = as_style({'base': 'h1'})
    nl = NL.set_parstyle(s).set_indent(2)
    root = Group([Text("Hello"), nl])
    em = ENDMARK.set_parstyle(as_style({'base': 'body'}))
    out = serialize(root, em)
    assert 'indent=2' in out
    assert 'NL(' in out
    root2, em2, _ = parse(out)
    assert get_text(root2) == "Hello\n"
    assert em2 is not None


def test_02():
    "Roundtrip: Container (Fraction)"
    from ..textmodel.texeltree import Fraction, get_text
    f = Fraction(Text("Sin(x)"), Text("Cos(x)"))
    root = Group([f])
    out = serialize(root)
    root2, _, _ = parse(out)
    assert get_text(root2) == "\tSin(x)\tCos(x)\t"


def test_03():
    "Roundtrip: Nested containers"
    from ..textmodel.texeltree import Fraction, get_text
    inner = Fraction(Text("a"), Text("b"))
    outer = Fraction(inner, Text("c"))
    root = Group([outer])
    out = serialize(root)
    root2, _, _ = parse(out)
    assert get_text(root2) == "\t\ta\tb\t\tc\t"


def test_05():
    "Roundtrip: document properties"
    from ..textmodel.texeltree import get_text
    props = {'author': 'Max', 'paper': 'A4', 'margin_top': 2.5}
    root = Group([Text("Hello")])
    out = serialize(root, properties=props)
    assert out.startswith('PROPS(')
    root2, em2, props2 = parse(out)
    assert get_text(root2) == "Hello"
    assert props2['author'] == 'Max'
    assert props2['paper'] == 'A4'
    assert props2['margin_top'] == 2.5


def test_06():
    "Roundtrip: Container with ncols"
    from ..textmodel.texeltree import get_text
    childs = [TAB, Text("A"), TAB, Text("B"), TAB, Text("C"), TAB, Text("D"), TAB]
    c = _make_container("table", childs)
    c._ncols = 2
    root = Group([c])
    out = serialize(root)
    assert 'ncols=2' in out
    root2, _, _ = parse(out)
    c2 = list(_flatten(root2))[0]
    assert c2._ncols == 2
    assert get_text(root2) == "\tA\tB\tC\tD\t"


def test_04():
    "Roundtrip: Container slot with style"
    from ..textmodel.texeltree import get_text, as_style
    sep_left  = TAB.set_style(as_style({'align': 'left'}))
    sep_right = TAB.set_style(as_style({'align': 'right'}))

    class Table(Container):
        def __init__(self, cell1, cell2):
            self.childs = [sep_left, cell1, sep_right, cell2, TAB]
            self.compute_weights()

    t = Table(Text("A"), Text("B"))
    root = Group([t])
    out = serialize(root)
    # leading sep style before slots, slot style at end of slot
    assert '{align="left"}' in out
    assert '[T(\'A\')]' in out or '[T("A")]' in out
    assert 'align="right"' in out
    root2, _, _ = parse(out)
    assert get_text(root2) == "\tA\tB\t"


def test_07():
    "Roundtrip: BR (forced line break)"
    from ..textmodel.texeltree import get_text, as_style
    br = BR()
    root = Group([Text("line1"), br, NL])
    out = serialize(root)
    assert 'BR' in out
    root2, _, _ = parse(out)
    assert get_text(root2) == 'line1\x0b\n'


def test_08():
    "Roundtrip: Table with cell attrs and nheader"
    from ..tables import from_strings
    from ..textmodel.texeltree import Group
    table = from_strings([['A', 'B'], ['C', 'D']])
    table = table.set_cellattr(0, 0, 0, 0, border_left='none')
    table = table.set_nheader(1)
    root = Group([table])
    out = serialize(root)
    assert 'nheader=1' in out
    assert 'border_left="none"' in out
    root2, _, _ = parse(out)
    t2 = list(_flatten(root2))[0]
    assert t2.nrows == 2
    assert t2.ncols == 2
    assert t2.nheader == 1
    cells = t2.get_cells()
    assert cells[0][0].get_attr('border_left') == 'none'


def test_09():
    "footnotes: content, nesting, label, numbering, style, endmark"
    from ..textmodel.submodel import Footnote
    em = ENDMARK.set_parstyle({'alignment': 'right'})
    f2 = Footnote(grouped([Text('inner'), em])).set_label('*')
    f1 = Footnote(grouped([Text('outer '), f2, Text(' end'), NL,
                           Text('second'), ENDMARK]))
    f1 = f1.set_numbering('roman').set_style({'bold': True})
    root = grouped([Text('ab'), f1, Text('cd')])
    text = serialize(root)
    assert text.count('FN(') == 2
    root2, endmark, props = parse(text)
    assert serialize(root2) == text
    g1 = [t for t in _flatten(root2) if isinstance(t, Footnote)][0]
    assert (g1.numbering, g1.label, dict(g1.style)) == \
        ('roman', None, {'bold': True})
    assert length(g1.content) == length(f1.content)
    inner = [t for t in _flatten(g1.content) if isinstance(t, Footnote)][0]
    assert inner.label == '*'
    last = list(_flatten(inner.content))[-1]
    assert last.is_endmark and last.parstyle.get('alignment') == 'right'


def test_10():
    "Roundtrip: None in a tuple (automatic table column)"
    from ..tables import from_strings
    table = from_strings([['A', 'B']]).set_col_widths([30, None])
    root2, _, _ = parse(serialize(Group([table])))
    t2 = list(_flatten(root2))[0]
    assert list(t2.col_widths) == [30, None]


def test_11():
    "Old files: block_padding is read as block_offset"
    root, _, _ = parse('T(\'a\')\nNL({block_color="red", block_padding=3})')
    nl = list(_flatten(root))[-1]
    assert nl.parstyle.get('block_offset') == 3
    assert 'block_padding' not in nl.parstyle
    # a block_offset written as well wins
    root, _, _ = parse(
        'T(\'a\')\nNL({block_offset=2, block_padding=3})')
    nl = list(_flatten(root))[-1]
    assert dict(nl.parstyle) == {'block_offset': 2}


def test_12():
    "Roundtrip: right indent and block properties"
    from ..textmodel.texeltree import NewLine
    ps = dict(right_indent=20, block_color='red', block_offset=3,
              block_border_width=1.5, block_border_color='blue',
              block_border_sides='tb', widow_orphan_control=False)
    root, _, _ = parse(serialize(Group([Text('a'),
                                        NewLine().set_parstyle(ps)])))
    nl = list(_flatten(root))[-1]
    assert dict(nl.parstyle) == ps
