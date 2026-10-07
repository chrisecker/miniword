# -*- coding: utf-8 -*-

"""
Tests for the side panels: layout and the links panel. IDs UI-n.

Run with: python runtests.py miniword/tests/test_panels.py
"""

from contextlib import contextmanager

import wx

from .guitest import app, click


@contextmanager
def main_frame(text=''):
    from ..core.document import Document
    from ..ui.mainwindow import MainFrame
    app()
    document = Document()
    document.textmodel.insert_text(0, text)
    frame = MainFrame(document)
    try:
        yield frame
    finally:
        frame.Destroy()


def labels(window):
    """The texts of window's static texts."""
    return [w.GetLabel() for w in window.GetChildren()
            if isinstance(w, wx.StaticText)]


def test_UI_1():
    "UI-1: the outline has a header and explains itself without headings"
    with main_frame('Nur Text\n') as frame:
        panel = frame._outline_panel
        assert 'CONTENTS' in labels(panel)
        panel.update()
        assert panel.hint.IsShown()
        model = frame.document.textmodel
        model.set_parstyle(0, dict(base='h1'))
        from ..core.styles import style_default
        frame.document.basestyles.set('h1', dict(style_default, role='h1',
                                                 fixed_indent=0))
        panel.update()
        assert not panel.hint.IsShown()


def test_UI_2():
    "UI-2: table borders are flat icon buttons with some space between"
    from ..ui.flatbutton import FlatButton
    with main_frame() as frame:
        panel = frame.table_panel
        assert all(isinstance(b, FlatButton) and b.icon
                   for b in panel._border_btns)
        grid = panel._border_btns[0].GetContainingSizer()
        assert grid.GetHGap() >= panel.FromDIP(4)


def test_UI_3():
    "UI-3: image size and scale share a row; crop, export as icons"
    from ..ui.flatbutton import FlatButton, FlatToggle
    with main_frame() as frame:
        panel = frame.image_inspector
        assert panel.btn_insert.GetLabel() == 'Image \u25be'
        grid = panel.txt_size_x.GetContainingSizer()  # one grid for both
        for widget in (panel.txt_scale_x, panel.txt_size_y,
                       panel.txt_scale_y):
            assert widget.GetContainingSizer() is grid
        assert grid.GetCols() == 4  # label, size, scale, x
        from ..ui.sidepanel import PANEL_W
        # fits: the panel minus the margins (make_panel 2 x 8, row 2 x 5)
        assert grid.GetMinSize()[0] <= panel.FromDIP(PANEL_W - 16 - 10)
        assert isinstance(panel.chk_proportional, wx.CheckBox)
        row = panel.chk_proportional.GetContainingSizer()  # below, labelled
        assert row is not grid
        assert 'Keep aspect ratio' in [
            item.GetWindow().GetLabel() for item in row.GetChildren()
            if isinstance(item.GetWindow(), wx.StaticText)]
        assert isinstance(panel.btn_crop, FlatToggle)
        assert 'crop' in panel.btn_crop.icon
        assert isinstance(panel.btn_export, FlatButton)
        assert 'download' in panel.btn_export.icon
        assert 'Scale' not in labels(panel)
        from ..ui.flatbutton import ResetButton
        assert isinstance(panel.btn_unset_crop, ResetButton)
        for label, *buttons in (('Crop', panel.btn_crop,
                                 panel.btn_unset_crop),
                                ('Export', panel.btn_export)):
            text, = [w for w in panel.GetChildren()
                     if isinstance(w, wx.StaticText)
                     and w.GetLabel() == label]
            assert text.GetFont().GetWeight() == wx.FONTWEIGHT_BOLD
            for button in buttons:  # in the label's row
                assert button.GetContainingSizer() is \
                    text.GetContainingSizer(), label


def test_UI_4():
    "UI-4: a flat toggle keeps its state and sends a toggle event"
    from ..ui.flatbutton import FlatToggle
    app()
    frame = wx.Frame(None)
    try:
        toggle = FlatToggle(frame, '', icon='crop_24dp_1F1F1F.svg')
        values = []
        toggle.Bind(wx.EVT_TOGGLEBUTTON, lambda e: values.append(e.GetInt()))
        click(toggle, True)
        assert toggle.GetValue() is True and values == [1]
        click(toggle, False)
        assert values == [1, 0]
    finally:
        frame.Destroy()


def test_UI_5():
    "UI-5: the search's up/down buttons are as narrow as a spinner's"
    from ..ui.unitentry import LengthInput
    with main_frame() as frame:
        search = frame._search_panel
        spinner = LengthInput(frame.image_inspector)
        up, down = [c for c in spinner.GetChildren()
                    if getattr(c, 'label', None) in ('▲', '▼')]
        assert search.btn_prev.GetMinSize()[0] == up.GetMinSize()[0]
        assert search.btn_next.GetMinSize()[0] == down.GetMinSize()[0]


