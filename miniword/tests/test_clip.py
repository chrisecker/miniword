# -*- coding: utf-8 -*-

"""
Tests for clipping: nothing is drawn outside the page or, in a table,
outside its cell (e.g. an image with a size wider than the text).
IDs CLIP-n.

Run with: python runtests.py miniword/tests/test_clip.py
"""

from ..layout.testdevice import TestDevice
from .test_rowfactory import doc, par, pages_from, small_memo


class ClipDevice(TestDevice):
    """Records clips and texts in order."""

    def __init__(self):
        self.calls = []

    def push_clip(self, x, y, w, h, dc):
        self.calls.append(('clip', x, y, w, h))

    def pop_clip(self, dc):
        self.calls.append(('pop',))

    def draw_text(self, text, x, y, dc):
        self.calls.append(('text', text))


def with_device(box, device):
    """box with device, also its rows' boxes."""
    box.device = device
    for _, _, row in getattr(box, 'rows', ()):
        for child in row.childs:
            child.device = device
    return box


def test_CLIP_1():
    "CLIP-1: a page's content is clipped to the page, on screen and print"
    page = pages_from(doc(par('ab')), small_memo(width=40, height=10))[0]
    for draw in (page.draw, page.draw_for_print):
        device = ClipDevice()
        with_device(page, device)
        draw(5, 7, None)
        calls = device.calls
        assert calls[0] == ('clip', 5, 7, page.width, page.height), draw
        assert ('text', 'ab') in calls
        assert calls.index(('pop',)) > calls.index(('text', 'ab'))


def test_CLIP_2():
    "CLIP-2: a table cell's content is clipped to the cell"
    from ..tables.table_boxes import create_cell
    device = ClipDevice()
    cell = create_cell([], 50, device, 8, 6)
    cell.draw(10, 20, None)
    assert device.calls[0] == ('clip', 10, 20, 50, cell.height
                               + cell.depth)
    assert device.calls[-1] == ('pop',)
