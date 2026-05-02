# -*- coding: utf-8 -*-

from .testdevice import TESTDEVICE
from .boxes import TabulatorBox, TextBox, EmptyTextBox, NewlineBox, Row




def find_goodbreak(box, maxw):
    """Search good break position at or before maxw, returns None
       (i.e. no good split position possible) otherwise. If 
       box.width <= maxw then len(box) is returned.
    """    
    if (not isinstance(box, TextBox)) or maxw <= 0:
        # no good split is possible
        return None

    if box.width<=maxw:
        # split is not necessary
        return len(box)

    text = box.text
    if not text:
        return None

    measure = box.measure
    width = 0
    ws = measure(' ')[0]
    i = 0
    for word in text.split(' '):
        w = measure(word)[0]
        if width+w <= maxw:
            i += len(word)+1
            width += w+ws
            continue
        if i==0:
            return None
        return min(len(text), i)
    return None

    
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


def simple_linewrap(boxes, maxw, maxw2=None, wordwrap=True):
    """Break boxes into rows where each row does not exceed width
    maxw.

    if wordwrap is True (default), tries to break at spaces. Only if
    no spaces are found, breaking in words is considered. 
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

            if isinstance(box, TextBox) and ' ' in box.text:
                last_space = (len(line) - 1, box.text.rindex(' ') + 1)
            continue

        # Try to break box
        avail = maxw - w
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
