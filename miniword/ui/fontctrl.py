import wx
from .colours import colours


class FontListBox(wx.VListBox):
    def __init__(self, parent, popup):
        super().__init__(parent)
        self.popup = popup
        self._items = []

        colours.set(self, 'BackgroundColour', 'WINDOW')
        colours.register(self, self.refresh_all)

        self.Bind(wx.EVT_LEFT_DOWN,    self.on_click)
        self.Bind(wx.EVT_MOTION,       self.on_motion)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.on_leave)
        self.Bind(wx.EVT_KEY_DOWN,     self.on_key)

    def refresh_all(self):
        self.RefreshAll()

    def set_items(self, items):
        self._items = items
        self.SetItemCount(len(items))
        self.RefreshAll()
        self._hover = -1

    # --- Drawing ---

    def OnDrawItem(self, dc, rect, n):
        if n < 0 or n >= len(self._items):
            return

        face = self._items[n]
        font = wx.Font(
            11, wx.FONTFAMILY_DEFAULT,
            wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL,
            faceName=face,
        )
        dc.SetFont(font)

        sel = self.GetSelection()
        if n == sel:
            dc.SetBrush(wx.Brush(
                wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
            ))
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawRectangle(rect)
            dc.SetTextForeground(
                wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT)
            )
        else:
            dc.SetTextForeground(
                wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
            )

        w, h = dc.GetTextExtent(face)
        dy = int(0.5 * (rect.height - h) + 0.5)
        dc.DrawText(face, rect.x + 5, rect.y + dy)

    def OnMeasureItem(self, n):
        return 22

    # --- Mouse ---

    def on_motion(self, event):
        """Highlight item under cursor."""
        item = self.VirtualHitTest(event.GetY())
        if item != wx.NOT_FOUND and item != self.GetSelection():
            self.SetSelection(item)
            self.Refresh()
        event.Skip()

    def on_leave(self, event):
        self.SetSelection(-1)
        self.Refresh()
        event.Skip()

    def on_click(self, event):
        item = self.VirtualHitTest(event.GetY())
        if item != wx.NOT_FOUND:
            self.popup.select_item(item)
        event.Skip()

    # --- Keyboard: ↑ ↓ Enter Esc ---

    def on_key(self, event):
        sel = self.GetSelection()
        key = event.GetKeyCode()
        if key == wx.WXK_DOWN:
            sel = min(sel + 1, len(self._items) - 1)
            self.SetSelection(sel)
            self.Refresh()
        elif key == wx.WXK_UP:
            sel = max(sel - 1, 0)
            self.SetSelection(sel)
            self.Refresh()
        elif key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            if sel != wx.NOT_FOUND:
                self.popup.select_item(sel)
        elif key == wx.WXK_ESCAPE:
            self.popup.combo.Dismiss()
        else:
            event.Skip()


class FontPopup(wx.ComboPopup):
    def __init__(self):
        super().__init__()
        self.listbox = None
        self.combo = None

    def Init(self):
        pass

    def Create(self, parent):
        self.listbox = FontListBox(parent, self)
        return True

    def GetControl(self):
        return self.listbox

    def GetStringValue(self):
        sel = self.listbox.GetSelection()
        if sel != wx.NOT_FOUND:
            return self.listbox._items[sel]
        return ""

    def set_items(self, items):
        self.listbox.set_items(items)

    def select_item(self, index):
        value = self.listbox._items[index]
        self.combo.SetText(value)

        # Find and store the index within _filtered_fonts
        try:
            self.combo._current_selection = (
                self.combo._filtered_fonts.index(value)
            )
        except ValueError:
            self.combo._current_selection = -1

        self.combo.Dismiss()

        # Fire EVT_COMBOBOX manually
        evt = wx.CommandEvent(wx.wxEVT_COMBOBOX, self.combo.GetId())
        evt.SetEventObject(self.combo)
        wx.PostEvent(self.combo, evt)


# =============================
# FontCombo (ComboCtrl)
# =============================

class FontCombo(wx.ComboCtrl):
    def __init__(self, parent):
        super().__init__(parent, style=wx.CB_READONLY)

        self._all_fonts      = []
        self._filtered_fonts = []

        self.popup       = FontPopup()
        self.popup.combo = self
        self.SetPopupControl(self.popup)

        self._current_selection = -1

        colours.set(self, 'BackgroundColour', 'WINDOW')
        colours.set(self, 'ForegroundColour', 'WINDOWTEXT')

        self._load_fonts()

    def _load_fonts(self):
        font_enum = wx.FontEnumerator()
        font_enum.EnumerateFacenames()
        fonts = font_enum.GetFacenames()
        fonts = [f for f in fonts if not f.startswith("@")]
        fonts = sorted(set(fonts), key=str.lower)
        self._all_fonts = fonts
        self.set_filter("")

    def set_filter(self, text):
        text = text.lower()
        if text:
            self._filtered_fonts = [
                f for f in self._all_fonts if text in f.lower()
            ]
        else:
            self._filtered_fonts = self._all_fonts.copy()

        self.popup.set_items(self._filtered_fonts)

        if self._filtered_fonts:
            self._current_selection = 0
            self.SetText(self._filtered_fonts[0])
        else:
            self._current_selection = -1
            self.SetText("")

    def GetFontName(self):
        return self.GetValue() or None

    def SetFontName(self, name):
        if name in self._filtered_fonts:
            self._current_selection = self._filtered_fonts.index(name)
        else:
            self._current_selection = -1
        self.SetText(name)


# =============================
# Test UI
# =============================

class TestPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.filter_ctrl = wx.TextCtrl(self)
        self.font_combo  = FontCombo(self)
        sizer.Add(self.filter_ctrl, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.font_combo,  0, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(sizer)

        self.filter_ctrl.Bind(wx.EVT_TEXT,    self.on_filter)
        self.font_combo.Bind(wx.EVT_COMBOBOX, self.on_family)

    def on_filter(self, event):
        text = self.filter_ctrl.GetValue()
        self.font_combo.set_filter(text)

    def on_family(self, event):
        print("Font selected:", self.font_combo.GetFontName())


class TestFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="Font Chooser", size=(400, 300))
        TestPanel(self)
        self.Centre()
        self.Show()


def demo_00():
    app = wx.App(redirect=True)
    TestFrame()
    app.MainLoop()
    
