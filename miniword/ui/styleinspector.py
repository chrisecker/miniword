# -*- coding: utf-8 -*-


import wx
from .design import make_tab, add_section, add_row, add_row2
from .flatbutton import FlatButton, ResetButton
from .sidepanel import SidePanel
from ..textmodel.textmodel import TextModel
from ..textmodel.texeltree import EMPTYSTYLE, provides_childs, iter_childs, \
    NewLine, dump
from ..textmodel.utils import iter_newlines
from ..textmodel.styles import create_style
from ..wxtextview.wxdevice import defaultstyle

from .unitentry import LengthInput, FractionInput, EVT_UNIT_CHANGED
from .threestate import SpinCtrl3, EVT_SPIN_VALUE, ColourButton
from .buttonbar import ButtonBar, ButtonBarEvent, EVT_BUTTONBAR
from .stylemenu import BasestyleSelector
from ..core.styles import defaultbullets, n_levels, style_default
from ..core.utils import updated


# Display labels and matching format strings for the numbering dropdown.
_NUMBERING_FORMATS = ['1.', 'a.', 'A.', 'i.']

# (label, parstyle value) pairs for the role dropdown.
_ROLES = [
    ('(None)',         None),
    ('Header 1',      'h1'),
    ('Header 2',      'h2'),
    ('Header 3',      'h3'),
    ('Header 4',      'h4'),
    ('Header 5',      'h5'),
    ('Header 6',      'h6'),
    ('List',          'list'),
    ('Enumeration',   'numbered'),
    ('Code',          'pre'),
    ('Quote',         'quote'),
]



def _is_text_input(w: wx.Window) -> bool:
    """Return True for controls that must keep focus to function correctly."""
    return isinstance(w, (wx.TextCtrl, wx.ComboBox, wx.Choice,
                          wx.SpinCtrl, wx.SpinCtrlDouble, wx.SpinButton,
                          wx.CheckBox, wx.RadioButton, wx.Slider,
                          wx.ListBox, wx.ListCtrl))

def passfocus(widget: wx.Window, mainwidget: wx.Window, interval_ms: int = 100):
    def _check(event):
        if wx.GetMouseState().LeftIsDown():
            return  # don't steal focus mid-click; let the widget process it
        focused = wx.Window.FindFocus()
        if focused is None:
            return
        if widget.IsDescendant(focused) and not _is_text_input(focused):
            mainwidget.SetFocus()

    timer = wx.Timer(widget)
    widget.Bind(wx.EVT_TIMER, _check, timer)
    timer.Start(interval_ms)

    widget.Bind(wx.EVT_WINDOW_DESTROY, lambda e: timer.Stop())
    widget._passfocus_timer = timer  # reference to prevent gc

    
class AlignBar(ButtonBar):
    def __init__(self, parent):
        ButtonBar.__init__(self, parent, exclusive=True)
        for name, svg in [
            ("left",    "format_align_left_24dp_1F1F1F_FILL0_wght400_GRAD0_opsz24.svg"),
            ("center",  "format_align_center_24dp_1F1F1F_FILL0_wght400_GRAD0_opsz24.svg"),
            ("right",   "format_align_right_24dp_1F1F1F_FILL0_wght400_GRAD0_opsz24.svg"),
            ("justify", "format_align_justify_24dp_1F1F1F_FILL0_wght400_GRAD0_opsz24.svg")]:
            self.add(name, svg)


class IndentBar(ButtonBar):
    def __init__(self, parent):
        ButtonBar.__init__(self, parent, exclusive=False)
        for name, svg in [
            ("dedent", "format_indent_decrease_24dp_1F1F1F_FILL0_wght400_GRAD0_opsz24.svg"),
            ("indent", "format_indent_increase_24dp_1F1F1F_FILL0_wght400_GRAD0_opsz24.svg")]:
            self.add(name, svg)


    
class PromptingComboBox(wx.ComboBox) :
    def __init__(self, parent, choices=[], style=0, **par):
        wx.ComboBox.__init__(self, parent, wx.ID_ANY, style=style| \
                             wx.CB_DROPDOWN, choices=choices, **par)
        self.all_choices = choices
        self.choices = choices
        self.Bind(wx.EVT_TEXT, self.OnText)
        self.Bind(wx.EVT_KEY_DOWN, self.OnPress)
        self.ignoreEvtText = False
        self.deleteKey = False

    def OnPress(self, event):
        if event.GetKeyCode() == 8:
            self.deleteKey = True
        event.Skip()

    def OnText(self, event):
        currentText = event.GetString()
        if self.ignoreEvtText:
            self.ignoreEvtText = False
            return
        if self.deleteKey:
            self.deleteKey = False
            if self.preFound:
                currentText =  currentText[:-1]

        self.preFound = False
        l = []
        for choice in self.all_choices :
            if choice.startswith(currentText):
                l.append(choice)
        l = tuple(l)
        if l != self.choices:
            self.choices = l
            self.Freeze()
            self.Set(l)
            self.Thaw()
            
        for choice in self.all_choices :
            if choice.startswith(currentText):
                self.ignoreEvtText = True
                self.SetValue(choice)
                self.SetInsertionPoint(len(currentText))
                self.SetTextSelection(len(currentText), len(choice))
                self.preFound = True
                break

            

            



        

