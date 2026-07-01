import runtests

modules = [
    # textmodel (external dependency, read-only)
    "miniword.textmodel.texeltree",
    "miniword.textmodel.utils",
    "miniword.textmodel.styles",
    "miniword.textmodel.weights",
    "miniword.textmodel.textmodel",

    # texteditor
    "miniword.texteditor.actions",
    "miniword.texteditor.editor",
    "miniword.texteditor.controller",
    "miniword.texteditor.boxcontroller",
    "miniword.texteditor.textcanvas",
    "miniword.texteditor.undoredo",

    # core
    "miniword.core.stylesheet",
    "miniword.core.styles",
    "miniword.core.document",
    "miniword.core.utils",

    # layout
    "miniword.layout.stretchable",
    "miniword.layout.annotation",
    "miniword.layout.boxes",
    "miniword.layout.counters",
    "miniword.layout.cairodevice",
    "miniword.layout.page",
    "miniword.layout.pagegen",
    "miniword.layout.pagebuilder",
    "miniword.layout.builderbase",
    "miniword.layout.factory",
    "miniword.layout.rect",
    "miniword.layout.cache",
    "miniword.layout.linewrap",
    "miniword.layout.simplelayout",     

    # io
    "miniword.io.texeltreeformat",
    "miniword.io.txlio",
    "miniword.io.importexport",

    # tables
    "miniword.tables.tables",
    "miniword.tables.table_boxes",
    "miniword.tables.table_factory",
    "miniword.tables.table_controllers",
    "miniword.tables.table_panel",

    # images
    "miniword.images.images",

    # ui
    "miniword.ui.stylemenu",
    "miniword.ui.styleinspector",
    "miniword.ui.searchtool",

    # plugins
    "miniword.plugins.mdfilter",
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
