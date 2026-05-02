# -*- coding: utf-8 -*-
"""Action handlers for different editing contexts.

Handlers have the signature:
    handler(view, action, shift, ctx) -> bool

Return True to stop the pipeline, False to pass to the next handler.
`ctx` is the SimpleNamespace built by TextView._build_ctx().
"""


def text_handler(view, action, shift, ctx):
    """X-coordinate-based movement for wrapped (word-processor) text.

    Overrides move_up/move_down to track the visual x position across
    line breaks rather than the character column. All other actions fall
    through to the next handler.
    """
    if action == 'move_up':
        rect = ctx.layout.get_rect(ctx.index, 0, 0)
        i = ctx.layout.get_index(ctx.x, rect.y1 - 1)
        if i is not None:
            view.set_index(i, shift)
        return True
    elif action == 'move_down':
        rect = ctx.layout.get_rect(ctx.index, 0, 0)
        i = ctx.layout.get_index(ctx.x, rect.y2 + 1)
        if i is not None:
            view.set_index(i, shift)
        return True
    return False


def code_handler(view, action, shift, ctx):
    """Row/column-based movement and space-indentation for code views.

    Overrides move_up/move_down (character-column based) and indent/dedent
    (leading-space insertion). All other actions fall through.
    """
    if action == 'move_up':
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
