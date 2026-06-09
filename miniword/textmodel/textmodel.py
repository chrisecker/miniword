# -*- coding: utf-8 -*-


from .texeltree import (
    Text, Group, NewLine, Tabulator, insert, takeout, ENDMARK, provides_childs,
    grouped, length, iter_childs, strip2list, EMPTYSTYLE, dump)

from .styles import (
    updated_style, create_style, get_styles, set_styles, get_style,
    set_properties, get_parstyles, set_parstyles, set_parproperties,
    clear_properties, clear_parproperties, StyleIterator)

from .utils import (
    find_weight, get_weight, next_newline, prev_newline, 
    get_localroot, NotFound, get_newlines, transform_range)

from .modelbase import Model
from .properties import overridable_property
import re




def get_texel(texel, i):
    if provides_childs(texel):
        for i1, i2, child in iter_childs(texel):
            if i1 <= i < i2:
                return get_texel(child, i-i1)
    else:
        if i != 0:
            raise IndexError(i)
    return texel

def get_text(texel, i1, i2):
    r = []
    if provides_childs(texel):
        for j1, j2, child in iter_childs(texel):
            if i1 < j2 and j1 < i2: # intersection
                r.append(get_text(child, i1-j1, i2-j1))
        return u''.join(r)
    text = texel.text
    return text[max(0, i1):min(i2, len(text))]


def dump_range(texel, i1, i2, i0=0, indent=0):
    s = texel.__class__.__name__
    if texel.is_text:
        s += " "+repr(texel.text)
    print(" "*indent+"%i:%i %s" % (i0, i0+length(texel), s))
    if provides_childs(texel):
        skip = False
        for j1, j2, child in iter_childs(texel):
            if i1 < j2 and j1 < i2: # intersection
                dump_range(child, i1-j1, i2-j1, i0+j1, indent+4)
                skip = False
            elif not skip:
                print(" "*indent+'...')
                skip = True # skip output of more '...'


_split = re.compile(r"([\t\n])", re.MULTILINE).split


def expand_range(texel, s1, s2, offset=0):
    if not (texel.is_group or texel.is_container):
        return s1, s2
    for i, (j1, j2, child) in enumerate(iter_childs(texel)):
        abs_j1 = offset + j1
        abs_j2 = offset + j2
        if not (abs_j1 < s2 and abs_j2 > s1):
            continue
        if texel.is_container and i % 2 == 0:  # separator touched
            s1 = min(s1, offset)
            s2 = max(s2, offset + length(texel))
            return s1, s2
        s1, s2 = expand_range(child, s1, s2, abs_j1)
    return s1, s2


