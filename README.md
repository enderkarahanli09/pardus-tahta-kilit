# BB Kilit — Pardus 0.1.7

## Kullanım

BB Kilit normal, kapatılabilir bir **Python 3 + GTK 3 (PyGObject)** penceresidir. Yalnız masaüstündeki veya uygulama menüsündeki **BB Kilit** başlatıcısına tıklayınca açılır. Oturum başlangıcında kendiliğinden açılmaz; tam ekranı veya fiziksel klavyeyi/kısayolları engellemez.

1. BB Kilit'i açın.
2. QR'ı telefondan okutun. Site doğrudan 6 haneli kod verir; öğretmen parolası/girişi yoktur.
3. Kodu klavyeden veya dokunmatik tuş takımından girin ve **Tahtayı Aç** düğmesine/Enter'a basın.
4. Doğru kod nonce'ı tüketir ve pencereyi gizler. BB Kilit'e tekrar tıklayınca yeni pencere/QR açılır. 40 dakika sonra kendiliğinden geri gelmez.

QR'ı gören herkes kod alabilir. Bu uygulama artık öğrenciyi işletim sistemi düzeyinde kısıtlayan kiosk/ekran kilidi değildir.

## Mevcut kurulum üzerine güncelleme

GitHub Releases'ten `tahta-kilit_0.1.7_all.deb` indirin ve Pardus paket yöneticisinde çift tıklayıp üzerine kurun. Yönetici yetkisi gerekir. Oturumu bir kez kapatıp açın; eski arayüz süreci kapanır ve eski sistem autostart girdisi kaldırılır. Sonra BB Kilit'i elle açın.

Tahta anahtarı, kimliği ve web adresi korunur; Vercel kaydını yeniden eklemeyin. Yeni paket yalnız web 0.2.0/protokol v2 ile çalışır. Eski sekmeyi yenileyin ve yeni QR okutun. BB Kilit kısayolu görünmezse uygulama menüsündeki BB Kilit'i açın; kullanıcı masaüstü kısayolu oluşturulur. Masaüstü devre dışıysa menüyü kullanın.

## İlk kurulum

1. `.deb` dosyasını grafik paket yöneticisiyle kurun. Eksik Python/GTK/QR/XDG bağımlılıkları için Pardus deposuna erişim gerekebilir.
2. **Tahta Kilidi Kurulum** sihirbazını açın. Benzersiz tahta kimliği ve HTTPS site adresini girin.
3. Sistem yönetici doğrulamasını tamamlayın. 32 bayt anahtar oluşturulur ve root izinleriyle saklanır.
4. Gizli `BOARD_KEYS_JSON` kaydını Vercel Production'a ekleyin, yeniden dağıtın. Mevcut diğer tahta kayıtlarını koruyun; anahtarı paylaşmayın.
5. Kullanıcı grubunun etkinleşmesi için oturumu kapatıp açın; BB Kilit'i elle açın.

Örnek kimlik: `ETAP-01`; site: `https://pardus-tahta-kilit-web.vercel.app/ac`. Bu değerler örnektir; gerçek anahtar içermez.

## Bileşenler ve çevrimdışı davranış

- Python 3, GTK 3/PyGObject: normal arayüz, dokunmatik ve klavye girişi.
- `python3-qrcode` ve Pillow: yerel QR görüntüsü.
- Standart `secrets`, `hmac`, `hashlib`: nonce, QR imzası ve kod doğrulama.
- Root doğrulama servisi + izinli Unix soketi; arayüz anahtarı doğrudan okuyamaz.
- systemd sistem servisi: doğrulayıcıyı çalıştırır. Kullanıcı arayüz servisi yalnız başlatıcı tarafından açılır; normal kapanış yeniden başlatılmaz.
- Debian `.deb`: kurulum/güncelleme. Başlangıç uyumluluk hedefi Pardus ETAP 23.4; gerçek sürüm cihazda doğrulanmalıdır.

Tahta günlük QR üretimi/doğrulama için internet kullanmaz. Telefonun kod servisine erişimi için internet gerekir. Yeni protokol `qr:v2` ve `unlock:v2` HMAC alanlarını, 120 saniyelik nonce süresini ve 6 haneli kodu kullanır. Ayrıntılı ortak algoritma web README'sindedir.

## Hatalar

Yanlış/eski/yeniden kullanılmış kod reddedilir. Hatalı denemelerde 30/60 saniyelik yerel bekleme uygulanır. Anahtar uyuşmazsa yönetici tahta kaydını kontrol etmelidir. Kod başındaki sıfırları atlamayın. Yerel servis hatasında kurulum ve kullanıcı grubu kontrol edilir. Web erişimi yoksa yeni kod alınamaz. Pencere kapatma düğmesi uygulamayı kapatır; sistem kilidini açma iddiası yoktur.

## BB Kilit kısayol koruması

0.1.6'daki yönetici onaylı koruma korunur. **Tahta Kilidi Kurulum → BB Kilit kısayolunu silinmeye karşı koru** ile etkinleştirin. Linux immutable destekleyen dosya sistemlerinde silme/değiştirme/taşıma engellenir. **Kısayol korundu** mesajını görmeden etkin kabul etmeyin. Desteklenmeyen dosya sisteminde hata gösterilir.

Silmek/paketi kaldırmak/masaüstünü taşımak için önce **BB Kilit kısayolunun korumasını kaldır (yönetici)** düğmesiyle sistem yönetici onayını tamamlayın. Dosya yöneticisinin normal Sil işlemi parola penceresi yerine izin hatası gösterebilir. Bu koruma işletim sistemi yöneticisini, masaüstünün gizlenmesini veya alternatif oturumları engellemez.

## Kaynak ve paket oluşturma

Linux ortamında `sh scripts/build-deb.sh` paketi `dist/` altında oluşturur. Kaynak `src/tahta_kilit/`, paket girdileri `share/`, Debian kurulum betikleri `debian/` altındadır. `board.key` `/etc/tahta-kilit/` altında tutulur ve pakete/Git'e eklenmez. Windows WSL/WSLg arayüz geliştirmesi için kullanılabilir; gerçek Pardus kurulumu ve masaüstü entegrasyonu ayrıca doğrulanmalıdır.
