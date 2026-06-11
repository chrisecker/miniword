# -*- coding: utf-8 -*-


from ..textmodel import texeltree
from ..textmodel.viewbase import ViewBase
from ..textmodel.properties import overridable_property
from ..textmodel.textmodel import TextModel
from ..textmodel.texeltree import NewLine, Group, Text, length
from ..textmodel.styles import EMPTYSTYLE
from .testdevice import TESTDEVICE
from .boxes import TextBox, NewlineBox, TabulatorBox, EmptyTextBox, \
    EndBox, check_box, Box, calc_length
from .cache import LRUCache



class Factory:
    # The Factory object takes a texeltree as an outline to create a
    # sequence of boxes. For every Texel-Class Factory has a
    # corresponding handler method of the same name,
    # e.g. Group_handler for Group-texels. The call signature is
    # handler(texel, i1, i2), where i1 and i2 denotes the part of
    # texel for which boxes are generated.

    TextBox = TextBox
    NewlineBox = NewlineBox
    TabulatorBox = TabulatorBox
    EndBox = EndBox

    parstyle = EMPTYSTYLE

    def __init__(self, device=TESTDEVICE):
        self.device = device
        self.cache = LRUCache(10000)

    def clear_caches(self):
        self.cache.clear()
        self.device.clear_caches()

    def get_device(self):
        return self.device

    def mk_style(self, style):
        # This can overriden e.g. to implement style sheets. The
        # default behaviour is to use the paragraph style and add the
        # text styles.
        r = self.parstyle.copy()
        r.update(style)
        return r

    ### Factory methods
    def create_all(self, texel):
        # Convenience method
        return self.create_boxes(texel, 0, length(texel))

    def create_boxes(self, texel, i1, i2):
        assert i1>=0
        assert i2<=length(texel)
        assert i1<=i2
        if i1 == i2:
            return () # XXX Why is this needed?
        name = texel.__class__.__name__+'_handler'
        handler = getattr(self, name)
        #print "calling handler", name, i1, i2
        l = handler(texel, i1, i2)
        try:
            assert calc_length(l) == i2-i1
        except:
            print("handler=", handler)
            raise
        return tuple(l)
        
    def Group_handler(self, texel, i1, i2):
        # Handles group texels. Note that the list of childs is
        # traversed from right to left. This way the "Newline" which
        # ends a line is handled before the content in the line. This
        # is important because in order to build boxes for the line
        # elements, we need the paragraph style which is located in
        # the NewLine-Texel.
        r = ()
        for j1, j2, child in reversed(list(texeltree.iter_childs(texel))):
            if i1 < j2 and j1 < i2: # overlapp
                r = self.create_boxes(child, max(0, i1-j1), min(i2, j2)-j1)+r
        return r

    def Text_handler(self, texel, i1, i2):
        return [self.TextBox(texel.text[i1:i2], self.mk_style(texel.style), 
                             self.device)]

    def Text_handler(self, texel, i1, i2):
        # Caching version. It is important that dicts do not change!
        key = texel.text, id(texel.style), id(self.parstyle), i1, i2, self.device
        try:
            return self.cache.get(key)
        except KeyError:
            pass
        r = [self.TextBox(texel.text[i1:i2], self.mk_style(texel.style), 
                          self.device)]
        self.cache.set(key, r)
        return r

    def NewLine_handler(self, texel, i1, i2):
        self.parstyle = texel.parstyle
        if texel.is_endmark:
            return [self.EndBox(self.mk_style(texel.style), self.device)]
        return [self.NewlineBox(self.mk_style(texel.style), self.device)] # XXX: Hmmmm

    def Tabulator_handler(self, texel, i1, i2):
        return [self.TabulatorBox(self.mk_style(texel.style), self.device)]



class BuilderBase(ViewBase):
    """
    The builder is responsible for creating and updating the layout. 

    The length of layout is always the length of the model +1, because
    we add a special box ("end mark").
    """

    layout = overridable_property('layout')
    _layout = None
    def __init__(self, model):
        ViewBase.__init__(self)
        self.model = model

    def get_layout(self):
        assert self._layout is not None
        return self._layout

    def inserted(self, model, i, n):
        self.rebuild_range(i, i, n)

    def removed(self, model, i, text):
        self.rebuild_range(i, i, -len(text)) # XXX besser wäre i, i+len, -len

    def properties_changed(self, model, i1, i2):
        self.rebuild_range(i1, i2, 0)

    def assure_finished(self):
        pass # default: do nothing
    
    def assure_index(self, i):
        pass # default: do nothing

    def assure_rect(self, r):
        pass # default: do nothing

    def assure_y(self, y):
        pass # default: do nothing
                
    def rebuild(self):
        raise NotImplemented()

    def rebuild_range(self, i1, i2, delta):
        raise NotImplemented()
    
        

        
class TestBuilder(BuilderBase):
    """A dummy Builder which enables simple testing."""
    def get_layout(self):
        return



def test_01():
    factory = Factory()
    boxes = factory.create_all(TextModel("123").texel)
    assert calc_length(boxes) == 3
    boxes = factory.create_all(TextModel("123\n567").get_xtexel())
    assert calc_length(boxes) == 8

    


