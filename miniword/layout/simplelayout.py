# -*- coding: utf-8 -*-

# Simple layout for text editors
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# The layout can be characterized by three different layers of boxes:

# paragraphs, lines and boxes. The top layer is the paragraph
# layer. It consists of a tree formed by ParagraphStacks and
# Paragraphs. Each paragraph has a tree of lines. Each line has a list
# of boxes.
#
# All paragraphs are stacked on top of each other. Each line has
# exactly the same width.
#
# When the model changes, we identify the corresponding paragraph
# objects, rebuild them and replace them.

from . import boxes
from .boxes import Box, HBox, VBox, VGroup, TextBox, EmptyTextBox, NewlineBox, \
                   EndBox, check_box, Box, tree_depth, Row, calc_length
from ..textmodel.texeltree import NewLine, length

from .testdevice import TESTDEVICE
from .linewrap import simple_linewrap
from .rect import Rect
from .builderbase import BuilderBase
from .builderbase import Factory as _Factory



class Paragraph(VBox):
    # A paragraph consists of one or several rows, which are stacked
    # on top of each other. It is assumed, that the text consists of
    # one single page with a constant left margin and uniform row
    # width. These assumptions correspond to the typical behaviour in
    # a text editor. If there are different requirements, e.g. in a
    # word processor, Paragraph could be redefined.
    #
    # The number of paragraphs can be very long. Therefore we group
    # paragraph into VGroups. This makes the GUI considerably faster.

    def create_group(self, l):
        return VGroup(l, device=self.device)

    

class SimpleLayout(VBox):
    def get_flow(self, x, y):
        return 0

    def prev_row(self, i, flow):
        return boxes.prev_row(self, i)
    
    def next_row(self, i, flow):
        return boxes.next_row(self, i)

    ### add flow-argument to box methods (needed by textview)
    def get_index(self, x, y, flow=0):
        return VBox.get_index(self, x, y)

    def get_rect(self, i, x0, y0, flow=0):
        return VBox.get_rect(self, i, x0, y0)

    def draw_cursor(self, i, x0, y0, dc, style, flow=0):
        return VBox.draw_cursor(self, i, x0, y0, dc, style)

    def draw_selection(self, i1, i2, x, y, dc, flow=0):
        return VBox.draw_selection(self, i1, i2, x, y, dc)

    def find_paragraph(self, i):
        """
        Helper: computes child number and start index of the paragraph
        containing i.
        """ 
        k = -1
        i2 = 0 # needed when empty!
        for i1, i2, child in self.iter_childs():
            k += 1
            if i1<=i<i2:
                return i1, i2, k, k+1
        return i2, i2, k+1, k+1
        
    def replace_paragraphs(self, k1, k2, stuff):
        childs = self.childs
        new = childs[:k1]+stuff+childs[k2:]
        return SimpleLayout(new)
        


def create_paragraphs(textboxes, maxw=0, wordwrap=True, Paragraph=Paragraph, \
                      device=TESTDEVICE):
    try:
        if len(textboxes):        
            assert isinstance(textboxes[-1], NewlineBox) or \
                isinstance(textboxes[-1], EndBox)
    except:
        i1 = 0
        for box in textboxes:
            i2 = i1+len(box)
            print(i1, i2, repr(box)[:50])
            i1 = i2
        raise
    r = []
    l = []
    for box in textboxes:
        assert isinstance(box, Box)
        l.append(box)
        if isinstance(box, NewlineBox) or isinstance(box, EndBox):
            if maxw>0:
                lines = simple_linewrap(l, maxw, wordwrap=wordwrap)
            else:
                lines = [l]
            rows = []
            for line in lines:
                row = Row(line, device)                
                rows.append(row)
                
            r.append(Paragraph(rows, device))
            l = []
    #print l
    assert not l # There is always one final box which is either a
                 # NewLine or an EndBox. Therefore there is no rest in
                 # l.

    assert calc_length(r) == calc_length(textboxes)
    while len(r)>boxes.nmax:
        r = groups(r)
    return r



class Factory(_Factory):
    def create_paragraphs(self, texel, i1, i2):
        # creates a list of paragraphs
        textboxes = self.create_boxes(texel, i1, i2)
        assert len(textboxes)
        assert isinstance(textboxes[-1], EndBox) or isinstance(textboxes[-1], \
                                                               NewlineBox)
        return create_paragraphs(
            textboxes, self._maxw, 
            Paragraph = self.Paragraph,
            device = self.device,
        )



class SimpleBuilder(BuilderBase, Factory):
    Paragraph = Paragraph

    def __init__(self, model, device=TESTDEVICE, maxw=0):
        BuilderBase.__init__(self, model)
        assert self.model == model
        assert self in model.views
        self._maxw = maxw
        Factory.__init__(self, device)

    def extended_texel(self):
        return self.model.get_xtexel()
        
    def set_maxw(self, maxw):
        if maxw != self._maxw:
            self._maxw = maxw
            self.rebuild()
        
    ### Builder-Protocol
    def rebuild(self):
        texel = self.extended_texel()
        l = self.create_paragraphs(texel, 0, length(texel))
        self._layout = SimpleLayout(l, device=self.device)

    def rebuild_range(self, i1, i2, delta):
        """XXX" Achtung: der Bereich i1,i2 ist bisher inkonsistent"""
        i2 -= delta # XXX bisher wird remove mit i1=i2 aufgerufen. Das
                    # sollte geändert werden auf i1..i2 betroffener Bereich in den
                    # alten Koordinaten.
        layout = self._layout
        j1, _, k1, _ = layout.find_paragraph(i1)
        _, j2, _, k2 = layout.find_paragraph(max(i1+1, i2))
        j2 += delta
        texel = self.extended_texel()
        new = self.create_paragraphs(texel, j1, j2)
        self._layout = layout.replace_paragraphs(k1, k2, new)




