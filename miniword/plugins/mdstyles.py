# -*- coding: utf-8 -*-

"""
Markdown styles: presets, features (the Add/Remove actions of the
Markdown menu) and reading their state - pure functions on styles
{name: style} and settings, returning new dicts; then applying them to
a document, and the menu. See develnotes/markdown_menu_concept.md.
"""

from ..core.styles import style_default, updated, n_levels
from ..core.document import settings_default, undo_setting
from ..core.stylesheet import undo_basestyle_change
from ..layout.rowfactory import block_space

MM = 72 / 25.4
HEADINGS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')
TEXT = ('body', 'list', 'numbered', 'quote')  # running text
STYLE_NAMES = ('body',) + HEADINGS + ('pre', 'list', 'numbered', 'quote',
                                      'pageheader', 'pagefooter')
FONTS = {'sans': 'Arial', 'serif': 'Times New Roman'}
MONO = 'Courier New'
LINE = '#d0d7de'  # grey lines (code frame, quote bar, heading rules)

# heading font size relative to the body (as on github.com)
HEADING_SIZE = dict(h1=2.0, h2=1.5, h3=1.17, h4=1.0, h5=0.92, h6=0.83)

FEATURES = ('section_numbers', 'code_frame', 'quote_bar',
            'first_line_indent', 'page_numbers', 'chapters', 'justify',
            'hyphenation')

# name: (font, size, features)
PRESETS = {
    'github':       ('sans', 12, {'quote_bar', 'page_numbers'}),
    'github_small': ('sans', 10, {'quote_bar', 'page_numbers'}),
    'report':       ('serif', 12, {'justify', 'hyphenation',
                                   'first_line_indent', 'page_numbers'}),
    'compact':      ('sans', 10, {'hyphenation', 'page_numbers'}),
    'book':         ('serif', 11, {'justify', 'hyphenation',
                                   'first_line_indent', 'chapters',
                                   'page_numbers'}),
    'technical':    ('sans', 11, {'section_numbers', 'code_frame',
                                  'quote_bar', 'page_numbers'}),
}


def _inset(style, extra=0):
    """style with its box on the text edges: the text moves in by the
    box's padding and line (as on github.com), plus extra."""
    space = block_space(style) + extra
    levels = style_default['indent_levels']
    return dict(style, right_indent=space,
                indent_levels=tuple(x + space for x in levels))


def _space(size, compact):
    """Space after running text."""
    return 2 if compact else round(size / 2)


def _base(font, size, compact=False):
    """Styles in font and size, without features."""
    family = FONTS[font]
    spacing = 1.0 if compact else 1.15
    text = dict(font_family=family, font_size=size, line_spacing=spacing)
    props = {
        'body': dict(text, name='Body', role='body',
                     space_after=_space(size, compact)),
        'pre': dict(name='Code', role='pre', font_family=MONO,
                    font_size=max(8, round(size * 0.83)), hyphenate=False,
                    block_color='#F6F8FA', block_offset=2 * MM * size / 12),
        'list': dict(text, name='List', role='list', space_after=0,
                     paragraph_type='list'),
        'numbered': dict(text, name='Numbered', role='numbered',
                         space_after=0, paragraph_type='numbered'),
        'quote': dict(text, name='Quote', role='quote',
                      block_color='#F0F0F0',
                      block_offset=2 * MM * size / 12),
        'pageheader': dict(name='Page header', role='header',
                           font_family=family, font_size=round(size * .75),
                           color='#606060'),
        'pagefooter': dict(name='Page footer', role='footer',
                           font_family=family, font_size=round(size * .75),
                           color='#606060'),
    }
    for level, key in enumerate(HEADINGS):
        before = size * (0.5 if compact else 1.0) * (1 if level < 3 else .5)
        props[key] = dict(
            name='Heading %d' % (level + 1), role=key, font_family=family,
            font_size=round(size * HEADING_SIZE[key]), bold=level != 5,
            italic=level in (3, 5), space_before=round(before),
            space_after=round(before / 2), fixed_indent=level,
            indent_levels=(0,) * n_levels, counter='section',
            hyphenate=False, keep_with_next=True)
    styles = {key: updated(style_default, p) for key, p in props.items()}
    for key in ('pre', 'quote'):
        styles[key] = _inset(styles[key])
    return styles


