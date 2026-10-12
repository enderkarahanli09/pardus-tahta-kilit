"""Klavye yakalama yaşam döngüsü; gerçek masaüstü ayarlarını değiştirmez."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tahta_kilit.keyboard_guard import KeyboardGuard
from tahta_kilit import lock_screen
from gi.repository import Gdk


class KeyboardGuardTests(unittest.TestCase):
    def window(self, backend="GdkX11Display"):
        seat = Mock()
        seat.grab.return_value = Gdk.GrabStatus.SUCCESS
        display = SimpleNamespace(__gtype__=SimpleNamespace(name=backend), get_default_seat=lambda: seat)
        window = Mock()
        window.get_window.return_value = object()
        window.get_mapped.return_value = True
        window.get_display.return_value = display
        return window, seat

    def test_only_keyboard_is_grabbed(self):
        window, seat = self.window()
        guard = KeyboardGuard(window)
        self.assertEqual(guard.acquire(), "active_x11")
        self.assertEqual(seat.grab.call_args.args[1], Gdk.SeatCapabilities.KEYBOARD)
        self.assertIs(seat.grab.call_args.args[2], False)
        self.assertEqual(guard.acquire(), "active_x11")
        seat.grab.assert_called_once()

    def test_wayland_result_is_request_not_confirmation(self):
        window, seat = self.window("GdkWaylandDisplay")
        guard = KeyboardGuard(window)
        self.assertEqual(guard.acquire(), "requested_wayland")
        guard.release()
        seat.ungrab.assert_called_once()

    def test_release_is_idempotent(self):
        window, seat = self.window()
        guard = KeyboardGuard(window)
        guard.acquire()
        guard.release()
        guard.release()
        self.assertIsNone(guard.seat)
        seat.ungrab.assert_called_once()

    def test_unmapped_window_is_not_grabbed(self):
        window, seat = self.window()
        window.get_mapped.return_value = False
        self.assertEqual(KeyboardGuard(window).acquire(), "pending")
        seat.grab.assert_not_called()

    def test_failed_grab_can_retry(self):
        window, seat = self.window()
        seat.grab.side_effect = [Gdk.GrabStatus.ALREADY_GRABBED, Gdk.GrabStatus.SUCCESS]
        guard = KeyboardGuard(window)
        self.assertEqual(guard.acquire(), "failed")
        self.assertIsNone(guard.seat)
        self.assertEqual(guard.acquire(), "active_x11")

    def test_broken_grab_can_be_reacquired(self):
        window, seat = self.window()
        guard = KeyboardGuard(window)
        guard.acquire()
        guard.broken()
        self.assertIsNone(guard.seat)
        self.assertEqual(guard.acquire(), "active_x11")
        self.assertEqual(seat.grab.call_count, 2)

    def test_unsupported_backend_is_reported(self):
        window, seat = self.window("UnknownDisplay")
        self.assertEqual(KeyboardGuard(window).acquire(), "unsupported")
        seat.grab.assert_not_called()

    def test_unlocked_callbacks_do_not_grab_again(self):
        screen = lock_screen.LockScreen.__new__(lock_screen.LockScreen)
        screen.unlocked = True
        screen.keyboard_guard = Mock()
        screen.keyboard_timer = 9
        self.assertFalse(screen.ensure_keyboard_guard())
        screen.on_map(None, None)
        screen.retry_keyboard_guard()
        screen.on_grab_broken(None, SimpleNamespace(keyboard=True))
        screen.keyboard_guard.acquire.assert_not_called()
        screen.keyboard_guard.broken.assert_not_called()

    def test_broken_keyboard_grab_is_scheduled_only_while_locked(self):
        screen = lock_screen.LockScreen.__new__(lock_screen.LockScreen)
        screen.unlocked = False
        screen.keyboard_guard = Mock()
        with patch.object(lock_screen.GLib, "idle_add") as idle:
            screen.on_grab_broken(None, SimpleNamespace(keyboard=False))
            idle.assert_not_called()
            screen.on_grab_broken(None, SimpleNamespace(keyboard=True))
            idle.assert_called_once_with(screen.retry_keyboard_guard)
        screen.keyboard_guard.broken.assert_called_once()


if __name__ == "__main__":
    unittest.main()
