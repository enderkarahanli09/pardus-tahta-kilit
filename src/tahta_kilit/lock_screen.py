"""BB Kilit tam ekran oturum arayüzü; kilitliyken dokunmatik kod girişi."""

import datetime
import grp
import json
import os
import socket
import subprocess
from io import BytesIO
from tahta_kilit.qr_portal import DEFAULT_QR_PORTAL_URL, build_portal_qr_url
from tahta_kilit.portal_sync import resolve_qr_portal_url
from tahta_kilit.keyboard_guard import KeyboardGuard

import qrcode
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango

CONFIG_PATH = "/etc/tahta-kilit/config.json"
SOCKET_PATH = "/run/tahta-kilit/verifier.sock"
MAX_CODE_DIGITS = 6
SCHOOL_LOGO_PATH = "/usr/share/tahta-kilit/borusan-mtal-logo.png"
TEST_MODE = os.environ.get("TAHTA_KILIT_TEST_MODE") == "1"
# Bu yükseklikten kısa ekranlarda (ör. 1366×768) sıkışık düzen kullanılır.
COMPACT_MAX_HEIGHT = 900
QR_SIZE = 320
COMPACT_QR_SIZE = 240
# Root tanı zamanlayıcısının (tahta-kilit-tani.timer) kilit ekranı için yazdığı rapor.
DIAGNOSIS_REPORT_PATH = "/run/bb-kilit-tani/rapor.txt"
UNIT_PROPERTIES = "LoadState,ActiveState,SubState,Result,ExecMainStatus,NRestarts,UnitFileState"

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
        connection.settimeout(15 if payload.get("action") == "verify-master" else 2)
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


def verifier_error_message(error):
    # Kurulumda kullanıcı tahta-kilit grubuna eklenir ama grup ancak yeni oturumda geçerli olur;
    # bu yüzden soket izin hatası "servis çalışmıyor"dan ayrı anlatılır.
    if isinstance(error, PermissionError):
        return "Bu oturum doğrulama servisine erişemiyor. Tahtayı yeniden başlatın (ilk kurulumdan sonra gerekir)."
    if isinstance(error, (FileNotFoundError, ConnectionRefusedError)):
        return "Doğrulama servisi çalışmıyor. Yönetici: systemctl status tahta-kilit-verifier.service"
    return "Yerel doğrulama servisi yanıt vermedi. Tahtayı yeniden başlatıp tekrar deneyin."


def unit_state(unit):
    # systemctl show yetkisiz kullanıcıyla da çalışır (D-Bus üzerinden salt okunur).
    try:
        result = subprocess.run(["systemctl", "show", unit, "-p", UNIT_PROPERTIES],
                                capture_output=True, text=True, timeout=5)
        return " ".join(result.stdout.split()) or result.stderr.strip() or "?"
    except (OSError, subprocess.SubprocessError) as error:
        return "okunamadı ({})".format(type(error).__name__)


def collect_diagnosis():
    """Kilit ekranının gösterdiği tanı metni: bu oturumdan canlı durum + root tanı raporu."""
    lines = ["CANLI DURUM (bu oturum)"]
    try:
        group_id = grp.getgrnam("tahta-kilit").gr_gid
        in_group = group_id in os.getgroups() or os.getgid() == group_id
        lines.append("tahta-kilit grubu: " + ("var" if in_group else "YOK → tahtayı yeniden başlatın"))
    except KeyError:
        lines.append("tahta-kilit grubu: sistemde yok → paketi yeniden kurun")
    try:
        os.stat(SOCKET_PATH)
        lines.append("Doğrulama soketi: var")
    except FileNotFoundError:
        lines.append("Doğrulama soketi: YOK → doğrulama servisi çalışmıyor")
    except PermissionError:
        lines.append("Doğrulama soketi: erişim izni yok → grup bu oturumda geçerli değil")
    lines.append("Doğrulama servisi: " + unit_state("tahta-kilit-verifier.service"))
    lines.append("Master eşitleme: " + unit_state("tahta-kilit-master-sync.service"))
    lines.append("Tanı zamanlayıcısı: " + unit_state("tahta-kilit-tani.timer"))
    lines.append("")
    try:
        with open(DIAGNOSIS_REPORT_PATH, encoding="utf-8") as stream:
            report = stream.read(200000)
        written = datetime.datetime.fromtimestamp(os.path.getmtime(DIAGNOSIS_REPORT_PATH))
        lines.append("OTOMATİK TANI RAPORU · " + written.strftime("%H:%M:%S"))
        lines.append(report)
    except FileNotFoundError:
        lines.append("Otomatik tanı raporu henüz yok. Açılıştan yaklaşık 30 saniye sonra hazır olur; "
                     "'Yenile'ye basın. Uzun süre gelmezse tanı zamanlayıcısı çalışmıyordur.")
    except OSError as error:
        lines.append("Otomatik tanı raporu okunamadı ({}).".format(type(error).__name__))
    return "\n".join(lines)


