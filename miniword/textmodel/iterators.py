# -*- coding: utf-8 -*-
from .texeltree import NewLine, length


def iter_leafes(texel, i, descend_containers=False):
    """Iterates through all leaf-elements starting at i. """

    l = [[texel]]
    i1 = 0
    while 1:
        while l and not l[-1]:
            l.pop()
        if not l:
            break
        ll = l[-1]
        elem = ll[0]
        del ll[0]
        n = length(elem)
        if i1+n <= i:
            i1 = i1+n        
        elif elem.is_group:
            l.append(list(elem.childs))
        elif elem.is_container and descend_containers:
            l.append(list(elem.childs))
        else:
            i2 = i1+n
            yield i1, i2, elem
            i1 = i2

def iter_newlines(texel, i, descend_containers=False):
    """Find all NewLine-Texels at or after position i. 
    """
    for j1, j2, elem in iter_leafes(texel, i, descend_containers):
        if isinstance(elem, NewLine):
            yield j1, j2, elem

            
def iter_paragraphs(texel, i, descend_containers=False):
    """Break the texel material into paragraphs. Yields for each
    paragraph begin, end and list of texels. 
    """
    l = []
    i1 = 0
    for j1, j2, elem in iter_leafes(texel, i, descend_containers):
        l.append(elem)
        if isinstance(elem, NewLine):
            yield i1, j2, l
            l = []
            i1 = j2

    
def test_00():
    "iter_leafes"
    from .texeltree import T, G, Container
    t1 = T("012345678")
    t2 = T("ABC")
    t3 = T("xyz")
    c = Container().set_childs((t2, t3))
    g = G((t1, c))
    l = []
    for i1, i2, elem in iter_leafes(g, 0):
        l.append((i1, i2, elem))
    assert repr(l) == "[(0, 9, T('012345678')), (9, 15, C([T('ABC'), T('xyz')]))]"
    
