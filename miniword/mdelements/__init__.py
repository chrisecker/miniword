"""
The Markdown elements that have no package of their own - rule,
checkbox, code and HTML block: each module holds texel, box, controller
and the insert command (like tables/ and images/); panel.py the
Elements panel.
"""

from ..core.utils import get_path
from ..textmodel.texeltree import NL, grouped


def texel_at(editor, j, cls):
    """(index, texel) of the texel of class cls at j - the cursor before
    or after it -, or None."""
    model = editor.target
    for i in (j, j - 1):
        if 0 <= i < len(model):
            texel = get_path(model.texel, i)[-1][2]
            if isinstance(texel, cls):
                return i, texel
    return None


def box_hit(controller, x, y):
    """The controller's box if it is under (x, y) (content coordinates):
    (box, x, y), x and y relative to the box; else None."""
    editor = controller.editor
    found = editor.canvas.box_under(x, y)
    if found is None:
        return None
    flow, i, box, (bx, by) = found
    if flow != editor.flow or editor.local_idx(i) != controller.i1:
        return None
    return box, bx, by


def insert_par(editor, texel, parstyle={}):
    """Insert texel in a paragraph of its own (with parstyle); where it
    went."""
    with editor.atomic():
        editor.remove()
        if editor.index != editor.target.linestart(editor.index):
            editor.insert_newline()
        i = editor.index
        editor.insert_texel(grouped([texel, NL.set_parstyle(parstyle)]))
    return i
