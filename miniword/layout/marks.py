# -*- coding: utf-8 -*-

"""Formatting marks (View > Formatting marks): drawn on screen on top of
the layout, like annotation.squiggle - never part of the layout, so they
don't move the text, and never printed (print and PDF use
Page.draw_for_print)."""

from .boxes import _TextBoxBase, NewlineBox, TabulatorBox
from .page import ForceBreakBox
from .stretchable import StretchableText

# marks for characters within the text
MARKS = {'\u00a0': '°',   # protected space
         '\u2011': '_',   # protected hyphen: underlined
         '\u00ad': '¬'}   # soft hyphen (no width)

COLOR = '#909090'


def iter_marks(dc, box, x, y):
    """(x, y, mark, leaf box) for every formatting mark in box at x, y:
    paragraph ends, line breaks, tabs and the characters in MARKS."""
    for j1, j2, x1, y1, child in box.iter_boxes(0, x, y):
        if not child.visible(x1, y1, dc):
            continue
        if isinstance(child, ForceBreakBox):
            yield x1, y1, '↵', child
        elif isinstance(child, NewlineBox):
            yield x1, y1, '¶', child
        elif isinstance(child, TabulatorBox):
            yield x1, y1, '→', child
        elif isinstance(child, _TextBoxBase):
            for k, c in enumerate(child.text):
                if c in MARKS:
                    dx = child.measure(child.text[:k])[0]
                    yield x1 + dx, y1, MARKS[c], child
        elif isinstance(child, StretchableText):
            text = ''.join(string for string, _ in child.items)
            for k, c in enumerate(text):
                if c in MARKS:
                    yield x1 + child.find_x(k), y1, MARKS[c], child
        else:
            yield from iter_marks(dc, child, x1, y1)


def draw_marks(dc, boxes):
    """Draw the marks of boxes ((j1, j2, x, y, box) as from
    layout.iter_boxes(flow)) in grey."""
    for j1, j2, x, y, box in boxes:
        for mx, my, mark, leaf in iter_marks(dc, box, x, y):
            device = leaf.device
            if mark == '¬':  # a thin bar between two letters: no width
                h = leaf.height
                device.fill_rect(mx - 0.3, my + 0.3 * h, 0.6, 0.6 * h,
                                 COLOR, dc)
                continue
            style = dict(getattr(leaf, 'style', {}), color=COLOR,
                         bgcolor='white', underline=False)
            if mark == '→':  # centered in the tab, smaller if too wide
                w = device.measure(mark, style)[0]
                if w > leaf.width > 0:
                    style['font_size'] = style.get('font_size', 12) \
                        * leaf.width / w
                    w = leaf.width
                mx += (leaf.width - w) / 2
            device.set_style(style, dc)
            device.draw_text(mark, mx, my, dc)
