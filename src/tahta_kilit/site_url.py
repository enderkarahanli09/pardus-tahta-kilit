"""BB Kilit sitesi ve Google Apps Script deployment adresi doğrulaması."""
import re
from urllib.parse import urlsplit


def validate_site_url(value):
    if not isinstance(value, str) or len(value) > 2048 or not value:
        raise ValueError("Web adresi geçersiz.")
    if value != value.strip() or any(ord(char) < 0x21 or ord(char) == 0x7f for char in value):
        raise ValueError("Web adresinde boşluk/kontrol karakteri olmamalı.")
    parts = urlsplit(value)
    gas = parts.hostname == "script.google.com" and re.fullmatch(r"/macros/s/[A-Za-z0-9_-]{20,}/exec", parts.path)
    if (parts.scheme != "https" or not parts.hostname or parts.port not in (None, 443)
            or parts.username or parts.password or parts.query or parts.fragment
            or (parts.path not in ("", "/", "/ac") and not gas)):
        raise ValueError("HTTPS site adresi veya Google Apps Script /exec adresi gerekiyor.")
    return value


DEFAULT_SITE_URL = "https://script.google.com/macros/s/AKfycbzl4l1T9ONvPlbzYROs8uQajxuHrk8FiY82d_7MAbsRIkXcpMziWgsMhO5QRVbc0kAF/exec"

def resolve_site_url(value):
    validate_site_url(value)
    parts = urlsplit(value)
    if parts.hostname == "pardus-tahta-kilit-web.vercel.app":
        return DEFAULT_SITE_URL
    return value
