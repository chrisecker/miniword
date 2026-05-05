from ..textmodel.texeltree import iter_childs, length, provides_childs, Group


def find_texel(tree, texel, i):
    """Search for texel in tree at position i.

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
        raise IndexError("Position %i out of bounds for target texel" % i)

    if not provides_childs(tree):
        raise IndexError("Depth %i not reachable at position %i (reached leaf)"
                         % (depth, i))

    for j1, j2, child in iter_childs(tree):
        if j1 <= i < j2:
            return get_texel(child, i - j1, depth - 1)

    raise IndexError("No child covers position %i at remaining depth %i"
                     % (i, depth))


def transform(tree, i, d, fun):
    """Apply fun to the node at position i and depth d."""
    if d == 0:
        return fun(tree)
    if not provides_childs(tree):
        raise IndexError("Can't descend into texel %s" % repr(tree))
    r = []
    for j1, j2, child in iter_childs(tree):
        if j1 <= i < j2:
            r.append(transform(child, i - j1, d - 1, fun))
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



def updated(default, *styles):
    """Merges dicts by updating from left to right."""    
    r = default.copy()
    for s in styles:
        r.update(s)
    return r


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_00():
    "selection not touching any separator is unchanged"
    from ..textmodel.textmodel import TextModel
    from ..textmodel.texeltree import Fraction, Text
    m = TextModel()
    m.texel = Fraction(Text("a"), Text("b"))
    assert m.expand_range(1, 2) == (1, 2)


def test_01():
    "selection spanning a separator expands to full container"
    from ..textmodel.textmodel import TextModel
    from ..textmodel.texeltree import Fraction, Text, length
    m = TextModel()
    m.texel = Fraction(Text("a"), Text("b"))
    assert m.expand_range(1, 4) == (0, length(m.texel))


def test_02():
    "selection touching left separator expands to full container"
    from ..textmodel.textmodel import TextModel
    from ..textmodel.texeltree import Fraction, Text, length
    m = TextModel()
    m.texel = Fraction(Text("a"), Text("b"))
    assert m.expand_range(0, 1) == (0, length(m.texel))


def test_03():
    "nested container: inner separator expands to full inner container"
    from ..textmodel.textmodel import TextModel
    from ..textmodel.texeltree import Fraction, Text
    m = TextModel()
    inner = Fraction(Text("x"), Text("y"))
    m.texel = Fraction(inner, Text("z"))
    assert m.expand_range(2, 5) == (1, 6)


def test_04():
    "nested container: selection touching outer separator expands to full outer"
    from ..textmodel.textmodel import TextModel
    from ..textmodel.texeltree import Fraction, Text, length
    m = TextModel()
    inner = Fraction(Text("x"), Text("y"))
    m.texel = Fraction(inner, Text("z"))
    assert m.expand_range(2, 7) == (0, length(m.texel))


def test_05():
    "get_path"
    from ..textmodel.texeltree import G, T, Fraction
    tree = G([Fraction(T('A'), T('B'))])
    path = get_path(tree, 1)
    assert len(path) == 3
    assert path[0] == (0, 5, tree)
    assert path[1][2].is_container
    assert path[2] == (1, 2, path[1][2].childs[1])


def test_06():
    "get_texel"
    from ..textmodel.texeltree import G, T, Fraction
    a = T('A')
    b = T('B')
    f = Fraction(a, b)
    assert get_texel(f, 0, 0) is f
    assert get_texel(f, 1, 1) is a
    assert get_texel(f, 3, 1) is b
    assert get_texel(f, 0, 1) is f.childs[0]
    assert get_texel(f, 2, 1) is f.childs[2]
    assert get_texel(f, 4, 1) is f.childs[4]


def test_07():
    "find_texel"
    from ..textmodel.texeltree import G, T, Fraction
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


def test_08():
    "transform"
    from ..textmodel.texeltree import G, T, Fraction, get_text
    a = T('A')
    b = T('B')
    c = T('C')
    x = T('X')
    f = Fraction(a, b)
    replace = lambda old: x
    assert find_texel(f, a, 1) == (1, 2, 1)
    assert get_text(transform(f, 1, 1, replace)) == '\nX\nB\n'
    assert get_text(transform(f, 3, 1, replace)) == '\nA\nX\n'
    tree = G([f, c])
    assert get_text(transform(tree, 1, 2, replace)) == '\nX\nB\nC'
    try:
        transform(tree, 1, 3, replace)
        assert False
    except IndexError:
        pass
    # separators can also be replaced
    assert get_text(transform(f, 0, 1, replace)) == 'XA\nB\n'
