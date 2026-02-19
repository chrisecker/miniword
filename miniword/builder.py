# -*- coding: utf-8 -*-


# The Builder monitors model changes and updates the layout. 



from .textmodel.texeltree import length, NewLine, get_text, takeout
from .wxtextview.builder import BuilderBase
from .wxtextview.wxtextview import WXTextView
from .wxtextview.boxes import VBox, get_text
from .wxtextview import boxes

from .pagegen import show_page, RestartMemo, generate_pages
from .styles import stylesheet, cm, mm, updated
from .factory import Factory
from .cairodevice import CairoDevice

from copy import copy as shallow_copy
import wx
import threading
import queue
import time




class PageGeometry:
    width  = 210 * mm
    height = 297 * mm
    margin = (2.5 * cm,) * 4  # TRBL — Top, Right, Bottom, Left


class Layout(VBox):
    """Simple single-column layout containing pages."""
    is_finished = False

    def append_page(self, page):
        self.childs.append(page)
        self.length += len(page)
        self.width   = max(self.width, page.width)
        self.height += page.height  # assumes a specific page geometry

    def from_childs(self, l):
        assert False

    def create_group(self, l):
        assert False

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
    waitfor_height and waitfor_page, both of which can be called from
    Update().
    """
    _layout    = None
    layout     = property(BuilderBase.get_layout)
    # Required by wxtextview:
    device     = property(lambda self: self.factory.device)
    stylesheet = property(lambda self: self.factory.stylesheet)
    rest_memo  = 0, ()
    # Stats for debugging:
    nbefore = 0
    nrest   = 0

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
        p = len(layout)
        self.generator = self.create_generator(
            texel, p, state, self.factory)

        if not len(self.model):
            # The text view is typically created with an empty model;
            # set_model is called later. We avoid a background task at
            # startup by finishing manually here.
            return self.waitfor_finish()

        # If a generator is already running this is redundant and will
        # cause one extra build_step call at the very end. Since
        # generator is set to None after finish, this has no effect.
        wx.CallAfter(self.build_step)
        # The caller may now produce pages itself via waitfor_xx, or
        # simply wait for them to be produced via CallAfter.

    def build_step(self, call_after=True):
        """Advance the active update task by one step.

        Results are appended to the layout. Checks whether the task
        can be finished; if not, schedules the next step via CallAfter
        (when call_after is True).

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
        if call_after:
            wx.Yield()
            wx.CallAfter(self.build_step)

    def waitfor_finish(self):
        layout = self._layout
        while not layout.is_finished:
            self.build_step(call_after=False)

    def waitfor_index(self, i):
        layout = self._layout
        while len(layout) < i and not layout.is_finished:
            self.build_step(call_after=False)
        wx.CallAfter(self.build_step)

    def waitfor_page(self, i):
        layout = self._layout
        while len(layout.childs) < i + 1 and not layout.is_finished:
            self.build_step(call_after=False)
        wx.CallAfter(self.build_step)

    def rebuild(self):
        """Rebuild the entire layout from i=0; nothing is reused."""
        self._layout = Layout([], self.factory.device)
        self.start(RestartMemo(), 0, ())

    def finish(self):
        """Clean up, append rest pages, update statistics."""
        rest_i, rest = self.rest_memo
        self.nrest = len(rest)
        if rest:
            for page in rest:
                print("finish: appending_rest page")
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
        self._layout.is_finished = True
        self.dump_updatestats()

    def adjust_pages(self):
        # Used here solely to update page numbers.
        # The call is very fast (≈1 ms for moby), so it is safe to
        # run after every change.
        for i, page in enumerate(self._layout.childs):
            page.adjust(i + 1)

    def rebuild_dirty(self, i1, i2, delta):
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
            pages_before = []
            state = RestartMemo()
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
        self.waitfor_index(i2 + delta + 1000)  # XXX

    def can_finish(self, state):
        """Update rest_memo and check whether the remaining pages can
        be reused without further reflow."""
        layout = self._layout
        rest_i, rest = self.rest_memo

        k2 = len(layout)
        if k2 >= len(self.model):
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

        return True

    def get_updatestats(self):
        n      = len(self._layout.childs)
        nbefore = self.nbefore
        nrest   = self.nrest
        return nbefore, n - nrest - nbefore, nrest

    def dump_updatestats(self):
        print("pages before %s, pages updated %s, rest %s" %
              self.get_updatestats())

    # --- Signal handlers ---

    def properties_changed(self, i1, i2):
        self.rebuild_dirty(i1, i2, 0)

    def inserted(self, i, n):
        self.rebuild_dirty(i, i, n)

    def removed(self, i, n):
        self.rebuild_dirty(i, i, -n)


