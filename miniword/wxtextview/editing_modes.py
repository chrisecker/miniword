# -*- coding: utf-8 -*-
"""Action handlers for different editing contexts.

Handlers have the signature:
    handler(view, action, shift, ctx) -> bool

Return True to stop the pipeline, False to pass to the next handler.
`ctx` is the SimpleNamespace built by TextView._build_ctx().
"""

def text_handler(view, action, shift, ctx):
    """X-coordinate-based movement for wrapped (word-processor) text."""
    if action == 'move_up':
        view.move_up(shift)
        return True
    elif action == 'move_down':
        view.move_down(shift)
        return True
    return False


def code_handler(view, action, shift, ctx):
    """Row/column-based movement and space-indentation for code views.

    Overrides move_up/move_down (character-column based) and indent/dedent
    (leading-space insertion). All other actions fall through.
    """
    if action == 'move_up':
        asdsa
        view.move_cursor_to(ctx.row - 1, ctx.col, shift)
        return True
    elif action == 'move_down':
        view.move_cursor_to(ctx.row + 1, ctx.col, shift)
        return True
    elif action == 'indent':
        s1, s2 = ctx.s1, ctx.s2
        view.shift(s1, s2)
        return True
    elif action == 'dedent':
        s1, s2 = ctx.s1, ctx.s2
        view.unshift(s1, s2)
        return True
    return False
