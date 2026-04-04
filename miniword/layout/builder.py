# -*- coding: utf-8 -*-


# The Builder monitors model changes and updates the layout. 



from ..textmodel.texeltree import length, NewLine, get_text, takeout
from ..wxtextview.builder import BuilderBase
from ..wxtextview.wxtextview import WXTextView
from ..wxtextview.boxes import VBox, get_text
from ..wxtextview import boxes
from ..wxtextview.rect import Rect

from .pagegen import show_page, RestartMemo, generate_pages, \
    restartmemo_from_settings
from ..core.units import cm, mm
from ..core.styles import updated
from .factory import Factory
from .cairodevice import CairoDevice

from copy import copy as shallow_copy
import wx
import threading
import queue
import time




DEBUG = False
def trace(fn):
    """Decorator: print method entry, exit and duration."""
    name = fn.__qualname__
    def wrapper(*args, **kwargs):
        if not DEBUG:
            return fn(*args, **kwargs)
        t0 = time.perf_counter()
        print(f">>> {name}")
        try:
            return fn(*args, **kwargs)
        finally:
            dt = time.perf_counter() - t0
            print(f"<<< {name}  ({dt*1000:.1f} ms)")
    wrapper.__name__ = fn.__name__
    return wrapper

NOOP = lambda: None

class Layout(VBox):
    """Simple single-column layout containing pages."""
    is_finished = False
    page_gap = 12  # visual gap between pages (screen only; PDF/print unaffected)

    def append_page(self, page):
        self.height += self.page_gap  # gap before every page, including the first
        self.childs.append(page)
        self.length += len(page)
        self.width   = max(self.width, page.width)
        self.height += page.height  # assumes a specific page geometry

    def iter_boxes(self, i, x, y):
        j1 = i
        y += self.page_gap  # initial gap before first page
        for child in self.childs:
            j2 = j1 + len(child)
            yield j1, j2, x, y, child
            y  += child.height + child.depth + self.page_gap
            j1  = j2

    def from_childs(self, l):
        assert False

    def create_group(self, l):
        assert False

    def draw_background(self, x, y, gc):
        """Fill the background of every visible page."""
        device = self.device
        for j1, j2, x1, y1, child in self.iter_boxes(0, x, y):
            if device.intersects(gc, Rect(x1, y1,
                                          x1 + child.width,
                                          y1 + child.height)):
                child.draw_background(x1, y1, gc)

    def get_text(self):
        # For debugging
        return boxes.get_text(self)[:-1]  # strip end marker


class Builder(BuilderBase):
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

    def __init__(self, model, factory):
        self.model   = model
        self._layout = Layout([], factory.device)
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
            self.buildto_finish()

    def build_step(self):
        """Advance the active update task by one step.

        Has no effect if the task is already finished.
        """
        if self.generator is None:
            return
        try:
            page = next(self.generator)
            self._layout.append_page(page)
            layout = self._layout
            rest_i, rest = self.rest_memo
            k2 = len(layout)
            while rest_i < k2 and rest:
                _ = rest.pop(0)
                rest_i += len(_)
            self.rest_memo = rest_i, rest

            state  = page.restartmemo
            if state is not None:
                if self.can_finish(state):
                    return self.finish()
        except StopIteration:
            return self.finish()

    def build_background(self):
        """One build step for the async loop: step + Yield + reschedule."""
        self.build_step()
        if self.generator is not None:
            wx.Yield()
            if self.generator is not None:
                wx.CallAfter(self.build_background)

    @trace
    def buildto_finish(self, callback=NOOP):
        layout = self._layout
        while not layout.is_finished:
            self.build_step()
            callback()

    @trace
    def buildto_index(self, i, callback=NOOP):
        layout = self._layout
        while len(layout) < i and not layout.is_finished:
            self.build_step()
            callback()

    @trace
    def buildto_page(self, i, callback=NOOP):
        layout = self._layout
        while len(layout.childs) < i + 1 and not layout.is_finished:
            self.build_step()
            callback()

    @trace
    def buildto_y(self, y, callback=NOOP):
        layout = self._layout
        while layout.height+layout.depth < y and not layout.is_finished:
            self.build_step()
            callback()
        
    def rebuild(self):
        """Rebuild the entire layout from i=0; nothing is reused."""
        if DEBUG: print("rebuild")
        self._layout = Layout([], self.factory.device)
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

        # Update counters
        self.adjust_pages()
        try:
            assert len(self._layout) == len(self.model)+1
        except:
            print("layout:", len(self._layout))
            print("model:", len(self.model))
            raise
        self._layout.is_finished = True
        self.dump_updatestats()

    def adjust_pages(self):
        # Used here solely to update page numbers.
        # The call is very fast (≈1 ms for moby), so it is safe to
        # run after every change.
        for i, page in enumerate(self._layout.childs):
            page.adjust(i + 1)

    def rebuild_range(self, i1, i2, delta):
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

        if not k1:
            # k1 is either None (empty layout) or 0 (first page)
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

        self._layout = Layout(pages_before, self.factory.device)
        self.start(state, i_rest, pages_rest)

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

        # Condition 2: page must start at the correct position
        if k2 != rest_i:
            return False

        # Condition 3: RestartMemo must have the same number of rows.
        # (Simple and fast, but not sufficient in the general case.)
        n1 = len(old_restartmemo.rows)
        n2 = len(state.rows)
        if n1 != n2:
            return False

        # Condition 4: RestartMemo must have the same length
        # (sufficient in the simple model here, but insufficient in
        # general.)
        n1 = old_restartmemo.get_length()
        n2 = state.get_length()
        if n1 != n2:
            return False

        # Condition 5: numbered-list counter state must match so that
        # reused rest pages carry the correct counter values.
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




class MyView(WXTextView):
    """Simple view for testing."""

    def create_builder(self):
        from ..core.styles import testsheet
        factory = Factory(testsheet, device=CairoDevice())
        builder = Builder(self.model, factory)
        return builder

    def set_index(self, index, extend=False, update=True):
        self.builder.device.reset_blink()
        WXTextView.set_index(self, index, extend, update)

    def iter_rows(self):
        for p1, p2, px, py, page in self.layout.iter_boxes(0, 0, 0):
            for r1, r2, rx, ry, row in page.iter_boxes(p1, px, py):
                yield r1, r2, rx, ry, row



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
    view  = MyView(frame, -1)
    view.model = model
    view.builder.device.zoom = 2
    frame.Show()

    if 1:
        from ..wxtextview import testing
        l = locals()
        l.update(globals())
        testing.pyshell(l)
    app.MainLoop()


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

    newpages = list(generate_pages(xtexel, i1, info, factory))
    assert len(newpages) > 0


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

    import styles
    styles.normal['space_after']        = 0.5 * cm
    styles.normal['first_line_indent']  = 0.8 * cm

    for i in findall(model, 'CHAPTER'):
        model.set_parstyle(i, dict(base='h0'))

    model.set_properties(0, 10, text_color='red')
    app   = wx.App(redirect=True)
    frame = wx.Frame(None)
    view  = MyView(frame, -1)
    view.model = model

    frame.Show()
    from inspector import Inspector
    inspector = Inspector(view, None)
    inspector.Show()

    if 1:
        from ..wxtextview import testing
        l = locals()
        l.update(globals())
        testing.pyshell(l)
    app.MainLoop()
    
