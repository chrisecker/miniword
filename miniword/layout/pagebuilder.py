# -*- coding: utf-8 -*-


# The Builder monitors model changes and updates the layout. 


from ..core.units import cm, mm
from ..core.styles import updated
from . import boxes
from .boxes import VBox, select_i_by_xy, select_i_by_y
from .builderbase import BuilderBase
from .rect import Rect
from .pagegen import RestartMemo, generate_pages, restartmemo_from_settings
from .page import show_page
from .factory import Factory
from .layoutbase import LayoutBase
from .cairodevice import CairoDevice

import wx
import time




DEBUG = False
def trace(fn):
    """Decorator: print method entry, exit and duration."""
    name = fn.__qualname__
    def wrapper(*args, **kwargs):
        if not DEBUG:
            return fn(*args, **kwargs)
        t0 = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            dt = 1000*(time.perf_counter() - t0)
            if dt>20:
                print(f"<<< {name}  ({dt:.1f} ms)")
    wrapper.__name__ = fn.__name__
    return wrapper

NOOP = lambda: None



class Layout(LayoutBase):
    """Simple single-column layout containing pages."""
    is_finished = False
    page_gap = 12  # visual gap between pages (screen only; PDF/print unaffected)
    pages_per_row = 1

    def append_page(self, page):
        self.height += self.page_gap  # gap before every page, including the first
        self.childs.append(page)
        page.adjust(len(self.childs))
        self.length[0] += len(page)
        if page.footnotebox is not None:
            self.length[1] += len(page.footnotebox[-1])
        self.width   = max(self.width, page.width)
        self.height += page.height  # assumes a specific page geometry

    def layout(self):
        w0 = w1 = h0 = h1 = h2 = 0
        n0 = 0
        n1 = 0
        for j1, j2, x, y, child in self.iter_pages():
            w0 = min(w0, x)
            h0 = min(h0, y)
            w1 = max(w1, x+child.width)
            h1 = max(h1, y+child.height)
            h2 = max(h2, y+child.height+child.depth)
            n0 = j2
            if child.footnotebox is not None:
                n1 += len(child.footnotebox[-1])
            
        self.width = w1
        self.height = h1
        self.depth = h2-h1
        self.length = [n0, n1]
        
    def iter_pages(self):
        j1 = 0
        x = 0
        y = self.page_gap  # initial gap before first page
        for child in self.childs:
            j2 = j1 + len(child)
            yield j1, j2, x, y, child
            y  += child.height + child.depth + self.page_gap
            j1  = j2
        
    def iter_boxes(self, flow):
        if flow == 0:
            yield from self.iter_pages()
        else:
            j1 = 0
            for i1, i2, px, py, page in self.iter_pages():
                if page.footnotebox is None:
                    continue
                x, y, box = page.footnotebox
                j2 = j1+len(box)
                yield j1, j2, x+px, y+py, box
                j1 = j2

    def find_page(self, x, y):
        for j1, j2, x0, y0, page in self.iter_pages():
            if y >= y0 and y <= y0+page.height:
                return j1, j2, x0, y0, page
        raise ValueError("No page contains %f,%f"%(x,y))

    def get_flow(self, x, y):
        try:
            j1, j2, x0, y0, page = self.find_page(x, y)
        except ValueError:
            return 0 # Fallback!
        if page.footnotebox is None:
            return 0
        fx, fy, box = page.footnotebox
        if y-y0 > fy:
            return 1 # in footnote box
        return 0 # normal text
    
    def draw_background(self, gc):
        """Fill the background of every visible page."""
        for j1, j2, x1, y1, child in self.iter_pages():
            if child.device.intersects(
                    gc, Rect(x1, y1,
                             x1 + child.width,
                             y1 + child.height)):
                child.draw_background(x1, y1, gc)

    def get_text(self):
        # For debugging
        return boxes.get_text(self)[:-1]  # strip end marker

    def get_fntext(self):
        raise NotImplemented


