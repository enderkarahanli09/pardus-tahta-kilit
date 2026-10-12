"""Root test: gerçek anahtar/izin işlemleri geçici dizinde; servisler değiştirilmez."""
import contextlib
import io
import json
import os
import pwd
import stat
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from tahta_kilit import provision, setup_backend, verifier_service


assert os.geteuid() == 0, "Bu entegrasyon kontrolü root test ortamı ister."
caller = next(user for user in pwd.getpwall() if 1000 <= user.pw_uid < 65534 and user.pw_shell not in ("/bin/false", "/usr/sbin/nologin"))
with tempfile.TemporaryDirectory(prefix="tahta-setup-test-") as temporary, contextlib.ExitStack() as stack:
    directory = str(Path(temporary) / "config")
    key_path = str(Path(directory) / "board.key")
    config_path = str(Path(directory) / "config.json")
    stack.enter_context(patch.object(provision, "CONFIG_DIR", directory))
    for module in (provision, verifier_service):
        stack.enter_context(patch.object(module, "KEY_PATH", key_path))
        stack.enter_context(patch.object(module, "CONFIG_PATH", config_path))
    stack.enter_context(patch.dict(os.environ, {"PKEXEC_UID": str(caller.pw_uid)}))
    stack.enter_context(patch.object(setup_backend.subprocess, "run", return_value=type("Result", (), {"returncode": 0})()))
    stack.enter_context(patch.object(sys, "argv", ["setup-helper", "ETAP-DEMO", "https://example.org/ac"]))
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert setup_backend.main() == 0
    payload = json.loads(output.getvalue())
    original = Path(key_path).read_bytes()
    assert len(original) == 32
    assert stat.S_IMODE(os.stat(key_path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(config_path).st_mode) == 0o640
    assert os.stat(key_path).st_uid == 0
    assert payload["boardId"] == "ETAP-DEMO"
    assert not payload["existing"]
    result = setup_backend.configure(["OTHER-ID", "https://other.example/ac"])
    assert result["existing"]
    assert result["boardId"] == "ETAP-DEMO"
    assert Path(key_path).read_bytes() == original
    assert result["boardKeysEntry"] == payload["boardKeysEntry"]
print("Root setup integration passed; real board files and services unchanged")