def test_00():
    "Paragraph"
    from ..textmodel import TextModel
    box1 = TextBox("0123")
    box2 = TextBox("5678")
    texel = TextModel("0123\n5678\n").texel
    box = Paragraph([
        Row([box1, NewlineBox()]), 
        Row([box2, NewlineBox()]),
        Row([EmptyTextBox()])
    ])
    assert check_box(box, texel)
    #box.dump_boxes(0, 0, 0)
    assert (box.height, box.width, box.depth) == (3, 4, 0)

    assert str(box.get_info(0, 0, 0)) == "(TB('0123'), 0, 0, 0)"
    assert str(box.get_info(1, 0, 0)) == "(TB('0123'), 1, 1, 0)"
    assert str(box.get_info(2, 0, 0)) == "(TB('0123'), 2, 2, 0)"
    assert str(box.get_info(3, 0, 0)) == "(TB('0123'), 3, 3, 0)"
    assert str(box.get_info(4, 0, 0)) == "(NL, 0, 4, 0)"
    assert str(box.get_info(5, 0, 0)) == "(TB('5678'), 0, 0, 1)"
    assert str(box.get_info(6, 0, 0)) == "(TB('5678'), 1, 1, 1)"
    assert str(box.get_info(7, 0, 0)) == "(TB('5678'), 2, 2, 1)"
    assert str(box.get_info(8, 0, 0)) == "(TB('5678'), 3, 3, 1)"
    assert str(box.get_info(9, 0, 0)) == "(NL, 0, 4, 1)"
    assert str(box.get_info(10, 0, 0)) == "(ETB, 0, 0, 2)"


def _mk_pars(text):
    # for testing
    from .cairodevice import defaultstyle
    l = []
    for line in text.split('\n'):
        for word in line.split():
            l.append(TextBox(word))
        l.append(NewlineBox(defaultstyle))
    return create_paragraphs(l)

def test_01():
    "creating paragraphs"
    l = _mk_pars("word1 word2 word3")
    assert str(l) == "[Paragraph[Row[TB('word1'), TB('word2'), TB('word3'), NL]]]"
    l = _mk_pars("word1\nword2\nword3")
    assert str(l) == "[Paragraph[Row[TB('word1'), NL]], Paragraph[Row[TB('word2')," \
                     " NL]], Paragraph[Row[TB('word3'), NL]]]"

def test_02():
    "layout.find_paragraph"
    l = _mk_pars("word1 word2 word3")
    layout = SimpleLayout(l)
    n = len(layout)
    assert layout.find_paragraph(0) == (0, 16, 0, 1)
    assert layout.find_paragraph(n) == (16, 16, 1, 1)

def test_03():
    "Paragraph dimensions"
    t1 = TextBox("0123456789")
    t2 = TextBox("0123456789")
    p1 = Paragraph([Row([t1, NewlineBox()])])
    row = p1.childs[0]
    assert p1.height == 1
    assert p1.width == 10
    assert len(p1) == 11
    p2 = VBox([Row([t2])])
    assert p2.height == 1
    s = VBox([p1, p2])
    assert s.height == 2    

def test_04():
    "Paragraph tree structure"
    t1 = TextBox("0123456789")
    t2 = TextBox("0123456789")
    NL = NewlineBox()
    p1 = Paragraph([Row([t1, NL])])
    assert tree_depth(p1) == 0

    p2 = Paragraph([Row([t2, NL])])
    assert tree_depth(p2) == 0
    
def test_05():
    "Paragraph.get_rect"
    t1 = TextBox("0123456789")
    t2 = TextBox("0123456789")
    p = Paragraph([Row([t1, t2, NewlineBox()])])
    assert p.get_rect(0, 0, 0) == Rect(0, 0.0, 1, 1.0)
    assert p.get_rect(10, 0, 0) == Rect(10, 0.0, 11, 1.0)

def test_06():
    "insert"
    from ..textmodel import TextModel
    model = TextModel("Line 1\nLine 2")
    builder = SimpleBuilder(model, maxw=10)
    builder.rebuild()
    model.insert_text(1, 'XX')
    s = str(builder.layout)
    assert  s == "SimpleLayout[Paragraph[Row[TB('LXXine 1'), NL]], Paragraph[" \
                 "Row[TB('Line 2'), ENDBOX]]]"

def test_07():
    "remove"
    from ..textmodel import TextModel
    model = TextModel("Line 1\nLine 2")
    builder = SimpleBuilder(model, maxw=10)
    builder.rebuild()
    model.remove(1, 3)
    s = str(builder.layout)
    assert  s == "SimpleLayout[Paragraph[Row[TB('Le 1'), NL]], Paragraph[" \
                 "Row[TB('Line 2'), ENDBOX]]]"



