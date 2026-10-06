#!/bin/sh
set -eu

# Masaüstü oturumunun ekran değişkenlerini kullanıcı systemd yöneticisine aktar.
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS || true
systemctl --user start tahta-kilit-ui.service
