# -*- coding: utf-8 -*-

"""
An action is a string which names an user action intented by the
user (e.g. 'move_left'). Action handlers are functions they return
True (handled) or False (not handled).
Action handlers can be combined using "join_handlers".
"""


import types

def create_ctx(editor):
    ctx = types.SimpleNamespace()
    ctx.editor = editor
    ctx.model = editor.target
    ctx.index = editor.index
    if editor.canvas is not None:
        ctx.layout = editor.canvas.layout
    else:
        ctx.layout = editor.layout

    if editor.has_selection():
        ctx.s1, ctx.s2 = sorted(editor.selection)
        #e1, e2 = model.expand_range(s1, s2)
        ctx.e1, ctx.e2 = ctx.s1, ctx.s2 # XXX
    else:
        ctx.s1 = ctx.s2 = ctx.e1 = ctx.e2 = ctx.index
    return ctx

def _navigate(layout, i, x, row_fn, flow=0):
    # row_fn is a bound method, e.g. layout.prev_row or layout.next_row
    first = row_fn(i, flow)
    if first is None:
        return None
    target_y, candidates, cur = first[3], [first], first
    while True:
        nxt = row_fn(cur[0], flow)
        if nxt is None or nxt[3] != target_y:
            break
        candidates.append(nxt)
        cur = nxt
    best_i, best_dist = None, float('inf')
    for r1, r2, rx, ry, row in candidates:
        j = r1 + row.get_index(x - rx, row.height)
        dist = abs(layout.get_rect(j, flow).x1 - x)
        if dist < best_dist:
            best_dist, best_i = dist, j
    return best_i


def _handle_action(action, shift, ctx, handlers):
    # helper
    for handler in handlers:
        if handler(action, shift, ctx):
            return True # handled
    return False # not handled
        
        
def join_handlers(*handlers):
    """Creates a combined handler function. """
    return lambda a, s, ctx: _handle_action(a, s, ctx, handlers)

    
def default_handler(action, shift, ctx):
    """Fallback handler: implements all standard editing actions."""
    editor = ctx.editor
    model = ctx.model
    index = ctx.index
    layout = ctx.layout
    canvas = editor.canvas
    #row, col = ctx.row, ctx.col
    #x, y = ctx.x, ctx.y
    #style, parstyle = ctx.style, ctx.parstyle
    e1, e2 = ctx.e1, ctx.e2
    def isalnum(j):
        return model.get_text(j, j+1).isalnum()

    if action == 'dump_info':
        dump_range(model.texel, e1, e2)
        r, c, i0 = model.index2position(index)
        print("index=", index, "row=", r, "col=", c, "i0=", i0)
    elif action == 'dump_boxes':
        layout.dump_boxes(0, 0, 0)
    elif action == 'move_word_end':
        i, n = index, len(model)
        try:
            while not isalnum(i):
                i += 1
            while isalnum(i):
                i += 1
        except IndexError:
            i = n
        editor.set_index(i, shift)
    elif action == 'move_right':
        editor.set_index(index + 1, shift)
    elif action == 'move_word_begin':
        i = index
        try:
            while not isalnum(i-1):
                i -= 1
            while isalnum(i-1):
                i -= 1
        except IndexError:
            i = 0
        editor.set_index(i, shift)
    elif action == 'move_left':
        editor.set_index(index - 1, shift)
    elif action == 'move_paragraph_end':
        i, n = model.linestart(index), len(model)
        while model.lineend(i) < n and model.linelength(i) == 1:
            i = model.lineend(i) + 1
        while model.lineend(i) < n and model.linelength(i) > 1:
            i = model.lineend(i) + 1
        editor.set_index(i, shift)
    elif action == 'move_paragraph_begin':
        i = model.linestart(index)
        while i > 0 and model.linelength(model.linestart(i - 1)) == 1:
            i = model.linestart(i - 1)
        while i > 0 and model.linelength(model.linestart(i - 1)) > 1:
            i = model.linestart(i - 1)
        editor.set_index(i, shift)
    elif action == 'move_up':
        flow = editor.flow
        x = layout.get_rect(index, flow).x1
        i = editor.abs_idx(index)
        k = _navigate(layout, i, x, layout.prev_row, flow)
        if k is not None:
            editor.set_index(editor.local_idx(k), shift)
    elif action == 'move_down':
        flow = editor.flow
        x = layout.get_rect(index, flow).x1
        i = editor.abs_idx(index)
        k = _navigate(layout, i, x, layout.next_row, flow)
        if k is not None:
            editor.set_index(editor.local_idx(k), shift)
    elif action == 'move_line_start':
        editor.set_index(model.linestart(index), shift)
    elif action == 'move_line_end':
        editor.set_index(model.lineend(index), shift)
    elif action == 'move_page_down':
        _, height = canvas.get_client_size()
        editor.set_index(editor.compute_index(x, y + height / editor.scale), shift)
    elif action == 'move_page_up':
        _, height = canvas.get_client_size()
        editor.set_index(editor.compute_index(x, y - height / editor.scale), shift)
    elif action == 'move_document_start':
        editor.set_index(0, shift)
    elif action == 'move_document_end':
        editor.set_index(len(model), shift)
    elif action == 'select_all':
        editor.selection = (0, len(model))
    elif action == 'insert_newline':
        with editor.atomic():
            editor.remove()
            editor.insert_newline()        
    elif action == 'del_left':
        with editor.atomic():
            editor.remove()
            if index > 0:
                editor.selection = index-1, index
                editor.remove()
    elif action == 'copy':
        editor.copy()
    elif action == 'paste':
        with editor.atomic():
            editor.remove()
            editor.paste()
    elif action == 'cut':
        editor.cut()
    elif action == 'delete':
        editor.remove()
    elif action == 'indent':
        editor.indent()
    elif action == 'dedent':
        editor.dedent()
    elif action == 'undo':
        editor.undo()
    elif action == 'redo':
        editor.redo()
    elif action == 'del_line_end':
        editor.selection = index, model.lineend(index)
        editor.cut()
    elif action == 'del_word_left':
        i = index
        try:
            while not model.get_text(i-1, i).isalnum(): i -= 1
            while model.get_text(i-1, i).isalnum():     i -= 1
        except IndexError:
            i = 0
        i = max(i, model.linestart(index))
        editor.selection = i, index
        editor.cut()
    else:
        return False # not handled
    return True



