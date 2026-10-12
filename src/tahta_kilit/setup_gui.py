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


class SetupWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Tahta Kilidi Kurulum")
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
        self.add_text(box, "Tahta Kilidi ilk kurulumu", bold=True)
        self.add_text(box, "Yönetici doğrulaması sistem penceresinde yapılır. Mevcut tahta anahtarı değiştirilmez.")
        self.add_text(box, "Otomatik başlangıç hesabı: " + pwd.getpwuid(os.getuid()).pw_name)
        self.board = self.add_entry(box, "Tahta kimliği (örnek: ETAP-01)", "ETAP-01")
        self.site = self.add_entry(box, "Öğretmen web adresi", "https://pardus-tahta-kilit-web.vercel.app/ac")
        try:
            with open("/etc/tahta-kilit/config.json", encoding="utf-8") as config_file:
                config = json.load(config_file)
            self.board.set_text(config["board_id"])
            self.site.set_text(config["site_url"])
        except (OSError, ValueError, KeyError, TypeError):
            pass
        self.install = Gtk.Button(label="Kurulumu tamamla / mevcut anahtarı al")
        self.install.connect("clicked", self.on_install)
        box.pack_start(self.install, False, False, 0)
        self.status = self.add_text(box, "Kurulum tamamlandıktan sonra anahtarı Vercel'e ekleyip oturumu kapatıp açın.")
        self.key = self.add_entry(box, "Vercel BOARD_KEYS_JSON için kayıt (gizli)", "")
        self.key.set_editable(False)
        self.key.set_visibility(False)
        self.reveal = Gtk.CheckButton(label="Gizli kaydı göster")
        self.reveal.connect("toggled", lambda widget: self.key.set_visibility(widget.get_active()))
        box.pack_start(self.reveal, False, False, 0)
        self.copy = Gtk.Button(label="Vercel kaydını kopyala")
        self.copy.set_sensitive(False)
        self.copy.connect("clicked", self.on_copy)
        box.pack_start(self.copy, False, False, 0)
        self.add_text(box, "Vercel'de mevcut kayıtları koruyarak bu tahta kaydını ekleyin ve yeniden dağıtın. Anahtarı sohbet veya GitHub'da paylaşmayın.")

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
        threading.Thread(target=self.run_helper, args=(arguments,), daemon=True).start()

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
        self.board.set_sensitive(True)
        self.site.set_sensitive(True)
        if error:
            self.status.set_text(error)
            return False
        self.board.set_text(result["boardId"])
        self.site.set_text(result["siteUrl"])
        self.secret_json = json.dumps(result["boardKeysEntry"], separators=(",", ":"))
        self.key.set_text(self.secret_json)
        self.copy.set_sensitive(True)
        prefix = "Mevcut anahtar korundu. " if result["existing"] else "Tahta anahtarı oluşturuldu. "
        self.status.set_text(prefix + "Kurulum tamamlandı. Vercel'e ekleyip yeniden dağıtın; ardından Pardus oturumunu kapatıp açın.")
        return False

    def on_copy(self, _button):
        if self.secret_json:
            self.copied_text = self.secret_json
            self.clipboard.set_text(self.secret_json, -1)
            GLib.timeout_add_seconds(60, self.clear_clipboard, self.secret_json)
            self.status.set_text("Gizli kayıt kopyalandı. Vercel'e yapıştırın; pano 60 saniye sonra temizlenir. Sonra oturumu kapatıp açın.")

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
