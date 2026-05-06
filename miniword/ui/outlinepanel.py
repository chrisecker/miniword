import wx
from ..textmodel.viewbase import ViewBase
from ..textmodel.utils import get_newlines
from ..layout.counters import format_number, set_counter, inc_counter
from ..core.styles import n_levels


def iter_headings(model, stylesheet):
    """Yield (nl_index, level, label, par_start) for heading paragraphs.

    label includes the section number when the heading uses counter='section'.
    """
    xtexel   = model.get_xtexel()
    n        = len(model)
    counters = {}  # {ckey: [int]*n_levels}

    for index, nl in get_newlines(xtexel, 0, n):
        parstyle  = nl.parstyle
        base      = parstyle.get('base', 'normal')
        basestyle = stylesheet.get(base) or {}
        merged    = {**basestyle, **parstyle}

        role = merged.get('role', '')
        if not (role and len(role) >= 2 and role[0] == 'h' and role[1:].isdigit()):
            continue

        level  = int(role[1:])
        indent = merged['fixed_indent']
        if indent is None:
            indent = getattr(nl, 'indent', 0) or 0
        
        ptype  = merged.get('paragraph_type', 'normal')
        ckey   = merged.get('counter', 'item')

        prefix = ''
        if ptype == 'numbered' and ckey == 'section':
            ns = merged.get('numbering_style', ('1.',) * n_levels)
            if ckey not in counters:
                counters[ckey] = [0] * n_levels
            counter = counters[ckey]
            sn = parstyle.get('start_number')
            if sn is not None:
                set_counter(indent, counter, sn)
            else:
                inc_counter(indent, counter)
            counters['item'] = [0] * n_levels
            prefix = format_number(counters[ckey], indent, ns[indent]) + ' '

        prev_nl = model.prev_newline(index)
        start   = prev_nl + 1
        text    = model.get_text(start, index).strip()
        yield index, level, prefix + text, start


class OutlinePanel(wx.Panel, ViewBase):

    def __init__(self, parent, document, textview):
        wx.Panel.__init__(self, parent)
        ViewBase.__init__(self)
        self._textview   = textview
        self._basestyles = document.basestyles
        self._entries    = []   # [(par_start, wx.TreeItemId)] sorted by par_start
        self._timer      = wx.Timer(self)

        self._tree = wx.TreeCtrl(self,
            style=wx.TR_HAS_BUTTONS | wx.TR_NO_LINES |
                  wx.TR_FULL_ROW_HIGHLIGHT | wx.TR_HIDE_ROOT)
        self._hover_item = wx.TreeItemId()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._tree, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self._tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._on_activate)
        self._tree.Bind(wx.EVT_MOTION,       self._on_hover)
        self._tree.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.Bind(wx.EVT_TIMER, lambda _: self.refresh())

        self.add_model(document.textmodel)
        self.add_model(document.basestyles)

    # --- ViewBase handlers ----------------------------------------------

    def inserted(self, model, i, n):
        self._schedule_refresh()

    def removed(self, model, i, removed):
        self._schedule_refresh()

    def properties_changed(self, model, i1, i2):
        self._schedule_refresh()

    def model_changed(self, model):
        self._schedule_refresh()

    def _schedule_refresh(self):
        self._timer.StartOnce(400)

    # --- Document switch ------------------------------------------------

    def set_document(self, document):
        for model in list(self._models):
            self.remove_model(model)
        self._basestyles = document.basestyles
        self.add_model(document.textmodel)
        self.add_model(document.basestyles)
        wx.CallAfter(self.refresh)

    # --- Tree building --------------------------------------------------

    def refresh(self):
        model = self._textview.model
        tree  = self._tree
        tree.DeleteAllItems()
        self._entries    = []
        self._hover_item = wx.TreeItemId()

        root  = tree.AddRoot("Document")
        stack = []   # [(level, tree_item)]

        for index, level, label, start in iter_headings(model, self._basestyles):
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1] if stack else root
            item   = tree.AppendItem(parent, label or '—')
            tree.SetItemData(item, start)
            self._entries.append((start, item))
            stack.append((level, item))

        tree.ExpandAll()
        self._sync_cursor()

    # --- Navigation & cursor sync ---------------------------------------

    def _on_activate(self, event):
        index = self._tree.GetItemData(event.GetItem())
        if index is not None:
            self._textview.set_index(index)
            self._textview.adjust_viewport()
            self._textview.SetFocus()

    def _sync_cursor(self):
        if not self._entries:
            return
        index = self._textview.index
        best  = None
        for start, item in self._entries:
            if start <= index:
                best = item
            else:
                break
        if best and best.IsOk():
            self._tree.SelectItem(best)

    # --- Hover highlight ------------------------------------------------

    _HOVER_LIGHTNESS = 140   # % of highlight colour (lighter = more subtle)

    def _on_hover(self, event):
        item, _ = self._tree.HitTest(event.GetPosition())
        self._set_hover(item)
        event.Skip()

    def _on_leave(self, event):
        self._set_hover(wx.TreeItemId())
        event.Skip()

    def _set_hover(self, item):
        if self._hover_item == item:
            return
        if self._hover_item.IsOk():
            self._tree.SetItemBackgroundColour(self._hover_item, wx.NullColour)
        self._hover_item = item
        if item.IsOk():
            colour = wx.SystemSettings.GetColour(
                wx.SYS_COLOUR_HIGHLIGHT).ChangeLightness(self._HOVER_LIGHTNESS)
            self._tree.SetItemBackgroundColour(item, colour)

    # --- DPI ------------------------------------------------------------

    def dpi_changed(self):
        pass