def test_UI_6():
    "UI-6: inline sections (Crop, Export) have the space of a section"
    with main_frame() as frame:
        panel = frame.image_inspector
        content = panel.btn_crop.GetContainingSizer().GetContainingWindow() \
            .GetSizer().GetChildren()[-1].GetSizer()  # make_panel's content
        items = content.GetChildren()
        for button in (panel.btn_crop, panel.btn_export):
            row = button.GetContainingSizer()
            k = [item.GetSizer() for item in items].index(row)
            before = items[k - 1]
            assert before.IsSpacer(), button
            assert before.GetMinSize()[1] >= panel.FromDIP(10), button


def test_UI_7():
    "UI-7: table panel: header row labelled left, cell rows with a reset x"
    from ..ui.flatbutton import ResetButton
    with main_frame() as frame:
        panel = frame.table_panel
        assert panel._chk_header.GetLabel() == ''
        row = panel._chk_header.GetContainingSizer()
        assert 'Header row' in [
            item.GetWindow().GetLabel() for item in row.GetChildren()
            if isinstance(item.GetWindow(), wx.StaticText)]
        for widget, reset in ((panel._bgcolor_btn, panel._reset_bgcolor),
                              (panel._valign, panel._reset_valign)):
            assert isinstance(reset, ResetButton)
            assert reset.GetContainingSizer() is \
                widget.GetContainingSizer()


def test_UI_8():
    "UI-8: links panel: footnotes and hyperlink one below the other"
    with main_frame() as frame:
        panel = frame._links_panel
        assert not [w for w in panel.GetChildren()
                    if isinstance(w, wx.Notebook)]
        for widget in (panel.numbering, panel.label_ctrl, panel.url_ctrl):
            assert widget.GetParent() is panel
        texts = labels(panel)
        assert 'Footnotes' in texts and 'Hyperlink' in texts
        row = panel.url_ctrl.GetContainingSizer()  # the field fills it
        assert row.GetItem(panel.url_ctrl).GetProportion() == 1


def test_UI_9():
    "UI-9: links panel: the cursor in a link shows its URL; x removes it"
    from .guitest import click_button
    with main_frame('see the docs here\n') as frame:
        panel, editor = frame._links_panel, frame.editor
        model = frame.document.textmodel
        editor.selection = (4, 12)  # "the docs"
        editor.set_properties(href='https://x.org', underline=True)
        editor.selection = None
        editor.set_index(6)  # in the link, no selection
        panel.update()
        assert panel.url_ctrl.IsEnabled()
        assert panel.url_ctrl.GetValue() == 'https://x.org'
        assert model.get_style(6).get('underline')
        click_button(panel.reset_url)  # removes the link and its underline
        assert all(not model.get_style(j).get('href')
                   and not model.get_style(j).get('underline')
                   for j in range(len(model.get_text())))


def test_UI_10():
    "UI-10: links panel: x removes the link of a selection"
    from .guitest import click_button
    with main_frame('see the docs here\n') as frame:
        panel, editor = frame._links_panel, frame.editor
        model = frame.document.textmodel
        editor.selection = (4, 12)
        editor.set_properties(href='https://x.org', underline=True)
        panel.update()
        assert panel.url_ctrl.GetValue() == 'https://x.org'
        click_button(panel.reset_url)
        assert all(not model.get_style(j).get('href')
                   and not model.get_style(j).get('underline')
                   for j in range(4, 12))


def test_UI_11():
    "UI-11: a panel header shows '&' literally (Find & Replace)"
    with main_frame() as frame:
        texts = [w.GetLabelText() for w in frame._search_panel.GetChildren()
                 if isinstance(w, wx.StaticText)]
        assert 'FIND & REPLACE' in texts


def test_UI_12():
    "UI-12: side strip order: format, navigate, document"
    with main_frame() as frame:
        assert list(frame._strip._key_to_btn) == [
            'style', 'table', 'image', 'links', 'outline', 'search',
            'settings']


def test_UI_13():
    "UI-13: links panel: a selection with text and links shows the x"
    from .guitest import click_button
    with main_frame('see the docs here\n') as frame:
        panel, editor = frame._links_panel, frame.editor
        model = frame.document.textmodel
        for j1, j2, url in ((4, 7, 'https://a.org'), (8, 12, 'https://b.org')):
            editor.selection = (j1, j2)
            editor.set_properties(href=url, underline=True)
        editor.selection = (0, 17)  # starts with plain text
        panel.update()
        assert panel.reset_url.label  # the x is shown
        assert panel.url_ctrl.GetValue() == ''
        click_button(panel.reset_url)
        assert all(not model.get_style(j).get('href') for j in range(17))
        editor.selection = (8, 12)  # one link: its URL
        editor.set_properties(href='https://b.org')
        panel.update()
        assert panel.url_ctrl.GetValue() == 'https://b.org'
