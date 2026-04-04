from collections import OrderedDict
from .documentnode import DocumentNode
from ..textmodel.styles import create_style


class StyleSheet(DocumentNode):
    """Ein Stylesheet ist eine Liste von Styles. Dabei hat jeder
    Style einen eindeutigen Key, mit dem er identifiziert werden kann.

    """
    def __init__(self):
        self.data = OrderedDict()

    def set(self, key, value):
        # create_style ist eigentlich nicht nötig. Zumindest wenn das
        # Dict wirklich ein registrierter Style ist.
        self.data[key] = create_style(**value)
        self.notify('style_changed', key)

    def delete(self, key):
        del self.data[key]
        self.notify('style_removed', key)

    def get(self, key):
        return self.data.get(key)
    
    def items(self):
        return list(self.data.items())

    def keys(self):
        return list(self.data.keys())

    def contains(self, key):
        return key in self.data


def test_00():
    ss = StyleSheet()
    ss.set('normal', dict(fontsize=10, color="black"))
    ss.set('h1', dict(fontsize=12, color="red"))
    s = ss.get('normal')
    assert s == dict(fontsize=10, color="black")
    s = ss.get('h1')
    assert s == dict(fontsize=12, color="red")
    assert ss.items() == [('normal', {'fontsize': 10, 'color': 'black'}),
                          ('h1', {'fontsize': 12, 'color': 'red'})]


    
