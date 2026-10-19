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


def describe_error(error):
    """Log/tanı için hata türü ve kısa, sır içermeyen ayrıntı (HTTP kodu, errno, ağ nedeni)."""
    import socket
    import urllib.error
    name = type(error).__name__
    if isinstance(error, urllib.error.HTTPError):
        return "{} (HTTP {})".format(name, error.code)
    if isinstance(error, urllib.error.URLError):
        return "{} ({})".format(name, describe_error(error.reason) if isinstance(error.reason, BaseException) else str(error.reason)[:120])
    if isinstance(error, (socket.timeout, TimeoutError)):
        return "zaman aşımı ({})".format(name)
    if isinstance(error, OSError) and error.errno is not None:
        return "{} (errno {}: {})".format(name, error.errno, (error.strerror or "")[:80])
    if isinstance(error, (ValueError, KeyError, PermissionError)):
        # Bu paketteki ValueError/PermissionError iletileri sabit metinlerdir; sır taşımaz.
        return "{}: {}".format(name, str(error)[:160])
    return name


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
