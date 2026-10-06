# -*- coding: utf-8 -*-

"""
Tests for headers and footers, following
develnotes/header_footer_concept.md. Each test's docstring starts with
its ID (HF-n).

Run with: python runtests.py miniword/tests/test_headerfooter.py
"""

from ..core.document import settings_default
from ..core.utils import updated
from ..layout.page import field_text, header_footer
from ..layout.pagebuilder import Layout, same_continuation
from ..layout.testdevice import TestDevice
from .test_rowfactory import doc, par, lines, pages_from, small_memo, \
    page_starts


VALUES = dict(page=3, pages=10, title='Report', author='Ann',
              date='06.10.2026', chapter='Intro', section='Scope')


def settings(**kw):
    return updated(settings_default, kw)


def test_HF_1():
    "HF-1: field_text gives the text of each kind of field"
    expected = {'none': '', 'page': '3', 'page_pages': '3 / 10',
                'title': 'Report', 'author': 'Ann', 'date': '06.10.2026',
                'chapter': 'Intro', 'section': 'Scope'}
    for kind, text in expected.items():
        assert field_text((kind, 'ignored'), VALUES) == text, kind
    assert field_text(('text', 'Firm {page}'), VALUES) == 'Firm {page}'


def test_HF_2():
    "HF-2: by default only the footer shows the page number, centered"
    header, footer = header_footer(settings(), VALUES)
    assert header == ['', '', '']
    assert footer == ['', '3', '']


def test_HF_3():
    "HF-3: header_footer_first_page=False leaves the first page empty"
    s = settings(header_footer_first_page=False,
                 header_left=('title', ''))
    assert header_footer(s, dict(VALUES, page=1)) == \
        (['', '', ''], ['', '', ''])
    assert header_footer(s, dict(VALUES, page=2)) == \
        (['Report', '', ''], ['', '2', ''])


def test_HF_4():
    "HF-4: mirroring swaps left and right on even pages only"
    s = settings(header_footer_mirror=True, footer_center=('none', ''),
                 footer_right=('page', ''), header_left=('chapter', ''))
    assert header_footer(s, dict(VALUES, page=3)) == \
        (['Intro', '', ''], ['', '', '3'])
    assert header_footer(s, dict(VALUES, page=4)) == \
        (['', '', 'Intro'], ['4', '', ''])


# ---------------------------------------------------------------------
# Running heads: chapter (role h1) and section (role h2)
# ---------------------------------------------------------------------

def heads(texel, height=5):
    pages = pages_from(texel, small_memo(width=20, height=height))
    return [(page.chapter, page.section) for page in pages]


def h1(text):
    return par(text, role='h1')


def h2(text):
    return par(text, role='h2')


def body(name, n):
    return par(*lines(name, n))


def test_HF_5():
    "HF-5: a page shows the first heading on it, else the last before"
    texel = doc(h1('A'), body('a', 3),   # page 1: A
                body('b', 5),            # page 2: no heading
                h2('A1'), body('c', 3))  # page 3: A1
    assert heads(texel) == [('A', ''), ('A', ''), ('A', 'A1')]
    texel = doc(h1('A'), h1('B'), body('a', 3))
    assert heads(texel) == [('A', '')]  # the first one on the page


def test_HF_6():
    "HF-6: a new chapter clears the section"
    texel = doc(h1('A'), h2('A1'), body('a', 3),  # page 1
                body('b', 5),                     # page 2: A, A1
                h1('B'), body('c', 4),            # page 3: B, ''
                body('d', 5))                     # page 4: B, ''
    assert heads(texel) == [('A', 'A1'), ('A', 'A1'), ('B', ''), ('B', '')]


def test_HF_7():
    "HF-7: headings are found by role, not by numbering"
    numbered = dict(paragraph_type='numbered', list_indent=0)
    texel = doc(par('A', role='h1', **numbered),
                par('X', counter='section', **numbered),
                body('a', 2))
    assert heads(texel) == [('A', '')]


def test_HF_8():
    "HF-8: restarting from a page's memo gives the same running heads"
    texel = doc(h1('A'), body('a', 6), h2('A1'), body('b', 6),
                h1('B'), body('c', 6), h2('B1'), body('d', 6))
    pages = pages_from(texel, small_memo(width=20, height=5))
    starts = page_starts(pages)
    expected = [(p.chapter, p.section) for p in pages]
    for k in range(len(pages) - 1):
        again = pages_from(texel, pages[k].restartmemo, starts[k + 1])
        assert [(p.chapter, p.section) for p in again] == expected[k + 1:]