class TextModel(Model):
    """A data type for storing and manipulating styled text. Changes to
    the data are notified to views by emitting the following signals:
    - "inserted" (arguments: i, length)
    - "removed" (arguments: i, removed data)
    - "properties changed" (arguments: i1, i2)

    """
    defaultstyle = create_style()
    texel = overridable_property('texel', "Root texel of this model")
    xtexel = overridable_property('xtexel', "Extended root (texel+endmark)")


    def create_textmodel(self, text=u'', **properties):
        """Creates a new textmodel with text $text$ and uniform style."""
        return self.__class__(text, **properties)

    def __init__(self, text='', **properties):
        assert type(text) == str
        style = updated_style(self.defaultstyle, properties)
        self.ENDMARK = ENDMARK.set_style(style)
        l = []
        text = text.replace('\r', '')
        for part in _split(text):
            if part == '\n':
                l.append(NewLine(style))
            elif part == '\t':
                l.append(Tabulator(style))
            elif len(part):
                l.append(Text(part, style))
        self._texel = grouped(l)

    def get_texel(self):
        return self._texel

    def set_texel(self, value):
        self._texel = value

    def __len__(self):
        return length(self.texel)

    def __getstate__(self):
        state = self.__dict__.copy()
        return state

    def __setstate__(self, state):
        if state is not None:
            self.__dict__ = state

    def get_xtexel(self):
        """Returns the texel tree extended by an ENDMARK glyph."""
        texel = self.texel
        return Group([texel, self.ENDMARK])

    def set_xtexel(self, xtexel):
        """Sets self.texel and self.ENDMARK from xtexel."""
        n = length(xtexel)-1
        assert n>=0 # xtexel must contain ENDMARK, therefore
                    # len(xtexel)>0
        t, e = takeout(xtexel, n, n+1)
        self.ENDMARK = grouped(e)
        self.texel = grouped(t)

    def nlines(self):
        """Returns the number of lines."""
        return self.texel.weights[2]+1

    def get_text(self, i1=None, i2=None):
        """Returns the text between *i1* and *i2* as unicode string."""
        if i1 is None:
            i1 = 0
        if i2 is None:
            i2 = length(self.texel)
        if i1<0:
            raise IndexError(i1)
        if i2>len(self):
            raise IndexError(i2)
        return get_text(self.texel, i1, i2)

    def get_style(self, i):
        """Returns the style at index *i*."""
        return get_style(self.get_xtexel(), i)

    def next_newline(self, i):
        """Return position of first NewLine at or after *i*, or length if none.
        """
        return next_newline(self.get_xtexel(), i)

    def prev_newline(self, i):
        """Return position of last NewLine strictly before *i*, or -1 if none.
        """
        return prev_newline(self.get_xtexel(), i)

    def get_start(self, i):
        """Return start of the local region: 0, or cell start if i is inside a
        container.
        """
        _, offset = get_localroot(self.texel, i)
        return offset

    def get_end(self, i):
        """Return end of the local region: length of model, or closing
        separator of the container cell.
        """
        root, offset = get_localroot(self.texel, i)
        return offset + length(root)

    def get_parstyle(self, i):
        xtexel = self.get_xtexel()
        j = next_newline(xtexel, i)
        return get_texel(xtexel, j).parstyle

    def expand_range(self, s1, s2):
        """Expand (s1, s2) so no container is only partially selected.

        If any separator of a container falls within [s1, s2], the selection
        is expanded to cover the complete container. Works recursively for
        nested containers.
        """
        return expand_range(self.texel, s1, s2)

    def position2index(self, row, col, i0=0):
        """Returns the index for (row, col) within the flow starting at i0."""
        if i0 > 0:
            root, _ = get_localroot(self.texel, i0)
        else:
            root = self.texel
        try:
            start = i0 + find_weight(root, row, 2)
        except NotFound:
            raise IndexError("row not found: %s" % row)
        maxcol = self.linelength(start)-1
        return start+max(0, min(maxcol, col))

    def index2position(self, i):
        """Returns (row, col, i0) for index *i*, where i0 is the flow start."""
        root, i0 = get_localroot(self.texel, i)
        local_i = i - i0
        row = get_weight(root, 2, local_i)
        col = local_i - find_weight(root, row, 2)
        return row, col, i0

    def linestart(self, i):
        """Returns the index where the line containing *i* starts."""
        return self.prev_newline(i) + 1

    def lineend(self, i):
        """Returns the NewLine position at the end of the line containing *i*,
        or length of model if on the last line.
        """
        return self.next_newline(i)

    def linelength(self, i):
        """Returns the length of the line containing *i*, including the NL if
        present.
        """
        end = self.lineend(i)
        start = self.linestart(i)
        if end < len(self):
            return end - start + 1
        return end - start

    def clear_styles(self, i1, i2):
        """Empties all the style-Attributes between *i1* and *i2*.""" 
        return self.set_styles(i1, [(i2-i1, EMPTYSTYLE)])

    def set_properties(self, i1, i2, **properties):
        """Sets the text properties between *i1* and *i2*."""
        if not (-1 <= i1 <= i2 <= len(self)):
            raise IndexError((i1, i2))
        memo = get_styles(self.texel, i1, i2)
        self.texel = grouped(
            set_properties(self.texel, i1, i2, properties))
        self.notify_views('properties_changed', i1, i2)
        return memo

    def clear_properties(self, i1, i2, *keys):
        """Unsets the text properties keys between *i1* and *i2*."""
        if not (-1 <= i1 <= i2 <= len(self)):
            raise IndexError((i1, i2))
        memo = get_styles(self.texel, i1, i2)
        self.texel = grouped(
            clear_properties(self.texel, i1, i2, keys))
        self.notify_views('properties_changed', i1, i2)
        return memo    

    def set_styles(self, i, styles):
        """Sets the styling of a span of text. Usually used by undo."""
        if not (0 <= i <= len(self)):
            raise IndexError(i)        
        n = sum([entry[0] for entry in styles])
        memo = get_styles(self.texel, i, i+n)
        iterator = StyleIterator(iter(styles))
        self.texel = grouped(
            set_styles(self.texel, i, iterator))
        self.notify_views('properties_changed', i, i+n)
        return memo

    def set_parproperties(self, i1, i2, **properties):
        """Sets the paragraph properties between *i1* and *i2*.

        Note that i2 can include the endmark, so that i2 <= len(self)+1.
        Also note that only NL-texels between i1..i2 are changed. 
        """
        n = len(self)
        if not (0 <= i1 <= i2 <= n+1):
            raise IndexError((i1, i2))
        texel = self.get_xtexel()
        memo = get_parstyles(texel, i1, i2)
        t = grouped(
            set_parproperties(texel, i1, i2, properties))
        self.set_xtexel(t)        
        
        # This is controversial: should we restrict the change
        # message to the range occupied by Texel or should we allow +1
        # to signal ENDMARK-changes?
        self.notify_views('properties_changed', i1, min(i2, n))
        return memo

    def clear_parproperties(self, i1, i2, *keys):
        if not (-1 <= i1 <= i2 <= len(self)+1):
            raise IndexError((i1, i2))
        texel = self.get_xtexel()
        memo = get_parstyles(texel, i1, i2)
        t = grouped(
            clear_parproperties(texel, i1, i2, keys))
        assert length(t) == length(texel)
        self.set_xtexel(t)
        self.notify_views('properties_changed', i1, i2)
        return memo    
        
    def set_parstyles(self, i, styles):
        """Sets the paragraph style of a span of text. Usually used by undo."""
        if not (0 <= i <= len(self)+1):
            raise IndexError(i)
        n = len(self)
        m = sum([entry[0] for entry in styles])
        texel = self.get_xtexel()
        memo = get_parstyles(texel, i, i+m)
        iterator = StyleIterator(iter(styles))

        t = grouped(
            set_parstyles(texel, i, iterator))
        self.set_xtexel(t)        

        # This is controversial: should we restrict the change
        # message to the range occupied by Texel or should we allow +1
        # to signal ENDMARK-changes?
        self.notify_views('properties_changed', i, min(i+m, n))        
        return memo

    def set_parstyle(self, i, style):
        j = next_newline(self.get_xtexel(), i)
        return self.set_parstyles(i, [(j + 1 - i, style)])

    def increase_indent(self, i1, i2):
        indents = self.get_indents(i1, i2)
        new = [min(9, i+1) for i in indents]        
        return self.set_indents(i1, i2, new)

    def decrease_indent(self, i1, i2):
        indents = self.get_indents(i1, i2)
        new = [max(0, i-1) for i in indents]
        return self.set_indents(i1, i2, new)
    
    def get_indent(self, i):
        texel = self.get_xtexel()
        j = next_newline(texel, i)
        return get_texel(texel, j).indent

    def set_indent(self, i, indent):
        j = next_newline(self.get_xtexel(), i)
        return self.set_indents(i, j + 1, [indent])

    def set_indents(self, i1, i2, indents):
        old = self.get_indents(i1, i2)
        def fun(texel, new=list(indents)):
            if isinstance(texel, NewLine):
                return texel.set_indent(new.pop(0))
            return texel
        texel = self.get_xtexel()
        t = transform_range(texel, i1, i2, fun)
        self.set_xtexel(grouped(t))
        self.notify_views('properties_changed', i1, i2)
        return old

    def get_indents(self, i1, i2):
        return [nl.indent for _, nl in get_newlines(self.get_xtexel(), i1, i2)]
            
    def insert(self, i, text):
        """Inserts *text* at position *i*."""
        n = length(text.texel)
        m = length(self.texel)
        stuff = strip2list(text.texel)
        tmp = grouped(insert(self.texel, i, stuff))
        self.texel = tmp
        assert length(self.texel) == m+n
        self.notify_views('inserted', i, n)

    def append(self, text):
        """Appends textmodel *texel*."""
        return self.insert(len(self), text)

    def append_text(self, text, **properties):
        """Appends unicode text."""
        return self.insert_text(len(self), text, **properties)

    def insert_text(self, i, text, **properties):
        """Inserts a unicode text string *text* at index *i*.""" 
        textmodel = self.create_textmodel(text, **properties)
        self.insert(i, textmodel)

    def copy(self, i1, i2):
        """Returns a copy of all data between *i1* and *i2*."""
        rest, removed = takeout(self.texel, i1, i2)
        model = self.create_textmodel()
        model.texel = grouped(removed)
        return model

    def __add__(self, other):
        model = self.create_textmodel()
        model.texel = self.texel
        model.insert(len(self), other)
        return model

    def __getitem__(self, slice):
        if slice.start is None:
            i1 = 0
        else:
            i1 = slice.start
            if i1 < 0:
                i1 = len(self)+i1
                if i1 < 0:
                    raise IndexError(slice.start)

        if slice.stop is None:
            i2 = len(self)
        else:
            i2 = slice.stop
            if i2 < 0:
                i2 = len(self)+i2
                if i2 < 0:
                    raise IndexError(slice.stop)
        return self.copy(i1, i2)

    def remove(self, i1, i2):
        """Removes everything between *i1* and *i2*."""
        rest, kern = takeout(self.texel, i1, i2)
        self.texel = grouped(rest)

        model = self.create_textmodel()
        model.texel = grouped(kern)

        self.notify_views('removed', i1, model)
        #assert check(self.texel)
        return model

    def dump(self, i1=None, i2=None):
        dump_range(self.texel, i1 or 0, i2 or len(self))



