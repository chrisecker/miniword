# -*- coding: utf-8 -*-

"""
Tests for colorizing code blocks: the registry of colorizers (one per
language, from plugins) and the built-in one for Python. IDs COLOR-n.

Run with: python runtests.py miniword/tests/test_colorize.py
"""

from ..mdelements.colorize import colorizer, register_colorizer, \
    colorizers, colorize_python, KEYWORD, STRING, COMMENT, NUMBER


def styled(text, spans):
    """{piece of text: its style} of spans."""
    return {text[i1:i2]: style for i1, i2, style in spans}


def test_COLOR_1():
    "COLOR-1: Python is built in, as 'python' and 'py', in any case"
    assert colorizer('python') is colorize_python
    assert colorizer('Py') is colorize_python
    assert colorizer('cobol') is None and colorizer('') is None


def test_COLOR_2():
    "COLOR-2: a plugin registers a colorizer for its languages"
    def colorize(text):
        return [(0, 1, KEYWORD)]
    try:
        register_colorizer(['Foo', 'f'], colorize)
        assert colorizer('foo') is colorize and colorizer('F') is colorize
    finally:
        del colorizers['foo'], colorizers['f']


def test_COLOR_3():
    "COLOR-3: Python: keywords, strings, comments and numbers, not names"
    text = 'def f(x):\n    return "s" + 1  # c'
    found = styled(text, colorize_python(text))
    assert found['def'] == found['return'] == KEYWORD
    assert found['"s"'] == STRING
    assert found['# c'] == COMMENT
    assert found['1'] == NUMBER
    assert 'f' not in found and 'x' not in found


def test_COLOR_4():
    "COLOR-4: incomplete code is colorized up to where it breaks"
    text = 'if (x and\n    "abc'
    found = styled(text, colorize_python(text))  # no exception
    assert found['if'] == found['and'] == KEYWORD


def test_COLOR_5():
    "COLOR-5: indices count characters, also after non-ASCII ones"
    text = 'ä = "ö"\nif x: pass'
    found = styled(text, colorize_python(text))
    assert found['"ö"'] == STRING and found['if'] == KEYWORD
