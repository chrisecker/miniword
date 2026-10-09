"""
The code block (Markdown ```, develnotes/code_block_concept.md): texel,
box, insert command. An HTML block expanded is one of kind 'html' (see
rawhtml.py).
"""

from copy import copy as shallow_copy
from ..textmodel.texeltree import Container, Text, NewLine, NL, \
    NULL_TEXEL, grouped, length, get_text
from ..textmodel.utils import iter_leafes
from ..core.utils import get_path
from ..layout.boxes import Box
from ..tables.table_boxes import TableBox, create_cell
from ..texteditor.controller import ElementController
from ..texteditor.editor import Editor
from . import insert_par


class Code(Container):
    """A code block (kind 'code', in a language lang) or HTML block (kind
    'html'): a container like a table with one cell, followed by a
    newline of its own (develnotes/code_block_concept.md)."""
    kind = 'code'
    lang = ''

    def __init__(self, content=NULL_TEXEL, kind='code', lang=''):
        self.kind, self.lang = kind, lang
        # childs as a table cell's: SEP, content, SEP ending its last line
        self.childs = [NL, content, NL.set_parstyle({'base': 'pre'})]
        self.compute_weights()

    @classmethod
    def from_text(cls, text, kind='code', lang=''):
        """A code block of text, its lines in the style 'pre'."""
        texels = []
        for line in text.split('\n'):
            texels += [Text(line), NL.set_parstyle({'base': 'pre'})]
        return cls(grouped(texels[:-1]), kind, lang)  # the last NL: ours

    @property
    def source(self):
        """The text of the code."""
        return get_text(self.childs[1])

    def set_lang(self, lang):
        clone = shallow_copy(self)
        clone.lang = lang
        return clone


class CodeBox(TableBox):
    """A code block: a table box of one cell, set from row records (the
    lines), without cell lines (the 'pre' style draws ground and frame);
    an HTML block (icon: a TextBox) gets a thin frame and the icon at
    the top right. Split at a page break into parts of whole lines; a
    continuation has no leading SEP and no icon."""
    pad = 2

    def __init__(self, records, width, kind, device=None, icon=None,
                 is_continuation=False):
        cell = create_cell(records, width, device)
        cell.length = sum(len(record[0]) for record in records)
        TableBox.__init__(self, [[cell]], [cell.width],
                          [cell.height + cell.depth], break_level=1,
                          device=device, is_continuation=is_continuation)
        self.records, self.kind, self.icon = records, kind, icon
        self.is_continuation = is_continuation

    def split(self, height):
        """The lines that fit into height (one at least) and the rest;
        None if there is no rest."""
        from ..layout.rowfactory import RowStack  # avoids a circular import
        rest = list(self.records)
        stack = RowStack(self.width)
        stack.take(rest, height)
        if not rest:
            return None
        first = [record for _, record in stack.placed]
        return (CodeBox(first, self.width, self.kind, self.device,
                        self.icon, self.is_continuation),
                CodeBox(rest, self.width, self.kind, self.device,
                        is_continuation=True))

    def icon_rect(self):
        """(x, y, w, h) of the icon, relative to the box, or None."""
        if self.icon is None:
            return None
        icon = self.icon
        return (self.width - icon.width - 2 * self.pad, 0,
                icon.width + 2 * self.pad,
                icon.height + icon.depth + 2 * self.pad)

    def pointer_at(self, x, y):
        rect = self.icon_rect()
        if rect is None:
            return None
        ix, iy, iw, ih = rect
        if ix <= x < ix + iw and iy <= y < iy + ih:
            return 'hand'  # a double click collapses the HTML block
        return None

    def draw(self, x, y, dc):
        Box.draw(self, x, y, dc)
        if self.kind == 'html':
            self.device.draw_rect(x, y, self.width, self.height, dc)
        if self.icon is not None:
            ix, iy, iw, ih = self.icon_rect()
            self.icon.draw(x + ix + self.pad, y + iy + self.pad, dc)


def shown(content, parstyle):
    """content as shown: the text without its styles, each line in
    parstyle (later: colorized)."""
    texels = []
    for *_, texel in iter_leafes(content, 0):
        if isinstance(texel, NewLine):
            texel = NL.set_parstyle(parstyle)
        elif texel.is_text:
            texel = Text(texel.text)
        texels.append(texel)
    return grouped(texels)


def code_at(editor, j):
    """(index, texel) of the code block (Code) j is in, or None."""
    for i1, i2, node in get_path(editor.target.texel, j):
        if isinstance(node, Code) and i1 < j < i2:
            return i1, node
    return None


def insert_code(editor):
    """Insert an empty code block, in a paragraph of its own; the cursor
    goes into it."""
    i = insert_par(editor, Code())
    editor.set_index(i + 1)


class CodeController(ElementController):
    """The cursor in a code block: indent and dedent (Alt+Right/Left)
    insert or remove 4 spaces at the line starts."""
    auto_installable = True

    @classmethod
    def match(cls, editor, path):
        found = code_at(editor, editor.index)
        if found is None:
            return None
        i, texel = found
        return cls(editor, texel, i, i + length(texel), len(path) - 1)

    def handle_action(self, action, shift):
        # an HTMLController at inline HTML has no Code
        if action not in ('indent', 'dedent') \
                or not isinstance(self.texel, Code):
            return super().handle_action(action, shift)
        editor = self.editor
        j1, j2 = editor.selected_range()
        editor.shift_lines(j1, j2, 4 if action == 'indent' else -4)
        return True


Editor.controller_registry.insert(0, CodeController)  # innermost
