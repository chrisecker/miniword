# -*- coding: utf-8 -*-
import wx
from .sidepanel import SidePanel
from .design import make_panel, add_section, add_row, flat_button, \
    ALL_CENTER
from .flatbutton import ResetButton
from ..textmodel.styles import get_styles

NUMBERING_CHOICES = ["Numbers", "Letters", "Roman", "Custom Label"]
NUMBERING_KEYS    = ["numbers", "letters", "roman", "custom"]


def link_at(model, j):
    """(j1, j2) of the link at j (the character before j, else after),
    or None."""
    def href(k):
        return 0 <= k < len(model) and model.get_style(k).get('href')
    k = j - 1 if href(j - 1) else j
    url = href(k)
    if not url:
        return None
    j1, j2 = k, k + 1
    while href(j1 - 1) == url:
        j1 -= 1
    while href(j2) == url:
        j2 += 1
    return j1, j2


class LinksPanel(SidePanel):

    def __init__(self, parent, editor, document):
        SidePanel.__init__(self, parent)
        self.editor   = editor
        self.document = document
        self.add_model(editor)
        self.create()

    def create(self):
        sizer = make_panel(self, "LINKS")
        self._build_footnotes(sizer)
        self._build_hyperlink(sizer)
        self.update()

    def _build_footnotes(self, sizer):
        add_section("Footnotes", self, sizer)
        btn_insert = flat_button(self, "Insert", size=(-1, self.FromDIP(24)))
        add_row(sizer, btn_insert)
        self.numbering = wx.Choice(self, choices=NUMBERING_CHOICES)
        add_row(sizer, wx.StaticText(self, label="Numbering"), self.numbering)
        self.label_ctrl = wx.TextCtrl(self)
        self.label_ctrl.SetHint("e.g. *")
        add_row(sizer, wx.StaticText(self, label="Label"), self.label_ctrl)

        btn_insert.Bind(wx.EVT_BUTTON,     self.on_insert)
        self.numbering.Bind(wx.EVT_CHOICE, self.on_numbering_changed)
        self.label_ctrl.Bind(wx.EVT_TEXT,  self.on_label_changed)

    def _build_hyperlink(self, sizer):
        add_section("Hyperlink", self, sizer)
        dip = self.FromDIP
        self.url_ctrl = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.reset_url = ResetButton(self)
        self.reset_url.callback = self.clear_href
        row = wx.BoxSizer(wx.HORIZONTAL)  # the field fills the row
        row.Add(wx.StaticText(self, label="URL"), 0, ALL_CENTER, dip(5))
        row.Add(self.url_ctrl, 1, ALL_CENTER, dip(5))
        row.Add(self.reset_url, 0, ALL_CENTER, dip(5))
        sizer.Add(row, 0, wx.EXPAND)
        for evt in (wx.EVT_TEXT_ENTER, wx.EVT_KILL_FOCUS):
            self.url_ctrl.Bind(evt, self.on_url_changed)

    def active_footnote(self):
        editor = self.editor
        if getattr(editor, 'flow', 0) != 1:
            return None
        return getattr(editor, 'target', None)

    def get_texel(self, fn):
        from ..textmodel.submodel import Footnote
        from ..textmodel.utils import iter_leafes
        for i1, i2, t in iter_leafes(fn.root.texel, 0, True):
            if isinstance(t, Footnote) and i1 == fn.anchor:
                return t
        return None

    def update(self):
        fn     = self.active_footnote()
        has_fn = fn is not None
        self.numbering.Enable(has_fn)
        if not has_fn:
            self.label_ctrl.Enable(False)
        else:
            texel = self.get_texel(fn)
            if texel is not None:
                if texel.label is not None:
                    self.numbering.SetSelection(NUMBERING_KEYS.index('custom'))
                    self.label_ctrl.Enable(True)
                    self.label_ctrl.ChangeValue(texel.label)
                else:
                    key = texel.numbering
                    idx = NUMBERING_KEYS.index(key) if key in NUMBERING_KEYS else 0
                    self.numbering.SetSelection(idx)
                    self.label_ctrl.Enable(False)
                    self.label_ctrl.ChangeValue('')

        ranges = self.link_ranges()
        self.url_ctrl.Enable(bool(ranges))
        self.reset_url.Enable(bool(ranges))
        if not ranges:
            self.url_ctrl.SetHint("Select text to add a link")
            if self.url_ctrl.GetValue():
                self.url_ctrl.ChangeValue('')
            self.reset_url.set_x(False)
            return

        model = self.editor.target
        urls = {style.get('href') or ''
                for j1, j2 in ranges
                for n, style in get_styles(model.get_xtexel(), j1, j2)}
        href = min(urls) if len(urls) == 1 else ''
        self.url_ctrl.SetHint("https://…" if len(urls) == 1 else
                              "Partly linked" if '' in urls else
                              "Several links")
        if self.url_ctrl.GetValue() != href:
            self.url_ctrl.ChangeValue(href)
        self.reset_url.set_x(urls != {''})  # any link

    def link_ranges(self):
        """Where the URL applies: the selection, else the link at the
        cursor."""
        editor = self.editor
        ranges = editor.selected_ranges()
        if ranges:
            return ranges
        link = link_at(editor.target, editor.index)
        return [link] if link else []

    def on_insert(self, event=None):
        from ..textmodel.submodel import Footnote
        from ..textmodel.texeltree import ENDMARK
        from ..footnotes.footnotes import footnote_anchored_at
        editor = self.editor
        with editor.atomic():
            editor.remove()
            flow = getattr(editor, 'flow', 0)  # in a footnote: nested
            anchor = editor.abs_idx(editor.index)
            editor.insert_texel(Footnote(ENDMARK))
        fn_offset = footnote_anchored_at(editor.root.texel, flow, anchor)
        if fn_offset is not None:
            editor.switch_target(1, fn_offset)
            editor.set_index(editor.local_idx(fn_offset))
            if editor.canvas:
                wx.CallAfter(editor.canvas.adjust_viewport)

    def on_numbering_changed(self, event=None):
        fn = self.active_footnote()
        if fn is None:
            return
        key = NUMBERING_KEYS[self.numbering.GetSelection()]
        if key == 'custom':
            self.label_ctrl.Enable(True)
            self.label_ctrl.SetFocus()
        else:
            self.label_ctrl.Enable(False)
            self.label_ctrl.ChangeValue('')
            fn.update_host(lambda t: t.set_numbering(key).set_label(None))

    def on_url_changed(self, event=None):
        url    = self.url_ctrl.GetValue().strip()
        editor = self.editor
        ranges = self.link_ranges()
        if not ranges:
            return
        with editor.atomic():
            saved = editor.selection
            for i1, i2 in ranges:
                editor.selection = (i1, i2)
                if url:
                    editor.set_properties(href=url, underline=True)
                else:
                    editor.clear_properties('href', 'underline')
            editor.selection = saved
        self.reset_url.set_x(bool(url))

    def clear_href(self):
        self.url_ctrl.ChangeValue('')
        self.on_url_changed()

    def on_label_changed(self, event=None):
        fn = self.active_footnote()
        if fn is None or not self.label_ctrl.IsEnabled():
            return
        text = self.label_ctrl.GetValue()
        fn.update_host(lambda t: t.set_label(text))
