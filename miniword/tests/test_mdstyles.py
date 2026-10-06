# -*- coding: utf-8 -*-

"""
Tests for the Markdown styles (plugins/mdstyles.py), following
develnotes/markdown_menu_concept.md: presets, features (the Add/Remove
actions of the Markdown menu) and reading their state. IDs MDS-n.

Run with: python runtests.py miniword/tests/test_mdstyles.py
"""

from ..plugins.mdstyles import STYLE_NAMES, HEADINGS, FEATURES, PRESETS, \
    preset, set_feature, feature_state, set_font, font_state, set_size, \
    size_state


def test_MDS_1():
    "MDS-1: every preset defines all Markdown styles"
    for name in PRESETS:
        styles, settings = preset(name)
        assert sorted(styles) == sorted(STYLE_NAMES), name


def test_MDS_2():
    "MDS-2: a preset's font, size and features are what it declares"
    for name, (font, size, features) in PRESETS.items():
        styles, settings = preset(name)
        assert font_state(styles) == font, name
        assert size_state(styles) == size, name
        for feature in FEATURES:
            assert feature_state(styles, settings, feature) == \
                (feature in features), (name, feature)


def test_MDS_3():
    "MDS-3: code and headings aren't hyphenated; headings keep with next"
    for name in PRESETS:
        styles, settings = preset(name)
        for key in HEADINGS + ('pre',):
            assert styles[key]['hyphenate'] is False, (name, key)
        for key in HEADINGS:
            assert styles[key]['keep_with_next'] is True, (name, key)
        assert styles['pageheader']['role'] == 'header'
        assert styles['pagefooter']['role'] == 'footer'


def test_MDS_4():
    "MDS-4: each feature can be added and removed, twice gives the same"
    for name in ('github', 'book'):
        styles, settings = preset(name)
        for feature in FEATURES:
            for on in (True, False):
                s1 = set_feature(styles, settings, feature, on)
                assert feature_state(*s1, feature) is on, (name, feature)
                assert set_feature(*s1, feature, on) == s1, (name, feature)


def test_MDS_5():
    "MDS-5: a mixed state reads as None"
    styles, settings = preset('github')
    styles = dict(styles, h1=dict(styles['h1'], paragraph_type='numbered'))
    assert feature_state(styles, settings, 'section_numbers') is None
    styles, settings = preset('github')
    styles = dict(styles, body=dict(styles['body'], alignment='justify'))
    assert feature_state(styles, settings, 'justify') is None


def test_MDS_6():
    "MDS-6: features and font leave the other styles alone"
    styles, settings = preset('github')
    s2, _ = set_feature(styles, settings, 'justify', True)
    assert s2['pre'] == styles['pre']             # code stays left aligned
    s2, _ = set_feature(styles, settings, 'code_frame', True)
    assert [k for k in styles if s2[k] != styles[k]] == ['pre']
    s2 = set_font(styles, 'serif')
    assert s2['pre']['font_family'] == styles['pre']['font_family']
    assert s2['body']['font_family'] != styles['body']['font_family']


def test_MDS_7():
    "MDS-7: font and size are set and read; headings scale with the size"
    styles, settings = preset('github')                     # 12 pt
    assert font_state(set_font(styles, 'serif')) == 'serif'
    small = set_size(styles, 10)
    assert size_state(small) == 10
    assert small['body']['font_size'] == 10
    assert small['h1']['font_size'] < styles['h1']['font_size']
    mixed = dict(styles, list=dict(styles['list'], font_size=11))
    assert size_state(mixed) is None


def test_MDS_8():
    "MDS-8: hyphenation and page numbers are document settings"
    styles, settings = preset('github')
    _, s2 = set_feature(styles, settings, 'hyphenation', True)
    assert s2['hyphenation'] is True
    _, s2 = set_feature(styles, settings, 'page_numbers', False)
    assert all(s2[key][0] not in ('page', 'page_pages')
               for key in ('footer_left', 'footer_center', 'footer_right'))
    _, s3 = set_feature(styles, s2, 'page_numbers', True)
    assert s3['footer_center'] == ('page', '')


