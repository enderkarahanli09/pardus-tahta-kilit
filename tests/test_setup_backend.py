"""Kurulum yetkisi, mevcut anahtarın korunması ve sınırlı servis işlemleri."""
import contextlib
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
        result = backend.configure(["IGNORED", "https://example.org/ac"])
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


if __name__ == "__main__":
    unittest.main()
