#!/bin/sh
set -eu

# İlk kurulumu kullanıcı oturumunda göster; paket postinst içinde GUI açılmaz.
if [ ! -r /etc/tahta-kilit/config.json ]; then
    exec /usr/bin/python3 -I -m tahta_kilit.setup_gui
fi

# Masaüstü oturumunun ekran değişkenlerini kullanıcı systemd yöneticisine aktar.
systemctl --user daemon-reload
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS || true
# Linger/başka oturum nedeniyle eski gizli süreç yaşıyor olsa bile her yeni giriş kilitlidir.
systemctl --user restart tahta-kilit-ui.service
