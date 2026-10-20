"""Yönetim panelindeki otomatik kapanma saatini imzalı alır ve tahtayı o saatte kapatır.

Saat Türkiye saatidir (SS:DD). Tahta internete bağlıyken sunucunun imzalı yanıtındaki saatle kendi saatini
düzeltir; internet yoksa en son aldığı kapanma saatini sistem saatine göre uygular. Boş saat = kapalı.

  python3 -m tahta_kilit.shutdown_schedule --check   (tahta-kilit-kapanis.timer, dakikada bir, root)
"""
import datetime
import hmac
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
import time

from tahta_kilit.google_http import post_json, sign

CONFIG_DIR = "/etc/tahta-kilit"
STATE_PATH = os.path.join(CONFIG_DIR, "shutdown.json")
STAMP_PATH = "/var/lib/tahta-kilit/kapanis-son"
TIME_PATTERN = re.compile(r"([01][0-9]|2[0-3]):[0-5][0-9]")
SIGNATURE_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")
# Kapanma saatinden sonraki bu süre içinde tahta açıksa kapanır; daha geç açılan tahta o gün kapatılmaz.
WINDOW_MINUTES = 5
# Sunucu saati düzeltmesi bu kadar yeni bir eşitlemeden geliyorsa kullanılır; yoksa sistem saati.
CLOCK_TRUST_SECONDS = 15 * 60
MAX_OFFSET_SECONDS = 24 * 3600
MAX_STATE_BYTES = 4096

try:
    from zoneinfo import ZoneInfo
    TURKEY = ZoneInfo("Europe/Istanbul")
except Exception:  # zoneinfo/tzdata yoksa: Türkiye 2016'dan beri sürekli UTC+3
    TURKEY = datetime.timezone(datetime.timedelta(hours=3))


def build_request(board_id, key, nonce=None):
    if nonce is None:
        nonce = secrets.token_hex(16)
    if not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise ValueError("Invalid nonce")
    return {"action": "shutdown-sync", "version": 1, "boardId": board_id, "nonce": nonce,
            "signature": sign(key, "shutdown-sync:v1|" + board_id + "|" + nonce)}


def verify_response(data, board_id, nonce, key):
    """(saat, sunucuZamanıMs) döndürür; sunucu reddettiyse None. Saat '' ise otomatik kapanma kapalıdır."""
    if not isinstance(data, dict):
        raise ValueError("Invalid response")
    if data.get("ok") is not True:
        return None
    if data.get("boardId") != board_id or data.get("nonce") != nonce:
        raise ValueError("Unexpected board or nonce")
    value, server_ms, signature = data.get("time"), data.get("serverTime"), data.get("signature")
    if not isinstance(value, str) or (value and not TIME_PATTERN.fullmatch(value)):
        raise ValueError("Invalid shutdown time")
    if type(server_ms) is not int or not 0 < server_ms < 10 ** 14:
        raise ValueError("Invalid server time")
    if not isinstance(signature, str) or not SIGNATURE_PATTERN.fullmatch(signature):
        raise ValueError("Invalid shutdown signature")
    expected = sign(key, "shutdown-response:v1|{}|{}|{}|{}".format(board_id, nonce, value, server_ms))
    if not hmac.compare_digest(expected, signature):
        raise ValueError("Invalid shutdown signature")
    return value, server_ms


def _trusted(info):
    return stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not stat.S_IMODE(info.st_mode) & 0o022


def read_state(board_id, path=STATE_PATH):
    """shutdown.json geçerli ve bu tahtaya aitse içeriği, değilse None döndürür."""
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            if not _trusted(os.fstat(stream.fileno())):
                return None
            raw = stream.read(MAX_STATE_BYTES + 1)
        if len(raw) > MAX_STATE_BYTES:
            return None
        state = json.loads(raw.decode("utf-8"))
        if not isinstance(state, dict) or state.get("boardId") != board_id:
            return None
        if not isinstance(state.get("time"), str) or (state["time"] and not TIME_PATTERN.fullmatch(state["time"])):
            return None
        for name in ("offset", "syncedAt"):
            if not isinstance(state.get(name), (int, float)) or isinstance(state.get(name), bool):
                return None
        return state
    except (OSError, ValueError, TypeError):
        return None


