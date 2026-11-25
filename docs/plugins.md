# MiniWord plugins

MiniWord is extensible via Python plugins. To install a plugin, copy the `.py` file into the plugins directory for your platform:

| Platform | Plugins directory                                 |
| -------- | ------------------------------------------------- |
| Linux    | `~/.config/miniword/plugins/`                     |
| macOS    | `~/Library/Application Support/miniword/plugins/` |
| Windows  | `%APPDATA%\miniword\plugins\`                     |

Example plugins are provided in the `examples/` directory:

| File                  | Description                           |
| --------------------- | ------------------------------------- |
| `wordcount.py`        | Word count of document and selection  |
| `wordcount_dialog.py` | The same in a dialog that stays open  |
| `txtfilter.py`        | Filter for importing plain text files |
| `epubfilter.py`       | Import of EPUB e-books (without DRM)  |

For example, to install the word count dialog on Linux:

```
mkdir -p ~/.config/miniword/plugins
cp examples/wordcount_dialog.py ~/.config/miniword/plugins
```

It then appears in the Tools menu as "Word Count…".
