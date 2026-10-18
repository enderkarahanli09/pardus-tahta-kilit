"""Google Apps Script servisine vekil sunucusuz, sınırlı JSON POST istemcisi."""
import base64
import hashlib
import hmac
import json
import urllib.request
from urllib.parse import urlsplit

ALLOWED_HOSTS = ("script.google.com", "script.googleusercontent.com")
TIMEOUT_SECONDS = 20


class GoogleRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError("Unexpected redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_opener():
    # Ortam vekil ayarları yok sayılır; yönlendirme yalnız Google alanlarına izinlidir.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), GoogleRedirect())


def sign(key, message):
    """HMAC-SHA256 imzası; dolgusuz Base64url."""
    digest = hmac.new(key, message.encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def post_json(url, payload, max_bytes=4096, opener=None):
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with (opener or build_opener()).open(request, timeout=TIMEOUT_SECONDS) as response:
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("Response too large")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid response")
    return data
