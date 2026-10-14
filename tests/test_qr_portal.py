import unittest
from urllib.parse import parse_qs, urlsplit

from tahta_kilit.qr_portal import DEFAULT_QR_PORTAL_URL, build_portal_qr_url


class PortalQrTests(unittest.TestCase):
    def setUp(self):
        self.challenge = {"boardId": "BILISIM-01", "nonce": "a" * 32,
                          "qrSignature": "b" * 43, "manualRequestCode": "K7M4P2"}

    def test_qr_goes_to_teacher_portal_and_carries_both_input_fields(self):
        url = build_portal_qr_url(self.challenge)
        self.assertEqual(url.split("?")[0], DEFAULT_QR_PORTAL_URL)
        self.assertEqual(urlsplit(url).scheme, "https")
        self.assertEqual(urlsplit(url).hostname, "borusandijital.s.gy")
        self.assertEqual(urlsplit(url).path, "/")
        params = parse_qs(urlsplit(url).query)
        self.assertEqual(params["board"], ["BILISIM-01"])
        self.assertEqual(params["request"], ["K7M4P2"])
        self.assertEqual(params["nonce"], [self.challenge["nonce"]])
        self.assertEqual(params["sig"], [self.challenge["qrSignature"]])
        self.assertEqual(set(params), {"v", "board", "request", "nonce", "sig"})

    def test_invalid_request_code_and_redirect_target_are_rejected(self):
        self.challenge["manualRequestCode"] = "K7M4P0"
        with self.assertRaises(ValueError):
            build_portal_qr_url(self.challenge)
        self.challenge["manualRequestCode"] = "K7M4P2"
        with self.assertRaises(ValueError):
            build_portal_qr_url(self.challenge, "https://example.org/ac?target=other")


if __name__ == "__main__":
    unittest.main()
