"""İlk kurulum için tahta kimliği/yapılandırması ve 256 bit anahtar üretir."""

import argparse
import grp
import json
import os
import secrets
import stat
import subprocess
import tempfile
from urllib.parse import urlsplit

from tahta_kilit.protocol import BOARD_ID_PATTERN

CONFIG_DIR = "/etc/tahta-kilit"
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
KEY_PATH = os.path.join(CONFIG_DIR, "board.key")


def write_new_file(path, contents, mode):
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".tahta-kilit-", dir=os.path.dirname(path)
    )
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as output:
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def main():
    parser = argparse.ArgumentParser(
        description="ETAP tahtası için ilk yapılandırmayı hazırlar."
    )
    parser.add_argument("--board-id", required=True, help="Örnek: ETAP-01")
    parser.add_argument(
        "--site-url",
        required=True,
        help="Öğretmenin açacağı HTTPS web adresi, örnek: https://kilit.example/ac",
    )
    args = parser.parse_args()

    if not BOARD_ID_PATTERN.fullmatch(args.board_id):
        parser.error("Tahta kimliği A-Z, 0-9 ve tire karakterlerinden oluşmalıdır.")
    parts = urlsplit(args.site_url)
    try:
        port = parts.port
    except ValueError:
        parser.error("--site-url içindeki bağlantı noktası geçersizdir.")
    if (
        args.site_url != args.site_url.strip()
        or any(ord(character) < 0x21 or ord(character) == 0x7F for character in args.site_url)
        or parts.scheme != "https"
        or not parts.hostname
        or port not in (None, 443)
        or parts.username
        or parts.password
        or parts.path not in ("", "/", "/ac")
        or parts.query
        or parts.fragment
    ):
        parser.error("--site-url HTTPS olmalı ve query/fragment içermemelidir.")

    if os.path.lexists(KEY_PATH) or os.path.lexists(CONFIG_PATH):
        raise SystemExit(
            "Yapılandırma veya anahtar zaten var. Güvenlik için mevcut dosyaların "
            "üzerine yazılmadı; yöneticiyle anahtar yenileme prosedürünü uygulayın."
        )

    group_id = grp.getgrnam("tahta-kilit").gr_gid
    try:
        os.mkdir(CONFIG_DIR, mode=0o750)
    except FileExistsError:
        pass
    directory_info = os.lstat(CONFIG_DIR)
    if (
        not stat.S_ISDIR(directory_info.st_mode)
        or directory_info.st_uid != 0
        or stat.S_IMODE(directory_info.st_mode) & 0o022
    ):
        raise PermissionError("Tahta ayar dizini root tarafından korunmalıdır.")
    os.chown(CONFIG_DIR, 0, group_id)
    os.chmod(CONFIG_DIR, 0o750)
    config = json.dumps(
        {"board_id": args.board_id, "site_url": args.site_url},
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8") + b"\n"
    key_created = False
    try:
        write_new_file(KEY_PATH, secrets.token_bytes(32), 0o600)
        key_created = True
        write_new_file(CONFIG_PATH, config, 0o640)
    except FileExistsError:
        if key_created and not os.path.lexists(CONFIG_PATH):
            os.unlink(KEY_PATH)
        raise SystemExit(
            "Kurulum sırasında dosya zaten oluştu. Hiçbir mevcut dosya değiştirilmedi."
        )
    except Exception:
        if key_created and not os.path.lexists(CONFIG_PATH):
            os.unlink(KEY_PATH)
        raise

    os.chown(KEY_PATH, 0, 0)
    os.chown(CONFIG_PATH, 0, group_id)
    os.chmod(KEY_PATH, 0o600)
    os.chmod(CONFIG_PATH, 0o640)
    print("Tahta yapılandırması oluşturuldu. Anahtar stdout'a veya loglara yazılmadı.")
    try:
        service_result = subprocess.run(
            ["systemctl", "enable", "--now", "tahta-kilit-verifier.service"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        service_result = None

    if service_result is not None and service_result.returncode == 0:
        print("Yerel doğrulama servisi etkinleştirildi ve başlatıldı.")
    else:
        print(
            "Yapılandırma tamamlandı; doğrulama servisi başlatılamadı. "
            "Yönetici şu komutla başlatabilir:"
        )
        print("  sudo systemctl enable --now tahta-kilit-verifier.service")

    print("Web sunucusuna aktarılacak Base64 anahtarı yetkili yönetici alsın:")
    print("  sudo base64 -w 0 {}".format(KEY_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
