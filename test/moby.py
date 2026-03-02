from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
FILE = BASE_DIR / "moby.txt"


from miniword.textmodel.textmodel import TextModel


def get_moby_model():
    txt = open(FILE).read()
    return TextModel(txt)

def get_moby_styled():
    # this is not propper, since we should use create_style:
    s0 = dict(base='h0')
    s1 = dict(base='h1')
    
    textmodel =  get_moby_model()    
    import re
    pattern = re.compile(
    r'^(CHAPTER\s+.+)\r?\n([A-Z][A-Z\s\'\-\.]+)\r?\n',
        re.MULTILINE)
    text = textmodel.get_text()
    for match in pattern.finditer(text):
        i1, i2 = match.start(1), match.end(1)
        textmodel.set_parstyle(i1, s0)
        i1, i2 = match.start(2), match.end(2)
        textmodel.set_parstyle(i1, s1)
    return textmodel

def get_moby():
    return get_moby_model().get_xtexel()

