# Pardus Tahta Kilit — masaüstü uygulaması

Bu klasör, ETAP akıllı tahtası için çevrimdışı çalışan kilit ekranı ve yerel kod doğrulama servisidir. Pardus/Linux için tek dosyalı kurulum biçimi `.deb` paketidir; Windows `.exe` dosyası Pardus'ta çalışmaz. Paket uygulama dosyalarını ve servis/autostart tanımlarını bir araya getirir. GTK/Python gibi sistem bağımlılıkları hedef Pardus kurulumunda bulunmalıdır.

Sürüm paketini GitHub'dan almak için [Releases sayfasını](https://github.com/enderkarahanli09/pardus-tahta-kilit/releases) kullanın. Kaynak kodu ve paketleme dosyaları bu depoda bulunur.

İlk donanım uyumluluk hedefi 64 bit Pardus ETAP 23.4'tür. Gerçek pilot tahtanın ETAP/Pardus sürümünü ve grafik oturumunu kurulum öncesinde doğrulayın.

## Kullanılan teknoloji

- Python 3
- GTK 3 / PyGObject: tam ekran dokunmatik kilit arayüzü
- python3-qrcode: QR görüntüsü üretimi
- Python standart kütüphanesi: HMAC-SHA256, Unix soketi, rastgele nonce ve JSON
- systemd: doğrulama servisi ve oturum uygulamasını yönetme
- Debian paketi (.deb): Pardus'a kurulum

## Akış

1. ETAP oturumu açıldığında kullanıcı oturumundaki GTK uygulaması başlar ve ekranı kilitler.
2. UI, root tarafından çalışan doğrulama servisine Unix soketi üzerinden challenge isteği gönderir.
3. Servis her tahta için bellekte 120 saniye geçerli 128 bit rastgele nonce tutar ve QR imzasını hesaplar. UI, yapılandırmadaki HTTPS web adresiyle QR'ı oluşturur.
4. Öğretmen telefon kamerasıyla QR'ı okutur, web sayfasına Excel listesindeki 6 haneli öğretmen kodunu girer ve sekiz haneli açma kodunu alır.
5. Kod tahtadaki dokunmatik tuş takımından girilir. UI kodu ve güncel nonce değerini yerel Unix soketine iletir.
6. Servis kodu yerel anahtarla yeniden hesaplar. Doğru ve güncel kodda UI 40 dakika gizlenir; süre bitince kilit ekranı geri gelir.

Tahta çalışma sırasında web sitesine, OneDrive'a veya internete istek göndermez. QR ve tahta tarafındaki açma kodu doğrulaması yerelde yapılır. Öğretmenin telefonu ve web API'si çevrimiçi olmalıdır; internet yoksa telefondan yeni açma kodu alınamaz ve tahta kilitli kalır. Web sunucusu ile tahta aynı tahta anahtarına sahip olmalıdır. Excel'deki öğretmen listesi Pardus uygulamasına aktarılmaz; listedeki değişiklikler Pardus paketini etkilemeden web sunucusunda geçerli olur.

## Web sunucusuyla ortak protokol

- Tahta kimliği büyük Latin harfleri, rakam ve tireden oluşur. Örnek: ETAP-01.
- Her QR için servis 16 rastgele bayt üretir ve küçük harfli 32 karakter hex nonce olarak taşır.
- QR imzası, 32 baytlık tahta anahtarıyla HMAC-SHA256 üzerinden ASCII qr:v1|tahta_kimliği|nonce mesajından hesaplanır. Sonuç padding içermeyen Base64URL biçimindedir.
- QR açma adresi; yapılandırılmış HTTPS sayfasına board, nonce ve sig sorgu parametreleri eklenerek oluşturulur. QR gizli anahtar veya okul numarası içermez.
- Açma kodu, aynı anahtarla ASCII unlock:v1|tahta_kimliği|nonce mesajının HMAC-SHA256 sonucundan türetilir. İlk 8 bayt büyük endian tam sayı olarak yorumlanır, 100.000.000'a göre kalanı alınır ve 8 basamağa sıfırla tamamlanır. Web tarafı bu yöntemin aynısını uygulamalıdır.
- Servisin yerel JSON protokolünde challenge isteği {"action":"challenge"}, kod doğrulama isteği {"action":"verify","nonce":"...","unlockCode":"KOD_BURAYA"} biçimindedir. KOD_BURAYA yalnızca şema yer tutucusudur; gerçek giriş sekiz rakamdır. Yanıtlar tek satır JSON'dur.
- Servis güncel nonce değerini bellekte 120 saniye tutar. Başarılı doğrulamada tüketir; aynı kod/nonce ikinci defa kabul edilmez.

## Dosyalar

