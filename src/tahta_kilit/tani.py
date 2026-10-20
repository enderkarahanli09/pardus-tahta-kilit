"""BB Kilit tanı aracı: tahtadaki kurulumu baştan sona denetler ve rapor yazar.

Kullanım (root): sudo bb-kilit-tani [--onar] [--usb]
  --onar  güvenli onarımları uygular (servisleri etkinleştirir/yeniden başlatır, master eşitler,
          oturum kullanıcısını tahta-kilit grubuna ekler), sonra denetimi yeniden çalıştırır.
  --usb   raporu takılı USB belleklere de kopyalar.

Rapor hiçbir sır içermez: tahta anahtarı, master özeti, nonce ve imzalar yazdırılmaz.
"""
import argparse
import datetime
import glob
import grp
import json
import os
import pwd
import re
import shutil
import socket
import stat
import subprocess
import sys
import time

from tahta_kilit.google_http import describe_error

CONFIG_DIR = "/etc/tahta-kilit"
CONFIG_PATH = CONFIG_DIR + "/config.json"
KEY_PATH = CONFIG_DIR + "/board.key"
MASTER_PATH = CONFIG_DIR + "/master.json"
PORTAL_PATH = CONFIG_DIR + "/portal.json"
RUN_DIR = "/run/tahta-kilit"
SOCKET_PATH = RUN_DIR + "/verifier.sock"
GROUP = "tahta-kilit"
REPORT_PATH = "/var/log/bb-kilit-tani.txt"
SCREEN_DIR = "/run/bb-kilit-tani"
SCREEN_REPORT_PATH = SCREEN_DIR + "/rapor.txt"
SYSTEM_UNITS = ("tahta-kilit-verifier.service", "tahta-kilit-master-sync.timer", "tahta-kilit-master-sync.service",
                "tahta-kilit-kapanis.timer")


# Rapor kilit ekranında açılmadan önce de görülebilir; anahtar/imza/nonce gibi görünen her dizi gizlenir.
# Apps Script /exec adresleri ("/s/AKfycb…") ve onay kodu (ABCD-1234) gizli değildir, korunur.
SECRET_PATTERNS = (
    re.compile(r"(?<![/A-Za-z0-9_+=-])[A-Za-z0-9+/_-]{40,}={0,2}(?![A-Za-z0-9_+/=-])"),
    re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32,}(?![0-9a-fA-F])"),
    re.compile(r"(?i)\b(bilet|token|sig|signature|nonce|key|password|parola)=([^\s&]+)"),
)


def _looks_secret(match):
    # Base64 anahtar/imza: büyük harf, küçük harf ve rakam birlikte. Dosya yolları ve tahta kimlikleri böyle değildir.
    value = match.group(0)
    if "AKfycb" in value:
        return value  # Apps Script dağıtım kimliği (herkese açık /exec adresi), gizli değil
    mixed = re.search(r"[a-z]", value) and re.search(r"[A-Z]", value) and re.search(r"[0-9]", value)
    return "[gizlendi]" if mixed else value


def redact(text):
    text = SECRET_PATTERNS[0].sub(_looks_secret, text)
    text = SECRET_PATTERNS[1].sub("[gizlendi]", text)
    return SECRET_PATTERNS[2].sub(lambda match: match.group(1) + "=[gizlendi]", text)


class Report:
    def __init__(self, quiet=False):
        self.lines = []
        self.problems = []
        self.quiet = quiet

    def write(self, text=""):
        text = redact(text)
        if not self.quiet:
            print(text)
        self.lines.append(text)

    def section(self, title):
        self.write("")
        self.write("== " + title + " ==")

    def ok(self, text):
        self.write("[ OK ] " + text)

    def info(self, text):
        self.write("[BİLGİ] " + text)

    def warn(self, text, hint=None):
        self.write("[UYARI] " + text + (" → " + hint if hint else ""))

    def fail(self, text, hint=None):
        self.write("[HATA] " + text + (" → " + hint if hint else ""))
        self.problems.append(text + (" → " + hint if hint else ""))

    def block(self, text):
        for line in (text or "").rstrip().splitlines()[-40:]:
            self.write("    " + line)


def run(command, timeout=20):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        return result.returncode, (result.stdout + result.stderr).strip()
    except (OSError, subprocess.SubprocessError) as error:
        return -1, describe_error(error)


