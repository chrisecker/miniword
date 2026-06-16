# -*- coding: utf-8 -*-
import wx
from .sidepanel import SidePanel
from .design import make_panel, make_tab, add_section, flat_button

NUMBERING_CHOICES = ["Numbers", "Letters", "Roman", "Custom Label"]
NUMBERING_KEYS    = ["numbers", "letters", "roman", "custom"]


class LinksPanel(SidePanel):

    def __init__(self, parent, editor, document):
        SidePanel.__init__(self, parent)
        self.editor   = editor
        self.document = document
        self.add_model(editor)
        self.create()

    def create(self):
        dip      = self.FromDIP
        content  = make_panel(self, "LINKS")
        notebook = wx.Notebook(self)
        notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED,
            lambda e: (e.Skip(), wx.CallAfter(self.editor.canvas.SetFocus)))
        content.Add(notebook, 1, wx.EXPAND)

        self._build_footnotes_tab(notebook)
        self._build_hyperlink_tab(notebook)
        self.update()

    def _build_footnotes_tab(self, notebook):
        panel, content = make_tab(notebook, 'Footnotes')
        dip = panel.FromDIP

        btn_insert = flat_button(panel, "Insert", size=(-1, dip(24)))
        content.Add(btn_insert, 0, wx.EXPAND | wx.BOTTOM, dip(8))

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(panel, label="Numbering"), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, dip(6))
        self.numbering = wx.Choice(panel, choices=NUMBERING_CHOICES)
        row.Add(self.numbering, 1, wx.ALIGN_CENTER_VERTICAL)
        content.Add(row, 0, wx.EXPAND | wx.BOTTOM, dip(4))

        lbl_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl_row.Add(wx.StaticText(panel, label="Label"), 0,
                    wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, dip(6))
        self.label_ctrl = wx.TextCtrl(panel)
        self.label_ctrl.SetHint("e.g. *")
        lbl_row.Add(self.label_ctrl, 1, wx.ALIGN_CENTER_VERTICAL)
        content.Add(lbl_row, 0, wx.EXPAND | wx.BOTTOM, dip(4))

        btn_insert.Bind(wx.EVT_BUTTON,     self.on_insert)
        self.numbering.Bind(wx.EVT_CHOICE, self.on_numbering_changed)
        self.label_ctrl.Bind(wx.EVT_TEXT,  self.on_label_changed)

    def _build_hyperlink_tab(self, notebook):
        panel, content = make_tab(notebook, 'Hyperlink')
        dip = panel.FromDIP

        url_row = wx.BoxSizer(wx.HORIZONTAL)
        url_row.Add(wx.StaticText(panel, label="URL"), 0,
                    wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, dip(6))
        self.url_ctrl = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.url_ctrl.SetHint("https://…")
        url_row.Add(self.url_ctrl, 1, wx.ALIGN_CENTER_VERTICAL)
        content.Add(url_row, 0, wx.EXPAND | wx.BOTTOM, dip(4))

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

        href = self.editor.get_current_style().get('href', '')
        if self.url_ctrl.GetValue() != href:
            self.url_ctrl.ChangeValue(href)

    def on_insert(self, event=None):
        from ..textmodel.submodel import Footnote
        from ..textmodel.texeltree import ENDMARK, length
        from ..textmodel.utils import iter_leafes
        editor = self.editor
        with editor.atomic():
            editor.remove()
            anchor = editor.abs_idx(editor.index)
            editor.insert_texel(Footnote(ENDMARK))
        fn_offset = 0
        for i1, i2, texel in iter_leafes(editor.root.texel, 0, True):
            if not isinstance(texel, Footnote):
                continue
            if i1 == anchor:
                editor.switch_target(1, fn_offset)
                editor.set_index(editor.local_idx(fn_offset))
                if editor.canvas:
                    wx.CallAfter(editor.canvas.adjust_viewport)
                break
            fn_offset += length(texel.content)

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
        ranges = editor.selected_ranges()
        if not ranges:
            style = dict(editor.current_style)
            if url:
                style.update(href=url, underline=True)
            else:
                style.pop('href', None)
            editor.current_style = style
            return
        with editor.atomic():
            saved = editor.selection
            for i1, i2 in ranges:
                editor.selection = (i1, i2)
                if url:
                    editor.set_properties(href=url, underline=True)
                else:
                    editor.clear_properties('href')
            editor.selection = saved

    def on_label_changed(self, event=None):
        fn = self.active_footnote()
        if fn is None or not self.label_ctrl.IsEnabled():
            return
        text = self.label_ctrl.GetValue()
        fn.update_host(lambda t: t.set_label(text))