def preset(name, settings=settings_default):
    """(styles, settings) of a preset; settings it doesn't define (title,
    language, margins ...) are taken from settings."""
    font, size, features = PRESETS[name]
    styles = _base(font, size, compact=name == 'compact')
    settings = dict(settings, header_left=('none', ''),
                    header_center=('none', ''), header_right=('none', ''),
                    footer_left=('none', ''), footer_center=('page', ''),
                    footer_right=('none', ''))
    for feature in FEATURES:
        styles, settings = set_feature(styles, settings, feature,
                                       feature in features)
    if name.startswith('github'):  # rules below H1/H2, as on github.com
        for key in ('h1', 'h2'):
            styles[key] = dict(styles[key], block_border_width=0.75,
                               block_border_sides='b',
                               block_border_color=LINE)
    if name == 'report':  # header: title and chapter; page x / y
        settings.update(header_left=('title', ''),
                        header_right=('chapter', ''),
                        footer_center=('none', ''),
                        footer_right=('page_pages', ''))
        styles = _changed(styles, TEXT, line_spacing=1.3)
        quote = dict(styles['quote'], block_color=None, italic=True)
        styles['quote'] = _inset(quote, 5 * MM)  # indented both sides
    return styles, settings


def _changed(styles, keys, **props):
    """styles with props set in the styles keys."""
    new = dict(styles)
    for key in keys:
        new[key] = dict(styles[key], **props)
    return new


def _state(values):
    """True if all values are true, False if none, else None."""
    values = [bool(v) for v in values]
    return all(values) or (None if any(values) else False)


FOOTER = ('footer_left', 'footer_center', 'footer_right')
PAGE_KINDS = ('page', 'page_pages')


def _number_room(level, size):
    """Room for a heading's number at the text edge, the text after it:
    two digits in the last number (em widths of digit and dot)."""
    width = size * (0.56 * (level + 2) + 0.28 * level + 0.4)
    return dict(list_indent=width, marker_pos=(-width,) * n_levels)


def set_feature(styles, settings, feature, on):
    """(styles, settings) with feature added (on) or removed."""
    settings = dict(settings)
    size = styles['body']['font_size']
    if feature == 'section_numbers':
        for level, key in enumerate(HEADINGS[:3]):  # 1 / 1.1 / 1.1.1
            style = ('1', '1.1', '1.1.1')[level]
            styles = _changed(
                styles, [key],
                paragraph_type='numbered' if on else 'normal',
                numbering_style=(style,) * n_levels,
                **_number_room(level, styles[key]['font_size']))
    elif feature == 'code_frame':
        styles = dict(styles, pre=_inset(dict(
            styles['pre'], block_border_width=0.75 if on else 0,
            block_border_color=LINE)))
    elif feature == 'quote_bar':
        styles = dict(styles, quote=_inset(dict(
            styles['quote'], block_border_width=3 if on else 0,
            block_border_sides='l', block_border_color=LINE,
            block_color=None if on else '#F0F0F0',
            color='#59636e' if on else 'black')))
    elif feature == 'first_line_indent':
        styles = _changed(styles, ['body'],
                          first_line_indent=size if on else 0,
                          space_after=0 if on else _space(size, False))
    elif feature == 'chapters':
        styles = _changed(styles, ['h1'], page_break_before=on)
    elif feature == 'justify':
        styles = _changed(styles, TEXT,
                          alignment='justify' if on else 'left')
    elif feature == 'hyphenation':
        settings['hyphenation'] = on
    elif feature == 'page_numbers':
        if not on:
            for key in FOOTER:
                if settings[key][0] in PAGE_KINDS:
                    settings[key] = ('none', '')
        elif feature_state(styles, settings, feature) is False:
            settings['footer_center'] = ('page', '')
    else:
        raise KeyError(feature)
    return styles, settings


def feature_state(styles, settings, feature):
    """True, False or None (mixed) for a feature."""
    if feature == 'section_numbers':
        return _state(styles[key]['paragraph_type'] == 'numbered'
                      for key in HEADINGS[:3])
    if feature == 'code_frame':
        return bool(styles['pre']['block_border_width'])
    if feature == 'quote_bar':
        quote = styles['quote']
        return bool(quote['block_border_width']) \
            and quote['block_border_sides'] == 'l'
    if feature == 'first_line_indent':
        return bool(styles['body']['first_line_indent'])
    if feature == 'chapters':
        return bool(styles['h1']['page_break_before'])
    if feature == 'justify':
        return _state(styles[key]['alignment'] == 'justify'
                      for key in TEXT)
    if feature == 'hyphenation':
        return bool(settings['hyphenation'])
    if feature == 'page_numbers':
        return any(settings[key][0] in PAGE_KINDS for key in FOOTER)
    raise KeyError(feature)


def set_font(styles, font):
    """styles in font (a key of FONTS); code keeps its monospace font."""
    keys = [k for k in styles if k != 'pre']
    return _changed(styles, keys, font_family=FONTS[font])


def font_state(styles):
    """The font of all styles but code, None if mixed."""
    families = {styles[k]['font_family'] for k in styles if k != 'pre'}
    fonts = [f for f, family in FONTS.items() if {family} == families]
    return fonts[0] if fonts else None