def mode_text(info):
    owner = pwd.getpwuid(info.st_uid).pw_name if _has_uid(info.st_uid) else str(info.st_uid)
    try:
        group = grp.getgrgid(info.st_gid).gr_name
    except KeyError:
        group = str(info.st_gid)
    return "{:o} {}:{}".format(stat.S_IMODE(info.st_mode), owner, group)


def _has_uid(uid):
    try:
        pwd.getpwuid(uid)
        return True
    except KeyError:
        return False


def group_id():
    try:
        return grp.getgrnam(GROUP).gr_gid
    except KeyError:
        return None


def check_package(report):
    report.section("Paket")
    code, output = run(["dpkg-query", "-W", "-f=${Version}", "tahta-kilit"])
    if code == 0:
        report.ok("tahta-kilit sürümü " + output)
    else:
        report.fail("tahta-kilit paketi kurulu görünmüyor", "paketi yeniden kurun")
    code, output = run(["uname", "-r"])
    report.info("Çekirdek " + output)
    report.info("Python " + sys.version.split()[0])


def check_files(report):
    report.section("Yapılandırma dosyaları")
    gid = group_id()
    if gid is None:
        report.fail("'{}' grubu yok".format(GROUP), "paketi yeniden kurun (postinst grubu oluşturur)")
    expected = {
        CONFIG_DIR: (0o750, "dizin"),
        CONFIG_PATH: (0o640, "config.json"),
        KEY_PATH: (0o600, "board.key"),
    }
    for path, (mode, label) in expected.items():
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            report.fail("{} yok ({})".format(label, path), "kurulum uygulamasını (BB Kilit Kurulum) çalıştırın")
            continue
        text = mode_text(info)
        good = info.st_uid == 0 and stat.S_IMODE(info.st_mode) == mode
        if path != KEY_PATH and gid is not None:
            good = good and info.st_gid == gid
        if path == KEY_PATH and info.st_size != 32:
            report.fail("board.key boyutu {} bayt (32 olmalı)".format(info.st_size), "kurulumu yeniden yapın")
        (report.ok if good else report.fail)(
            "{} izinleri {}".format(label, text),
            *(() if good else ("beklenen {:o} root:{}; --onar düzeltmez, yöneticiye bildirin".format(mode, GROUP),)))

    config = key = None
    try:
        from tahta_kilit.verifier_service import read_config, read_key
        config = read_config()
        report.ok("config.json okundu: tahta {} · servis {}".format(config["board_id"], config["site_url"]))
    except Exception as error:
        report.fail("config.json doğrulanamadı: " + describe_error(error))
    try:
        from tahta_kilit.verifier_service import read_key
        key = read_key()
        from tahta_kilit.board_registration import fingerprint
        report.ok("board.key okundu · onay kodu (parmak izi) " + fingerprint(key))
    except Exception as error:
        report.fail("board.key doğrulanamadı: " + describe_error(error))

    try:
        info = os.lstat(MASTER_PATH)
        report.info("master.json izinleri " + mode_text(info))
        if config:
            from tahta_kilit.master_password import read_state
            state = read_state(config["board_id"])
            if state is None:
                report.fail("master.json var ama geçersiz/izinleri yanlış veya başka tahtaya ait",
                            "--onar ile master eşitlemesini yeniden çalıştırın")
            else:
                count = len(state.get("entries", [state]))
                (report.ok if count else report.fail)(
                    "master kaydı sürüm {} · {} parola".format(state["version"], count),
                    *(() if count else ("yönetim panelinden master parola belirleyin",)))
    except FileNotFoundError:
        report.fail("master.json yok: master parola tahtaya hiç inmemiş",
                    "aşağıdaki 'Sunucu' bölümüne bakın; --onar eşitlemeyi dener")
    if config:
        from tahta_kilit import shutdown_schedule
        state = shutdown_schedule.read_state(config["board_id"])
        if state is None:
            report.info("Otomatik kapanma: kayıt yok (panelde saat ayarlanmamış veya henüz eşitlenmedi)")
        else:
            current = shutdown_schedule.turkey_now(state)
            age = int(datetime.datetime.now().timestamp() - state["syncedAt"])
            report.info("Otomatik kapanma: {} · Türkiye saati şimdi {} · son eşitleme {} sn önce · saat farkı {:+.0f} sn".format(
                state["time"] or "kapalı", current.strftime("%H:%M"), age, state["offset"]))
            if state["time"] and abs(state["offset"]) > 120:
                report.warn("Tahta saati sunucudan {:+.0f} sn farklı".format(state["offset"]),
                            "internetsizken kapanma bu kadar kayabilir; tarih/saat ayarını (NTP) kontrol edin")
    try:
        with open(PORTAL_PATH, encoding="utf-8") as stream:
            portal = json.load(stream)
        report.info("portal.json: QR adresi " + str(portal.get("portalUrl")))
    except FileNotFoundError:
        report.info("portal.json yok (QR varsayılan portal adresini kullanır)")
    except Exception as error:
        report.warn("portal.json okunamadı: " + describe_error(error))
    return config, key


