# -*- coding: utf-8 -*-

import re

from .testdevice import TESTDEVICE
from .boxes import TabulatorBox, TextBox, EmptyTextBox, NewlineBox, Row, \
    HyphenBox


# CJK line breaking - once lost in the move to layout/; kept by
# linewrap.test_02 and test_rowfactory WRAP-14..16
_KINSOKU_START = (
    '、。，．！？）」』】〕〉》…‥ー゛゜'   # punctuation that cannot start a line
    'ぁぃぅぇぉっゃゅょゎ'                  # small hiragana
    'ァィゥェォッャュョヮヵヶ'               # small katakana
)

# Break opportunities: after a space, after a hyphen between letters
# ([^\W\d_]: a letter), or after a CJK character unless a kinsoku-start
# character follows.
_BREAK_RE = re.compile(
    r'(?<= )'
    r'|(?<=[^\W\d_]-)(?=[^\W\d_])'
    r'|(?<=['
    '\u4e00-\u9fff'   # CJK Unified Ideographs
    '\u3040-\u30ff'   # Hiragana + Katakana
    '\uac00-\ud7af'   # Hangul
    '\u3400-\u4dbf'   # CJK Extension A
    r'])'
    r'(?![' + re.escape(_KINSOKU_START) + r'])'
)


def line_widths(box, maxw):
    """Widths of the box text's prefixes (see prefix_widths), at least
    up to the first character beyond maxw: shaped once per line, not
    once per word. The part shaped is estimated from the box's average
    character width and doubled if too short."""
    text = box.text
    n = int(maxw / max(box.width / len(text), 0.1) * 1.2) + 20
    while True:
        widths = box.device.prefix_widths(text[:n], box.style)
        if widths[-1] > maxw or n >= len(text):
            return widths
        n *= 2


def find_goodbreak(box, maxw):
    """Search good break position at or before maxw, returns None if no good
    split position is possible. If box.width <= maxw, len(box) is returned.

    Recognises both Latin word boundaries (spaces) and CJK character
    boundaries, including Japanese kinsoku rules.
    """
    if not isinstance(box, TextBox) or maxw <= 0:
        return None
    if box.width <= maxw:
        return len(box)
    text = box.text
    if not text:
        return None

    widths = line_widths(box, maxw)
    last_fit = None
    for m in _BREAK_RE.finditer(text):
        pos = m.start()
        # a space before the break hangs over the edge: not measured
        check_pos = pos - 1 if pos > 0 and text[pos - 1] == ' ' else pos
        if check_pos < len(widths) and widths[check_pos] <= maxw:
            last_fit = pos
        else:
            break   # widths are monotonically non-decreasing
    return last_fit

    
PUNCTUATION = '.,;:!?"\'()[]«»„“”‘’'  # stripped before hyphenating
NBHYPHEN, SOFTHYPHEN = '\u2011', '\u00ad'


def find_hyphen_break(box, maxw, hyphenate, continues=False):
    """Where to hyphenate the word reaching over maxw (part plus hyphen
    fit), or None. hyphenate: word -> pieces; in words with soft hyphens
    only these count. Breaks after the word's own hyphens, but not after
    protected ones (U+2011). continues: the box starts within a word,
    which is then not hyphenated."""
    if not isinstance(box, TextBox) or maxw <= 0:
        return None
    text, measure = box.text, box.measure
    widths = line_widths(box, maxw)

    def width(i):  # beyond the widths: too wide anyway
        return widths[i] if i < len(widths) else maxw + 1
    start = 0
    for word in text.split(' '):
        end = start + len(word)
        if width(end) > maxw:
            break
        start = end + 1
    else:
        return None
    if start == 0 and continues:
        return None
    core = word.strip(PUNCTUATION)
    if not core:
        return None
    pos = start + word.index(core)
    hyphen = measure('-')[0]
    soft = SOFTHYPHEN in core
    best = None
    tokens = re.split('([-%s])' % NBHYPHEN, core)  # Hals, -, Nasen, ...
    for k, token in enumerate(tokens):
        if token == '-':
            pos += 1
            if tokens[k + 1] and width(pos) <= maxw:
                best = pos  # after the word's own hyphen
            continue
        if token == NBHYPHEN:
            pos += 1
            continue
        if soft:
            breaks = [i + 1 for i, c in enumerate(token) if c == SOFTHYPHEN]
        else:
            breaks, n = [], 0
            for piece in hyphenate(token)[:-1]:
                n += len(piece)
                breaks.append(n)
        for n in breaks:
            if width(pos + n) + hyphen <= maxw:
                best = pos + n
        pos += len(token)
    return best


