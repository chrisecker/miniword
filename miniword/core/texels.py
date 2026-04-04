from ..textmodel.texeltree import Single, EMPTYSTYLE


class BR(Single):
    """Forced line break (Shift-Enter). Does not start a new paragraph."""
    text = '\x0B'

    def __repr__(self):
        return 'BR'