def pycolorize(rawtext, coding='latin-1'): # is latin-1 ok?
    # used for benchmarking
    assert type(rawtext) == bytes
    
    from io import BytesIO
    rawtext += b'\n' # still needed in py3?
    instream = BytesIO(rawtext).readline

    import token, tokenize, keyword
    _KEYWORD = token.NT_OFFSET + 1
    _TEXT    = token.NT_OFFSET + 2

    _colors = {
        token.NUMBER:       '#0080C0',
        token.OP:           '#0000C0',
        token.STRING:       '#004080',
        tokenize.COMMENT:   '#008000',
        token.NAME:         '#000000',
        token.ERRORTOKEN:   '#FF8080',
        _KEYWORD:           '#C00000',
        #_TEXT:              '#000000',
    }

    text = rawtext.decode(coding)    
    model = TextModel(text)

    for t in tokenize.tokenize(instream):
        toktype = t.type
        if token.LPAR <= toktype and toktype <= token.OP:
            toktype = token.OP
        elif toktype == token.NAME and keyword.iskeyword(t.string):
            toktype = _KEYWORD
        color = _colors.get(toktype)            
        if color is not None:
            srow, scol = t.start
            erow, ecol = t.end
            i1 = model.position2index(srow-1, scol)
            i2 = model.position2index(erow-1, ecol)
            model.set_properties(i1, i2, textcolor=color)            

    return model.copy(0, len(model)-1)




