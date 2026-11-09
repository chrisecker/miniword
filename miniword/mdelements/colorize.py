"""
Colorizers of code blocks: one per language, a function text -> [(i1,
i2, style), ...] (character indices, style e.g. {'color': ...}). Python
is built in, plugins register others (register_colorizer).
"""

import io
import keyword
import token
import tokenize
from ..textmodel.styles import Style

colorizers = {}  # language (lower case) -> colorize


def register_colorizer(names, colorize):
    """colorize for the languages names, e.g. ['python', 'py']."""
    for name in names:
        colorizers[name.lower()] = colorize


def colorizer(lang):
    """The colorizer of the language lang, or None."""
    return colorizers.get(lang.lower())


# GitHub's colors
KEYWORD = Style(color='#cf222e')
STRING = Style(color='#0a3069')
COMMENT = Style(color='#6e7781')
NUMBER = Style(color='#0550ae')

TOKEN_STYLES = {token.STRING: STRING, tokenize.COMMENT: COMMENT,
                token.NUMBER: NUMBER}
for name in ('FSTRING_START', 'FSTRING_MIDDLE', 'FSTRING_END'):
    if hasattr(token, name):  # Python 3.12: f-strings in parts
        TOKEN_STYLES[getattr(token, name)] = STRING


def colorize_python(text):
    """Keywords, strings, comments and numbers; incomplete code up to
    where it breaks."""
    starts = [0]  # the index of each line
    for line in text.split('\n'):
        starts.append(starts[-1] + len(line) + 1)
    spans = []
    try:
        for t in tokenize.generate_tokens(io.StringIO(text).readline):
            if t.type == token.NAME and keyword.iskeyword(t.string):
                style = KEYWORD
            else:
                style = TOKEN_STYLES.get(t.type)
            if style is not None:
                (r1, c1), (r2, c2) = t.start, t.end
                spans.append((starts[r1 - 1] + c1, starts[r2 - 1] + c2,
                              style))
    except (tokenize.TokenError, SyntaxError):
        pass
    return spans


register_colorizer(['python', 'py'], colorize_python)
