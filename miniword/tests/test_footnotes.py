# -*- coding: utf-8 -*-

"""
Tests for footnotes nested in footnotes (editing, numbering, layout),
following develnotes/footnote_tests.md. Each test's docstring starts
with its ID from that list.

Run with: python runtests.py miniword/tests/test_footnotes.py

The footnote flow (flow 1) holds the contents of all footnotes, one
after the other, in the order RowFactory lays them out: a footnote,
then the footnotes nested in its content, then the next one (see
footnotes.iter_footnotes).
"""

import wx

from ..textmodel.textmodel import TextModel
from ..textmodel.texeltree import T, G, grouped, ENDMARK, NewLine
from ..textmodel.utils import iter_leafes
from ..textmodel.submodel import Footnote, _get_text
from ..texteditor.editor import TwoFlowEditor
from ..footnotes.footnotes import iter_footnotes
from ..layout.pagebuilder import PageBuilder
from ..layout.rowfactory import Factory
from ..layout.boxes import TextBox
from ..core.stylesheet import testsheet


def fnote(*items):
    """A footnote whose content is items (strings become Text)."""
    texels = [T(item) if isinstance(item, str) else item for item in items]
    return Footnote(grouped(texels + [ENDMARK]))


def mk_model(*items):
    """A TextModel of items (strings become Text), ending with ENDMARK."""
    texels = [T(item) if isinstance(item, str) else item for item in items]
    model = TextModel()
    model.set_xtexel(grouped(texels + [ENDMARK]))
    return model


def mk_editor(model):
    editor = TwoFlowEditor()
    editor.root = model
    return editor


def text(model):
    """Main text with footnote contents in brackets."""
    return _get_text(model.texel)


def offsets(model):
    return [offset for offset, _, _ in iter_footnotes(model.texel)]


def footnotes(model):
    return [chain[-1][1] for _, chain, _ in iter_footnotes(model.texel)]


def type_at(editor, flow_index, s):
    """Type s at position flow_index of the footnote flow."""
    editor.switch_target(1, flow_index)
    editor.index = editor.local_idx(flow_index)
    editor.insert_text(s)


def three_levels():
    """'ab[x[y[z]]]cd[w]': F1 = 'x[F2]', F2 = 'y[F3]', F3 = 'z',
    F4 = 'w'. Flow: F1 0..3, F2 3..6, F3 6..8, F4 8..10."""
    f3 = fnote('z')
    f2 = fnote('y', f3)
    f1 = fnote('x', f2)
    return mk_model('ab', f1, 'cd', fnote('w'))


def test_NFN_1():
    "NFN-1: typing at every level of three nested footnotes, and undo"
    model = three_levels()
    assert text(model) == 'ab[x[y[z]]]cd[w]'
    assert offsets(model) == [0, 3, 6, 8]
    editor = mk_editor(model)

    type_at(editor, 6, 'Q')   # F3
    assert text(model) == 'ab[x[y[Qz]]]cd[w]'
    type_at(editor, 3, 'P')   # F2
    assert text(model) == 'ab[x[Py[Qz]]]cd[w]'
    type_at(editor, 0, 'O')   # F1
    assert text(model) == 'ab[Ox[Py[Qz]]]cd[w]'
    type_at(editor, 11, 'R')  # F4, now at 3 + 1 + 3 + 1 + 2 + 1 = 11
    assert text(model) == 'ab[Ox[Py[Qz]]]cd[Rw]'

    for k in range(4):
        editor.undo()
    assert text(model) == 'ab[x[y[z]]]cd[w]'


def test_NFN_2():
    "NFN-2: removing text in a nested footnote, and undo"
    model = three_levels()
    editor = mk_editor(model)

    editor.switch_target(1, 3)  # F2 'y[F3]'
    editor.selection = (0, 1)
    editor.remove()
    assert text(model) == 'ab[x[[z]]]cd[w]'

    editor.switch_target(1, 5)  # F3, now at 3 + 2
    editor.selection = (0, 1)
    editor.remove()
    assert text(model) == 'ab[x[[]]]cd[w]'

    editor.undo()
    editor.undo()
    assert text(model) == 'ab[x[y[z]]]cd[w]'


def test_NFN_3():
    "NFN-3: typing in a footnote before a nested anchor shifts the nested one"
    model = three_levels()
    editor = mk_editor(model)

    type_at(editor, 0, 'AAA')  # F1, before the anchor of F2
    assert offsets(model) == [0, 6, 9, 11]
    assert editor.find_footnote(6)[1] == 6

    type_at(editor, 6, 'B')    # F2 at its new position
    assert text(model) == 'ab[AAAx[By[z]]]cd[w]'
    type_at(editor, 10, 'C')   # F3, shifted by both edits
    assert text(model) == 'ab[AAAx[By[Cz]]]cd[w]'


def test_NFN_4():
    "NFN-4: label and numbering of a nested footnote via update_host"
    model = three_levels()
    editor = mk_editor(model)

    editor.switch_target(1, 3)  # F2
    editor.target.update_host(lambda t: t.set_label('*'))
    editor.switch_target(1, 6)  # F3
    editor.target.update_host(lambda t: t.set_numbering('roman'))

    f1, f2, f3, f4 = footnotes(model)
    assert [f.label for f in (f1, f2, f3, f4)] == [None, '*', None, None]
    assert [f.numbering for f in (f1, f2, f3, f4)] == \
        ['numbers', 'numbers', 'roman', 'numbers']
    assert text(model) == 'ab[x[y[z]]]cd[w]'


