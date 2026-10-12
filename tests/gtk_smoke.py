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
}, None)
assert not window.key.get_visibility()
assert window.copy.get_sensitive()
assert window.board.get_text() == "ETAP-DEMO"
assert "Mevcut anahtar korundu" in window.status.get_text()
root = Path(__file__).resolve().parent.parent
policy = ET.parse(root / "share/org.tahtakilit.setup.policy")
action = policy.find("action")
assert action.attrib["id"] == "org.tahtakilit.setup"
assert action.findtext("defaults/allow_active") == "auth_admin"
assert action.findtext("defaults/allow_any") == "no"
assert action.findtext("defaults/allow_inactive") == "no"
assert action.find("annotate").text == "/usr/lib/tahta-kilit/setup-helper"
print("GTK setup and polkit policy smoke passed")
