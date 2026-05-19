# -*- coding: utf-8 -*-


import wx
import string

from ..textmodel import TextModel
from ..textmodel.styles import updated_style
from .textview import TextView
from .wxdevice import WxDevice, defaultstyle
from .testdevice import TESTDEVICE
from .simplelayout import Builder

from math import ceil
import pickle
import re


def slugify(text):
    """Convert heading text to a GitHub-compatible anchor ID."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    return text.strip('-')


def find_anchor_index(model, anchor_id):
    """Return the text index of the heading whose slug matches anchor_id, or None."""
    from ..textmodel.iterators import iter_paragraphs
    from ..textmodel.texeltree import NewLine, get_text
    _HEADINGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
    for i1, _i2, elems in iter_paragraphs(model.get_xtexel(), 0):
        nl = elems[-1]
        if not isinstance(nl, NewLine):
            continue
        if nl.parstyle.get('base', '') not in _HEADINGS:
            continue
        text = ''.join(get_text(e) for e in elems[:-1])
        if slugify(text) == anchor_id:
            return i1
    return None




class WxMixin(wx.ScrolledWindow):
    """wx-specific layer: rendering, scrolling, clipboard, events.

    Designed to be mixed with TextView (or a subclass) to produce a
    working wx widget without duplicating that code for every view type.
    """
    _scrollrate = 10, 10

    @property
    def scale(self):
        try:
            dpi = self.GetDPI().y
        except AttributeError:
            dpi = wx.ScreenDC().GetPPI()[1]
        return self.builder.get_device().get_scale(dpi)

    def __init__(self, parent, id=-1,
                 pos=wx.DefaultPosition, size=wx.DefaultSize, style=0):
        wx.ScrolledWindow.__init__(self, parent, id,
                                   pos, size,
                                   style | wx.WANTS_CHARS)
        try:
            wx.ScrolledWindow.DisableKeyboardScrolling(self)
        except AttributeError:
            pass
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: None)
        self.Bind(wx.EVT_CHAR, self.on_char)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_leftdown)
        self.Bind(wx.EVT_LEFT_UP, self.on_leftup)
        self.Bind(wx.EVT_LEFT_DCLICK, self.on_leftdclick)
        self.Bind(wx.EVT_MOTION, self.on_motion)
        self.Bind(wx.EVT_KILL_FOCUS, self.on_focus)
        self.Bind(wx.EVT_SET_FOCUS, self.on_focus)

        self.timer = wx.Timer(self)
        self.timer.Start(500)  # 2x per second
        self.Bind(wx.EVT_TIMER, self.on_blink)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.on_destroy)

        # key = (keycode, control, alt)
        self.actions = {
            (wx.WXK_ESCAPE, False, False): 'dump_info',
            (wx.WXK_ESCAPE, True,  False): 'dump_boxes',
            (wx.WXK_RIGHT,  True,  False): 'move_word_end',
            (wx.WXK_RIGHT,  False, False): 'move_right',
            (wx.WXK_LEFT,   True,  False): 'move_word_begin',
            (wx.WXK_LEFT,   False, False): 'move_left',
            (wx.WXK_DOWN,   True,  False): 'move_paragraph_end',
            (wx.WXK_DOWN,   False, False): 'move_down',
            (wx.WXK_UP,     True,  False): 'move_paragraph_begin',
            (wx.WXK_UP,     False, False): 'move_up',
            (wx.WXK_HOME,   False, False): 'move_line_start',
            (wx.WXK_END,    False, False): 'move_line_end',
            (wx.WXK_HOME,   True,  False): 'move_document_start',
            (wx.WXK_END,    True,  False): 'move_document_end',
            (wx.WXK_PAGEDOWN, False, False): 'move_page_down',
            (wx.WXK_PAGEUP,   False, False): 'move_page_up',
            (wx.WXK_PAGEUP,   True,  False): 'move_document_start',
            (wx.WXK_PAGEDOWN, True,  False): 'move_document_end',
            (wx.WXK_RETURN, False, False): 'insert_newline',
            (wx.WXK_BACK,   False, False): 'backspace',
            (wx.WXK_DELETE, False, False): 'delete',
            (3,  True, False): 'copy',
            (22, True, False): 'paste',
            (24, True, False): 'cut',
            (26, True, False): 'undo',
            (18, True, False): 'redo',
            (11, True, False): 'del_line_end',
            (wx.WXK_BACK, True, False): 'del_word_left',
            (1,  True, False): 'select_all',
            (9,  True, False): 'indent',
            (21, True, False): 'dedent',
        }

    # --- wx hooks (satisfy TextView abstract interface) ---

    def refresh(self):
        try:
            self.Refresh()
        except RuntimeError: # happens during close
            pass

    def get_client_size(self):
        return self.GetClientSize()

    def content_offset(self):
        return 0, 0

    def keep_cursor_on_screen(self):
        pass

    # --- timer / focus ---

    def on_blink(self, event):
        self.Refresh()

    def on_destroy(self, event):
        if self.timer.IsRunning():
            self.timer.Stop()
        event.Skip()

    def on_focus(self, event):
        self.Refresh()

    def on_size(self, event):
        self.keep_cursor_on_screen()

    # --- keyboard ---

    def on_char(self, event):
        if self.editor.on_key(event.GetKeyCode(), event):
            return
        keycode = event.GetKeyCode()
        ukey = event.GetUnicodeKey()
        ctrl = event.ControlDown()
        shift = event.ShiftDown()
        alt = event.AltDown()
        action = self.actions.get((keycode, ctrl, alt))

        if action is not None:
            self.handle_action(action, shift)
            return

        # Ctrl-Sequences are used for menu shortcuts -> Skip the event
        # so it is handled by wx. 
        if ctrl and not alt:
            # NOTE: AltGr triggers Ctrl in wx and is used only for
            # text here. We therefore have to exclude this case.
            event.Skip()
            return

        if ukey != wx.WXK_NONE:
            self.type_char(chr(ukey))
        else:
            event.Skip()
        
    # --- clipboard ---
    
    def to_clipboard(self, textmodel):
        for i in range(2):
            # loop is a hack to make clipboard work reliably under linux
            text = textmodel.get_text()
            plain = wx.TextDataObject()
            plain.SetText(text)
            pickled = wx.CustomDataObject("pytextmodel")
            pickled.SetData(pickle.dumps(textmodel))
            data = wx.DataObjectComposite()
            data.Add(pickled, preferred=True)
            data.Add(plain)
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(data)
                wx.TheClipboard.Flush()
                wx.TheClipboard.Close()
                self._clipboard_data = data  # prevent gc of collecting data

    def read_clipboard(self):
        if wx.TheClipboard.IsOpened():
            return
        if not wx.TheClipboard.Open():
            return None
        pickled = wx.CustomDataObject("pytextmodel")
        plain = wx.TextDataObject()
        textmodel = None
        if wx.TheClipboard.GetData(pickled):
            textmodel = pickle.loads(pickled.GetData())
        elif wx.TheClipboard.GetData(plain):
            textmodel = self._TextModel(plain.GetText())
        wx.TheClipboard.Close()
        return textmodel

    # --- mouse ---

    def on_motion(self, event):
        if self.editor.on_motion(event):
            return
        if not event.LeftIsDown():
            x, y = self.window_to_content(event.Position)
            i = self.compute_index(x, y)
            href = ''
            if i is not None:
                href = self.model.get_style(max(0, i - 1)).get('href', '')
            cursor = wx.CURSOR_HAND if href else wx.CURSOR_IBEAM
            self.SetCursor(wx.Cursor(cursor))
            return event.Skip()
        x, y = self.window_to_content(event.Position)
        i = self.layout.get_index(x, y)
        if i is not None:
            self.set_index(i, extend=True)

    def on_leftdown(self, event):
        if self.editor.on_leftdown(event):
            return
        x, y = self.window_to_content(event.Position)
        i = self.compute_index(x, y)
        if i is not None:
            if event.ControlDown():
                style = self.model.get_style(max(0, i - 1))
                href = style.get('href', '')
                if href:
                    if href.startswith('#'):
                        target = find_anchor_index(self.model, href[1:])
                        if target is not None:
                            self.set_index(target)
                    else:
                        import webbrowser
                        webbrowser.open(href)
                    self.SetFocus()
                    return
            self.set_index(i, extend=event.ShiftDown())
        self.SetFocus()

    def on_leftup(self, event):
        if self.editor.on_leftup(event):
            self.SetCursor(wx.Cursor(wx.CURSOR_IBEAM))

    def on_leftdclick(self, event):
        if self.try_install_click_editor():
            return
        x, y = self.window_to_content(event.Position)
        self.select_word(x, y)
        self.SetFocus()

            
    # --- painting ---

    def on_paint(self, event):
        self.ensure_viewport()
        self._update_scroll()
        self.keep_cursor_on_screen()

        pdc = wx.PaintDC(self)
        pdc.SetAxisOrientation(True, False)
        device = self.builder.get_device()
        if device.buffering:
            dc = wx.BufferedDC(pdc)
            if not dc.IsOk():
                return
        else:
            dc = pdc

        spx, spy = self.CalcScrolledPosition((0, 0))
        ox, oy   = self.content_offset()
        px, py   = spx + ox, spy + oy

        dc.SetBackgroundMode(wx.SOLID)
        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.Clear()
        region = self.GetUpdateRegion()
        rx, ry, rw, rh = region.Box
        dc.SetClippingRegion(rx - 1, ry - 1, rw + 2, rh + 2)
        painter = device.create_painter(dc, origin=(px, py))

        self.draw(painter)
        dc = None
        painter = None

    def has_focus(self):
        return wx.Window.FindFocus() is self and self.index <= len(self.layout)

    # --- scroll ---

    def _update_scroll(self):
        layout = self.layout
        scale = self.scale
        w = int(layout.width * scale)
        h = int(layout.height * scale)
        vw, vh = self.GetVirtualSize()
        if vw == w and vh == h:
            return
        # While rebuilding, never shrink the virtual size.
        if not getattr(self.layout, 'is_finished', True):
            w = max(w, vw)
            h = max(h, vh)
        if vw == w and vh == h:
            return
        self.SetVirtualSize((w, h))
        self.SetScrollRate(*self._scrollrate)

    def adjust_viewport(self):
        layout = self.layout
        scale = self.scale

        if self.index > len(layout):
            return  # layout not yet rebuilt to cursor position
        r = layout.get_rect(self.index, 0, 0)

        x1 = r.x1 * scale
        y1 = r.y1 * scale
        x2 = r.x2 * scale
        y2 = r.y2 * scale

        fw, fh = self._scrollrate
        width, height = self.GetClientSize()
        firstcol, firstrow = self.GetViewStart()

        vx = firstcol * fw
        vy = firstrow * fh

        if y1 <= vy:
            vy = y1
            firstrow = int(vy / fh)
        elif y2 > vy + height:
            vy = y2 - height
            firstrow = ceil(vy / float(fh))

        if x1 <= vx:
            vx = x1
            firstcol = int(vx / fw)
        elif x2 > vx + width:
            vx = x2 - width
            firstcol = ceil(vx / float(fh))

        if (firstcol, firstrow) != self.GetViewStart():
            self.Scroll(firstcol, firstrow)

    def window_to_content(self, pos):
        """Calculates content coordinates from window-coordinates,
        accounts for scroll position."""
        scale = self.scale
        x, y = self.CalcUnscrolledPosition(pos)
        ox, oy = self.content_offset()
        return (x - ox) / scale, (y - oy) / scale

    # --- zoom ---

    def get_zoom(self):
        return self.builder.get_device().zoom

    def set_zoom(self, zoom):
        self.builder.get_device().zoom = zoom
        self.refresh()


class WXTextView(WxMixin, TextView):

    def __init__(self, parent, id=-1,
                 pos=wx.DefaultPosition, size=wx.DefaultSize, style=0):
        WxMixin.__init__(self, parent, id, pos, size, style)
        TextView.__init__(self)

    def create_builder(self):
        return Builder(
            self.model,
            device=WxDevice(),
            maxw=self._maxw)






def init_testing(redirect=True):
    from .textview import testtext
    app = wx.App(redirect=redirect)
    model = TextModel(testtext)
    model.set_properties(15, 24, fontsize=14)
    model.set_properties(249, 269, fontsize=14)

    frame = wx.Frame(None)
    win = wx.Panel(frame)
    view = WXTextView(win)
    view.model = model
    assert view.layout is not None
    box = wx.BoxSizer(wx.VERTICAL)
    box.Add(view, 1, wx.ALL | wx.GROW, 1)
    win.SetSizer(box)
    win.SetAutoLayout(True)
    frame.Show()
    return locals()

def test_02():
    "setting cursor & selection"
    ns = init_testing(redirect=True)
    view = ns['view']
    view.cursor = 5
    view.selection = 3, 6
    return ns

def test_03():
    "inserting text"
    ns = init_testing(redirect=False)
    model = ns['model']
    view = ns['view']
    assert view.layout is not None

    model.set_properties(10, 20, fontsize=15)
    assert view.layout is not None

    n = len(model)
    text = '\n12345\n'
    model.insert_text(5, text)
    model.remove(5, 5 + len(text))
    assert len(model) == n
    assert len(view.layout) == n + 1
    return locals()

def test_04():
    "insert/remove"
    ns = init_testing(False)
    model = ns['model']
    view = ns['view']
    text = model.get_text()
    n = len(model)
    for i in range(len(text)):
        model.insert_text(i, 'X')
        assert len(model) == n+1
        model.remove(i, i+1)
        assert len(model) == n

def test_05():
    "remove"
    ns = init_testing(redirect=False)
    model = ns['model']
    view = ns['view']
    text = model.get_text()
    n = len(model)
    for i in range(len(text)-1):
        old = model.remove(i, i+1)
        assert len(model) == n-1
        model.insert(i, old)
        assert len(model) == n

def test_09():
    "linebreak"
    ns = init_testing(redirect=False)
    model = ns['model']
    view = ns['view']
    text = model.get_text()
    view.set_maxw(100)
    return ns

def test_10():
    "linebreak after insert"
    ns = init_testing(redirect=False)
    model = ns['model']
    view = ns['view']
    model.remove(0, len(model))
    model.insert(0, TextModel("123\n"))

    builder = view.builder
    builder.set_maxw(100)
    layout = view.layout
    assert layout.get_info(4, 0, 0)
    x, y = layout.get_info(3, 0, 0)[-2:]
    u, v = layout.get_info(4, 0, 0)[-2:]
    assert u < x
    assert v > y

def test_11():
    "relayout after changes"
    ns = init_testing(redirect=False)
    model = ns['model']
    view = ns['view']
    model.remove(0, len(model))
    model.insert(0, TextModel("123\n"))
    assert view.layout.get_index(100, 0) == 3

def test_13():
    "exception during delete 10.01.2015"
    ns = init_testing(redirect=False)
    model = ns['model']
    view = ns['view']
    view.index = 271
    view.selection = (42, 42 + 227)
    view.cut()


def test_14():
    "join_undo"
    ns = init_testing(redirect=False)
    view = ns['view']
    for i, text in enumerate('abcd'):
        view.add_undo(view.insert(i, TextModel(text)))
    assert len(view._undoinfo) == 1

    view._undoinfo = [] # reset undo

    # emulate backspace
    view.add_undo(view.remove(10, 11))
    view.add_undo(view.remove(9, 10))
    assert len(view._undoinfo) == 1

def test_15():
    "slugify converts heading text to anchor IDs"
    assert slugify("Hello World") == "hello-world"
    assert slugify("Über uns") == "über-uns"
    assert slugify("Links im Fließtext") == "links-im-fließtext"
    assert slugify("  spaced  ") == "spaced"
    assert slugify("foo_bar") == "foo-bar"


def test_16():
    "find_anchor_index locates headings by slug"
    from miniword.textmodel.textmodel import TextModel
    from miniword.core.document import Document
    doc = Document()
    doc.textmodel = TextModel('')
    pos = 0
    for line in ("# Introduction\n", "Some text.\n", "## Details\n"):
        tm = doc.textmodel.create_textmodel(line)
        doc.textmodel.insert(pos, tm)
        pos += len(line)
    base = 'h1' if True else ''
    doc.textmodel.set_parstyle(len("# Introduction") , {'base': 'h1'})
    doc.textmodel.set_parstyle(len("# Introduction\nSome text."), {'base': 'body'})
    doc.textmodel.set_parstyle(len("# Introduction\nSome text.\n## Details"), {'base': 'h2'})

    i = find_anchor_index(doc.textmodel, 'introduction')
    assert i == 0
    i2 = find_anchor_index(doc.textmodel, 'details')
    assert i2 is not None and i2 > i
    assert find_anchor_index(doc.textmodel, 'nonexistent') is None


def demo_00():
    "simple demo"
    ns = test_02()
    from . import testing
    testing.pyshell(ns)
    ns['app'].MainLoop()


def demo_01():
    "colorize demo"
    app = wx.App(redirect=False)
    frame = wx.Frame(None)
    win = wx.Panel(frame)
    view = WXTextView(win)
    box = wx.BoxSizer(wx.VERTICAL)
    box.Add(view, 1, wx.ALL | wx.GROW, 1)
    win.SetSizer(box)
    win.SetAutoLayout(True)

    from ..textmodel.textmodel import pycolorize
    from ..textmodel import texeltree
    filename = texeltree.__file__.replace('pyc', 'py')
    rawtext = open(filename, 'rb').read()
    model = pycolorize(rawtext)
    view.set_model(model)
    frame.Show()
    app.MainLoop()


def demo_02():
    "empty text"
    app = wx.App(redirect=True)
    frame = wx.Frame(None)
    win = wx.Panel(frame)
    view = WXTextView(win)
    box = wx.BoxSizer(wx.VERTICAL)
    box.Add(view, 1, wx.ALL | wx.GROW, 1)
    win.SetSizer(box)
    win.SetAutoLayout(True)
    model = TextModel(u'')
    view.set_model(model)
    frame.Show()
    from . import testing
    testing.pyshell(locals())
    app.MainLoop()


def demo_03():
    "line break"
    ns = test_09()
    from . import testing
    testing.pyshell(ns)
    ns['app'].MainLoop()

def benchmark_00():
    text = ""
    for i in range(1000):
        text += "Copy #%d \n" % i

    model = TextModel(u'Hello World!')
    model.set_properties(6, 11, fontsize=14)
    model.set_properties(0, 11, bgcolor='yellow')
    model.insert(len(model), TextModel(text))
    app = wx.App(False)

    frame = wx.Frame(None)
    view = WXTextView(frame, -1)
    view.model = model
    frame.Show()

    for i in range(100):
        model.insert_text(1000, "TEXT")