text1 = "0123456789"
text2 = "abcdefghijklmnopqrstuvwxyz"
text3 = "01\n345\n\n89012\n45678\n"


def test_00():
    "remove w. simplify"
    t2 = TextModel(text2)

    for i in range(len(text1)):
        t = TextModel(text1)
        t.remove(i, i+1)
        if not isinstance(t.texel, Text):
            dump(t.texel)
        assert isinstance(t.texel, Text)

    for i in range(len(text1)):
        t = TextModel(text1)
        t.texel = Group([t.texel])
        t.remove(i, i+1)
        assert isinstance(t.texel, Text)

    # Groups of only one element should be opened
    for i in range(len(text1)):
        t = TextModel(text1)
        t.texel = Group([t.texel])
        t.remove(i, i+1)
        assert isinstance(t.texel, Text)

    # Text with different styling should not be merged
    for i in range(2*len(text1)):
        t = TextModel(text1)
        t1 = TextModel(text1, fontsize=20)
        t.insert(len(t), t1)
        t.remove(i, i+1)
        #print ("removed", i, i+1, t.texel)
        assert isinstance(t.texel, Group)
        assert len(t.texel.childs) == 2
        assert isinstance(t.texel.childs[0], Text)
        assert isinstance(t.texel.childs[1], Text)
        text = '01234567890123456789'
        text = text[:i]+text[i+1:]
        assert t.get_text() == text



