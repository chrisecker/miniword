import re
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
    use_regex = False
    whole_word = False
    valide = True

    def __init__(self, model):
        ViewBase.__init__(self)
        Model.__init__(self)
        self.model = model

    def search(self, substring):
        self.substring = substring
        self.valide = False

    def update(self):
        substring = self.substring
        text = self.model.get_text()
        if not substring:
            self._results = []
            self.valide = True
            return
        try:
            pattern = substring if self.use_regex else re.escape(substring)
            if self.whole_word:
                pattern = r'\b' + pattern + r'\b'
            flags = re.IGNORECASE if self.ignorecase else 0
            rx = re.compile(pattern, flags)
        except re.error:
            self._results = []
            self.valide = True
            return
        context = 50 + min(len(substring) * 2, 60)
        results = []
        for m in rx.finditer(text):
            i1, i2 = m.start(), m.end()
            left = max(0, i1 - context)
            right = min(len(text), i2 + context)
            snippet = "…" + text[left:right].replace("\n", " ").strip() + "…"
            results.append((i1, i2, snippet, m.group()))
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
        return row + 1


class SearchPanel(wx.Panel, ViewBase):
    _current_idx = -1
    _update_queued = False

    def __init__(self, parent, textview):
        wx.Panel.__init__(self, parent)
        ViewBase.__init__(self)
        self.textview = textview
        self.textmodel = textview.model
        self.search = Search(self.textmodel)
        self.set_model(self.search)

        outer = wx.BoxSizer(wx.VERTICAL)

        # Search + Replace fields
        grid = wx.FlexGridSizer(2, 2, 4, 4)
        grid.AddGrowableCol(1)
        grid.Add(wx.StaticText(self, label="Search:"), 0,
                 wx.ALIGN_CENTER_VERTICAL)
        self.search_ctrl = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search_ctrl.SetHint("Search…")
        grid.Add(self.search_ctrl, 0, wx.EXPAND)
        grid.Add(wx.StaticText(self, label="Replace:"), 0,
                 wx.ALIGN_CENTER_VERTICAL)
        self.replace_ctrl = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.replace_ctrl.SetHint("Replace…")
        grid.Add(self.replace_ctrl, 0, wx.EXPAND)
        outer.Add(grid, 0, wx.EXPAND | wx.ALL, 8)

        # Nav bar: count label + buttons
        nav = wx.BoxSizer(wx.HORIZONTAL)
        self.count_label = wx.StaticText(self, label="")
        nav.Add(self.count_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
        bmp_prev = wx.ArtProvider.GetBitmap(wx.ART_GO_BACK, wx.ART_BUTTON)
        bmp_next = wx.ArtProvider.GetBitmap(wx.ART_GO_FORWARD, wx.ART_BUTTON)
        btn_prev = wx.BitmapButton(self, bitmap=bmp_prev)
        btn_next = wx.BitmapButton(self, bitmap=bmp_next)
        btn_replace = wx.Button(self, label="Replace")
        btn_all = wx.Button(self, label="All")
        nav.Add(btn_prev, 0, wx.RIGHT, 2)
        nav.Add(btn_next, 0, wx.RIGHT, 6)
        nav.Add(btn_replace, 0, wx.RIGHT, 2)
        nav.Add(btn_all, 0, wx.RIGHT, 4)
        outer.Add(nav, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)

        # Options toggle + panel
        btn_opts = wx.ToggleButton(self, label="Options")
        outer.Add(btn_opts, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        opts_panel = wx.Panel(self)
        opts = wx.BoxSizer(wx.HORIZONTAL)
        self.cb_regex = wx.CheckBox(opts_panel, label="Regex")
        self.cb_case = wx.CheckBox(opts_panel, label="Case sensitive")
        self.cb_word = wx.CheckBox(opts_panel, label="Whole word")
        opts.Add(self.cb_regex, 0, wx.RIGHT, 8)
        opts.Add(self.cb_case, 0, wx.RIGHT, 8)
        opts.Add(self.cb_word, 0)
        opts_panel.SetSizer(opts)
        opts_panel.Hide()
        outer.Add(opts_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)

        # Result list
        self.result_list = SearchResultsList(self, textview)
        self.result_list.on_select = self._on_result_selected
        outer.Add(self.result_list, 1, wx.EXPAND | wx.ALL, 6)

        self.SetSizer(outer)

        # Bindings
        self.search_ctrl.Bind(wx.EVT_TEXT, self.on_text_changed)
        self.search_ctrl.Bind(wx.EVT_TEXT_ENTER, self._go_next)
        self.replace_ctrl.Bind(wx.EVT_TEXT_ENTER, self._replace_current)
        btn_prev.Bind(wx.EVT_BUTTON, self._go_prev)
        btn_next.Bind(wx.EVT_BUTTON, self._go_next)
        btn_replace.Bind(wx.EVT_BUTTON, self._replace_current)
        btn_all.Bind(wx.EVT_BUTTON, self._replace_all)
        self.cb_regex.Bind(wx.EVT_CHECKBOX, self._on_option_changed)
        self.cb_case.Bind(wx.EVT_CHECKBOX, self._on_option_changed)
        self.cb_word.Bind(wx.EVT_CHECKBOX, self._on_option_changed)
        btn_opts.Bind(wx.EVT_TOGGLEBUTTON,
                      lambda e: (opts_panel.Show(btn_opts.GetValue()),
                                 self.Layout()))

    def on_text_changed(self, event):
        self.search.search(self.search_ctrl.GetValue().strip())
        self._current_idx = -1
        self.update()

    def results_changed(self, model):
        if self._update_queued:
            return
        self._update_queued = True
        wx.CallAfter(self.update)

    def update(self):
        results = self.search.get_results()
        self._current_idx = min(self._current_idx, len(results) - 1)
        self.result_list.set_results(results)
        self._update_queued = False
        if self._current_idx >= 0:
            self.result_list.SetSelection(self._current_idx)
        self._update_highlights()
        self._update_count_label()

    def _update_highlights(self):
        highlights = []
        for idx, (i1, i2, *_) in enumerate(self.result_list.results):
            color = 'orange' if idx == self._current_idx else 'yellow'
            highlights.append((i1, i2, color))
        self.textview.highlights = highlights
        self.textview.Refresh()

    def _update_count_label(self):
        n = len(self.result_list.results)
        if n == 0:
            label = "No matches"
        elif self._current_idx >= 0:
            label = "%d / %d" % (self._current_idx + 1, n)
        else:
            label = "%d matches" % n
        self.count_label.SetLabel(label)

    def _go_next(self, event=None):
        n = len(self.result_list.results)
        if not n:
            return
        self._current_idx = (self._current_idx + 1) % n
        self._select_current()

    def _go_prev(self, event=None):
        n = len(self.result_list.results)
        if not n:
            return
        self._current_idx = (self._current_idx - 1) % n
        self._select_current()

    def _select_current(self):
        idx = self._current_idx
        self.result_list.SetSelection(idx)
        self.result_list.goto_index(idx)
        self._update_highlights()
        self._update_count_label()

    def _on_result_selected(self):
        self._current_idx = self.result_list.GetSelection()
        self._update_highlights()
        self._update_count_label()

    def _replace_current(self, event=None):
        results = self.result_list.results
        idx = self._current_idx
        if idx < 0 or idx >= len(results):
            if results:
                self._current_idx = 0
                self._select_current()
            return
        i1, i2, _, _ = results[idx]
        replacement = self.replace_ctrl.GetValue()
        self.textview.remove(i1, i2)
        if replacement:
            self.textview.insert_text(i1, replacement)
        self.search.update()
        new_results = self.search.get_results()
        self._current_idx = min(idx, len(new_results) - 1)
        self.result_list.set_results(new_results)
        self._update_highlights()
        if self._current_idx >= 0:
            self.result_list.SetSelection(self._current_idx)
            self.result_list.goto_index(self._current_idx)
        self._update_count_label()
        self._update_queued = True

    def _replace_all(self, event=None):
        results = self.search.get_results()
        if not results:
            return
        replacement = self.replace_ctrl.GetValue()
        self.textview.begin_undo_group()
        for i1, i2, _, _ in reversed(results):
            self.textview.remove(i1, i2)
            if replacement:
                self.textview.insert_text(i1, replacement)
        self.textview.end_undo_group()
        self._current_idx = -1

    def _on_option_changed(self, event):
        self.search.use_regex = self.cb_regex.GetValue()
        self.search.ignorecase = not self.cb_case.GetValue()
        self.search.whole_word = self.cb_word.GetValue()
        self.search.search(self.search_ctrl.GetValue().strip())
        self._current_idx = -1
        self.update()


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


def test_01():
    "case sensitivity"
    from einstein import get_einstein_model
    model = get_einstein_model()
    search = Search(model)

    # default ignorecase=True: lowercase finds all occurrences
    search.search('einstein')
    assert len(search.results) == 9

    # case-sensitive: lowercase matches nothing
    search.ignorecase = False
    search.search('einstein')
    assert search.results == []

    # case-sensitive: exact casing matches
    search.search('Einstein')
    res = [(i1, i2) for i1, i2, *_ in search.results]
    assert res == [(7, 15), (633, 641), (1516, 1524), (2667, 2675),
                   (2770, 2778), (3147, 3155), (3274, 3282), (3643, 3651),
                   (3743, 3751)]


def test_02():
    "regex and whole word"
    from einstein import get_einstein_model
    model = get_einstein_model()
    search = Search(model)
    search.use_regex = True

    # alternation: 9 Einstein + 3 Zurich
    search.search(r'Einstein|Zurich')
    assert len(search.results) == 12

    # 4-digit years: all matches exactly 4 digits
    search.search(r'\d{4}')
    text = model.get_text()
    assert all(i2 - i1 == 4 and text[i1:i2].isdigit()
               for i1, i2, *_ in search.results)
    assert len(search.results) > 15

    # invalid regex → empty results, no exception
    search.search(r'[invalid')
    assert search.results == []

    # whole word: no match is part of a longer word
    search2 = Search(model)
    search2.whole_word = True
    search2.search('he')
    assert search2.results
    for i1, i2, *_ in search2.results:
        assert i1 == 0 or not text[i1 - 1].isalpha()
        assert i2 >= len(text) or not text[i2].isalpha()


def test_03():
    "replace via model operations"
    from miniword.textmodel.textmodel import TextModel
    model = TextModel('aaa bbb aaa ccc aaa')
    search = Search(model)
    search.search('aaa')
    assert len(search.results) == 3

    # single replace: first 'aaa' → 'xx'
    i1, i2, _, _ = search.results[0]
    assert model.get_text()[i1:i2] == 'aaa'
    model.remove(i1, i2)
    model.insert_text(i1, 'xx')

    # search auto-updates via inserted/removed callbacks
    results = search.get_results()
    assert len(results) == 2
    assert all(model.get_text()[j1:j2] == 'aaa' for j1, j2, *_ in results)

    # replace all remaining in reverse order (preserves offsets)
    for i1, i2, _, _ in reversed(results):
        model.remove(i1, i2)
        model.insert_text(i1, 'yy')

    assert search.get_results() == []
    assert 'aaa' not in model.get_text()