def page_sig(page):
    def row_text(row):
        return ''.join(box.text for box in row.childs
                       if isinstance(box, TextBox))
    notes = page.footnotebox[2].data if page.footnotebox else ()
    return (len(page),
            [row_text(row) for _, _, row in page.rows],
            [row_text(row) for _, _, row in notes])


def mk_builder(model):
    builder = PageBuilder(model, Factory(testsheet))
    builder.settings = {
        'paper': 'custom', 'paper_width': 60, 'paper_height': 20,
        'margin_top': 1, 'margin_right': 1, 'margin_bottom': 1,
        'margin_left': 1,
    }
    builder.rebuild()
    builder.assure_finished()
    return builder


def test_NFN_5():
    "NFN-5: editing a nested footnote updates the layout like a rebuild"
    if wx.App.Get() is None:
        wx.App(False)
    f2 = fnote('second level note')
    f1 = fnote('first level note ', f2, ' continues')
    items = []
    for k in range(80):
        items.append('paragraph %d with a few words ' % k)
        if k == 3:
            items.append(f1)
        if k == 5:
            items.append(fnote('a later note'))
        items.append(NewLine())
    model = mk_model(*items)
    builder = mk_builder(model)
    model.add_view(builder)
    assert len(builder._layout.childs) > 3

    editor = mk_editor(model)
    f2_offset = offsets(model)[1]
    type_at(editor, f2_offset, 'inserted ' * 4)
    builder.assure_finished()
    assert 'inserted' in text(model)

    expected = [page_sig(p) for p in mk_builder(model)._layout.childs]
    assert [page_sig(p) for p in builder._layout.childs] == expected
    assert any('inserted' in ''.join(sig[2]) for sig in expected)


def test_NFN_6():
    "NFN-6: a nested footnote in a table cell can be edited"
    # Currently fails: writing a footnote back into a table cell
    # dissolves the cell's Group into the Table's childs (transform_range
    # fuses Groups inside Containers), which breaks the content/SEP
    # pairing. Already for a single footnote, see develnotes/TODO.md.
    from ..tables.tables import Table as RealTable
    f2 = fnote('inner')
    f1 = fnote('outer ', f2)
    table = RealTable((grouped([T('cell '), f1, T(' end')]), {}),
                      (T('x'), {}), ncols=2)
    model = mk_model('ab', table, 'cd')
    assert offsets(model) == [0, 8]  # F1: 'outer ' + anchor + END
    editor = mk_editor(model)

    def table_childs():
        return [len(child.childs) for child in model.texel.childs
                if isinstance(child, RealTable)]
    before = table_childs()

    type_at(editor, 8, 'X')  # F2, nested in the cell's footnote F1
    type_at(editor, 0, 'Y')  # F1 itself
    assert 'cell [Youter [Xinner]] end' in text(model)
    assert table_childs() == before  # the table's structure survives

    editor.undo()
    editor.undo()
    assert 'cell [outer [inner]] end' in text(model)


def save_load(model):
    """Save a document with model's texel to TXL and load it again."""
    import os
    import tempfile
    from ..core.document import Document
    doc = Document()
    doc.textmodel.texel = model.texel
    with tempfile.NamedTemporaryFile(suffix='.txl', delete=False) as f:
        path = f.name
    try:
        doc.save(path)
        return Document.load(path).textmodel
    finally:
        os.unlink(path)


def test_NFN_7():
    "NFN-7: footnotes survive saving and loading TXL"
    from ..textmodel.texeltree import ENDMARK as EM
    f3 = fnote('z')
    f2 = Footnote(grouped([T('y'), f3, NewLine(), T('second line'),
                           EM.set_parstyle({'base': 'normal',
                                            'alignment': 'right'})]))
    f1 = fnote('x', f2.set_label('*')).set_numbering('roman')
    model = mk_model('ab', f1, 'cd', fnote('w'))
    loaded = save_load(model)
    assert text(loaded) == text(model) == \
        'ab[x[y[z]\nsecond line]]cd[w]'
    g1, g2, g3, g4 = footnotes(loaded)
    assert (g1.numbering, g2.label) == ('roman', '*')
    assert offsets(loaded) == offsets(model)
    last = list(iter_leafes(g2.content, 0))[-1][2]
    assert last.is_endmark and last.parstyle.get('alignment') == 'right'

    # and the loaded footnotes can be edited
    editor = mk_editor(loaded)
    type_at(editor, offsets(loaded)[2], 'Q')
    assert text(loaded) == 'ab[x[y[Qz]\nsecond line]]cd[w]'


def test_NFN_8():
    "NFN-8: an image in a footnote is saved with its data"
    import io
    import cairocffi as cairo
    from ..images.images import Image, iter_images
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 3, 2)
    buf = io.BytesIO()
    surface.write_to_png(buf)
    data = buf.getvalue()
    model = mk_model('ab', fnote('see ', Image(data, alt='pic')), 'cd')
    loaded = save_load(model)
    images = list(iter_images(loaded.texel))
    assert [(image.content, image.alt) for image in images] == \
        [(data, 'pic')]

