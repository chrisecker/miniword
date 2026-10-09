"""The horizontal rule (Markdown ---): texel, box, insert command."""

from ..textmodel.texeltree import Single
from ..layout.boxes import SingleBox
from . import insert_par


class Rule(Single):
    """Horizontal rule, alone in its paragraph (Markdown ---)."""
    text = '―'

    def __repr__(self):
        return 'HR'


class RuleBox(SingleBox):
    """A horizontal rule over width, one line high (font size)."""
    color = '#d1d9e0'

    def __init__(self, width, size, device=None):
        self.width = width
        self.height, self.depth = 0.75 * size, 0.25 * size
        self.thickness = size / 6
        if device is not None:
            self.device = device

    def draw(self, x, y, gc):
        middle = y + (self.height + self.depth) / 2
        self.device.fill_rect(x, middle - self.thickness / 2, self.width,
                              self.thickness, self.color, gc)


def insert_rule(editor):
    """Insert a horizontal rule, in a paragraph of its own (style with
    the role 'rule', if there is one)."""
    key = editor.role_key('rule')
    insert_par(editor, Rule(), {'base': key} if key else {})
