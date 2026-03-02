import wx
from .textmodel.viewbase import ViewBase
from .textmodel.modelbase import Model
from .textmodel.properties import overridable_property


class Search(ViewBase, Model):
    # Search model
    results = overridable_property('results')
    _results = ()
    substring = ""
    ignorecase = True
    valide = True

    def __init__(self, model):
        ViewBase.__init__(self)
        Model.__init__(self)
        self.model = model

    def search(self, substring, ignorecase=True):
        self.substring = substring
        self.ignorecase = ignorecase
        self.valide = False

    def update(self):
        substring = self.substring
        text = _text = self.model.get_text()
        if self.ignorecase:
            text = text.upper()
            substring = substring.upper()
        if substring == "":
            self._results = []
            return

        results = []
        start = 0
        n = len(substring)
        while True:
            index = text.find(substring, start)
            if index == -1:
                break
            end = index + n
            # Kontext für MiniPreview
            context = 50 + min(len(substring) * 2, 60)
            left = max(0, index - context)
            right = min(len(text), end + context)
            snippet = "…" + _text[left:right].replace("\n", " ").strip() + "…"
            results.append((index, end, snippet, substring))
            start = index + 1  # Überlappende Treffer erlauben
        self._results = results
        self.valide = True

    def get_results(self):
        if not self.valide:
            self.update()
        return self._results

    def inserted(self, model, i, n):
        self.valide = False
        self.notify_views('results_changed')

    def removed(self, model, i, text):
        self.valide = False
        self.notify_views('results_changed')


