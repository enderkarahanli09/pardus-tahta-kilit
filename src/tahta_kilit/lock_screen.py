"""BB Kilit normal GTK penceresi; klavye ve dokunmatik kod girişi."""

import json
import os
import socket
from io import BytesIO
from urllib.parse import urlencode, urlsplit, urlunsplit

import qrcode
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

CONFIG_PATH = "/etc/tahta-kilit/config.json"
SOCKET_PATH = "/run/tahta-kilit/verifier.sock"
MAX_CODE_DIGITS = 6
SCHOOL_LOGO_PATH = "/usr/share/tahta-kilit/borusan-mtal-logo.jpg"
TEST_MODE = os.environ.get("TAHTA_KILIT_TEST_MODE") == "1"

COLORS = {
    "background": "#0b0b0d",
    "panel": "#19191c",
    "primary": "#c24c06",
    "text": "#ffffff",
    "muted": "#c8c8ce",
    "danger": "#ffb4ab",
}


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as config_file:
        config = json.load(config_file)
    site_url = config.get("site_url")
    if not isinstance(site_url, str) or not site_url.startswith("https://"):
        raise ValueError("Web adresi HTTPS olmalıdır.")
    return config


def call_verifier(payload):
    request_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        connection.connect(SOCKET_PATH)
        connection.sendall(request_bytes + b"\n")
        response_bytes = b""
        while not response_bytes.endswith(b"\n") and len(response_bytes) <= 4096:
            part = connection.recv(4096)
            if not part:
                break
            response_bytes += part
    if not response_bytes or len(response_bytes) > 4096:
        raise OSError("Doğrulama servisi yanıt vermedi.")
    response = json.loads(response_bytes.decode("utf-8"))
    if not isinstance(response, dict):
        raise ValueError("Doğrulama servisi yanıtı geçersiz.")
    return response


