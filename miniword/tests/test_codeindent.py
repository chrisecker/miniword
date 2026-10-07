# -*- coding: utf-8 -*-

"""
Tests for indenting code: in paragraphs whose base style has the role
'pre', indent/dedent (Alt+Right/Left) insert or remove 4
spaces at the line starts instead of changing the level. IDs CODE-n.

Run with: python runtests.py miniword/tests/test_codeindent.py
"""

from types import SimpleNamespace

from ..core.stylesheet import StyleSheet
from ..texteditor.editor import Editor
from ..textmodel.textmodel import TextModel


def code_editor(text, code_lines, base='pre'):
    """(model, editor) for text; the lines code_lines are code."""
    sheet = StyleSheet()
    sheet.set('normal', dict(role='body'))
    sheet.set(base, dict(role='pre'))
    model = TextModel(text)
    editor = Editor(model)
    # the stylesheet comes from the canvas' builder
    editor.canvas = SimpleNamespace(
        builder=SimpleNamespace(stylesheet=sheet),
        reset_blink=lambda: None, adjust_viewport=lambda: None,
        refresh=lambda: None)
    starts = [0] + [i + 1 for i, c in enumerate(text) if c == '\n']
    for k in code_lines:
        model.set_parstyle(starts[k], dict(base=base))
    return model, editor


def test_CODE_1():
    "CODE-1: indent in a code line: 4 spaces at its start, cursor follows"
    model, editor = code_editor("def f():\nreturn 1\n", [0, 1])
    editor.index = 12  # in 'return'
    editor.indent()
    assert model.get_text() == "def f():\n    return 1\n"
    assert editor.index == 16


def test_CODE_2():
    "CODE-2: a selection over code lines: each line, one undo step"
    model, editor = code_editor("a\nb\nc\n", [0, 1, 2])
    editor.selection = (0, 3)  # 'a\nb'
    editor.indent()
    assert model.get_text() == "    a\n    b\nc\n"
    assert editor.selection == (0, 11)
    editor.undo()
    assert model.get_text() == "a\nb\nc\n"


def test_CODE_3():
    "CODE-3: dedent removes up to 4 leading spaces per line; one undo step"
    text = "  a\n      b\nc\n"
    model, editor = code_editor(text, [0, 1, 2])
    editor.selection = (0, len(text) - 1)
    editor.dedent()
    assert model.get_text() == "a\n  b\nc\n"
    editor.undo()
    assert model.get_text() == text


def test_CODE_4():
    "CODE-4: outside code indent changes the level, as before"
    model, editor = code_editor("Text\n", [])
    editor.indent()
    assert model.get_text() == "Text\n"
    assert model.get_indent(0) == 1


def test_CODE_5():
    "CODE-5: code is found by the role of the base style, not its name"
    model, editor = code_editor("x = 1\n", [0], base='Quelltext')
    editor.indent()
    assert model.get_text() == "    x = 1\n"