class Inspector(wx.Frame):
    def __init__(self, view, parent, *args, **kwds):    
        wx.Frame.__init__(self, parent, *args, title='Format',
                          style=wx.DEFAULT_FRAME_STYLE|wx.FRAME_FLOAT_ON_PARENT
                          |wx.FRAME_TOOL_WINDOW, **kwds)
        self.panel = StyleInspector(self, view, view.document.basestyles)
        framesizer = wx.BoxSizer( wx.VERTICAL )
        framesizer.Add(self.panel, 1, wx.EXPAND, 0)
        self.SetSizer(framesizer)
        self.Layout()
        framesizer.Fit(self)

    
class StyleInspector(SidePanel):
    sizes = (8, 9, 10, 12, 14, 16, 18, 20, 22, 24, 26, 30)
    _state = None

    def __init__(self, parent, view, basestyles):
        SidePanel.__init__(self, parent)
        self._view = view
        self.basestyles = basestyles
        self.add_model(view)
        self.create()
        passfocus(self, view)

    def create(self):
        view = self._view
        mainsizer = wx.BoxSizer(wx.VERTICAL)

        self.basestyle = BasestyleSelector(self, size=(-1, self.FromDIP(40)))
        self.basestyle.Bind(wx.EVT_CHOICE, self.on_basestyle)
        self.basestyle.set_stylesheet(self.basestyles)
        self.basestyle.on_redefine_style = self._redefine_style
        self.basestyle.on_create_style   = self._create_style
        self.basestyle.on_revert_style   = self._revert_style
        self.basestyle.on_rename_style   = self._rename_style
        self.basestyle.on_delete_style   = self._delete_style
        mainsizer.Add(self.basestyle, 0, wx.ALL|wx.EXPAND, self.FromDIP(5))

        notebook = wx.Notebook(self)
        notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED,
            lambda e: (e.Skip(), wx.CallAfter(view.SetFocus)))

        panel, contentsizer = make_tab(notebook, 'Style')
        choices = list(map(str, self.sizes))

        add_section("Fontstyle", panel, contentsizer)

        from .fontctrl import FontCombo
        self.family = FontCombo(panel)
        self.reset_family = ResetButton(panel, ['font_family'])
        add_row(contentsizer, self.family, self.reset_family)
        self.family.Bind(wx.EVT_COMBOBOX, self.on_family)

        self.size = wx.ComboBox(
            panel, value="12", choices=choices,
            style=wx.CB_DROPDOWN | wx.TE_PROCESS_ENTER
        )
        self.reset_size = ResetButton(panel, ['font_size'])
        self.size.SetMinSize((100, -1))
        add_row(contentsizer, self.size, self.reset_size)
        for binder in wx.EVT_TEXT_ENTER, wx.EVT_KILL_FOCUS, wx.EVT_COMBOBOX:
            self.size.Bind(binder, self.on_size)

        self.color = ColourButton(panel)
        self.bgcolor = ColourButton(panel)
        self.reset_colors = ResetButton(panel, ['color', 'bgcolor'])
        rowsizer = wx.BoxSizer(wx.HORIZONTAL)
        rowsizer.Add(self.color, 1, wx.ALL, 5)
        rowsizer.Add(self.bgcolor, 1, wx.ALL, 5)
        rowsizer.Add(self.reset_colors, 0, wx.ALL, 5)
        contentsizer.Add(rowsizer, 0, wx.EXPAND)

        self.color.callback = lambda: self.set_char_properties(
                color=self.color.get_colour())
        self.bgcolor.callback = lambda: self.set_char_properties(
                bgcolor=self.bgcolor.get_colour())

        self.underline = wx.CheckBox(panel, -1, "Underline", style=wx.CHK_3STATE)
        self.reset_underline = ResetButton(panel, ['underline'])
        add_row(contentsizer, self.underline, self.reset_underline)
        self.underline.Bind(
            wx.EVT_CHECKBOX,
            lambda e: self.set_char_properties(underline=self.underline.GetValue()))

        self.bold = wx.CheckBox(panel, -1, "Bold", style=wx.CHK_3STATE)
        self.reset_bold = ResetButton(panel, ['bold'])
        add_row(contentsizer, self.bold, self.reset_bold)
        self.bold.Bind(
            wx.EVT_CHECKBOX,
            lambda e: self.set_char_properties(bold=self.bold.GetValue()))

        self.italic = wx.CheckBox(panel, -1, "Italic", style=wx.CHK_3STATE)
        self.reset_italic = ResetButton(panel, ['italic'])
        add_row(contentsizer, self.italic, self.reset_italic)
        self.italic.Bind(
            wx.EVT_CHECKBOX,
            lambda e: self.set_char_properties(italic=self.italic.GetValue()))

        ### layout tab ###
        panel, contentsizer = make_tab(notebook, 'Layout')

        add_section("Alignment", panel, contentsizer)

        self.align = AlignBar(panel)
        self.align.Bind(EVT_BUTTONBAR, self.on_align)
        self.reset_align = ResetButton(panel, ['alignment'])
        add_row(contentsizer, self.align, self.reset_align)

        add_section("Space", panel, contentsizer)

        self.space_before = LengthInput(panel, category='typographic')
        self.reset_space_before = ResetButton(panel, ['space_before'])
        add_row2('Before paragraph', panel, contentsizer, self.space_before, self.reset_space_before)
        self.space_before.Bind(EVT_UNIT_CHANGED, self.on_space_before)

        self.space_after = LengthInput(panel, category='typographic')
        self.reset_space_after = ResetButton(panel, ['space_after'])
        add_row2('After paragraph', panel, contentsizer, self.space_after, self.reset_space_after)
        self.space_after.Bind(EVT_UNIT_CHANGED, self.on_space_after)

        self.line_spacing = FractionInput(panel)
        self.reset_line_spacing = ResetButton(panel, ['line_spacing'])
        add_row2('Relative line height', panel, contentsizer, self.line_spacing, self.reset_line_spacing)
        self.line_spacing.Bind(EVT_UNIT_CHANGED, self.on_line_spacing)

        add_section("Indentation", panel, contentsizer)

        self.indent_first = LengthInput(panel, category='typographic')
        self.reset_first = ResetButton(panel, ['first_line_indent'])
        add_row2('First line', panel, contentsizer, self.indent_first, self.reset_first)
        self.indent_first.Bind(EVT_UNIT_CHANGED, self.on_indent_first)

        ### structure tab ###
        panel, contentsizer = make_tab(notebook, 'Structure')
        self._structure_page = panel
        add_section("Indentation", panel, contentsizer)

        label = wx.StaticText(panel, label='Level')
        self.level = wx.TextCtrl(panel, value='1', size=(50, -1))
        self.level.SetEditable(False)
        self.indent = IndentBar(panel)
        self.indent.buttons['indent'].Bind(wx.EVT_BUTTON, self.on_indent)
        self.indent.buttons['dedent'].Bind(wx.EVT_BUTTON, self.on_dedent)
        _ = ResetButton(panel, ['indent'])
        add_row(contentsizer, label, self.level, self.indent, _)

        label = wx.StaticText(panel, label='Fixed indent')
        self.policy = wx.CheckBox(panel)
        self.reset_policy = ResetButton(panel, ['fixed_indent'])
        self.policy.Bind(wx.EVT_CHECKBOX, self.on_policy)
        add_row(contentsizer, label, self.policy, self.reset_policy)

        label = wx.StaticText(panel, label='Indentation')
        self.indent_position = LengthInput(panel, category='typographic')
        self.reset_indent = ResetButton(panel, ['indent_levels'])
        self.indent_position.Bind(EVT_UNIT_CHANGED, self.on_indent_position)
        add_row(contentsizer, label, self.indent_position, self.reset_indent)

        add_section("Bullets and numbers", panel, contentsizer)
        self.paragraph_type = wx.Choice(panel, choices=["Normal", "List", "Numbered"])
        self.reset_paragraph_type = ResetButton(panel, ['paragraph_type'])
        self.paragraph_type.Bind(wx.EVT_CHOICE, self.on_paragraph_type)
        add_row(contentsizer, self.paragraph_type, self.reset_paragraph_type)

        label = wx.StaticText(panel, label='List indent')
        self.list_indent = LengthInput(panel, category='typographic')
        self.reset_list_indent = ResetButton(panel, ['list_indent'])
        self.list_indent.Bind(EVT_UNIT_CHANGED, self.on_list_indent)
        add_row(contentsizer, label, self.list_indent, self.reset_list_indent)

        ### Marker properties
        spanel = self.marker_panel = wx.Panel(panel)
        spanelsizer = wx.BoxSizer(wx.VERTICAL)
        spanel.SetSizer(spanelsizer)

        add_section("Marker options", spanel, spanelsizer)

        label = wx.StaticText(spanel, label="Offset")
        self.marker_pos = LengthInput(spanel, category='typographic')
        self.reset_marker_pos = ResetButton(spanel, ['marker_pos'])
        self.marker_pos.Bind(EVT_UNIT_CHANGED, self.on_marker_pos)
        add_row(spanelsizer, label, self.marker_pos, self.reset_marker_pos)

        label = wx.StaticText(spanel, label="Color")
        self.marker_color = ColourButton(spanel)
        self.reset_marker_color = ResetButton(spanel, ['marker_color'])
        add_row(spanelsizer, label, self.marker_color, self.reset_marker_color)
        self.marker_color.callback = lambda: self.set_list_value(
            "marker_color", self.marker_color.get_colour())

        label = wx.StaticText(spanel, label="Marker size")
        self.marker_size = SpinCtrl3(
            spanel, min=1.0, max=10.0, inc=0.1, initial=1.0, digits=1)
        self.marker_size.Bind(EVT_SPIN_VALUE, self.on_marker_size)
        self.reset_marker_size = ResetButton(spanel, ['marker_size'])
        add_row(spanelsizer, label, self.marker_size, self.reset_marker_size)
        contentsizer.Add(spanel, 0, wx.EXPAND, 5)

        ### list options
        spanel = self.list_panel = wx.Panel(panel)
        spanelsizer = wx.BoxSizer(wx.VERTICAL)
        spanel.SetSizer(spanelsizer)
        add_section("List options", spanel, spanelsizer)

        label = wx.StaticText(spanel, label="Symbol")
        self.bullet = wx.Choice(spanel, choices=defaultbullets)
        self.reset_bullet = ResetButton(spanel, ['marker'])
        self.bullet.Bind(wx.EVT_CHOICE, self.on_bullet)
        add_row(spanelsizer, label, self.bullet, self.reset_bullet)
        contentsizer.Add(spanel, 0, wx.EXPAND, 5)

        ### Enumeration options
        spanel = self.enum_panel = wx.Panel(panel)
        spanelsizer = wx.BoxSizer(wx.VERTICAL)
        spanel.SetSizer(spanelsizer)
        add_section("Enumeration options", spanel, spanelsizer)

        label = wx.StaticText(spanel, label="Number format")
        self.numbering = wx.Choice(
            spanel, choices=["1,2,3", "a,b,c", "A,B,C", "i,ii,iii"])
        self.numbering.SetSelection(0)
        self.reset_numbering = ResetButton(spanel, ['numbering_style'])
        add_row(spanelsizer, label, self.numbering, self.reset_numbering)
        self.numbering.Bind(wx.EVT_CHOICE, self.on_numbering)

        label = wx.StaticText(spanel, label="Counter")
        self.counter = wx.Choice(spanel, choices=["Item", "Section"])
        self.counter.SetSelection(0)
        self.reset_counter = ResetButton(spanel, ['counter'])
        add_row(spanelsizer, label, self.counter, self.reset_counter)
        self.counter.Bind(wx.EVT_CHOICE, self.on_counter)

        self.start_check = wx.CheckBox(spanel, label="Start value")
        self.start_number = wx.TextCtrl(spanel, style=wx.TE_PROCESS_ENTER)
        self.reset_start = ResetButton(spanel, ['start_number'])
        self.start_number.Enable(False)
        add_row(spanelsizer, self.start_check, self.start_number, self.reset_start)
        self.start_check.Bind(wx.EVT_CHECKBOX, self.on_start_check)
        self.start_number.Bind(wx.EVT_KILL_FOCUS, self.on_start_number)
        self.start_number.Bind(wx.EVT_TEXT_ENTER, self.on_start_number)

        contentsizer.Add(spanel, 0, wx.EXPAND, 5)

        ### other tab ###
        panel, contentsizer = make_tab(notebook, 'Other')

        add_section("Block", panel, contentsizer)
        self.block_color = ColourButton(panel)
        self.reset_block_color = ResetButton(panel, ['block_color'])
        add_row(contentsizer, wx.StaticText(panel, label="Color"),
                self.block_color, self.reset_block_color)
        self.block_color.callback = lambda: self.set_parproperties(
            block_color=self.block_color.get_colour())

        self.block_padding = LengthInput(panel, category='typographic')
        self.reset_block_padding = ResetButton(panel, ['block_padding'])
        add_row(contentsizer, wx.StaticText(panel, label="Padding"),
                self.block_padding, self.reset_block_padding)
        self.block_padding.Bind(
            EVT_UNIT_CHANGED,
            lambda e: self.set_parproperties(
                block_padding=self.block_padding.GetValue()))

        add_section("Page break", panel, contentsizer)
        self.page_break_before = wx.CheckBox(panel, -1, "Break before",
                                             style=wx.CHK_3STATE)
        self.reset_page_break_before = ResetButton(panel, ['page_break_before'])
        add_row(contentsizer, self.page_break_before, self.reset_page_break_before)
        self.page_break_before.Bind(
            wx.EVT_CHECKBOX,
            lambda e: self.set_parproperties(
                page_break_before=self.page_break_before.GetValue()))

        add_section("Semantics", panel, contentsizer)
        self.role = wx.Choice(panel, choices=[lbl for lbl, _ in _ROLES])
        self.reset_role = ResetButton(panel, ['role'])
        add_row(contentsizer, wx.StaticText(panel, label="Role"),
                self.role, self.reset_role)
        self.role.SetSelection(0)
        self.role.Bind(wx.EVT_CHOICE, self.on_role)

        ### epilog
        mainsizer.Add(notebook, 1, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(mainsizer)

        for resetter in [
                self.reset_colors, self.reset_family, self.reset_size,
                self.reset_underline, self.reset_bold, self.reset_italic]:
            resetter.callback = self.clear_char_properties

        for resetter in [
                self.reset_align, self.reset_first, self.reset_line_spacing,
                self.reset_space_before, self.reset_space_after, self.reset_policy,
                self.reset_indent, self.reset_paragraph_type, self.reset_list_indent,
                self.reset_marker_pos, self.reset_marker_color, self.reset_marker_size,
                self.reset_bullet, self.reset_numbering, self.reset_start,
                self.reset_page_break_before, self.reset_block_color,
                self.reset_block_padding, self.reset_role]:
            resetter.callback = self.clear_parproperties

    def dpi_changed(self):
        self._state = None
        SidePanel.dpi_changed(self)

    def on_align(self, event):
        variant = event.name
        self.set_parproperties(alignment=variant)
        
    def on_indent(self, event):
        with self.model.atomic():
            for s1, s2 in self.get_parrange():
                self.model.model.increase_indent(s1, s2)

    def on_dedent(self, event):
        with self.model.atomic():
            for s1, s2 in self.get_parrange():
                self.model.model.decrease_indent(s1, s2)

    def on_policy(self, event):
        if self.policy.GetValue():
            value = self.model.model.get_indent(self.model.index)
        else:
            value = None
        self.set_parproperties(fixed_indent=value)

    def on_paragraph_type(self, event):
        i = self.paragraph_type.Selection
        value = ['normal', 'list', 'numbered'][i]
        self.set_parproperties(paragraph_type=value)

    def on_numbering(self, event):
        fmt = _NUMBERING_FORMATS[self.numbering.Selection]
        self.set_parproperties(numbering_style=(fmt,) * n_levels)

    def on_role(self, event):
        _, value = _ROLES[self.role.GetSelection()]
        self.set_parproperties(role=value)

    def on_counter(self, event):
        value = ['item', 'section'][self.counter.Selection]
        self.set_parproperties(counter=value)

    def on_start_check(self, event):
        value = self.start_check.Value
        if not value:
            self.set_parproperties(start_number=None)
        else:
            self.set_parproperties(start_number=1)
        
    def on_start_number(self, event):
        s = self.start_number.Value
        try:
            value = max(1, int(s))
        except:
            # reset to the old value
            return self.update()
        self.set_parproperties(start_number=value)

    def set_list_value(self, name, value):
        # Helper
        view = self.model
        model = view.model
        indent = model.get_indent(view.index)
        parstyle = model.get_parstyle(view.index)
        properties = self.mk_style(parstyle, {})
        fixed = properties.get('fixed_indent')
        if fixed is not None:
            indent = fixed
        l = list(properties[name])
        l[indent] = value
        self.set_parproperties(**{name:tuple(l)})

    def on_bullet(self, event):
        i = self.bullet.Selection
        self.set_list_value('marker', defaultbullets[i])

    def on_marker_size(self, event):
        value = event.Value
        self.set_list_value('marker_size', value)
                                
    def on_marker_pos(self, event):
        self.set_list_value('marker_pos', event.value)
        
    def on_indent_position(self, event):
        self.set_list_value('indent_levels', event.value)

    def on_list_indent(self, event):
        self.set_parproperties(list_indent=event.value)

    def on_indent_first(self, event):
        value = event.value
        self.set_parproperties(first_line_indent=value)

    def on_space_before(self, event):
        value = event.value
        self.set_parproperties(space_before=value)

    def on_space_after(self, event):
        value = event.value
        self.set_parproperties(space_after=value)

    def on_line_spacing(self, event):
        self.set_parproperties(line_spacing=event.value)



    def set_properties(self, **properties):
        with self.model.atomic():
            for i1, i2 in self.get_range():
                self.model.set_properties(i1, i2, **properties)

    def clear_properties(self, *keys):
        with self.model.atomic():
            for i1, i2 in self.get_range():
                self.model.clear_properties(i1, i2, *keys)

    def set_char_properties(self, **properties):
        """Apply character properties: to the selection, or to the input
        style when there is no selection."""
        ranges = self.get_range()
        if ranges == [(self.model.index, self.model.index)]:
            self.model.set_current_style(**properties)
        else:
            with self.model.atomic():
                for i1, i2 in ranges:
                    self.model.set_properties(i1, i2, **properties)

    def clear_char_properties(self, *keys):
        """Clear character properties: from the selection, or from the
        input style when there is no selection."""
        ranges = self.get_range()
        if ranges == [(self.model.index, self.model.index)]:
            self.model.clear_current_style(*keys)
        else:
            with self.model.atomic():
                for i1, i2 in ranges:
                    self.model.clear_properties(i1, i2, *keys)

    def set_parproperties(self, **properties):
        with self.model.atomic():
            for i1, i2 in self.get_parrange():
                self.model.set_parproperties(i1, i2, **properties)

    def clear_parproperties(self, *keys):
        with self.model.atomic():
            for i1, i2 in self.get_parrange():
                self.model.clear_parproperties(i1, i2, *keys)

    def on_size(self, event=None):
        try:
            font_size=float(self.size.GetValue())
        except ValueError:
            return self.update()
        self.set_char_properties(font_size=font_size)

    def on_family(self, event=None):
        name = self.family.GetFontName()
        self.set_char_properties(font_family=name)

    def on_basestyle(self, event=None):
        key = self.basestyle.GetSelectedKey()
        self.set_parproperties(base=key)

    # ------------------------------------------------------------------
    # Style menu callbacks
    # ------------------------------------------------------------------

    def _split_overrides(self, overrides):
        """Split a combined overrides set into (char_keys, par_keys).

        Reads the current char- and par-style from the model to determine
        which keys belong to which layer.
        """
        view  = self.model
        model = view.model
        index = view.index
        char_keys = set(model.get_style(max(0, index - 1)).keys()) & overrides
        par_keys  = set(model.get_parstyle(index).keys()) & overrides
        return char_keys, par_keys

    def _clear_overrides(self, overrides):
        """Remove *overrides* from the current selection in the text model.

        Each call to clear_properties / clear_parproperties adds an undo entry
        on its own.  Wrap this call inside view.atomic() to group all entries
        together with any surrounding stylesheet changes.
        """
        char_keys, par_keys = self._split_overrides(overrides)
        if char_keys:
            self.clear_properties(*char_keys)
        if par_keys:
            self.clear_parproperties(*par_keys)

    def _redefine_style(self, name, new_style, overrides):
        """Redefine an existing style and clear matching text-model overrides.

        Coordinator for the 'Redefine style from selection' action.
        Performs stylesheet update + override removal as a single atomic
        operation (one rebuild, one undo entry).
        """
        view = self.model
        old_style = view.document.basestyles.get(name).copy()
        with view.atomic():
            view.add_undo((view._undo_stylesheet, name, old_style, new_style))
            view.document.basestyles.set(name, new_style)
            self._clear_overrides(overrides - {'base'})

    def _create_style(self, new_name, new_style, overrides):
        """Create a new paragraph style and apply it to the current paragraph.

        Coordinator for the 'Create new paragraph style from selection' action.
        Performs stylesheet insert + base change + override removal as a single
        atomic operation (one rebuild, one undo entry).
        """
        view = self.model
        with view.atomic():
            # Undo entry: delete the new style (restore_to=None means delete).
            view.add_undo((view._undo_stylesheet, new_name, None, new_style))
            view.document.basestyles.set(new_name, new_style)
            for pi1, pi2 in self.get_parrange():
                self.model.set_parproperties(pi1, pi2, base=new_name)
            self._clear_overrides(overrides - {'base'})

    def _revert_style(self, overrides):
        """Remove all local overrides from the current paragraph / selection.

        Coordinator for the 'Revert to original style' action.
        Groups all override removals into one rebuild and one undo entry.
        """
        view = self.model
        with view.atomic():
            self._clear_overrides(overrides)

    def _rename_style(self, name, new_label):
        """Change the display name of a style (undo-able)."""
        view = self.model
        old_style = view.document.basestyles.get(name).copy()
        new_style = old_style.copy()
        new_style["name"] = new_label
        with view.atomic():
            view.add_undo((view._undo_stylesheet, name, old_style, new_style))
            view.document.basestyles.set(name, new_style)

    def _delete_style(self, name):
        """Delete a style and remap all uses to 'normal' (undo-able)."""
        view = self.model
        textmodel = view.model
        texel = textmodel.get_xtexel()
        old_style = view.document.basestyles.get(name).copy()
        with view.atomic():
            for j1, j2, _ in iter_newlines(texel, 0):
                if textmodel.get_parstyle(j1).get('base') == name:
                    view.set_parproperties(j1, j2, base='normal')
            # Add stylesheet undo last so it's applied first when undoing,
            # ensuring the style exists before paragraph bases are restored.
            view.add_undo((view._undo_stylesheet, name, old_style, None))
            view.document.basestyles.delete(name)

    def mk_style(self, parstyle, style):
        # Computes the style of a single run of text. Unlike the code
        # in nbview, we aggregate parstyle and textstyles. This way,
        # we can use the same code for paragraph and text
        # styles. Further we include defaultstyles which is not done
        # in nbviews (but in wxdevice).
        stylesheet = self.model.builder.stylesheet
        basestyle = stylesheet.get(parstyle.get('base', 'normal')) or {}
        r = updated(style_default, basestyle, parstyle, style)
        if not 'base' in r:
            r['base'] = 'normal'
        return r

    def get_range(self):
        """Return list of (i1, i2) ranges for the current selection.

        Returns [(index, index)] when there is no selection (cursor only).
        """
        selected = self.model.get_selected()
        if not selected:
            i = self.model.index
            return [(i, i)]
        return selected

    def get_parrange(self):
        """Return list of (i1, i2) ranges extended to cover complete lines."""
        view = self.model
        selected = view.get_selected()
        if selected:
            return [view.expand_lines(i1, i2) for i1, i2 in selected]
        i = view.index
        return [view.expand_lines(i, i)]

    _stylenames = ()

    def update(self, event=None):
        textview = self.model
        textmodel = textview.model
        
        index = textview.index
        index_style = textmodel.get_style(max(0, index-1)) # XXX warum -1 ???
        index_parstyle = textmodel.get_parstyle(index)
        index_properties = self.mk_style(index_parstyle, index_style)
        index_overrides = set(index_style.keys()).union(index_parstyle.keys())
        index_indent = textmodel.get_indent(index)


        selected = textview.get_selected()
        if selected:
            properties, overrides = collect_properties(
                textmodel, *selected[0], self.mk_style)
            indent = min(textmodel.get_indents(*selected[0]) + [index_indent])
            for s1, s2 in selected[1:]:
                p2, o2 = collect_properties(textmodel, s1, s2, self.mk_style)
                overrides |= o2
                for key in set(properties) | set(p2):
                    v1 = properties.get(key)
                    v2 = p2.get(key)
                    properties[key] = v1 if v1 == v2 else None
                indent = min(textmodel.get_indents(s1, s2) + [indent])
        else:
            current_style = textview.get_current_style()
            properties = self.mk_style(index_parstyle, current_style)
            overrides = set(current_style.keys()).union(index_parstyle.keys())
            indent = index_indent

        #print("overrides", overrides)
        #print("properties", properties)

        state = properties, overrides, indent
        if state == self._state:
            return
        self._state = state

        base = properties.get('base', 'normal')
        self.basestyle.set_properties(base, properties, overrides)
                                  
        self.color.set_colour(properties['color'])
        self.bgcolor.set_colour(properties['bgcolor'])
        x = 'color' in overrides or 'bgcolor' in overrides
        self.reset_colors.set_x(x)
            
        checkboxes_names = "underline italic bold".split()
        for name in checkboxes_names:
            widget = getattr(self, name)
            reset = getattr(self, 'reset_'+name)
            reset.set_x(name in overrides)
            value = properties[name]
            if value is None:
                widget.Set3StateValue(wx.CHK_UNDETERMINED)
            else:
                widget.SetValue(value)

        family = properties['font_family']
        self.family.SetFontName(family or '')
        x = 'font_family' in overrides
        self.reset_family.set_x(x)
        
        size = properties['font_size']
        if size is None:
            self.size.SetValue('')
        else:
            self.size.SetValue(str(size))
        x = 'font_size' in overrides
        self.reset_size.set_x(x)

        value = properties['alignment']
        if value is None:
            for name, widget in self.align.buttons.items():
                widget.Value = False
        else:
            for name, widget in self.align.buttons.items():
                state = name == value
                widget.SetValue(state)
        x = 'alignment' in overrides
        self.reset_align.set_x(x)

        value = properties['space_before']
        self.space_before.SetValue(value)
        x = 'space_before' in overrides
        self.reset_space_before.set_x(x)

        value = properties['space_after']
        self.space_after.SetValue(value)
        x = 'space_after' in overrides
        self.reset_space_after.set_x(x)

        value = properties['line_spacing']
        self.line_spacing.SetValue(value)
        x = 'line_spacing' in overrides
        self.reset_line_spacing.set_x(x)
        
        first = properties['first_line_indent']
        self.indent_first.SetValue(first)
        x = 'first_line_indent' in overrides
        self.reset_first.set_x(x)

        self.list_indent.SetValue(properties['list_indent'])
        self.reset_list_indent.set_x('list_indent' in overrides)

        fixed = properties['fixed_indent']
        if fixed is not None:
            indent = fixed
        self.level.SetValue(str(indent + 1))
        self.policy.SetValue(fixed is not None)
        x = 'fixed_indent' in overrides
        self.reset_policy.set_x(x)
        free = (fixed is None)
        if self.level.IsEnabled() != free:
            self.level.Enable(free)
            self.indent.Enable(free)

        positions = properties['indent_levels']
        if positions is None:
            self.indent_position.SetValue(None)
        else:
            pos = positions[indent]
            self.indent_position.SetValue(pos)
        x = 'indent_levels' in overrides
        self.reset_indent.set_x(x)

        markers = properties['marker']
        if markers is None:
            self.bullet.SetSelection(-1)
        else:
            marker = markers[indent]
            self.bullet.SetSelection(defaultbullets.index(marker))
        x = 'marker' in overrides
        self.reset_bullet.set_x(x)
            
        positions = properties['marker_pos']
        if positions is None:
            self.marker_pos.SetValue(None)
        else:
            pos = positions[indent]
            self.marker_pos.SetValue(pos)
        x = 'marker_pos' in overrides
        self.reset_marker_pos.set_x(x)

        colors = properties['marker_color']
        if colors is None:
            self.marker_color.set_colour(None)
        else:
            color = colors[indent]
            self.marker_color.set_colour(color)
        x = 'marker_color' in overrides
        self.reset_marker_color.set_x(x)

        sizes = properties['marker_size']
        if sizes is None:
            self.marker_size.SetValue(None)
        else:
            size = sizes[indent]
            self.marker_size.SetValue(size)
        x = 'marker_size' in overrides
        self.reset_marker_size.set_x(x)
        
        ### update paragraph_type & visibility
        try:
            i = ["normal", "list", "numbered"].index(properties[ \
                                               'paragraph_type'])
        except ValueError:
            i = -1
        self.paragraph_type.Selection = i
        x = 'paragraph_type' in overrides
        self.reset_paragraph_type.set_x(x)

        ns = properties['numbering_style']
        if ns is not None:
            fmt = ns[indent]
            try:
                self.numbering.SetSelection(_NUMBERING_FORMATS.index(fmt))
            except ValueError:
                self.numbering.SetSelection(0)
        else:
            self.numbering.SetSelection(0)
        x = 'numbering_style' in overrides
        self.reset_numbering.set_x(x)

        counter = properties.get('counter', 'item')
        self.counter.SetSelection(0 if counter != 'section' else 1)
        self.reset_counter.set_x('counter' in overrides)

        sn = properties.get('start_number')
        self.start_number.Enable(sn is not None)
        self.start_check.SetValue(sn is not None)
        if sn:
            self.start_number.SetValue(str(sn))
        else:
            self.start_number.SetValue("")
        self.reset_start.set_x('start_number' in overrides)
            
        ptype = properties['paragraph_type']
        self.marker_panel.Show(ptype in ("list", "numbered"))
        self.list_panel.Show(ptype == "list")
        self.enum_panel.Show(ptype == "numbered")
        self._structure_page.Layout()

        value = properties['page_break_before']
        if value is None:
            self.page_break_before.Set3StateValue(wx.CHK_UNDETERMINED)
        else:
            self.page_break_before.SetValue(value)
        x = 'page_break_before' in overrides
        self.reset_page_break_before.set_x(x)

        self.block_color.set_colour(properties['block_color'])
        self.reset_block_color.set_x('block_color' in overrides)

        self.block_padding.SetValue(properties['block_padding'])
        self.reset_block_padding.set_x('block_padding' in overrides)

        role = properties.get('role')
        role_values = [v for _, v in _ROLES]
        self.role.Unbind(wx.EVT_CHOICE)
        self.role.SetSelection(role_values.index(role) if role in role_values else 0)
        self.role.Bind(wx.EVT_CHOICE, self.on_role)
        self.reset_role.set_x('role' in overrides)

        self.Layout()
        
            
        
def _collect_properties(texel, i1, i2, parstyle, indent, mk_style):
    """Gibt ein Dict mit Properties zurück (values sind None wenn
    uneindeutig) und ein Set mit override den überschriebenen
    Properties.

    Indent wird hier als Property behandelt und ist auch enthalten. 

    """
    if provides_childs(texel):
        properties = dict()
        overrides = set()
        
        for j1, j2, child in reversed(list(iter_childs(texel))):
            if i1 < j2 and j1 < i2: # overlapp
                s, o, parstyle = _collect_properties(
                    child, i1-j1, i2-j1, parstyle, indent, mk_style)
                overrides.update(o)
                for key, value in s.items():
                    if not key in properties:
                        properties[key] = value
                    elif properties[key] != value:
                        properties[key] = None
    else:
        if isinstance(texel, NewLine):
            parstyle = texel.parstyle
            indent = texel.indent
        s = texel.style
        overrides = set(s.keys()).union(parstyle.keys())
        properties = mk_style(parstyle, s)
        properties['indent'] = indent
    return properties, overrides, parstyle


def _mk_style(parstyle, style):
    # Simplified style-model. For testing only.
    return updated(parstyle, style)


def collect_properties(model, i1, i2, mk_style=_mk_style):
    parstyle = model.get_parstyle(i2)
    indent = model.get_indent(i2)
    return _collect_properties(model.get_xtexel(), i1, i2, parstyle,
                               indent, mk_style)[:2]
                        

def mk_demo(redirect=False):
    from pynotebook.nbview import NBView    
    from pynotebook.nbtexels import TextCell, NULL_TEXEL, mk_textmodel, TextModel
    from pynotebook.textmodel.texeltree import T
    
    app = wx.App(redirect=redirect)
    frame = wx.Frame(None)
    win = wx.Panel(frame)
    view = NBView(win)
    model = TextModel(u"Some\ntext\n...")
    model.set_properties(1, 5, color='red')
    text = model.texel
    cell = TextCell(text)
    view.model.insert(0, mk_textmodel(cell))
    box = wx.BoxSizer(wx.VERTICAL)
    box.Add(view, 1, wx.ALL|wx.GROW, 1)
    win.SetSizer(box)
    win.SetAutoLayout(True)
    win.Show()
    frame.Show()    
    return app, view, model
    


def test_00():
    "get_parstyle" # just to be sure
    m = TextModel("Eins\nZwei\ndrei")
    m.set_parstyle(0, dict(x=1)) # -> Parstyle für "Eins\n"
    m.set_parstyle(5, dict(x=2)) # -> Parstyle für "Zwei\n"
    assert m.get_parstyle(0)['x'] == 1 # E
    assert m.get_parstyle(1)['x'] == 1 # i
    assert m.get_parstyle(2)['x'] == 1 # n
    assert m.get_parstyle(3)['x'] == 1 # s
    assert m.get_parstyle(4)['x'] == 1 # \n
    assert m.get_parstyle(5)['x'] == 2 # Z
    assert m.get_parstyle(6)['x'] == 2 # w
    
def _test_01():
    "collect styles"
    # XXX Update this
    
    m = TextModel("Eins\nZwei\ndrei")
    m.set_parstyle(0, dict(x=1)) # -> Parstyle für "Eins\n"
    #m.set_parstyle(5, dict(x=2)) # -> Parstyle für "Zwei\n"
    m.set_parstyle(11, dict(x=3)) # -> Parstyle für "Drei\n"
    #dump(m.get_xtexel())

    assert collect_properties(m, 1, 3) == \
        ({'x': 1, 'indent': 0}, {'x'})
    # base style is overriden, single value

    m.set_properties(1, 2, x=99)
    assert collect_properties(m, 1, 3) == \
        ({'x': None, 'indent': 0}, {'x'})
    # base style is overriden, multiple values for 'x'

    m.set_properties(1, 4, x=99)
    
    assert collect_properties(m, 1, 3) == \
        ({'x': 99, 'indent': 0}, set('x'))
    # base style is overriden, single value

    assert collect_properties(m, 1, 4) == \
        ({'x': 99, 'indent': 0}, set('x'))
    # base style is overriden, single value

    assert collect_properties(m, 1, 5) == \
        ({'x': None, 'indent': 0}, set('x'))
    # base style is overriden, multiple values

    print(collect_properties(m, 5, 7))
    assert collect_properties(m, 5, 7) == \
        ({'indent': 0}, set())
    # base style is not overriden, single values

    assert collect_properties(m, 4, 7) == \
        ({'x': None, 'indent': 0}, set())
    # base style is not overriden, multiple values

    
       
def demo_01():
    "alignment"
    app = wx.App(redirect=False)
    f = wx.Frame(None)
    b = AlignBar(f)
    f.Show()
    app.MainLoop()


def demo_02():
    "indent"
    app = wx.App(redirect=False)
    f = wx.Frame(None)
    b = IndentBar(f)
    f.Show()
    app.MainLoop()


    
    
