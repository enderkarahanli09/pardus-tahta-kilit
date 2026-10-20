"""Otomatik kapanma saati: imzalı eşitleme, Türkiye saati, kapanma penceresi (root/gi gerektirmez)."""
import base64
import datetime
import hashlib
import hmac
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from tahta_kilit import shutdown_schedule as ss

KEY = bytes(range(32))
BOARD = "BILISIM-05"
SITE = "https://script.google.com/macros/s/AKfycbzl4l1T9ONvPlbzYROs8uQajxuHrk8FiY82d_7MAbsRIkXcpMziWgsMhO5QRVbc0kAF/exec"


def sign(message, key=KEY):
    return base64.urlsafe_b64encode(hmac.new(key, message.encode(), hashlib.sha256).digest()).decode().rstrip("=")


def reply_for(nonce, value="17:30", server_ms=1_792_500_000_000, key=KEY):
    return {"ok": True, "boardId": BOARD, "nonce": nonce, "time": value, "serverTime": server_ms,
            "signature": sign("shutdown-response:v1|{}|{}|{}|{}".format(BOARD, nonce, value, server_ms), key)}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class FakeOpener:
    def __init__(self, reply):
        self.reply = reply
        self.sent = None

    def open(self, request, timeout):
        self.sent = json.loads(request.data)
        return FakeResponse(json.dumps(self.reply(self.sent)).encode())


def turkey(*args):
    return datetime.datetime(*args, tzinfo=ss.TURKEY)


class RequestResponseTest(unittest.TestCase):
    def test_request_is_signed(self):
        payload = ss.build_request(BOARD, KEY, "a" * 32)
        self.assertEqual(payload["action"], "shutdown-sync")
        self.assertEqual(payload["signature"], sign("shutdown-sync:v1|" + BOARD + "|" + "a" * 32))

    def test_valid_and_disabled(self):
        self.assertEqual(ss.verify_response(reply_for("b" * 32), BOARD, "b" * 32, KEY), ("17:30", 1_792_500_000_000))
        self.assertEqual(ss.verify_response(reply_for("b" * 32, ""), BOARD, "b" * 32, KEY)[0], "")
        self.assertIsNone(ss.verify_response({"ok": False}, BOARD, "b" * 32, KEY))

    def test_rejects_forgery(self):
        forged = reply_for("c" * 32, key=bytes(32))
        with self.assertRaises(ValueError):
            ss.verify_response(forged, BOARD, "c" * 32, KEY)
        tampered = reply_for("c" * 32)
        tampered["time"] = "08:00"
        with self.assertRaises(ValueError):
            ss.verify_response(tampered, BOARD, "c" * 32, KEY)
        bad = reply_for("c" * 32, "25:00")
        with self.assertRaises(ValueError):
            ss.verify_response(bad, BOARD, "c" * 32, KEY)


class StateTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "shutdown.json")
        self.trusted = patch.object(ss, "_trusted", return_value=True)
        self.trusted.start()

    def tearDown(self):
        self.trusted.stop()

    def test_sync_writes_time_and_clock_offset(self):
        opener = FakeOpener(lambda sent: reply_for(sent["nonce"], "22:15", 1_000_100_000))
        clock = iter([1_000_000.0, 1_000_002.0])
        with patch.object(ss.os, "lstat", return_value=os.stat_result((0o40755, 0, 0, 0, 0, 0, 0, 0, 0, 0))):
            value = ss.synchronize_shutdown({"board_id": BOARD, "site_url": SITE}, KEY, opener, self.path,
                                            clock=lambda: next(clock))
        self.assertEqual(value, "22:15")
        state = ss.read_state(BOARD, self.path)
        self.assertEqual(state["time"], "22:15")
        self.assertAlmostEqual(state["offset"], 1_000_100 - 1_000_001, places=3)
        self.assertIsNone(ss.read_state("BASKA-TAHTA", self.path))

    def test_rejected_sync_keeps_old_state(self):
        with open(self.path, "w") as output:
            json.dump({"boardId": BOARD, "time": "18:00", "offset": 0, "syncedAt": 1}, output)
        opener = FakeOpener(lambda sent: {"ok": False})
        self.assertIsNone(ss.synchronize_shutdown({"board_id": BOARD, "site_url": SITE}, KEY, opener, self.path))
        self.assertEqual(ss.read_state(BOARD, self.path)["time"], "18:00")


