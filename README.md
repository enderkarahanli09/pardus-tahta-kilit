# Pardus Tahta Kilidi — ETAP masaüstü uygulaması

Pardus Tahta Kilidi, ETAP akıllı tahtada oturum açıldığında açılan tam ekran bir öğretmen kilit ekranı ve yerel kod doğrulama servisidir. QR kodunu tahta kendi üzerinde ve internet olmadan üretir. Öğretmen telefonundan web sayfasını açıp Excel listesindeki 6 haneli öğretmen kodunu girer; web uygulaması QR'a özel 8 haneli açma kodunu verir. Tahta kodu kendi anahtarıyla yerelde doğrular.

> Bu depo Pardus uygulamasını içerir. Öğretmen web uygulaması ayrı depoda geliştirilir: [pardus-tahta-kilit-web](https://github.com/enderkarahanli09/pardus-tahta-kilit-web). Pardus'ta `.exe` kullanılmaz; dağıtım biçimi Debian `.deb` paketidir.

## İçindekiler

- [Önemli çalışma sınırları](#önemli-çalışma-sınırları)
- [Mimari ve kullanım akışı](#mimari-ve-kullanım-akışı)
- [Kolay kurulum](#kolay-kurulum)
- [Kurulumdan sonra web sunucusunu eşleştirme](#kurulumdan-sonra-web-sunucusunu-eşleştirme)
- [Elle kurulum](#elle-kurulum)
- [Tahta başlatma ve günlük kullanım](#tahta-başlatma-ve-günlük-kullanım)
- [Windows/WSL üzerinde arayüz testi](#windowswsl-üzerinde-arayüz-testi)
- [Güvenlik ve öğrenci oturumu](#güvenlik-ve-öğrenci-oturumu)
- [Sorun giderme](#sorun-giderme)
- [Kaldırma ve anahtar saklama](#kaldırma-ve-anahtar-saklama)
- [Geliştirme ve paket oluşturma](#geliştirme-ve-paket-oluşturma)
- [Kaynak kod haritası](#kaynak-kod-haritası)

## Önemli çalışma sınırları

- İlk uyumluluk hedefi **64 bit Pardus ETAP 23.4**. Kurmadan önce pilot tahtanın ETAP/Pardus sürümünü, ekran çözünürlüğünü ve grafik oturum türünü doğrulayın.
- Tahta tarafı QR üretimi ve kod doğrulaması **çevrimdışı** çalışır. Öğretmenin telefonu ile web API'si, öğretmen kodunu kontrol etmek için internete bağlı olmalıdır. İnternet/Web yoksa yeni kod alınamaz; tahta kilitli kalır.
- Tahta anahtarı web sunucusunda ve tahtada aynı olmalıdır. Her tahtanın farklı kimliği ve anahtarı olmalıdır.
- Öğretmen kodları ve çalışma kitabı Pardus'a indirilmez. Dosya ve öğretmen listesi web uygulamasında kalır; kod değişince Pardus paketini tekrar kurmak gerekmez.
- Uygulama ekranı tek başına işletim sistemi güvenlik kilidi değildir. Öğrenci oturumunu kısıtlama ve BIOS/UEFI ayarları ayrıca yapılmalıdır.
- Bu depo prototip düzeyindedir. Gerçek ETAP cihazında kısayol, oturum açılışı, dokunmatik kullanım ve kurtarma testleri tamamlanmadan üretim güvenliği varmış gibi değerlendirmeyin.

## Mimari ve kullanım akışı

1. ETAP'ın grafik oturumunda `tahta-kilit` otomatik açılır ve tam ekran kilit arayüzünü gösterir.
2. Root yetkili `tahta-kilit-verifier` servisi yerel Unix soketi açar. Anahtarı yalnız bu servis okur.
3. Servis 128 bit rastgele nonce üretir; HMAC-SHA256 QR imzası hesaplar. Arayüz, tahtanın QR'ını her 120 saniyede yeniler.
4. Öğretmen QR'ı telefon kamerasıyla okutur. Web sayfası QR bağlantısını açar.
5. Öğretmen Excel listesindeki **6 haneli Öğretmen Kodu** değerini girer. Altıncı rakamdan sonra web uygulaması otomatik doğrulama isteği yapar.
6. Web sitesi öğretmen kodunu ve QR imzasını doğrular; 8 haneli açma kodunu gösterir.
7. Öğretmen kodu tahtanın dokunmatik sayı tuş takımına girer. Tahta kodu internet kullanmadan aynı anahtarla tekrar hesaplar.
8. Doğru, güncel ve kullanılmamış kodda kilit ekranı 40 dakika gizlenir; sonra tekrar görünür. Servis veya tahta yeniden başlarsa başlangıç durumu kilitlidir.

### Bileşenler

- **GTK 3 kilit ekranı:** Python 3 / PyGObject ile dokunmatik arayüzü açar; QR ve tuş takımını gösterir.
- **Yerel doğrulama servisi:** Python standart kütüphanesiyle HMAC kontrolü, nonce süre sınırı, tekrar kullanımı engelleme ve deneme beklemesi uygular.
- **Unix soketi:** Arayüz ile servis arasında aynı makinede izinleri sınırlı JSON iletişimi sağlar.
- **systemd ve XDG autostart:** Servisi sistem açılışında, arayüzü grafik oturum açılışında başlatır; arayüz çökerse yeniden başlatır.
- **`.deb` paketi:** Uygulama dosyaları, servis tanımları ve oturum başlatma girdilerini kurar. Pardus bağımlılık paketlerini sistemde bulmalı veya kurulum sırasında paket deposuna erişebilmelidir.

## Kolay kurulum

Bu yöntem GitHub Releases'den alınan `.deb` ile bu depodaki yardımcı betiği kullanır. Başka bir internet bağlantılı bilgisayarda dosyaları indirip USB ile tahtaya aktarabilirsiniz. Uygulamanın günlük çalışması için internet gerekmez; ilk kurulumdaki sistem bağımlılıkları için Pardus paket deposu bağlantısı gerekebilir.

### 1. İndirme

1. [GitHub Releases](https://github.com/enderkarahanli09/pardus-tahta-kilit/releases) sayfasından en son `tahta-kilit_<sürüm>_all.deb` paketini indirin.
2. Bu depodaki [`scripts/install-pardus.sh`](https://github.com/enderkarahanli09/pardus-tahta-kilit/blob/main/scripts/install-pardus.sh) dosyasını indirin ve `install-pardus.sh` adıyla `.deb` dosyasının bulunduğu klasöre kaydedin.
3. İki dosyayı tahtaya veya USB belleğe kopyalayın.

### 2. Tek komutla kurulum

Dosyaların olduğu klasörde terminal açın. Paket dosya adını indirdiğiniz sürüme göre yazın:

```sh
sudo sh ./install-pardus.sh ./tahta-kilit_0.1.0_all.deb
```

Yardımcı betik şunları yapar:

- Mevcut anahtar/config varsa üzerine yazmamak için durur.
- Grafik oturum kullanıcısını sorar; `sudo` ile açıldıysa mevcut oturum hesabını varsayılan gösterir.
- Tahta kimliğini ve web adresini sorar. Varsayılan web adresi `https://pardus-tahta-kilit-web.vercel.app/ac` olur.
- `.deb` paketini `apt-get install` ile kurar; eksik Python, GTK ve QR bağımlılıklarını Pardus paket yöneticisinden yükler.
- Tahta için 256 bit anahtar üretir, yerel yapılandırmayı yazar, doğrulama servisini başlatır ve seçilen oturum kullanıcısını `tahta-kilit` grubuna ekler.

Tahta kimliği yalnız büyük Latin harfleri, rakam ve tire içerebilir; örneğin `ETAP-01`. Bu kimlik, Vercel'deki tahta anahtarı kaydında **aynı yazılmalıdır**. Tahtanın grafik oturumunu kapatıp yeniden açın; ilk açılışta kilit ekranı otomatik gelmelidir.

### İnternet olmayan kurulum

QR üretimi ve tahta doğrulaması çalışma sırasında çevrimdışıdır. Kurulum betiği yerel `.deb` dosyasını kurarken eksik bağımlılıklar için `apt-get` kullanır. Tahtada internet yoksa şu iki seçeneği kullanın:

1. Kurulumdan önce gereken bağımlılıkları Pardus paket deposuna erişen bir ağda indirin/kurun, ardından `.deb` paketini USB'den kurun.
2. Ağ erişimli Pardus/ETAP ortamında paketi kurup anahtar/yapılandırmayı oluşturun; cihaz sürümü ve grafik oturum uyumunu yine hedef tahtada doğrulayın.

Yalnız `.deb` dosyasının olması tüm bağımlılıkların içine gömülü olduğu anlamına gelmez. İnternetsiz kurulum için GTK, Python, QR ve sistem paketlerini de önceden hazırlayın.

## Kurulumdan sonra web sunucusunu eşleştirme

Her tahtada üretilen anahtarı, web uygulamasının sunucu ayarlarındaki `BOARD_KEYS_JSON` eşlemesine güvenli biçimde ekleyin. Örnek biçim:

```json
{"ETAP-01":"<bu-tahtaya-ait-base64-anahtar>"}
```

Anahtar değerini tahtada yönetici terminalinden almak için:

```sh
sudo base64 -w 0 /etc/tahta-kilit/board.key
```

Bu komutun çıktısı **gizli anahtardır**. Yalnız yetkili yönetici Vercel'in sunucu tarafındaki `BOARD_KEYS_JSON` değişkenine girsin. Anahtarı GitHub'a, bu sohbete, QR'a, öğretmen telefonuna veya ekran görüntüsüne koymayın. Değişken güncellenince web projesini yeniden dağıtın. Web uygulaması ayrıca öğretmen tablosunun OneDrive/Google E-Tablolar bağlantısını yönetici panelinin özel ayarında saklar; o bağlantı tahtaya aktarılmaz.

Tahta yapılandırmasını yönetici olarak doğrulama:

```sh
sudo cat /etc/tahta-kilit/config.json
sudo systemctl status tahta-kilit-verifier.service --no-pager
```

`config.json` içinde `board_id` ve HTTPS `site_url` bulunur; gizli anahtar `board.key` dosyasındadır. Anahtar içeriğini `cat` ile görüntülemeyin; Base64 aktarım komutunu yalnız güvenli Vercel ayarı için kullanın.

## Elle kurulum

Otomatik betik kullanmadan kurmak isteyen sistem yöneticisi:

```sh
sudo apt update
sudo apt install ./tahta-kilit_0.1.0_all.deb
sudo python3 -m tahta_kilit.provision --board-id ETAP-01 --site-url https://pardus-tahta-kilit-web.vercel.app/ac
sudo usermod -aG tahta-kilit "$USER"
sudo systemctl enable --now tahta-kilit-verifier.service
```

`sudo usermod` satırında `sudo` komutuyla çalışan shell içindeki `$USER` `root` olabilir. Böyle bir durumda gerçek ETAP oturum kullanıcısını açıkça yazın:

```sh
sudo usermod -aG tahta-kilit ogretmen
```

Paket yüklemesinden sonra oturumu kapatıp açmak gerekir; grup üyeliği var olan oturuma anında uygulanmaz. Provision komutu mevcut anahtarı veya yapılandırmayı hiçbir koşulda ezmez. Komut “zaten var” hatası verirse yeni anahtar üretmek için dosyaları silmeyin; önce mevcut tahtayı ve web anahtar eşlemesini yöneticinizle doğrulayın.

### Otomatik kurulumda sorulacak değerler

- **Grafik oturum kullanıcısı:** Kilit ekranının açılacağı standart ETAP kullanıcısı. Yönetici/root hesabı olmamalıdır.
- **Tahta kimliği:** Yönetici tarafından seçilen benzersiz `ETAP-01` benzeri kimlik.
- **Web adresi:** Öğretmenlerin açtığı HTTPS adresi; genellikle `/ac` ile biter.

Bu bilgi ve anahtarlar tahtaya kurulum sırasında bir kez yazılır. Öğretmen kod listesi, OneDrive paylaşım bağlantısı ve öğretmen adları tahtaya gelmez.

## Tahta başlatma ve günlük kullanım

- **Başlangıç:** ETAP grafik oturumu kullanıcı girişinden sonra kilit ekranı otomatik başlamalıdır.
- **QR:** 120 saniye geçerli olacak şekilde yenilenir. Süresi geçmiş QR'dan kod alınsa bile tahta eski nonce'ı kabul etmez. Yeni QR okutun.
- **Açma kodu:** Öğretmen sayfasında Excel listesindeki 6 haneli öğretmen kodunun son rakamını girdikten sonra otomatik görünür. Tahtaya girilecek ayrı açma kodu 8 hanedir.
- **Kullanım süresi:** Doğru kod ekranı 40 dakika kapatır; sonra kilit geri gelir.
- **İnternet kesilmesi:** Tahta QR üretmeye ve yerel doğrulamaya devam eder. Telefon ve web/API erişimi olmadan yeni bir öğretmen açma kodu alınamaz.
- **Excel güncellemesi:** Öğretmen listesi web sunucusunca okunur. Yönetici panelinde Drive yenileme işlemi yapılır; Pardus paketinin yeniden kurulması gerekmez.
- **Yanlış kod:** Beş yanlış denemeden sonra tahtada 30 saniye bekleme uygulanır; daha geniş periyotta ek bekleme vardır.
- **Yeniden başlatma/çökme:** Arayüz yeniden açıldığında kilit ekranına döner; 40 dakikalık açma oturumu yeniden başlatma sonrası korunmaz.

## Windows/WSL üzerinde arayüz testi

WSL, uygulamanın arayüzünü Windows masaüstünde açmaya yarar; gerçek Pardus/ETAP güvenlik davranışını taklit etmez. `Alt+F1` kapatma kısayolu sadece `TAHTA_KILIT_TEST_MODE=1` ile etkin olur.

WSL2/WSLg ve Ubuntu kuruluysa Ubuntu terminalinde kaynak klasörüne gidin. Windows proje klasörü `/mnt/c` altında görünür. Gerekli arayüz kitaplıkları:

```sh
sudo apt update
sudo apt install python3 python3-gi gir1.2-gtk-3.0 python3-qrcode python3-pil
```

Test modu, `/etc/tahta-kilit/config.json`, root korumalı `/etc/tahta-kilit/board.key`, `tahta-kilit` grubu ve çalışan yerel doğrulama servisi ister. Daha önce kurulum yapıldıysa iki ayrı terminalde çalıştırın.

Terminal 1 — yerel doğrulama servisi (root):

```sh
sudo install -d -o root -g tahta-kilit -m 0750 /run/tahta-kilit
cd "/mnt/c/Users/<WindowsKullanıcısı>/Desktop/Kendi Projelerim/Tübitak 2027/pardus-tahta-kilit"
sudo env PYTHONPATH=src python3 -m tahta_kilit.verifier_service
```

Terminal 2 — test arayüzü:

```sh
cd "/mnt/c/Users/<WindowsKullanıcısı>/Desktop/Kendi Projelerim/Tübitak 2027/pardus-tahta-kilit"
TAHTA_KILIT_TEST_MODE=1 PYTHONPATH=src python3 -m tahta_kilit.lock_screen
```

Bu komutlar daha önce yapılandırılmış tahtayı gerektirir. WSL'de henüz key/config yoksa önce test amaçlı .deb kurup `provision` çalıştırın veya ayrı bir test ortamı oluşturun; üretim tahtasının anahtarını kopyalamayın. Pencere odaktayken **Alt+F1** yalnız test uygulamasını kapatır. Normal Pardus dağıtımında test değişkeni tanımlanmaz ve bu çıkış kısayolu kullanılmaz.

Gerçek ETAP'ta `Alt+Tab`, `Alt+F4`, `Ctrl+Alt+F1…F6`, güç menüsü, oturum kapatma ve BIOS/USB önyükleme davranışları ayrıca denenmelidir. WSLg, bu sistem çapı kısayol ve kiosk testlerinin yerine geçmez.

## Güvenlik ve öğrenci oturumu

### Dosya ve süreç izinleri

- `/etc/tahta-kilit/board.key`: root sahibi, `0600`; yalnız root doğrulama servisi okur.
- `/etc/tahta-kilit/config.json`: root ve `tahta-kilit` grubu; arayüz yalnız tahta kimliği/web URL'sini okur.
- `/run/tahta-kilit/verifier.sock`: root:`tahta-kilit`, `0660`; yalnız yetkilendirilmiş yerel grup erişir.
- Doğrulama servisi root olarak çalışsa da `CAP_CHOWN` dışındaki Linux yetkileri sınırlandırılmıştır; ağ adres aileleri, eşzamanlı istemci sayısı, görev ve bellek kullanımı da kısıtlanır.
- Öğretmen web/API sırrı, OneDrive bağlantısı ve Excel satırları UI sürecine ve öğrenci hesabına aktarılmaz.

### İşletim sistemi düzeyi kısıtlar

1. Öğrenci/tahta oturumunu standart kullanıcı yapın; `sudo`, yönetici parolası veya root erişimi vermeyin.
2. Terminal, uygulama başlatma penceresi, dosya yöneticisi, ayarlar, sistem menüsü ve oturum kapatma/yeniden başlatma seçeneklerini ETAP kiosk politikasına göre kısıtlayın.
3. Masaüstü pencere yöneticisi ve ETAP politikaları üzerinden `Alt+Tab`, `Alt+F4`, `Ctrl+Alt+F1…F6` ve diğer sistem kısayollarını gerçek cihazda doğrulayın.
4. UEFI/BIOS yönetici parolası ve harici USB'den önyükleme kurallarını okul yöneticisi ayarlasın.
5. `TAHTA_KILIT_TEST_MODE=1` yalnız test içindir. Gerçek oturumun autostart veya systemd tanımına eklemeyin.

**Yayın engeli:** Arayüz `systemd --user` biriminde, oturum kullanıcısının yetkileriyle çalışır. Aynı hesap terminal veya başka bir yönetim aracı açabiliyorsa `systemctl --user stop/disable tahta-kilit-ui.service` komutuyla kilidi durdurabilir; `Restart=always` bu kasıtlı durdurmayı engellemez. Bu nedenle öğrenci hesabı ETAP kiosk oturumuyla sınırlandırılmalı, terminal/kısayollar engellenmeli ve uygulama oturum yöneticisi tarafından korunmalıdır. Yalnız GTK tam ekranı öğrenciyi kilitlemek için yeterli değildir.

Yönetici/root yetkisine erişebilen biri uygulamayı durdurabilir, kaldırabilir veya anahtarları değiştirebilir; yazılımın amacı yöneticiye karşı koruma sağlamak değildir. Fiziksel güç düğmesi, BIOS, harici önyükleme ve işletim sistemi açıklarına karşı garanti verilmez. Gerçek ETAP'ta `Alt+Tab`, `Alt+F4`, `Ctrl+Alt+F1…F6`, güç menüsü, oturum kapatma, kiosk oturumu ve uygulama servisinin öğrenci hesabından durdurulamaması ayrıca doğrulanmalıdır.

## Sorun giderme

| Belirti | Kontrol / işlem |
| --- | --- |
| Grafik oturum açılınca kilit ekranı gelmiyor | Oturumu kapatıp açın; XDG autostart `tahta-kilit.desktop` dosyasını ve kullanıcı systemd servisini kontrol edin. `journalctl --user -u tahta-kilit-ui.service -b` ile kullanıcı servisi günlüğüne bakın. |
| “Yerel doğrulama servisine ulaşılamıyor” | `sudo systemctl status tahta-kilit-verifier.service --no-pager` ve `sudo journalctl -u tahta-kilit-verifier.service -b --no-pager` komutlarını çalıştırın. Tahta oturum kullanıcısının `tahta-kilit` grubunda olduğunu doğrulayın; sonra oturumu yeniden açın. |
| QR hiç görünmüyor | Doğrulama servisi, config ve anahtar izinlerini kontrol edin. Web sitesi interneti olmasa da QR üretilir; tahta üzerindeki QR için web API'si gerekmez. |
| Telefon “QR geçersiz” diyor | QR'ın `/ac` HTTPS adresine gittiğini, `board` kimliğinin sunucu `BOARD_KEYS_JSON` içinde olduğunu ve `sig` imzası için aynı anahtarın kullanıldığını kontrol edin. |
| Öğretmen sayfası geçersiz kod diyor | Altı haneli **Öğretmen Kodu** sütununu girin; ID veya öğretmen adı kullanılmaz. Güncel QR okutun. Excel başlıklarının `ID`, `Öğretmen Adı`, `Öğretmen Kodu` olduğunu ve kodların benzersiz altı rakam olduğunu doğrulayın. |
| Web sayfası Drive listesini okuyamıyor | Yönetici panelinde “Drive'dan şimdi güncelle” sonucuna bakın. Dosyanın görüntüleme paylaşım iznini, çalışma sayfasındaki başlıkları, eksik/tekrarlı satırları ve HTTPS paylaşım adresini kontrol edin. |
| Doğru 8 hane tahtada reddediliyor | QR'ın yenilenmediğini (120 saniye), tahta/sunucu kimlik ve anahtar eşleşmesini, kodu son QR'dan aldığınızı ve nonce'ın daha önce kullanılmadığını doğrulayın. |
| Birçok yanlış koddan sonra giriş yapılamıyor | Tahtadaki bekleme süresini tamamlayın; doğru öğretmen kodunu ve güncel QR'ı yeniden kullanın. |
| Servis `systemd` olmadan çalışmıyor | WSL'de systemd ve soket izinleri Pardus ile aynı olmayabilir. WSL yalnız arayüz geliştirme testi içindir; gerçek servis davranışını ETAP cihazında doğrulayın. |

### Yönetici tanılama komutları

```sh
sudo systemctl status tahta-kilit-verifier.service --no-pager
sudo journalctl -u tahta-kilit-verifier.service -b --no-pager
systemctl --user status tahta-kilit-ui.service --no-pager
journalctl --user -u tahta-kilit-ui.service -b --no-pager
id ogretmen
ls -ld /etc/tahta-kilit /run/tahta-kilit
ls -l /etc/tahta-kilit/config.json /etc/tahta-kilit/board.key
```

`ls -l` yalnız sahiplik ve izin bilgisini gösterir; anahtar içeriğini göstermez. Öğrenci cihazında tanılama komutlarını yönetici hesabıyla çalıştırın.

## Kaldırma ve anahtar saklama

Programı kaldırmak için:

```sh
sudo apt remove tahta-kilit
```

Paket kaldırma doğrulama servisini durdurur. Güvenlik nedeniyle uygulama tarafından oluşturulan `/etc/tahta-kilit/` ayarları ve anahtar otomatik silinmez. Bu anahtarla yeniden kurulum yapılacaksa aynı Vercel eşlemesi korunmalıdır. Tahtayı kullanım dışı bırakıyorsanız önce ilgili `BOARD_KEYS_JSON` girdisini web sunucusundan iptal edin; sonra yönetici onayıyla anahtar/config yedeğini okul saklama politikasına göre silin.

Anahtarı yenilemek, web sunucusundaki anahtar eşlemesini ve tahtadaki anahtarı aynı bakım penceresinde değiştirmeyi gerektirir. Provision aracı mevcut dosyaların üzerine yazmaz. Dosyaları silerek yeniden provision etmeye çalışmayın; iki tarafta anahtarlar farklı kalırsa bütün QR'lar reddedilir.

## Geliştirme ve paket oluşturma

Paket oluşturmak için Pardus/Debian veya uyumlu bir Linux ortamında `dpkg-deb`, `sed`, `install` ve `tar` araçları bulunmalıdır. Windows üzerinde WSL Ubuntu ile depoya geçin:

```sh
cd "/mnt/c/Users/<WindowsKullanıcısı>/Desktop/Kendi Projelerim/Tübitak 2027/pardus-tahta-kilit"
sh scripts/build-deb.sh
```

Paket `dist/tahta-kilit_<debian/changelog-sürümü>_all.deb` yolunda oluşur. Sürüm `debian/changelog` dosyasının ilk satırından alınır. Kaynak ve paket dosyalarını pilot ETAP tahtasında deneyin; Windows'taki `.deb` üretimi ETAP uyumluluğunu kanıtlamaz.

Çalışma zamanı gereksinimleri Debian/Pardus paket bağımlılıklarında tanımlıdır:

- `python3`
- `python3-gi` ve `gir1.2-gtk-3.0`
- `python3-qrcode`, `python3-pil`
- `systemd`, `adduser`

## Kaynak kod haritası

- `src/tahta_kilit/lock_screen.py`: GTK kilit ekranı, QR gösterimi ve dokunmatik tuş takımı.
- `src/tahta_kilit/verifier_service.py`: root yetkili Unix soketi, nonce ve açma kodu doğrulaması.
- `src/tahta_kilit/protocol.py`: web uygulamasıyla ortak HMAC/nonce protokolü.
- `src/tahta_kilit/provision.py`: benzersiz tahta kimliği config'i ve 256 bit anahtar üretimi.
- `scripts/install-pardus.sh`: `.deb` kurulumunu ve ilk yapılandırmayı adım adım tamamlayan yönetici yardımcısı.
- `scripts/build-deb.sh`: Debian paketi üretimi.
- `debian/`: paket metaverisi, bağımlılıklar ve kurulum/kaldırma kancaları.
- `share/`: systemd servisleri, grafik oturum başlatıcısı ve XDG autostart girdisi.

## Web kodları ve veri sınırı

Web uygulaması yalnız öğretmen kodunu doğrular ve QR'a özel açma kodunu üretir. Pardus uygulaması web sitesine/OneDrive'a istek göndermez; telefon bağlantı yoksa yeni açma kodu alınmaz. Sunucu tarafı öğretmen listesi yenileme davranışı için web deposundaki README'ye bakın: [pardus-tahta-kilit-web README](https://github.com/enderkarahanli09/pardus-tahta-kilit-web/blob/main/README.md).
