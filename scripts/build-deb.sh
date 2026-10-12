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
    "$PACKAGE_ROOT/usr/share/applications" \
    "$PACKAGE_ROOT/usr/share/tahta-kilit" \
    "$PACKAGE_ROOT/usr/share/polkit-1/actions" \
    "$PACKAGE_ROOT/lib/systemd/system" \
    "$PACKAGE_ROOT/lib/systemd/user" \
    "$OUTPUT_DIR"

install -m 0644 "$PROJECT_DIR"/src/tahta_kilit/*.py \
    "$PACKAGE_ROOT/usr/lib/python3/dist-packages/tahta_kilit/"
install -m 0644 "$PROJECT_DIR/share/tahta-kilit-verifier.service" \
    "$PACKAGE_ROOT/lib/systemd/system/tahta-kilit-verifier.service"
install -m 0644 "$PROJECT_DIR/share/tahta-kilit-ui.service" \
    "$PACKAGE_ROOT/lib/systemd/user/tahta-kilit-ui.service"
sed 's/\r$//' "$PROJECT_DIR/share/start-ui.sh" > \
    "$PACKAGE_ROOT/usr/lib/tahta-kilit/start-ui.sh"
chmod 0755 "$PACKAGE_ROOT/usr/lib/tahta-kilit/start-ui.sh"
sed 's/\r$//' "$PROJECT_DIR/share/setup-helper" > "$PACKAGE_ROOT/usr/lib/tahta-kilit/setup-helper"
chmod 0755 "$PACKAGE_ROOT/usr/lib/tahta-kilit/setup-helper"
install -m 0644 "$PROJECT_DIR/share/tahta-kilit-setup.desktop" "$PACKAGE_ROOT/usr/share/applications/tahta-kilit-setup.desktop"
install -m 0644 "$PROJECT_DIR/share/bb-kilit.desktop" "$PACKAGE_ROOT/usr/share/applications/bb-kilit.desktop"
if [ -f "$PROJECT_DIR/share/assets/borusan-mtal-logo.jpg" ]; then
    install -m 0644 "$PROJECT_DIR/share/assets/borusan-mtal-logo.jpg" \
        "$PACKAGE_ROOT/usr/share/tahta-kilit/borusan-mtal-logo.jpg"
fi
install -m 0644 "$PROJECT_DIR/share/org.tahtakilit.setup.policy" "$PACKAGE_ROOT/usr/share/polkit-1/actions/org.tahtakilit.setup.policy"

cat > "$CONTROL_DIR/control" <<EOF
Package: tahta-kilit
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: adduser, passwd, systemd, pkexec, policykit-1-gnome | polkit-kde-agent-1, python3, python3-gi, gir1.2-gtk-3.0, python3-qrcode, python3-pil, xdg-user-dirs
Maintainer: enderkarahanli09 <301288247+enderkarahanli09@users.noreply.github.com>
Description: BB Kilit offline QR code application
  Python GTK 3 normal window and local verifier for six-digit QR unlock codes.
EOF

for maintainer_script in postinst prerm; do
    sed 's/\r$//' "$PROJECT_DIR/debian/$maintainer_script" \
        > "$CONTROL_DIR/$maintainer_script"
    chmod 0755 "$CONTROL_DIR/$maintainer_script"
done

dpkg-deb --build --root-owner-group "$PACKAGE_ROOT" \
    "$OUTPUT_DIR/tahta-kilit_${VERSION}_all.deb"
echo "Paket hazır: $OUTPUT_DIR/tahta-kilit_${VERSION}_all.deb"
