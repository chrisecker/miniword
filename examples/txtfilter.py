# Example import/export plugin: Plain Text
# Install: copy to ~/.miniword/plugins/txtfilter.py
#
# Note: Plain Text (.txt) is already built into Miniword (importexport.py).
# This file demonstrates how to write an import/export plugin for other formats.

from miniword.importexport import register_import, register_export
from miniword.document import Document
from miniword.textmodel.textmodel import TextModel


def _load(path):
    with open(path, encoding='utf-8') as f:
        text = f.read()
    doc = Document()
    doc.textmodel = TextModel(text)
    return doc


def _save(doc, path):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(doc.textmodel.get_text())


def _check_txt(doc):
    from miniword.importexport import _check_txt as builtin_check
    return builtin_check(doc)


register_import("Plain Text", ["txt"], _load, lossless=False)
register_export("Plain Text", ["txt"], _save, lossless=False,
                check_fn=_check_txt)