def set_size(styles, size):
    """styles for body size; headings, code, header and footer scale."""
    new = _changed(styles, TEXT, font_size=size)
    for level, key in enumerate(HEADINGS):
        font_size = round(size * HEADING_SIZE[key])
        new = _changed(new, [key], font_size=font_size,
                       **_number_room(level, font_size))
    new = _changed(new, ['pre'], font_size=max(8, round(size * 0.83)))
    return _changed(new, ['pageheader', 'pagefooter'],
                    font_size=round(size * .75))


def size_state(styles):
    """The size of running text, None if mixed."""
    sizes = {styles[key]['font_size'] for key in TEXT}
    return sizes.pop() if len(sizes) == 1 else None


# ---------------------------------------------------------------------
# On a document: styles are found by their role, each action is one
# undo step
# ---------------------------------------------------------------------

ROLES = dict({name: name for name in STYLE_NAMES},  # {name: role}
             pageheader='header', pagefooter='footer')


def read(document):
    """(styles, settings) of document; a style is found by its role,
    a missing one is plain."""
    keys = role_keys(document)
    styles = {name: updated(style_default,
                            document.basestyles.get(keys.get(role)) or {})
              for name, role in ROLES.items()}
    return styles, updated(settings_default, document.settings)


def role_keys(document):
    """{role: key of the first style with it}"""
    keys = {}
    for key, style in document.basestyles.items():
        keys.setdefault(style.get('role'), key)
    return keys


def apply(editor, document, styles, settings):
    """Set the styles and settings that differ, as one undo step; a
    style is replaced where its role is, or added under its name."""
    old_styles, old_settings = read(document)
    keys = role_keys(document)
    with editor.atomic():
        for name, style in styles.items():
            if style == old_styles[name]:
                continue
            key = keys.get(ROLES[name], name)
            old = document.basestyles.get(key)
            editor.add_undo((undo_basestyle_change, document.basestyles,
                             key, old and dict(old), style))
            document.basestyles.set(key, style)
        for name, value in settings.items():
            if value != old_settings[name]:
                editor.add_undo(undo_setting(document, name, value))


def apply_preset(editor, document, name):
    apply(editor, document, *preset(name, read(document)[1]))


def apply_feature(editor, document, feature, on):
    apply(editor, document, *set_feature(*read(document), feature, on))


def document_state(document, feature):
    """True, False or None (mixed) for a feature of document."""
    return feature_state(*read(document), feature)


# ---------------------------------------------------------------------
# The Markdown menu (see ui/mainwindow.plugin_menu); entries without
# effect are greyed out
# ---------------------------------------------------------------------

PRESET_LABELS = [('GitHub', 'github'), ('GitHub Small', 'github_small'),
                 ('Report', 'report'), ('Compact', 'compact'),
                 ('Book', 'book'), ('Technical', 'technical')]
FEATURE_LABELS = [  # (label, feature, labels for on and off)
    ('Section numbers', 'section_numbers', 'Add', 'Remove'),
    ('Code frame', 'code_frame', 'Add', 'Remove'),
    ('Quote bar', 'quote_bar', 'Add', 'Remove'),
    ('First-line indent', 'first_line_indent', 'Add', 'Remove'),
    ('Page numbers', 'page_numbers', 'Add', 'Remove'),
    ('Chapters on new page', 'chapters', 'On', 'Off'),
    ('Justify', 'justify', 'On', 'Off'),
    ('Hyphenation', 'hyphenation', 'On', 'Off')]
SIZES = (10, 11, 12)


def menu_items():
    """Items of the Markdown menu; handlers take the main window."""
    def entry(label, change, state, value):
        """change(styles, settings, value) -> (styles, settings);
        state(styles, settings) -> value: greyed out if equal."""
        def run(frame):
            apply(frame.editor, frame.document,
                  *change(*read(frame.document), value))
        return label, run, lambda f: state(*read(f.document)) != value

    def font(styles, settings, value):
        return set_font(styles, value), settings

    def size(styles, settings, value):
        return set_size(styles, value), settings

    items = [('Predefined', [
        (label, lambda f, name=name: apply_preset(f.editor, f.document,
                                                  name))
        for label, name in PRESET_LABELS]), None,
        ('Font', [entry(label, font, lambda s, t: font_state(s), value)
                  for label, value in (('Sans', 'sans'),
                                       ('Serif', 'serif'))]),
        ('Size', [entry('%d pt' % value, size,
                        lambda s, t: size_state(s), value)
                  for value in SIZES]), None]
    for label, feature, on, off in FEATURE_LABELS:
        def change(s, t, value, feature=feature):
            return set_feature(s, t, feature, value)

        def state(s, t, feature=feature):
            return feature_state(s, t, feature)
        items.append((label, [entry(on, change, state, True),
                              entry(off, change, state, False)]))
    return items
