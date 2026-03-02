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

total_n = 0
total_ok = 0
for modname in modules:
    n, n_ok = runtests.test_library(modname)
    total_n += n
    total_ok += n_ok

print()
print("=" * 62)
print("Total: %i tests, %i failed" % (total_n, total_n - total_ok))