def find_anybreak(box, maxw):
    """Search possible break position at or before maxw, returns None
       otherwise."""
    if not isinstance(box, TextBox) or maxw <= 0:
        return None # not breakable

    parts = box.measure_parts(box.text)
    for i, part in enumerate(parts):
        if part > maxw:
            return max(i, 1)  # Minimum 1 char
    return len(parts)


def split_box(box, i):
    if not isinstance(box, TextBox):
        assert i == 0
        return EmptyTextBox(), box

    text, style, device = box.text, box.style, box.device
    return (
        box.__class__(text[:i], style, device),
        box.__class__(text[i:], style, device),
    )


def simple_linewrap(boxes, maxw, maxw2=None, wordwrap=True,
                    hyphenate=None):
    """Break boxes into rows where each row does not exceed width
    maxw.

    if wordwrap is True (default), tries to break at spaces. Only if
    no spaces are found, breaking in words is considered. With
    hyphenate (word -> pieces), a word reaching over the edge is
    hyphenated first, before it is moved to the next row.
    """
    if maxw2 is None:
        maxw2 = maxw
    rows, line = [], []
    w = 0
    boxes = list(boxes)

    last_space = None  # (index_in_line, char_index)

    while boxes:
        box = boxes.pop(0)
        if not box or not len(box):
            continue

        # Does box fit completely?
        if w + box.width <= maxw:
            line.append(box)
            w += box.width

            if isinstance(box, TextBox):
                matches = list(_BREAK_RE.finditer(box.text))
                if matches:
                    last_space = (len(line) - 1, matches[-1].start())
            continue

        # Try to break box
        avail = maxw - w
        if hyphenate is not None or (isinstance(box, TextBox)
                                     and SOFTHYPHEN in box.text):
            continues = bool(line) and isinstance(line[-1], TextBox) \
                and not line[-1].text.endswith(' ')
            i = find_hyphen_break(box, avail, hyphenate or (lambda w: [w]),
                                  continues)
            if i:
                a, b = split_box(box, i)
                hyphen = [] if a.text.endswith('-') else \
                    [HyphenBox(box.style, box.device)]  # not a second one
                rows.append(line + [a] + hyphen)
                boxes = [b] + boxes
                maxw = maxw2
                line, w, last_space = [], 0, None
                continue
        i = None
        if wordwrap:
            i = find_goodbreak(box, avail)
            if i is None and last_space:
                k, j = last_space
                a, b = split_box(line[k], j)

                boxes = [b] + line[k + 1:] + [box] + boxes
                line = line[:k] + [a]
                rows.append(line)
                maxw = maxw2
                line, w, last_space = [], 0, None
                continue
            
        if i is None:
            i = find_anybreak(box, avail)
        if i is not None and i>0:
            # break box
            a, b = split_box(box, i)
            if i > 0:
                line.append(a)
            boxes = [b] + boxes if b else boxes
        else:
            # box is unbreakable! Note that box is the first box which
            # does not fit in and before it was ok. So we have two
            # possible solutions: either break before box or break
            # after box.
            if w<=0:
                # line is empty -> put box in this line
                line.append(box)
            else:
                # Line is not empty -> put box in next line
                boxes = [box]+boxes
        rows.append(line)
        line, w, last_space = [], 0, None
        maxw = maxw2

    if line:
        rows.append(line)
    return rows



def test_00():
    "find_break"    
    box = TextBox("123 567 90")
    assert find_goodbreak(box, 0) == None # not possible
    assert find_goodbreak(box, 1) == None # not possible
    assert find_goodbreak(box, 2) == None # not possible
    assert find_goodbreak(box, 3) == 4 # note that the space is not counted!
    assert find_goodbreak(box, 4) == 4
    assert find_goodbreak(box, 5) == 4
    assert find_goodbreak(box, 6) == 4
    assert find_goodbreak(box, 7) == 8
    assert find_goodbreak(box, 8) == 8
    assert find_goodbreak(box, 9) == 8
    assert find_goodbreak(box, 10) == 10 # no split necessary
    assert find_goodbreak(box, 11) == 10 # no split necessary


