import runtests

modules = [
    # textmodel (external dependency, read-only)
    "miniword.textmodel.texeltree",
    "miniword.textmodel.iterators",
    "miniword.textmodel.styles",
    "miniword.textmodel.textmodel",

    # wxtextview
    "miniword.wxtextview.linewrap",
    "miniword.wxtextview.markbuffer",
    "miniword.wxtextview.simplelayout",
    "miniword.wxtextview.boxes",
    "miniword.wxtextview.builder",
    "miniword.wxtextview.wxtextview",

    # core
    "miniword.core.stylesheet",
    "miniword.core.styles",
    "miniword.core.document",
    "miniword.core.utils",

    # layout
    "miniword.layout.stretchable",
    "miniword.layout.annotation",
    "miniword.layout.cairodevice",
    "miniword.layout.builder",
    "miniword.layout.pagegen",

    # io
    "miniword.io.texeltreeformat",
    "miniword.io.txlio",
    "miniword.io.importexport",

    # tables
    "miniword.tables.tables",
    "miniword.tables.table_boxes",
    "miniword.tables.table_factory",
    "miniword.tables.table_editors",

    # images
    "miniword.images.images",

    # ui
    "miniword.ui.stylemenu",
    "miniword.ui.styleinspector",
    "miniword.ui.searchtool",
    "miniword.ui.documentview",

    # examples
    "examples.mdfilter",
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
