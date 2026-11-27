"""ISpellChecker of Windows 8 and later, through COM. Methods are called
by their index in the vtable, as declared in spellcheck.h of the Windows
SDK (0-2 are IUnknown's)."""

import ctypes
from ctypes import c_ulong, c_void_p, c_wchar_p, pointer, HRESULT, WINFUNCTYPE
from uuid import UUID

factory = None


def guid(text):
    return (ctypes.c_char * 16).from_buffer_copy(UUID(text).bytes_le)


def call(obj, index, *args):
    """Method index of the COM object obj; an error HRESULT raises
    OSError."""
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(c_void_p)))[0]
    method = WINFUNCTYPE(HRESULT, c_void_p, *map(type, args))(vtable[index])
    return method(obj, *args)


def release(obj):
    if obj:
        call(obj, 2)


def strings(enum):
    """The strings of an IEnumString, which is released."""
    found = []
    s, fetched = c_wchar_p(), c_ulong()
    while call(enum, 3, c_ulong(1), pointer(s), pointer(fetched)) == 0:
        found.append(s.value)
        ctypes.windll.ole32.CoTaskMemFree(s)
    release(enum)
    return found


def init():
    global factory
    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx(None, 2)  # apartment threaded; fails if wx did it
    ole32.CoCreateInstance.restype = HRESULT
    factory = c_void_p()
    ole32.CoCreateInstance(guid('7AB36653-1796-484B-BDFA-E74F1DB7C1DC'),
                           None, 1,  # in process
                           guid('8E018A9D-2415-4677-BF08-794EA61F94BB'),
                           pointer(factory))


def languages():
    enum = c_void_p()
    call(factory, 3, pointer(enum))  # get_SupportedLanguages
    return strings(enum)


class Dictionary:
    def __init__(self, language):
        self.language = language
        self.handle = c_void_p()
        call(factory, 5, c_wchar_p(language), pointer(self.handle))

    def __del__(self):
        release(self.handle)

    def check(self, word):
        enum, error = c_void_p(), c_void_p()
        call(self.handle, 4, c_wchar_p(word), pointer(enum))  # Check
        correct = call(enum, 3, pointer(error)) != 0  # S_FALSE: no error
        release(error)
        release(enum)
        return correct

    def suggest(self, word):
        enum = c_void_p()
        call(self.handle, 5, c_wchar_p(word), pointer(enum))  # Suggest
        return strings(enum)