class TwoPageLayout(Layout):
    """Two-column layout: pages are arranged in left/right pairs side by side."""
    page_gap_h = 20  # horizontal gap between the two pages of a pair
    pages_per_row = 2

    def append_page(self, page):
        n = len(self.childs)
        self.childs.append(page)
        page.adjust(n + 1)
        self.length[0] += len(page)
        if page.footnotebox is not None:
            self.length[1] += len(page.footnotebox[-1])
        self.width = max(self.width, page.width * 2 + self.page_gap_h)
        if n % 2 == 0:
            # Left page: starts a new row
            self.height += self.page_gap + page.height + page.depth
        else:
            # Right page: extend the row if it is taller than the left page
            left = self.childs[n - 1]
            self.height += max(0, page.height + page.depth
                                   - left.height - left.depth)

    def iter_pages(self):
        j1 = 0
        row_y = self.page_gap
        row_height = 0
        for k, child in enumerate(self.childs):
            j2 = j1 + len(child)
            if k % 2 == 0:
                if k > 0:
                    row_y += row_height + self.page_gap
                row_height = child.height + child.depth
                yield j1, j2, 0, row_y, child
            else:
                left = self.childs[k - 1]
                row_height = max(row_height, child.height + child.depth)
                yield j1, j2, left.width + self.page_gap_h, row_y, child
            j1 = j2

    def get_index(self, x, y, flow):
        # Override the base behaviour (select by y only), to enable
        # picking the correct page in a left/right pair.
        items = list(self.iter_boxes(flow))
        r = select_i_by_xy(x, y, items)
        if r is not None:
            return r
        return select_i_by_y(x, y, items)



