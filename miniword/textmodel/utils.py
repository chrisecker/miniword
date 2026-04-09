from .texeltree import NewLine, length, iter_childs, fuse, grouped


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


def get_newlines(texel, i1, i2, _offset=0):
    """Yield (abs_pos, nl) for all NewLines in [i1, i2).

    Descends into both Groups and Containers, so works inside table cells.
    """
    if texel.is_group or texel.is_container:
        for j1, j2, child in iter_childs(texel):
            if j2 <= i1 or j1 >= i2:
                continue
            yield from get_newlines(child, i1 - j1, i2 - j1, _offset + j1)
    elif isinstance(texel, NewLine):
        if i1 <= 0 < i2:
            yield _offset, texel


def transform(texel, i1, i2, fun):
    """Apply fun to all texels in [i1, i2), descending into containers.

    Returns a list of texels (like texeltree.transform).
    Groups and Containers are treated identically: recursed into.
    """
    if texel.is_group or texel.is_container:
        r1 = []; r2 = []; r3 = []
        for j1, j2, child in iter_childs(texel):
            if j2 <= i1:
                r1.append(child)
            elif j1 >= i2:
                r3.append(child)
            else:
                r2 = fuse(r2, transform(child, i1 - j1, i2 - j1, fun))
        if texel.is_container:
            return [texel.set_childs(r1 + r2 + r3)]
        return fuse(r1, r2, r3)
    elif texel.is_single:
        if i1 >= 1 or i2 <= 0:
            return [texel]
        return [fun(texel)]
    elif texel.is_text:
        from .texeltree import T
        r = []
        text = texel.text
        n = len(text)
        i1 = max(0, i1)
        i2 = min(n, i2)
        if i1:
            r.append(T(text[:i1], texel.style))
        if i2 > i1:
            r.append(fun(T(text[i1:i2], texel.style)))
        if i2 < n:
            r.append(T(text[i2:], texel.style))
        return r
    return [texel]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

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


def test_01():
    "get_newlines descends into containers"
    from .texeltree import G, NL, Container
    nl1 = NL.set_indent(1)
    nl2 = NL.set_indent(2)
    c = Container().set_childs([nl1])
    g = G([nl2, c])
    # nl2 at pos 0, c at pos 1..2 (nl1 inside)
    result = list(get_newlines(g, 0, 3))
    assert len(result) == 2
    assert result[0] == (0, nl2)
    assert result[1] == (1, nl1)


def test_02():
    "transform descends into containers"
    from .texeltree import G, NL, Container, length
    nl = NL.set_indent(0)
    c = Container().set_childs([nl])
    g = G([c])

    called = []
    def fun(texel):
        if isinstance(texel, NewLine):
            called.append(texel)
            return texel.set_indent(3)
        return texel

    result = transform(g, 0, length(g), fun)
    assert called, "fun was not called"
    result_g = G(result)
    inner_nl = result_g.childs[0].childs[0]
    assert inner_nl.indent == 3
