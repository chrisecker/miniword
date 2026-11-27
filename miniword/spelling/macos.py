"""NSSpellChecker of macOS, through the Objective-C runtime."""

import ctypes
from contextlib import contextmanager
from ctypes import c_bool, c_char_p, c_long, c_ulong, c_void_p

objc = None
checker = None


class NSRange(ctypes.Structure):
    _fields_ = [('location', c_ulong), ('length', c_ulong)]


def send(restype, obj, selector, *args):
    """[obj selector:args...]; objc_msgSend is cast to the signature."""
    method = ctypes.CFUNCTYPE(restype, c_void_p, c_void_p,
                              *map(type, args))(('objc_msgSend', objc))
    return method(obj, objc.sel_registerName(selector.encode()), *args)


def nsstring(s):
    return c_void_p(send(c_void_p, objc.objc_getClass(b'NSString'),
                         'stringWithUTF8String:', c_char_p(s.encode())))


def strings(array):
    """The strings of an NSArray of NSString (none for nil)."""
    found = []
    for i in range(send(c_ulong, array, 'count')):
        s = send(c_void_p, array, 'objectAtIndex:', c_ulong(i))
        found.append(send(c_char_p, s, 'UTF8String').decode())
    return found


@contextmanager
def autorelease_pool():
    """Frees the strings made by the methods; also without a run loop."""
    pool = objc.objc_autoreleasePoolPush()
    try:
        yield
    finally:
        objc.objc_autoreleasePoolPop(pool)


def init():
    global objc, checker
    objc = ctypes.CDLL('/usr/lib/libobjc.A.dylib')
    ctypes.CDLL('/System/Library/Frameworks/AppKit.framework/AppKit')
    objc.objc_getClass.restype = c_void_p
    objc.sel_registerName.restype = c_void_p
    objc.objc_autoreleasePoolPush.restype = c_void_p
    objc.objc_autoreleasePoolPop.argtypes = [c_void_p]
    checker = send(c_void_p, objc.objc_getClass(b'NSSpellChecker'),
                   'sharedSpellChecker')


def languages():
    with autorelease_pool():
        return strings(send(c_void_p, checker, 'availableLanguages'))


class Dictionary:
    def __init__(self, language):
        self.language = language

    def check(self, word):
        with autorelease_pool():
            found = send(NSRange, checker,
                         'checkSpellingOfString:startingAt:language:wrap:'
                         'inSpellDocumentWithTag:wordCount:',
                         nsstring(word), c_long(0), nsstring(self.language),
                         c_bool(False), c_long(0), c_void_p())
            return found.length == 0

    def suggest(self, word):
        length = len(word.encode('utf-16-le')) // 2  # NSString counts so
        with autorelease_pool():
            return strings(send(c_void_p, checker,
                                'guessesForWordRange:inString:language:'
                                'inSpellDocumentWithTag:',
                                NSRange(0, length), nsstring(word),
                                nsstring(self.language), c_long(0)))
