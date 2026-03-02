from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
FILE = BASE_DIR / "moby.txt"


from miniword.textmodel.textmodel import TextModel


def get_moby_model():
    txt = open(FILE).read()
    return TextModel(txt)

def get_moby():
    return get_moby_model().get_xtexel()

