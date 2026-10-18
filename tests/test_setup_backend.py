"""Kurulum yetkisi, mevcut anahtarın korunması ve sınırlı servis işlemleri."""
import contextlib
import io
import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tahta_kilit import setup_backend as backend


class SetupBackendTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {"PKEXEC_UID": "1000"}))
        self.euid = self.stack.enter_context(patch.object(backend.os, "geteuid", return_value=0))
        self.account = self.stack.enter_context(patch.object(backend.pwd, "getpwuid", return_value=SimpleNamespace(pw_uid=1000, pw_name="teacher", pw_shell="/bin/bash")))
        self.exists = self.stack.enter_context(patch.object(backend.os.path, "lexists", return_value=True))
        self.provision = self.stack.enter_context(patch.object(backend.provision, "main"))
        self.stack.enter_context(patch.object(backend, "read_config", return_value={"board_id": "ETAP-01", "site_url": "https://example.org/ac"}))
        self.stack.enter_context(patch.object(backend, "read_key", return_value=b"k" * 32))
        self.run = self.stack.enter_context(patch.object(backend.subprocess, "run"))

    def test_existing_key_is_preserved_and_group_matches_caller(self):
        # Aynı kimlik ve adresle yeniden kurulum: anahtar ve ayar dosyası yeniden yazılmaz (0.1.14'ten beri kimlik değiştirilebilir).
        result = backend.configure(["ETAP-01", "https://example.org/ac"])
        self.provision.assert_not_called()
        self.assertTrue(result["existing"])
        self.assertEqual(result["boardId"], "ETAP-01")
        self.assertEqual(list(result["boardKeysEntry"]), ["ETAP-01"])
        self.assertEqual(self.run.call_args_list[0].args[0], ["/usr/sbin/usermod", "-aG", "tahta-kilit", "--", "teacher"])
        self.assertEqual(self.run.call_args_list[1].args[0], ["/usr/bin/systemctl", "enable", "--now", "tahta-kilit-verifier.service"])
        for call in self.run.call_args_list:
            self.assertTrue(call.kwargs["check"])
            self.assertNotIn("shell", call.kwargs)

    def test_unprivileged_call_does_not_modify_system(self):
        self.euid.return_value = 1000
        with self.assertRaises(PermissionError):
            backend.configure(["ETAP-01", "https://example.org/ac"])
        self.provision.assert_not_called()
        self.run.assert_not_called()

    def test_missing_polkit_caller_is_rejected(self):
        os.environ.pop("PKEXEC_UID")
        with self.assertRaises(PermissionError):
            backend.configure(["ETAP-01", "https://example.org/ac"])
        self.run.assert_not_called()

    def test_system_account_is_rejected(self):
        self.account.return_value.pw_uid = 0
        with self.assertRaises(PermissionError):
            backend.configure(["ETAP-01", "https://example.org/ac"])
        self.run.assert_not_called()

    def test_partial_configuration_is_not_overwritten(self):
        self.exists.side_effect = [True, False]
        with self.assertRaises(ValueError):
            backend.configure(["ETAP-01", "https://example.org/ac"])
        self.provision.assert_not_called()
        self.run.assert_not_called()

    def test_new_configuration_uses_validating_provisioner(self):
        self.exists.return_value = False
        previous = sys.argv
        result = backend.configure(["ETAP-01", "https://example.org/ac"])
        self.provision.assert_called_once_with()
        self.assertIs(sys.argv, previous)
        self.assertFalse(result["existing"])

    def test_registration_is_passwordless_and_reports_pending(self):
        pending = {"status": "pending", "fingerprint": "ABCD-1234", "boardId": "ETAP-01"}
        with patch.object(backend.board_registration, "register", return_value=pending) as register:
            result = backend.configure(["--register-board"])
        self.assertEqual(result, {"registered": False, "pending": True, "boardId": "ETAP-01", "fingerprint": "ABCD-1234"})
        register.assert_called_once_with("https://example.org/ac", "ETAP-01", b"k" * 32)
        self.run.assert_not_called()

    def test_registered_board_starts_master_sync(self):
        done = {"status": "registered", "fingerprint": "ABCD-1234", "boardId": "ETAP-01"}
        with patch.object(backend.board_registration, "register", return_value=done):
            result = backend.configure(["--register-board"])
        self.assertTrue(result["registered"])
        self.assertEqual(self.run.call_args_list[-1].args[0], ["/usr/bin/systemctl", "start", "--no-block", "tahta-kilit-master-sync.service"])

    def test_setup_sends_registration_and_tolerates_failure(self):
        pending = {"status": "pending", "fingerprint": "ABCD-1234", "boardId": "ETAP-01"}
        with patch.object(backend.board_registration, "register", return_value=pending):
            result = backend.configure(["ETAP-01", "https://example.org/ac"])
        self.assertTrue(result["registration"]["pending"])
        error = backend.board_registration.RegistrationError(backend.board_registration.NO_INTERNET)
        with patch.object(backend.board_registration, "register", side_effect=error):
            result = backend.configure(["ETAP-01", "https://example.org/ac"])
        self.assertIn("İnternet bağlantısı yok", result["registrationError"])
        self.assertTrue(result["existing"])

    def test_registration_requires_root_and_polkit_caller(self):
        self.euid.return_value = 1000
        with patch.object(backend.board_registration, "register") as register:
            with self.assertRaises(PermissionError):
                backend.configure(["--register-board"])
        register.assert_not_called()

    def test_registration_error_is_reported_on_stderr(self):
        stderr, stdout = io.StringIO(), io.StringIO()
        error = backend.board_registration.RegistrationError(backend.board_registration.NO_INTERNET)
        with patch.object(backend.sys, "argv", ["setup-helper", "--register-board"]),                 patch.object(backend.board_registration, "register", side_effect=error),                 contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            self.assertEqual(backend.main(), 1)
        self.assertIn("İnternet bağlantısı yok", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

if __name__ == "__main__":
    unittest.main()