class PageBuilder(BuilderBase):
    """The Builder operates in two phases:

    - Initial phase: pages are built synchronously; the GUI freezes.
    - Background phase: pages are built asynchronously.

    The initial phase ends when all of the following build thresholds
    are reached:
    - Total height reaches height_threshold.
    - Page count reaches pages_threshold.

    The phase also ends when the end of the document is reached.

    Synchronous building can be forced during the background phase via
    buildto_height and buildto_page, both of which can be called from
    Update().
    """
    _layout         = None
    layout          = property(BuilderBase.get_layout)
    # Required by wxtextview:
    device          = property(lambda self: self.factory.device)
    stylesheet      = property(lambda self: self.factory.stylesheet)
    rest_memo       = 0, ()
    _pending_range  = None  # (j1, j2) while inhibited, else None
    # Stats for debugging:
    nbefore  = 0
    nrest    = 0
    settings = {}  # document settings dict; set by DocumentView
    layout_class    = Layout

    def __init__(self, model, factory):
        BuilderBase.__init__(self, model)
        self._layout = self.layout_class([])
        self._layout.is_finished = True  # no generator yet: nothing to build
        self.factory = factory

    def clear_caches(self):
        self.device.clear_caches()
        self.factory.clear_caches()
        
    def get_device(self):
        return self.device

    def create_generator(self, texel, p, state, factory):
        # Override this method to use a different generator.
        return generate_pages(texel, p, state, factory)

    generator = None

    @trace
    def start(self, state, irest, rest):
        """Start the update task.

        Missing pages will be appended to the layout, using rest as a
        shortcut. A new layout must have been created before calling
        this, containing only the pages prior to the change.
        """
        layout = self._layout
        self.nbefore = len(layout.childs)

        self.rest_memo = irest, rest
        texel = self.model.get_xtexel()
        if self.generator is not None:
            if DEBUG: print("overriding old generator")
        p = len(layout)
        self.generator = self.create_generator(
            texel, p, state, self.factory)

        if not len(self.model):
            self.assure_finished()

    def build_step(self):
        """Advance the active update task by one step.

        Has no effect if the task is already finished.
        """
        if self.generator is None:
            return
        try:
            page = next(self.generator)
            layout = self._layout
            rest_i, rest = self.rest_memo
            k2 = len(layout)  # position before appending = start of new page
            state = page.restartmemo
            if state is not None and rest and k2 == rest_i:
                if self.can_finish(state):
                    return self.finish()
            layout.append_page(page)
            k2 = len(layout)
            while rest_i < k2 and rest:
                _ = rest.pop(0)
                rest_i += len(_)
            self.rest_memo = rest_i, rest
        except StopIteration:
            # The generator produced fresh pages for the entire remainder
            # of the document, so any leftover 'rest' (never matched via
            # can_finish) is stale and must be dropped, not appended.
            self.rest_memo = 0, ()
            return self.finish()

    def build_background(self):
        """One build step for the async loop: step + reschedule."""
        self.build_step()
        if self.generator is not None:
            wx.Yield() # Necessary!
            wx.CallAfter(self.build_background)

    @trace
    def assure_finished(self, callback=NOOP):
        layout = self._layout
        while not layout.is_finished:
            self.build_step()
            callback()

    def _row_complete(self):
        n = len(self._layout.childs)
        return n % self._layout.pages_per_row == 0

    @trace
    def assure_index(self, i, flow=0, callback=NOOP):
        layout = self._layout
        while not layout.is_finished:
            if layout.length[flow] >= i and self._row_complete():
                break
            self.build_step()
            callback()

    @trace
    def assure_page(self, i, callback=NOOP):
        layout = self._layout
        while not layout.is_finished:
            if len(layout.childs) >= i + 1 and self._row_complete():
                break
            self.build_step()
            callback()

    @trace
    def assure_y(self, y, callback=NOOP): # REPLACE THIS!
        layout = self._layout
        while not layout.is_finished:
            if layout.height + layout.depth >= y and self._row_complete():
                break
            self.build_step()
            callback()

    @trace
    def assure_rect(self, rect):
        layout = self._layout
        y = rect.y2
        while not layout.is_finished:
            if layout.height + layout.depth >= y and self._row_complete():
                break
            self.build_step()
                
    def rebuild(self):
        """Rebuild the entire layout from i=0; nothing is reused."""
        if DEBUG: print("rebuild")
        self._layout = self.layout_class([])
        self.start(restartmemo_from_settings(self.settings), 0, ())

    def finish(self):
        """Clean up, append rest pages, update statistics."""
        rest_i, rest = self.rest_memo
        self.nrest = len(rest)
        if rest:
            if DEBUG: print("finish: appending %d rest pages" % self.nrest)
            for page in rest:
                self._layout.append_page(page)
            self.rest_memo = 0, ()
        
        # Clean up
        self.generator = None

        try:
            assert len(self._layout) == len(self.model)+1
        except:
            print("layout:", len(self._layout))
            print("model:", len(self.model))
            raise
        self._layout.is_finished = True
        self.dump_updatestats()

    def rebuild_range(self, i1, i2, delta):
        """
        XXX bisher haben wir bei remove i1=i2 und delta<0
        gewählt. Logischer wäre aber i1, i2 alter Bereich, delta
        Änderung (wie bisher). Hier scheint die Interpretation i2>i1
        zu sein, passt also nicht zu der bisherigen Interpretation!
        """
        layout = self._layout
        q1 = q2 = k1 = k2 = state = None

        # Note: layout may be incomplete or even empty.
        for k, (j1, j2, page) in enumerate(layout.iter_childs()):
            if k1 is None and j2 >= i1:
                # First dirty page
                k1 = k
                q1 = j1
            if j1 > i2:
                # First page beyond the changed range
                k2 = k
                q2 = j1
                break

        if k1 is None or k1 == 0:
            # empty layout, or first page is dirty: no pages_before,
            # rebuild from the start
            pages_before = []
            state = restartmemo_from_settings(self.settings)
        else:
            # Shift start left to account for spillover
            pages = layout.childs
            while True:
                state = pages[k1].restartmemo
                if state and q1 + state.get_length() <= i1:
                    # i1 must not lie within the spillover region
                    break
                k1 -= 1
                assert k1 >= 0  # The first page must have a RestartMemo
                                # with length 0.
                q1 -= len(pages[k1])

            pages_before = layout.childs[:k1]

        if k2 is None:
            i_rest    = 0
            pages_rest = []
        elif layout.is_finished:
            pages_rest = layout.childs[k2:]
            i_rest     = q2 + delta
        else:
            i_rest, pages_rest = self.rest_memo
            i_rest += delta

        self._layout = self.layout_class(pages_before)
        self.start(state, i_rest, pages_rest)
        wx.CallAfter(self.build_background)

    def can_finish(self, state):
        """Update rest_memo and check whether the remaining pages can
        be reused without further reflow."""
        layout = self._layout
        rest_i, rest = self.rest_memo

        k2 = len(layout)
        if k2 > len(self.model):
            return True

        if not rest:
            # No rest pages remain but document is not finished.
            # Return False so that additional pages are generated.
            return False

        # Check whether we can short-circuit by reusing the rest.
        old_restartmemo = rest[0].restartmemo

        # Condition 1: page must have a RestartMemo
        if old_restartmemo is None:
            return False

        # Condition 2: RestartMemo must have the same number of rows.
        n1 = len(old_restartmemo.rows)
        n2 = len(state.rows)
        if n1 != n2:
            return False

        # Condition 3: RestartMemo must have the same length.
        n1 = old_restartmemo.get_length()
        n2 = state.get_length()
        if n1 != n2:
            return False

        # Condition 4: numbered-list counter state must match.
        if old_restartmemo.counters != state.counters:
            return False

        if DEBUG: print("can finish!")
        return True

    def get_updatestats(self):
        n      = len(self._layout.childs)
        nbefore = self.nbefore
        nrest   = self.nrest
        return nbefore, n - nrest - nbefore, nrest

    def dump_updatestats(self):
        if DEBUG: print("pages before %s, pages updated %s, rest %s" %
              self.get_updatestats())



