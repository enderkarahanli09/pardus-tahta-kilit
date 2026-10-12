"""Kilit penceresine klavye yönlendirme; masaüstü ayarlarını kalıcı değiştirmez."""
import gi
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk


class KeyboardGuard:
    def __init__(self, window):
        self.window = window
        self.seat = None
        self.state = "pending"

    def acquire(self):
        if self.seat is not None:
            return self.state
        native = self.window.get_window()
        if native is None or not self.window.get_mapped():
            self.state = "pending"
            return self.state
        display = self.window.get_display()
        backend = display.__gtype__.name
        if backend not in ("GdkX11Display", "GdkWaylandDisplay"):
            self.state = "unsupported"
            return self.state
        seat = display.get_default_seat()
        if seat is None:
            self.state = "failed"
            return self.state
        try:
            result = seat.grab(native, Gdk.SeatCapabilities.ALL, False, None, None, None, None)
        except (RuntimeError, TypeError, ValueError):
            self.state = "failed"
            return self.state
        if result != Gdk.GrabStatus.SUCCESS:
            self.state = "failed"
            return self.state
        self.seat = seat
        # Wayland'da GTK compositor'a inhibit isteği gönderir; kabul garantisi yoktur.
        self.state = "active_x11" if backend == "GdkX11Display" else "requested_wayland"
        return self.state

    def broken(self):
        self.seat = None
        self.state = "pending"

    def release(self):
        seat, self.seat = self.seat, None
        self.state = "released"
        if seat is not None:
            try:
                seat.ungrab()
            except (RuntimeError, TypeError, ValueError):
                # Pencere gizlenmesi/yok edilmesi de native grab'i bırakır.
                pass