"""Paket postinst güncellemesini geçici dosyalar ve sahte sistem araçlarıyla sınar."""
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix="tahta-upgrade-test-") as temporary:
    base = Path(temporary)
    config = base / "config"
    config.mkdir()
    key = config / "board.key"
    settings = config / "config.json"
    key.write_bytes(b"k" * 32)
    settings.write_text('{"board_id":"ETAP-DEMO","site_url":"https://example.org/ac"}')
    key.chmod(0o600)
    settings.chmod(0o640)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (key, settings)}
    tools = base / "bin"
    tools.mkdir()
    calls = base / "calls"
    for name in ("getent", "install", "systemctl"):
        tool = tools / name
        tool.write_text('#!/bin/sh\nprintf "%s\\n" "' + name + ' $*" >> "$CALLS_PATH"\nexit 0\n')
        tool.chmod(0o700)
    script = base / "postinst"
    script.write_text((root / "debian/postinst").read_text().replace("/etc/tahta-kilit", str(config)))
    env = dict(os.environ, PATH=str(tools) + ":" + os.environ["PATH"], CALLS_PATH=str(calls))
    subprocess.run(["/bin/sh", str(script), "configure", "0.1.2"], env=env, check=True)
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (key, settings)}
    assert before == after
    assert key.stat().st_mode & 0o777 == 0o600
    assert settings.stat().st_mode & 0o777 == 0o640
    recorded = calls.read_text()
    assert "systemctl daemon-reload" in recorded
    assert "systemctl try-restart tahta-kilit-verifier.service" in recorded
    assert "tahta-kilit-ui.service" not in recorded
    key.unlink()
    settings.unlink()
    calls.write_text("")
    subprocess.run(["/bin/sh", str(script), "configure"], env=env, check=True)
    assert "try-restart" not in calls.read_text()
print("Upgrade smoke passed: keys/config preserved; no active UI restart; fresh install not started")
