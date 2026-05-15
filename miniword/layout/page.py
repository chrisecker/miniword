from ..wxtextview.boxes import Box, TextBox, NewlineBox, Row, select_i_by_x, \
    select_i_by_y, get_text
from ..wxtextview.testdevice import TESTDEVICE
from ..core.units import mm, cm, pt



class ForceBreakBox(NewlineBox):
    """Sentinel box for a forced line break (BR texel)."""


class Page(Box):
    pagenum      = 0
    margin       = (2 * cm,) * 4  # XXX
    page         = 0
    height       = 0
    decorations  = ()
    restartmemo  = None

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

    def draw(self, x, y, gc):
        Box.draw(self, x, y, gc)
        self.device.draw_rect(x, y, self.width, self.height, gc)
        margin = self.margin
        self.device.set_style({}, gc)
        self.device.draw_text(
            "Page %i" % self.pagenum,
            x + margin[3], y + self.height - margin[2], gc)

    def draw_for_print(self, x, y, gc):
        Box.draw(self, x, y, gc)

    def iter_boxes(self, i, x, y):
        j1 = i
        for x_, y_, row in self.rows:
            j2 = j1 + len(row)
            yield j1, j2, x + x_, y + y_, row
            j1 = j2

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

