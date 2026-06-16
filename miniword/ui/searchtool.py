# -*- coding: utf-8 -*-
import re
import wx
from ..textmodel.viewbase import ViewBase
from ..textmodel.modelbase import Model
from ..textmodel.properties import overridable_property
from ..textmodel.utils import iter_leafes
from ..textmodel.submodel import Footnote
from ..textmodel.texeltree import get_text as texel_get_text
from .sidepanel import SidePanel
from .colours import colours
from .design import muted_button, flat_button, make_panel


def make_snippet(text, start, end, context):
    left  = max(0, start - context)
    right = min(len(text), end + context)
    return "…" + text[left:right].replace("\n", " ").strip() + "…"


class Search(ViewBase, Model):
    """Search model.

    Invalidated on every model change; updated lazily on get_results().
    """
    results   = overridable_property('results')
    _results  = ()
    fn_ranges = ()   # (fn_start, fn_end, fn_num) built during update()
    substring = ""
    ignorecase = True
    use_regex  = False
    whole_word = False
    valid      = True
    max_results = 500
    truncated   = False

    def __init__(self, model):
        ViewBase.__init__(self)
        Model.__init__(self)
        self.model = model

    def search(self, substring):
        self.substring = substring
        self.valid = False

    def update(self):
        substring = self.substring
        if not substring:
            self._results = []
            self.valid = True
            return
        try:
            pattern = substring if self.use_regex else re.escape(substring)
            if self.whole_word:
                pattern = r'\b' + pattern + r'\b'
            flags = re.IGNORECASE if self.ignorecase else 0
            rx = re.compile(pattern, flags)
        except re.error:
            self._results = []
            self.valid = True
            return
        context = 50 + min(len(substring) * 2, 60)
        results = []

        # flow=0: main text
        text = self.model.get_text()
        for m in rx.finditer(text):
            i1, i2 = m.start(), m.end()
            results.append((0, i1, i2, make_snippet(text, i1, i2, context), m.group()))
            if len(results) >= self.max_results:
                self.truncated = True
                self._results = results
                self.valid = True
                return

        # flow=1: footnotes — single traversal builds fn_ranges and searches
        fn_offset = 0
        fn_num    = 0
        fn_ranges = []
        for _, _, texel in iter_leafes(self.model.texel, 0, True):
            if not isinstance(texel, Footnote):
                continue
            fn_num  += 1
            fn_text  = texel_get_text(texel.content)[:-1]  # exclude ENDMARK
            fn_len   = len(fn_text) + 1                    # +1 for ENDMARK
            fn_ranges.append((fn_offset, fn_offset + fn_len, fn_num))
            for m in rx.finditer(fn_text):
                i1 = fn_offset + m.start()
                i2 = fn_offset + m.end()
                results.append((1, i1, i2,
                                make_snippet(fn_text, m.start(), m.end(), context),
                                m.group()))
                if len(results) >= self.max_results:
                    self.truncated = True
                    self.fn_ranges = fn_ranges
                    self._results  = results
                    self.valid     = True
                    return
            fn_offset += fn_len
        self.fn_ranges = fn_ranges

        self.truncated = False
        self._results  = results
        self.valid     = True

    def fn_number(self, i1_flow1):
        """Return the 1-based number of the footnote containing flow=1 position i1."""
        for fn_start, fn_end, num in self.fn_ranges:
            if i1_flow1 < fn_end:
                return num
        return len(self.fn_ranges)

    def get_results(self):
        if not self.valid:
            self.update()
        return self._results

    def inserted(self, model, i, n):
        self.valid = False
        self.notify_views('results_changed')

    def removed(self, model, i, text):
        self.valid = False
        self.notify_views('results_changed')


