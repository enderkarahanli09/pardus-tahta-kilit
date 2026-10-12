"""Terminal gerektirmeyen GTK ilk kurulum ve yönetici anahtar aktarımı."""

import json
import os
import pwd
import subprocess
import threading

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk
from tahta_kilit.site_url import DEFAULT_SITE_URL, resolve_site_url
from tahta_kilit.desktop_shortcut import main as install_desktop_shortcut
from tahta_kilit.desktop_shortcut import find_desktop_directory


class SetupWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="BB Kilit Kurulum")
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
            window { background: #0b0b0d; color: #ffffff; }
            label { color: #ffffff; }
            entry { background: #19191c; color: #ffffff; border: 1px solid #424247;
                    border-radius: 8px; padding: 8px; }
            entry:focus { border-color: #ff8a26; }
            button { background: #242428; background-image: none; color: #ffffff;
                     border: 1px solid #424247; border-radius: 8px; padding: 10px; }
            button:hover { background: #c24c06; border-color: #ff8a26; }
            button:disabled { color: #96969c; }
        """)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        install_desktop_shortcut()
        self.set_default_size(600, 460)
        self.set_border_width(24)
        self.connect("destroy", Gtk.main_quit)
        self.connect("delete-event", self.on_close)
        self.busy = False
        self.secret_json = None
        self.copied_text = None
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(box)
        self.add_text(box, "BB Kilit — Borusan Bilişim Kilit", bold=True)
        self.add_text(box, "Yönetici doğrulaması sistem penceresinde yapılır. Mevcut tahta anahtarı değiştirilmez.")
        self.add_text(box, "Oturum hesabı: " + pwd.getpwuid(os.getuid()).pw_name)
        self.board = self.add_entry(box, "Tahta kimliği (örnek: ETAP-01)", "ETAP-01")
        self.site = self.add_entry(box, "QR sitesinin HTTPS / Apps Script adresi", DEFAULT_SITE_URL)
        try:
            with open("/etc/tahta-kilit/config.json", encoding="utf-8") as config_file:
                config = json.load(config_file)
            self.board.set_text(config["board_id"])
            self.site.set_text(resolve_site_url(config["site_url"]))
        except (OSError, ValueError, KeyError, TypeError):
            pass
        self.install = Gtk.Button(label="Kurulumu tamamla / site adresini güncelle")
        self.install.connect("clicked", self.on_install)
        box.pack_start(self.install, False, False, 0)
        self.protect_button = Gtk.Button(label="BB Kilit kısayolunu silinmeye karşı koru")
        self.protect_button.connect("clicked", self.on_shortcut_protection, True)
        box.pack_start(self.protect_button, False, False, 0)
        self.unprotect_button = Gtk.Button(label="BB Kilit kısayolunun korumasını kaldır (yönetici)")
        self.unprotect_button.connect("clicked", self.on_shortcut_protection, False)
        box.pack_start(self.unprotect_button, False, False, 0)
        self.status = self.add_text(box, "Kurulum tamamlandıktan sonra tahta kaydını kod servisine ekleyip oturumu kapatıp açın.")
        self.key = self.add_entry(box, "Google Apps Script / kod servisi için tahta kaydı (gizli)", "")
        self.key.set_editable(False)
        self.key.set_visibility(False)
        self.reveal = Gtk.CheckButton(label="Gizli kaydı göster")
        self.reveal.connect("toggled", lambda widget: self.key.set_visibility(widget.get_active()))
        box.pack_start(self.reveal, False, False, 0)
        self.copy = Gtk.Button(label="Tahta kaydını kopyala")
        self.copy.set_sensitive(False)
        self.copy.connect("clicked", self.on_copy)
        box.pack_start(self.copy, False, False, 0)
        self.add_text(box, "Google tablosunda BB Kilit → Tahta kaydet menüsüne bu kaydı yapıştırın. Vercel kullanıyorsanız mevcut JSON'a ekleyin. Anahtarı sohbet veya GitHub'da paylaşmayın.")

    @staticmethod
    def add_text(box, text, bold=False):
        label = Gtk.Label(label=text)
        label.set_xalign(0)
        label.set_line_wrap(True)
        if bold:
            label.set_markup("<b>" + GLib.markup_escape_text(text) + "</b>")
        box.pack_start(label, False, False, 0)
        return label

    def add_entry(self, box, label, value):
        self.add_text(box, label)
        entry = Gtk.Entry()
        entry.set_text(value)
        entry.set_max_length(2048)
        box.pack_start(entry, False, False, 0)
        return entry

    def on_install(self, _button):
        if self.copied_text:
            self.clear_clipboard(self.copied_text)
        self.busy = True
        self.install.set_sensitive(False)
        self.board.set_sensitive(False)
        self.site.set_sensitive(False)
        self.copy.set_sensitive(False)
        self.key.set_text("")
        self.secret_json = None
        self.status.set_text("Yönetici onayı bekleniyor… Sistem parola penceresini kontrol edin.")
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
            self.status.set_text("Masaüstü klasörü bulunamadı. Yönetici XDG masaüstü ayarını kontrol etsin.")
            return
        self.busy = True
        self.install.set_sensitive(False)
        self.protect_button.set_sensitive(False)
        self.unprotect_button.set_sensitive(False)
        self.status.set_text("Kısayol için yönetici onayı bekleniyor…")
        action = "--protect-shortcut" if protect else "--unprotect-shortcut"
        threading.Thread(target=self.run_helper, args=([action, str(directory)],), daemon=True).start()

    def run_helper(self, arguments):
        try:
            result = subprocess.run(
                ["/usr/bin/pkexec", "/usr/lib/tahta-kilit/setup-helper"] + arguments,
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
        self.board.set_sensitive(True)
        self.site.set_sensitive(True)
        if error:
            self.status.set_text(error)
            return False
        if "boardId" not in result:
            self.status.set_text("BB Kilit kısayolu silinmeye karşı korundu." if result["shortcutProtected"] else "Kısayol koruması yönetici onayıyla kaldırıldı. Şimdi dosya yöneticisinden silebilirsiniz.")
            return False
        self.board.set_text(result["boardId"])
        self.site.set_text(result["siteUrl"])
        self.secret_json = json.dumps(result["boardKeysEntry"], separators=(",", ":"))
        self.key.set_text(self.secret_json)
        self.copy.set_sensitive(True)
        prefix = "Mevcut anahtar korundu. " if result["existing"] else "Tahta anahtarı oluşturuldu. "
        protection = " BB Kilit kısayolu korundu." if result.get("shortcutProtected") else " Kısayol korunamadı; dosya sistemi/yönetici ayarlarını kontrol edin."
        self.status.set_text(prefix + "Kurulum tamamlandı. Tahta kaydını kod servisine ekleyin. İlk kurulumda oturumu kapatıp açın; site adresi değişince BB Kilit'i yeniden açın." + protection)
        return False

    def on_copy(self, _button):
        if self.secret_json:
            self.copied_text = self.secret_json
            self.clipboard.set_text(self.secret_json, -1)
            GLib.timeout_add_seconds(60, self.clear_clipboard, self.secret_json)
            self.status.set_text("Gizli kayıt kopyalandı. Google tablosundaki kayıt ekranına yapıştırın; pano 60 saniye sonra temizlenir. Sonra oturumu kapatıp açın.")

    def clear_clipboard(self, copied):
        if self.clipboard.wait_for_text() == copied:
            self.clipboard.clear()
        if self.copied_text == copied:
            self.copied_text = None
        return False

    def on_close(self, _window, _event):
        if self.busy:
            self.status.set_text("Kurulum sürüyor. Yönetici penceresini tamamlayın veya iptal edin.")
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
