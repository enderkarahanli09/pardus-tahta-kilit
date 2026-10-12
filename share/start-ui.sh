#!/bin/sh
set -eu

# Kullanıcı masaüstü oturumunda BB Kilit başlatıcısını oluştur/güncelle.
/usr/bin/python3 -I -m tahta_kilit.desktop_shortcut || true

# İlk kurulumu kullanıcı oturumunda göster; paket postinst içinde GUI açılmaz.
if [ ! -r /etc/tahta-kilit/config.json ]; then
    exec /usr/bin/python3 -I -m tahta_kilit.setup_gui
fi

# Masaüstü oturumunun ekran değişkenlerini kullanıcı systemd yöneticisine aktar.
systemctl --user daemon-reload
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS || true
# Eski sürümde elle etkinleştirilmiş otomatik kullanıcı servisini kaldır.
systemctl --user disable tahta-kilit-ui.service 2>/dev/null || true
# BB Kilit'e tıklanınca mevcut süreç yerine tek normal pencere aç.
systemctl --user restart tahta-kilit-ui.service
