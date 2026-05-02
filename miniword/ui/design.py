import wx
from .flatbutton import FlatButton 

BAR_BG     = wx.Colour(245, 245, 245)
BUTTON_BG  = wx.Colour(235, 235, 231)
TEXT       = wx.Colour(38, 38, 36)
TEXT_MUTED = wx.Colour(160, 160, 156)
TEXT_HIGH  = wx.Colour(233, 84, 32, 255)


SPACER = (0, 0)
ALL_CENTER = wx.ALL|wx.ALIGN_CENTER_VERTICAL


### sidepanel
def make_tab(notebook, title):
    """Add a standard notebook page with BAR_BG background and 8px padding.
    Returns (panel, content_sizer)."""
    panel = wx.Panel(notebook)
    panel.SetBackgroundColour(BAR_BG)
    notebook.AddPage(panel, title)
    dip = panel.FromDIP
    content = wx.BoxSizer(wx.VERTICAL)
    outer = wx.BoxSizer(wx.VERTICAL)
    outer.Add(content, 1, wx.EXPAND | wx.ALL, dip(8))
    panel.SetSizer(outer)
    return panel, content


def make_panel(panel, title):
    """Standard panel setup: BAR_BG background, header, padded content sizer.

    Returns the content sizer. The outer sizer is set on the panel.
    """
    panel.SetBackgroundColour(BAR_BG)
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

    # Section header
    hdr = wx.StaticText(parent, label=label)
    hdr.SetFont(wx.Font(8, wx.FONTFAMILY_DEFAULT,
                        wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
    hdr.SetForegroundColour(TEXT_MUTED)
    sizer.Add(hdr, 0, wx.LEFT | wx.TOP, dip(8))
    sizer.AddSpacer(dip(3))

def add_section(label, panel, sizer):
    # Helper: add a heading
    text = wx.StaticText(panel, label=label)
    font = text.GetFont()
    font.SetWeight(wx.FONTWEIGHT_BOLD)
    text.SetFont(font)
    sizer.Add(text, 0, wx.EXPAND|wx.TOP, panel.FromDIP(10))

def add_label(label, panel, sizer):
    # Helper: add a label
    text = wx.StaticText(panel, label=label)
    sizer.Add(text, 0, wx.EXPAND)

    
def add_row(sizer, *widgets):
    # Helper: add a row of widgets
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
    # Helper: add a row containing a label and widgets
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
    bg = BUTTON_BG
    bg_hover = bg.ChangeLightness(90)
    b.colors = {
        'normal': (bg, TEXT),
        'hover':  (bg_hover, TEXT),
        'press':  (bg_hover, TEXT_HIGH)
    }
    return b

def muted_button(parent, label, size):
    b = FlatButton(parent, label, size)
    bg = BAR_BG
    b.colors = {
        'normal': (bg, TEXT_MUTED),
        'hover':  (bg, TEXT_HIGH),
        'press':  (bg, TEXT_HIGH.ChangeLightness(150)),
    }
    return b

def text_button(parent, label, size):
    b = FlatButton(parent, label, size)
    bg = BAR_BG
    b.colors = {
            'normal': (bg, TEXT),
            'hover':  (bg, TEXT_HIGH),
            'press':  (bg, TEXT_HIGH.ChangeLightness(150)) # Shine
        }
    return b




class DemoPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.SetBackgroundColour(BAR_BG)
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        search_bar = wx.Panel(self)
        search_bar.SetBackgroundColour(BAR_BG)
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


