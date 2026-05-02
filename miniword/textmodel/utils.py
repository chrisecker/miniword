# -*- coding: utf-8 -*-
from .texeltree import NewLine, length, iter_childs, fuse, grouped, \
    provides_childs, Group


class NotFound(Exception):
    pass


def find_weight(texel, w, windex):
    """Return the position where the accumulated weight *windex* first reaches *w*.

    Inverse of get_weight: find_weight(t, get_weight(t, wi, i), wi) == i
    for positions i that are exactly at a weight boundary (e.g. a NewLine).
    Only works for additive weights (length, lineno), not depth.
    Containers are treated as atomic.
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


def get_weight(texel, windex, i):
    """Return the accumulated weight *windex* of texel up to (not including) position *i*.

    For windex=2 (lineno) this counts the number of NewLines before position i.
    """
    if i < 0:
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



def get_localroot(texel, i, i0=0):
    """Return (root, offset) for the local coordinate system at position i.

    Inside a container's content area: returns (content_child, cell_start).
    Outside any container: returns (texel, i0).
    """
    if texel.is_container:
        j2 = i0 + 1
        for child in texel.childs[1::2]:
            j1 = j2
            j2 += length(child) + 1
            if j1 <= i < j2:
                return child, j1
        return texel, i0
    if texel.is_group:
        for j1, j2, child in iter_childs(texel):
            if j1 <= i - i0 < j2:
                result = get_localroot(child, i, i0 + j1)
                if result[0] is not child:
                    return result
                break
    return texel, i0


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


def next_newline(texel, i):
    """Return position of first NewLine at or after i, or length(texel) if none.

    Sentinel: result < length(texel) iff a NewLine was found.
    Inside a container, searches the current content cell; the closing separator
    counts as a NewLine. Outside containers are treated as atomic.
    """
    n = length(texel)
    if isinstance(texel, NewLine):
        return 0 if i <= 0 else n
    if texel.is_container:
        if i <= 0:
            return n
        j2 = 1
        for content in texel.childs[1::2]:
            j1 = j2
            j2 += length(content) + 1
            if j2 <= i:
                continue
            if i < j2 - 1:
                return next_newline(content, i - j1) + j1
            return j2 - 1
        return n
    if texel.is_group:
        if texel.weights[2] == 0:
            return n
        for j1, j2, child in iter_childs(texel):
            if j2 <= i:
                continue
            if j1 < i and child.is_container:
                result = next_newline(child, i - j1)
                if result < length(child):
                    return result + j1
                continue
            if child.weights[2] == 0:
                continue
            result = next_newline(child, i - j1)
            if result < length(child):
                return result + j1
    return n


def prev_newline(texel, i):
    """Return position of last NewLine strictly before i, or -1 if none exists.

    Inside a container, searches the current content cell. Outside containers
    are treated as atomic. Returning -1 allows ``prev_newline(...) + 1`` to
    always give the line start without a None check.
    """
    if i <= 0:
        return -1
    if isinstance(texel, NewLine):
        return 0
    if texel.is_container:
        j2 = 1
        for content in texel.childs[1::2]:
            j1 = j2
            j2 += length(content) + 1
            if j2 <= i:
                continue
            if i > j1 and content.weights[2]:
                result = prev_newline(content, i - j1)
                if result != -1:
                    return result + j1
            return j1 - 1
        return -1
    if texel.is_group:
        if texel.weights[2] == 0:
            return -1
        for j1, j2, child in reversed(list(iter_childs(texel))):
            if j1 >= i:
                continue
            if child.is_container and j2 > i:
                result = prev_newline(child, i - j1)
                if result != -1:
                    return result + j1
                continue
            if child.weights[2] == 0:
                continue
            result = prev_newline(child, i - j1)
            if result != -1:
                return result + j1
    return -1


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


    
def transform_range(texel, i1, i2, fun):
    """Apply fun to all texels in [i1, i2), descending into containers.

    Returns a list of texels.  Groups and Containers are treated identically.
    """
    if texel.is_group or texel.is_container:
        r1 = []; r2 = []; r3 = []
        for j1, j2, child in iter_childs(texel):
            if j2 <= i1:
                r1.append(child)
            elif j1 >= i2:
                r3.append(child)
            else:
                r2 = fuse(r2, transform_range(child, i1 - j1, i2 - j1, fun))
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


def find_texel(tree, texel, i):
    """Search for texel by identity in tree at position i.

    Returns (i1, i2, depth): absolute interval and depth of the texel.
    """
    if tree is texel:
        return 0, length(tree), 0
    if not provides_childs(tree):
        raise IndexError("Texel not found at position %i" % i)
    for j1, j2, child in iter_childs(tree):
        if j1 <= i < j2:
            i1_rel, i2_rel, depth = find_texel(child, texel, i - j1)
            return i1_rel + j1, i2_rel + j1, depth + 1
    raise IndexError("Texel not found at position %i" % i)


def get_texel(tree, i, depth):
    """Return the texel at position i and the given depth."""
    if depth == 0:
        if 0 <= i < length(tree):
            return tree
        raise IndexError("Position %i out of bounds" % i)
    if not provides_childs(tree):
        raise IndexError("Depth %i not reachable at position %i" % (depth, i))
    for j1, j2, child in iter_childs(tree):
        if j1 <= i < j2:
            return get_texel(child, i - j1, depth - 1)
    raise IndexError("No child covers position %i at depth %i" % (i, depth))


def transform_node(tree, i, d, fun):
    """Apply fun to the single node at position i and depth d."""
    if d == 0:
        return fun(tree)
    if not provides_childs(tree):
        raise IndexError("Can't descend into texel %s" % repr(tree))
    r = []
    for j1, j2, child in iter_childs(tree):
        if j1 <= i < j2:
            r.append(transform_node(child, i - j1, d - 1, fun))
        else:
            r.append(child)
    if tree.is_group:
        return Group(r)
    assert tree.is_container
    return tree.set_childs(r)


def get_path(tree, i, _offset=0):
    """Return the path of nodes covering position i.

    Returns a list of (abs_i1, abs_i2, node) tuples from root to leaf.
    """
    path = [(_offset, _offset + length(tree), tree)]
    if provides_childs(tree):
        for j1, j2, child in iter_childs(tree):
            if j1 <= i < j2:
                return path + get_path(child, i - j1, _offset + j1)
    return path


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
    "transform_range descends into containers"
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

    result = transform_range(g, 0, length(g), fun)
    assert called, "fun was not called"
    result_g = G(result)
    inner_nl = result_g.childs[0].childs[0]
    assert inner_nl.indent == 3


def test_03():
    "expand_range: selection not touching any separator is unchanged"
    from .textmodel import TextModel
    from .texeltree import Fraction, Text
    m = TextModel()
    m.texel = Fraction(Text("a"), Text("b"))
    assert m.expand_range(1, 2) == (1, 2)


def test_04():
    "expand_range: selection spanning a separator expands to full container"
    from .textmodel import TextModel
    from .texeltree import Fraction, Text, length
    m = TextModel()
    m.texel = Fraction(Text("a"), Text("b"))
    assert m.expand_range(1, 4) == (0, length(m.texel))


def test_05():
    "expand_range: selection touching left separator expands to full container"
    from .textmodel import TextModel
    from .texeltree import Fraction, Text, length
    m = TextModel()
    m.texel = Fraction(Text("a"), Text("b"))
    assert m.expand_range(0, 1) == (0, length(m.texel))


def test_06():
    "get_path"
    from .texeltree import G, T, Fraction
    tree = G([Fraction(T('A'), T('B'))])
    path = get_path(tree, 1)
    assert len(path) == 3
    assert path[0] == (0, 5, tree)
    assert path[1][2].is_container
    assert path[2] == (1, 2, path[1][2].childs[1])


def test_07():
    "get_texel"
    from .texeltree import G, T, Fraction
    a = T('A')
    b = T('B')
    f = Fraction(a, b)
    assert get_texel(f, 0, 0) is f
    assert get_texel(f, 1, 1) is a
    assert get_texel(f, 3, 1) is b
    assert get_texel(f, 0, 1) is f.childs[0]
    assert get_texel(f, 2, 1) is f.childs[2]
    assert get_texel(f, 4, 1) is f.childs[4]


def test_08():
    "find_texel"
    from .texeltree import G, T, Fraction
    a = T('A')
    b = T('B')
    f = Fraction(a, b)
    assert find_texel(f, f, 0) == (0, 5, 0)
    tree = G([f, T('C')])
    assert find_texel(tree, f, 0) == (0, 5, 1)
    assert find_texel(tree, a, 1) == (1, 2, 2)
    try:
        find_texel(tree, a, 2)
        assert False
    except IndexError:
        pass


def test_09():
    "transform_node"
    from .texeltree import G, T, Fraction, get_text
    a = T('A')
    b = T('B')
    c = T('C')
    x = T('X')
    f = Fraction(a, b)
    replace = lambda old: x
    assert find_texel(f, a, 1) == (1, 2, 1)
    assert get_text(transform_node(f, 1, 1, replace)) == '\nX\nB\n'
    assert get_text(transform_node(f, 3, 1, replace)) == '\nA\nX\n'
    tree = G([f, c])
    assert get_text(transform_node(tree, 1, 2, replace)) == '\nX\nB\nC'
    try:
        transform_node(tree, 1, 3, replace)
        assert False
    except IndexError:
        pass


def test_09b():
    "get_localroot"
    from .texeltree import T, NL, G, Fraction
    f = Fraction(T('x'), T('y'))
    # Fraction: sep0 at 0, T('x') at 1, sep1 at 2, T('y') at 3, sep2 at 4
    root, off = get_localroot(f, 1)   # inside cell 1
    assert root is f.childs[1] and off == 1
    root, off = get_localroot(f, 3)   # inside cell 2
    assert root is f.childs[3] and off == 3

    g = G([T('a'), f, NL])
    # T('a') at 0, f at [1,6), NL at 6
    root, off = get_localroot(g, 0)   # outside container
    assert root is g and off == 0
    root, off = get_localroot(g, 1)   # opening separator of f → outside
    assert root is g and off == 0
    root, off = get_localroot(g, 6)   # outside container
    assert root is g and off == 0
    root, off = get_localroot(g, 2)   # inside cell 1 of f → g-pos 2 = f-pos 1
    assert root is f.childs[1] and off == 2
    root, off = get_localroot(g, 4)   # inside cell 2 of f → g-pos 4 = f-pos 3
    assert root is f.childs[3] and off == 4

    # get_start / get_end semantics via get_localroot
    def get_start(texel, i):
        _, offset = get_localroot(texel, i)
        return offset
    def get_end(texel, i):
        r, offset = get_localroot(texel, i)
        return offset + length(r)
    assert get_start(g, 0) == 0
    assert get_end(g, 0) == length(g)
    assert get_start(g, 2) == 2   # cell 1 start
    assert get_end(g, 2) == 3     # cell 1 closing sep
    assert get_start(g, 4) == 4   # cell 2 start
    assert get_end(g, 4) == 5     # cell 2 closing sep


def test_10():
    "next_newline, prev_newline: plain group and smart container behavior"
    from .texeltree import T, NL, G, Fraction

    # plain group: 'ab\ncd\n', NLs at positions 2 and 5
    g = G([T('ab'), NL, T('cd'), NL])
    n = length(g)  # 6
    assert next_newline(g, 0) == 2
    assert next_newline(g, 2) == 2   # at NL returns that position
    assert next_newline(g, 3) == 5
    assert next_newline(g, 5) == 5
    assert next_newline(g, 6) == n   # sentinel: no NL found

    assert prev_newline(g, 0) == -1
    assert prev_newline(g, 2) == -1  # strictly before
    assert prev_newline(g, 3) == 2
    assert prev_newline(g, 5) == 2
    assert prev_newline(g, 6) == 5
    assert prev_newline(g, 0) + 1 == 0   # sentinel usage: line start
    assert prev_newline(g, 3) + 1 == 3

    # smart container: G([T('a'), Fraction(T('x'),T('y')), NL])
    # T('a') at [0,1); Fraction at [1,6): seps at 1,3,5; cells at [2,3) and [4,5)
    # outer NL at [6,7)
    f = Fraction(T('x'), T('y'))
    g2 = G([T('a'), f, NL])
    n2 = length(g2)  # 7

    # outside container: only outer NL visible
    assert next_newline(g2, 0) == 6
    assert prev_newline(g2, 6) == -1  # container is opaque from outside
    assert prev_newline(g2, 7) == 6

    # inside container: searches cell content, returns cell separator
    assert next_newline(g2, 2) == 3   # inside cell 1 → sep1 at g2-pos 3
    assert next_newline(g2, 4) == 5   # inside cell 2 → sep2 at g2-pos 5
    assert prev_newline(g2, 3) == 1   # inside cell 1 → sep0 at g2-pos 1
    assert prev_newline(g2, 5) == 3   # inside cell 2 → sep1 at g2-pos 3



def test_12():
    "find_weight"
    from .texeltree import T, NL, G, Fraction
    g = G([T("ab"), NL, T("cd"), NL])
    assert find_weight(g, 1, 2) == 3
    assert find_weight(g, 2, 2) == 6
    f = Fraction(T("x"), T("y"))
    g2 = G([f, NL])
    assert find_weight(g2, 1, 2) == length(f) + 1
    try:
        find_weight(g, 99, 2)
        assert False
    except NotFound:
        pass


def test_13():
    "get_weight"
    from .texeltree import T, NL, G, Fraction
    g = G([T("ab"), NL, T("cd"), NL])
    assert get_weight(g, 2, 0) == 0
    assert get_weight(g, 2, 1) == 0
    assert get_weight(g, 2, 3) == 1
    assert get_weight(g, 2, 5) == 1
    assert get_weight(g, 2, 6) == 2
    assert get_weight(g, 2, length(g)) == g.weights[2]
    f = Fraction(T("x"), T("y"))
    g2 = G([T("a"), f, NL])
    for i in range(1, 1 + length(f) + 1):
        assert get_weight(g2, 2, i) == 0
    assert get_weight(g2, 2, length(g2)) == 1
