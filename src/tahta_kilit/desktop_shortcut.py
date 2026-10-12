"""BB Kilit kısayolunu oturum kullanıcısının XDG masaüstüne ekler."""
import os
from pathlib import Path
import subprocess
import tempfile

SOURCE = Path("/usr/share/applications/bb-kilit.desktop")


def ensure_desktop_shortcut():
    # Paket kurulumu root ile yapılır; kullanıcının masaüstü kendi oturumunda yazılır.
    if os.getuid() == 0 or not SOURCE.is_file():
        return
    home = Path.home()
    try:
        result = subprocess.run(
            ["/usr/bin/xdg-user-dir", "DESKTOP"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        directory = Path(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        directory = home / "Desktop"
    # HOME çıktısı, XDG'de masaüstünün devre dışı olduğu anlamına gelebilir.
    if not directory.is_absolute() or not directory.is_dir() or directory.resolve() == home.resolve():
        return
    target = directory / "BB Kilit.desktop"
    content = SOURCE.read_bytes()
    if target.is_symlink() or (target.exists() and not target.is_file()):
        return
    if target.exists():
        existing = target.read_bytes()
        if existing != content and b"X-BB-Kilit-Managed=true" not in existing:
            return  # Aynı isimli kullanıcı dosyasını değiştirme.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".bb-kilit-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            os.fchmod(stream.fileno(), 0o755)
        os.replace(temporary, target)
        temporary = None
        # GNOME/Caja destekliyorsa güvenilir başlatıcı işareti ekle.
        if Path("/usr/bin/gio").is_file():
            subprocess.run(
                ["/usr/bin/gio", "set", "-t", "boolean", str(target), "metadata::trusted", "true"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                check=False,
            )
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    try:
        ensure_desktop_shortcut()
    except (OSError, ValueError, subprocess.SubprocessError):
        # Masaüstü yazılamasa da kilit otomatik başlangıcı devam etmelidir.
        pass


if __name__ == "__main__":
    main()
