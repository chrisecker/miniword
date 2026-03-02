import runtests

modules = [
    "miniword.textmodel.texeltree",
    "miniword.textmodel.iterators",
    "miniword.textmodel.styles",
    "miniword.textmodel.textmodel",
    "miniword.wxtextview.linewrap",
    "miniword.wxtextview.markbuffer",
    "miniword.wxtextview.simplelayout",
    "miniword.wxtextview.boxes",
    "miniword.wxtextview.builder",
    "miniword.wxtextview.wxtextview",
    "miniword.stylesheet",
    "miniword.styles",
    "miniword.stretchable",
    "miniword.cairodevice",
    "miniword.document",
    "miniword.texeltreeformat",
    "miniword.txlio",
    "miniword.pagegen",
    "miniword.stylemenu",
    "miniword.inspector",
    "miniword.search",
    "miniword.annotation",
    "miniword.builder",
    "miniword.documentview",
]

for modname in modules:
    runtests.test_library(modname)