def test_MDS_9():
    "MDS-9: GitHub look: quote with a bar on the left, H1/H2 underlined"
    styles, settings = preset('github')
    quote = styles['quote']
    assert quote['block_border_sides'] == 'l'
    assert quote['block_border_width'] > 0 and quote['block_color'] is None
    for key in ('h1', 'h2'):
        assert styles[key]['block_border_sides'] == 'b', key
        assert styles[key]['block_border_width'] > 0, key


# ---------------------------------------------------------------------
# On a document: styles found by role, one undo step per action
# ---------------------------------------------------------------------

from ..core.document import Document
from ..texteditor.editor import Editor
from ..plugins.mdstyles import apply_preset, apply_feature, \
    document_state, read


def md_document(name='github'):
    """(document, editor) with the styles of preset name."""
    document = Document()
    editor = Editor(document.textmodel)
    apply_preset(editor, document, name)
    return document, editor


def test_MDS_10():
    "MDS-10: styles are found by role, whatever their name"
    document, editor = md_document()
    styles = document.basestyles
    style = styles.get('h1')
    styles.delete('h1')
    styles.set('Ueberschrift', dict(style, name='Überschrift 1'))
    apply_feature(editor, document, 'chapters', True)
    assert styles.get('Ueberschrift')['page_break_before'] is True
    assert styles.get('h1') is None  # no second h1 style
    assert document_state(document, 'chapters') is True


def test_MDS_11():
    "MDS-11: an action is one undo step, styles and settings"
    document, editor = md_document()
    n = editor.undocount()
    apply_feature(editor, document, 'hyphenation', True)
    apply_feature(editor, document, 'justify', True)
    assert editor.undocount() == n + 2
    editor.undo()
    assert document_state(document, 'justify') is False
    assert document_state(document, 'hyphenation') is True
    editor.undo()
    assert document_state(document, 'hyphenation') is False


def test_MDS_12():
    "MDS-12: an action that changes nothing adds no undo step"
    document, editor = md_document()
    n = editor.undocount()
    apply_feature(editor, document, 'quote_bar', True)  # GitHub has it
    assert editor.undocount() == n


def test_MDS_13():
    "MDS-13: a preset adds missing styles under their own name"
    document = Document()
    editor = Editor(document.textmodel)
    apply_preset(editor, document, 'technical')
    assert document.basestyles.get('pageheader')['role'] == 'header'
    assert document_state(document, 'section_numbers') is True
    editor.undo()
    assert document.basestyles.get('pageheader') is None
    assert [k for k, _ in document.basestyles.items()] == ['normal']


def test_MDS_14():
    "MDS-14: a preset keeps the document's other settings (language ...)"
    document = Document()
    editor = Editor(document.textmodel)
    document.set_setting('language', 'de-1996')
    document.set_setting('title', 'Bericht')
    apply_preset(editor, document, 'report')
    assert document.settings['language'] == 'de-1996'
    assert document.settings['title'] == 'Bericht'
    assert document.settings['header_left'] == ('title', '')


def test_MDS_15():
    "MDS-15: line spacing: GitHub 1.15, Report 1.3, Compact 1.0; code 1.0"
    for name, spacing in (('github', 1.15), ('github_small', 1.15),
                          ('report', 1.3), ('compact', 1.0)):
        styles, settings = preset(name)
        for key in ('body', 'list', 'numbered', 'quote'):
            assert styles[key]['line_spacing'] == spacing, (name, key)
        assert styles['pre']['line_spacing'] == 1.0, name


def test_MDS_16():
    "MDS-16: Markdown import gets the GitHub styles; paste no page styles"
    from ..plugins.mdfilter import _register_styles
    document = Document()
    _register_styles(document)
    assert read(document)[0] == preset('github')[0]
    document = Document()
    _register_styles(document, overwrite=False)
    assert document.basestyles.get('h1')['role'] == 'h1'
    assert document.basestyles.get('pageheader') is None


# ---------------------------------------------------------------------
# The Markdown menu
# ---------------------------------------------------------------------

from types import SimpleNamespace
from ..plugins.mdstyles import menu_items


