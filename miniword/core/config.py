import json
import os
import sys
from pathlib import Path

_defaults = {"layout_unit": "mm", "typographic_unit": "mm",
             "appearance": "system"}

_instance = None


def config_dir():
    """The folder of MiniWord's settings, recent files and user plugins.
    MINIWORD_CONFIG_DIR replaces it (the tests use an empty one)."""
    if os.environ.get('MINIWORD_CONFIG_DIR'):
        return os.environ['MINIWORD_CONFIG_DIR']
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
    elif sys.platform == 'darwin':
        base = os.path.expanduser('~/Library/Application Support')
    else:
        base = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
    return os.path.join(base, 'miniword')


def get_config():
    global _instance
    if _instance is None:
        _instance = Config()
    return _instance


class Config:
    """Persistent user preferences, stored in config.json in config_dir()."""

    def __init__(self):
        self._data = {**_defaults}
        self._path = Path(config_dir()) / "config.json"
        if self._path.exists():
            try:
                self._data.update(json.loads(self._path.read_text()))
            except Exception:
                pass

    def get(self, key):
        return self._data.get(key, _defaults.get(key))

    def set(self, key, value):
        self._data[key] = value
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))
