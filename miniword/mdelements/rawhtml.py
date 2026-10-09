"""
HTML blocks (Markdown, never rendered): texel, box, controller, insert
command. Collapsed (RawHTML) a block is only its icon, in a row of its
own; expanded (a Code of kind 'html') the icon is at its top right; a
double click on the icon toggles it. Inline HTML see tag.py.
"""

from copy import copy as shallow_copy
from ..textmodel.texeltree import Single, length
from ..layout.boxes import SingleBox
from ..texteditor.editor import Editor
from .code import Code, CodeController, code_at
from . import texel_at, box_hit, insert_par


class RawHTML(Single):
    """An HTML block, collapsed, kept as its source: never rendered (a
    passive document), written back unchanged."""
    text = '￼'

    def __init__(self, source='', style=None):
        Single.__init__(self, style)
        self.source = source

    def set_source(self, source):
        clone = shallow_copy(self)
        clone.source = source
        return clone

    def __repr__(self):
        return 'RAW(%r)' % self.source


class HTMLIconBox(SingleBox):
    """The icon of an HTML block, as large as the text: a chip with </>
    in lines. Collapsed it is the block, expanded at its top right; a
    double click toggles."""
    standalone = True
    color = '#0969da'
    ground = '#ddf4ff'
    strokes = (((.32, .3), (.2, .5)), ((.2, .5), (.32, .7)),  # <
               ((.56, .22), (.44, .78)),  # /
               ((.68, .3), (.8, .5)), ((.8, .5), (.68, .7)))  # >

    def __init__(self, size, device=None):
        self.size = size
        self.width = 1.8 * size
        self.height, self.depth = 0.75 * size, 0.15 * size
        if device is not None:
            self.device = device

    def pointer_at(self, x, y):
        return 'hand'

    def draw(self, x, y, gc):
        w, h, device = self.width, self.height + self.depth, self.device
        line = self.size / 16  # the frame
        device.fill_rect(x, y, w, h, self.color, gc)
        device.fill_rect(x + line, y + line, w - 2 * line, h - 2 * line,
                         self.ground, gc)
        for (x1, y1), (x2, y2) in self.strokes:
            device.draw_line(x + x1 * w, y + y1 * h, x + x2 * w,
                             y + y2 * h, 1.5, gc, color=self.color)


def html_at(editor, j):
    """(index, texel) of the collapsed HTML block at j - the cursor
    before or after it -, or None."""
    return texel_at(editor, j, RawHTML)


def toggle_html(editor, j):
    """Expand the collapsed HTML block at j (RawHTML -> Code), or
    collapse the expanded one j is in; one undo step. Whether there was
    one."""
    found = html_at(editor, j)
    if found:
        i, texel = found
        new = Code.from_text(texel.source, kind='html')
    else:
        found = code_at(editor, j)
        if not found or found[1].kind != 'html':
            return False
        i, texel = found
        new = RawHTML(texel.source)
    editor.replace_texel(editor.abs_idx(i), texel, new)
    return True


def insert_html(editor):
    """Insert an empty HTML block, expanded, in a paragraph of its own;
    the cursor goes into it."""
    i = insert_par(editor, Code(kind='html'))
    editor.set_index(i + 1)


class HTMLController(CodeController):
    """The cursor at an HTML block: a double click on its icon collapses
    or expands it; expanded, it indents as code."""

    @classmethod
    def match(cls, editor, path):
        found = texel_at(editor, editor.index, RawHTML)
        if found is None:
            found = code_at(editor, editor.index)
            if found is None or found[1].kind != 'html':
                return None
        i, texel = found
        return cls(editor, texel, i, i + length(texel), len(path) - 1)

    def on_leftdclick(self, event):
        canvas = self.editor.canvas
        return self.double_click(*canvas.window_to_content(event.Position))

    def double_click(self, x, y):
        """Toggle on the icon; whether done."""
        hit = box_hit(self, x, y)
        if hit is None:
            return False
        box, bx, by = hit
        if box.pointer_at(bx, by) is None:
            return False
        # i1 + 1: after a collapsed block, in an expanded one
        return toggle_html(self.editor, self.i1 + 1)


Editor.controller_registry.insert(0, HTMLController)  # innermost