class MyView(WXTextView):
    """Simple view for testing."""

    def create_builder(self):
        factory = Factory(stylesheet, device=CairoDevice())
        builder = Builder(self.model, factory)
        return builder

    def set_index(self, index, extend=False, update=True):
        self.builder.device.reset_blink()
        WXTextView.set_index(self, index, extend, update)

    def print(self):
        import printer
        printer.show_printdlg(self.builder.layout)

    def iter_rows(self):
        for p1, p2, px, py, page in self.layout.iter_boxes(0, 0, 0):
            for r1, r2, rx, ry, row in page.iter_boxes(p1, px, py):
                yield r1, r2, rx, ry, row

    def move_down(self, shift):
        index  = self.index
        layout = self.layout
        x, y   = layout.get_rect(index, 0, 0).items()[:2]
        for r1, r2, rx, ry, row in self.iter_rows():
            if ry > y:
                i = row.get_index(x - rx, row.height)
                return self.set_index(r1 + i, shift)

    def move_up(self, shift):
        index  = self.index
        layout = self.layout
        x, y   = layout.get_rect(index, 0, 0).items()[:2]
        prev   = None
        for r1, r2, rx, ry, row in self.iter_rows():
            if ry + row.height + row.depth >= y:
                if not prev:
                    return
                r1, r2, rx, ry, row = prev
                i = row.get_index(x - rx, row.height)
                return self.set_index(r1 + i, shift)
            prev = r1, r2, rx, ry, row

    def handle_action(self, action, shift=False):
        if action == 'move_down':
            self.move_down(shift)
        elif action == 'move_up':
            self.move_up(shift)
        else:
            return WXTextView.handle_action(self, action, shift)


def show_pages(layout):
    """Dump all pages in the layout."""
    for i, (i1, i2, page) in enumerate(layout.iter_childs()):
        print("Page", i + 1, "[%s, %s; %s]" %
              (i1, i2, i1 + length_lines(page.restartmemo.lines)))
        show_page(page)


def demo_00():
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
        from .inspector import Inspector
        inspector = Inspector(view, None)
        inspector.Show()
    if 1:
        from .wxtextview import testing
        l = locals()
        l.update(globals())
        testing.pyshell(l)
    app.MainLoop()


def test_01():
    "generate_pages"
    from einstein import get_einstein

    xtexel     = get_einstein()
    restartmemo = RestartMemo()
    factory    = Factory(stylesheet)
    if 1:
        i = 1
        i1 = i2 = 0
        for page in generate_pages(xtexel, 0, restartmemo, factory):
            i2 = i1 + len(page)
            print("Page", i, "[%i, %i]" % (i1, i2))
            show_page(page)
            i  += 1
            i2  = i1


def test_02():
    "restartmemo"
    from einstein import get_einstein

    info          = RestartMemo()
    info.geometry = (100, 10)
    info.border   = 1, 1, 1, 1

    xtexel  = get_einstein()
    factory = Factory(stylesheet)
    pages   = []
    i = i1 = i2 = 0
    for page in generate_pages(xtexel, 0, info, factory):
        i  += 1
        i2  = i1 + len(page)
        print("Page", i, "[%i, %i]" % (i1, i2))
        show_page(page)
        pages.append((i1, i2, page))
        i1 = i2

    for i, (i1, i2, page) in enumerate(pages):
        info = page.restartmemo
        if info:
            print(i, "n info:", len(info.rows), repr(page)[:40])
        else:
            print(i, "no info", repr(page)[:40])

    print(len(pages))
    i = 4
    i1, i2, p = pages[i - 1]
    info = p.restartmemo

    if 1:
        print("RestartMemo of page", i, ":",
              len(info.rows), "rows", repr(info.rows)[:40])
        for row in info.rows:
            print("info:", repr(row)[:40])

    print("Restarting from i1=", i1)

    newpages = []
    i1 = i2 = 0
    for page in generate_pages(xtexel, i1, info, factory):
        i2 = i1 + len(page)
        print("Page", i, "[%i, %i]" % (i1, i2))
        if 1:
            show_page(page)
        i1 = i2
        newpages.append(page)
        i += 1


def demo_01():
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
        from .wxtextview import testing
        l = locals()
        l.update(globals())
        testing.pyshell(l)
    app.MainLoop()
    
