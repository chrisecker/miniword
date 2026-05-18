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
    #ctx.layout = self.layout
    #style = self.get_current_style()
    #parstyle = model.get_parstyle(index)
    #row, col = self.current_position()
    #rect = layout.get_rect(index, 0, 0)
    #x, y = rect.x1, rect.y1
    if editor.has_selection():
        ctx.s1, ctx.s2 = sorted(editor.selection)
        #e1, e2 = model.expand_range(s1, s2)
        ctx.e1, ctx.e2 = ctx.s1, ctx.s2 # XXX
    else:
        ctx.s1 = ctx.s2 = ctx.e1 = ctx.e2 = ctx.index
    return ctx

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
        ctx.layout.dump_boxes(0, 0, 0)
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
        row, col, i0 = model.index2position(index)
        print("move_up from:", row, col, i0)
        if row>0:
            i = model.position2index(row-1, col, i0)
            editor.set_index(i, shift)
    elif action == 'move_down':
        row, col, i0 = model.index2position(index)
        try:
            i = model.position2index(row+1, col, i0)
        except IndexError:
            i = model.lineend(index)
        editor.set_index(i, shift)            
    elif action == 'move_line_start':
        editor.set_index(model.linestart(index), shift)
    elif action == 'move_line_end':
        editor.set_index(model.lineend(index), shift)
    elif action == 'move_page_down':
        _, height = editor.get_client_size()
        editor.set_index(editor.compute_index(x, y + height / editor.scale), shift)
    elif action == 'move_page_up':
        _, height = editor.get_client_size()
        editor.set_index(editor.compute_index(x, y - height / editor.scale), shift)
    elif action == 'move_document_start':
        editor.set_index(0, shift)
    elif action == 'move_document_end':
        editor.set_index(len(model), shift)
    elif action == 'select_all':
        editor.selection = (0, len(model))
    elif action == 'insert_newline':
        editor.insert_newline()
    elif action == 'backspace':
        if editor.has_selection():
            j1, j2 = model.expand_range(ctx.s1 - 1, ctx.s2)
            editor.remove(e1, e2) if j2 != e2 else editor.remove(j1, j2)
        elif index > 0:
            j1, j2 = model.expand_range(index - 1, index)
            editor.remove(j1, j2)
    elif action == 'copy':
        editor.editor.copy()
    elif action == 'paste':
        editor.editor.paste()
    elif action == 'cut':
        editor.editor.cut()
    elif action == 'delete':
        if editor.has_selection():
            ctx.del_selection()
        elif index < len(model):
            j1, j2 = model.expand_range(index, index + 1)
            editor.remove(j1, j2)
    elif action == 'indent':
        editor.indent()
    elif action == 'dedent':
        editor.dedent()
    elif action == 'undo':
        editor.undo()
    elif action == 'redo':
        editor.redo()
    elif action == 'del_line_end':
        el, off = get_localroot(model.texel, index)
        try:
            i = find_weight(el, row + 1, 2) - 1 + off
        except Exception:
            i = length(el) - 1 + off
        if i == index:
            i += 1
        i = min(i, model.get_end(index))
        j1, j2 = model.expand_range(index, i)
        editor.to_clipboard(model[j1:j2])
        editor.remove(j1, j2)
    elif action == 'del_word_left':
        i = index
        try:
            while not model.get_text(i-1, i).isalnum(): i -= 1
            while model.get_text(i-1, i).isalnum():     i -= 1
        except IndexError:
            i = 0
        i = max(i, model.start(index))
        j1, j2 = model.expand_range(i, index)
        editor.remove(j1, j2)
    else:
        return False # not handled
    return True



def text_handler(action, shift, ctx):
    """X-coordinate-based movement for wrapped (word-processor) text."""
    if action == 'move_up':
        editor.move_up(shift)
        return True
    elif action == 'move_down':
        editor.move_down(shift)
        return True
    return False


def code_handler(action, shift, ctx):
    """Row/column-based movement and space-indentation for code views.

    Overrides move_up/move_down (character-column based) and indent/dedent
    (leading-space insertion). All other actions fall through.
    """
    if action == 'move_up':
        editor.move_cursor_to(ctx.row - 1, ctx.col, shift)
        return True
    elif action == 'move_down':
        editor.move_cursor_to(ctx.row + 1, ctx.col, shift)
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
