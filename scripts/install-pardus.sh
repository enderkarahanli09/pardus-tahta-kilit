#!/bin/sh
set -eu

fail() {
    printf 'Kurulum durduruldu: %s\n' "$1" >&2
    exit 1
}

SCRIPT_PATH=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/$(basename -- "$0")
if [ "$(id -u)" -ne 0 ]; then
    command -v sudo >/dev/null 2>&1 || fail "Yönetici yetkisi için sudo bulunamadı."
    exec sudo -- sh "$SCRIPT_PATH" "$@"
fi

if [ "$#" -ne 1 ]; then
    printf 'Kullanım: sudo sh %s /yol/tahta-kilit_surum_all.deb\n' "$SCRIPT_PATH" >&2
    exit 2
fi

PACKAGE_PATH=$(readlink -f -- "$1")
[ -f "$PACKAGE_PATH" ] || fail ".deb paketi bulunamadı: $1"
command -v apt-get >/dev/null 2>&1 || fail "Bu yardımcı Pardus/Debian için apt-get gerektirir."

if [ -e /etc/tahta-kilit/config.json ] || [ -e /etc/tahta-kilit/board.key ]; then
    fail "Tahta yapılandırması zaten var. Mevcut anahtarı ezmemek için otomatik kurulum durduruldu."
fi

DEFAULT_USER=${SUDO_USER:-}
if [ -n "$DEFAULT_USER" ] && [ "$DEFAULT_USER" != root ]; then
    printf 'ETAP grafik oturum kullanıcı adı [%s]: ' "$DEFAULT_USER"
else
    printf 'ETAP grafik oturum kullanıcı adı: '
fi
IFS= read -r SESSION_USER
SESSION_USER=${SESSION_USER:-$DEFAULT_USER}
[ -n "$SESSION_USER" ] || fail "Grafik oturum kullanıcı adı boş bırakılamaz."
getent passwd "$SESSION_USER" >/dev/null 2>&1 || fail "Kullanıcı bulunamadı: $SESSION_USER"

printf 'Tahta kimliği [ETAP-01]: '
IFS= read -r BOARD_ID
BOARD_ID=${BOARD_ID:-ETAP-01}
printf '%s\n' "$BOARD_ID" | grep -Eq '^[A-Z0-9][A-Z0-9-]{0,63}$' || \
    fail "Tahta kimliği büyük A-Z harfleri, rakam ve tire içermelidir."

printf 'Öğretmen web adresi [https://pardus-tahta-kilit-web.vercel.app/ac]: '
IFS= read -r SITE_URL
SITE_URL=${SITE_URL:-https://pardus-tahta-kilit-web.vercel.app/ac}
case "$SITE_URL" in
    https://*) ;;
    *) fail "Web adresi https:// ile başlamalıdır." ;;
esac

printf '\nPaket kuruluyor ve gerekli Pardus paketleri çözümleniyor…\n'
apt-get install -y "$PACKAGE_PATH" || fail "Paket kurulamadı. İnternet/aPT kaynaklarını ve paket sürümünü kontrol edin."

printf '\nTahta için yerel anahtar ve yapılandırma oluşturuluyor…\n'
/usr/bin/python3 -m tahta_kilit.provision \
    --board-id "$BOARD_ID" \
    --site-url "$SITE_URL" || fail "Tahta yapılandırması tamamlanamadı."

usermod -aG tahta-kilit "$SESSION_USER" || fail "Oturum kullanıcısı tahta-kilit grubuna eklenemedi."
systemctl enable --now tahta-kilit-verifier.service || \
    fail "Doğrulama servisi başlatılamadı. systemctl status tahta-kilit-verifier.service çıktısını kontrol edin."

printf '\nKurulum tamamlandı.\n'
printf 'Tahta kimliği: %s\n' "$BOARD_ID"
printf 'Grafik oturum kullanıcısı: %s\n' "$SESSION_USER"
printf 'Değişikliklerin geçerli olması için bu kullanıcı oturumunu kapatıp yeniden açın.\n'
printf '\nWeb yöneticisi, Vercel BOARD_KEYS_JSON ayarını bu tahtanın kimliği ve anahtarıyla eşleştirmelidir.\n'
printf 'Anahtar değerini almak için yönetici terminalinde şu komutu çalıştırın:\n'
printf '  sudo base64 -w 0 /etc/tahta-kilit/board.key\n'
printf 'Bu komutun çıktısı gizlidir; yalnız Vercel sunucu ayarına girin.\n'
