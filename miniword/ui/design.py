import wx
from .flatbutton import FlatButton 

BAR_BG     = wx.Colour(245, 245, 245)
BUTTON_BG  = wx.Colour(235, 235, 231)
TEXT       = wx.Colour(38, 38, 36)
TEXT_MUTED = wx.Colour(160, 160, 156)
TEXT_HIGH  = wx.Colour(233, 84, 32, 255)



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
        
        btn_rep = flat_button(self, "Replace", size=(-1, 28))
        btn_all = flat_button(self, "Replace all", size=(-1, 28))
        
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