class SearchResultsList(wx.VListBox):
    MAX_LINES = 3
    on_select = None  # optional callback()

    def __init__(self, parent, editor):
        super().__init__(parent)
        self.editor    = editor
        self.textmodel = editor.root
        self.results   = []

        colours.set(self, 'BackgroundColour', 'WINDOW')
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
        return self.FromDIP(78)

    def OnDrawItem(self, dc, rect, index):
        gc       = wx.SystemSettings.GetColour
        window   = gc(wx.SYS_COLOUR_WINDOW)
        sel_col  = gc(wx.SYS_COLOUR_HIGHLIGHT)
        graytext = gc(wx.SYS_COLOUR_GRAYTEXT)
        wintext  = gc(wx.SYS_COLOUR_WINDOWTEXT)
        shadow   = gc(wx.SYS_COLOUR_BTNSHADOW)
        hotlight = gc(wx.SYS_COLOUR_HOTLIGHT)

        flow, i1, i2, snippet, query = self.results[index]

        dc.SetBrush(wx.Brush(window))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(rect)

        dip     = self.FromDIP
        padding = dip(12)

        if self.IsSelected(index):
            sel_rect = wx.Rect(rect)
            sel_rect.Deflate(1, 1)
            dc.SetBrush(wx.Brush(sel_col.ChangeLightness(185)))
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawRoundedRectangle(sel_rect, dip(6))

        dc.SetFont(self.line_font)
        dc.SetTextForeground(graytext)
        dc.DrawText(self.line_label(flow, i1), rect.x + padding, rect.y + padding)

        dc.SetFont(self.preview_font)
        lines = self.wrap_text(dc, snippet, rect.width - dip(60))
        y = rect.y + padding
        for line_text in lines[:self.MAX_LINES]:
            self.draw_line(dc, line_text, query, rect.x + dip(50), y, wintext, hotlight)
            y += dip(18)

        dc.SetPen(wx.Pen(shadow.ChangeLightness(140)))
        dc.DrawLine(rect.x + dip(10), rect.bottom - 1, rect.right - dip(10), rect.bottom - 1)

    def wrap_text(self, dc, text, max_width):
        words, lines, current = text.split(), [], ""
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

    def draw_line(self, dc, text, query, x, y, wintext, hotlight):
        text_lower  = text.lower()
        query_lower = query.lower()
        ox = x
        i  = 0
        while i < len(text):
            idx = text_lower.find(query_lower, i)
            if idx == -1:
                dc.SetTextForeground(wintext)
                dc.DrawText(text[i:], ox, y)
                break
            if idx > i:
                dc.SetTextForeground(wintext)
                part = text[i:idx]
                dc.DrawText(part, ox, y)
                ox += dc.GetTextExtent(part)[0]
            dc.SetTextForeground(hotlight)
            dc.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT,
                               wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
            match = text[idx:idx + len(query)]
            dc.DrawText(match, ox, y)
            ox += dc.GetTextExtent(match)[0]
            dc.SetFont(self.preview_font)
            i = idx + len(query)

    def on_click(self, event):
        pos = event.GetPosition()
        for idx in range(self.GetItemCount()):
            if self.GetItemRect(idx).Contains(pos):
                self.SetSelection(idx)
                self.goto_index(idx)
                if self.on_select:
                    self.on_select()
                break

    def goto_index(self, index):
        if index < 0 or index >= len(self.results):
            return
        flow, i1, i2, _, _ = self.results[index]
        editor = self.editor
        if flow == 1:
            editor.switch_target(1, i1)
            j1, j2 = editor.local_idx(i1), editor.local_idx(i2)
            editor.set_index(j1)
            editor.selection = (j1, j2)
        else:
            editor.set_index(i1)
            editor.selection = (i1, i2)
        editor.canvas.adjust_viewport()

    def line_label(self, flow, index):
        if flow == 1:
            return "FN %d" % self.search.fn_number(index)
        row, col, _ = self.textmodel.index2position(index)
        return str(row + 1)


