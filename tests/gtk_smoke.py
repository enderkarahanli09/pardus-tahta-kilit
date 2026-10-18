"""Grafik oturumda çalıştırılır; pencere göstermeden sentetik sonucu kontrol eder."""
import xml.etree.ElementTree as ET
from pathlib import Path

from tahta_kilit.setup_gui import SetupWindow


window = SetupWindow()
assert not window.key.get_visibility()
assert not window.copy.get_sensitive()
window.complete({
    "boardId": "ETAP-DEMO",
    "siteUrl": "https://example.org/ac",
    "existing": True,
    "boardKeysEntry": {"ETAP-DEMO": "DEMO-ONLY"},
    "registrationError": "İnternet bağlantısı yok",
}, None)
assert not window.key.get_visibility()
assert window.copy.get_sensitive()
assert window.board.get_text() == "ETAP-DEMO"
assert "Mevcut anahtar korundu" in window.status.get_text()
assert "Otomatik kayıt yapılamadı: İnternet bağlantısı yok" in window.status.get_text()
assert "onaya gönderildi" not in window.status.get_text()
assert not hasattr(window, "password")
window.complete({"registered": False, "pending": True, "boardId": "ETAP-DEMO", "fingerprint": "ABCD-1234"}, None)
assert "Onay kodu: ABCD-1234" in window.status.get_text()
assert window.code_label.get_text() == "ABCD-1234" and window.code_revealer.get_reveal_child()
window.complete({"registered": True, "pending": False, "boardId": "ETAP-DEMO", "fingerprint": "ABCD-1234"}, None)
assert "sisteme kayıtlı" in window.status.get_text()
assert not window.code_revealer.get_reveal_child()
window.complete(None, "Yönetici onayı verilmedi.")
assert window.status_box.get_style_context().has_class("error")
assert window.register_button.get_sensitive()
root = Path(__file__).resolve().parent.parent
policy = ET.parse(root / "share/org.tahtakilit.setup.policy")
action = policy.find("action")
assert action.attrib["id"] == "org.tahtakilit.setup"
assert action.findtext("defaults/allow_active") == "auth_admin"
assert action.findtext("defaults/allow_any") == "no"
assert action.findtext("defaults/allow_inactive") == "no"
assert action.find("annotate").text == "/usr/lib/tahta-kilit/setup-helper"
print("GTK setup and polkit policy smoke passed")
