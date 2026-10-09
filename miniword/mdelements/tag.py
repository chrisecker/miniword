"""
Inline HTML (Markdown: a tag in the text, e.g. <kbd>): texel, box,
insert command. A tag is a container [<, content, >]: its source is
edited in the text, between the brackets. Shown as a chip, never
rendered, written back unchanged. HTML blocks see rawhtml.py.
"""

from ..textmodel.texeltree import NewLine, Container, Text, \
    NULL_TEXEL, get_text
from ..layout.boxes import HBox


class Bracket(NewLine):
    """A separator of a tag, '<' or '>': a newline, as a container's
    separators are (the model finds a cell's end by it); outside the
    container it does not count."""

    def __init__(self, text):
        self.text = text

    def __repr__(self):
        return 'Bracket(%r)' % self.text


OPEN, CLOSE = Bracket('<'), Bracket('>')


class Tag(Container):
    """One HTML tag in the text, kept as its source."""

    def __init__(self, source='<>'):
        inner = source[1:-1]  # without the brackets
        self.childs = [OPEN, Text(inner) if inner else NULL_TEXEL, CLOSE]
        self.compute_weights()

    @property
    def source(self):
        return '<%s>' % get_text(self.childs[1])


class TagBox(HBox):
    """A tag: its source (text boxes, one per bracket and the content)
    on a light ground in a thin frame."""
    color = '#0969da'
    ground = '#ddf4ff'

    def draw(self, x, y, gc):
        w, h, device = self.width, self.height + self.depth, self.device
        line = 0.5  # the frame
        device.fill_rect(x, y, w, h, self.color, gc)
        device.fill_rect(x + line, y + line, w - 2 * line, h - 2 * line,
                         self.ground, gc)
        HBox.draw(self, x, y, gc)


def insert_tag(editor):
    """Insert an empty tag <> at the cursor (it replaces the selection);
    the cursor goes between the brackets."""
    with editor.atomic():
        editor.remove()
        i = editor.index
        editor.insert_texel(Tag())
    editor.set_index(i + 1)
