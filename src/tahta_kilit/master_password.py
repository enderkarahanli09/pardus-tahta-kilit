"""Root-only offline recovery verifier and authenticated Google synchronization."""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import tempfile
import urllib.request
from urllib.parse import urlsplit

PATH = "/etc/tahta-kilit/master.json"
ITERATIONS = 600000


def read_state(board_id):
    try:
        fd = os.open(PATH, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
                return None
            raw = stream.read(4097)
        if len(raw) > 4096:
            return None
        state = json.loads(raw)
        if state.get("boardId") != board_id:
            return None
        validate_state(state)
        return state
    except (OSError, ValueError, TypeError, KeyError):
        return None


def validate_state(state):
    if type(state.get("version")) is not int or not 1 <= state["version"] <= 9007199254740991:
        raise ValueError("Invalid master version")
    if state.get("iterations") != ITERATIONS:
        raise ValueError("Invalid work factor")
    for field in ("salt", "hash"):
        value = state.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9+/]{43}=", value):
            raise ValueError("Invalid master data")
        if len(base64.b64decode(value, validate=True)) != 32:
            raise ValueError("Invalid master data")


def matches(board_id, candidate):
    if not isinstance(candidate, str) or not re.fullmatch(r"[0-9]{6}", candidate):
        return False
    state = read_state(board_id)
    if state is None:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", candidate.encode("ascii"), base64.b64decode(state["salt"]), ITERATIONS)
    return hmac.compare_digest(actual, base64.b64decode(state["hash"]))


class GoogleRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname not in ("script.google.com", "script.googleusercontent.com") or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError("Unexpected redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def synchronize():
    from tahta_kilit.verifier_service import read_config, read_key
    from tahta_kilit.site_url import resolve_site_url
    config, key = read_config(), read_key()
    url = resolve_site_url(config["site_url"])
    if urlsplit(url).hostname != "script.google.com":
        return
    board = config["board_id"]
    nonce = secrets.token_hex(16)
    signature = base64.urlsafe_b64encode(hmac.new(key, ("master-sync:v1|" + board + "|" + nonce).encode("ascii"), hashlib.sha256).digest()).decode().rstrip("=")
    body = json.dumps({"action":"master-sync", "boardId":board, "nonce":nonce, "signature":signature}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), GoogleRedirect())
    with opener.open(req, timeout=20) as response:
        raw = response.read(4097)
    if len(raw) > 4096:
        raise ValueError("Response too large")
    data = json.loads(raw)
    if data.get("ok") is not True or data.get("boardId") != board or data.get("nonce") != nonce:
        return
    validate_state(data)
    message = "master-response:v1|{}|{}|{}|{}|{}|{}".format(board, nonce, data["version"], data["iterations"], data["salt"], data["hash"])
    expected = base64.urlsafe_b64encode(hmac.new(key, message.encode("ascii"), hashlib.sha256).digest()).decode().rstrip("=")
    if not isinstance(data.get("signature"), str) or not hmac.compare_digest(expected, data["signature"]):
        raise ValueError("Invalid master signature")
    old = read_state(board)
    if old and data["version"] <= old["version"]:
        return
    state = {name:data[name] for name in ("boardId", "version", "iterations", "salt", "hash")}
    directory = os.lstat("/etc/tahta-kilit")
    if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != 0 or stat.S_IMODE(directory.st_mode) & 0o022:
        raise PermissionError("Unprotected configuration directory")
    fd, temporary = tempfile.mkstemp(dir="/etc/tahta-kilit", prefix=".master-")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump(state, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    try:
        synchronize()
    except Exception:
        # Never log HTTP request, authentication material or master verifier.
        print("Master parola güncellenemedi; mevcut çevrimdışı kayıt korunuyor.")