def build_qr_url(site_url, challenge):
    parts = urlsplit(site_url)
    query = urlencode(
        {
            "v": "2",
            "board": challenge["boardId"],
            "nonce": challenge["nonce"],
            "sig": challenge["qrSignature"],
        }
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def pixbuf_from_qr(text):
    image = qrcode.make(text).convert("RGB")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    loader = GdkPixbuf.PixbufLoader.new_with_type("png")
    loader.write(buffer.getvalue())
    loader.close()
    pixbuf = loader.get_pixbuf()
    return pixbuf.scale_simple(320, 320, GdkPixbuf.InterpType.NEAREST)


class LockScreen:
    def __init__(self):
        self.config = load_config()
        self.challenge = None
        self.code = ""
        self.unlocked = False
        self.seconds_left = 0

        self.window = Gtk.Window(title="BB Kilit")
        self.window.set_default_size(940, 900)
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.connect("delete-event", self.on_delete)
        self.window.connect("key-press-event", self.on_key_press)
        self.window.connect("destroy", lambda _window: Gtk.main_quit())
        self.apply_css()
        self.build_view()
        self.refresh_challenge()
        self.refresh_timer = GLib.timeout_add_seconds(5, self.refresh_challenge)
        self.tick_timer = GLib.timeout_add_seconds(1, self.tick)
        self.keyboard_timer = None

    def apply_css(self):
        css = """
        window, .screen { background-color: %(background)s; color: %(text)s; }
        .panel { background-color: %(panel)s; border: 1px solid #333337;
                 border-radius: 22px; padding: 24px; }
        .title { color: %(text)s; font-size: 36px; font-weight: 700; }
        .brand-name { color: #ff8a26; font-size: 17px; font-weight: 600; }
        .school-name { color: %(text)s; font-size: 15px; font-weight: 600; }
        .section-title { color: #ff8a26; font-size: 15px; font-weight: 700; }
        .subtitle { color: %(muted)s; font-size: 17px; }
        .code { color: %(text)s; background: #101012; border: 1px solid #3c3c42;
                border-radius: 12px; padding: 12px; font-size: 30px; letter-spacing: 9px; }
        .status { color: %(muted)s; font-size: 15px; }
        .error { color: %(danger)s; font-size: 15px; }
        button.key { background: #242428; background-image: none;
                     color: %(text)s; border: 1px solid #3b3b42; box-shadow: none;
                     border-radius: 14px; min-width: 72px; min-height: 54px;
                     font-size: 25px; font-weight: 600; }
        button.key:hover { background: #343438; border-color: #ff8a26; }
        button.key:active { background: #453022; }
        button.confirm { background: %(primary)s; border-color: #ef7420; }
        button.confirm:hover { background: #d55a0c; }
        button.key:disabled { background: #242426; color: #929299; border-color: #39393e; }
        button.small { font-size: 17px; }
        """ % COLORS
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def build_view(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        root.set_border_width(24)
        root.set_halign(Gtk.Align.CENTER)
        root.set_valign(Gtk.Align.CENTER)
        root.get_style_context().add_class("screen")

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        header.set_hexpand(True)
        school = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        school.set_halign(Gtk.Align.CENTER)
        if os.path.isfile(SCHOOL_LOGO_PATH):
            logo = GdkPixbuf.Pixbuf.new_from_file_at_scale(SCHOOL_LOGO_PATH, 80, 80, True)
            school.pack_start(Gtk.Image.new_from_pixbuf(logo), False, False, 0)
        else:
            school_name = Gtk.Label(label="Borusan Asım Kocabıyık\nMesleki ve Teknik Anadolu Lisesi")
            school_name.set_justify(Gtk.Justification.CENTER)
            school_name.get_style_context().add_class("school-name")
            school.pack_start(school_name, False, False, 0)
        header.pack_start(school, False, False, 0)
        brand = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        brand.set_halign(Gtk.Align.CENTER)
        title = Gtk.Label(label="BB Kilit")
        title.get_style_context().add_class("title")
        brand.pack_start(title, False, False, 0)
        expanded_name = Gtk.Label(label="Borusan Bilişim Kilit")
        expanded_name.get_style_context().add_class("brand-name")
        brand.pack_start(expanded_name, False, False, 0)
        header.pack_start(brand, False, False, 0)
        root.pack_start(header, False, False, 0)

        subtitle = Gtk.Label(
            label="QR kodu telefonunuzla okutun ve 6 haneli açma kodunu alın."
        )
        subtitle.get_style_context().add_class("subtitle")
        root.pack_start(subtitle, False, False, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        content.get_style_context().add_class("panel")
        root.pack_start(content, False, False, 0)

        qr_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        qr_column.set_halign(Gtk.Align.CENTER)
        qr_column.set_valign(Gtk.Align.CENTER)
        qr_caption = Gtk.Label(label="01  ·  QR KODU OKUT")
        qr_caption.get_style_context().add_class("section-title")
        qr_column.pack_start(qr_caption, False, False, 0)
        self.qr_image = Gtk.Image()
        self.qr_image.set_size_request(320, 320)
        qr_column.pack_start(self.qr_image, False, False, 0)
        self.board_label = Gtk.Label(label="QR hazırlanıyor…")
        self.board_label.get_style_context().add_class("status")
        qr_column.pack_start(self.board_label, False, False, 0)
        self.qr_countdown = Gtk.Label(label="")
        self.qr_countdown.get_style_context().add_class("status")
        qr_column.pack_start(self.qr_countdown, False, False, 0)
        content.pack_start(qr_column, False, False, 0)

        keypad_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        keypad_column.set_halign(Gtk.Align.CENTER)
        keypad_column.set_valign(Gtk.Align.CENTER)
        code_caption = Gtk.Label(label="02  ·  6 HANELİ KODU GİR")
        code_caption.get_style_context().add_class("section-title")
        keypad_column.pack_start(code_caption, False, False, 0)
        self.code_label = Gtk.Label(label="○○○○○○")
        self.code_label.get_style_context().add_class("code")
        keypad_column.pack_start(self.code_label, False, False, 2)

        grid = Gtk.Grid()
        grid.set_row_spacing(9)
        grid.set_column_spacing(9)
        digits = (("1", "2", "3"), ("4", "5", "6"), ("7", "8", "9"))
        for row, values in enumerate(digits):
            for column, digit in enumerate(values):
                grid.attach(
                    self.make_button(digit, lambda value=digit: self.add_digit(value)),
                    column,
                    row,
                    1,
                    1,
                )
        grid.attach(self.make_button("Sil", self.backspace, small=True), 0, 3, 1, 1)
        grid.attach(self.make_button("0", lambda: self.add_digit("0")), 1, 3, 1, 1)
        grid.attach(self.make_button("Temizle", self.clear_code, small=True), 2, 3, 1, 1)
        keypad_column.pack_start(grid, False, False, 0)

        self.confirm_button = self.make_button(
            "Giriş Yap", self.submit_code, confirm=True
        )
        self.confirm_button.set_sensitive(False)
        keypad_column.pack_start(self.confirm_button, False, False, 0)
        self.status_label = Gtk.Label(label="Telefonunuzdan aldığınız kodu girin.")
        self.status_label.set_line_wrap(True)
        self.status_label.set_max_width_chars(36)
        self.status_label.get_style_context().add_class("status")
        keypad_column.pack_start(self.status_label, False, False, 0)
        content.pack_start(keypad_column, False, False, 0)

        self.keyboard_label = Gtk.Label(label="Kodu klavyeden veya dokunmatik tuş takımından girebilirsiniz.")
        self.keyboard_label.set_line_wrap(True)
        self.keyboard_label.set_max_width_chars(36)
        self.keyboard_label.get_style_context().add_class("status")
        keypad_column.pack_start(self.keyboard_label, False, False, 0)
        # Sağ alt alan sonraki görsel/metin için boş tutulur.
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        footer.set_size_request(-1, 20)
        self.footer_extension = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.footer_extension.set_halign(Gtk.Align.END)
        footer.pack_end(self.footer_extension, False, False, 0)
        root.pack_start(footer, False, False, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(root)
        self.window.add(scroll)
        self.window.show_all()

    @staticmethod
    def make_button(label, callback, small=False, confirm=False):
        button = Gtk.Button(label=label)
        button.set_can_focus(False)
        button.get_style_context().add_class("key")
        if small:
            button.get_style_context().add_class("small")
        if confirm:
            button.get_style_context().add_class("confirm")
        button.connect("clicked", lambda _button: callback())
        return button

    def set_status(self, message, is_error=False):
        context = self.status_label.get_style_context()
        context.remove_class("error")
        context.remove_class("status")
        context.add_class("error" if is_error else "status")
        self.status_label.set_text(message)

    def refresh_challenge(self):
        if self.unlocked:
            self.refresh_timer = None
            return False
        try:
            response = call_verifier({"action": "challenge"})
            if not response.get("ok"):
                self.show_service_error(response)
                self.confirm_button.set_sensitive(False)
                self.challenge = None
                self.qr_image.clear()
                return True
            self.challenge = response
            qr_url = build_qr_url(self.config["site_url"], response)
            self.qr_image.set_from_pixbuf(pixbuf_from_qr(qr_url))
            self.board_label.set_text("Tahta: {}".format(response["boardId"]))
            self.seconds_left = response["expiresIn"]
            self.confirm_button.set_sensitive(len(self.code) == MAX_CODE_DIGITS)
            self.set_status("Telefonunuzdan aldığınız kodu girin.")
        except Exception:
            self.challenge = None
            self.confirm_button.set_sensitive(False)
            self.qr_image.clear()
            self.board_label.set_text("Yerel doğrulama servisine ulaşılamıyor.")
            self.set_status(
                "Servis başlatılmalı ve oturum kullanıcısı tahta-kilit grubunda olmalı.",
                is_error=True,
            )
        return True

    def show_service_error(self, response):
        error = response.get("error", "internal_error")
        if error == "cooldown":
            retry = response.get("retryAfter", 30)
            self.set_status(
                "Çok fazla hatalı deneme. {} saniye sonra tekrar deneyin.".format(retry),
                is_error=True,
            )
        elif error == "stale_challenge":
            self.set_status("QR kodun süresi doldu. Yeni QR kodu okutun.", is_error=True)
        else:
            self.set_status("İstek tamamlanamadı. QR kodu yenileyip tekrar deneyin.", is_error=True)

    def tick(self):
        if self.unlocked:
            self.tick_timer = None
            return False
        if self.challenge is not None:
            self.seconds_left = max(0, self.seconds_left - 1)
            self.qr_countdown.set_text(
                "QR yenilenmesine {} sn".format(self.seconds_left)
            )
            if self.seconds_left == 0:
                self.refresh_challenge()
        return True

    def add_digit(self, digit):
        if self.unlocked or len(self.code) >= MAX_CODE_DIGITS:
            return
        self.code += digit
        self.update_code_display()

    def backspace(self):
        self.code = self.code[:-1]
        self.update_code_display()

    def clear_code(self):
        self.code = ""
        self.update_code_display()

    def update_code_display(self):
        shown = "●" * len(self.code) + "○" * (MAX_CODE_DIGITS - len(self.code))
        self.code_label.set_text(shown)
        self.confirm_button.set_sensitive(
            len(self.code) == MAX_CODE_DIGITS and self.challenge is not None
        )

    def submit_code(self):
        if self.unlocked or self.challenge is None or len(self.code) != MAX_CODE_DIGITS:
            return
        try:
            response = call_verifier(
                {
                    "action": "verify",
                    "nonce": self.challenge["nonce"],
                    "unlockCode": self.code,
                }
            )
        except Exception:
            self.set_status("Yerel doğrulama servisine ulaşılamıyor.", is_error=True)
            return

        if not response.get("ok"):
            self.code = ""
            self.update_code_display()
            self.show_service_error(response)
            if response.get("error") == "stale_challenge":
                self.challenge = None
                self.refresh_challenge()
            elif response.get("error") == "cooldown":
                self.challenge = None
                self.qr_image.clear()
                self.confirm_button.set_sensitive(False)
            return

        self.unlock_session()

    def unlock_session(self):
        # GTK döngüsü canlı kalır; systemd başarılı açmayı çökme sanıp yeniden başlatmaz.
        self.unlocked = True
        self.code = ""
        self.challenge = None
        self.update_code_display()
        self.qr_image.clear()
        for name in ("refresh_timer", "tick_timer", "keyboard_timer"):
            source = getattr(self, name, None)
            if source is not None:
                GLib.source_remove(source)
                setattr(self, name, None)
        self.window.hide()

    def on_delete(self, _window, _event):
        Gtk.main_quit()
        return False

    def on_key_press(self, _window, event):
        key = Gdk.keyval_to_unicode(event.keyval)
        if key and chr(key) in "0123456789":
            self.add_digit(chr(key))
            return True
        if event.keyval == Gdk.KEY_BackSpace:
            self.backspace()
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.submit_code()
            return True
        return False

    def restore_lock_window(self):
        if not self.unlocked:
            self.window.show_all()
            self.window.present()
        return False


def main():
    Gtk.init([])
    try:
        screen = LockScreen()
        Gtk.main()
    except Exception as error:
        print("Tahta kilit ekranı başlatılamadı: {}".format(error))
        return 1
    del screen
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
