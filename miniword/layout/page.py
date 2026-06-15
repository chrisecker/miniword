from .boxes import Box, VBox, NewlineBox, Row, select_i_by_y, get_text
from .testdevice import TESTDEVICE
from ..core.units import mm, cm, pt


class ForceBreakBox(NewlineBox):
    """Sentinel box for a forced line break (BR texel)."""


class FootnoteBox(VBox):
    """A column of footnote rows, optionally preceded by a separator line.

    Like any box, its rows are positioned relative to its own top-left
    corner; the box's position on the page is carried separately (see
    Page.footnotebox, a (x, y, box) tuple).

    The separator is omitted when the footnote box fills the whole
    remaining page (no normal text above it).
    """

    def __init__(self, rows, width, draw_separator=True, device=None):
        VBox.__init__(self, rows, device=device)
        self.width = max(self.width, width)
        self.draw_separator = draw_separator

    def draw(self, x, y, gc):
        if self.draw_separator:
            sep_y = y - 4   # 4pt gap above the line
            self.device.draw_line(x, sep_y, x + self.width * 0.3, sep_y,
                                   0.5, gc)
        VBox.draw(self, x, y, gc)


class Page(Box):
    pagenum       = 0
    margin        = (2 * cm,) * 4  # XXX
    page          = 0
    height        = 0
    decorations   = ()
    restartmemo   = None

    def __init__(self, rowdata, geometry, footnotebox=None, device=TESTDEVICE):
        if device is not None:
            self.device = device
        self.rows = rowdata[:]
        self.footnotebox = footnotebox
        n0 = 0
        for x, y, row in rowdata:
            n0 += len(row)
        n1 = len(footnotebox[2]) if footnotebox is not None else 0
        self.length = (n0, n1)
        self.width, self.height = geometry

    def __len__(self):
        return self.length[0]

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
        if self.footnotebox is not None:
            fx, fy, box = self.footnotebox
            box.draw(x + fx, y + fy, gc)

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
        # XXX Draw page-Number?

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

