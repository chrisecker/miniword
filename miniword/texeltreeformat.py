# -*- coding: utf-8 -*-
"""
TexelTree Canonical Format - Parser and Serializer

Canonical format uses 3 types (Groups dissolved):
    T("text")                         -- Text with empty style
    T("text", {bold, color="red"})    -- Text with style
    NL                                -- NewLine with empty styles
    NL({parStyle="h1", indent=2})     -- NewLine with parStyle/indent
    TAB                               -- Tabulator
    S("-")                            -- Other Single (char only)
    S("-", {color="red"})             -- Other Single with style
    C("frac",                         -- Container
      T("a"),
      T("b")
    )
    C("table",                        -- Container with slot styles
      {align="left"}: T("cell1"),
      {align="right"}: (T("line1") NL T("line2"))
    )

Document format:
    TEXELS...
    ENDMARK({parStyle="h1", indent=0})
"""

import re
from .textmodel.texeltree import (
    Text, Single, Group, Container, NewLine, Tabulator,
    NL, TAB, ENDMARK, EMPTYSTYLE,
    as_style, grouped, join, length, depth,
    iter_childs
)


# ---------------------------------------------------------------------------
# Serializer: TexelTree -> str
# ---------------------------------------------------------------------------

def serialize_style(style, indent=0):
    """Serialize a style dict to {key, key="value"} notation."""
    if not style:
        return ''
    parts = []
    for k, v in sorted(style.items()):
        if v is True or v == 1:
            parts.append(k)
        elif isinstance(v, str):
            parts.append('%s="%s"' % (k, v))
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
            if texel.parstyle:
                parts.update(texel.parstyle)
            if texel.indent:
                parts['indent'] = texel.indent
            if texel.style:
                parts['_style'] = texel.style  # rare, stored separately
            if parts:
                s = serialize_style(parts)
                return '%sNL(%s)' % (pad, s)
            return '%sNL' % pad

        elif isinstance(texel, Tabulator):
            s = serialize_style(texel.style) if texel.style else ''
            if s:
                return '%sTAB(%s)' % (pad, s)
            return '%sTAB' % pad

        else:
            s = serialize_style(texel.style) if texel.style else ''
            if s:
                return '%sS(%r, %s)' % (pad, texel.text, s)
            return '%sS(%r)' % (pad, texel.text)

    elif texel.is_container:
        return serialize_container(texel, indent)

    raise ValueError("Unknown texel type: %r" % texel)


def serialize_container(texel, indent=0):
    """Serialize a Container with hidden separators."""
    pad = '  ' * indent
    inner = '  ' * (indent + 1)

    # Extract type name
    ctype = texel.__class__.__name__

    # Get mutable slots and their preceding separator styles
    mutable = texel.get_mutability()
    slots = []
    sep_style = EMPTYSTYLE

    for k, (i1, i2, child) in enumerate(iter_childs(texel)):
        if not mutable[k]:
            # This is a separator - capture its style
            sep_style = child.style if hasattr(child, 'style') else EMPTYSTYLE
        else:
            # This is content - serialize with preceding sep style
            slots.append((sep_style, child))
            sep_style = EMPTYSTYLE

    if not slots:
        return '%sC("%s")' % (pad, ctype)

    lines = ['%sC("%s",' % (pad, ctype)]
    for i, (sep_s, content) in enumerate(slots):
        is_last = (i == len(slots) - 1)
        comma = '' if is_last else ','

        # Serialize content (flatten groups)
        flat = list(_flatten(content))
        if len(flat) == 1:
            content_str = serialize_texel(flat[0], indent=indent + 1).lstrip()
        else:
            # Multiple texels in slot -> wrap in (...)
            inner_lines = [serialize_texel(t, indent=indent + 2) for t in flat]
            content_str = '(\n%s\n%s)' % (
                '\n'.join(inner_lines),
                inner
            )

        if sep_s:
            style_str = serialize_style(sep_s)
            lines.append('%s%s: %s%s' % (inner, style_str, content_str, comma))
        else:
            lines.append('%s%s%s' % (inner, content_str, comma))

    lines.append('%s)' % pad)
    return '\n'.join(lines)


def serialize(root, endmark=None):
    """Serialize a TexelTree root to canonical string.

    Args:
        root: the root Texel
        endmark: optional NewLine endmark (carries parStyle of last paragraph)

    Returns:
        str in canonical format
    """
    lines = []
    for texel in _flatten(root):
        lines.append(serialize_texel(texel, indent=0))

    if endmark is not None:
        parts = {}
        if endmark.parstyle:
            parts.update(endmark.parstyle)
        if endmark.indent:
            parts['indent'] = endmark.indent
        if parts:
            lines.append('ENDMARK(%s)' % serialize_style(parts))
        else:
            lines.append('ENDMARK')

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Parser: str -> TexelTree
# ---------------------------------------------------------------------------

class ParseError(Exception):
    pass


