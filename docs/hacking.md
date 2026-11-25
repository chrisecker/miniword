# Hacking on MiniWord

Run the full test suite:

```
python test_all.py
```

Run tests for a single module:

```
python runtests.py miniword/layout/rowfactory.py
```

Run a specific test or demo:

```
python runtests.py miniword/ui/searchtool.py test_00
python runtests.py miniword/texteditor/textcanvas.py demo_00
```

`runtests.py` sets the environment variable `MINIWORD_CONFIG_DIR` to an
empty temporary folder. Tests and demos therefore start without your
settings, recent files and plugins, and don't change them. The variable
also works for MiniWord itself, e.g. to try it with fresh settings:

```
MINIWORD_CONFIG_DIR=/tmp/mw python miniword.py
```