def test_01():
    "row, col"

    def index2position(t, i):
        row = t[:i].count('\n')
        i0 = 0
        for j in range(row):
            i0 = t.index('\n', i0)+1
        col = i-i0
        return row, col

    def lfromt(t):
        # for debugging
        splitter = t.split('\n')
        l = [len(s)+1 for s in splitter[:-1]]
        return l

    texts = [text3]
    text = '0123456789'
    import random
    while text.count('\n')<len(text):
        i = random.randrange(len(text))
        if text[i] == '\n':
            continue
        text = text[:i]+'\n'+text[i+1:]
        texts.append(text)

    for text in texts:
        t = TextModel(text)
        ll_text = lfromt(text)


        for i in range(len(text)):
            row, col, i0 = t.index2position(i)
            assert (row, col) == index2position(text, i)
            assert i0 == 0

        for i in range(len(text)):
            row, col = index2position(text, i)
            i_ = t.position2index(row, col)
            assert i == i_



def test_03():
    "TextModel"
    t1 = TextModel(text1)
    assert t1.get_text() == text1
    t2 = TextModel(text2)
    assert t2.get_text() == text2
    t3 = TextModel(text1+'\n'+text2)
    assert t3.get_text() == text1+'\n'+text2
    assert t3.nlines() == 2
    assert t3.position2index(0, 5) == 5
    assert t3.position2index(1, 0) == 11
    assert t3.get_text()[10] == '\n'
    assert t3.get_text()[11] == 'a'
    assert t3.linelength(0) == len(text1)+1 # the newline counts!
    assert t3.linelength(len(text1)+1) == len(text2)

    t1.insert(0, t2)
    assert  t1.get_text() == text2+text1
    t1.remove(0, len(text2))
    assert t1.get_text() == text1

    t1.insert(3, t3)
    tmp = text1[:3]+text1+'\n'+text2+text1[3:]
    assert t1.get_text() == tmp
    n = len(t1)
    old = t1.remove(3, 3+len(t3))
    assert len(old) + len(t1) == n
    assert t1.get_text() == text1


def test_04():
    "indices"
    t = TextModel(text1+'\n'+text2)
    row = col = 0

    for i in range(len(t)):

        assert t.index2position(i) == (row, col, 0)
        if t.get_text(i, i+1) == '\n':
            row += 1
            col = 0
        else:
            col += 1


def test_05():
    "style"
    class TestModel(TextModel):
        defaultstyle = create_style(textcolor='black', fontsize=10)

    t1 = TestModel(text1)
    assert t1.get_text() == text1
    t2 = TestModel(text2)
    assert t2.get_text() == text2
    t3 = TestModel(text1+'\n'+text2)

    # Styles are compared by their id. Same styles always have the
    # same id. This is assured by the factory function "new_style()"
    assert t3.get_style(0) == TestModel.defaultstyle
    assert t3.get_style(0) is TestModel.defaultstyle

    t3.set_properties(5, 10, textcolor='red')
    t3.set_properties(3, 8, fontsize=8)

    for i in range(len(t3)):
        style = t3.get_style(i)
        if i<5:
            assert style.get('textcolor') == 'black'
        elif i<10:
            assert style['textcolor'] == 'red'
        else:
            assert style['textcolor'] == 'black'

        if i<3:
            assert style['fontsize'] == 10
        elif i<8:
            assert style['fontsize'] == 8
        else:
            assert style['fontsize'] == 10

    #assert len(style_pool) == 4 # depends on gc

    t3.set_properties(0, len(t3), **TestModel.defaultstyle)
    for i in range(len(t3)):
        style = t3.get_style(i)
        assert style == TestModel.defaultstyle
        assert id(style) == id(TestModel.defaultstyle)

    t3.set_properties(0, len(t3), fontsize = 6)
    s0 = t3.get_style(0)
    for i in range(len(t3)):
        style = t3.get_style(i)
        assert id(style) == id(s0)
    assert s0['fontsize'] == 6


