import json
from pathlib import Path

_path = Path.home() / ".config" / "miniword" / "config.json"
_defaults = {"layout_unit": "mm", "typographic_unit": "mm"}

_instance = None


def get_config():
    global _instance
    if _instance is None:
        _instance = Config()
    return _instance


class Config:
    """Persistent user preferences, stored in ~/.config/miniword/config.json."""

    def __init__(self):
        self._data = {**_defaults}
        if _path.exists():
            try:
                self._data.update(json.loads(_path.read_text()))
            except Exception:
                pass

    def get(self, key):
        return self._data.get(key, _defaults.get(key))

    def set(self, key, value):
        self._data[key] = value
        _path.parent.mkdir(parents=True, exist_ok=True)
        _path.write_text(json.dumps(self._data, indent=2))
