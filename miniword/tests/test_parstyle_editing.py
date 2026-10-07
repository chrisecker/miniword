# -*- coding: utf-8 -*-

"""
Tests for paragraph styles when joining and pasting: the paragraph one
works in keeps its style (develnotes/parstyle_editing_concept.md).
IDs PAR-n.

Run with: python runtests.py miniword/tests/test_parstyle_editing.py
"""

from types import SimpleNamespace

from ..texteditor.editor import Editor
from ..textmodel.textmodel import TextModel


def doc(*paragraphs):
    """(model, editor) for paragraphs (text, base, indent); the last one
    without a newline if its text ends with '$'."""
    text = ''.join(t.rstrip('$') + ('' if t.endswith('$') else '\n')
                   for t, *_ in paragraphs)
    model = TextModel(text)
    i = 0
    for t, base, *indent in paragraphs:
        model.set_parstyle(i, dict(base=base))
        model.set_indent(i, indent[0] if indent else 0)
        i += len(t.rstrip('$')) + 1
    return model, Editor(model)


def styles(model):
    """[(text, base, indent)] of the paragraphs."""
    result, i = [], 0
    for text in model.get_text().split('\n'):
        result.append((text, model.get_parstyle(i).get('base'),
                       model.get_indent(i)))
        i += len(text) + 1
    return result


def backspace(editor, index):
    editor.index = index
    editor.selection = index - 1, index
    editor.remove()


def test_PAR_1():
    "PAR-1: backspace at the start of B: A+B with A's style; one undo step"
    model, editor = doc(('Titel', 'h1', 1), ('Text', 'body'))
    before = styles(model)
    backspace(editor, 6)
    assert styles(model)[0] == ('TitelText', 'h1', 1)
    editor.undo()
    assert styles(model) == before


def test_PAR_2():
    "PAR-2: Delete at the end of A, a selection from A into C: A's style"
    model, editor = doc(('Titel', 'h1'), ('Text', 'body'))
    editor.selection = 5, 6
    editor.remove()
    assert styles(model)[0] == ('TitelText', 'h1', 0)
    model, editor = doc(('Eins', 'h2'), ('Zwei', 'body'), ('Drei', 'quote'))
    editor.selection = 2, 12  # Ei|ns ... Dr|ei
    editor.remove()
    assert styles(model)[0] == ('Eiei', 'h2', 0)


def test_PAR_3():
    "PAR-3: a selection from the start of A, or an empty A: B keeps its style"
    model, editor = doc(('Titel', 'h1'), ('Text', 'body'))
    editor.selection = 0, 6  # the whole heading with its newline
    editor.remove()
    assert styles(model)[0] == ('Text', 'body', 0)
    model, editor = doc(('', 'h1'), ('Text', 'body'))
    backspace(editor, 1)
    assert styles(model)[0] == ('Text', 'body', 0)


def test_PAR_4():
    "PAR-4: joining with the last paragraph (no newline)"
    model, editor = doc(('Titel', 'h1'), ('Ende$', 'body'))
    backspace(editor, 6)
    assert styles(model) == [('TitelEnde', 'h1', 0)]


def test_PAR_5():
    "PAR-5: undo: equal styles merge with keystrokes, a style change not"
    model, editor = doc(('ab', 'body'), ('cd', 'body'))
    for index in (5, 4, 3, 2):  # 'dc', the newline, 'b'
        backspace(editor, index)
    assert editor.undocount() == 1  # all merged, as before
    model, editor = doc(('ab', 'h1'), ('cd', 'body'))
    for index in (5, 4, 3, 2):
        backspace(editor, index)
    assert editor.undocount() == 3  # 'dc' | the join | 'b'
    for _ in range(3):
        editor.undo()
    assert styles(model)[:2] == [('ab', 'h1', 0), ('cd', 'body', 0)]


def paste(editor, model, index, fragment):
    """Paste fragment (a TextModel) at index."""
    editor.canvas = SimpleNamespace(
        read_clipboard=lambda: fragment, reset_blink=lambda: None,
        adjust_viewport=lambda: None, refresh=lambda: None)
    editor.index = index
    editor.selection = index, index
    editor.paste()


def fragment():
    """'chrift-A' with a newline in style quote, then 'Te'."""
    part, _ = doc(('chrift-A', 'quote', 2), ('Te$', 'body'))
    return part


def test_PAR_6():
    "PAR-6: pasted into the middle of X, X keeps its style"
    model, editor = doc(('XlinksXrechts', 'h2', 1))
    paste(editor, model, 6, fragment())
    assert styles(model)[:2] == [('Xlinkschrift-A', 'h2', 1),
                                 ('TeXrechts', 'h2', 1)]
    editor.undo()
    assert styles(model)[0] == ('XlinksXrechts', 'h2', 1)


def test_PAR_7():
    "PAR-7: pasted at the start of X, the pasted paragraphs keep theirs"
    model, editor = doc(('X', 'h2'))
    paste(editor, model, 0, fragment())
    assert styles(model)[:2] == [('chrift-A', 'quote', 2), ('TeX', 'h2', 0)]


def with_sheet(editor, roles):
    """A canvas stand-in whose stylesheet has styles {key: role}."""
    from ..core.stylesheet import StyleSheet
    sheet = StyleSheet()
    sheet.set('normal', dict(role=None))
    for key, role in roles.items():
        sheet.set(key, dict(role=role))
    editor.canvas = SimpleNamespace(
        builder=SimpleNamespace(stylesheet=sheet), reset_blink=lambda: None,
        adjust_viewport=lambda: None, refresh=lambda: None)


def enter(editor, index):
    editor.index = index
    editor.selection = index, index
    editor.insert_newline()


def test_PAR_8():
    "PAR-8: Enter at the end of a heading: a body paragraph follows"
    model, editor = doc(('Titel', 'Kapitel', 1), ('Text', 'Fliesstext'))
    with_sheet(editor, dict(Kapitel='h1', Fliesstext='body'))
    enter(editor, 5)
    assert styles(model)[:3] == [('Titel', 'Kapitel', 1),
                                 ('', 'Fliesstext', 0),
                                 ('Text', 'Fliesstext', 0)]
    editor.undo()  # one step
    assert styles(model)[:2] == [('Titel', 'Kapitel', 1),
                                 ('Text', 'Fliesstext', 0)]


def test_PAR_9():
    "PAR-9: Enter elsewhere continues the style; without body: normal"
    model, editor = doc(('Titel', 'Kapitel'), ('Text', 'Fliesstext'))
    with_sheet(editor, dict(Kapitel='h1', Fliesstext='body'))
    enter(editor, 2)  # Ti|tel
    assert [s[1] for s in styles(model)[:2]] == ['Kapitel', 'Kapitel']
    enter(editor, len('Ti\ntel\nText'))  # end of a body paragraph
    assert styles(model)[3] == ('', 'Fliesstext', 0)
    model, editor = doc(('Titel', 'Kapitel'))
    with_sheet(editor, dict(Kapitel='h2'))
    enter(editor, 5)
    assert styles(model)[1][1] == 'normal'
