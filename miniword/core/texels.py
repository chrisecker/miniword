from copy import copy as shallow_copy

from ..textmodel.texeltree import Single, EMPTYSTYLE


class BR(Single):
    """Forced line break (Shift-Enter). Does not start a new paragraph."""
    text = '\x0B'

    def __repr__(self):
        return 'BR'


class Checkbox(Single):
    """A checkbox, e.g. at the start of a task list item (Markdown
    - [ ] / - [x])."""
    checked = False

    @property
    def text(self):
        return '\u2611' if self.checked else '\u2610'

    def set_checked(self, checked):
        clone = shallow_copy(self)
        clone.checked = bool(checked)
        return clone

    def __repr__(self):
        return 'CB(checked)' if self.checked else 'CB'


class RawHTML(Single):
    """HTML from Markdown, kept as its source: shown, never rendered (a
    passive document), written back unchanged."""
    text = '\ufffc'

    def __init__(self, source='', style=None):
        Single.__init__(self, style)
        self.source = source

    def set_source(self, source):
        clone = shallow_copy(self)
        clone.source = source
        return clone

    def __repr__(self):
        return 'RAW(%r)' % self.source


class Rule(Single):
    """Horizontal rule, alone in its paragraph (Markdown ---)."""
    text = '\u2015'

    def __repr__(self):
        return 'HR'