def check_services(report):
    report.section("Sistem servisleri")
    for unit in SYSTEM_UNITS:
        _, enabled = run(["systemctl", "is-enabled", unit])
        _, active = run(["systemctl", "is-active", unit])
        _, details = run(["systemctl", "show", unit, "-p", "Result", "-p", "ExecMainStatus", "-p", "NRestarts"])
        details = " ".join(details.split())
        line = "{}: etkin={} durum={} {}".format(unit, enabled, active, details)
        if unit == "tahta-kilit-master-sync.service":
            # Tek seferlik servis; 'inactive' normaldir, Result=success olmalı.
            bad = "Result=success" not in details and active != "activating"
        else:
            bad = active != "active" or enabled != "enabled"
        if bad:
            report.fail(line, "sudo bb-kilit-tani --onar")
        else:
            report.ok(line)
    for unit, lines in (("tahta-kilit-verifier.service", 30), ("tahta-kilit-master-sync.service", 20),
                        ("tahta-kilit-kapanis.service", 6)):
        report.info("Son günlük: " + unit)
        report.block(run(["journalctl", "-b", "--no-pager", "-o", "short-monotonic", "-n", str(lines), "-u", unit])[1])


def session_processes():
    """Çalışan kilit ekranı süreçleri: (pid, uid, gid, ek gruplar, DISPLAY)."""
    found = []
    for status_path in glob.glob("/proc/[0-9]*/status"):
        pid = status_path.split("/")[2]
        try:
            with open("/proc/{}/cmdline".format(pid), "rb") as stream:
                cmdline = stream.read().replace(b"\0", b" ").decode("utf-8", "replace")
            if "tahta_kilit.lock_screen" not in cmdline:
                continue
            fields = {}
            with open(status_path, encoding="utf-8") as stream:
                for line in stream:
                    name, _, value = line.partition(":")
                    fields[name] = value.split()
            display = ""
            with open("/proc/{}/environ".format(pid), "rb") as stream:
                for item in stream.read().split(b"\0"):
                    if item.startswith(b"DISPLAY="):
                        display = item[8:].decode("utf-8", "replace")
            found.append((int(pid), int(fields["Uid"][0]), int(fields["Gid"][0]),
                          [int(g) for g in fields.get("Groups", [])], display))
        except (OSError, KeyError, ValueError, IndexError):
            continue
    return found


def ask_verifier_as(uid, gid, groups):
    """Alt süreçte verilen kimliğe geçip sokete 'challenge' sorar; sonuç metni döner."""
    read_end, write_end = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_end)
        try:
            os.setgroups(groups)
            os.setgid(gid)
            os.setuid(uid)
            result = ask_verifier()
        except Exception as error:
            result = "kimlik değiştirilemedi: " + describe_error(error)
        os.write(write_end, result.encode("utf-8")[:2000])
        os._exit(0)
    os.close(write_end)
    chunks = []
    while True:
        chunk = os.read(read_end, 4096)
        if not chunk:
            break
        chunks.append(chunk)
    os.close(read_end)
    os.waitpid(pid, 0)
    return b"".join(chunks).decode("utf-8", "replace")


