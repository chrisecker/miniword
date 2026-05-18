from .boxes import Box, TextBox, NewlineBox, Row, select_i_by_x, \
    select_i_by_y, get_text
from .testdevice import TESTDEVICE
from ..core.units import mm, cm, pt



class ForceBreakBox(NewlineBox):
    """Sentinel box for a forced line break (BR texel)."""


class Page(Box):
    pagenum       = 0
    margin        = (2 * cm,) * 4  # XXX
    page          = 0
    height        = 0
    decorations   = ()
    footnote_rows = ()
    restartmemo   = None

    def __init__(self, rowdata, geometry, device=TESTDEVICE):
        if device is not None:
            self.device = device
        self.rows = rowdata[:]
        n = 0
        for x, y, row in rowdata:
            n += len(row)
        self.length = n
        self.width, self.height = geometry

    def __len__(self):
        return self.length

    def adjust(self, pagenum):
        """Update page properties that do not affect layout.

        Currently used only for the page number. Could also be used
        for section numbering and list numbering (as long as layout is
        unaffected).
        """
        self.pagenum = pagenum

    def draw_background(self, x, y, gc):
        """Fill the page with its background color."""
        self.device.fill_rect(x, y, self.width, self.height, 'white', gc)
        self.draw_decorations(x, y, gc)

    def draw_decorations(self, x, y, gc):
        for dx, dy, dw, dh, color in self.decorations:
            self.device.fill_rect(x + dx, y + dy, dw, dh, color, gc)

    def draw_footnotes(self, x, y, gc):
        if not self.footnote_rows:
            return
        x0, y0, _ = self.footnote_rows[0]
        sep_y = y0 - 4   # 4pt gap above the line
        self.device.draw_line(x + x0, y + sep_y,
                              x + x0 + self.width * 0.3, y + sep_y,
                              0.5, gc)
        for x_, y_, row in self.footnote_rows:
            row.draw(x + x_, y + y_, gc)

    def draw(self, x, y, gc):
        Box.draw(self, x, y, gc)
        self.device.draw_rect(x, y, self.width, self.height, gc)
        margin = self.margin
        self.device.set_style({}, gc)
        self.device.draw_text(
            "Page %i" % self.pagenum,
            x + margin[3], y + self.height - margin[2], gc)
        self.draw_footnotes(x, y, gc)

    def draw_for_print(self, x, y, gc):
        Box.draw(self, x, y, gc)
        self.draw_footnotes(x, y, gc)

    def iter_boxes(self, i, x, y):
        j1 = i
        for x_, y_, row in self.rows:
            j2 = j1 + len(row)
            yield j1, j2, x + x_, y + y_, row
            j1 = j2

    def iter_fnboxes(self, i, x, y):
        j1 = i
        for x_, y_, row in self.footnote_rows:
            j2 = j1 + len(row)
            yield j1, j2, x + x_, y + y_, row
            j1 = j2

    def compute_fnindex(self, x, y):
        """Return local footnote flow index at page-relative (x, y), or None."""
        j = 0
        for x_, y_, row in self.footnote_rows:
            if y_ <= y < y_ + row.height + row.depth:
                return j + row.get_index(x - x_, row.height)
            j += len(row)
        return None

    def get_flow(self, x, y):
        if not self.footnote_rows:
            return 0
        # XXX wir brauchen eine footnote-Box!
        return 0 # XXX
        

    def draw_mdcursor(self, i, x, y, dc, style):
        for j1, j2, rx, ry, row in self.iter_fnboxes(0, x, y):
            if j1 <= i < j2:
                row.draw_cursor(i - j1, rx, ry, dc, style)
                return

    def draw_mdselection(self, i1, i2, x, y, dc):
        for j1, j2, rx, ry, row in self.iter_fnboxes(0, x, y):
            if j2 > i1 and j1 < i2:
                row.draw_selection(max(i1, j1) - j1, min(i2, j2) - j1, rx, ry, dc)

    def get_index(self, x, y):
        items = self.iter_boxes(0, 0, 0)
        return select_i_by_y(x, y, items)
    

def show_page(page):
    """Dump the contents of a page."""
    memo = page.restartmemo
    if memo:
        print("RestartMemo present")
        for x, y, row in memo.rows:
            print("--", x, y, get_text(row))

    for i1, i2, x, y, row in page.iter_boxes(0, 0, 0):
        print(x, y, repr(get_text(row)))
    print()