class StatusTest(unittest.TestCase):
    def test_request_carries_board_status(self):
        status = {"package": "0.1.31", "masterVersion": 5, "portalUrl": "https://borusandijital.s.gy/", "shutdownTime": "17:30"}
        payload = ss.build_request(BOARD, KEY, "d" * 32, status)
        self.assertEqual(payload["masterVersion"], 5)
        self.assertEqual(payload["signature"], sign("shutdown-sync:v1|" + BOARD + "|" + "d" * 32))
        self.assertFalse(any(isinstance(v, bytes) for v in payload.values()))

    def test_status_without_files(self):
        with patch.object(ss, "read_state", return_value=None):
            status = ss.board_data_status("YOK-TAHTA")
        self.assertEqual(status["package"], ss.PACKAGE_VERSION)
        self.assertEqual(status["masterVersion"], 0)
        self.assertEqual(status["shutdownTime"], "")


class ClockAndWindowTest(unittest.TestCase):
    def test_server_offset_used_only_when_fresh(self):
        now = 1_800_000_000.0
        fresh = {"time": "17:00", "offset": 120.0, "syncedAt": now - 30}
        stale = {"time": "17:00", "offset": 120.0, "syncedAt": now - 3600}
        self.assertEqual(ss.turkey_now(fresh, now).timestamp(), now + 120)
        self.assertEqual(ss.turkey_now(stale, now).timestamp(), now)
        self.assertEqual(ss.turkey_now(None, now).utcoffset(), datetime.timedelta(hours=3))

    def test_window(self):
        self.assertEqual(ss.due_target("17:30", turkey(2026, 10, 20, 17, 30, 2)), "2026-10-20")
        self.assertEqual(ss.due_target("17:30", turkey(2026, 10, 20, 17, 34, 59)), "2026-10-20")
        self.assertIsNone(ss.due_target("17:30", turkey(2026, 10, 20, 17, 29, 59)))
        self.assertIsNone(ss.due_target("17:30", turkey(2026, 10, 20, 17, 35, 0)))
        self.assertIsNone(ss.due_target("", turkey(2026, 10, 20, 17, 30)))
        self.assertEqual(ss.due_target("00:00", turkey(2026, 10, 21, 0, 1)), "2026-10-21")


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.state = os.path.join(self.dir, "shutdown.json")
        self.stamp = os.path.join(self.dir, "lib", "kapanis-son")
        self.patches = [patch.object(ss, "_trusted", return_value=True),
                        patch("tahta_kilit.verifier_service.read_config", return_value={"board_id": BOARD, "site_url": SITE})]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()

    def write(self, value):
        with open(self.state, "w") as output:
            json.dump({"boardId": BOARD, "time": value, "offset": 0, "syncedAt": 0}, output)

    def test_no_daily_limit(self):
        # Tahta pencere içinde yeniden açılırsa yine kapanır (günlük sınır yok).
        self.write("17:30")
        now = turkey(2026, 10, 20, 17, 31).timestamp()
        calls = []
        self.assertIn("kapatılıyor", ss.check_and_shutdown(now, self.state, self.stamp, lambda: calls.append(1)))
        self.assertIn("kapatılıyor", ss.check_and_shutdown(now + 120, self.state, self.stamp, lambda: calls.append(1)))
        self.assertEqual(calls, [1, 1])

    def test_new_time_same_day_shuts_down_again_offline(self):
        # İnternetli denemeden sonra panelde saat değişti; tahta internetsiz (eşitleme eski) yeni saatte de kapanmalı.
        calls = []
        self.write("17:30")
        ss.check_and_shutdown(turkey(2026, 10, 20, 17, 31).timestamp(), self.state, self.stamp, lambda: calls.append(1))
        self.write("18:05")
        result = ss.check_and_shutdown(turkey(2026, 10, 20, 18, 6).timestamp(), self.state, self.stamp, lambda: calls.append(1))
        self.assertIn("tahta saatiyle", result)
        self.assertEqual(calls, [1, 1])

    def test_disabled_and_waiting(self):
        self.write("")
        self.assertEqual(ss.check_and_shutdown(0, self.state, self.stamp, lambda: self.fail("kapatmamalı")),
                         "otomatik kapanma kapalı")
        self.write("17:30")
        now = turkey(2026, 10, 20, 9, 0).timestamp()
        self.assertIn("bekleniyor", ss.check_and_shutdown(now, self.state, self.stamp, lambda: self.fail("kapatmamalı")))


if __name__ == "__main__":
    unittest.main()
