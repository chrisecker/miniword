# -*- coding: utf-8 -*-

"""
Submodels are models that are attached to a Texel in the root-model
but they form a separate flow in the layout.

Submodels are needed for footnotes, floats and captions.
"""



from ..textmodel.textmodel import TextModel
from ..textmodel.texeltree import grouped, Single, G, T, NULL_TEXEL, get_text, \
    ENDMARK, takeout, length
from ..textmodel.utils import transform_range
from copy import copy as shallow_copy



class SubModel(TextModel):
    """
    TextModel that immediately syncs texel changes back to a host
    texel in a root model.

    The host texel at anchor must implement set_content(texel) → new_host.
    """

    def __init__(self, root, anchor, offset, content):
        TextModel.__init__(self)
        self.root = root
        self.anchor = anchor
        self.offset = offset
        n = length(content)
        t, e = takeout(content, n-1, n)
        self._texel = grouped(t)
        self.ENDMARK = grouped(e)
        assert self.ENDMARK.is_endmark

    def create_textmodel(self, text='', **properties):
        return TextModel(text, **properties)

    def set_texel(self, value):
        # Set local texel and attach it as content in the host node
        self._texel = value
        # Here it becomes clear that the separation between texel and
        # endmark was a bad idea.
        xtexel = self.xtexel
        i = self.anchor
        new_list = transform_range(
            self.root.texel, i, i + 1, lambda host: host.set_content(xtexel)
        )
        self.root.texel = grouped(new_list)
        self.root.notify_views('properties_changed', i, i + 1)


        
class Footnote(Single):
    # Footnote texel: an inline anchor (length 1) whose content forms
    # a separate flow, layouted via SubModel. content must end with
    # an ENDMARK, carrying the parstyle of the last line.
    content = NULL_TEXEL
    def __init__(self, content=ENDMARK):
        self.content = content

    def set_content(self, content):
        clone = shallow_copy(self)
        clone.content = content
        return clone

    
def insert_footnote(model, i, text):
    # for testing: insert a footnote at position i
    fn = Footnote(G([T(text), ENDMARK]))
    m = TextModel()
    m.texel = fn
    return model.insert(i, m)

def _get_text(texel):
    # for testing: get text containing footnotes in brackets
    if isinstance(texel, Footnote):
        return "[%s]" % _get_text(texel.content)[:-1]
    if texel.is_single or texel.is_text:
        return texel.text
    return u''.join([_get_text(x) for x in texel.childs])
    
    
def mk_test():
    "create a model for testing submodels"
    fn1 = "Albert Einstein (1879–1955), deutsch-schweizerisch-amerikanischer "\
          "Physiker und Nobelpreisträger 1921."
    fn2 = "Erschienen unter dem Titel <<Zur Elektrodynamik bewegter Körper>> "\
          "in den Annalen der Physik."
    model = TextModel("Albert Einstein veröffentlichte 1905 seine Spezielle "\
                      "Relativitätstheorie.")
    insert_footnote(model, 72, fn2)
    insert_footnote(model, 15, fn1)
    return model

    

def test_00():
    from .utils import get_path
    model = mk_test()
    
    t = _get_text(model.texel)
    assert t == "Albert Einstein[Albert Einstein (1879–1955), deutsch-" \
                "schweizerisch-amerikanischer Physiker und Nobelpreisträger " \
                "1921.] veröffentlichte 1905 seine Spezielle Relativitäts" \
                "theorie[Erschienen unter dem Titel <<Zur Elektrodynamik " \
                "bewegter Körper>> in den Annalen der Physik.]."

    n = len(t)
    i1, i2, note = get_path(model.texel, 73)[-1]
    sm = SubModel(model, 73, 0, note.content)
    sm.insert_text(0, 'XXX')
    t = _get_text(model.texel)
    assert len(t) == n+3
    
    sm.remove(0, 3)
    t = _get_text(model.texel)
    assert len(t) == n
