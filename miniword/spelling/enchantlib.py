"""libenchant (Linux, BSD) with the dictionaries installed on the
system."""

import ctypes
import ctypes.util
from ctypes import c_char_p, c_int, c_size_t, c_ssize_t, c_void_p, POINTER

lib = None
broker = None
LIST_DICTS = ctypes.CFUNCTYPE(None, c_char_p, c_char_p, c_char_p, c_char_p,
                              c_void_p)


def init():
    global lib, broker
    lib = ctypes.CDLL(ctypes.util.find_library('enchant-2')
                      or 'libenchant-2.so.2')
    for name, restype, argtypes in [
            ('enchant_broker_init', c_void_p, []),
            ('enchant_broker_list_dicts', None, [c_void_p, LIST_DICTS,
                                                 c_void_p]),
            ('enchant_broker_request_dict', c_void_p, [c_void_p, c_char_p]),
            ('enchant_broker_free_dict', None, [c_void_p, c_void_p]),
            ('enchant_dict_check', c_int, [c_void_p, c_char_p, c_ssize_t]),
            ('enchant_dict_suggest', POINTER(c_char_p),
             [c_void_p, c_char_p, c_ssize_t, POINTER(c_size_t)]),
            ('enchant_dict_free_string_list', None,
             [c_void_p, POINTER(c_char_p)])]:
        func = getattr(lib, name)
        func.restype, func.argtypes = restype, argtypes
    broker = lib.enchant_broker_init()


def languages():
    tags = []
    lib.enchant_broker_list_dicts(
        broker, LIST_DICTS(lambda tag, *rest: tags.append(tag.decode())),
        None)
    return sorted(set(tags))  # a language may come from several providers


class Dictionary:
    def __init__(self, language):
        self.language = language
        self.handle = lib.enchant_broker_request_dict(broker,
                                                      language.encode())

    def __del__(self):
        if self.handle:
            lib.enchant_broker_free_dict(broker, self.handle)

    def check(self, word):
        return lib.enchant_dict_check(self.handle, word.encode(), -1) == 0

    def suggest(self, word):
        n = c_size_t()
        found = lib.enchant_dict_suggest(self.handle, word.encode(), -1,
                                         ctypes.byref(n))
        if not found:
            return []
        words = [found[i].decode() for i in range(n.value)]
        lib.enchant_dict_free_string_list(self.handle, found)
        return words
