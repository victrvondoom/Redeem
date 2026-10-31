import sys


def current():
    """Return the platform backend for this machine."""
    if sys.platform == "win32":
        from .windows import WindowsPlatform
        return WindowsPlatform()
    from .x11 import X11Platform
    return X11Platform()
