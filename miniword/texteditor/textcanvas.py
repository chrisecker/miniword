import wx
import string

from ..textmodel import TextModel
from ..textmodel.styles import updated_style
from ..textmodel.viewbase import overridable_property, ViewBase

from ..layout.cairodevice import CairoDevice, defaultstyle
from ..layout.testdevice import TESTDEVICE
from ..layout.simplelayout import SimpleBuilder
from ..layout.rect import Rect
from math import ceil
import pickle





class TextCanvas(wx.ScrolledWindow, ViewBase): # TextPanel, WxTextDisplay, TextCanvas
    """
    - Render bei Modelländerungen
    - Hat Editor als optionales Attribut
    - Wenn Editor None ist, dann wird auch kein Cursor dargestellt
    """
    _scrollrate = 10, 10

    zoom = overridable_property('zoom')
    scale = overridable_property('scale')
    layout = overridable_property('layout')
    _zoom = 1.0
    min_zoom    = 0.2
    max_zoom    = 5.0
    zoom_factor = 1.1
    

    def __init__(self, parent, model, builder, editor=None, pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=0):
        ViewBase.__init__(self)
        self.editor = editor
        self.model = model
        if editor is not None:
            self.add_model(editor)
        self.builder = builder
        wx.ScrolledWindow.__init__(self, parent, -1,
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
        self.Bind(wx.EVT_MOUSEWHEEL, self.on_mousewheel)
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
            (wx.WXK_BACK,   False, False): 'del_left',
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

    def ensure_viewport(self):
        # XXX weg damit ?
        pass

    def get_layout(self):
        return self.builder.layout

    def get_zoom(self):
        return self._zoom

    def set_zoom(self, zoom):
        self._zoom = zoom
    
    def get_scale(self):
        # XXX besser wäre die scale-Berechung direkt in TextView, aber
        # eine DPI-Berechung lokal! ??
        
        try:
            dpi = self.GetDPI().y
        except AttributeError:
            dpi = wx.ScreenDC().GetPPI()[1]
        return self.builder.device.get_scale(dpi, self.zoom)

    def reset_blink(self):
        self.builder.device.reset_blink()
        
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
        self.refresh()

    def on_destroy(self, event):
        if self.timer.IsRunning():
            self.timer.Stop()
        event.Skip()

    def on_focus(self, event):
        self.refresh()

    def on_size(self, event):
        self.keep_cursor_on_screen()

    # --- keyboard ---

    def on_char(self, event):
        if self.editor is None:
            return
        if self.editor.controller.on_key(event.GetKeyCode(), event):
            return
        keycode = event.GetKeyCode()
        ukey = event.GetUnicodeKey()
        ctrl = event.ControlDown()
        shift = event.ShiftDown()
        alt = event.AltDown()
        action = self.actions.get((keycode, ctrl, alt))

        if action is not None:
            self.editor.controller.handle_action(action, shift)
            return

        # Ctrl-Sequences are used for menu shortcuts -> Skip the event
        # so it is handled by wx. 
        if ctrl and not alt:
            # NOTE: AltGr triggers Ctrl in wx and is used only for
            # text here. We therefore have to exclude this case.
            event.Skip()
            return

        if ukey != wx.WXK_NONE:
            self.editor.insert_text(chr(ukey))
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
        if self.editor and self.editor.controller.on_motion(event):
            return
        if not event.LeftIsDown():
            return event.Skip()
        x, y = self.window_to_content(event.Position)
        i = self.layout.get_index(x, y)
        if i is not None:
            self.editor.set_index(i, extend=True)

    def on_mousewheel(self, event):
        if not event.ControlDown():
            return event.Skip()  # let wx handle normal scrolling

        old_scale = self.scale
        factor = self.zoom_factor if event.GetWheelRotation() > 0 \
            else 1 / self.zoom_factor
        new_zoom = max(self.min_zoom, min(self.max_zoom, self.zoom * factor))

        cw, ch = self.GetClientSize()
        rx, ry = self._scrollrate
        sx, sy = self.GetViewStart()
        scroll_x, scroll_y = sx * rx, sy * ry

        # content point currently at the viewport center
        cx_content = (scroll_x + cw / 2) / old_scale
        cy_content = (scroll_y + ch / 2) / old_scale

        self.zoom = new_zoom
        new_scale = self.scale

        # virtual size must be updated before scrolling
        layout = self.layout
        self.SetVirtualSize((int(layout.width * new_scale), int(layout.height * new_scale)))
        self.SetScrollRate(rx, ry)

        # scroll so the content point stays at the viewport center
        new_scroll_x = cx_content * new_scale - cw / 2
        new_scroll_y = cy_content * new_scale - ch / 2
        self.Scroll(max(0, int(new_scroll_x / rx)), max(0, int(new_scroll_y / ry)))
        self.refresh()

    def on_leftdown(self, event):
        editor = self.editor
        if editor.controller.on_leftdown(event):
            return
        x, y = self.window_to_content(event.Position)
        flow = self.layout.get_flow(x, y)
        i = self.layout.get_index(x, y, flow)
        if i is not None:
            if flow != editor.flow:
                editor.switch_target(flow, i)
            editor.set_index(i, extend=event.ShiftDown())
        self.SetFocus()

    def on_leftup(self, event):
        if self.editor.controller.on_leftup(event):
            self.SetCursor(wx.Cursor(wx.CURSOR_IBEAM))

    def on_leftdclick(self, event):
        #if self.try_install_click_editor():
        #    return
        x, y = self.window_to_content(event.Position)
        self.select_word(x, y)
        self.SetFocus()

    def select_word(self, x, y):
        editor = self.editor
        i = self.layout.get_index(x, y, editor.flow)
        if i is None:
            return
        model = editor.target
        n = len(model)
        
        def isalnum(j):
            return model.get_text(j, j+1).isalnum()
            
        try:
            while not isalnum(i-1):
                i = i-1
            while isalnum(i-1):
                i = i-1
        except IndexError:
            i = 0
        i1 = i
        i = i1
        try:
            while not isalnum(i):
                i = i+1
            while isalnum(i):
                i = i+1
        except IndexError:
            i = n
        i2 = i
        editor.index = i2
        editor.selection = (i1, i2)

    

            
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
        painter = device.create_painter(dc, origin=(px, py), zoom=self.zoom)

        self.draw(painter)
        dc = None
        painter = None

    def has_focus(self):
        return wx.Window.FindFocus() is self

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

    def get_viewport(self):
        w, h = self.GetClientSize()
        x1, y1 = self.window_to_content((0, 0))
        x2, y2 = self.window_to_content((w, h))
        return Rect(x1, y1, x2, y2)
    
    def adjust_viewport(self):
        layout = self.layout
        if self.editor.index > len(layout):
            return
        cursor = layout.get_rect(self.editor.index, 0, 0)
        vp = self.get_viewport()
        fw, fh = self._scrollrate
        scale = self.scale
        w, h = self.GetClientSize()
        firstcol, firstrow = self.GetViewStart()

        if cursor.y1 <= vp.y1:
            firstrow = int(cursor.y1 * scale / fh)
        elif cursor.y2 > vp.y2:
            firstrow = ceil((cursor.y2 * scale - h) / fh)

        if cursor.x1 <= vp.x1:
            firstcol = int(cursor.x1 * scale / fw)
        elif cursor.x2 > vp.x2:
            firstcol = ceil((cursor.x2 * scale - w) / fw)

        if (firstcol, firstrow) != self.GetViewStart():
            self.Scroll(firstcol, firstrow)

    def window_to_content(self, pos):
        """Calculates content coordinates from window-coordinates,
        accounts for scroll position."""
        scale = self.scale
        x, y = self.CalcUnscrolledPosition(pos)
        ox, oy = self.content_offset()
        return (x - ox) / scale, (y - oy) / scale

    ### Drawing

    def draw_background(self, painter):
        pass

    def draw(self, painter):
        self.builder.assure_rect(self.get_viewport())
        # unnütig! self.builder.assure_index(self.editor.index) # XXX flow?
                
        self.draw_background(painter)
        self.layout.draw(0, 0, painter)
        if self.editor is not None:
            self.editor.controller.draw(painter)

    def draw_cursor(self, painter):
        # note that draw_cursor is called by editor
        if not self.has_focus():
            return
        editor = self.editor
        style = {} # XXX self.get_filled_style(self.index).copy()
        current = editor.get_current_style()
        style.update(current)
        i = editor.abs_idx(editor.index)
        self.layout.draw_cursor(i, 0, 0, painter, style,
                                flow=editor.flow)

    def draw_selection(self, painter):
        # note that draw_selection is called by editor
        for j1, j2 in self.editor.selected_ranges():
            self.layout.draw_selection(j1, j2, 0, 0, painter,
                                       flow=self.editor.flow)
    def model_changed(self, *args):
        self.refresh()
    

def test_00():
    "simplebuilder as view"
    model = TextModel()
    builder = SimpleBuilder(model, maxw=100)
    assert builder.model.views == [builder]

    builder.rebuild()
    s = str(builder.layout)
    assert s == "SimpleLayout[Paragraph[Row[ENDBOX]]]"

    model.insert_text(0, 'Hi Chris!')
    s = str(builder.layout)
    assert s == "SimpleLayout[Paragraph[Row[TB('Hi Chris!'), ENDBOX]]]"

def test_01():
    "pagebuilder as view"
    from ..core.styles import testsheet
    from ..layout.factory import Factory
    from ..layout.pagebuilder import PageBuilder
    
    app = wx.App(redirect=False)    
    model = TextModel()
    factory = Factory(testsheet)
    builder = PageBuilder(model, factory)
    assert builder.model.views == [builder]

    model.insert_text(0, 'Hi Chris!')
    builder.assure_finished()
    assert len(builder.layout)

def demo_00():
    "Texteditor based on simplebuilder" 
    app = wx.App(redirect=True)
    model = TextModel()
    builder = SimpleBuilder(model, device=CairoDevice(), maxw=100)
    builder.rebuild()
    
    from .editor import Editor
    editor = Editor(model)

    frame = wx.Frame(None)
    win = wx.Panel(frame)
    canvas = TextCanvas(win, model, builder, editor)
    editor.canvas = canvas # XXX zirkuläre Referenz!
    
    box = wx.BoxSizer(wx.VERTICAL)
    box.Add(canvas, 1, wx.ALL | wx.GROW, 1)
    win.SetSizer(box)
    win.SetAutoLayout(True)
    frame.Show()

    editor.root.insert_text(0, 'Hi\nChris!')
    app.MainLoop()

def demo_01():
    "Texteditor based on the pages builder"     
    from ..layout.pagebuilder import PageBuilder
    from ..core.styles import testsheet
    from ..layout.factory import Factory
        
    app = wx.App(redirect=True)
    model = TextModel()
    factory = Factory(testsheet, device=CairoDevice())
    builder = PageBuilder(model, factory)    
    
    from .editor import Editor
    editor = Editor(model)

    frame = wx.Frame(None)
    win = wx.Panel(frame)
    canvas = TextCanvas(win, model, builder, editor)
    editor.canvas = canvas
    
    box = wx.BoxSizer(wx.VERTICAL)
    box.Add(canvas, 1, wx.ALL | wx.GROW, 1)
    win.SetSizer(box)
    win.SetAutoLayout(True)
    frame.Show()

    editor.root.insert_text(0, 'Hi\nChris!')
    builder.rebuild()
    builder.assure_index(len(model))
    
    assert builder.model is model
    assert len(builder.layout) == len(model)+1
    app.MainLoop()

def demo_02():
    "Footnotes"
    from ..textmodel.submodel import mk_test, _get_text
    from ..layout.pagebuilder import PageBuilder
    from ..core.styles import testsheet
    from ..layout.factory import Factory
        
    app = wx.App(redirect=True)
    model = mk_test()
    factory = Factory(testsheet, device=CairoDevice())
    builder = PageBuilder(model, factory)    
    
    from .editor import TestEditor
    editor = TestEditor(model)

    frame = wx.Frame(None)
    win = wx.Panel(frame)
    canvas = TextCanvas(win, model, builder, editor)
    editor.canvas = canvas
    
    box = wx.BoxSizer(wx.VERTICAL)
    box.Add(canvas, 1, wx.ALL | wx.GROW, 1)
    win.SetSizer(box)
    win.SetAutoLayout(True)
    frame.Show()

    editor.switch_target(1, 102)
    builder.rebuild()
    builder.assure_index(len(model))
    
    assert builder.model is model
    assert len(builder.layout) == len(model)+1

    if 1:
        from ..ui import testing
        l = locals()
        l.update(globals())
        testing.pyshell(l)

    app.MainLoop()

