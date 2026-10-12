#!/bin/sh
set -eu

# İlk kurulumu kullanıcı oturumunda göster; paket postinst içinde GUI açılmaz.
if [ ! -r /etc/tahta-kilit/config.json ]; then
    exec /usr/bin/python3 -I -m tahta_kilit.setup_gui
fi

# Masaüstü oturumunun ekran değişkenlerini kullanıcı systemd yöneticisine aktar.
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS || true
systemctl --user start tahta-kilit-ui.service
