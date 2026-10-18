"""İmzalı QR portal adresi eşitlemesi ve adres önceliği (gi/pwd/grp gerektirmez)."""
import base64
import hashlib
import hmac
import io
import json
import os
import stat
import tempfile
import unittest
from unittest.mock import patch

from tahta_kilit import portal_sync
from tahta_kilit.qr_portal import DEFAULT_QR_PORTAL_URL

KEY = bytes(range(32))
BOARD = "BILISIM-01"
NONCE = "0123456789abcdef0123456789abcdef"
SITE = "https://script.google.com/macros/s/AKfycbzl4l1T9ONvPlbzYROs8uQajxuHrk8FiY82d_7MAbsRIkXcpMziWgsMhO5QRVbc0kAF/exec"
PORTAL = "https://script.google.com/macros/s/AKfycbNEWPORTALxxxxxxxxxxxxxxxxxxxxxxxx/exec"


def b64url_hmac(key, message):
    digest = hmac.new(key, message.encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def signed_response(board=BOARD, nonce=NONCE, url=PORTAL, key=KEY):
    return {"ok": True, "boardId": board, "nonce": nonce, "portalUrl": url,
            "signature": b64url_hmac(key, "portal-response:v1|" + board + "|" + nonce + "|" + url)}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class FakeOpener:
    def __init__(self, reply):
        self.reply = reply
        self.requests = []

    def open(self, request, timeout=None):
        payload = json.loads(request.data.decode("utf-8"))
        self.requests.append((request, payload, timeout))
        body = self.reply(payload) if callable(self.reply) else self.reply
        return FakeResponse(body if isinstance(body, bytes) else json.dumps(body).encode())


class RequestSigningTests(unittest.TestCase):
    def test_request_fields_and_signature(self):
        request = portal_sync.build_portal_request(BOARD, KEY, NONCE)
        self.assertEqual(request["action"], "portal-sync")
        self.assertEqual(request["version"], 1)
        self.assertEqual(request["boardId"], BOARD)
        self.assertEqual(request["nonce"], NONCE)
        self.assertEqual(request["signature"], b64url_hmac(KEY, "portal-sync:v1|" + BOARD + "|" + NONCE))
        self.assertNotIn("=", request["signature"])
        self.assertEqual(len(request["signature"]), 43)

    def test_fresh_nonce_is_32_lowercase_hex(self):
        first = portal_sync.build_portal_request(BOARD, KEY)["nonce"]
        second = portal_sync.build_portal_request(BOARD, KEY)["nonce"]
        self.assertRegex(first, r"^[0-9a-f]{32}$")
        self.assertNotEqual(first, second)


class ResponseVerificationTests(unittest.TestCase):
    def verify(self, data):
        return portal_sync.verify_portal_response(data, BOARD, NONCE, KEY)

    def test_valid_response(self):
        self.assertEqual(self.verify(signed_response()), PORTAL)

    def test_not_configured_returns_none(self):
        self.assertIsNone(self.verify({"ok": False}))

    def test_tampered_url_is_rejected(self):
        data = signed_response()
        data["portalUrl"] = "https://evil.example/ac"
        with self.assertRaises(ValueError):
            self.verify(data)

    def test_tampered_signature_is_rejected(self):
        data = signed_response()
        data["signature"] = ("A" if data["signature"][0] != "A" else "B") + data["signature"][1:]
        with self.assertRaises(ValueError):
            self.verify(data)

    def test_wrong_key_is_rejected(self):
        with self.assertRaises(ValueError):
            self.verify(signed_response(key=b"x" * 32))

    def test_nonce_and_board_echo_required(self):
        with self.assertRaises(ValueError):
            self.verify(signed_response(nonce="f" * 32))
        with self.assertRaises(ValueError):
            self.verify(signed_response(board="BILISIM-02"))

    def test_signed_but_invalid_url_is_rejected(self):
        for url in ("http://example.org/ac", "https://example.org/ac?x=1", "https://example.org/other",
                    "https://user@example.org/ac", "https://exämple.org/ac"):
            with self.assertRaises(ValueError, msg=url):
                self.verify(signed_response(url=url))

    def test_missing_or_malformed_signature(self):
        data = signed_response()
        data.pop("signature")
        with self.assertRaises(ValueError):
            self.verify(data)
        data["signature"] = "short"
        with self.assertRaises(ValueError):
            self.verify(data)


class PortalFileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = os.path.join(self.directory.name, "portal.json")
        # Windows'ta root sahipliği yok; sahiplik/dizin kontrolleri ayrıca test edilir.
        patcher = patch.object(portal_sync, "_is_trusted_file", return_value=True)
        self.trusted = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(portal_sync, "_check_directory")
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, data):
        with open(self.path, "w", encoding="utf-8") as output:
            output.write(data if isinstance(data, str) else json.dumps(data))

    def test_precedence_portal_file_first(self):
        self.write({"boardId": BOARD, "portalUrl": PORTAL})
        self.assertEqual(portal_sync.resolve_qr_portal_url(BOARD, "https://example.org/ac", self.path), PORTAL)

    def test_board_mismatch_falls_back_to_config_then_default(self):
        self.write({"boardId": "OTHER-01", "portalUrl": PORTAL})
        self.assertEqual(portal_sync.resolve_qr_portal_url(BOARD, "https://example.org/ac", self.path), "https://example.org/ac")
        self.assertEqual(portal_sync.resolve_qr_portal_url(BOARD, None, self.path), DEFAULT_QR_PORTAL_URL)

    def test_invalid_file_contents_fall_back(self):
        for contents in ("not json", json.dumps([1]), json.dumps({"boardId": BOARD, "portalUrl": "http://x/ac"}),
                         json.dumps({"boardId": BOARD, "portalUrl": 5}), "x" * 5000):
            self.write(contents)
            self.assertEqual(portal_sync.resolve_qr_portal_url(BOARD, None, self.path), DEFAULT_QR_PORTAL_URL)

    def test_missing_file_and_invalid_config_use_default(self):
        self.assertEqual(portal_sync.resolve_qr_portal_url(BOARD, "javascript:alert(1)", self.path), DEFAULT_QR_PORTAL_URL)
        self.assertEqual(portal_sync.resolve_qr_portal_url(BOARD, "https://example.org/ac", self.path), "https://example.org/ac")

    def test_untrusted_file_is_ignored(self):
        self.write({"boardId": BOARD, "portalUrl": PORTAL})
        self.trusted.return_value = False
        self.assertEqual(portal_sync.resolve_qr_portal_url(BOARD, None, self.path), DEFAULT_QR_PORTAL_URL)

    def test_synchronize_writes_and_rewrites_on_change(self):
        config = {"board_id": BOARD, "site_url": SITE}
        target = {"url": PORTAL}

        def reply(payload):
            self.assertEqual(payload["signature"], b64url_hmac(KEY, "portal-sync:v1|" + BOARD + "|" + payload["nonce"]))
            return signed_response(nonce=payload["nonce"], url=target["url"])

        opener = FakeOpener(reply)
        self.assertEqual(portal_sync.synchronize_portal(config, KEY, opener, self.path), PORTAL)
        with open(self.path, encoding="utf-8") as stream:
            self.assertEqual(json.load(stream), {"boardId": BOARD, "portalUrl": PORTAL})
        self.assertEqual(opener.requests[0][0].full_url, SITE)
        self.assertEqual(opener.requests[0][2], 20)
        target["url"] = "https://borusandijital.s.gy/"
        portal_sync.synchronize_portal(config, KEY, opener, self.path)
        self.assertEqual(portal_sync.read_portal_url(BOARD, self.path), "https://borusandijital.s.gy/")
        self.assertEqual([name for name in os.listdir(self.directory.name)], ["portal.json"])

    def test_synchronize_keeps_file_on_bad_signature_or_not_configured(self):
        self.write({"boardId": BOARD, "portalUrl": PORTAL})
        config = {"board_id": BOARD, "site_url": SITE}
        bad = FakeOpener(lambda payload: dict(signed_response(nonce=payload["nonce"]), portalUrl="https://evil.example/ac"))
        with self.assertRaises(ValueError):
            portal_sync.synchronize_portal(config, KEY, bad, self.path)
        self.assertIsNone(portal_sync.synchronize_portal(config, KEY, FakeOpener({"ok": False}), self.path))
        self.assertEqual(portal_sync.read_portal_url(BOARD, self.path), PORTAL)

    def test_replayed_old_nonce_is_rejected(self):
        config = {"board_id": BOARD, "site_url": SITE}
        replay = FakeOpener(signed_response())  # sabit, eski nonce'lu imzalı yanıt
        with self.assertRaises(ValueError):
            portal_sync.synchronize_portal(config, KEY, replay, self.path)
        self.assertFalse(os.path.exists(self.path))

    def test_oversized_response_is_rejected(self):
        config = {"board_id": BOARD, "site_url": SITE}
        with self.assertRaises(ValueError):
            portal_sync.synchronize_portal(config, KEY, FakeOpener(b"{" + b" " * 5000 + b"}"), self.path)

    def test_non_google_site_is_skipped(self):
        opener = FakeOpener({"ok": False})
        self.assertIsNone(portal_sync.synchronize_portal({"board_id": BOARD, "site_url": "https://example.org/ac"}, KEY, opener, self.path))
        self.assertEqual(opener.requests, [])


class TrustCheckTests(unittest.TestCase):
    def info(self, mode, uid=0):
        return os.stat_result((mode, 0, 0, 1, uid, 0, 10, 0, 0, 0))

    def test_trust_rules(self):
        self.assertTrue(portal_sync._is_trusted_file(self.info(stat.S_IFREG | 0o644)))
        self.assertFalse(portal_sync._is_trusted_file(self.info(stat.S_IFREG | 0o644, uid=1000)))
        self.assertFalse(portal_sync._is_trusted_file(self.info(stat.S_IFREG | 0o664)))
        self.assertFalse(portal_sync._is_trusted_file(self.info(stat.S_IFREG | 0o646)))
        self.assertFalse(portal_sync._is_trusted_file(self.info(stat.S_IFDIR | 0o755)))


if __name__ == "__main__":
    unittest.main()
