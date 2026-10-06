# -*- coding: utf-8 -*-

"""
Tests for formatting marks (layout/marks.py): drawn on screen only,
never in print or PDF, and they never move the text. IDs MK-n.

Run with: python runtests.py miniword/tests/test_marks.py
"""

from ..core.texels import BR
from ..textmodel.texeltree import Tabulator
from ..layout.marks import iter_marks, MARKS
from ..layout.testdevice import TestDevice
from .test_rowfactory import doc, par, pages_from, small_memo, row_text


def page_marks(texel):
    page = pages_from(texel, small_memo(width=40, height=10))[0]
    return page, [(mark, x, y) for x, y, mark, box
                  in iter_marks(None, page, 0, 0)]


def test_MK_1():
    "MK-1: paragraph ends, line breaks and tabs are marked at their place"
    page, marks = page_marks(doc(par('ab', BR(), 'c', Tabulator(), 'd'),
                                 par('e')))
    (_, y1, row1), (_, y2, row2), (_, y3, row3) = page.rows
    left = page.rows[0][0]
    assert ('↵', left + 2, y1) in marks       # after 'ab'
    assert ('¶', left + row2.width, y2) in marks
    assert ('¶', left + 1, y3) in marks       # after 'e'
    tab = [(x, y) for mark, x, y in marks if mark == '→']
    assert tab == [(left + 1, y2)]           # after 'c'


def test_MK_2():
    "MK-2: protected space, protected hyphen and soft hyphen are marked"
    page, marks = page_marks(doc(par('a\u00a0b\u2011c\u00add')))
    left, y = page.rows[0][:2]
    assert (MARKS['\u00a0'], left + 1, y) in marks
    assert (MARKS['\u2011'], left + 3, y) in marks
    assert (MARKS['\u00ad'], left + 5, y) in marks  # soft hyphen: no width


def test_MK_3():
    "MK-3: the marks never move the text - they aren't in the layout"
    texel = doc(par('a\u00a0b\u2011c\u00add', Tabulator(), 'x'), par('e'))
    memo = small_memo(width=40, height=10)
    before = [(x, y, row_text(row)) for x, y, row
              in pages_from(texel, memo)[0].rows]
    page, marks = page_marks(texel)
    assert marks
    assert [(x, y, row_text(row)) for x, y, row in page.rows] == before


class RecordingDevice(TestDevice):
    def __init__(self):
        self.texts = []

    def draw_text(self, text, x, y, dc):
        self.texts.append(text)


def test_MK_4():
    "MK-4: print and PDF (draw_for_print) draw no marks"
    page, marks = page_marks(doc(par('a\u00a0b', BR(), 'c\u00add'),
                                 par('e', Tabulator(), 'f')))
    assert marks
    device = RecordingDevice()
    page.device = device
    for _, _, row in page.rows:
        for box in row.childs:
            box.device = device
    page.draw_for_print(0, 0, None)
    drawn = ''.join(device.texts)
    assert not any(mark in drawn for mark in '¶↵→°¬')
