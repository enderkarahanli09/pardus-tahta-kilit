"""Tanı aracı ve hata açıklaması (root/gi gerektirmez)."""
import base64
import hashlib
import hmac
import io
import json
import os
import socket
import tempfile
import threading
import unittest
import urllib.error
from unittest.mock import patch

from tahta_kilit import master_password, tani
from tahta_kilit.google_http import describe_error

KEY = bytes(range(32))
BOARD = "BILISIM-01"
SITE = "https://script.google.com/macros/s/AKfycbzl4l1T9ONvPlbzYROs8uQajxuHrk8FiY82d_7MAbsRIkXcpMziWgsMhO5QRVbc0kAF/exec"
SALT = base64.b64encode(b"s" * 32).decode()
HASH = base64.b64encode(b"h" * 32).decode()


def sign(message):
    return base64.urlsafe_b64encode(hmac.new(KEY, message.encode(), hashlib.sha256).digest()).decode().rstrip("=")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class FakeOpener:
    def __init__(self, reply):
        self.reply = reply

    def open(self, request, timeout):
        sent = json.loads(request.data)
        return FakeResponse(json.dumps(self.reply(sent)).encode())


class DescribeErrorTest(unittest.TestCase):
    def test_http_and_network(self):
        http = urllib.error.HTTPError(SITE, 403, "Forbidden", {}, None)
        self.assertEqual(describe_error(http), "HTTPError (HTTP 403)")
        dns = urllib.error.URLError(socket.gaierror(-3, "Temporary failure in name resolution"))
        self.assertIn("errno -3", describe_error(dns))
        self.assertIn("zaman aşımı", describe_error(socket.timeout()))

    def test_permission_and_unknown(self):
        self.assertIn("errno 13", describe_error(PermissionError(13, "Permission denied")))
        self.assertEqual(describe_error(RuntimeError("gizli")), "RuntimeError")


class FetchMasterTest(unittest.TestCase):
    def test_valid_signed_master(self):
        def reply(sent):
            message = "|".join(["master-response:v2", BOARD, sent["nonce"], "3", "600000", SALT, HASH])
            return {"ok": True, "boardId": BOARD, "nonce": sent["nonce"], "version": 3, "iterations": 600000,
                    "entries": [{"salt": SALT, "hash": HASH}], "signature": sign(message)}
        data = master_password.fetch_master({"board_id": BOARD, "site_url": SITE}, KEY, FakeOpener(reply))
        self.assertEqual(data["version"], 3)

    def test_rejected_and_forged(self):
        config = {"board_id": BOARD, "site_url": SITE}
        self.assertIsNone(master_password.fetch_master(config, KEY, FakeOpener(lambda sent: {"ok": False})))

        def forged(sent):
            return {"ok": True, "boardId": BOARD, "nonce": sent["nonce"], "version": 1, "iterations": 600000,
                    "entries": [{"salt": SALT, "hash": HASH}], "signature": "A" * 43}
        with self.assertRaises(ValueError):
            master_password.fetch_master(config, KEY, FakeOpener(forged))


class VerifierProbeTest(unittest.TestCase):
    def serve(self, path, reply):
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(path)
        server.listen(1)

        def handle():
            connection, _ = server.accept()
            with connection:
                connection.recv(4096)
                connection.sendall(json.dumps(reply).encode() + b"\n")
            server.close()
        threading.Thread(target=handle, daemon=True).start()

    def test_reports_without_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "v.sock")
            self.serve(path, {"ok": True, "boardId": BOARD, "nonce": "f" * 32, "qrSignature": "S" * 43, "expiresIn": 99})
            with patch.object(tani, "SOCKET_PATH", path):
                result = tani.ask_verifier()
        self.assertEqual(result, "OK tahta=BILISIM-01 süre=99sn")
        self.assertNotIn("f" * 32, result)

    def test_missing_socket_and_service_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(tani, "SOCKET_PATH", os.path.join(directory, "yok.sock")):
                self.assertIn("FileNotFoundError", tani.ask_verifier())
            path = os.path.join(directory, "v.sock")
            self.serve(path, {"ok": False, "error": "internal_error"})
            with patch.object(tani, "SOCKET_PATH", path):
                self.assertEqual(tani.ask_verifier(), "SERVİS HATASI: internal_error")


class RedactionTest(unittest.TestCase):
    def test_hides_secrets_keeps_useful_text(self):
        key = base64.b64encode(KEY).decode()
        line = ("anahtar " + key + " imza " + "UvzzYlhnIhFV94MfFKn9XFzPu1RLX3suib_91-jcmLs" + " nonce " + "d8e38427e4d826a1e4fad533ca6b9531" +
                " qr https://borusandijital.s.gy/?v=2&board=BILISIM-05&request=UJVJ6L&sig=abc&token=xyz")
        out = tani.redact(line)
        for secret in (key, "UvzzYlhnIhFV94MfFKn9XFzPu1RLX3suib_91-jcmLs", "d8e38427e4d826a1e4fad533ca6b9531", "sig=abc", "token=xyz"):
            self.assertNotIn(secret, out)
        self.assertIn("board=BILISIM-05", out)
        keep = ("servis " + SITE + " onay kodu 297E-C23A tahta ETAP-01-KUTUPHANE-OGRETMENLER-ODASI-BINA-A "
                "/usr/lib/python3/dist-packages/tahta_kilit/verifier_service.py")
        self.assertEqual(tani.redact(keep), keep)

    def test_report_lines_are_redacted(self):
        report = tani.Report(quiet=True)
        report.ok("anahtar " + base64.b64encode(KEY).decode())
        self.assertNotIn(base64.b64encode(KEY).decode(), "\n".join(report.lines))


class MainTest(unittest.TestCase):
    def test_requires_root(self):
        with patch.object(tani.os, "geteuid", return_value=1000), patch("builtins.print"):
            self.assertEqual(tani.main([]), 2)

    def test_report_collects_problems(self):
        report = tani.Report()
        with patch("builtins.print"):
            report.ok("iyi")
            report.fail("kötü", "öneri")
        self.assertEqual(report.problems, ["kötü → öneri"])


if __name__ == "__main__":
    unittest.main()
