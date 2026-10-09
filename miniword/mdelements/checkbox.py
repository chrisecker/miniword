"""
The checkbox (Markdown task lists, - [ ] / - [x]): texel, box,
controller, insert command. A click into the box toggles it.
"""

from copy import copy as shallow_copy
from ..textmodel.texeltree import Single
from ..layout.boxes import SingleBox
from ..texteditor.controller import ElementController
from ..texteditor.editor import Editor
from . import texel_at, box_hit


class Checkbox(Single):
    """A checkbox, e.g. at the start of a task list item (Markdown
    - [ ] / - [x])."""
    checked = False

    @property
    def text(self):
        return '☑' if self.checked else '☐'

    def set_checked(self, checked):
        clone = shallow_copy(self)
        clone.checked = bool(checked)
        return clone

    def __repr__(self):
        return 'CB(checked)' if self.checked else 'CB'


class CheckboxBox(SingleBox):
    """A checkbox as large as the text (font size), on the baseline,
    with some space after it; checked: filled, with a tick."""
    color = '#57606a'
    checked_color = '#0969da'

    def __init__(self, checked, size, device=None):
        self.checked = checked
        self.size = 0.75 * size  # the square
        self.width = self.size + 0.4 * size
        self.height = self.size
        if device is not None:
            self.device = device

    def pointer_at(self, x, y):
        if x < self.size and y < self.size:
            return 'hand'  # a click toggles it
        return None

    def draw(self, x, y, gc):
        s, device = self.size, self.device
        if self.checked:  # filled, a white tick
            device.fill_rect(x, y, s, s, self.checked_color, gc)
            for (x1, y1), (x2, y2) in (((.2, .55), (.42, .75)),
                                       ((.42, .75), (.8, .28))):
                device.draw_line(x + x1 * s, y + y1 * s, x + x2 * s,
                                 y + y2 * s, 2, gc, color='white')
        else:  # a frame
            line = max(1, s / 10)
            device.fill_rect(x, y, s, s, self.color, gc)
            device.fill_rect(x + line, y + line, s - 2 * line,
                             s - 2 * line, 'white', gc)


def insert_checkbox(editor):
    """Insert a checkbox at the cursor (it replaces the selection)."""
    with editor.atomic():
        editor.remove()
        editor.insert_texel(Checkbox())


class CheckboxController(ElementController):
    """The cursor at a checkbox: a click into its box toggles it (one
    undo step) - also the click that put the cursor there."""
    auto_installable = True
    click_through = True

    @classmethod
    def match(cls, editor, path):
        found = texel_at(editor, editor.index, Checkbox)
        if found is None:
            return None
        i, texel = found
        return cls(editor, texel, i, i + 1, len(path) - 1)

    def on_leftdown(self, event):
        canvas = self.editor.canvas
        return self.click(*canvas.window_to_content(event.Position))

    def click(self, x, y):
        """Toggle the checkbox if (x, y) is in its box; whether done."""
        hit = box_hit(self, x, y)
        if hit is None:
            return False
        box, bx, by = hit
        if box.pointer_at(bx, by) is None:
            return False
        editor = self.editor
        editor.set_texel_attributes(editor.abs_idx(self.i1), self.texel,
                                    checked=not self.texel.checked)
        return True


Editor.controller_registry.insert(0, CheckboxController)  # innermost