def code_handler(action, shift, ctx):
    """Row/column-based movement and space-indentation for code views.

    Overrides move_up/move_down (character-column based) and indent/dedent
    (leading-space insertion). All other actions fall through.
    """
    if action == 'move_up':
        row, col, i0 = model.index2position(index)        
        if row>0:
            i = model.position2index(row-1, col, i0)
            editor.set_index(i, shift)            
        return True    
    elif action == 'move_down':
        row, col, i0 = model.index2position(index)
        try:
            i = model.position2index(row+1, col, i0)
        except IndexError:
            i = model.lineend(index)
        editor.set_index(i, shift)
        return True
    elif action == 'indent':
        s1, s2 = ctx.s1, ctx.s2
        editor.shift(s1, s2)
        return True
    elif action == 'dedent':
        s1, s2 = ctx.s1, ctx.s2
        editor.unshift(s1, s2)
        return True
    return False


def _build_layout(model):
    import wx
    if wx.App.Get() is None:
        wx.App(False)
    from .editor import Editor
    from ..layout.pagebuilder import PageBuilder
    from ..layout.factory import Factory
    from ..layout.cairodevice import CairoDevice
    from ..core.styles import testsheet

    factory = Factory(testsheet, device=CairoDevice())
    builder = PageBuilder(model, factory)
    builder.rebuild()
    builder.assure_index(len(model))
    return builder.layout


def test_00():
    "move_up / move_down: normal text"
    from .editor import Editor

    editor = Editor()
    editor.canvas = None
    editor.insert_text('Line one\nLine two\nLine three')
    editor.layout = _build_layout(editor.root)

    editor.index = 12  # column 3 in "Line two"
    ctx = create_ctx(editor)
    default_handler('move_up', False, ctx)
    assert editor.index == 3  # column 3 in "Line one"

    ctx = create_ctx(editor)
    default_handler('move_down', False, ctx)
    assert editor.index == 12  # back to "Line two"

    ctx = create_ctx(editor)
    default_handler('move_down', False, ctx)
    assert editor.index == 21  # column 3 in "Line three"

    # no row above the first line: index stays unchanged
    editor.index = 3
    ctx = create_ctx(editor)
    default_handler('move_up', False, ctx)
    assert editor.index == 3


def test_01():
    "move_up / move_down: inside a footnote"
    from .editor import TestEditor
    from ..textmodel.submodel import mk_test

    model = mk_test()
    editor = TestEditor(model)
    editor.canvas = None
    editor.layout = _build_layout(model)

    editor.switch_target(1, 10)  # switch into the first footnote
    assert editor.flow == 1
    editor.index = 0

    ctx = create_ctx(editor)
    default_handler('move_down', False, ctx)
    assert editor.index == 79  # start of the second row

    ctx = create_ctx(editor)
    default_handler('move_up', False, ctx)
    assert editor.index == 0  # back to the first row
