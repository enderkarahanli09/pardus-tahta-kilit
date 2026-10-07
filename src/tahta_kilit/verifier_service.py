"""Root yetkili Unix soketi üzerinden çevrimdışı QR/kod doğrulayıcısı."""

import json
import grp
import logging
import os
import secrets
import socketserver
import stat
import threading
import time
from collections import deque
from urllib.parse import urlsplit

from tahta_kilit.protocol import BOARD_ID_PATTERN, code_matches, qr_signature

CONFIG_PATH = "/etc/tahta-kilit/config.json"
KEY_PATH = "/etc/tahta-kilit/board.key"
SOCKET_PATH = "/run/tahta-kilit/verifier.sock"
SOCKET_GROUP = "tahta-kilit"
CHALLENGE_TTL_SECONDS = 120
UNLOCK_SECONDS = 40 * 60
MAX_BAD_CODES_PER_CHALLENGE = 5
MAX_BAD_CODES_PER_TEN_MINUTES = 10
MAX_REQUEST_BYTES = 4096
MAX_CONCURRENT_CLIENTS = 8
MAX_CONFIG_BYTES = 4096


class ServiceError(Exception):
    def __init__(self, code, retry_after=None):
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after


def read_config():
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(CONFIG_PATH, flags)
    with os.fdopen(descriptor, "rb") as config_file:
        info = os.fstat(config_file.fileno())
        expected_group = grp.getgrnam(SOCKET_GROUP).gr_gid
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_gid != expected_group
            or stat.S_IMODE(info.st_mode) != 0o640
            or info.st_size > MAX_CONFIG_BYTES
        ):
            raise PermissionError("Tahta yapılandırması root tarafından korunmalıdır.")
        raw_config = config_file.read(MAX_CONFIG_BYTES + 1)
    if len(raw_config) > MAX_CONFIG_BYTES:
        raise ValueError("Tahta yapılandırması çok büyük.")
    config = json.loads(raw_config.decode("utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Tahta yapılandırması geçersiz.")
    board_id = config.get("board_id")
    site_url = config.get("site_url")
    if not isinstance(board_id, str) or not BOARD_ID_PATTERN.fullmatch(board_id):
        raise ValueError("Tahta kimliği yapılandırılmamış.")
    if not isinstance(site_url, str) or len(site_url) > 2048:
        raise ValueError("Web adresi HTTPS olmalıdır.")
    try:
        parsed_url = urlsplit(site_url)
        port = parsed_url.port
    except ValueError as error:
        raise ValueError("Web adresi geçersiz.") from error
    if (
        site_url != site_url.strip()
        or any(ord(character) < 0x21 or ord(character) == 0x7F for character in site_url)
        or parsed_url.scheme != "https"
        or not parsed_url.hostname
        or port not in (None, 443)
        or parsed_url.username
        or parsed_url.password
        or parsed_url.path not in ("", "/", "/ac")
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise ValueError("Web adresi HTTPS olmalı ve yalnız /ac yolu kullanmalıdır.")
    return {"board_id": board_id, "site_url": site_url}


def read_key():
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(KEY_PATH, flags)
    with os.fdopen(descriptor, "rb") as key_file:
        info = os.fstat(key_file.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size != 32
        ):
            raise PermissionError("Tahta anahtarı root tarafından korunmalıdır.")
        key = key_file.read(33)
    if len(key) != 32:
        raise ValueError("Tahta anahtarı tam olarak 32 bayt olmalıdır.")
    return key


class Verifier:
    def __init__(self, board_id, key):
        self.board_id = board_id
        self.key = key
        self.lock = threading.Lock()
        self.challenge = None
        self.bad_codes_for_challenge = 0
        self.recent_failures = deque()
        self.cooldown_until = 0.0

    def _cooldown_remaining(self, now):
        if now >= self.cooldown_until:
            self.cooldown_until = 0.0
            return 0
        return max(1, int(self.cooldown_until - now + 0.999))

    def _ensure_available(self, now):
        remaining = self._cooldown_remaining(now)
        if remaining:
            raise ServiceError("cooldown", remaining)

    def _prune_failures(self, now):
        while self.recent_failures and now - self.recent_failures[0] > 600:
            self.recent_failures.popleft()

    def get_challenge(self):
        with self.lock:
            now = time.monotonic()
            self._ensure_available(now)
            if self.challenge is None or now >= self.challenge["expires_at"]:
                nonce = secrets.token_hex(16)
                self.challenge = {
                    "nonce": nonce,
                    "expires_at": now + CHALLENGE_TTL_SECONDS,
                }
                self.bad_codes_for_challenge = 0

            seconds_left = max(
                1, int(self.challenge["expires_at"] - now + 0.999)
            )
            return {
                "ok": True,
                "boardId": self.board_id,
                "nonce": self.challenge["nonce"],
                "qrSignature": qr_signature(
                    self.key, self.board_id, self.challenge["nonce"]
                ),
                "expiresIn": seconds_left,
            }

    def verify(self, nonce, candidate):
        with self.lock:
            now = time.monotonic()
            self._ensure_available(now)
            if self.challenge is None:
                raise ServiceError("stale_challenge")
            if now >= self.challenge["expires_at"]:
                self.challenge = None
                self.bad_codes_for_challenge = 0
                raise ServiceError("stale_challenge")
            if (
                not isinstance(nonce, str)
                or not secrets.compare_digest(nonce, self.challenge["nonce"])
            ):
                raise ServiceError("stale_challenge")

            if code_matches(self.key, self.board_id, nonce, candidate):
                self.challenge = None
                self.bad_codes_for_challenge = 0
                self.recent_failures.clear()
                return {"ok": True, "unlockSeconds": UNLOCK_SECONDS}

            self.bad_codes_for_challenge += 1
            self.recent_failures.append(now)
            self._prune_failures(now)
            if len(self.recent_failures) >= MAX_BAD_CODES_PER_TEN_MINUTES:
                self.cooldown_until = now + 60
                raise ServiceError("cooldown", 60)
            if self.bad_codes_for_challenge >= MAX_BAD_CODES_PER_CHALLENGE:
                self.cooldown_until = now + 30
                raise ServiceError("cooldown", 30)
            raise ServiceError("invalid_code")


class RequestHandler(socketserver.StreamRequestHandler):
    def setup(self):
        self.request.settimeout(3)
        super().setup()

    def handle(self):
        try:
            raw_request = self.rfile.readline(MAX_REQUEST_BYTES + 1)
            if not raw_request.endswith(b"\n") or len(raw_request) > MAX_REQUEST_BYTES:
                raise ServiceError("invalid_request")
            request = json.loads(raw_request.decode("utf-8"))
            response = self.dispatch(request)
        except ServiceError as error:
            response = {"ok": False, "error": error.code}
            if error.retry_after is not None:
                response["retryAfter"] = error.retry_after
        except (ValueError, UnicodeError, json.JSONDecodeError):
            response = {"ok": False, "error": "invalid_request"}
        except Exception:
            logging.warning("Yerel doğrulama isteği işlenemedi.")
            response = {"ok": False, "error": "internal_error"}

        try:
            encoded = json.dumps(response, separators=(",", ":")).encode("utf-8")
            self.wfile.write(encoded + b"\n")
        except OSError:
            pass

    def dispatch(self, request):
        if not isinstance(request, dict):
            raise ServiceError("invalid_request")
        action = request.get("action")
        if action == "challenge":
            return self.server.verifier.get_challenge()
        if action == "verify":
            return self.server.verifier.verify(
                request.get("nonce"), request.get("unlockCode")
            )
        raise ServiceError("invalid_request")


class UnixServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 16

    def __init__(self, socket_path, verifier):
        self.verifier = verifier
        self.request_slots = threading.BoundedSemaphore(MAX_CONCURRENT_CLIENTS)
        super().__init__(socket_path, RequestHandler)

    def process_request(self, request, client_address):
        if not self.request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        worker = threading.Thread(
            target=self.process_request_thread,
            args=(request, client_address),
            daemon=self.daemon_threads,
        )
        try:
            worker.start()
        except Exception:
            self.request_slots.release()
            self.shutdown_request(request)
            self.handle_error(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.request_slots.release()


def prepare_socket_path():
    if os.path.lexists(SOCKET_PATH):
        info = os.lstat(SOCKET_PATH)
        if not stat.S_ISSOCK(info.st_mode):
            raise RuntimeError("Soket yolunda beklenmeyen bir dosya var.")
        os.unlink(SOCKET_PATH)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    config = read_config()
    key = read_key()
    verifier = Verifier(config["board_id"], key)
    prepare_socket_path()
    server = UnixServer(SOCKET_PATH, verifier)
    group_id = grp.getgrnam(SOCKET_GROUP).gr_gid
    os.chown(SOCKET_PATH, 0, group_id)
    os.chmod(SOCKET_PATH, 0o660)
    logging.info("Tahta doğrulama servisi hazır.")
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)


if __name__ == "__main__":
    main()
