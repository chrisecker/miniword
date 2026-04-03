from copy import copy

from .textmodel.texeltree import Text, Container, NewLine, length, as_style, \
    NULL_TEXEL

"""
Terms:
- entry = (texel, style-Dict)
- cell = Cell-Object
- coord = (row, col)

"""


class Cell:
    """A data wrapper for a logical grid position with default attributes.

    Cell ist mutable, however we are not allowed to change content
    which is a texel. Texels are always immutable.

    """
    DEFAULTS = {
        'border_left':   'thin',
        'border_right':  'thin',
        'border_top':    'thin',
        'border_bottom': 'thin',
        'valign':        'top',
        'cell_bgcolor':   None
    }

    def __init__(self, content, parstyle):
        self.content = content
        # NOTE: we copy parstyle so we can make changes without
        # violating the immutability of the source dict.
        self.parstyle = parstyle.copy()

    def get_attr(self, key):
        """Returns value from style or fallback to default."""
        return self.parstyle.get(key, self.DEFAULTS.get(key))

    def set_attributes(self, **kwds):
        """Updates style dictionary inplace."""
        self.parstyle.update(kwds)

    @property
    def border_left(self):
        return self.get_attr('border_left')
    @property
    def border_right(self):
        return self.get_attr('border_right')
    @property
    def border_top(self):
        return self.get_attr('border_top')
    @property
    def border_bottom(self):
        return self.get_attr('border_bottom')
    @property
    def valign(self):
        return self.get_attr('valign')
    @property
    def cell_bgcolor(self):
        return self.get_attr('cell_bgcolor')

def dump_cells(cells):
    print("cells:", len(cells), len(cells[0]))
    i = 0
    for row in cells:
        j = 0
        for cell in row:
            print(i, j, cell.content, cell.parstyle)
            j += 1
        i += 1
            
    
class Separator(NewLine):
    weights = (0, 1, 0)
    text = '\n'
SEP = Separator()


class Table(Container):
    def __init__(self, *entries, ncols=1, col_widths=None, row_heights=None,
                 nheader=0, breaklevel=1, ):
        """
        Table implementation based on TexelTree.
        cells: list of (content_str, style_dict)
        """
        self.ncols = ncols
        self.col_widths = col_widths
        self.row_heights = row_heights
        self.nheader = nheader
        self.breaklevel = breaklevel
        
        # First child: Anchor separator (i=0) for cursor separation
        childs = [Separator({})] 
        
        # Following: Pairs of Content and Separator
        for texel, parstyle in entries:
            childs.extend([texel, SEP.set_parstyle(parstyle)])

        self.childs = childs
        self.compute_weights()

        # nrows is not part of the file format. However it is
        # convenient.
        self.nrows = len(entries)//ncols


    def set_col_widths(self, value):
        t = copy(self)
        t.col_widths = value
        return t

    def set_row_heights(self, value):
        t = copy(self)
        t.row_heights = value
        return t

    def set_nheader(self, value):
        t = copy(self)
        t.nheader = value
        return t

    def set_breaklevel(self, value):
        t = copy(self)
        t.breaklevel = value
        return t

    def get_cells(self):
        """
        Transforms childs[1:] into a mutable Matrix: List[List[Cell]].
        """
        childs = self.childs
        # Group into pairs (Entry)
        l = [Cell(childs[i], childs[i+1].parstyle) 
             for i in range(1, len(childs), 2)]
        # Chunk into rows
        n = len(l)
        ncols = self.ncols
        return [l[i:i+ncols] 
                for i in range(0, n, ncols)]

    def get_coord(self, i):
        """
        Resolves linear index i to (row, col) coordinates.
        """
        if i < 1:
            raise IndexError("Not a cell index: %i" % i)
        if i >= length(self):
            raise IndexError("Not a cell index: %i" % i)
        
        i2 = 0
        for k, child in enumerate(self.childs):
            i1 = i2
            i2 += length(child)
            
            if i1 <= i < i2:
                if k == 0: 
                    return 0, 0 # Anchor separator (before first cell)
                
                # Each cell consists of two texels (Content, Separator) starting at k=1
                # k=1,2 -> Cell 0 | k=3,4 -> Cell 1 | k=5,6 -> Cell 2
                cell_idx = (k - 1) // 2
                row = cell_idx // self.ncols
                col = cell_idx % self.ncols
                return row, col

    def get_rect(self, i1, i2):
        """Returns r1, c1, r2, c2 where (r1, c1) is the top left
        coord and (r2, c2) the bottom right coordinate of the
        rectangle connecting the cells described by i1 and i2).

        When bot indices are in the same cell, (r2, c2) == (r1, c1).
        """
        r1, c1 = self.get_coord(i1)
        r2, c2 = self.get_coord(i2)
        r1, r2 = sorted([r1, r2])
        c1, c2 = sorted([c1, c2])
        return r1, c1, r2, c2
    
    def get_cell_range(self, r1, c1, r2, c2):
        """Return (i_start, i_end) covering all cells in the rectangle
        (r1, c1)..(r2, c2), relative to the start of this Table texel."""
        start_idx = r1 * self.ncols + c1
        end_idx   = r2 * self.ncols + c2
        cum = 0
        i_start = i_end = None
        for k, child in enumerate(self.childs):
            if k == 2 * start_idx + 1:
                i_start = cum
            cum += length(child)
            if k == 2 * end_idx + 2:
                i_end = cum
        return i_start, i_end

    def set_cellattr(self, r1, c1, r2, c2, **kwds):
        r1, r2 = sorted([r1, r2])
        c1, c2 = sorted([c1, c2])
        cells = self.get_cells()
        for r in range(r1, r2+1):
            for c in range(c1, c2+1):
                cells[r][c].set_attributes(**kwds)
        return from_cells(cells)

    def remove_cols(self, i, n):
        if i+n > self.ncols:
            raise IndexError(i+n)
        
        cells = self.get_cells()
        new = []
        for row in cells:
            new.append(row[:i]+row[i+n:])
        return from_cells(new)

    def insert_cols(self, i, n):
        cells = self.get_cells()
        new = []
        for row in cells:
            part = [Cell(NULL_TEXEL, {}) for j in range(n)]            
            new.append(row[:i]+part+row[i:])
        return from_cells(new)

    def remove_rows(self, i, n):
        cells = self.get_cells()
        return from_cells(cells[:i]+cells[i+n:])         

    def insert_rows(self, i, n):
        cells = self.get_cells()
        m = self.ncols
        # NOTE: We use the same cell to fill all empty positions. This
        # is allowed here because cells and rows are destroyed
        # immediately afterward. Texels are immutable and can
        # therefore appear repeatedly in the TexelTree.
        new = [[Cell(NULL_TEXEL, {})]*m]*n
        return from_cells(cells[:i]+new+cells[i:])
        
        

    