class _Tokenizer:
    """Simple tokenizer for the canonical format."""
    
    # Token types
    IDENT   = 'IDENT'
    STRING  = 'STRING'
    NUMBER  = 'NUMBER'
    LPAREN  = 'LPAREN'
    RPAREN  = 'RPAREN'
    LBRACE  = 'LBRACE'
    RBRACE  = 'RBRACE'
    COMMA   = 'COMMA'
    COLON   = 'COLON'
    EQUALS  = 'EQUALS'
    NEWLINE = 'NEWLINE'
    EOF     = 'EOF'

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

    def __init__(self, text):
        self.tok = _Tokenizer(text)

    def parse_document(self):
        """Parse full document: texels + optional ENDMARK."""
        texels = []
        endmark = None

        while not self.tok.at_end():
            kind, value = self.tok.peek()
            if kind == 'IDENT' and value == 'ENDMARK':
                endmark = self.parse_endmark()
            else:
                texels.append(self.parse_texel())

        root = grouped(join(texels)) if texels else Group([])
        return root, endmark

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
        elif value == 'S':
            return self.parse_single()
        elif value == 'C':
            return self.parse_container()
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
        if self.tok.peek()[0] == 'LPAREN':
            self.tok.consume('LPAREN')
            d = self.parse_style()
            indent = d.pop('indent', 0)
            parstyle = as_style(d)
            self.tok.consume('RPAREN')
        nl = NL.set_parstyle(parstyle)
        nl = nl.set_indent(indent)
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

    def parse_container(self):
        self.tok.consume('IDENT')  # C
        self.tok.consume('LPAREN')
        ctype = self.parse_string()
        self.tok.consume('COMMA')

        # Build a Container subclass dynamically
        slots = []  # list of (sep_style, content_texel)
        while self.tok.peek()[0] != 'RPAREN':
            sep_style = EMPTYSTYLE
            # Check for optional {style}:
            if self.tok.peek()[0] == 'LBRACE':
                sep_style = as_style(self.parse_style())
                self.tok.consume('COLON')

            # Parse content: single texel or (texel texel ...)
            if self.tok.peek()[0] == 'LPAREN':
                self.tok.consume('LPAREN')
                children = []
                while self.tok.peek()[0] != 'RPAREN':
                    children.append(self.parse_texel())
                self.tok.consume('RPAREN')
                content = grouped(children) if children else Group([])
            else:
                content = self.parse_texel()

            slots.append((sep_style, content))

            if self.tok.peek()[0] == 'COMMA':
                self.tok.consume('COMMA')

        self.tok.consume('RPAREN')

        # Reconstruct childs: [SEP, content, SEP, content, ..., SEP]
        childs = []
        for sep_style, content in slots:
            sep = TAB.set_style(sep_style) if sep_style else TAB
            childs.append(sep)
            childs.append(content)
        childs.append(TAB)  # trailing separator

        # Create anonymous Container subclass with given type name
        c = _make_container(ctype, childs)
        return c

    def parse_endmark(self):
        self.tok.consume('IDENT')  # ENDMARK
        parstyle = EMPTYSTYLE
        indent = 0
        if self.tok.peek()[0] == 'LPAREN':
            self.tok.consume('LPAREN')
            d = self.parse_style()
            indent = d.pop('indent', 0)
            parstyle = as_style(d)
            self.tok.consume('RPAREN')
        em = ENDMARK.set_parstyle(parstyle)
        em = em.set_indent(indent)
        return em

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
                    d[k_val] = v_val
                else:
                    raise ParseError("Expected style value, got %r" % v_val)
            else:
                d[k_val] = True  # bare flag

            if self.tok.peek()[0] == 'COMMA':
                self.tok.consume('COMMA')
        self.tok.consume('RBRACE')
        return d

    def parse_string(self):
        kind, value = self.tok.consume('STRING')
        return value[1:-1]  # strip surrounding quotes


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


def parse(text):
    """Parse canonical TexelTree format.

    Returns:
        (root, endmark) where endmark may be None
    """
    p = _Parser(text)
    return p.parse_document()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_00():
    "Roundtrip: Text with style"
    from .textmodel.texeltree import as_style, get_text
    s = as_style({'color': 'red', 'bold': True})
    t = Text("Hello", s)
    root = Group([t])
    out = serialize(root)
    assert "T('Hello'" in out
    root2, em = parse(out)
    assert get_text(root2) == "Hello"


def test_01():
    "Roundtrip: NewLine with parStyle"
    from .textmodel.texeltree import as_style, get_text
    s = as_style({'base': 'h1'})
    nl = NL.set_parstyle(s).set_indent(2)
    root = Group([Text("Hello"), nl])
    em = ENDMARK.set_parstyle(as_style({'base': 'body'}))
    out = serialize(root, em)
    root2, em2 = parse(out)
    assert get_text(root2) == "Hello\n"
    assert em2 is not None


def test_02():
    "Roundtrip: Container (Fraction)"
    from .textmodel.texeltree import Fraction, get_text
    f = Fraction(Text("Sin(x)"), Text("Cos(x)"))
    root = Group([f])
    out = serialize(root)
    root2, _ = parse(out)
    assert get_text(root2) == "\tSin(x)\tCos(x)\t"


def test_03():
    "Roundtrip: Nested containers"
    from .textmodel.texeltree import Fraction, get_text
    inner = Fraction(Text("a"), Text("b"))
    outer = Fraction(inner, Text("c"))
    root = Group([outer])
    out = serialize(root)
    root2, _ = parse(out)
    assert get_text(root2) == "\t\ta\tb\t\tc\t"


def test_04():
    "Roundtrip: Container slot with style"
    from .textmodel.texeltree import get_text, as_style
    sep_left  = TAB.set_style(as_style({'align': 'left'}))
    sep_right = TAB.set_style(as_style({'align': 'right'}))

    class Table(Container):
        def __init__(self, cell1, cell2):
            self.childs = [sep_left, cell1, sep_right, cell2, TAB]
            self.compute_weights()

    t = Table(Text("A"), Text("B"))
    root = Group([t])
    out = serialize(root)
    root2, _ = parse(out)
    assert get_text(root2) == "\tA\tB\t"
    assert 'align' in out