class SearchResultsList(wx.VListBox):
    MAX_LINES = 3
    on_select = None  # optional callback()

    def __init__(self, parent, textview):
        super().__init__(parent)
        self.textview = textview
        self.textmodel = textview.model
        self.results = []

        self.SetBackgroundColour(wx.Colour(252, 252, 252))
        self.SetBackgroundStyle(wx.BG_STYLE_CUSTOM)

        self.preview_font = wx.Font(10, wx.FONTFAMILY_DEFAULT,
                                    wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.line_font = wx.Font(8, wx.FONTFAMILY_DEFAULT,
                                 wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)

        self.Bind(wx.EVT_LEFT_DOWN, self.on_click)

    def set_results(self, results):
        self.results = results or []
        self.SetItemCount(len(self.results))
        self.Refresh()

    def OnMeasureItem(self, index):
        return 78

    def OnDrawItem(self, dc, rect, index):
        i1, i2, snippet, query = self.results[index]

        dc.SetBrush(wx.Brush(wx.Colour(252, 252, 252)))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(rect)

        padding = 12

        if self.IsSelected(index):
            sel_rect = wx.Rect(rect)
            sel_rect.Deflate(1, 1)
            dc.SetBrush(wx.Brush(wx.Colour(225, 238, 255)))
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawRoundedRectangle(sel_rect, 6)

        dc.SetFont(self.line_font)
        dc.SetTextForeground(wx.Colour(140, 140, 140))
        line = self._line_from_pos(i1)
        dc.DrawText(str(line), rect.x + padding, rect.y + padding)

        dc.SetFont(self.preview_font)
        max_width = rect.width - 60
        lines = self._wrap_text(dc, snippet, max_width)
        y = rect.y + padding
        for line_text in lines[:self.MAX_LINES]:
            self._draw_highlighted_line(dc, line_text, query, rect.x + 50, y)
            y += 18

        dc.SetPen(wx.Pen(wx.Colour(235, 235, 235)))
        dc.DrawLine(rect.x + 10, rect.bottom - 1, rect.right - 10, rect.bottom - 1)

    def _wrap_text(self, dc, text, max_width):
        words = text.split()
        lines = []
        current = ""
        for word in words:
            test = current + " " + word if current else word
            w, _ = dc.GetTextExtent(test)
            if w <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def _draw_highlighted_line(self, dc, text, query, x, y):
        text_lower = text.lower()
        query_lower = query.lower()
        offset_x = x
        i = 0
        while i < len(text):
            idx = text_lower.find(query_lower, i)
            if idx == -1:
                dc.SetTextForeground(wx.Colour(40, 40, 40))
                dc.DrawText(text[i:], offset_x, y)
                break
            if idx > i:
                dc.SetTextForeground(wx.Colour(40, 40, 40))
                part = text[i:idx]
                dc.DrawText(part, offset_x, y)
                w, _ = dc.GetTextExtent(part)
                offset_x += w
            # Treffer
            dc.SetTextForeground(wx.Colour(200, 50, 50))
            dc.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT,
                               wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
            match_text = text[idx:idx+len(query)]
            dc.DrawText(match_text, offset_x, y)
            w, _ = dc.GetTextExtent(match_text)
            offset_x += w
            dc.SetFont(self.preview_font)
            i = idx + len(query)

    def on_click(self, event):
        pos = event.GetPosition()
        # Einfaches HitTest per ItemRect, robust auf allen wxPython-Versionen
        for idx in range(self.GetItemCount()):
            rect = self.GetItemRect(idx)
            if rect.Contains(pos):
                self.SetSelection(idx)
                self.goto_index(idx)
                if self.on_select:
                    self.on_select()
                break

    def goto_index(self, index):
        if index < 0 or index >= len(self.results):
            return
        i1, i2, _, _ = self.results[index]
        self.textview.set_index(i1)
        self.textview.set_selection((i1, i2))
        self.textview.adjust_viewport()

    def _line_from_pos(self, index):
        row, col = self.textmodel.index2position(index)
        return row+1


class SearchPanel(wx.Panel, ViewBase):
    def __init__(self, parent, textview):
        wx.Panel.__init__(self, parent)
        ViewBase.__init__(self)
        self.textview = textview
        self.textmodel = textview.model
        self.search = Search(self.textmodel)
        self.set_model(self.search)

        outer = wx.BoxSizer(wx.VERTICAL)
        self.search_ctrl = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search_ctrl.SetHint("Search…")
        outer.Add(self.search_ctrl, 0, wx.EXPAND | wx.ALL, 10)

        self.result_list = SearchResultsList(self, textview)
        self.result_list.on_select = self._update_highlights
        outer.Add(self.result_list, 1, wx.EXPAND | wx.ALL, 6)

        self.SetSizer(outer)

        self.search_ctrl.Bind(wx.EVT_TEXT, self.on_text_changed)

    def on_text_changed(self, event):
        query = self.search_ctrl.GetValue().strip()
        self.search.search(query)
        self.update()

    _update_queued = False
    def results_changed(self, model):
        if self._update_queued:
            return
        self._update_queued = True
        wx.CallAfter(self.update)

    def _update_highlights(self):
        sel = self.result_list.GetSelection()
        highlights = []
        for idx, (i1, i2, *_) in enumerate(self.result_list.results):
            color = 'orange' if idx == sel else 'yellow'
            highlights.append((i1, i2, color))
        self.textview.highlights = highlights
        self.textview.Refresh()

    def update(self):
        results = self.search.get_results()
        self.result_list.set_results(results)
        self._update_queued = False
        self._update_highlights()
        


def demo_00():
    from .wxtextview.wxtextview import WXTextView
    from einstein import get_einstein_model
    app = wx.App(True)
    frame = wx.Frame(None, title="Search Demo", size=(500, 400))
    model = get_einstein_model()
    f = wx.Frame(None)
    view = WXTextView(f)
    view.set_model(model)
    f.Show()
    panel = SearchPanel(frame, view)
    frame.Show()
    app.MainLoop()

def test_00():
    from einstein import get_einstein_model
    model = get_einstein_model()
    search = Search(model)

    search.search('Einstein')
    res = [(i1, i2) for i1, i2, *_ in search.results]
    expected = [(7, 15), (633, 641), (1516, 1524), (2667, 2675),
                (2770, 2778), (3147, 3155), (3274, 3282), (3643, 3651),
                (3743, 3751)]
    assert res == expected

    model.remove(0, 7)
    res2 = [(i1, i2) for i1, i2, *_ in search.results]
    expected2 = [(0, 8), (626, 634), (1509, 1517), (2660, 2668),
                 (2763, 2771), (3140, 3148), (3267, 3275), (3636, 3644),
                 (3736, 3744)]
    assert res2 == expected2

