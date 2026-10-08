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


class Rule(Single):
    """Horizontal rule, alone in its paragraph (Markdown ---)."""
    text = '\u2015'

    def __repr__(self):
        return 'HR'
