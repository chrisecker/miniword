"""
Raw HTML (Markdown HTML, shown as its source, never rendered): texel,
boxes, controller, insert command. Alone in its paragraph it is an HTML
block, collapsed (RawHTML: only its icon) or expanded (a Code of kind
'html', the icon at the top right); a double click on the icon toggles
it. A double click on inline HTML edits its source.
"""

import wx
from copy import copy as shallow_copy
from ..textmodel.texeltree import Single, length
from ..layout.boxes import SingleBox, TextBox
from ..texteditor.editor import Editor
from .code import Code, CodeController, code_at
from . import texel_at, box_hit, insert_par


class RawHTML(Single):
    """HTML from Markdown, kept as its source: shown, never rendered (a
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


class RawHTMLBox(SingleBox):
    """The source of inline HTML: its lines on a grey ground; the
    baseline is the last line's (it sits on the text's)."""
    color = '#f6f8fa'
    pad = 2

    def __init__(self, source, style, device=None):
        if device is not None:
            self.device = device
        self.lines = [TextBox(line or ' ', style, self.device)
                      for line in source.split('\n')]
        self.width = max(box.width for box in self.lines) + 2 * self.pad
        self.depth = self.lines[-1].depth
        self.height = sum(box.height + box.depth for box in self.lines) \
            - self.depth

    def draw(self, x, y, gc):
        self.device.fill_rect(x, y, self.width, self.height + self.depth,
                              self.color, gc)
        for box in self.lines:
            box.draw(x + self.pad, y, gc)
            y += box.height + box.depth


class HTMLIconBox(SingleBox):
    """The icon of an HTML block, as large as the text: a chip with </>
    in lines. Collapsed it is the block, expanded at its top right; a
    double click toggles."""
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
    """(index, texel) of the collapsed HTML block (RawHTML alone in its
    paragraph) at j - the cursor before or after it -, or None."""
    found = texel_at(editor, j, RawHTML)
    if found is None:
        return None
    i = found[0]
    model = editor.target
    if model.linestart(i) == i and model.lineend(i) == i + 1:
        return found
    return None


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


def ask_html(parent, source=''):
    """The HTML source edited in a dialog, or None (cancelled)."""
    with wx.TextEntryDialog(
            parent, "HTML source (shown as it is, never rendered):",
            "HTML", source,
            style=wx.TE_MULTILINE | wx.OK | wx.CANCEL) as dialog:
        if dialog.ShowModal() != wx.ID_OK:
            return None
        return dialog.GetValue()


def insert_html(editor, parent):
    """Insert raw HTML asked for (dialog over parent): more lines (a
    block) in a paragraph of their own, else at the cursor."""
    source = ask_html(parent)
    if not source:
        return
    if '\n' in source:
        insert_par(editor, RawHTML(source))
    else:
        with editor.atomic():
            editor.remove()
            editor.insert_texel(RawHTML(source))


class HTMLController(CodeController):
    """The cursor at raw HTML or in an HTML block: a double click on the
    block's icon collapses or expands it, on inline HTML it edits the
    source; expanded, it indents as code."""

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
        """Toggle on the icon, edit inline HTML; whether done."""
        hit = box_hit(self, x, y)
        if hit is None:
            return False
        box, bx, by = hit
        if box.pointer_at(bx, by):  # the icon
            # i1 + 1: after a collapsed block, in an expanded one
            return toggle_html(self.editor, self.i1 + 1)
        if isinstance(box, RawHTMLBox):
            return self.edit()
        return False

    def edit(self):
        """Edit the inline HTML's source in a dialog; one undo step.
        Whether it changed."""
        editor, texel = self.editor, self.texel
        source = ask_html(editor.canvas, texel.source)
        if source is None or source == texel.source:
            return False
        editor.set_texel_attributes(editor.abs_idx(self.i1), texel,
                                    source=source)
        return True


Editor.controller_registry.insert(0, HTMLController)  # innermost