def show_pages(layout):
    """Dump all pages in the layout."""
    for i, (i1, i2, page) in enumerate(layout.iter_childs()):
        print("Page", i + 1, "[%s, %s; %s]" %
              (i1, i2, i1 + length_lines(page.restartmemo.lines)))
        show_page(page)


def demo_00():
    global DEBUG; DEBUG = True
    from einstein import get_einstein_model
    model = get_einstein_model()

    model.set_properties(0, 15, color='red')
    model.set_parproperties(0, 1000, paragraph_type='list')
    app   = wx.App(redirect=True)
    frame = wx.Frame(None)
    
    from ..texteditor.editor import Editor
    editor = Editor(model)

    from ..layout.factory import Factory
    from ..core.styles import testsheet

    factory = Factory(testsheet, device=CairoDevice())
    builder = PageBuilder(model, factory)
    builder.rebuild()
    builder.build_background()

    from ..texteditor.textcanvas import TextCanvas
    canvas = TextCanvas(frame, model, builder, editor)
    editor.canvas = canvas
    
    frame.Show()
    #canvas.refresh() # XXX


    if 1:
        from ..ui import testing
        l = locals()
        l.update(globals())
        testing.pyshell(l)
    app.MainLoop()


def test_00():
    "TwoPageLayout: geometry, iter_boxes, rebuild"
    # Build a two-page layout from scratch
    layout = TwoPageLayout([])
    assert layout.height == 0
    assert layout.width  == 0

    # Fake page with known dimensions
    class FakePage:
        width = 100; height = 200; depth = 0; length = 10
        restartmemo = None
        footnotebox = None
        def __len__(self): return self.length
        def get_index(self, x, y): return 0

    p0, p1, p2, p3, p4 = [FakePage() for _ in range(5)]

    layout.append_page(p0)
    assert layout.height == layout.page_gap + 200    # one row
    assert layout.width  == 100 * 2 + layout.page_gap_h

    layout.append_page(p1)
    h_after_1 = layout.height
    assert h_after_1 == layout.page_gap + 200        # still one row
    assert layout.length[0] == 20

    layout.append_page(p2)
    assert layout.height == 2 * (layout.page_gap + 200)   # two rows

    layout.append_page(p3)
    assert layout.height == 2 * (layout.page_gap + 200)   # still two rows

    # iter_boxes: check x/y coordinates
    boxes = list(layout.iter_boxes(0))
    assert boxes[0][2] == 0                               # p0: x=0 (left)
    assert boxes[1][2] == 100 + layout.page_gap_h         # p1: x=left_width+gap
    assert boxes[0][3] == boxes[1][3]                     # p0, p1: same y (same row)
    assert boxes[2][3] > boxes[0][3]                     # p2: below p0/p1

    # Reconstruction from pages_before should give same geometry
    layout2 = TwoPageLayout([p0, p1, p2, p3])
    boxes2 = list(layout2.iter_boxes(0))
    assert len(boxes2) == 4
    assert boxes2[0][3] == boxes[0][3]
    assert boxes2[2][3] == boxes[2][3]

    # get_index: clicking on right page must return an index from page 1
    gap = layout.page_gap
    p1_x = 100 + layout.page_gap_h  # x-start of right page
    idx_left  = layout.get_index(50,        gap + 100, 0)  # mid of left page
    idx_right = layout.get_index(p1_x + 50, gap + 100, 0)  # mid of right page
    assert idx_left  < 10   # within p0 (length=10)
    assert idx_right >= 10  # within p1 (starts at offset 10)


