"""Öğretmen portalına giden QR bağlantısı; tahta servis adresinden bağımsızdır."""
import re
from urllib.parse import urlencode, urlsplit, urlunsplit

from tahta_kilit.site_url import validate_site_url


DEFAULT_QR_PORTAL_URL = "https://borusandijital.s.gy/"


def build_portal_qr_url(challenge, portal_url=DEFAULT_QR_PORTAL_URL):
    validate_site_url(portal_url)
    board = challenge.get("boardId", "")
    nonce = challenge.get("nonce", "")
    signature = challenge.get("qrSignature", "")
    request_code = challenge.get("manualRequestCode", "")
    patterns = (
        (board, r"[A-Z0-9][A-Z0-9-]{0,63}"),
        (nonce, r"[0-9a-f]{32}"),
        (signature, r"[A-Za-z0-9_-]{43}"),
        (request_code, r"[A-HJ-NP-Z2-9]{6}"),
    )
    if any(not isinstance(value, str) or not re.fullmatch(pattern, value)
           for value, pattern in patterns):
        raise ValueError("QR için tahta bilgileri geçersiz.")
    parts = urlsplit(portal_url)
    query = urlencode({"v": "2", "board": board, "request": request_code,
                       "nonce": nonce, "sig": signature})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))
