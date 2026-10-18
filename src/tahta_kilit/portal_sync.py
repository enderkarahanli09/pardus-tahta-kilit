"""QR portal adresini sunucudan imzalı alır ve kilit ekranı için güvenli biçimde saklar.

Yönetici QR kodlarının açacağı adresi panelden değiştirebilir; root zamanlayıcısı
adresi HMAC imzasıyla doğrular ve /etc/tahta-kilit/portal.json dosyasına yazar.
Kilit ekranı normal kullanıcıyla çalıştığından dosya root sahipli ve 0644'tür.
"""
import hmac
import json
import os
import re
import secrets
import stat
import tempfile
from urllib.parse import urlsplit

from tahta_kilit.google_http import post_json, sign
from tahta_kilit.qr_portal import DEFAULT_QR_PORTAL_URL
from tahta_kilit.site_url import validate_site_url

CONFIG_DIR = "/etc/tahta-kilit"
PORTAL_PATH = os.path.join(CONFIG_DIR, "portal.json")
MAX_PORTAL_BYTES = 4096
SIGNATURE_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")


def build_portal_request(board_id, key, nonce=None):
    if nonce is None:
        nonce = secrets.token_hex(16)
    if not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise ValueError("Invalid nonce")
    return {
        "action": "portal-sync",
        "version": 1,
        "boardId": board_id,
        "nonce": nonce,
        "signature": sign(key, "portal-sync:v1|" + board_id + "|" + nonce),
    }


def verify_portal_response(data, board_id, nonce, key):
    """Geçerli imzalı adresi döndürür; sunucuda ayar yoksa None döner."""
    if not isinstance(data, dict):
        raise ValueError("Invalid response")
    if data.get("ok") is not True:
        return None
    if data.get("boardId") != board_id or data.get("nonce") != nonce:
        raise ValueError("Unexpected board or nonce")
    url = data.get("portalUrl")
    signature = data.get("signature")
    if not isinstance(url, str) or not url.isascii() or len(url) > 2048:
        raise ValueError("Invalid portal URL")
    if not isinstance(signature, str) or not SIGNATURE_PATTERN.fullmatch(signature):
        raise ValueError("Invalid portal signature")
    expected = sign(key, "portal-response:v1|" + board_id + "|" + nonce + "|" + url)
    if not hmac.compare_digest(expected, signature):
        raise ValueError("Invalid portal signature")
    validate_site_url(url)
    return url


def _is_trusted_file(info):
    # Normal kullanıcı okuyabilir; yalnız root yazabilir.
    return stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not stat.S_IMODE(info.st_mode) & 0o022


def read_portal_url(board_id, path=PORTAL_PATH):
    """portal.json geçerli ve bu tahtaya aitse adresi, değilse None döndürür."""
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            if not _is_trusted_file(os.fstat(stream.fileno())):
                return None
            raw = stream.read(MAX_PORTAL_BYTES + 1)
        if len(raw) > MAX_PORTAL_BYTES:
            return None
        state = json.loads(raw.decode("utf-8"))
        if not isinstance(state, dict) or state.get("boardId") != board_id:
            return None
        url = state.get("portalUrl")
        if not isinstance(url, str) or not url.isascii():
            return None
        return validate_site_url(url)
    except (OSError, ValueError, TypeError):
        return None


def resolve_qr_portal_url(board_id, configured_url=None, path=PORTAL_PATH):
    """Öncelik: imzalı portal.json > config qr_portal_url > varsayılan kopya site."""
    url = read_portal_url(board_id, path)
    if url:
        return url
    if configured_url is not None:
        try:
            return validate_site_url(configured_url)
        except ValueError:
            pass
    return DEFAULT_QR_PORTAL_URL


def _check_directory(directory):
    info = os.lstat(directory)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
        raise PermissionError("Unprotected configuration directory")


def write_portal_state(board_id, url, path=PORTAL_PATH):
    directory = os.path.dirname(path)
    _check_directory(directory)
    contents = json.dumps({"boardId": board_id, "portalUrl": url}, ensure_ascii=True) + "\n"
    descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".portal-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        # mkstemp 0600 oluşturur; dizin yalnız root yazılabilir olduğundan yarış yoktur.
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def synchronize_portal(config=None, key=None, opener=None, path=PORTAL_PATH):
    """Root zamanlayıcısından çağrılır. Adres değiştiyse portal.json güncellenir."""
    if config is None or key is None:
        from tahta_kilit.verifier_service import read_config, read_key
        config, key = read_config(), read_key()
    from tahta_kilit.site_url import resolve_site_url
    url = resolve_site_url(config["site_url"])
    if urlsplit(url).hostname != "script.google.com":
        return None
    board = config["board_id"]
    payload = build_portal_request(board, key)
    data = post_json(url, payload, MAX_PORTAL_BYTES, opener)
    portal_url = verify_portal_response(data, board, payload["nonce"], key)
    if portal_url is None:
        # Sunucuda ayar yoksa mevcut kayıt korunur (imzasız yanıtla silinmez).
        return None
    if read_portal_url(board, path) == portal_url:
        return portal_url
    write_portal_state(board, portal_url, path)
    return portal_url
