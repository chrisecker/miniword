# -*- coding: utf-8 -*-

"""
Tests for the inspector panels: style inspector (INS-n) and document
settings (SET-n).

Run with: python runtests.py miniword/tests/test_inspector.py
"""

import wx

from ..textmodel.textmodel import TextModel
from .guitest import style_inspector, settings_inspector, click, choose, \
    enter


# ---------------------------------------------------------------------
# INS - style inspector
# ---------------------------------------------------------------------

# check boxes for paragraph properties: (inspector attribute, property,
# default)
PAR_CHECKBOXES = [
    ('hyphenate',         'hyphenate',            True),
    ('keep_with_next',    'keep_with_next',       False),
    ('widow_orphan',      'widow_orphan_control', True),
    ('page_break_before', 'page_break_before',    False),
]


def test_INS_1():
    "INS-1: get_parstyle gives the style of the paragraph at every index"
    m = TextModel("Eins\nZwei\ndrei")
    m.set_parstyle(0, dict(x=1))  # "Eins\n"
    m.set_parstyle(5, dict(x=2))  # "Zwei\n"
    assert [m.get_parstyle(i)['x'] for i in range(7)] == [1] * 5 + [2] * 2


def test_INS_2():
    "INS-2: paragraph check boxes show and set their property"
    for attr, key, default in PAR_CHECKBOXES:
        with style_inspector() as (inspector, model, editor):
            checkbox = getattr(inspector, attr)
            assert bool(checkbox.GetValue()) == default, attr
            click(checkbox, not default)
            assert model.get_parstyle(0)[key] is (not default), attr
            inspector.update()
            assert bool(checkbox.GetValue()) == (not default), attr


def test_INS_3():
    "INS-3: different values in the selection show as undetermined"
    for attr, key, default in PAR_CHECKBOXES:
        with style_inspector() as (inspector, model, editor):
            model.set_parstyle(0, {key: not default})
            # also different border sides (None in properties)
            model.set_parstyle(5, dict(block_border_sides='tb'))
            editor.selection = (0, len(model))
            inspector.update()
            checkbox = getattr(inspector, attr)
            assert checkbox.Get3StateValue() == wx.CHK_UNDETERMINED, attr


def test_INS_4():
    "INS-4: border line color and sides: greyed out without a line"
    with style_inspector() as (inspector, model, editor):
        sides = inspector.block_border_sides
        assert not inspector.block_border_color.IsEnabled()
        assert not sides.IsEnabled()
        inspector.set_parproperties(block_border_width=1,
                                    block_border_sides='tb')
        inspector.update()
        assert inspector.block_border_color.IsEnabled()
        assert [b.GetValue() for b in sides.buttons.values()] == \
            [True, True, False, False]  # t, b, l, r
        click(sides.buttons['l'], True)
        assert model.get_parstyle(0)['block_border_sides'] == 'tbl'


def test_INS_5():
    "INS-5: a tab higher than the window scrolls, its rows aren't squeezed"
    with style_inspector(size=(330, 400)) as (inspector, model, editor):
        model.set_parstyle(0, dict(paragraph_type='list'))
        inspector.GetParent().Layout()
        inspector.update()
        page = inspector._structure_page  # Layout tab, list options shown
        assert page.GetVirtualSize()[1] > page.GetClientSize()[1]
        for field in (inspector.indent_position, inspector.list_indent,
                      inspector.right_indent):
            assert field.GetSize()[1] >= field.GetBestSize()[1]


# ---------------------------------------------------------------------
# SET - document settings
# ---------------------------------------------------------------------

def test_SET_1():
    "SET-1: custom paper width and height are set"
    with settings_inspector() as (inspector, document):
        choose(inspector.choice_paper, 'custom')
        inspector.inp_width.text.SetValue("100 mm")
        inspector.inp_width._commit()
        wx.GetApp().ProcessPendingEvents()
        assert abs(document.settings['paper_width'] - 100 * 72 / 25.4) \
            < 1e-9


def test_SET_2():
    "SET-2: a header/footer field is chosen from a pulldown"
    with settings_inspector() as (inspector, document):
        choice, text = inspector.fields['footer_center']
        assert choice.GetStringSelection() == 'Page number'
        assert not text.IsShown()
        choose(inspector.fields['header_left'][0], 'Chapter')
        assert document.settings['header_left'] == ('chapter', '')
        choose(choice, '(none)')
        assert document.settings['footer_center'] == ('none', '')


def test_SET_3():
    "SET-3: 'Text' shows a text field; its text stays when the kind changes"
    with settings_inspector() as (inspector, document):
        choice, text = inspector.fields['header_right']
        choose(choice, 'Text')
        assert text.IsShown()
        enter(text, 'Firm {page}')
        assert document.settings['header_right'] == ('text', 'Firm {page}')
        choose(choice, 'Date')
        assert not text.IsShown()
        assert document.settings['header_right'] == ('date', 'Firm {page}')
        choose(choice, 'Text')
        assert text.GetValue() == 'Firm {page}'
        assert document.settings['header_right'] == ('text', 'Firm {page}')


def test_SET_4():
    "SET-4: first page and mirror are check boxes"
    with settings_inspector() as (inspector, document):
        assert inspector.chk_first_page.GetValue()
        assert not inspector.chk_mirror.GetValue()
        click(inspector.chk_first_page, False)
        click(inspector.chk_mirror, True)
        assert document.settings['header_footer_first_page'] is False
        assert document.settings['header_footer_mirror'] is True


def test_SET_5():
    "SET-5: the panel shows settings changed elsewhere (undo, loading)"
    with settings_inspector() as (inspector, document):
        document.set_setting('footer_left', ('text', 'Draft'))
        document.set_setting('header_footer_mirror', True)
        inspector.update()
        choice, text = inspector.fields['footer_left']
        assert choice.GetStringSelection() == 'Text'
        assert text.IsShown() and text.GetValue() == 'Draft'
        assert inspector.chk_mirror.GetValue()


def test_SET_6():
    "SET-6: language pulldown and hyphenation check box"
    with settings_inspector() as (inspector, document):
        assert inspector.choice_language.GetStringSelection() == \
            'English (US)'
        assert not inspector.chk_hyphenation.GetValue()
        choose(inspector.choice_language, 'German')
        click(inspector.chk_hyphenation, True)
        assert document.settings['language'] == 'de-1996'
        assert document.settings['hyphenation'] is True
        document.set_setting('language', 'en-us')
        inspector.update()
        assert inspector.choice_language.GetStringSelection() == \
            'English (US)'


def test_SET_7():
    "SET-7: Hyphenation is greyed out for a language without patterns"
    with settings_inspector() as (inspector, document):
        assert inspector.chk_hyphenation.IsEnabled()
        document.set_setting('language', 'fr')  # e.g. from another file
        inspector.update()
        assert inspector.choice_language.GetSelection() == -1
        assert not inspector.chk_hyphenation.IsEnabled()
        choose(inspector.choice_language, 'German')
        inspector.update()
        assert inspector.chk_hyphenation.IsEnabled()
