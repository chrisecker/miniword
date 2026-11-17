"""
Raw (develnotes/markdown_concept.md, "Das Element Raw"): source for a
target format, its language (html, markdown ...), never rendered (a
passive document), written back unchanged by the export of that format
and left out by the others. Collapsed (RawIcon) it is only its icon, in
a row of its own; expanded (Raw) the source, the icon at its top right;
a double click on the icon toggles it. Texels, box, controller, insert
command. Inline HTML see tag.py.
"""

from copy import copy as shallow_copy
from ..textmodel.texeltree import Single, length
from ..layout.boxes import SingleBox
from ..texteditor.editor import Editor
from .code import Code, CodeController, code_at
from . import texel_at, box_hit, insert_par


class Raw(Code):
    """Raw, expanded: its source as lines, like a code block (the
    language colors it); a code block it is not."""
    txl_name = 'raw'  # the type in TXL files: C("raw", ...)
    lang = 'html'


class RawIcon(Single):
    """Raw, collapsed: its source, shown as an icon."""
    text = '￼'
    lang = 'html'

    def __init__(self, source='', lang=None, style=None):
        Single.__init__(self, style)
        self.source = source
        if lang is not None:
            self.lang = lang

    def set_source(self, source):
        clone = shallow_copy(self)
        clone.source = source
        return clone

    def set_lang(self, lang):
        clone = shallow_copy(self)
        clone.lang = lang
        return clone

    def __repr__(self):
        return 'RAW(%r, %r)' % (self.source, self.lang)


# the languages offered, their names; the label of an icon (html: </>)
NAMES = {'html': 'HTML', 'markdown': 'Markdown', 'tex': 'TeX'}
LABELS = {'markdown': 'MD', 'tex': 'TeX'}


class RawIconBox(SingleBox):
    """The icon of Raw, as large as the text: a chip with </> in lines
    (html) or its label (a TextBox, see LABELS). Collapsed it is Raw,
    expanded at its top right; a double click toggles."""
    standalone = True
    color = '#0969da'
    ground = '#ddf4ff'
    strokes = (((.32, .3), (.2, .5)), ((.2, .5), (.32, .7)),  # <
               ((.56, .22), (.44, .78)),  # /
               ((.68, .3), (.8, .5)), ((.8, .5), (.68, .7)))  # >

    def __init__(self, size, label=None, device=None):
        self.size, self.label = size, label
        self.width = 1.8 * size
        if label is not None:
            self.width = max(self.width, label.width + 0.6 * size)
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
        label = self.label
        if label is not None:
            label.draw(x + (w - label.width) / 2,
                       y + (h - label.height - label.depth) / 2, gc)
            return
        for (x1, y1), (x2, y2) in self.strokes:
            device.draw_line(x + x1 * w, y + y1 * h, x + x2 * w,
                             y + y2 * h, 1.5, gc, color=self.color)


def raw_at(editor, j):
    """(index, texel) of the collapsed Raw (RawIcon) at j - the cursor
    before or after it -, or None."""
    return texel_at(editor, j, RawIcon)


def expanded_raw_at(editor, j):
    """(index, texel) of the expanded Raw j is in, or None."""
    found = code_at(editor, j)
    if found is None or not isinstance(found[1], Raw):
        return None
    return found


def any_raw_at(editor, j):
    """(index, texel) of the Raw at j, collapsed or expanded, or None."""
    return raw_at(editor, j) or expanded_raw_at(editor, j)


def toggle_raw(editor, j):
    """Expand the collapsed Raw at j (the cursor goes into it), or
    collapse the expanded one j is in; one undo step. Whether there was
    one."""
    found = raw_at(editor, j)
    if found:
        i, texel = found
        new = Raw.from_text(texel.source, texel.lang)
    else:
        found = expanded_raw_at(editor, j)
        if not found:
            return False
        i, texel = found
        new = RawIcon(texel.source, texel.lang)
    editor.replace_texel(editor.abs_idx(i), texel, new)
    if isinstance(new, Raw):
        editor.set_index(i + 1)
    return True


def insert_raw(editor):
    """Insert an empty Raw HTML, expanded, in a paragraph of its own;
    the cursor goes into it."""
    i = insert_par(editor, Raw())
    editor.set_index(i + 1)


class RawController(CodeController):
    """The cursor at Raw: a double click on its icon collapses or
    expands it; expanded, it indents as code."""

    @classmethod
    def match(cls, editor, path):
        found = any_raw_at(editor, editor.index)
        if found is None:
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
        # i1 + 1: after a collapsed Raw, in an expanded one
        return toggle_raw(self.editor, self.i1 + 1)


Editor.controller_registry.insert(0, RawController)  # innermost
