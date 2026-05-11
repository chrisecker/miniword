import wx
from .colours import colours
from .icons import themed_icon


wxEVT_BUTTONBAR = wx.NewEventType()
EVT_BUTTONBAR = wx.PyEventBinder(wxEVT_BUTTONBAR, 1)


class ButtonBarEvent(wx.CommandEvent):
    def __init__(self, id=0, name=None):
        super().__init__(wxEVT_BUTTONBAR, id)
        self.name = name


class ButtonBar(wx.Panel):
    def __init__(self, parent, *, exclusive=False, button_size=36):
        super().__init__(parent)

        self.exclusive  = exclusive
        self.buttons    = {}
        self._svg_names = {}

        self.sizer = wx.GridSizer(1, 0, 0, 0)
        self.SetSizer(self.sizer)

        self.btn_size = self.FromDIP(wx.Size(button_size, button_size))
        colours.register(self, self._update_icons)

    def add(self, name, svg_name):
        self._svg_names[name] = svg_name

        if self.exclusive:
            btn = wx.ToggleButton(self, label="")
            btn.Bind(wx.EVT_TOGGLEBUTTON, self._on_toggle)
        else:
            btn = wx.Button(self, label="")
            btn.Bind(wx.EVT_BUTTON, self._on_click)

        btn.SetBitmap(self._make_bitmap(svg_name))
        btn.SetMinSize(self.btn_size)

        self.buttons[name] = btn
        self.sizer.Add(btn, 1, wx.EXPAND)

    def _make_bitmap(self, svg_name):
        col = wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNTEXT)
        return themed_icon(svg_name, col)

    def _update_icons(self):
        for name, svg_name in self._svg_names.items():
            self.buttons[name].SetBitmap(self._make_bitmap(svg_name))

    def select(self, name):
        if not self.exclusive:
            return
        for n, btn in self.buttons.items():
            btn.SetValue(n == name)

    def _fire(self, name):
        evt = ButtonBarEvent(self.GetId(), name=name)
        evt.SetEventObject(self)
        self.ProcessWindowEvent(evt)

    def _on_click(self, event):
        for name, btn in self.buttons.items():
            if btn is event.GetEventObject():
                self._fire(name)
                break

    def _on_toggle(self, event):
        clicked = event.GetEventObject()
        for name, btn in self.buttons.items():
            btn.SetValue(btn is clicked)
            if btn is clicked:
                self._fire(name)