def find(items, *path):
    """The menu entry at path of labels."""
    for label in path:
        items = next(item for item in items if item and item[0] == label)
        entry, items = items, items[1]
    return entry


def test_MDS_17():
    "MDS-17: the menu has presets, font, size and the features"
    labels = [item and item[0] for item in menu_items()]
    assert labels == [
        'Predefined', None, 'Font', 'Size', None, 'Section numbers',
        'Code frame', 'Quote bar', 'First-line indent', 'Page numbers',
        'Chapters on new page', 'Justify', 'Hyphenation']
    assert [item[0] for item in find(menu_items(), 'Size')[1]] == \
        ['10 pt', '11 pt', '12 pt']
    assert [item[0] for item in find(menu_items(), 'Justify')[1]] == \
        ['On', 'Off']


def test_MDS_18():
    "MDS-18: menu entries act on the document; no effect is greyed out"
    document, editor = md_document('github')
    frame = SimpleNamespace(document=document, editor=editor)
    add, handler, enabled = find(menu_items(), 'Section numbers', 'Add')
    remove = find(menu_items(), 'Section numbers', 'Remove')
    assert enabled(frame) and not remove[2](frame)
    handler(frame)
    assert document_state(document, 'section_numbers') is True
    assert not enabled(frame) and remove[2](frame)
    # mixed: both possible
    h1 = document.basestyles.get('h1')
    document.basestyles.set('h1', dict(h1, paragraph_type='normal'))
    assert enabled(frame) and remove[2](frame)


def test_MDS_19():
    "MDS-19: font and size entries; presets are always possible"
    document, editor = md_document('github')
    frame = SimpleNamespace(document=document, editor=editor)
    serif = find(menu_items(), 'Font', 'Serif')
    assert serif[2](frame)
    serif[1](frame)
    assert not serif[2](frame)
    assert not find(menu_items(), 'Size', '12 pt')[2](frame)
    find(menu_items(), 'Size', '10 pt')[1](frame)
    assert document.basestyles.get('body')['font_size'] == 10
    book = find(menu_items(), 'Predefined', 'Book')
    assert len(book) == 2  # no enabled function
    book[1](frame)
    assert document_state(document, 'chapters') is True


def test_MDS_20():
    "MDS-20: code and quote boxes lie on the text edges, text inside"
    from ..layout.rowfactory import block_left, block_space

    def on_edges(style):
        space = block_space(style)
        return block_left(style) == space and style['right_indent'] == space

    styles, settings = preset('github')
    assert on_edges(styles['pre']) and on_edges(styles['quote'])
    assert block_space(styles['quote']) > 3  # line and padding
    for name in PRESETS:
        styles, settings = preset(name)
        for feature, key in (('code_frame', 'pre'), ('quote_bar', 'quote')):
            for on in (True, False):
                s2, _ = set_feature(styles, settings, feature, on)
                assert on_edges(s2[key]), (name, feature, on)


def test_MDS_21():
    "MDS-21: Report's quote is indented both sides, also after Justify"
    from ..layout.rowfactory import block_space
    styles, settings = preset('report')
    quote = styles['quote']
    assert quote['right_indent'] > block_space(quote)
    s2, _ = set_feature(styles, settings, 'justify', False)
    assert s2['quote']['right_indent'] == quote['right_indent']


def test_MDS_22():
    "MDS-22: section numbers (two digits last) fit before the heading"
    from ..layout.cairodevice import CairoDevice
    from .guitest import app
    app()
    device = CairoDevice()
    for name in ('technical', 'book', 'github_small'):
        styles, settings = preset(name)
        styles, _ = set_feature(styles, settings, 'section_numbers', True)
        if name == 'github_small':
            styles = set_size(styles, 12)  # 10 → 12 pt
        for key, number in (('h1', '10 '), ('h2', '9.10 '),
                            ('h3', '9.9.10 ')):
            style = styles[key]
            width = device.measure(number, style)[0]
            assert style['marker_pos'][0] == -style['list_indent']
            assert width <= style['list_indent'], (name, key, width)