def test_01():
    "generate_pages"
    from einstein import get_einstein
    from ..core.styles import testsheet

    xtexel     = get_einstein()
    restartmemo = RestartMemo()
    factory    = Factory(testsheet)
    pages = list(generate_pages(xtexel, 0, restartmemo, factory))
    assert len(pages) > 0


def test_02():
    "restartmemo"
    from einstein import get_einstein
    from ..core.styles import testsheet

    info          = RestartMemo()
    info.geometry = (100, 10)
    info.border   = 1, 1, 1, 1

    xtexel  = get_einstein()
    factory = Factory(testsheet)
    pages = []
    i1 = i2 = 0
    for page in generate_pages(xtexel, 0, info, factory):
        i2 = i1 + len(page)
        pages.append((i1, i2, page))
        i1 = i2

    assert len(pages) >= 4
    i1, i2, p = pages[3]
    info = p.restartmemo
    assert info is not None

    # build from page 3 on
    newpages = list(generate_pages(xtexel, i1, info, factory))
    assert len(newpages) > 0

def test_03():
    "relayout: abort condition reached after page 1"
    from einstein import get_einstein_model
    from ..core.styles import testsheet

    if wx.App.Get() is None:
        wx.App(False)

    model   = get_einstein_model()
    factory = Factory(testsheet)
    builder = PageBuilder(model + model, factory)
    builder.settings = {
        'paper':         'custom',
        'paper_width':   100,
        'paper_height':  20,
        'margin_top':    1,
        'margin_right':  1,
        'margin_bottom': 1,
        'margin_left':   1,
    }
    builder.rebuild()
    builder.assure_finished()
    n_pages = len(builder._layout.childs)
    assert n_pages >= 2, "Need multiple pages for this test"

    builder.rebuild_range(0, 1, delta=0)  # simulate change of first char
    builder.assure_finished()
    nbefore, n_rebuilt, nrest = builder.get_updatestats()
    assert nbefore == 0
    assert n_rebuilt == 1
    assert nrest == n_pages - 1
    

def demo_01():
    global DEBUG; DEBUG = True
    from moby import get_moby_model
    model = get_moby_model()

    def findall(model, pattern):
        text = model.get_text()
        i = -1
        while True:
            i = text.find(pattern, i + 1)
            if i < 0:
                return
            yield i

    from ..core import styles
    styles.normal['space_after']        = 0.5 * cm
    styles.normal['first_line_indent']  = 0.8 * cm

    for i in findall(model, 'CHAPTER'):
        model.set_parstyle(i, dict(base='h0'))

    model.set_properties(0, 10, text_color='red')

    app   = wx.App(redirect=True)
    frame = wx.Frame(None)
    
    from ..texteditor.editor import Editor
    editor = Editor(model)

    from ..layout.factory import Factory
    from ..core.styles import testsheet

    factory = Factory(testsheet, device=CairoDevice())
    builder = PageBuilder(model, factory)
    builder.rebuild()
    builder.build_background()

    from ..texteditor.textcanvas import TextCanvas
    canvas = TextCanvas(frame, model, builder, editor)
    editor.canvas = canvas
    
    frame.Show()
    canvas.refresh() # XXX

    if 1:
        from ..ui import testing
        l = locals()
        l.update(globals())
        testing.pyshell(l)
    app.MainLoop()
