from getxpos.tunnel import XposTunnel, connect


class _XposNamespace:
    connect = staticmethod(connect)


xpos = _XposNamespace()
__all__ = ["XposTunnel", "connect", "xpos"]