def build_qr_url(site_url, challenge, portal_url=DEFAULT_QR_PORTAL_URL):
    # site_url tahta servisi/master senkronizasyonu için korunur.
    return build_portal_qr_url(challenge, portal_url)


def pixbuf_from_qr(text, size=QR_SIZE):
    image = qrcode.make(text).convert("RGB")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    loader = GdkPixbuf.PixbufLoader.new_with_type("png")
    loader.write(buffer.getvalue())
    loader.close()
    pixbuf = loader.get_pixbuf()
    return pixbuf.scale_simple(size, size, GdkPixbuf.InterpType.NEAREST)


def screen_is_compact():
    # TAHTA_KILIT_COMPACT=1/0 ekran yüksekliğinden bağımsız zorlar (PC'de deneme için).
    forced = os.environ.get("TAHTA_KILIT_COMPACT")
    if forced in ("0", "1"):
        return forced == "1"
    display = Gdk.Display.get_default()
    if display is None:
        return False
    monitor = display.get_primary_monitor() or display.get_monitor(0)
    if monitor is None:
        return False
    return monitor.get_geometry().height < COMPACT_MAX_HEIGHT


class LockScreen:
    def __init__(self):
        self.config = load_config()
        self.challenge = None
        self.code = ""
        self.master_mode = False
        self.code_length = MAX_CODE_DIGITS
        self.unlocked = False
        self.seconds_left = 0
        self.compact = screen_is_compact()
        self.qr_size = COMPACT_QR_SIZE if self.compact else QR_SIZE

        self.window = Gtk.Window(title="BB Kilit")
        self.window.set_default_size(940, 740 if self.compact else 900)
        if self.compact:
            self.window.get_style_context().add_class("compact")
        self.window.set_position(Gtk.WindowPosition.CENTER)
        if not TEST_MODE:
            self.window.set_decorated(False)
            self.window.set_keep_above(True)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_skip_pager_hint(True)
        self.make_fullscreen()
        self.keyboard_guard = KeyboardGuard(self.window)
        self.window.connect("map-event", lambda *_: GLib.idle_add(self.guard_once))
        self.window.connect("grab-broken-event", self.on_grab_broken)
        self.window.connect("delete-event", self.on_delete)
        self.window.connect("key-press-event", self.on_key_press)
        self.window.connect("destroy", lambda _window: Gtk.main_quit())
        self.apply_css()
        self.build_view()
        self.refresh_challenge()
        self.refresh_timer = GLib.timeout_add_seconds(5, self.refresh_challenge)
        self.tick_timer = GLib.timeout_add_seconds(1, self.tick)
        self.keyboard_timer = GLib.timeout_add_seconds(1, self.ensure_keyboard_guard)

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
        .report { color: %(text)s; font-family: monospace; font-size: 13px; }
        .compact .panel { border-radius: 18px; padding: 14px 18px; }
        .compact .title { font-size: 28px; }
        .compact .brand-name { font-size: 15px; }
        .compact .subtitle { font-size: 15px; }
        .compact .section-title, .compact .status, .compact .error { font-size: 14px; }
        .compact .code { padding: 6px 10px; font-size: 24px; letter-spacing: 7px; }
        .compact button.key { min-width: 68px; min-height: 44px; font-size: 22px; }
        .compact button.small { font-size: 15px; }
        """ % COLORS
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def build_view(self):
        compact = self.compact
        gap = 8 if compact else 16
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=gap)
        root.set_border_width(12 if compact else 24)
        root.set_halign(Gtk.Align.CENTER)
        root.set_valign(Gtk.Align.CENTER)
        root.get_style_context().add_class("screen")

        # Sıkışık düzende logo ile başlık yan yana durur; dikey alandan ~100 piksel kazanılır.
        header = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL if compact else Gtk.Orientation.VERTICAL,
            spacing=16 if compact else 8,
        )
        header.set_hexpand(True)
        if compact:
            header.set_halign(Gtk.Align.CENTER)
        school = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        school.set_halign(Gtk.Align.CENTER)
        school.set_valign(Gtk.Align.CENTER)
        if os.path.isfile(SCHOOL_LOGO_PATH):
            logo_size = 56 if compact else 80
            logo = GdkPixbuf.Pixbuf.new_from_file_at_scale(SCHOOL_LOGO_PATH, logo_size, logo_size, True)
            school.pack_start(Gtk.Image.new_from_pixbuf(logo), False, False, 0)
        else:
            school_name = Gtk.Label(label="Borusan Asım Kocabıyık\nMesleki ve Teknik Anadolu Lisesi")
            school_name.set_justify(Gtk.Justification.CENTER)
            school_name.get_style_context().add_class("school-name")
            school.pack_start(school_name, False, False, 0)
        header.pack_start(school, False, False, 0)
        brand = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2 if compact else 6)
        brand.set_halign(Gtk.Align.CENTER)
        brand.set_valign(Gtk.Align.CENTER)
        title = Gtk.Label(label="BB Kilit")
        title.get_style_context().add_class("title")
        brand.pack_start(title, False, False, 0)
        expanded_name = Gtk.Label(label="Borusan Bilişim Kilit")
        expanded_name.get_style_context().add_class("brand-name")
        brand.pack_start(expanded_name, False, False, 0)
        header.pack_start(brand, False, False, 0)
        root.pack_start(header, False, False, 0)

        subtitle = Gtk.Label(
            label="QR okutun veya aşağıdaki istek kodunu siteye girin."
        )
        subtitle.get_style_context().add_class("subtitle")
        root.pack_start(subtitle, False, False, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        content.get_style_context().add_class("panel")
        # Kilit paneli ile tanı paneli aynı yerde yer değiştirir; tanı paneli kilit panelinin boyutunu alır.
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(content, "kilit")
        self.stack.add_named(self.build_diagnosis_panel(), "tani")
        root.pack_start(self.stack, False, False, 0)

        qr_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6 if compact else 10)
        qr_column.set_halign(Gtk.Align.CENTER)
        qr_column.set_valign(Gtk.Align.CENTER)
        qr_caption = Gtk.Label(label="01  ·  QR KODU OKUT")
        qr_caption.get_style_context().add_class("section-title")
        qr_column.pack_start(qr_caption, False, False, 0)
        self.qr_image = Gtk.Image()
        self.qr_image.set_size_request(self.qr_size, self.qr_size)
        qr_column.pack_start(self.qr_image, False, False, 0)
        self.board_label = Gtk.Label(label="QR hazırlanıyor…")
        self.board_label.get_style_context().add_class("status")
        qr_column.pack_start(self.board_label, False, False, 0)
        manual_caption = Gtk.Label(label="QR OKUTAMIYORSANIZ · SİTEYE BU KODU YAZIN")
        manual_caption.get_style_context().add_class("status")
        qr_column.pack_start(manual_caption, False, False, 0)
        self.manual_label = Gtk.Label(label="— — — — — —")
        self.manual_label.get_style_context().add_class("code")
        qr_column.pack_start(self.manual_label, False, False, 0)
        self.qr_countdown = Gtk.Label(label="")
        self.qr_countdown.get_style_context().add_class("status")
        qr_column.pack_start(self.qr_countdown, False, False, 0)
        # Klavyesiz tahtada sorunun nedenini görmenin yolu: dokunmatik tanı düğmesi.
        qr_column.pack_start(self.make_button("Hata ayrıntısı / Tanı", self.show_diagnosis, small=True),
                             False, False, 0)
        content.pack_start(qr_column, False, False, 0)

        keypad_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7 if compact else 12)
        keypad_column.set_halign(Gtk.Align.CENTER)
        keypad_column.set_valign(Gtk.Align.CENTER)
        self.code_caption = code_caption = Gtk.Label(label="02  ·  6 HANELİ KODU GİR")
        code_caption.get_style_context().add_class("section-title")
        keypad_column.pack_start(code_caption, False, False, 0)
        self.code_label = Gtk.Label(label="○○○○○○")
        self.code_label.get_style_context().add_class("code")
        keypad_column.pack_start(self.code_label, False, False, 2)

        grid = Gtk.Grid()
        grid.set_row_spacing(6 if compact else 9)
        grid.set_column_spacing(6 if compact else 9)
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
        self.master_button = self.make_button("Yönetici master parolası", self.toggle_master, small=True)
        keypad_column.pack_start(self.master_button, False, False, 0)
        self.status_label = Gtk.Label(label="Telefonunuzdan aldığınız kodu girin.")
        self.status_label.set_line_wrap(True)
        self.status_label.set_max_width_chars(36)
        self.status_label.get_style_context().add_class("status")
        keypad_column.pack_start(self.status_label, False, False, 0)
        content.pack_start(keypad_column, False, False, 0)

        self.keyboard_label = Gtk.Label(label="Kodu ekrandaki dokunmatik tuş takımından girin.")
        self.keyboard_label.set_line_wrap(True)
        self.keyboard_label.set_max_width_chars(36)
        self.keyboard_label.get_style_context().add_class("status")
        keypad_column.pack_start(self.keyboard_label, False, False, 0)
        # Sağ alt alan sonraki görsel/metin için boş tutulur.
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        footer.set_size_request(-1, 8 if compact else 20)
        self.footer_extension = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.footer_extension.set_halign(Gtk.Align.END)
        footer.pack_end(self.footer_extension, False, False, 0)
        root.pack_start(footer, False, False, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(root)
        self.window.add(scroll)
        self.window.show_all()

    def build_diagnosis_panel(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        panel.get_style_context().add_class("panel")
        caption = Gtk.Label(label="TANI RAPORU")
        caption.get_style_context().add_class("section-title")
        panel.pack_start(caption, False, False, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_kinetic_scrolling(True)
        scroll.set_size_request(-1, 120)
        self.diagnosis_label = Gtk.Label(label="")
        self.diagnosis_label.set_line_wrap(True)
        # Uzun günlük satırları/yollar boşluksuz da kırılsın; panel genişliği taşmasın.
        self.diagnosis_label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.diagnosis_label.set_xalign(0)
        self.diagnosis_label.set_yalign(0)
        self.diagnosis_label.set_max_width_chars(90)
        self.diagnosis_label.get_style_context().add_class("report")
        scroll.add(self.diagnosis_label)
        panel.pack_start(scroll, True, True, 0)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        buttons.set_homogeneous(True)
        buttons.pack_start(self.make_button("Yenile", self.refresh_diagnosis, small=True), True, True, 0)
        buttons.pack_start(self.make_button("Kilide dön", self.hide_diagnosis, small=True, confirm=True), True, True, 0)
        panel.pack_start(buttons, False, False, 0)
        return panel

    def show_diagnosis(self):
        self.refresh_diagnosis()
        self.stack.set_visible_child_name("tani")

    def refresh_diagnosis(self):
        self.diagnosis_label.set_text(collect_diagnosis())

    def hide_diagnosis(self):
        self.stack.set_visible_child_name("kilit")

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
                self.manual_label.set_text("— — — — — —")
                return True
            self.challenge = response
            # portal.json her QR'da yeniden okunur; panelden yapılan değişiklik yeniden başlatmadan uygulanır.
            portal_url = resolve_qr_portal_url(response.get("boardId"), self.config.get("qr_portal_url"))
            qr_url = build_qr_url(self.config["site_url"], response, portal_url)
            self.qr_image.set_from_pixbuf(pixbuf_from_qr(qr_url, self.qr_size))
            self.board_label.set_text("Tahta: {}".format(response["boardId"]))
            self.manual_label.set_text(response.get("manualRequestCode", "— — — — — —"))
            self.seconds_left = response["expiresIn"]
            self.confirm_button.set_sensitive(len(self.code) == self.code_length)
            self.set_status("Telefonunuzdan aldığınız kodu girin.")
        except Exception as error:
            self.challenge = None
            self.confirm_button.set_sensitive(False)
            self.qr_image.clear()
            self.manual_label.set_text("— — — — — —")
            self.board_label.set_text("Yerel doğrulama servisine ulaşılamıyor.")
            self.set_status(verifier_error_message(error), is_error=True)
        return True

    def show_service_error(self, response):
        error = response.get("error", "internal_error")
        if error == "master_unavailable":
            self.set_status("Master parola henüz alınmadı. Tahtayı internete bağlayın veya QR koduyla giriş yapın.", is_error=True)
        elif error == "cooldown":
            retry = response.get("retryAfter", 30)
            self.set_status(
                "Çok fazla hatalı deneme. {} saniye sonra tekrar deneyin.".format(retry),
                is_error=True,
            )
        elif error == "stale_challenge":
            self.set_status("İstek süresi doldu. Güncel QR veya istek kodunu kullanın.", is_error=True)
        else:
            self.set_status("İstek tamamlanamadı. QR kodu yenileyip tekrar deneyin.", is_error=True)

    def tick(self):
        if self.unlocked:
            self.tick_timer = None
            return False
        if self.challenge is not None:
            self.seconds_left = max(0, self.seconds_left - 1)
            self.qr_countdown.set_text(
                "QR / istek kodu yenilenmesine {} sn".format(self.seconds_left)
            )
            if self.seconds_left == 0:
                self.refresh_challenge()
        return True

    def add_digit(self, digit):
        if self.unlocked or len(self.code) >= self.code_length:
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
        shown = "●" * len(self.code) + "○" * (self.code_length - len(self.code))
        self.code_label.set_text(shown)
        self.confirm_button.set_sensitive(
            len(self.code) == self.code_length and (self.master_mode or self.challenge is not None)
        )

    def toggle_master(self):
        self.master_mode = not self.master_mode
        self.code_length = 6 if self.master_mode else MAX_CODE_DIGITS
        self.code = ""
        self.code_caption.set_text("02  ·  MASTER PAROLAYI GİR" if self.master_mode else "02  ·  6 HANELİ KODU GİR")
        self.master_button.set_label("QR koduna dön" if self.master_mode else "Yönetici master parolası")
        self.update_code_display()
        self.set_status("6 haneli yönetici master parolasını girin." if self.master_mode else "Telefonunuzdan aldığınız kodu girin.")

    def submit_code(self):
        if self.unlocked or (not self.master_mode and self.challenge is None) or len(self.code) != self.code_length:
            return
        try:
            response = call_verifier(
                {
                    "action": "verify-master" if self.master_mode else "verify",
                    "password": self.code if self.master_mode else None,
                    "nonce": self.challenge["nonce"] if self.challenge else None,
                    "unlockCode": self.code,
                }
            )
        except Exception as error:
            self.set_status(verifier_error_message(error), is_error=True)
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
                self.manual_label.set_text("— — — — — —")
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
        self.manual_label.set_text("— — — — — —")
        for name in ("refresh_timer", "tick_timer", "keyboard_timer"):
            source = getattr(self, name, None)
            if source is not None:
                GLib.source_remove(source)
                setattr(self, name, None)
        self.keyboard_guard.release()
        self.window.hide()

    def ensure_keyboard_guard(self):
        if self.unlocked:
            return False
        self.make_fullscreen()
        state = self.keyboard_guard.acquire()
        if state != "active_x11":
            self.keyboard_label.set_text("Kısayol koruması doğrulanamadı. Yönetici X11/kiosk oturum ayarlarını kontrol etmeli.")
        else:
            self.keyboard_label.set_text("Kilitliyken yalnız ekrandaki dokunmatik tuş takımını kullanın.")
        return True

    def make_fullscreen(self):
        # Test modu (TAHTA_KILIT_TEST_MODE=1, servis bunu kaldırır) normal pencere açar: WSLg tam ekran,
        # çerçevesiz ve üstte tutulan pencereye fare tıklaması iletmiyor.
        if not TEST_MODE:
            self.window.fullscreen()

    def guard_once(self):
        # Boşta (idle) çalıştırılan tek seferlik deneme. ensure_keyboard_guard kilitliyken True döndürdüğü
        # için doğrudan idle_add'e verilirse GLib onu durmadan tekrarlar ve ekrana sürekli tam ekran
        # isteği gönderir; düzenli deneme zaten saniyede bir keyboard_timer ile yapılır.
        self.ensure_keyboard_guard()
        return False

    def on_grab_broken(self, _window, _event):
        if not self.unlocked:
            self.keyboard_guard.broken()
        return True

    def on_delete(self, _window, _event):
        return not self.unlocked

    def on_key_press(self, _window, event):
        # Fiziksel klavyenin tüm tuşları kilitliyken tüketilir; kod ekrandan girilir.
        return not self.unlocked

    def restore_lock_window(self):
        if not self.unlocked:
            self.window.show_all()
            self.make_fullscreen()
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