- src/tahta_kilit/protocol.py: QR imzası, kod türetme ve imza kodlaması.
- src/tahta_kilit/verifier_service.py: root yetkili yerel doğrulama servisi.
- src/tahta_kilit/lock_screen.py: GTK kilit ekranı ve dokunmatik tuş takımı.
- src/tahta_kilit/provision.py: ilk tahta yapılandırması ve anahtar üretimi.
- debian/: kaynak paketi .deb haline getirmek için başlangıç dosyaları.
- share/: systemd ve masaüstü oturumu başlatma dosyaları.

## Pardus paketleri

Pilot ETAP cihazında önce sürümü ve oturum türünü doğrulayın. Gereken GTK/Python kitaplıklarını hedef cihazda kurmak için:

    sudo apt update
    sudo apt install python3 python3-gi gir1.2-gtk-3.0 python3-qrcode python3-pil

## Tek dosyalı kurulum paketi

Pardus/Debian ortamında, proje klasöründen tek `.deb` dosyası oluşturun:

    sh scripts/build-deb.sh

Başarılı derlemeden sonra `dist/tahta-kilit_0.1.0_all.deb` oluşur. Bu tek paketi USB ile tahtaya taşıyabilirsiniz. Paket dosyası tek olsa da Python, GTK ve QR kitaplıkları tahtada kurulu olmalı veya kurulum sırasında erişilebilir bir Pardus paket deposundan yüklenmelidir. Kurulum tamamen çevrimdışı yapılacaksa bağımlılıkları da önceden hazırlayın.

Kaynak kodunu kurulumdan önce denemek için proje klasöründen şu komutu kullanın. Geçerli config, tahta anahtarı ve doğrulama servisi önceden hazırlanmış olmalıdır:

    PYTHONPATH=src python3 -m tahta_kilit.lock_screen

### Windows bilgisayarda arayüz testi

Uygulama Windows üzerinde yerel olarak değil, Linux ortamında çalışır. Windows 11 veya WSLg destekli Windows 10 üzerinde WSL 2 / Ubuntu ile GTK arayüzü açılabilir. WSLg tek başına tam bir Pardus masaüstü sağlamaz; sistem kısayolları ve kiosk davranışını doğrulamak için Pardus sanal makinesi veya ETAP cihazı kullanın.

Arayüz tuş denemeleri için yalnız test sürecinde şu ortam değişkenini verin:

    TAHTA_KILIT_TEST_MODE=1 PYTHONPATH=src python3 -m tahta_kilit.lock_screen

Pencere odaktayken `Alt+F1` yalnızca bu test sürecini kapatır. Normal Pardus çalıştırmasında bu kısayol etkin değildir ve kilit ekranı fiziksel tuşları yutmaya devam eder. Test modu da config dosyasını ve çalışan yerel doğrulama servisini gerektirir.

Oluşan paketi ETAP tahtasına aktarın. Aşağıdaki ETAP-01 ve alan adı örnektir:

    sudo apt install ./dist/tahta-kilit_0.1.0_all.deb
    sudo python3 -m tahta_kilit.provision --board-id ETAP-01 --site-url https://kilit.example/ac

Kurulum aracı /etc/tahta-kilit/board.key dosyasını bir kez oluşturur; var olan anahtarı asla ezmez. Sunucu ortam değişkenine koymak için anahtarın Base64 gösterimi yetkili yönetici tarafından güvenli bir kanaldan alınmalıdır:

    sudo base64 -w 0 /etc/tahta-kilit/board.key

Bu komutun çıktısı gizli anahtardır. Sohbete, ekran görüntüsüne, komut geçmişine veya Git deposuna koymayın. Üretim web sunucusundaki `BOARD_KEYS_JSON` eşlemesine ekleyin. Web sunucusunda ayrıca öğretmen kodlarının tutulduğu Excel dosyasının kişisel OneDrive görüntüleme bağlantısı `ONEDRIVE_WORKBOOK_URL` sunucu ortam değişkeninde bulunur. Bu iki web ayarı tahtaya yüklenmez; öğrenci oturumuna gösterilmez. OneDrive bağlantısı herkesin görüntüleyebileceği paylaşım bağlantısı olduğundan, bağlantıyı bilen kişiler Excel içeriğini okuyabilir. Öğretmen kodlarını değiştirmeniz `.deb` paketini yeniden kurmanızı gerektirmez.

`provision` aracı yapılandırmayı kaydettikten sonra doğrulama servisini etkinleştirip başlatmayı dener. Başlatamazsa şu komutla yönetici elle başlatabilir:

    sudo systemctl enable --now tahta-kilit-verifier.service

ETAP'ta kilit ekranını çalıştıracak standart kullanıcıyı Unix soket grubuna ekleyin; ogretmen yerine tahtadaki gerçek oturum kullanıcı adını yazın:

    sudo usermod -aG tahta-kilit ogretmen

Kullanıcının oturumunu kapatıp yeniden açın. Paket, grafik oturum açıldığında kilit ekranını başlatan XDG autostart girdisini ve çökme sonrası yeniden başlatan systemd kullanıcı servisini kurar. Pilot ETAP oturumunda açılış davranışını doğrulayın.

