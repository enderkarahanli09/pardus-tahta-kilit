#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(sed -n '1s/^[^(]*(\([^)]*\)).*/\1/p' "$PROJECT_DIR/debian/changelog")
if [ -z "$VERSION" ]; then
    echo "debian/changelog içinden paket sürümü okunamadı." >&2
    exit 1
fi

TEMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/tahta-kilit-package.XXXXXX")
trap 'rm -rf "$TEMP_ROOT"' EXIT HUP INT TERM
PACKAGE_ROOT="$TEMP_ROOT/root"
CONTROL_DIR="$PACKAGE_ROOT/DEBIAN"
OUTPUT_DIR="$PROJECT_DIR/dist"

mkdir -p \
    "$CONTROL_DIR" \
    "$PACKAGE_ROOT/usr/lib/python3/dist-packages/tahta_kilit" \
    "$PACKAGE_ROOT/usr/lib/tahta-kilit" \
    "$PACKAGE_ROOT/etc/xdg/autostart" \
    "$PACKAGE_ROOT/lib/systemd/system" \
    "$PACKAGE_ROOT/lib/systemd/user" \
    "$OUTPUT_DIR"

install -m 0644 "$PROJECT_DIR"/src/tahta_kilit/*.py \
    "$PACKAGE_ROOT/usr/lib/python3/dist-packages/tahta_kilit/"
install -m 0644 "$PROJECT_DIR/share/tahta-kilit-verifier.service" \
    "$PACKAGE_ROOT/lib/systemd/system/tahta-kilit-verifier.service"
install -m 0644 "$PROJECT_DIR/share/tahta-kilit-ui.service" \
    "$PACKAGE_ROOT/lib/systemd/user/tahta-kilit-ui.service"
install -m 0644 "$PROJECT_DIR/share/tahta-kilit.desktop" \
    "$PACKAGE_ROOT/etc/xdg/autostart/tahta-kilit.desktop"
sed 's/\r$//' "$PROJECT_DIR/share/start-ui.sh" > \
    "$PACKAGE_ROOT/usr/lib/tahta-kilit/start-ui.sh"
chmod 0755 "$PACKAGE_ROOT/usr/lib/tahta-kilit/start-ui.sh"

cat > "$CONTROL_DIR/control" <<EOF
Package: tahta-kilit
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: adduser, systemd, python3, python3-gi, gir1.2-gtk-3.0, python3-qrcode, python3-pil
Maintainer: Okul BT Yöneticisi <bt@example.invalid>
Description: Pardus ETAP offline smartboard lock screen
 Python GTK 3 lock screen and local Unix socket verifier for teacher unlock codes.
EOF

for maintainer_script in postinst prerm; do
    sed 's/\r$//' "$PROJECT_DIR/debian/$maintainer_script" \
        > "$CONTROL_DIR/$maintainer_script"
    chmod 0755 "$CONTROL_DIR/$maintainer_script"
done

dpkg-deb --build --root-owner-group "$PACKAGE_ROOT" \
    "$OUTPUT_DIR/tahta-kilit_${VERSION}_all.deb"
echo "Paket hazır: $OUTPUT_DIR/tahta-kilit_${VERSION}_all.deb"
