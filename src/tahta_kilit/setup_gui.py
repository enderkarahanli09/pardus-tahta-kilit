"""Terminal gerektirmeyen GTK ilk kurulum ve yönetici anahtar aktarımı."""

import json
import os
import pwd
import subprocess
import threading

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
from tahta_kilit.site_url import DEFAULT_SITE_URL, resolve_site_url
from tahta_kilit.desktop_shortcut import main as install_desktop_shortcut
from tahta_kilit.desktop_shortcut import find_desktop_directory

SCHOOL_LOGO_PATH = "/usr/share/tahta-kilit/borusan-mtal-logo.png"

# Kilit ekranıyla aynı siyah-turuncu tema. GTK3 CSS geçişleri hafiftir; animasyon yalnız
# üzerine gelme/odak renklerinde ve onay kodunun açılışında (Gtk.Revealer) kullanılır.
CSS = b"""
window { background: #0b0b0d; color: #f4f4f6; }
label { color: #f4f4f6; }
.title { font-size: 22px; font-weight: 800; }
.brand { color: #ff8a26; font-size: 13px; font-weight: 700; }
.muted { color: #a9a9b4; font-size: 12px; }
.chip { background: #1d1d22; border: 1px solid #34343b; border-radius: 999px; padding: 4px 12px;
        color: #d6d6de; font-size: 12px; }
.card { background: #16161a; border: 1px solid #2c2c33; border-radius: 16px; padding: 18px; }
.step { color: #ff8a26; font-size: 12px; font-weight: 800; letter-spacing: 1px; }
.card-title { font-size: 15px; font-weight: 700; }
.field { color: #c9c9d2; font-size: 12px; font-weight: 600; }
entry { background: #0f0f12; color: #ffffff; border: 1px solid #3a3a42; border-radius: 10px;
        padding: 9px 11px; transition: border-color 160ms ease, box-shadow 160ms ease; }
entry:focus { border-color: #ff8a26; box-shadow: 0 0 0 2px rgba(255, 138, 38, 0.25); }
button { background: #232328; background-image: none; color: #ffffff; border: 1px solid #3a3a42;
         border-radius: 10px; padding: 10px 14px; font-weight: 600;
         transition: background 160ms ease, border-color 160ms ease; }
button:hover { background: #2e2e35; border-color: #ff8a26; }
button:disabled { color: #8a8a93; background: #1b1b1f; border-color: #2a2a30; }
button.primary { background: #ef7420; border-color: #ff8a26; color: #1b0f06; font-weight: 800; }
button.primary label { color: #1b0f06; }
button.primary:hover { background: #ff8a26; }
button.primary:disabled { background: #4a2c17; color: #b3927a; border-color: #5a3a22; }
.status { border-radius: 12px; padding: 12px 14px; background: #1b1b20; border: 1px solid #33333a; }
.status.ok { background: #13241a; border-color: #2f7a4c; }
.status.error { background: #2a1517; border-color: #8a3a3f; }
.status.wait { background: #2a1e12; border-color: #8a5a2a; }
.code { font-family: monospace; font-size: 30px; font-weight: 800; color: #ff9d4b; letter-spacing: 4px;
        background: #0f0f12; border: 1px dashed #8a5a2a; border-radius: 12px; padding: 10px 16px; }
expander title { color: #c9c9d2; font-weight: 600; }
checkbutton label { color: #c9c9d2; }
"""


class SetupWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="BB Kilit Kurulum")
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        install_desktop_shortcut()
        self.set_default_size(720, 820)
        self.connect("destroy", Gtk.main_quit)
        self.connect("delete-event", self.on_close)
        self.busy = False
        self.secret_json = None
        self.copied_text = None
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)

        # Küçük ekranlarda da tüm düğmelere ulaşılsın.
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.add(scroller)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_border_width(24)
        scroller.add(box)

        box.pack_start(self.build_header(), False, False, 0)
        self.status_box = Gtk.Box()
        self.status_box.get_style_context().add_class("status")
        self.status = Gtk.Label(label="Tahta bilgilerini kontrol edip kurulumu başlatın. Kurulum tahtayı onay için otomatik gönderir.")
        self.status.set_xalign(0)
        self.status.set_line_wrap(True)
        self.status_box.pack_start(self.status, True, True, 0)
        box.pack_start(self.status_box, False, False, 0)

        # 1 · Tahta bilgileri
        card = self.add_card(box, "1 · KURULUM", "Tahta bilgileri")
        self.board = self.add_entry(card, "Tahta kimliği (örnek: ETAP-01)", "ETAP-01")
        self.site = self.add_entry(card, "BB Kilit servis adresi (Apps Script)", DEFAULT_SITE_URL)
        try:
            with open("/etc/tahta-kilit/config.json", encoding="utf-8") as config_file:
                config = json.load(config_file)
            self.board.set_text(config["board_id"])
            self.site.set_text(resolve_site_url(config["site_url"]))
        except (OSError, ValueError, KeyError, TypeError):
            pass
        self.install = Gtk.Button(label="Kurulumu başlat / güncelle")
        self.install.get_style_context().add_class("primary")
        self.install.connect("clicked", self.on_install)
        card.pack_start(self.install, False, False, 0)
        self.add_text(card, "Yönetici doğrulaması sistem penceresinde yapılır. Mevcut tahta anahtarı değiştirilmez.", "muted")

        # 2 · Sisteme kayıt
        card = self.add_card(box, "2 · KAYIT", "Tahtayı sisteme kaydet")
        self.add_text(card, "Parola gerekmez. Tahta onaya gönderilir; SUPER yönetici BB Kilit yönetim panelinde "
                            "aşağıdaki onay kodunu görüp onaylar.", "muted")
        self.code_revealer = Gtk.Revealer()
        self.code_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.code_revealer.set_transition_duration(250)
        self.code_label = Gtk.Label(label="")
        self.code_label.get_style_context().add_class("code")
        self.code_revealer.add(self.code_label)
        card.pack_start(self.code_revealer, False, False, 0)
        self.register_button = Gtk.Button(label="Tahtayı sisteme kaydet (onaya gönder)")
        self.register_button.get_style_context().add_class("primary")
        self.register_button.connect("clicked", self.on_register)
        card.pack_start(self.register_button, False, False, 0)

        # 3 · Kısayol koruması
        card = self.add_card(box, "3 · KISAYOL", "BB Kilit kısayolunu koru")
        row = Gtk.Box(spacing=10, homogeneous=True)
        self.protect_button = Gtk.Button(label="Silinmeye karşı koru")
        self.protect_button.connect("clicked", self.on_shortcut_protection, True)
        self.unprotect_button = Gtk.Button(label="Korumayı kaldır (yönetici)")
        self.unprotect_button.connect("clicked", self.on_shortcut_protection, False)
        row.pack_start(self.protect_button, True, True, 0)
        row.pack_start(self.unprotect_button, True, True, 0)
        card.pack_start(row, False, False, 0)

        # Gelişmiş: internetsiz elle kayıt
        expander = Gtk.Expander(label="Gelişmiş: internet yoksa elle kayıt")
        advanced = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        advanced.set_border_width(8)
        expander.add(advanced)
        box.pack_start(expander, False, False, 0)
        self.key = self.add_entry(advanced, "Tahta kaydı (gizli)", "")
        self.key.set_editable(False)
        self.key.set_visibility(False)
        self.reveal = Gtk.CheckButton(label="Gizli kaydı göster")
        self.reveal.connect("toggled", lambda widget: self.key.set_visibility(widget.get_active()))
        advanced.pack_start(self.reveal, False, False, 0)
        self.copy = Gtk.Button(label="Tahta kaydını kopyala")
        self.copy.set_sensitive(False)
        self.copy.connect("clicked", self.on_copy)
        advanced.pack_start(self.copy, False, False, 0)
        self.add_text(advanced, "Google tablosunda BB Kilit → Tahta kaydet menüsüne bu kaydı yapıştırın. "
                                "Anahtarı sohbet veya GitHub'da paylaşmayın.", "muted")

    def build_header(self):
        header = Gtk.Box(spacing=14)
        if os.path.isfile(SCHOOL_LOGO_PATH):
            try:
                logo = GdkPixbuf.Pixbuf.new_from_file_at_scale(SCHOOL_LOGO_PATH, 56, 56, True)
                header.pack_start(Gtk.Image.new_from_pixbuf(logo), False, False, 0)
            except GLib.Error:
                pass
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label="BB Kilit Kurulum")
        title.set_xalign(0)
        title.get_style_context().add_class("title")
        brand = Gtk.Label(label="Borusan Bilişim Kilit")
        brand.set_xalign(0)
        brand.get_style_context().add_class("brand")
        titles.pack_start(title, False, False, 0)
        titles.pack_start(brand, False, False, 0)
        header.pack_start(titles, True, True, 0)
        user = Gtk.Label(label="Oturum: " + pwd.getpwuid(os.getuid()).pw_name)
        user.get_style_context().add_class("chip")
        user.set_valign(Gtk.Align.CENTER)
        header.pack_end(user, False, False, 0)
        return header

    def add_card(self, box, step, title):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.get_style_context().add_class("card")
        self.add_text(card, step, "step")
        self.add_text(card, title, "card-title")
        box.pack_start(card, False, False, 0)
        return card

    @staticmethod
    def add_text(box, text, style=None):
        label = Gtk.Label(label=text)
        label.set_xalign(0)
        label.set_line_wrap(True)
        if style:
            label.get_style_context().add_class(style)
        box.pack_start(label, False, False, 0)
        return label

    def add_entry(self, box, label, value):
        self.add_text(box, label, "field")
        entry = Gtk.Entry()
        entry.set_text(value)
        entry.set_max_length(2048)
        box.pack_start(entry, False, False, 0)
        return entry

    def set_status(self, text, kind=None):
        """Durum kutusu: kind None (bilgi), 'ok', 'error' veya 'wait'."""
        self.status.set_text(text)
        context = self.status_box.get_style_context()
        for name in ("ok", "error", "wait"):
            context.remove_class(name)
        if kind:
            context.add_class(kind)

    def show_code(self, fingerprint):
        self.code_label.set_text(fingerprint or "")
        self.code_revealer.set_reveal_child(bool(fingerprint))

    def on_install(self, _button):
        if self.copied_text:
            self.clear_clipboard(self.copied_text)
        self.busy = True
        self.install.set_sensitive(False)
        self.register_button.set_sensitive(False)
        self.board.set_sensitive(False)
        self.site.set_sensitive(False)
        self.copy.set_sensitive(False)
        self.key.set_text("")
        self.secret_json = None
        self.set_status("Yönetici onayı bekleniyor… Sistem parola penceresini kontrol edin.", "wait")
        arguments = [self.board.get_text(), self.site.get_text()]
        directory = find_desktop_directory()
        if directory is not None:
            arguments.append(str(directory))
        threading.Thread(target=self.run_helper, args=(arguments,), daemon=True).start()

    def on_shortcut_protection(self, _button, protect):
        if self.busy:
            return
        install_desktop_shortcut()
        directory = find_desktop_directory()
        if directory is None:
            self.set_status("Masaüstü klasörü bulunamadı. Yönetici XDG masaüstü ayarını kontrol etsin.", "error")
            return
        self.busy = True
        self.install.set_sensitive(False)
        self.register_button.set_sensitive(False)
        self.protect_button.set_sensitive(False)
        self.unprotect_button.set_sensitive(False)
        self.set_status("Kısayol için yönetici onayı bekleniyor…", "wait")
        action = "--protect-shortcut" if protect else "--unprotect-shortcut"
        threading.Thread(target=self.run_helper, args=([action, str(directory)],), daemon=True).start()

    def on_register(self, _widget):
        if self.busy:
            return
        self.busy = True
        self.install.set_sensitive(False)
        self.register_button.set_sensitive(False)
        self.protect_button.set_sensitive(False)
        self.unprotect_button.set_sensitive(False)
        self.set_status("Yönetici onayı bekleniyor… Ardından kayıt isteği gönderilecek.", "wait")
        threading.Thread(target=self.run_helper, args=(["--register-board"],), daemon=True).start()

    def run_helper(self, arguments):
        try:
            result = subprocess.run(
                ["/usr/bin/pkexec", "/usr/lib/tahta-kilit/setup-helper"] + arguments,
                input="",
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                if result.returncode in (126, 127):
                    error = "Yönetici onayı verilmedi. Kurulumu yetkili yönetici tamamlamalıdır."
                else:
                    error = result.stderr.strip()[:1000] or "Kurulum tamamlanamadı."
                GLib.idle_add(self.complete, None, error)
            else:
                GLib.idle_add(self.complete, json.loads(result.stdout), None)
        except (OSError, ValueError, subprocess.SubprocessError):
            GLib.idle_add(self.complete, None, "Kurulum aracı çalıştırılamadı veya zaman aşımına uğradı. Yöneticiyle kontrol edin.")

    def complete(self, result, error):
        self.busy = False
        self.install.set_sensitive(True)
        self.protect_button.set_sensitive(True)
        self.unprotect_button.set_sensitive(True)
        self.register_button.set_sensitive(True)
        self.board.set_sensitive(True)
        self.site.set_sensitive(True)
        if error:
            self.set_status(error, "error")
            return False
        if "registered" in result:
            self.show_registration(result)
            return False
        if "boardId" not in result:
            self.set_status("BB Kilit kısayolu silinmeye karşı korundu." if result["shortcutProtected"] else "Kısayol koruması yönetici onayıyla kaldırıldı. Şimdi dosya yöneticisinden silebilirsiniz.", "ok")
            return False
        self.board.set_text(result["boardId"])
        self.site.set_text(result["siteUrl"])
        self.secret_json = json.dumps(result["boardKeysEntry"], separators=(",", ":"))
        self.key.set_text(self.secret_json)
        self.copy.set_sensitive(True)
        prefix = "Mevcut anahtar korundu. " if result["existing"] else "Tahta anahtarı oluşturuldu. "
        if result.get("boardIdChanged"):
            prefix += "Tahta kimliği " + result["previousBoardId"] + " → " + result["boardId"] + " olarak değiştirildi. "
        protection = " BB Kilit kısayolu korundu." if result.get("shortcutProtected") else " Kısayol korunamadı; dosya sistemi/yönetici ayarlarını kontrol edin."
        if "registration" in result:
            registration = " " + self.registration_message(result["registration"])
            self.show_code(None if result["registration"].get("registered") else result["registration"].get("fingerprint"))
            kind = "ok"
        else:
            registration = " Otomatik kayıt yapılamadı: " + result.get("registrationError", "bilinmeyen hata")
            kind = "wait"
        self.set_status(prefix + "Kurulum tamamlandı. İlk kurulumda oturumu kapatıp açın; site adresi değişince BB Kilit'i yeniden açın." + protection + registration, kind)
        return False

    def show_registration(self, result):
        self.set_status(self.registration_message(result), "ok")
        self.show_code(None if result.get("registered") else result.get("fingerprint"))

    @staticmethod
    def registration_message(result):
        if result.get("registered"):
            return "Tahta " + result["boardId"] + " sisteme kayıtlı. Master parola ve QR adresi yaklaşık bir dakika içinde alınır."
        return ("Tahta " + result["boardId"] + " onaya gönderildi. Onay kodu: " + result["fingerprint"]
                + ". BB Kilit yönetim panelinde aynı kodu görüp onaylayın; onaydan sonra QR kod üretir.")

    def on_copy(self, _button):
        if self.secret_json:
            self.copied_text = self.secret_json
            self.clipboard.set_text(self.secret_json, -1)
            GLib.timeout_add_seconds(60, self.clear_clipboard, self.secret_json)
            self.set_status("Gizli kayıt kopyalandı. Google tablosundaki kayıt ekranına yapıştırın; pano 60 saniye sonra temizlenir. Sonra oturumu kapatıp açın.", "ok")

    def clear_clipboard(self, copied):
        if self.clipboard.wait_for_text() == copied:
            self.clipboard.clear()
        if self.copied_text == copied:
            self.copied_text = None
        return False

    def on_close(self, _window, _event):
        if self.busy:
            self.set_status("Kurulum sürüyor. Yönetici penceresini tamamlayın veya iptal edin.", "wait")
            return True
        if self.copied_text:
            self.clear_clipboard(self.copied_text)
        return False


def main():
    window = SetupWindow()
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
