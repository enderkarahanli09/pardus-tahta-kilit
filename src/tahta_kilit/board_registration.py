"""Tahtayı parolasız kayıt isteğiyle BB Kilit Apps Script servisine gönderir.

Sunucu yeni anahtarı "onay bekliyor" listesine alır; SUPER yetkili yönetici
BB Kilit yönetim panelinde onaylayana kadar tahta kod üretmez. Tahta ekranında
ve panelde aynı onay kodu (anahtar parmak izi) gösterilir; yönetici ikisini
karşılaştırarak sahte istekleri ayırt eder.

Yalnız root kurulum yardımcısından çağrılır; anahtar hiçbir dosyaya veya loga yazılmaz.
"""
import base64
import hashlib
import socket
import urllib.error
from urllib.parse import urlsplit

from tahta_kilit.google_http import post_json

MAX_RESPONSE_BYTES = 65536
STATUSES = ("registered", "pending")
NO_INTERNET = "İnternet bağlantısı yok; kaydı kopyalayıp yönetim paneline yapıştırın."
INVALID_RESPONSE = "Kayıt servisinden geçersiz yanıt alındı. Kaydı kopyalayıp yönetim paneline yapıştırın."
UNSUPPORTED_SITE = "Otomatik kayıt yalnız Google Apps Script servis adresiyle çalışır; kaydı kopyalayıp yönetim paneline yapıştırın."


class RegistrationError(Exception):
    """Kullanıcıya gösterilebilecek Türkçe kayıt hatası."""


def board_key_entry(board_id, key):
    # "Tahta kaydını kopyala" ile aynı biçim: standart Base64, dolgulu (44 karakter).
    return {board_id: base64.b64encode(key).decode("ascii")}


def fingerprint(key):
    """Onay kodu: SHA-256(anahtar) ilk 4 baytı, ABCD-1234 biçiminde."""
    digest = hashlib.sha256(key).hexdigest()[:8].upper()
    return digest[:4] + "-" + digest[4:]


def register_request(board_id, key):
    return {"action": "board-register", "boardId": board_id, "key": board_key_entry(board_id, key)[board_id]}


def clean_server_message(value):
    if not isinstance(value, str) or not value.strip():
        return "bilinmeyen hata"
    text = "".join(char if char.isprintable() else " " for char in value).strip()
    return text[:300]


def parse_register_response(data, board_id, key):
    if not isinstance(data, dict):
        raise RegistrationError(INVALID_RESPONSE)
    if data.get("success") is not True:
        raise RegistrationError("Sunucu tahta kaydını reddetti: " + clean_server_message(data.get("error")))
    status = data.get("status")
    if status not in STATUSES or data.get("boardId") != board_id:
        raise RegistrationError(INVALID_RESPONSE)
    # Sunucu anahtarı bozmadan aldıysa aynı onay kodunu hesaplar.
    if data.get("fingerprint") != fingerprint(key):
        raise RegistrationError(INVALID_RESPONSE)
    return {"status": status, "fingerprint": data["fingerprint"]}


def _call(url, payload, opener):
    try:
        return post_json(url, payload, MAX_RESPONSE_BYTES, opener)
    except urllib.error.HTTPError as error:
        raise RegistrationError(
            "Kayıt servisi hata döndürdü (HTTP {}). Kaydı kopyalayıp yönetim paneline yapıştırın.".format(error.code)
        ) from None
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError):
        raise RegistrationError(NO_INTERNET) from None
    except ValueError:
        raise RegistrationError(INVALID_RESPONSE) from None
    except OSError:
        raise RegistrationError(NO_INTERNET) from None


def register(site_url, board_id, key, opener=None):
    if urlsplit(site_url).hostname != "script.google.com":
        raise RegistrationError(UNSUPPORTED_SITE)
    result = parse_register_response(_call(site_url, register_request(board_id, key), opener), board_id, key)
    result["boardId"] = board_id
    return result
