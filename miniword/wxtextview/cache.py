from collections import OrderedDict

class LRUCache:
    def __init__(self, maxsize=10000):
        self.maxsize = maxsize
        self._data = OrderedDict()

    def get(self, key):
        val = self._data[key]
        self._data.move_to_end(key)
        return val

    def set(self, key, value):
        self._data[key] = value
        self._data.move_to_end(key)
        if len(self._data) > self.maxsize:
            self._data.popitem(last=False)

    def clear(self):
        self._data.clear()

        