def write_state(board_id, value, offset, synced_at, path=STATE_PATH):
    directory = os.path.dirname(path)
    info = os.lstat(directory)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
        raise PermissionError("Unprotected configuration directory")
    contents = json.dumps({"boardId": board_id, "time": value, "offset": round(offset, 3),
                           "syncedAt": round(synced_at, 3)}) + "\n"
    descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".shutdown-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        # Kilit ekranı ve tanı okuyabilsin (sır içermez); yalnız root yazar.
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def synchronize_shutdown(config=None, key=None, opener=None, path=STATE_PATH, clock=time.time):
    """Root zamanlayıcısından çağrılır. Kapanma saatini ve sunucu saatini imzalı alıp kaydeder."""
    if config is None or key is None:
        from tahta_kilit.verifier_service import read_config, read_key
        config, key = read_config(), read_key()
    from urllib.parse import urlsplit
    from tahta_kilit.site_url import resolve_site_url
    url = resolve_site_url(config["site_url"])
    if urlsplit(url).hostname != "script.google.com":
        return None
    board = config["board_id"]
    payload = build_request(board, key)
    sent = clock()
    data = post_json(url, payload, MAX_STATE_BYTES, opener)
    received = clock()
    result = verify_response(data, board, payload["nonce"], key)
    if result is None:
        # Sunucu reddettiyse (tahta onaysız / eski sunucu) mevcut kayıt korunur.
        return None
    value, server_ms = result
    # Yanıtın yolda geçen süresinin ortası sunucunun damga anına en yakın yerel andır.
    offset = server_ms / 1000.0 - (sent + received) / 2.0
    if abs(offset) > MAX_OFFSET_SECONDS:
        offset = 0.0
    write_state(board, value, offset, received, path)
    return value


def turkey_now(state, now=None):
    """Türkiye saati. Yeni bir eşitleme varsa sunucu saatiyle düzeltilir, yoksa sistem saati kullanılır."""
    now = time.time() if now is None else now
    if state and 0 <= now - state["syncedAt"] <= CLOCK_TRUST_SECONDS and abs(state["offset"]) <= MAX_OFFSET_SECONDS:
        now += state["offset"]
    return datetime.datetime.fromtimestamp(now, TURKEY)


def due_target(value, current):
    """Kapanma zamanı geldiyse o günün hedef tarihini (YYYY-AA-GG) döndürür, gelmediyse None."""
    if not value or not TIME_PATTERN.fullmatch(value):
        return None
    hour, minute = (int(part) for part in value.split(":"))
    target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    elapsed = (current - target).total_seconds()
    if 0 <= elapsed < WINDOW_MINUTES * 60:
        return target.date().isoformat()
    return None


def _last_done(path=STAMP_PATH):
    try:
        with open(path, encoding="utf-8") as stream:
            return stream.read(32).strip()
    except OSError:
        return ""


def _mark_done(day, path=STAMP_PATH):
    os.makedirs(os.path.dirname(path), mode=0o755, exist_ok=True)
    with open(path, "w", encoding="utf-8") as output:
        output.write(day + "\n")
        output.flush()
        os.fsync(output.fileno())


def check_and_shutdown(now=None, state_path=STATE_PATH, stamp_path=STAMP_PATH, poweroff=None):
    """Kapanma saati geldiyse tahtayı kapatır. Yapılanı kısa bir metinle döndürür (günlük için)."""
    from tahta_kilit.verifier_service import read_config
    board = read_config()["board_id"]
    state = read_state(board, state_path)
    if not state or not state["time"]:
        return "otomatik kapanma kapalı"
    current = turkey_now(state, now)
    day = due_target(state["time"], current)
    if not day:
        return "bekleniyor ({} · Türkiye saati {})".format(state["time"], current.strftime("%H:%M"))
    if _last_done(stamp_path) == day:
        return "bugün zaten kapatıldı"
    # Damga önce yazılır: tahta pencere içinde yeniden açılırsa aynı gün ikinci kez kapanmaz.
    _mark_done(day, stamp_path)
    (poweroff or (lambda: subprocess.run(["/usr/bin/systemctl", "poweroff"], check=False, timeout=60)))()
    return "kapatılıyor ({})".format(state["time"])


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    from tahta_kilit.google_http import describe_error
    try:
        if args == ["--check"]:
            print(check_and_shutdown())
        elif args == ["--sync"]:
            print("Kapanma saati: " + (synchronize_shutdown() or "kapalı / değişmedi"))
        else:
            print("Kullanım: python3 -m tahta_kilit.shutdown_schedule --check | --sync")
            return 2
    except Exception as error:
        # Anahtar ve istek ayrıntısı yazılmaz; yalnız hata türü.
        print("Otomatik kapanma denetlenemedi: " + describe_error(error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
