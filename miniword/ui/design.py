import wx
from .colours import colours
from .flatbutton import FlatButton


SPACER = (0, 0)
ALL_CENTER = wx.ALL|wx.ALIGN_CENTER_VERTICAL


def make_tab(notebook, title):
    """Add a standard notebook page with panel background and 8px padding.
    Returns (panel, content_sizer)."""
    panel = wx.Panel(notebook)
    colours.set(panel, 'BackgroundColour', 'BTNFACE')
    notebook.AddPage(panel, title)
    dip = panel.FromDIP
    content = wx.BoxSizer(wx.VERTICAL)
    outer = wx.BoxSizer(wx.VERTICAL)
    outer.Add(content, 1, wx.EXPAND | wx.ALL, dip(8))
    panel.SetSizer(outer)
    return panel, content


def make_panel(panel, title):
    """Standard panel setup: background, header, padded content sizer.
    Returns the content sizer."""
    colours.set(panel, 'BackgroundColour', 'BTNFACE')
    dip = panel.FromDIP
    outer = wx.BoxSizer(wx.VERTICAL)
    add_header(title, panel, outer)
    content = wx.BoxSizer(wx.VERTICAL)
    outer.Add(content, 1, wx.EXPAND | wx.ALL, dip(8))
    panel.SetSizer(outer)
    return content


def add_header(label, parent, sizer):
    """Add a panel header to vertical sizer *sizer*."""
    dip = parent.FromDIP
    sizer.AddSpacer(dip(6))
    hdr = wx.StaticText(parent, label=label)
    hdr.SetFont(wx.Font(8, wx.FONTFAMILY_DEFAULT,
                        wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
    colours.set(hdr, 'ForegroundColour', 'GRAYTEXT')
    sizer.Add(hdr, 0, wx.LEFT | wx.TOP, dip(8))
    sizer.AddSpacer(dip(3))


def add_section(label, panel, sizer):
    text = wx.StaticText(panel, label=label)
    font = text.GetFont()
    font.SetWeight(wx.FONTWEIGHT_BOLD)
    text.SetFont(font)
    sizer.Add(text, 0, wx.EXPAND|wx.TOP, panel.FromDIP(10))


def add_label(label, panel, sizer):
    text = wx.StaticText(panel, label=label)
    sizer.Add(text, 0, wx.EXPAND)


def add_row(sizer, *widgets):
    rowsizer = wx.BoxSizer(wx.HORIZONTAL)
    ref = next((w for w in widgets if isinstance(w, wx.Window)), None)
    border = ref.FromDIP(5) if ref else 5
    for i, widget in enumerate(widgets):
        if isinstance(widget, tuple):
            w, h = widget
            widget = wx.Size(w, h)
        if i == 0:
            rowsizer.Add(widget, 1, ALL_CENTER, border)
        else:
            rowsizer.Add(widget, 0, ALL_CENTER, border)
    sizer.Add(rowsizer, 0, wx.EXPAND)


def add_row2(label, panel, sizer, *widgets):
    add_label(label, panel, sizer)
    dip = panel.FromDIP
    rowsizer = wx.BoxSizer(wx.HORIZONTAL)
    rowsizer.AddStretchSpacer(1)
    rowsizer.Add(widgets[0], 0, ALL_CENTER, dip(5))
    rowsizer.AddStretchSpacer(1)
    for widget in widgets[1:]:
        rowsizer.Add(widget, 0, ALL_CENTER, dip(5))
    sizer.Add(rowsizer, 0, wx.EXPAND | wx.LEFT, dip(24))


def flat_button(parent, label, size):
    b = FlatButton(parent, label, size)
    colours.set(b, 'colour_normal_bg', 'BTNFACE')
    colours.set(b, 'colour_normal_fg', 'WINDOWTEXT')
    colours.set(b, 'colour_hover_bg',  'ButtonHover')
    colours.set(b, 'colour_hover_fg',  'WINDOWTEXT')
    colours.set(b, 'colour_press_bg',  'ButtonHover')
    colours.set(b, 'colour_press_fg',  'Highlight')
    return b


def muted_button(parent, label, size):
    b = FlatButton(parent, label, size)
    colours.set(b, 'colour_normal_bg', 'BTNFACE')
    colours.set(b, 'colour_normal_fg', 'GRAYTEXT')
    colours.set(b, 'colour_hover_bg',  'BTNFACE')
    colours.set(b, 'colour_hover_fg',  'Highlight')
    colours.set(b, 'colour_press_bg',  'BTNFACE')
    colours.set(b, 'colour_press_fg',  'Highlight')
    return b


def text_button(parent, label, size):
    b = FlatButton(parent, label, size)
    colours.set(b, 'colour_normal_bg', 'BTNFACE')
    colours.set(b, 'colour_normal_fg', 'WINDOWTEXT')
    colours.set(b, 'colour_hover_bg',  'BTNFACE')
    colours.set(b, 'colour_hover_fg',  'Highlight')
    colours.set(b, 'colour_press_bg',  'BTNFACE')
    colours.set(b, 'colour_press_fg',  'Highlight')
    return b


class DemoPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        colours.set(self, 'BackgroundColour', 'BTNFACE')

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        search_bar = wx.Panel(self)
        colours.set(search_bar, 'BackgroundColour', 'BTNFACE')
        sb_sizer = wx.BoxSizer(wx.HORIZONTAL)

        ctrl = wx.TextCtrl(search_bar)
        btn_up = text_button(search_bar, label="▲", size=(20, -1))
        btn_dn = text_button(search_bar, label="▼", size=(20, -1))

        sb_sizer.Add(ctrl, 1, wx.CENTER | wx.LEFT, 5)
        sb_sizer.Add(btn_up, 0, wx.EXPAND|wx.LEFT, 5)
        sb_sizer.Add(btn_dn, 0, wx.EXPAND|wx.RIGHT, 5)
        search_bar.SetSizer(sb_sizer)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_rep = flat_button(self, "Replace", size=(-1, self.FromDIP(28)))
        btn_all = flat_button(self, "Replace all", size=(-1, self.FromDIP(28)))

        btn_sizer.Add(btn_rep, 1, wx.RIGHT, 5)
        btn_sizer.Add(btn_all, 1)

        main_sizer.Add(search_bar, 0, wx.EXPAND | wx.ALL, 10)
        main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.SetSizer(main_sizer)


def demo_00():
    app = wx.App()
    frame = wx.Frame(None, title="Cross-Platform UI", size=(350, 200))
    DemoPanel(frame)
    frame.Show()
    app.MainLoop()
