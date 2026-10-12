"""Yönetici onayı sonrası tek BB Kilit dosyasında Linux immutable koruması."""
from array import array
import fcntl
import os
from pathlib import Path
import stat

# Linux FS_IOC_{GET,SET}FLAGS; _IOR/_IOW unsigned long platform boyutundadır.
_SIZE = array("L").itemsize
GET_FLAGS = (2 << 30) | (_SIZE << 16) | (ord("f") << 8) | 1
SET_FLAGS = (1 << 30) | (_SIZE << 16) | (ord("f") << 8) | 2
IMMUTABLE = 0x10
SOURCE = Path("/usr/share/applications/bb-kilit.desktop")


def protect_shortcut(caller, directory_text, protect=True):
    home = Path(caller.pw_dir)
    directory = Path(directory_text)
    if not home.is_absolute() or not directory.is_absolute():
        raise ValueError("Masaüstü konumu geçersiz.")
    try:
        parts = directory.relative_to(home).parts
    except ValueError:
        raise ValueError("Masaüstü kullanıcı ev dizini içinde olmalıdır.") from None
    if not parts or any(part in (".", "..") for part in parts):
        raise ValueError("Masaüstü konumu geçersiz.")
    # Root kullanıcı kontrollü symlink yollarını takip etmez.
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    file_descriptor = None
    try:
        for component in home.parts[1:] + parts:
            next_descriptor = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        file_descriptor = os.open("BB Kilit.desktop", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        info = os.fstat(file_descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid not in (0, caller.pw_uid) or info.st_size > 4096:
            raise PermissionError("Yalnız kurulumun BB Kilit kısayolu korunabilir.")
        expected = SOURCE.read_bytes()
        if os.read(file_descriptor, 4097) != expected:
            raise PermissionError("BB Kilit kısayolu değiştirilmiş; yönetici orijinal kısayolu yeniden oluşturmalı.")
        flags = array("L", [0])
        fcntl.ioctl(file_descriptor, GET_FLAGS, flags, True)
        if protect:
            was_protected = bool(flags[0] & IMMUTABLE)
            if not was_protected:
                os.fchown(file_descriptor, 0, 0)
                os.fchmod(file_descriptor, 0o755)
                try:
                    fcntl.ioctl(file_descriptor, SET_FLAGS, array("L", [flags[0] | IMMUTABLE]))
                    # Koruma kurulmadan önce açık yazma tanıtıcısıyla değiştirilmiş mi?
                    os.lseek(file_descriptor, 0, os.SEEK_SET)
                    if os.read(file_descriptor, 4097) != expected:
                        raise PermissionError("Kısayol koruma sırasında değişti; koruma uygulanmadı.")
                except BaseException:
                    try:
                        fcntl.ioctl(file_descriptor, SET_FLAGS, flags)
                    finally:
                        os.fchown(file_descriptor, caller.pw_uid, caller.pw_gid)
                    raise
        else:
            fcntl.ioctl(file_descriptor, SET_FLAGS, array("L", [flags[0] & ~IMMUTABLE]))
            os.fchown(file_descriptor, caller.pw_uid, caller.pw_gid)
        return {"shortcutProtected": protect}
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        os.close(descriptor)
