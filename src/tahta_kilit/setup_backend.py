"""Sınırlı polkit kurulum işlemi; yalnız GUI çağıranının oturumunu yapılandırır."""

import contextlib
import io
import json
import os
import pwd
import subprocess
import sys
import stat
import tempfile
from base64 import b64encode

from tahta_kilit import provision
from tahta_kilit.verifier_service import read_config, read_key
from tahta_kilit.shortcut_protection import protect_shortcut
from tahta_kilit.site_url import validate_site_url


def configure(arguments):
    if os.geteuid() != 0:
        raise PermissionError("Kurulum için yönetici yetkisi gerekiyor.")
    caller_text = os.environ.get("PKEXEC_UID", "")
    if not caller_text.isascii() or not caller_text.isdecimal():
        raise PermissionError("Kurulumu uygulama menüsünden açın.")
    caller = pwd.getpwuid(int(caller_text))
    if caller.pw_uid < 1000 or caller.pw_shell in ("/usr/sbin/nologin", "/bin/false"):
        raise PermissionError("Kurulumu standart grafik oturum hesabında açın.")
    if len(arguments) == 2 and arguments[0] in ("--protect-shortcut", "--unprotect-shortcut"):
        return protect_shortcut(caller, arguments[1], arguments[0] == "--protect-shortcut")
    if len(arguments) not in (2, 3):
        raise ValueError("Tahta kimliği ve HTTPS web adresi gerekiyor.")
    validate_site_url(arguments[1])

    key_exists = os.path.lexists(provision.KEY_PATH)
    config_exists = os.path.lexists(provision.CONFIG_PATH)
    if key_exists != config_exists:
        raise ValueError("Kurulum dosyaları eksik. Mevcut dosyaları silmeden yöneticinizle kontrol edin.")
    if not key_exists:
        previous_argv = sys.argv
        try:
            sys.argv = ["provision", "--board-id", arguments[0], "--site-url", arguments[1]]
            # Provision aracının açıklamalarını gizli JSON yanıtına karıştırma.
            with contextlib.redirect_stdout(io.StringIO()):
                provision.main()
        finally:
            sys.argv = previous_argv

    config = read_config()
    key = read_key()
    if config["board_id"] != arguments[0]:
        raise ValueError("Mevcut tahta kimliğini değiştirmeyin; aynı kimlikle site adresini güncelleyin.")
    if config["site_url"] != arguments[1]:
        directory = os.lstat(provision.CONFIG_DIR)
        if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != 0 or stat.S_IMODE(directory.st_mode) & 0o022:
            raise PermissionError("Tahta ayar dizini root tarafından korunmalıdır.")
        current = os.stat(provision.CONFIG_PATH)
        config["site_url"] = arguments[1]
        descriptor, temporary = tempfile.mkstemp(prefix=".site-update-", dir=provision.CONFIG_DIR)
        try:
            os.fchown(descriptor, 0, current.st_gid)
            os.fchmod(descriptor, 0o640)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(config, output, ensure_ascii=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, provision.CONFIG_PATH)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    # Hiçbir shell kullanılmaz; hesap PKEXEC_UID üzerinden sistemden seçilir.
    subprocess.run(
        ["/usr/sbin/usermod", "-aG", "tahta-kilit", "--", caller.pw_name],
        check=True, capture_output=True, timeout=30,
    )
    subprocess.run(
        ["/usr/bin/systemctl", "enable", "--now", "tahta-kilit-verifier.service"],
        check=True, capture_output=True, timeout=30,
    )
    result = {
        "boardId": config["board_id"],
        "siteUrl": config["site_url"],
        "sessionUser": caller.pw_name,
        "boardKeysEntry": {config["board_id"]: b64encode(key).decode("ascii")},
        "existing": key_exists,
    }
    if len(arguments) == 3:
        try:
            result.update(protect_shortcut(caller, arguments[2]))
        except (OSError, ValueError, PermissionError):
            result["shortcutProtected"] = False
    return result


def main():
    try:
        result = configure(sys.argv[1:])
    except SystemExit:
        print("Tahta kimliği veya HTTPS web adresi geçersiz.", file=sys.stderr)
        return 1
    except (PermissionError, ValueError, KeyError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except (subprocess.SubprocessError, RuntimeError):
        print("Oturum grubu veya doğrulama servisi ayarlanamadı. Yönetici kurulumu kontrol etsin.", file=sys.stderr)
        return 1
    # Sır yalnız yetkilendirilmiş GUI'nin özel stdout borusuna gönderilir.
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