### Öğrenci oturumunu kısıtlama

Uygulama tek başına işletim sistemi kiosk kilidi değildir. Dağıtımda şu cihaz politikaları da uygulanmalıdır:

- Öğrenci/tahta oturumu standart kullanıcı olsun; `sudo` veya yönetici parolası verilmesin.
- ETAP masaüstünde terminal, uygulama çalıştırma penceresi, dosya yöneticisi ve sistem ayarları öğrenci oturumundan kaldırılıp/kısıtlansın.
- Alt+Tab, Alt+F4, Ctrl+Alt+F tuşları, sanal terminaller (Ctrl+Alt+F1…F6), oturumu kapatma, güç/uyku menüsü ve ekran kilidi davranışı pilot tahtada tek tek doğrulansın ve ETAP politikalarıyla kısıtlansın. GTK tam ekran penceresi bu kısayolları tek başına kapatmaz.
- UEFI/BIOS yönetici parolası ayarlansın; harici USB'den başlatma ve önyükleme sırası yönetici tarafından korunsun.
- Kodda `TAHTA_KILIT_TEST_MODE=1` yalnız WSL/test için kullanılır. Üretim oturumunda bu değişken tanımlanmamalıdır; bu mod Alt+F1 ile uygulamadan çıkışa izin verir.

Kaynak Python dosyaları sistem dizininde okunabilir olabilir; bunları derlemek yalnızca incelemeyi zorlaştırır. Güvenlik sınırı kaynak kodunu saklamak değil, tahta anahtarını root'a özel tutmak, öğrenciye yönetici yetkisi vermemek ve oturumu işletim sistemi düzeyinde kısıtlamaktır. Yönetici/root hesabı uygulamayı kaldırabilir; bu hesap öğrenciye verilmemelidir.

### Etablo / OneDrive bağlantısının sınırı

Etablo öğretmen kod listesinin web sunucusunca okunması içindir. Pardus uygulaması Excel'i indirmez, öğretmen adını/kodunu saklamaz ve OneDrive adresini bilmez. Tahta her QR'da rastgele nonce üretip imzalar; web sunucusu öğretmen kodunu kontrol ederek açma kodunu verir; tahta bu kodu kendi anahtarıyla internet olmadan doğrular. Bu nedenle Etablo/OneDrive'ın yanıt vermemesi yalnızca yeni öğretmen kodu kontrolünü ve telefondan açma kodu almayı etkiler. Mevcut kilit ekranı, QR üretimi ve yerel doğrulama çalışır; geçerli web kodu alınamazsa tahta açılmaz.

## Güvenlik ve sınırlar

- Anahtar UI sürecine verilmez. UI yalnızca /run/tahta-kilit/verifier.sock üzerinden istek gönderir.
- Anahtar /etc/tahta-kilit/board.key altında root tarafından okunur; doğrulama servisi root olarak çalışır. Anahtarın yedeği ve web sunucusuna aktarımı okul yöneticisinin sorumluluğundadır.
- Soket root:tahta-kilit, 0660; çalışma dizini root:tahta-kilit, 0750 olacak şekilde sınırlandırılır.
- Kilit ekranı fiziksel klavyeden kod kabul etmez. GTK penceresinin tam ekran olması tek başına kiosk güvenliği değildir. ETAP'ta öğrenciye yönetici olmayan kısıtlı oturum, uygulama başlatma politikası ve sistem kısayolu/TTY geçiş ayarları ayrıca uygulanmalıdır.
- Bu yazılım BIOS, harici diskten başlatma, yönetici hesabı, fiziksel güç düğmesi veya işletim sistemi açıklarını engellemez.
- systemd uygulama çökerse yeniden başlatır; yeniden başlatılan UI her zaman kilitli açılır. Kod girilerek açılmış 40 dakikalık süre yeniden başlatma sonrasında devam etmez.
- Web uygulaması ortak okul numarasını öğretmen hesabı olmadan kullanır. Bu numarayı bilen biri geçerli QR için kod isteyebilir; numara sızarsa yönetici sunucu gizlisini değiştirmelidir.

## İlk prototipte tamamlanmamış işler

- Kilitli ETAP oturumunda Alt+Tab, Alt+F4, Ctrl+Alt+F tuşları, sistem menüsü, sanal terminaller ve güç/uyku davranışı cihaz üzerinde doğrulanmalıdır. Uygulama içindeki tuş olaylarını yutmak, işletim sistemi kısayollarını tek başına engellemez.
- `.deb` henüz bu geliştirme ortamında derlenip pilot ETAP üzerinde doğrulanmadı. Kaynaklar Windows çalışma alanında hazırlanmıştır; hedef Pardus sürümünde paket derlenip kiosk kısıtları gerçek tahtada denenmelidir.
- Sonraki adım: Web API sözleşmesiyle ortak Python/Node test vektörlerini tanımlamak ve ETAP pilotunda kabul testlerini uygulamak.
