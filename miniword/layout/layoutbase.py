# -*- coding: utf-8 -*-


from .boxes import find_row, select_i_by_y, calc_length, Row



class LayoutBase:
    def __init__(self, childs):
        self.childs = childs
        self.layout()

    def __repr__(self):
        return self.__class__.__name__+repr(list(self.childs))

    def __len__(self):
        return self.length[0]

    def iter_childs(self):
        j1 = 0
        for child in self.childs:
            j2 = j1+len(child)
            yield j1, j2, child
                
    def iter_boxes(self, flow):
        # Default behavior: stack child boxes
        if flow != 0:
            # Assumpte: only one flow
            raise ValueError(flow)
        x = y = 0
        j1 = 0
        for child in self.childs:
            j2 = j1+len(child)
            yield j1, j2, x, y, child
            y += child.height+child.depth
            j1 = j2

    def layout(self):
        w0 = w1 = h0 = h1 = h2 = 0
        for j1, j2, x, y, child in self.iter_boxes(flow=0):
            w0 = min(w0, x)
            h0 = min(h0, y)
            w1 = max(w1, x+child.width)
            h1 = max(h1, y+child.height)
            h2 = max(h2, y+child.height+child.depth)
        self.width = w1
        self.height = h1
        self.depth = h2-h1
        self.length = [calc_length(self.childs)]
       
    def get_flow(self, x, y):
        # We try all flow number starting from flow=1 until iter_boxes
        # raises ValueError        
        flow = 1
        try:
            while True:
                for j1, j2, _x, _y, box in self.iter_boxes(flow):
                    if _x <= x < _x+box.width and \
                       _y<= y < _y+box.height+box.depth:
                        return flow
                flow += 1
        except ValueError:
            pass
        # No higher flows matched, so we return 0 (i.e. the main flow)
        return 0    

    def get_index(self, x, y, flow):
        items = self.iter_boxes(flow)
        # Note: selecting by y is what we need for continuos text. For
        # discrete pages selecting by x,y would be better.
        r = select_i_by_y(x, y, items)        
        if r is not None:
            return r
        # None of the childs contains xy!
        return 0
    
    def get_rect(self, i, flow):
        assert self.childs
        for j1, j2, x, y, child in self.iter_boxes(flow):
            if j1<=i<j2:
                return child.get_rect(i-j1, x, y)
        raise IndexError("Wrong index %i for flow %i"%(i, flow))
        
    def find_row(self, i, flow):
        if not 0 <= i < self.length[flow]:
            return None
        for j1, j2, x, y, child in self.iter_boxes(flow):
            if j1<=i<j2:
                deeper = find_row(child, i, j1, x, y)
                if deeper is not None:
                    return deeper
                if isinstance(child, Row):
                    return j1, j2, x, y, child
                return None
        return None

    def prev_row(self, i, flow):
        cur = self.find_row(i, flow)
        if cur is None:
            return None
        return self.find_row(cur[0]-1, flow)

    def next_row(self, i, flow):
        cur = self.find_row(i, flow)
        if cur is None:
            return None
        return self.find_row(cur[1], flow)
    
    def draw(self, dc):
        for j1, j2, x, y, child in self.iter_boxes(flow=0):
            child.draw(x, y, dc)
        
    def draw_cursor(self, i, flow, dc, style):
        for j1, j2, x, y, child in self.iter_boxes(flow):
            if j1<=i<j2:
                child.draw_cursor(i-j1, x, y, dc, style)
                return

    def draw_selection(self, i1, i2, flow, dc):
        for j1, j2, x, y, child in self.iter_boxes(flow):
            if i1 < j2 and j1< i2:
                child.draw_selection(i1-j1, i2-j1, x, y, dc)

    def draw_background(self, dc):
        pass


def test_00():
    "find_row, prev_row, next_row"
    from .boxes import NewlineBox, _create_testobjects

    b1, _ = _create_testobjects("01")
    b2, _ = _create_testobjects("34")
    row1 = Row([b1, NewlineBox()])   # len=3, positions 0..2
    row2 = Row([b2, NewlineBox()])   # len=3, positions 3..5
    layout = LayoutBase([row1, row2])

    assert layout.find_row(0, 0)[:2] == (0, 3)
    assert layout.find_row(2, 0)[:2] == (0, 3)
    assert layout.find_row(3, 0)[:2] == (3, 6)
    assert layout.find_row(5, 0)[:2] == (3, 6)
    assert layout.find_row(6, 0) is None

    assert layout.prev_row(0, 0) is None
    assert layout.prev_row(2, 0) is None
    assert layout.prev_row(3, 0)[:2] == (0, 3)
    assert layout.prev_row(5, 0)[:2] == (0, 3)

    assert layout.next_row(0, 0)[:2] == (3, 6)
    assert layout.next_row(2, 0)[:2] == (3, 6)
    assert layout.next_row(3, 0) is None
    assert layout.next_row(5, 0) is None