def ask_verifier():
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(3)
            connection.connect(SOCKET_PATH)
            connection.sendall(b'{"action":"challenge"}\n')
            raw = b""
            while not raw.endswith(b"\n") and len(raw) <= 4096:
                part = connection.recv(4096)
                if not part:
                    break
                raw += part
        response = json.loads(raw.decode("utf-8"))
    except Exception as error:
        return "BAĞLANAMADI: " + describe_error(error)
    if response.get("ok"):
        # Nonce/imza yazdırılmaz; yalnız QR'ın üretilebildiği bilgisi.
        return "OK tahta={} süre={}sn".format(response.get("boardId"), response.get("expiresIn"))
    return "SERVİS HATASI: " + str(response.get("error"))


def check_socket(report):
    report.section("Doğrulama soketi")
    gid = group_id()
    for path in (RUN_DIR, SOCKET_PATH):
        try:
            info = os.lstat(path)
            report.info("{} {}".format(path, mode_text(info)))
        except FileNotFoundError:
            report.fail(path + " yok: doğrulama servisi çalışmıyor", "sudo bb-kilit-tani --onar")
    result = ask_verifier()
    if result.startswith("OK"):
        report.ok("root olarak QR isteği: " + result)
    else:
        report.fail("root olarak QR isteği: " + result, "servis günlüğüne bakın (yukarıda)")

    report.section("Kilit ekranı oturumu")
    processes = session_processes()
    if not processes:
        report.warn("Çalışan kilit ekranı süreci bulunamadı",
                    "konsoldan çalıştırdıysanız normal; grafik oturumda kilit görünmüyorsa oturum günlüğüne bakın")
    for pid, uid, pgid, groups, display in processes:
        name = pwd.getpwuid(uid).pw_name if _has_uid(uid) else str(uid)
        in_group = gid is not None and (gid in groups or gid == pgid)
        report.info("Kilit ekranı pid {} · kullanıcı {} · DISPLAY={}".format(pid, name, display or "?"))
        if in_group:
            report.ok("Süreç '{}' grubunda".format(GROUP))
        else:
            report.fail("Kilit ekranı süreci '{}' grubunda DEĞİL".format(GROUP),
                        "grup eklendikten sonra oturum yenilenmemiş; tahtayı yeniden başlatın")
        result = ask_verifier_as(uid, pgid, groups)
        if result.startswith("OK"):
            report.ok("Kilit ekranının kimliğiyle QR isteği: " + result)
        else:
            report.fail("Kilit ekranının kimliğiyle QR isteği: " + result,
                        "PermissionError ise grup/oturum sorunu; FileNotFoundError ise servis çalışmıyor")
    user = os.environ.get("SUDO_USER")
    if user and user != "root":
        try:
            entry = pwd.getpwnam(user)
            member = gid is not None and (user in grp.getgrgid(gid).gr_mem or entry.pw_gid == gid)
            (report.ok if member else report.fail)(
                "Kullanıcı {} grup kaydında {}".format(user, "var" if member else "yok"),
                *(() if member else ("sudo bb-kilit-tani --onar (sonra yeniden başlatın)",)))
        except KeyError:
            pass
    report.info("Kilit ekranı günlüğü (kullanıcı servisi)")
    report.block(run(["journalctl", "-b", "--no-pager", "-o", "short-monotonic", "-n", "25",
                      "_SYSTEMD_USER_UNIT=tahta-kilit-ui.service"])[1])


