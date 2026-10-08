import sys

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
    "miniword.layout.linewrap",
    "miniword.layout.annotation",
    "miniword.layout.boxes",
    "miniword.layout.counters",
    "miniword.layout.cairodevice",
    "miniword.layout.page",
    "miniword.layout.pagebuilder",
    "miniword.layout.builderbase",
    "miniword.layout.rowfactory",
    "miniword.tests.test_rowfactory",
    "miniword.tests.test_footnotes",
    "miniword.tests.test_images",
    "miniword.tests.test_tables",
    "miniword.tests.test_headerfooter",
    "miniword.tests.test_hyphenation",
    "miniword.tests.test_marks",
    "miniword.tests.test_inspector",
    "miniword.tests.test_mdstyles",
    "miniword.tests.test_pluginmenu",
    "miniword.tests.test_progress",
    "miniword.tests.test_codeindent",
    "miniword.tests.test_measure",
    "miniword.tests.test_paste",
    "miniword.tests.test_linked_images",
    "miniword.tests.test_cli",
    "miniword.tests.test_shortcuts",
    "miniword.tests.test_panels",
    "miniword.tests.test_folders",
    "miniword.tests.test_desktop",
    "miniword.tests.test_clip",
    "miniword.tests.test_parstyle_editing",
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
    "miniword.tables.table_controllers",
    "miniword.tables.table_panel",

    # images
    "miniword.images.images",

    # ui
    "miniword.ui.stylemenu",
    "miniword.ui.unitentry",
    "miniword.ui.searchtool",
    "miniword.ui.markdownpreview",

    # plugins
    "miniword.plugins.mdfilter",
    "miniword.plugins.htmlfilter",
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

if total_ok < total_n:
    sys.exit(1)
