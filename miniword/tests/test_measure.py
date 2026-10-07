# -*- coding: utf-8 -*-

"""
Tests for measuring once per line instead of once per word: devices
give the widths of all prefixes of a text (prefix_widths), the line
wrapping looks them up. IDs MEAS-n.

Run with: python runtests.py miniword/tests/test_measure.py
"""

import wx

from ..hyphenation import get_hyphenator
from ..layout.boxes import TextBox
from ..layout.cairodevice import CairoDevice
from ..layout.linewrap import simple_linewrap
from ..layout.testdevice import TestDevice
from .guitest import app

STYLE = dict(font_family='Times New Roman', font_size=12)


class PrefixByPrefix(CairoDevice):
    """The old way, as reference: every prefix shaped on its own."""
    prefix_widths = TestDevice.prefix_widths


def paragraphs(n=60):
    """The first n longer paragraphs of moby.txl."""
    from ..core.document import Document
    text = Document.load('test/moby.txl').textmodel.get_text()
    return [p for p in text.split('\n') if len(p) > 200][:n]


def rows(text, device, width, hyphenate=None):
    return [''.join(box.text for box in row if isinstance(box, TextBox))
            for row in simple_linewrap([TextBox(text, STYLE, device)],
                                       width, hyphenate=hyphenate)]


def test_MEAS_1():
    "MEAS-1: prefix widths are the widths of the prefixes measured alone"
    app()
    device = CairoDevice()
    for text in ('Hello world', 'Silben­trennung', 'office fly',
                 'a中文b', 'x'):
        widths = device.prefix_widths(text, STYLE)
        assert len(widths) == len(text) + 1 and widths[0] == 0
        for i in range(len(text) + 1):
            alone = device.measure(text[:i], STYLE)[0]
            assert abs(widths[i] - alone) < 0.5, (text, i, widths[i], alone)


def test_MEAS_2():
    "MEAS-2: moby.txl wraps into the same lines as measuring by prefix"
    app()
    fast, reference = CairoDevice(), PrefixByPrefix()
    for text in paragraphs():
        for width in (300, 450):
            assert rows(text, fast, width) == \
                rows(text, reference, width), (width, text[:40])


def test_MEAS_3():
    "MEAS-3: the same with hyphenation"
    app()
    fast, reference = CairoDevice(), PrefixByPrefix()
    hyphenate = get_hyphenator('en-us').hyphenate
    for text in paragraphs(30):
        assert rows(text, fast, 300, hyphenate) == \
            rows(text, reference, 300, hyphenate), text[:40]


def test_MEAS_4():
    "MEAS-4: a long paragraph is shaped a few times per line, not per word"
    app()

    class Counting(CairoDevice):
        shapes = 0

        def _shape(self, text, hb_font):
            self.shapes += 1
            return CairoDevice._shape(self, text, hb_font)

    device = Counting()
    text = max(paragraphs(), key=len)
    lines = len(rows(text, device, 300))
    device.clear_caches()
    device.shapes = 0
    rows(text, device, 300)
    assert device.shapes <= 4 * lines, (device.shapes, lines)
