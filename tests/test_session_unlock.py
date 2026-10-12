"""Gerçek doğrulama protokolü ve pencere gizleme yaşam döngüsü kontrolleri."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tahta_kilit import lock_screen
from tahta_kilit.protocol import unlock_code
from tahta_kilit.verifier_service import Verifier, ServiceError


class SessionUnlockTests(unittest.TestCase):
    def screen(self):
        screen = lock_screen.LockScreen.__new__(lock_screen.LockScreen)
        screen.unlocked = False
        screen.code = "12345678"
        screen.challenge = {"nonce": "a" * 32}
        screen.window = Mock()
        screen.qr_image = Mock()
        screen.code_label = Mock()
        screen.confirm_button = Mock()
        screen.refresh_timer = 11
        screen.tick_timer = 12
        screen.set_status = Mock()
        return screen

    def test_valid_code_consumes_nonce_and_hides_until_next_instance(self):
        verifier = Verifier("ETAP-DEMO", b"k" * 32)
        challenge = verifier.get_challenge()
        screen = self.screen()
        screen.challenge = challenge
        screen.code = unlock_code(b"k" * 32, "ETAP-DEMO", challenge["nonce"])
        with patch.object(lock_screen, "call_verifier", side_effect=lambda request: verifier.verify(request["nonce"], request["unlockCode"])) as call, patch.object(lock_screen.GLib, "source_remove") as remove:
            screen.submit_code()
            self.assertTrue(screen.unlocked)
            screen.window.hide.assert_called_once_with()
            self.assertEqual(screen.code, "")
            self.assertIsNone(screen.challenge)
            self.assertIsNone(screen.refresh_timer)
            self.assertIsNone(screen.tick_timer)
            self.assertEqual([c.args[0] for c in remove.call_args_list], [11, 12])
            # Saat ilerlese veya eski zamanlayıcı olayı gelse de pencere geri dönmez.
            for _ in range(3601):
                self.assertFalse(screen.tick())
            self.assertFalse(screen.refresh_challenge())
            screen.restore_lock_window()
            screen.window.show_all.assert_not_called()
            screen.window.present.assert_not_called()
            call.assert_called_once()
        with self.assertRaises(ServiceError):
            verifier.verify(challenge["nonce"], "12345678")
        next_instance = self.screen()
        self.assertFalse(next_instance.unlocked)
        next_instance.restore_lock_window()
        next_instance.window.show_all.assert_called_once_with()

    def test_wrong_code_keeps_window_locked(self):
        screen = self.screen()
        with patch.object(lock_screen, "call_verifier", return_value={"ok": False, "error": "invalid_code"}):
            screen.submit_code()
        self.assertFalse(screen.unlocked)
        screen.window.hide.assert_not_called()

    def test_verifier_failure_does_not_unlock(self):
        screen = self.screen()
        with patch.object(lock_screen, "call_verifier", side_effect=OSError("unavailable")):
            screen.submit_code()
        self.assertFalse(screen.unlocked)
        screen.window.hide.assert_not_called()

    def test_old_verifier_duration_does_not_restore_timer(self):
        screen = self.screen()
        with patch.object(lock_screen, "call_verifier", return_value={"ok": True, "unlockSeconds": 1}), patch.object(lock_screen.GLib, "source_remove"):
            screen.submit_code()
        self.assertTrue(screen.unlocked)
        self.assertFalse(screen.tick())
        screen.window.show_all.assert_not_called()

    def test_iconified_event_does_not_restore_unlocked_window(self):
        screen = self.screen()
        screen.unlocked = True
        with patch.object(lock_screen.GLib, "idle_add") as idle:
            screen.on_window_state(None, SimpleNamespace(new_window_state=lock_screen.Gdk.WindowState.ICONIFIED))
        idle.assert_not_called()

    def test_session_mode_response(self):
        verifier = Verifier("ETAP-DEMO", b"k" * 32)
        challenge = verifier.get_challenge()
        result = verifier.verify(challenge["nonce"], unlock_code(b"k" * 32, "ETAP-DEMO", challenge["nonce"]))
        self.assertEqual(result, {"ok": True, "unlockMode": "session"})


if __name__ == "__main__":
    unittest.main()