def test_06():
    "get_style"
    t = TextModel(text1)
    assert t.get_text() == text1

    t.set_properties(3, 5, fontsize=8)
    s = t.get_style(4)
    n = len(t)
    t.insert(4, TextModel('x', **s))
    assert len(t) == n+1
    assert t.get_style(3) is s
    assert t.get_style(4) is s
    assert t.get_style(5) is s


def test_08():
    "insert/remove"
    text = text1+'\n'+text2
    for i in range(len(text)):
        t = TextModel(text)
        n = len(t)
        x = TextModel('x')
        t.insert(i, x)
        assert len(t) == n+1
        t.remove(i, i+1)
        assert len(t) == n


def test_09():
    "slice"
    text = "Text A"
    model = TextModel(text)

    assert model.get_text() == text
    assert model[5:6].get_text() == text[5:6]
    assert model[-1:].get_text() == text[-1:]
    for i in range(len(text)):
        for n in range(1, len(text)-i):
            j = i+n
            assert model[i:j].get_text() == text[i:j]
            assert model[i:-n].get_text() == text[i:-n]
            assert model[-i:].get_text() == text[-i:]


def test_10():
    "split"
    t = TextModel(text1+'\n'+text2)
    n = len(t)
    for i in range(len(t)+1):
        #print i
        item1 = t[:i]
        item2 = t[i:]
        assert len(item1)+len(item2) == n


def test_11():
    "properties"
    t = TextModel(text1+'\n'+text2)
    t.set_properties(5, 15, selected=True)
    t.set_properties(5, 15, selected=False)
    #print t.texel
    t.get_style(5) == {
        'bgcolor': 'white', 'textcolor': 'black', 'fontsize': 10,
        'selected': False}


def test_12():
    "remove all"
    t = TextModel(text1+'\n'+text2)
    t.remove(0, len(t))

def test_13():
    'ENDMARK'
    t = TextModel(text1+'\n'+text2)
    assert length(t.get_xtexel()) == length(t.texel)+1

def heavy_test():
    'pycolorize'
    filename = 'textmodel/textmodel.py'
    rawtext = open(filename).read()
    pycolorize(rawtext)


def test_14():
    "random insert/remove"
    class TestModel(TextModel):
        defaultstyle = create_style(s=10)

    model = TestModel(u'0123')
    from random import randrange, choice


    n = len(model)
    for j in range(1000):
        i1 = randrange(n)
        i2 = randrange(n)
        i1, i2 = sorted([i1, i2])

        model.remove(i1, i2)

        m = i2-i1
        text = u'abcdefghijkl'[:m]
        i1 = randrange(len(model))

        size = choice([6, 8, 10, 14])

        model.insert(i1, TestModel(text, s=size))

        assert not "C(u'')" in str(model.texel)


def test_15():
    "get/set styles"

    s0 = TextModel.defaultstyle
    s1 = create_style(bgcolor='red')

    t = Text(text1)
    assert get_styles(t, 0, length(t)) == [(length(t), s0)]

    t = grouped(set_properties(t, 3, 5, {'bgcolor':'red'}))
    styles = get_styles(t, 0, length(t))
    assert styles == [
        (3, s0),
        (2, s1),
        (5, s0),
        ]

    # Override styling
    n = length(t)
    t = grouped(set_styles(t, 0, StyleIterator(iter([(n, s0)]))))
    assert get_styles(t, 0, length(t)) == [(n, s0)]

    # And revert
    t = grouped(set_styles(t, 0, StyleIterator(iter(styles))))
    styles = get_styles(t, 0, length(t))
    assert styles == [
        (3, s0),
        (2, s1),
        (5, s0),
        ]

    # Merge styles:
    styles = get_styles(Group([Text(text1), Text(text1)]),
             0, 2*len(text1))
    assert len(styles) == 1
    assert styles[0][0] == 2*len(text1)


