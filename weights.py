# -*- coding: latin-1 -*-

# Utilities for working with weights
#
# NOTE: The following helper functions only work with certain weight
# functions. They will work for weights aggregated by 'sum', such as
# lengths and line numbers. But trying to find depth values will lead
# to unexpected and unpredicted behaviour.


from .texeltree import length, iter_childs, Texel


debug = 0


class NotFound(Exception): 
    pass



def find_weight(texel, w, windex):
    """Return the position where the accumulated weight *windex* first reaches *w*.

    Inverse of get_weight: find_weight(t, get_weight(t, wi, i), wi) == i
    for positions i that are exactly at a weight boundary (e.g. a NewLine).
    Only works for additive weights (length, lineno), not depth.
    Containers are treated as atomic --> their inner weights are not traversed.
    """
    assert type(w) is int
    if w == 0:
        return 0
    if texel.is_group:
        sum_w = 0
        for i1, i2, child in iter_childs(texel):
            delta = child.weights[windex]
            if sum_w+delta >= w:
                return find_weight(child, w-sum_w, windex)+i1
            sum_w += delta
    if w == texel.weights[windex]:
        return length(texel)
    raise NotFound(w)



def find_newline(texel, i):
    """
    Returns the position of the next newline at or after i.

    If i lies inside a container, the corresponding container cell is
    searched. The closing seperator always counts as NewLine. When i
    lies outside, the container is treated as atomic.
    
    Returns None if no next newline exists.
    """
    windex = 2
    if texel.is_container:
        if i <= 0:
            return None

        j2 = 1
        for content in texel.childs[1::2]:
            j1 = j2
            j2 += length(content)+1
            if j2 <= i:
                continue            
            if i < j2-1 and content.weights[windex]:
                result = find_newline(content, i-j1)
                if result is not None:
                    return result+j1
            return j2-1 # position of SEP

    elif texel.is_group:
        for j1, j2, child in iter_childs(texel):
            if j2 <= i:
                continue
            if j1 < i and child.is_container:
                result = find_newline(child, i-j1)
                if result is not None:
                    return result+j1
                continue
            if child.weights[windex] == 0:
                continue
            result = find_newline(child, i-j1)
            if result is not None:
                return result+j1

    elif texel.is_single and texel.weights[windex] > 0:
        # we found it!
        return 0

    # not found
    return None



    
def get_weight(texel, windex, i):
    """Return the accumulated weight *windex* of texel up to (not including) position *i*.

    For windex=2 (lineno) this counts the number of NewLines before position i.
    """
    if i<0:
        raise IndexError
    if i >= length(texel):
        return texel.weights[windex]
    w = 0
    if i == 0:
        return w

    if texel.is_group:
        for i1, i2, child in iter_childs(texel):
            if i2 <= i:
                w += child.weights[windex]
            elif i1 <= i <= i2:
                w += get_weight(child, windex, i-i1)
            else:
                break
    return w




def test_00():
    "find_newline"
    from .texeltree import T, NL, G, Fraction, dump, get_text
    g = G([T("abc"), NL])
    assert find_newline(g, 0) == 3
    assert find_newline(g, 1) == 3
    assert find_newline(g, 2) == 3
    assert find_newline(g, 3) == 3
    assert find_newline(g, 4) is None

    f = Fraction(T("x"), T("y"))
    t = get_text(f)
    
    assert find_newline(f, 0) == None # not inside a cell
    assert find_newline(f, 1) == 2 # first cell
    assert find_newline(f, 2) == 2
    assert t[2] == '\n'
    assert find_newline(f, 3) == 4 # second cell
    assert find_newline(f, 4) == 4
    assert find_newline(f, 5) is None # outside container

    g = G([T("ab"), f])
    assert find_newline(g, 0) == None # outside
    assert find_newline(g, 1) == None
    assert find_newline(g, 2) == None # not inside cell    
    assert find_newline(g, 3) == 4 # inside cell #1
    assert find_newline(g, 4) == 4 
    assert find_newline(g, 5) == 6 # inside cell #2
    assert find_newline(g, 6) == 6 
    assert find_newline(g, 7) is None # outside container

    g = G([T("ab"), f, NL])
    assert find_newline(g, 0) == 7
    assert find_newline(g, 7) == 7


def test_01():
    "find_weight"
    from .texeltree import T, NL, G, Fraction
    # windex=2 is lineno (NewLine count)
    g = G([T("ab"), NL, T("cd"), NL])
    # text: 'ab\ncd\n', lengths: 2+1+2+1=6
    assert find_weight(g, 1, 2) == 3   # position after 1st NL
    assert find_weight(g, 2, 2) == 6   # position after 2nd NL (== length)
    # containers are opaque: their inner NLs don't count at the outer level
    f = Fraction(T("x"), T("y"))       # has NLs inside cells, but weights[2]=0
    g2 = G([f, NL])
    assert find_weight(g2, 1, 2) == length(f) + 1  # the outer NL, not inner ones
    try:
        find_weight(g, 99, 2)
        assert False
    except NotFound:
        pass


def test_02():
    "get_weight"
    from .texeltree import T, NL, G, Fraction
    g = G([T("ab"), NL, T("cd"), NL])
    # lineno before each position
    assert get_weight(g, 2, 0) == 0
    assert get_weight(g, 2, 1) == 0
    assert get_weight(g, 2, 3) == 1    # after 1st NL
    assert get_weight(g, 2, 5) == 1
    assert get_weight(g, 2, 6) == 2    # full weight
    assert get_weight(g, 2, length(g)) == g.weights[2]
    # containers are opaque: positions inside a container contribute 0 lineno
    f = Fraction(T("x"), T("y"))       # inner NLs don't count at outer level
    g2 = G([T("a"), f, NL])
    for i in range(1, 1 + length(f) + 1):  # any position inside or at end of f
        assert get_weight(g2, 2, i) == 0
    assert get_weight(g2, 2, length(g2)) == 1  # the outer NL is counted