def from_cells(cells, col_widths=None, row_heights=None, nheader=0, breaklevel=1):
    """
    Reconstructs a Table from the mutable Matrix of cells.
    """
    ncols = len(cells[0])
    entries = []
    for row in cells:
        for cell in row:
            entries.append((cell.content, as_style(cell.parstyle)))
    return Table(*entries, ncols=ncols)


def from_strings(rows, parstyle={}):
    """
    Creates a Table from a nested list of strings with a default parstyle.
    """
    ncols = len(rows[0]) if rows and rows[0] else 0
    entries = [(Text(s), parstyle) for row in rows for s in row]
    return Table(*entries, ncols=ncols)



def empty_table(rows, cols, parstyle={}):
    """
    Initializes a new Table grid with empty content strings.
    """
    cells = [(NULL_TEXEL, parstyle)] * (rows * cols)
    return Table(*cells, ncols=cols)

def copy_rect(cells, r1, r2, c1, c2):
    """
    Extracts a rectangular sub-matrix using coordinate slicing.
    """
    return [row[c1:c2+1] for row in cells[r1:r2+1]]


def test_00():
    """from_strings"""
    t = from_strings([["a", "b"], ["c", "d"]])
    assert t.ncols == 2
    assert len(t.childs) == 9
    assert length(t) == 9


def test_01():
    """get_cells, from_cells"""
    from .textmodel.texeltree import get_text
    t1 = from_strings([["a", "b"], ["c", "d"]])
    cells = t1.get_cells()
    assert len(cells) == 2
    assert len(cells[0]) == 2
    t2 = from_cells(cells)
    assert t2.ncols == 2
    assert len(t2.childs) == 9
    assert length(t2) == 9
    assert get_text(t1) == get_text(t2)
    

def test_02():
    """set_cellattr"""
    t = from_strings([["a", "b"], ["c", "d"]])
    t2 = t.set_cellattr(0, 0, 0, 1, valign='center')
    cells = t2.get_cells()
    
    assert cells[0][0].get_attr('valign') == 'center'
    assert cells[0][1].get_attr('valign') == 'center'
    assert cells[1][0].get_attr('valign') == 'top'
    assert cells[1][1].get_attr('valign') == 'top'

def _text(cell):
    from .textmodel.texeltree import get_text
    return get_text(cell.content)