def test_16():
    "undo properties"
    s0 = TextModel.defaultstyle
    s1 = create_style(fontsize=3)

    model = TextModel(text1)
    old = model.set_properties(2, 5, fontsize=3)
    styles = get_styles(model.texel, 0, len(model))
    assert styles == [
        (2, s0),
        (3, s1),
        (5, s0),
        ]
    model.set_styles(2, old)
    styles = get_styles(model.texel, 0, len(model))
    assert styles == [
        (10, s0)
        ]

def test_17():
    "Tabulator"
    text = "line 1\nline 2\tcol 1\tcol2\n\n"
    model = TextModel(text)
    assert model.get_text() == text


def test_18():
    "dump_range"
    import io
    from contextlib import redirect_stdout
    t = TextModel(text1+'\n'+text2)
    with redirect_stdout(io.StringIO()):
        dump_range(t.texel, 1, 10)


def test_19():
    "get/set parstyle"
    model = TextModel(text1+'\n'+text2)
    n = len(model)
    assert model.get_parstyle(1) == {}
    model.set_parproperties(0, len(model), textcolor='red')
    assert model.get_parstyle(1) == {'textcolor':'red'}
    model.clear_parproperties(0, len(model), 'textcolor')
    assert model.get_parstyle(1) == {}
    assert n == len(model)

    
def test_20():
    "indent"
    model = TextModel(text1+'\n'+text2+'\n'+text3)
    n = len(model)
    assert model.get_indents(0, n) == [0, 0, 0, 0, 0, 0, 0]
    model.increase_indent(0, n)
    assert model.get_indents(0, n) == [1, 1, 1, 1, 1, 1, 1]
    model.increase_indent(0, 38)
    assert model.get_indents(0, n) == [2, 2, 1, 1, 1, 1, 1]
    model.decrease_indent(0, n)
    assert model.get_indents(0, n) == [1, 1, 0, 0, 0, 0, 0]
    model.decrease_indent(0, n)
    assert model.get_indents(0, n) == [0, 0, 0, 0, 0, 0, 0]
    assert len(model) == n
    

def test_21():
    "expand_range"
    m = TextModel("hello")
    assert m.expand_range(1, 3) == (1, 3)

    from .texeltree import Fraction
    m = TextModel()
    m.texel = Fraction(Text("a"), Text("b"))
    n = length(m.texel)
    # touching leading separator --> full container
    assert m.expand_range(0, 1) == (0, n)
    # spanning middle separator --> full container
    assert m.expand_range(1, 4) == (0, n)
    # inside first child only --> unchanged
    assert m.expand_range(1, 2) == (1, 2)


def test_22():
    "get_start / get_end"
    m = TextModel("hello")
    n = len(m)
    assert m.get_start(0) == 0
    assert m.get_end(0) == n

    from .texeltree import Fraction
    m = TextModel()
    m.texel = Fraction(Text("a"), Text("b"))
    n = len(m) 
    assert m.get_start(0) == 0
    assert m.get_start(1) == 1
    assert m.get_start(2) == 1   # sep1 treated as end of cell 1
    assert m.get_start(3) == 3
    
    assert m.get_end(0) == n
    assert m.get_end(1) == 2     # closing sep of cell 1
    assert m.get_end(3) == 4     # closing sep of cell 2

    
def test_23():
    "get_parstyle inside a container"
    from .texeltree import Fraction
    # Paragraph: [container] [NL with parstyle]
    nl = NewLine({'color': 'red'})
    nl = nl.set_parstyle({'alignment': 'left'})
    nl.indent = 2
    
    container = Fraction(Text("a"), Text("b"))
    sep1 = container.childs[2].set_parstyle({'alignment' : 'right'})
    sep2 = container.childs[4].set_parstyle({'alignment' : 'center'})

    container.childs[2] = sep1
    container.childs[4] = sep2
    
    m = TextModel()
    m.texel = grouped([container, nl])

    assert m.get_parstyle(1) == {'alignment': 'right'}
    assert m.get_parstyle(2) == {'alignment': 'right'}
    assert m.get_parstyle(3) == {'alignment': 'center'}
    assert m.get_parstyle(4) == {'alignment': 'center'}


__all__ = ['TextModel']
