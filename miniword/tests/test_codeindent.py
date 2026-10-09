# -*- coding: utf-8 -*-

"""
Tests for indenting code: in a code block indent/dedent (Alt+Right/
Left) insert or remove 4 spaces at the line starts instead of changing
the level; elsewhere they change the level. IDs CODE-n.

Run with: python runtests.py miniword/tests/test_codeindent.py
"""

from ..textmodel.texeltree import Group, Text, NL
from .test_code import frame_with, code, codes
from .guitest import close


def act(frame, action):
    """The action as from a key or the menu: via the controller."""
    frame.editor.controller.handle_action(action, False)


def test_CODE_1():
    "CODE-1: indent in a code line: 4 spaces at its start, cursor follows"
    frame = frame_with(code('def f():', 'return 1'))
    try:
        editor, model = frame.editor, frame.document.textmodel
        j = model.get_text().index('return') + 2
        editor.set_index(j)
        act(frame, 'indent')
        assert codes(model.texel) == [('code', '', 'def f():\n    return 1')]
        assert editor.index == j + 4
    finally:
        close(frame)


def test_CODE_2():
    "CODE-2: a selection over code lines: each line, one undo step"
    frame = frame_with(code('x', 'y', 'z'))
    try:
        editor, model = frame.editor, frame.document.textmodel
        i = model.get_text().index('x')
        editor.set_index(i)
        editor.set_index(i + 3, extend=True)  # 'x\ny'
        act(frame, 'indent')
        assert codes(model.texel) == [('code', '', '    x\n    y\nz')]
        assert editor.selection == (i, i + 11)
        editor.undo()
        assert codes(model.texel) == [('code', '', 'x\ny\nz')]
    finally:
        close(frame)


def test_CODE_3():
    "CODE-3: dedent removes up to 4 leading spaces per line; one undo step"
    frame = frame_with(code('  x', '      y', 'z'))
    try:
        editor, model = frame.editor, frame.document.textmodel
        text = model.get_text()
        editor.set_index(text.index('  x'))
        editor.set_index(text.index('z'), extend=True)
        act(frame, 'dedent')
        assert codes(model.texel) == [('code', '', 'x\n  y\nz')]
        editor.undo()
        assert codes(model.texel) == [('code', '', '  x\n      y\nz')]
    finally:
        close(frame)


def test_CODE_4():
    "CODE-4: outside code indent changes the level - also in a paragraph "
    "of the style 'pre' (code is what is in a code block)"
    frame = frame_with(code('x'))
    try:
        editor, model = frame.editor, frame.document.textmodel
        editor.set_index(0)  # in 'a', the paragraph before the code
        act(frame, 'indent')
        assert model.get_text().startswith('a\n')
        assert model.get_indent(0) == 1
        model.set_parstyle(1, {'base': 'pre'})
        frame.canvas.builder.assure_index(len(model), 0)
        act(frame, 'indent')
        assert model.get_text().startswith('a\n')
        assert model.get_indent(0) == 2
    finally:
        close(frame)


def test_CODE_5():
    "CODE-5: a line pasted into code with another paragraph style is "
    "indented by spaces too"
    frame = frame_with(code('x'))
    try:
        editor, model = frame.editor, frame.document.textmodel
        editor.set_index(model.get_text().index('x') + 1)
        editor.insert_texel(Group([
            Text('y'), NL.set_parstyle({'base': 'h1'}), Text('z')]))
        editor.set_index(model.get_text().index('xy'))
        act(frame, 'indent')
        assert codes(model.texel) == [('code', '', '    xy\nz')]
    finally:
        close(frame)


def test_CODE_6():
    "CODE-6: the cursor at a line start (e.g. an empty last line) moves "
    "behind the spaces; a selection keeps its whole lines"
    frame = frame_with(code('x', ''))
    try:
        editor, model = frame.editor, frame.document.textmodel
        j = model.get_text().index('x') + 2  # the empty last line
        editor.set_index(j)
        act(frame, 'indent')
        assert codes(model.texel) == [('code', '', 'x\n    ')]
        assert editor.index == j + 4
        i = j - 2  # 'x'
        editor.set_index(i)
        editor.set_index(i + 1, extend=True)
        act(frame, 'indent')
        assert editor.selection == (i, i + 5)
    finally:
        close(frame)