def test_03():
    """insert_cols"""
    t = from_strings([["a", "b"], ["c", "d"]])
    t2 = t.insert_cols(1, 1)
    assert t2.ncols == 3
    cells = t2.get_cells()
    assert _text(cells[0][0]) == 'a'
    assert length(cells[0][1].content) == 0
    assert _text(cells[0][2]) == 'b'
    assert _text(cells[1][0]) == 'c'
    assert length(cells[1][1].content) == 0
    assert _text(cells[1][2]) == 'd'


def test_04():
    """get_coord"""
    t = from_strings([["a", "b"], ["c", "d"]])
    # NOTE:
    #
    # The index i denotes cursor positions. Index i=1 means "left of
    # the first element". If the element is of length 1, i=2 means
    # "right of the first element". So the first cell occupies index
    # positions 1 and 2. Index position 3 goes in the second cell.
    #
    # For |a|b| / |c|d|:
    #  Anchor  a   Sep  b   Sep  c   Sep  d   Sep
    #    |     a    |   b    |   c    |   d    |
    #    0     1    2   3    4   5    6   7    8   

    try:
        t.get_coord(0)
        assert False
    except IndexError: pass
    assert t.get_coord(1) ==(0, 0)
    assert t.get_coord(2) ==(0, 0)
    assert t.get_coord(3) ==(0, 1)
    assert t.get_coord(4) ==(0, 1)
    assert t.get_coord(5) ==(1, 0)
    assert t.get_coord(6) ==(1, 0)
    assert t.get_coord(7) ==(1, 1)    
    assert t.get_coord(8) ==(1, 1)
    try:
        t.get_coord(9)
        assert False
    except IndexError: pass


def test_05():
    """remove_rows"""
    t = from_strings([["a", "b"], ["c", "d"], ["e", "f"]])
    t2 = t.remove_rows(1, 1)
    assert t2.nrows == 2
    assert t2.ncols == 2
    cells = t2.get_cells()
    assert _text(cells[0][0]) == 'a' and _text(cells[0][1]) == 'b'
    assert _text(cells[1][0]) == 'e' and _text(cells[1][1]) == 'f'


def test_06():
    """remove_cols"""
    t = from_strings([["a", "b", "c"], ["d", "e", "f"]])
    t2 = t.remove_cols(1, 1)
    assert t2.ncols == 2
    assert t2.nrows == 2
    cells = t2.get_cells()
    assert _text(cells[0][0]) == 'a' and _text(cells[0][1]) == 'c'
    assert _text(cells[1][0]) == 'd' and _text(cells[1][1]) == 'f'

    t = from_strings([["a", "b"], ["c", "d"]])
    try:
        t.remove_cols(1, 2)
        assert False
    except IndexError:
        pass


def test_07():
    """insert_rows"""
    t = from_strings([["a", "b"], ["c", "d"]])
    t2 = t.insert_rows(1, 2)
    assert t2.nrows == 4
    assert t2.ncols == 2
    cells = t2.get_cells()
    assert _text(cells[0][0]) == 'a'
    assert length(cells[1][0].content) == 0
    assert length(cells[2][0].content) == 0
    assert _text(cells[3][0]) == 'c'

def test_08():
    """get_rect"""
    t = from_strings([["a", "b"], ["c", "d"]])
    assert t.get_rect(1, 1) == (0, 0, 0, 0)
    assert t.get_rect(1, 2) == (0, 0, 0, 0)
    assert t.get_rect(2, 2) == (0, 0, 0, 0)
    assert t.get_rect(2, 3) == (0, 0, 0, 1)
    assert t.get_rect(2, 4) == (0, 0, 0, 1)
    assert t.get_rect(2, 5) == (0, 0, 1, 0)
    assert t.get_rect(2, 6) == (0, 0, 1, 0)
    assert t.get_rect(2, 7) == (0, 0, 1, 1)


def test_09():
    """get_cell_range"""
    # 2x2 table: childs = [sep0, a, sep, b, sep, c, sep, d, sep]
    #            indices:   0    1   2   3   4   5   6   7   8
    t = from_strings([["a", "b"], ["c", "d"]])
    # single cell (0,0): content starts at 1, ends after sep at 3
    assert t.get_cell_range(0, 0, 0, 0) == (1, 3)
    # single cell (0,1)
    assert t.get_cell_range(0, 1, 0, 1) == (3, 5)
    # full first row (0,0)..(0,1)
    assert t.get_cell_range(0, 0, 0, 1) == (1, 5)
    # full table (0,0)..(1,1)
    assert t.get_cell_range(0, 0, 1, 1) == (1, 9)

