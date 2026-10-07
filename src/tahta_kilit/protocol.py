"""Tahta kilidi için web sunucusuyla ortak kriptografik protokol."""

import base64
import hashlib
import hmac
import re

NONCE_PATTERN = re.compile(r"^[0-9a-f]{32}$")
BOARD_ID_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{0,63}$")
UNLOCK_CODE_LENGTH = 8
UNLOCK_CODE_SPACE = 100_000_000


def _validate_key(key):
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError("Tahta anahtarı tam olarak 32 bayt olmalıdır.")


def _validate_board_id(board_id):
    if not isinstance(board_id, str) or not BOARD_ID_PATTERN.fullmatch(board_id):
        raise ValueError("Tahta kimliği biçimi geçersiz.")


def _validate_nonce(nonce):
    if not isinstance(nonce, str) or not NONCE_PATTERN.fullmatch(nonce):
        raise ValueError("Nonce biçimi geçersiz.")


def _b64url_no_padding(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def qr_signature(key, board_id, nonce):
    """QR imzasını Base64URL biçiminde döndürür."""
    _validate_key(key)
    _validate_board_id(board_id)
    _validate_nonce(nonce)
    message = "qr:v1|{}|{}".format(board_id, nonce).encode("ascii")
    digest = hmac.new(key, message, hashlib.sha256).digest()
    return _b64url_no_padding(digest)


def unlock_code(key, board_id, nonce):
    """HMAC'in ilk 8 baytını büyük endian okuyup 8 haneli koda indirger."""
    _validate_key(key)
    _validate_board_id(board_id)
    _validate_nonce(nonce)
    message = "unlock:v1|{}|{}".format(board_id, nonce).encode("ascii")
    digest = hmac.new(key, message, hashlib.sha256).digest()
    number = int.from_bytes(digest[:8], byteorder="big") % UNLOCK_CODE_SPACE
    return str(number).zfill(UNLOCK_CODE_LENGTH)


def code_matches(key, board_id, nonce, candidate):
    """Sabit zamanlı karşılaştırmayla girilen kodu doğrular."""
    if not isinstance(candidate, str) or not re.fullmatch(r"[0-9]{8}", candidate):
        return False
    expected = unlock_code(key, board_id, nonce)
    return hmac.compare_digest(expected, candidate)