class SearchPanel(SidePanel):
    cur   = -1
    delay = 100

    def __init__(self, parent, editor):
        SidePanel.__init__(self, parent)
        self.editor    = editor
        self.textmodel = editor.root
        self.search    = Search(self.textmodel)
        self.set_model(self.search)
        self.cur = -1
        self.create()

    def create(self):
        dip     = self.FromDIP
        content = make_panel(self, "FIND & REPLACE")

        # Search field + ▲▼ navigation
        sr       = wx.BoxSizer(wx.HORIZONTAL)
        self.search_ctrl = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search_ctrl.SetHint("Search…")
        btn_w    = dip(20)
        btn_prev = muted_button(self, "▲", size=(btn_w, -1))
        btn_next = muted_button(self, "▼", size=(btn_w, -1))
        btn_prev.SetMinSize((btn_w, -1))
        btn_next.SetMinSize((btn_w, -1))
        sr.Add(self.search_ctrl, 1, wx.EXPAND)
        sr.Add(btn_prev, 0, wx.EXPAND | wx.LEFT, dip(4))
        sr.Add(btn_next, 0, wx.EXPAND)
        content.Add(sr, 0, wx.EXPAND | wx.BOTTOM, dip(4))

        # Replace field
        self.replace_ctrl = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.replace_ctrl.SetHint("Replace…")
        content.Add(self.replace_ctrl, 0, wx.EXPAND | wx.BOTTOM, dip(4))

        # Options: Aa (case), .* (regex), W (whole word)
        os_ = wx.BoxSizer(wx.HORIZONTAL)
        self.cb_case  = wx.CheckBox(self, label="Aa")
        self.cb_regex = wx.CheckBox(self, label=".*")
        self.cb_word  = wx.CheckBox(self, label="W")
        font = wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        for cb, tip in [(self.cb_case,  "Case sensitive"),
                        (self.cb_regex, "Regex"),
                        (self.cb_word,  "Whole word")]:
            cb.SetFont(font)
            cb.SetToolTip(tip)
        os_.Add(self.cb_case,  0, wx.RIGHT, dip(10))
        os_.Add(self.cb_regex, 0, wx.RIGHT, dip(10))
        os_.Add(self.cb_word,  0)
        content.Add(os_, 0, wx.BOTTOM, dip(4))

        # Replace buttons
        brs         = wx.BoxSizer(wx.HORIZONTAL)
        btn_replace = flat_button(self, "Replace",     size=(-1, dip(24)))
        btn_all     = flat_button(self, "Replace All", size=(-1, dip(24)))
        brs.Add(btn_replace, 1, wx.RIGHT, dip(3))
        brs.Add(btn_all, 1)
        content.Add(brs, 0, wx.EXPAND | wx.BOTTOM, dip(8))

        # Separator + count label
        content.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.BOTTOM, dip(4))
        self.count_label = wx.StaticText(self, label="")
        self.count_label.SetFont(wx.Font(8, wx.FONTFAMILY_DEFAULT,
                                         wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        colours.set(self.count_label, 'ForegroundColour', 'GRAYTEXT')
        content.Add(self.count_label, 0, wx.BOTTOM, dip(3))

        # Result list
        self.result_list = SearchResultsList(self, self.editor)
        self.result_list.search    = self.search
        self.result_list.on_select = self.on_result_selected
        content.Add(self.result_list, 1, wx.EXPAND)

        # Bindings
        self.search_ctrl.Bind(wx.EVT_TEXT,       self.on_text_changed)
        self.search_ctrl.Bind(wx.EVT_TEXT_ENTER, self.go_next)
        self.replace_ctrl.Bind(wx.EVT_TEXT_ENTER, self.replace_current)
        btn_prev.Bind(wx.EVT_BUTTON,    self.go_prev)
        btn_next.Bind(wx.EVT_BUTTON,    self.go_next)
        btn_replace.Bind(wx.EVT_BUTTON, self.replace_current)
        btn_all.Bind(wx.EVT_BUTTON,     self.replace_all)
        self.cb_regex.Bind(wx.EVT_CHECKBOX, self.on_option_changed)
        self.cb_case.Bind(wx.EVT_CHECKBOX,  self.on_option_changed)
        self.cb_word.Bind(wx.EVT_CHECKBOX,  self.on_option_changed)

        # Restore search state
        self.cb_case.SetValue(not self.search.ignorecase)
        self.cb_regex.SetValue(self.search.use_regex)
        self.cb_word.SetValue(self.search.whole_word)
        if self.search.substring:
            self.search_ctrl.SetValue(self.search.substring)

    def update_visible(self):
        super().update_visible()
        if not self.visible:
            self.editor.canvas.highlights = {}
            self.editor.canvas.refresh()

    def on_text_changed(self, event):
        self.search.search(self.search_ctrl.GetValue().strip())
        self.cur = -1
        self.update()

    def results_changed(self, model):
        if self.visible:
            self.queue_update()

    def update(self):
        results = self.search.get_results()
        self.cur = min(self.cur, len(results) - 1)
        self.result_list.set_results(results)
        if self.cur >= 0:
            self.result_list.SetSelection(self.cur)
        self.show_highlights()
        self.show_count()

    def show_highlights(self):
        highlights = {}
        for idx, (flow, i1, i2, *_) in enumerate(self.result_list.results):
            color = 'orange' if idx == self.cur else 'yellow'
            highlights.setdefault(flow, []).append((i1, i2, color))
        self.editor.canvas.highlights = highlights
        self.editor.canvas.refresh()

    def show_count(self):
        results = self.result_list.results
        n      = len(results)
        suffix = "+" if self.search.truncated else ""
        if not self.search.substring:
            label = ""
        elif n == 0:
            label = "NO MATCHES"
        elif self.cur >= 0:
            label = "%d / %d%s MATCHES" % (self.cur + 1, n, suffix)
        else:
            label = "%d%s MATCHES" % (n, suffix)
        self.count_label.SetLabel(label)

    def go_next(self, event=None):
        n = len(self.result_list.results)
        if not n:
            return
        self.cur = (self.cur + 1) % n
        self.select_current()

    def go_prev(self, event=None):
        n = len(self.result_list.results)
        if not n:
            return
        self.cur = (self.cur - 1) % n
        self.select_current()

    def select_current(self):
        self.result_list.SetSelection(self.cur)
        self.result_list.goto_index(self.cur)
        self.show_highlights()
        self.show_count()

    def on_result_selected(self):
        self.cur = self.result_list.GetSelection()
        self.show_highlights()
        self.show_count()

    def replace_one(self, flow, i1, i2, replacement):
        editor = self.editor
        if flow == 1:
            editor.switch_target(1, i1)
            j1, j2 = editor.local_idx(i1), editor.local_idx(i2)
            editor.selection = (j1, j2)
            editor.remove()
            if replacement:
                editor.index = j1
                editor.insert_text(replacement)
        else:
            editor.selection = (i1, i2)
            editor.remove()
            if replacement:
                editor.index = i1
                editor.insert_text(replacement)

    def replace_current(self, event=None):
        results = self.result_list.results
        idx = self.cur
        if idx < 0 or idx >= len(results):
            if results:
                self.cur = 0
                self.select_current()
            return
        flow, i1, i2, _, _ = results[idx]
        self.replace_one(flow, i1, i2, self.replace_ctrl.GetValue())
        self.search.update()
        new_results = self.search.get_results()
        self.cur = min(idx, len(new_results) - 1)
        self.result_list.set_results(new_results)
        self.show_highlights()
        if self.cur >= 0:
            self.result_list.SetSelection(self.cur)
            self.result_list.goto_index(self.cur)
        self.show_count()

    def replace_all(self, event=None):
        results = self.search.get_results()
        if not results:
            return
        replacement = self.replace_ctrl.GetValue()
        editor = self.editor
        editor.begin_undo_group()
        for flow, i1, i2, _, _ in reversed(results):
            self.replace_one(flow, i1, i2, replacement)
        editor.end_undo_group()
        self.cur = -1

    def on_option_changed(self, event):
        self.search.use_regex   = self.cb_regex.GetValue()
        self.search.ignorecase  = not self.cb_case.GetValue()
        self.search.whole_word  = self.cb_word.GetValue()
        self.search.search(self.search_ctrl.GetValue().strip())
        self.cur = -1
        self.update()


def demo_00():
    "Search panel on a TextEditor showing the Einstein text"
    from einstein import get_einstein_model
    from ..core.styles import testsheet
    from ..layout.factory import Factory
    from ..layout.cairodevice import CairoDevice
    from ..layout.pagebuilder import PageBuilder
    from ..texteditor.editor import Editor
    from ..texteditor.textcanvas import TextCanvas

    app = wx.App(True)
    model = get_einstein_model()
    factory = Factory(testsheet, device=CairoDevice())
    builder = PageBuilder(model, factory)
    builder.rebuild()
    builder.assure_index(len(model))
    editor = Editor(model)

    frame = wx.Frame(None, title="Search Demo", size=(800, 600))
    canvas = TextCanvas(frame, model, builder, editor)
    editor.canvas = canvas

    panel = SearchPanel(wx.Frame(None, title="Search"), editor)
    panel.GetParent().Show()
    frame.Show()
    app.MainLoop()


def test_00():
    from einstein import get_einstein_model
    model  = get_einstein_model()
    search = Search(model)

    search.search('Einstein')
    res = [(flow, i1, i2) for flow, i1, i2, *_ in search.results]
    expected = [(0, 7, 15), (0, 633, 641), (0, 1516, 1524), (0, 2667, 2675),
                (0, 2770, 2778), (0, 3147, 3155), (0, 3274, 3282), (0, 3643, 3651),
                (0, 3743, 3751)]
    assert res == expected

    model.remove(0, 7)
    res2 = [(flow, i1, i2) for flow, i1, i2, *_ in search.results]
    expected2 = [(0, 0, 8), (0, 626, 634), (0, 1509, 1517), (0, 2660, 2668),
                 (0, 2763, 2771), (0, 3140, 3148), (0, 3267, 3275), (0, 3636, 3644),
                 (0, 3736, 3744)]
    assert res2 == expected2


def test_01():
    "case sensitivity"
    from einstein import get_einstein_model
    model  = get_einstein_model()
    search = Search(model)

    search.search('einstein')
    assert len(search.results) == 9

    search.ignorecase = False
    search.search('einstein')
    assert search.results == []

    search.search('Einstein')
    res = [(i1, i2) for _, i1, i2, *_ in search.results]
    assert res == [(7, 15), (633, 641), (1516, 1524), (2667, 2675),
                   (2770, 2778), (3147, 3155), (3274, 3282), (3643, 3651),
                   (3743, 3751)]


def test_02():
    "regex and whole word"
    from einstein import get_einstein_model
    model  = get_einstein_model()
    search = Search(model)
    search.use_regex = True

    search.search(r'Einstein|Zurich')
    assert len(search.results) == 12

    search.search(r'\d{4}')
    text = model.get_text()
    assert all(i2 - i1 == 4 and text[i1:i2].isdigit()
               for flow, i1, i2, *_ in search.results if flow == 0)
    assert len(search.results) > 15

    search.search(r'[invalid')
    assert search.results == []

    search2 = Search(model)
    search2.whole_word = True
    search2.search('he')
    assert search2.results
    for flow, i1, i2, *_ in search2.results:
        if flow == 0:
            assert i1 == 0 or not text[i1 - 1].isalpha()
            assert i2 >= len(text) or not text[i2].isalpha()


def test_03():
    "replace via model operations"
    from miniword.textmodel.textmodel import TextModel
    model  = TextModel('aaa bbb aaa ccc aaa')
    search = Search(model)
    search.search('aaa')
    assert len(search.results) == 3

    _, i1, i2, _, _ = search.results[0]
    assert model.get_text()[i1:i2] == 'aaa'
    model.remove(i1, i2)
    model.insert_text(i1, 'xx')

    results = search.get_results()
    assert len(results) == 2
    assert all(model.get_text()[j1:j2] == 'aaa' for _, j1, j2, *_ in results)

    for _, i1, i2, _, _ in reversed(results):
        model.remove(i1, i2)
        model.insert_text(i1, 'yy')

    assert search.get_results() == []
    assert 'aaa' not in model.get_text()


def test_04():
    "search in footnotes (flow=1)"
    from ..textmodel.submodel import mk_test
    model  = mk_test()
    search = Search(model)

    search.search('Zur')
    fn_results = [(i1, i2) for flow, i1, i2, *_ in search.results if flow == 1]
    assert len(fn_results) > 0
    assert all(flow in (0, 1) for flow, *_ in search.results)
