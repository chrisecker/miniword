from .boxes import Box, VBox, RowsBox, NewlineBox, Row, select_i_by_y, \
    get_text, draw_border
from .testdevice import TESTDEVICE
from ..core.units import mm, cm, pt
from ..core.document import settings_default
import datetime


def field_text(field, values):
    """Text of a header/footer field (kind, text). values: page, pages,
    title, author, date, chapter, section."""
    kind, text = field
    if kind == 'text':
        return text
    if kind == 'none':
        return ''
    if kind == 'page_pages':
        return '%s / %s' % (values['page'], values['pages'])
    return str(values[kind])


def header_footer(settings, values):
    """Header and footer texts [left, center, right] of page
    values['page']: empty on the first page if switched off, left and
    right swapped on even pages if mirrored."""
    page = values['page']
    if page == 1 and not settings['header_footer_first_page']:
        return ['', '', ''], ['', '', '']

    def texts(line):
        r = [field_text(settings[line + side], values)
             for side in ('_left', '_center', '_right')]
        if settings['header_footer_mirror'] and page % 2 == 0:
            r.reverse()
        return r
    return texts('header'), texts('footer')


class ForceBreakBox(NewlineBox):
    """Sentinel box for a forced line break (BR texel)."""


class FootnoteBox(RowsBox):
    """A column of footnote rows, optionally preceded by a separator line.

    Takes ready-made row data ((x, y, row), ...) plus height and
    decorations - e.g. from stack_rows - and doesn't stack rows itself.

    Like any box, its rows are positioned relative to its own top-left
    corner; the box's position on the page is carried separately (see
    Page.footnotebox, a (x, y, box) tuple).

    The separator is omitted when the footnote box fills the whole
    remaining page (no normal text above it).
    """

    def __init__(self, data, width, height, shadings=(), borders=(),
                 device=None, draw_separator=True):
        RowsBox.__init__(self, data, width, height, 0, (0, 0),
                         shadings, borders, device)
        self.draw_separator = draw_separator

    def draw(self, x, y, gc):
        if self.draw_separator:
            sep_y = y - 4   # 4pt gap above the line
            self.device.draw_line(x, sep_y, x + self.width * 0.3, sep_y,
                                   0.5, gc)
        RowsBox.draw(self, x, y, gc)


class Page(Box):
    pagenum       = 0
    margin        = (2 * cm,) * 4  # XXX
    page          = 0
    height        = 0
    shadings      = ()
    borders       = ()
    restartmemo   = None
    settings      = settings_default
    chapter       = ''  # running heads, see generate_pages
    section       = ''
    layout        = None  # set by Layout.append_page: the page count
    header_style  = {}    # basestyles 'header'/'footer', see generate_pages
    footer_style  = {}

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
        for dx, dy, dw, dh, color in self.shadings:
            self.device.fill_rect(x + dx, y + dy, dw, dh, color, gc)
        for dx, dy, dw, dh, style in self.borders:
            draw_border(self.device, x + dx, y + dy, dw, dh, style, gc)

    def draw_footnotes(self, x, y, gc):
        if self.footnotebox is not None:
            fx, fy, box = self.footnotebox
            box.draw(x + fx, y + fy, gc)

    def header_footer_texts(self, date=None):
        """Header and footer texts of this page, see header_footer."""
        if date is None:
            date = datetime.date.today().strftime('%x')
        settings = self.settings
        pages = len(self.layout.childs) if self.layout else self.pagenum
        values = dict(page=self.pagenum, pages=pages, date=date,
                      title=settings['title'], author=settings['author'],
                      chapter=self.chapter, section=self.section)
        return header_footer(settings, values)

    def draw_header_footer(self, x, y, gc):
        """Draw header and footer, vertically centered in the top and
        bottom margin; left/right at the margins, center on the page."""
        top, right, bottom, left = self.margin
        header, footer = self.header_footer_texts()
        for texts, middle, style in (
                (header, top / 2, self.header_style),
                (footer, self.height - bottom / 2, self.footer_style)):
            self.device.set_style(style, gc)
            for k, text in enumerate(texts):
                if not text:
                    continue
                w, h, d = self.device.measure(text, style)
                dx = (left, (self.width - w) / 2,
                      self.width - right - w)[k]
                self.device.draw_text(text, x + dx, y + middle - h / 2, gc)

    def _draw(self, x, y, gc):
        Box.draw(self, x, y, gc)
        self.draw_footnotes(x, y, gc)
        self.draw_header_footer(x, y, gc)

    def draw(self, x, y, gc):
        self._draw(x, y, gc)
        self.device.draw_rect(x, y, self.width, self.height, gc)

    def draw_for_print(self, x, y, gc):
        self._draw(x, y, gc)
        
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

