"""Parolasız, onay bekleyen tahta kaydı (sahte HTTP; gi/pwd/grp gerektirmez)."""
import base64
import hashlib
import io
import json
import socket
import unittest
import urllib.error

from tahta_kilit import board_registration as registration
from tahta_kilit.board_registration import RegistrationError

KEY = bytes(range(32))
BOARD = "BILISIM-01"
SITE = "https://script.google.com/macros/s/AKfycbzl4l1T9ONvPlbzYROs8uQajxuHrk8FiY82d_7MAbsRIkXcpMziWgsMhO5QRVbc0kAF/exec"
FINGERPRINT = registration.fingerprint(KEY)


def reply(status="pending", **extra):
    data = {"success": True, "status": status, "boardId": BOARD, "fingerprint": FINGERPRINT}
    data.update(extra)
    return data


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class FakeOpener:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.payloads = []

    def open(self, request, timeout=None):
        self.payloads.append(json.loads(request.data.decode("utf-8")))
        self.timeout = timeout
        answer = self.replies.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return FakeResponse(answer if isinstance(answer, bytes) else json.dumps(answer).encode())


class RequestTests(unittest.TestCase):
    def test_key_entry_matches_copy_record_format(self):
        entry = registration.board_key_entry(BOARD, KEY)
        self.assertEqual(list(entry), [BOARD])
        self.assertEqual(len(entry[BOARD]), 44)
        self.assertEqual(base64.b64decode(entry[BOARD], validate=True), KEY)

    def test_fingerprint_format(self):
        expected = hashlib.sha256(KEY).hexdigest()[:8].upper()
        self.assertEqual(FINGERPRINT, expected[:4] + "-" + expected[4:])
        self.assertRegex(FINGERPRINT, r"^[0-9A-F]{4}-[0-9A-F]{4}$")

    def test_request_payload_has_no_password(self):
        payload = registration.register_request(BOARD, KEY)
        self.assertEqual(payload, {"action": "board-register", "boardId": BOARD,
                                   "key": base64.b64encode(KEY).decode()})


class FlowTests(unittest.TestCase):
    def test_pending(self):
        opener = FakeOpener(reply("pending"))
        result = registration.register(SITE, BOARD, KEY, opener)
        self.assertEqual(result, {"status": "pending", "fingerprint": FINGERPRINT, "boardId": BOARD})
        self.assertEqual(len(opener.payloads), 1)
        self.assertEqual(opener.timeout, 20)

    def test_already_registered(self):
        result = registration.register(SITE, BOARD, KEY, FakeOpener(reply("registered")))
        self.assertEqual(result["status"], "registered")

    def test_fingerprint_mismatch_is_invalid(self):
        with self.assertRaises(RegistrationError) as caught:
            registration.register(SITE, BOARD, KEY, FakeOpener(reply(fingerprint="0000-0000")))
        self.assertEqual(str(caught.exception), registration.INVALID_RESPONSE)

    def test_wrong_board_or_status_is_invalid(self):
        for bad in (reply(boardId="ETAP-01"), reply(status="saved"), reply(status=None)):
            with self.assertRaises(RegistrationError) as caught:
                registration.register(SITE, BOARD, KEY, FakeOpener(bad))
            self.assertEqual(str(caught.exception), registration.INVALID_RESPONSE)

    def test_server_rejection_shows_message(self):
        answer = {"success": False, "error": "Çok fazla bekleyen kayıt var.\n"}
        with self.assertRaises(RegistrationError) as caught:
            registration.register(SITE, BOARD, KEY, FakeOpener(answer))
        self.assertIn("Çok fazla bekleyen kayıt var.", str(caught.exception))
        self.assertNotIn("\n", str(caught.exception))

    def test_no_internet(self):
        for error in (urllib.error.URLError(socket.gaierror(-3, "Temporary failure")), socket.timeout("timed out"),
                      ConnectionResetError(), OSError("Network is unreachable")):
            with self.assertRaises(RegistrationError) as caught:
                registration.register(SITE, BOARD, KEY, FakeOpener(error))
            self.assertEqual(str(caught.exception), registration.NO_INTERNET)

    def test_http_error_and_invalid_json(self):
        http = urllib.error.HTTPError(SITE, 500, "err", {}, None)
        with self.assertRaises(RegistrationError) as caught:
            registration.register(SITE, BOARD, KEY, FakeOpener(http))
        self.assertIn("HTTP 500", str(caught.exception))
        for body in (b"<html>hata</html>", b"[1,2]", b"{" + b" " * 70000 + b"}"):
            with self.assertRaises(RegistrationError) as caught:
                registration.register(SITE, BOARD, KEY, FakeOpener(body))
            self.assertEqual(str(caught.exception), registration.INVALID_RESPONSE)

    def test_key_never_in_error_text(self):
        encoded = base64.b64encode(KEY).decode()
        with self.assertRaises(RegistrationError) as caught:
            registration.register(SITE, BOARD, KEY, FakeOpener({"success": False, "error": "x"}))
        self.assertNotIn(encoded, str(caught.exception))

    def test_non_google_site_is_not_contacted(self):
        opener = FakeOpener()
        with self.assertRaises(RegistrationError) as caught:
            registration.register("https://example.org/ac", BOARD, KEY, opener)
        self.assertEqual(str(caught.exception), registration.UNSUPPORTED_SITE)
        self.assertEqual(opener.payloads, [])


if __name__ == "__main__":
    unittest.main()
