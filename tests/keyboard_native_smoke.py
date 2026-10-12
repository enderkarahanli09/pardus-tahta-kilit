"""Grafik test ortamında kısa süreli native klavye isteği; tam ekran/kiosk testi değildir."""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from tahta_kilit.keyboard_guard import KeyboardGuard

Gtk.init([])
window = Gtk.Window(title="Tahta Kilidi — kısa klavye API kontrolü")
window.set_default_size(260, 100)
window.add(Gtk.Label(label="Geçici API kontrolü"))
guard = KeyboardGuard(window)
try:
    window.show_all()
    state = guard.acquire()
    assert state in ("active_x11", "requested_wayland"), state
    guard.release()
    assert guard.seat is None
    print("Native keyboard grab/release API passed:", state)
finally:
    guard.release()
    window.destroy()