def check_server(report, config, key, allow_register=True):
    report.section("Sunucu (Google Apps Script)")
    if not config or not key:
        report.fail("Yapılandırma/anahtar okunamadığı için sunucu denenmedi")
        return
    from tahta_kilit.site_url import resolve_site_url
    from urllib.parse import urlsplit
    try:
        url = resolve_site_url(config["site_url"])
    except ValueError as error:
        report.fail("Servis adresi geçersiz: " + describe_error(error))
        return
    host = urlsplit(url).hostname
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
        report.ok("DNS {} → {}".format(host, ", ".join(addresses[:3])))
    except OSError as error:
        report.fail("DNS çözülemedi ({}): {}".format(host, describe_error(error)), "internet/DNS ayarlarını kontrol edin")
        return
    _, clock = run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"])
    report.info("Saat {} · NTP eşitli={}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), clock or "?"))

    from tahta_kilit.master_password import fetch_master
    master_ok = False
    try:
        data = fetch_master(config, key)
        if data is None:
            report.fail("master-sync: sunucu reddetti (ok:false)",
                        "tahta anahtarı sunucuda onaylı değil ya da panelde master parola yok; aşağıdaki kayıt durumuna bakın")
        else:
            master_ok = True
            report.ok("master-sync: imza geçerli · sürüm {} · {} parola".format(
                data["version"], len(data.get("entries", [data]))))
    except Exception as error:
        report.fail("master-sync isteği başarısız: " + describe_error(error))

    try:
        from tahta_kilit.google_http import post_json
        from tahta_kilit.portal_sync import build_portal_request, verify_portal_response
        payload = build_portal_request(config["board_id"], key)
        portal = verify_portal_response(post_json(url, payload), config["board_id"], payload["nonce"], key)
        report.ok("portal-sync: " + (portal or "sunucuda adres ayarı yok (varsayılan kullanılır)"))
    except Exception as error:
        report.warn("portal-sync başarısız: " + describe_error(error))

    try:
        from tahta_kilit import shutdown_schedule
        from tahta_kilit.google_http import post_json
        payload = shutdown_schedule.build_request(config["board_id"], key)
        result = shutdown_schedule.verify_response(post_json(url, payload), config["board_id"], payload["nonce"], key)
        if result is None:
            report.warn("shutdown-sync: sunucu yanıt vermedi (sunucu eski sürüm veya tahta onaysız)")
        else:
            report.ok("shutdown-sync: kapanma saati {}".format(result[0] or "kapalı"))
    except Exception as error:
        report.warn("shutdown-sync başarısız: " + describe_error(error))

    if not master_ok and not allow_register:
        report.info("Kayıt durumu otomatik denetimde sorulmaz (sunucuda bekleyen kayıt oluşturabilir); "
                    "kurulum uygulamasındaki 'Kaydı gönder' ile veya sudo bb-kilit-tani ile denetlenir")
    if not master_ok and allow_register:
        # "Kaydı tekrar gönder" düğmesiyle aynı istek: anahtar zaten onaylıysa yalnız 'registered' döner.
        from tahta_kilit import board_registration
        try:
            result = board_registration.register(url, config["board_id"], key)
            if result["status"] == "registered":
                report.ok("Kayıt durumu: tahta anahtarı sunucuda ONAYLI (onay kodu {})".format(result["fingerprint"]))
                report.fail("Tahta onaylı ama master gelmiyor", "yönetim panelinde master parolayı (yeniden) kaydedin")
            else:
                report.fail("Kayıt durumu: bu anahtar ONAY BEKLİYOR (onay kodu {})".format(result["fingerprint"]),
                            "sunucu bu tahtanın şu anki anahtarını tanımıyor (tahta yeniden kurulduysa eski onay geçersizdir); "
                            "yönetim panelinde 'Onay bekleyen tahtalar'dan bu onay kodunu onaylayın")
        except Exception as error:
            report.fail("Kayıt durumu sorgulanamadı: " + describe_error(error))


def repair(report):
    report.section("Onarım")
    user = os.environ.get("SUDO_USER")
    gid = group_id()
    if user and user != "root" and gid is not None:
        try:
            if user not in grp.getgrgid(gid).gr_mem and pwd.getpwnam(user).pw_gid != gid:
                code, output = run(["usermod", "-aG", GROUP, "--", user])
                (report.ok if code == 0 else report.fail)("{} grubuna {} eklendi ({})".format(GROUP, user, output or code))
        except KeyError:
            pass
    steps = (
        ["systemctl", "daemon-reload"],
        ["systemctl", "reset-failed", "tahta-kilit-verifier.service", "tahta-kilit-master-sync.service"],
        ["systemctl", "enable", "tahta-kilit-verifier.service"],
        ["systemctl", "restart", "tahta-kilit-verifier.service"],
        ["systemctl", "enable", "--now", "tahta-kilit-master-sync.timer"],
        ["systemctl", "start", "tahta-kilit-master-sync.service"],
    )
    for command in steps:
        code, output = run(command, timeout=120)
        text = " ".join(command[1:])
        if code == 0:
            report.ok(text)
        else:
            report.fail("{} başarısız: {}".format(text, output[-300:]))


def save(report, usb):
    text = "\n".join(report.lines) + "\n"
    try:
        with open(REPORT_PATH, "w", encoding="utf-8") as output:
            output.write(text)
        os.chmod(REPORT_PATH, 0o644)
        print("\nRapor kaydedildi: " + REPORT_PATH)
    except OSError as error:
        print("\nRapor kaydedilemedi: " + describe_error(error))
    if not usb:
        return
    copied = False
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    for mount in glob.glob("/media/*/*") + glob.glob("/run/media/*/*") + glob.glob("/media/*"):
        if not os.path.ismount(mount):
            continue
        target = os.path.join(mount, "bb-kilit-tani-{}.txt".format(stamp))
        try:
            shutil.copyfile(REPORT_PATH, target)
            os.sync()
            print("USB'ye kopyalandı: " + target)
            copied = True
        except OSError:
            continue
    if not copied:
        print("Takılı USB bellek bulunamadı (önce masaüstünde açılmalı/bağlanmalı).")


def auto_repair(report):
    """Zamanlayıcıdan: doğrulama servisi çalışmıyorsa sıfırlayıp yeniden başlatır (dosyalara dokunmaz)."""
    _, active = run(["systemctl", "is-active", "tahta-kilit-verifier.service"])
    if active == "active" or not (os.path.exists(CONFIG_PATH) and os.path.exists(KEY_PATH)):
        return
    report.section("Otomatik onarım")
    report.info("Doğrulama servisi '{}' durumundaydı; yeniden başlatılıyor".format(active))
    for command in (["systemctl", "reset-failed", "tahta-kilit-verifier.service"],
                    ["systemctl", "enable", "--now", "tahta-kilit-verifier.service"],
                    ["systemctl", "restart", "tahta-kilit-verifier.service"]):
        code, output = run(command, timeout=60)
        (report.ok if code == 0 else report.warn)(" ".join(command[1:]) + ("" if code == 0 else ": " + output[-300:]))
    # Python'un açılıp soketi oluşturması birkaç saniye sürer; denetim hemen yapılırsa yanlış "yok" görünür.
    for _ in range(20):
        if os.path.exists(SOCKET_PATH):
            break
        time.sleep(0.5)


def diagnose(report, allow_register=True):
    report.write("BB Kilit tanı raporu · " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    check_package(report)
    config, key = check_files(report)
    check_services(report)
    check_socket(report)
    check_server(report, config, key, allow_register)


def summary_lines(report):
    if not report.problems:
        return ["Sorun bulunmadı."]
    return ["{}. {}".format(index, problem) for index, problem in enumerate(report.problems, 1)]


def save_screen_report(report):
    """Kilit ekranının (normal kullanıcı) okuyacağı rapor: önce özet, sonra ayrıntı."""
    os.makedirs(SCREEN_DIR, mode=0o755, exist_ok=True)
    os.chmod(SCREEN_DIR, 0o755)
    text = "\n".join(["ÖZET"] + summary_lines(report) + ["", "AYRINTI"] + report.lines) + "\n"
    temporary = SCREEN_REPORT_PATH + ".tmp"
    with open(temporary, "w", encoding="utf-8") as output:
        output.write(text)
    os.chmod(temporary, 0o644)
    os.replace(temporary, SCREEN_REPORT_PATH)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="bb-kilit-tani", description="BB Kilit kurulumunu denetler.")
    parser.add_argument("--onar", action="store_true", help="güvenli onarımları uygula ve yeniden denetle")
    parser.add_argument("--usb", action="store_true", help="raporu takılı USB belleğe kopyala")
    parser.add_argument("--ekran", action="store_true",
                        help="zamanlayıcı kipi: servis düşmüşse yeniden başlat, raporu kilit ekranı için yaz")
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        print("Bu araç root yetkisi ister: sudo bb-kilit-tani")
        return 2
    report = Report(quiet=args.ekran)
    if args.onar:
        repair(report)
    if args.ekran:
        auto_repair(report)
    diagnose(report, allow_register=not args.ekran)
    report.section("ÖZET")
    for line in summary_lines(report):
        report.write(line)
    if args.ekran:
        save_screen_report(report)
        print("Tanı raporu yazıldı; {} sorun".format(len(report.problems)))
        return 0
    save(report, args.usb)
    return 1 if report.problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