def test_HF_9():
    "HF-9: memos with different running heads don't continue the same way"
    texel = doc(h1('A'), body('a', 6))
    other = doc(h1('B'), body('a', 6))
    old = pages_from(texel, small_memo(width=20, height=5))[0].restartmemo
    new = pages_from(other, small_memo(width=20, height=5))[0].restartmemo
    assert not same_continuation(old, new)
    assert same_continuation(old, old.copy())


def test_HF_10():
    "HF-10: headers and footers don't change the page breaks"
    texel = doc(h1('A'), body('a', 7), body('b', 4))
    memo = small_memo(width=20, height=5)
    plain = pages_from(texel, memo)
    memo = small_memo(width=20, height=5)
    memo.settings = settings(header_center=('chapter', ''),
                             footer_right=('page_pages', ''))
    decorated = pages_from(texel, memo)
    assert [len(p) for p in decorated] == [len(p) for p in plain]


# ---------------------------------------------------------------------
# Pages: the texts and where they are drawn
# ---------------------------------------------------------------------

class RecordingDevice(TestDevice):
    def __init__(self):
        self.texts = []

    def draw_text(self, text, x, y, dc):
        self.texts.append((text, x, y))


def laid_out(texel, **kw):
    """Pages of texel in a Layout (numbered), height 5, border 2."""
    memo = small_memo(width=20, height=5)
    memo.border = (2, 2, 2, 2)
    memo.geometry = (24, 9)
    memo.settings = settings(**kw)
    layout = Layout([])
    for page in pages_from(texel, memo):
        layout.append_page(page)
    return layout.childs


def test_HF_11():
    "HF-11: a page's texts use its number, the page count and its heads"
    pages = laid_out(doc(h1('A'), body('a', 8)),
                     header_left=('chapter', ''),
                     footer_right=('page_pages', ''),
                     footer_center=('none', ''))
    assert len(pages) == 2
    texts = [page.header_footer_texts(date='today') for page in pages]
    assert texts == [(['A', '', ''], ['', '', '1 / 2']),
                     (['A', '', ''], ['', '', '2 / 2'])]


def test_HF_12():
    "HF-12: texts are drawn in the margins, aligned left/center/right"
    pages = laid_out(doc(body('a', 2)), header_left=('text', 'L'),
                     header_center=('text', 'CC'),
                     header_right=('text', 'RRR'),
                     footer_center=('page', ''))
    page = pages[0]
    page.device = device = RecordingDevice()
    page.draw_for_print(0, 0, None)
    drawn = {text: (x, y) for text, x, y in device.texts}
    assert drawn['L'][0] == 2                 # left margin
    assert drawn['CC'][0] == (24 - 2) / 2     # centered on the page
    assert drawn['RRR'][0] == 24 - 2 - 3      # ends at the right margin
    assert drawn['1'][0] == (24 - 1) / 2
    assert all(0 <= drawn[t][1] < 2 for t in ('L', 'CC', 'RRR'))
    assert 7 <= drawn['1'][1] < 9             # in the bottom margin
    assert 'Page 1' not in drawn              # the old fixed number is gone


def test_HF_13():
    "HF-13: header and footer settings survive saving and loading"
    import os
    import tempfile
    from ..core.document import Document
    from ..textmodel.textmodel import TextModel
    doc_ = Document()
    doc_.textmodel = TextModel("Hi")
    doc_.set_setting('header_left', ('text', 'Firm {page}'))
    doc_.set_setting('footer_center', ('page_pages', ''))
    doc_.set_setting('header_footer_mirror', True)
    with tempfile.NamedTemporaryFile(suffix='.txl', delete=False) as f:
        path = f.name
    try:
        doc_.save(path)
        loaded = Document.load(path)
        props = updated(settings_default, loaded.settings)
        assert tuple(props['header_left']) == ('text', 'Firm {page}')
        assert tuple(props['footer_center']) == ('page_pages', '')
        assert props['header_footer_mirror'] is True
    finally:
        os.unlink(path)
