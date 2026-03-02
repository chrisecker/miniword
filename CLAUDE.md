- Always use English for code and documentation
- Write code in a minimalist, concise style
- Variables and methods in lowercase with underscores _
- Functions and methods preferably as "verb_noun"
- Comments only when they are truly helpful / necessary
- Tests are run via runtests.py:
    python runtests.py miniword/txlio.py
    python runtests.py miniword/txlio.py test_00
- All tests are invoked via
    python test_all
- All tests must pass before a commit
- Individual .py files should be as independent as possible
- textmodel and texeltree are also used in separate projects. They should not be extended.
- Ignoriere Dateien und Verzeichnisse mit dem Präfix dev_ - sie sind nur Entwürfe zum Ausprobieren. 