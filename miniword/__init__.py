import sys
import os

if sys.platform == 'win32':
    # Python 3.8+ no longer searches PATH for DLLs automatically (security
    # hardening).  Find libcairo-2.dll, register its directory, and preload
    # it.  The preload is necessary because cairocffi uses its own search
    # logic; a DLL already in the process is always found.
    #
    # os.environ['PATH'] is unreliable when launched from WSL — it reflects
    # the Linux shell PATH, not the Windows user/system PATH.  Read the real
    # Windows PATH directly from the registry instead.
    import ctypes, winreg

    def _find_cairo():
        dirs = []
        for hive, subkey in [
            (winreg.HKEY_LOCAL_MACHINE,
             r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'),
            (winreg.HKEY_CURRENT_USER, r'Environment'),
        ]:
            try:
                with winreg.OpenKey(hive, subkey) as k:
                    raw, _ = winreg.QueryValueEx(k, 'Path')
                dirs.extend(os.path.expandvars(raw).split(os.pathsep))
            except OSError:
                pass
        # Process PATH as additional fallback (works in non-WSL scenarios)
        dirs.extend(os.environ.get('PATH', '').split(os.pathsep))
        for d in dirs:
            dll = os.path.join(d, 'libcairo-2.dll')
            if os.path.isfile(dll):
                os.add_dll_directory(d)
                ctypes.CDLL(dll)
                return True
        return False

    if not _find_cairo():
        print("Warning: libcairo-2.dll not found in PATH.")


import wx.lib.wxcairo as wxcairo