def test_02():
    "CJK line breaking with kinsoku rules"
    # Break after every CJK character
    box = TextBox("中文日本語")
    assert find_goodbreak(box, 0) is None
    assert find_goodbreak(box, 1) == 1
    assert find_goodbreak(box, 4) == 4
    assert find_goodbreak(box, 5) == 5   # fits

    # Kinsoku: no break before '。' (line-start prohibited)
    # "日本。語": a break after '日' (pos 1), not before '。' (pos 2)
    box = TextBox("日本。語")
    assert find_goodbreak(box, 2) == 1   # pos 2 blocked by kinsoku


def test_01():
    "simple_linewrap"

    # maxw and maxw2
    boxes = []
    for text in "aa bb cc dd ee".split():
        boxes.append(TextBox(text))
    assert str(simple_linewrap(boxes, 5, 3)) == \
        "[[TB('aa'), TB('bb'), TB('c')], [TB('c'), TB('dd')], " \
        "[TB('ee')]]"
    
    # wrapping at NL
    boxes = []
    for text in "aa bb cc dd ee".split():
        boxes.append(TextBox(text))
        if text == 'dd':
            boxes.append(NewlineBox())
    assert str(simple_linewrap(boxes, 5)) == \
        "[[TB('aa'), TB('bb'), TB('c')], [TB('c'), TB('dd'), NL, "\
        "TB('ee')]]"
    
    # word wrapping
    boxes = []
    for text in "ff gg_hh ii jj".split('_'):
        boxes.append(TextBox(text))

    assert str(simple_linewrap(boxes, 1)) == \
        "[[TB('f')], [TB('f ')], [TB('g')], [TB('g')], " \
        "[TB('h')], [TB('h ')], [TB('i')], [TB('i ')], " \
        "[TB('j')], [TB('j')]]"
    assert str(simple_linewrap(boxes, 4)) == \
        "[[TB('ff ')], [TB('gg'), TB('hh ')], [TB('ii ')], [TB('jj')]]"
    assert str(simple_linewrap(boxes, 2)) == \
        "[[TB('ff ')], [TB('gg')], [TB('hh ')], [TB('ii ')], " \
        "[TB('jj')]]" # emergency break between gg and hh
    assert str(simple_linewrap(boxes, 3)) == \
        "[[TB('ff ')], [TB('gg'), TB('h')], [TB('h ')], " \
        "[TB('ii ')], [TB('jj')]]" # emergency break between h and h
    assert str(simple_linewrap(boxes, 5)) == \
        "[[TB('ff ')], [TB('gg'), TB('hh ')], [TB('ii jj')]]"
    assert str(simple_linewrap(boxes, 7)) == \
        "[[TB('ff gg'), TB('hh ')], [TB('ii jj')]]"
    assert str(simple_linewrap(boxes, 8)) == \
        "[[TB('ff gg'), TB('hh ')], [TB('ii jj')]]"
    assert str(simple_linewrap(boxes, 9)) == \
        "[[TB('ff gg'), TB('hh ')], [TB('ii jj')]]"
    assert str(simple_linewrap(boxes, 10)) == \
        "[[TB('ff gg'), TB('hh ii ')], [TB('jj')]]"
    assert str(simple_linewrap(boxes, 11)) == \
        "[[TB('ff gg'), TB('hh ii ')], [TB('jj')]]"
    assert str(simple_linewrap(boxes, 12)) == \
        "[[TB('ff gg'), TB('hh ii ')], [TB('jj')]]"
    assert str(simple_linewrap(boxes, 13)) == \
        "[[TB('ff gg'), TB('hh ii jj')]]"
    
    # hard wrapping
    assert str(simple_linewrap(boxes, 5, wordwrap=False)) == \
        "[[TB('ff gg')], [TB('hh ii')], [TB(' jj')]]"
    assert str(simple_linewrap(boxes, 6, wordwrap=False)) == \
        "[[TB('ff gg'), TB('h')], [TB('h ii j')], [TB('j')]]"

    


def profile_00():
    "breaking a long string"
    import wx
    from .wxdevice import WxDevice
    app = wx.App(redirect=False)
    frame = wx.Frame(None)
    
    device = WxDevice()
    s = "123456789 " * 100
    boxes = [TextBox(s, device=device)]
    simple_linewrap(boxes, 100, tabstops=(), wordwrap=True)    
