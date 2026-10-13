# BB Kilit 0.1.18 — QR olmadan alternatif giriş

QR yanında **K7M4P2** gibi altı karakterlik bir istek kodu görünür. Bu yalnız örnektir; gerçek kod her istekte tahtada çevrimdışı üretilir. Telefonunuzda Google kod sitesini açın; **QR olmadan kod al** alanına tahta kimliğini ve ekrandaki istek kodunu yazın. Altıncı karakterde site altı rakamlık açma kodunu otomatik getirir. Bu rakamları tahtanın dokunmatik tuş takımından girin. İstek kodunu doğrudan tahtanın sayısal tuş takımına yazmayın. Öğretmen parolası veya Drive listesi gerekmez.

İstek kodu `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` alfabesinden rastgele seçilir; `0`, `1`, `I`, `O` kullanılmaz. Küçük harfler webde büyük harfe çevrilir. Altı karakter yaklaşık 30 bit rastgelelik sağlar; kolay yazılabilmesi için QR'daki önceki 128 bit rastgele nonce yerine kısa koddan tahtaya özel HMAC nonce türetilir. Bu bir öğretmen yetkilendirmesi değildir: QR veya güncel istek kodunu gören herkes açma kodu isteyebilir.

QR ve elle giriş **aynı altı rakamlık sonucu** verir. Her ikisi aynı 120 saniyelik isteğe bağlıdır; başarılı giriş ikisini birlikte tüketir. Yerel hatalı deneme sınırları ve Google'da tahta başına dakikada 10 istek bütçesi korunur. Google çevrimdışı tahtanın güncel isteğini bilemez; eski veya yanlış istek koduna bir sonuç üretse bile tahta yalnız mevcut isteğin sonucunu kabul eder. Altı rakamlık sonuçlar nedeniyle tesadüfi çakışma mümkündür; mutlak çakışmasızlık iddiası yoktur.

**Güncelleme:** `tahta-kilit_0.1.18_all.deb` dosyasını mevcut kurulumun üzerine kurun ve oturumu kapatıp açın. Tahta kimliği, anahtar, site adresi ve master kayıtları korunur; yeniden tahta kaydı gerekmez. Google tarafında yeni `Code.gs` ve `Index.html` dosyaları aynı deployment'a yeni sürüm olarak yayımlanmalıdır. Başka Google projesine kopyalanmış siteler kendiliğinden güncellenmez. Önceki Pardus sürümlerinin QR girişi yeni Google sürümüyle uyumludur; elle giriş için 0.1.18 gerekir. Tam ekran, oturumda otomatik açılma ve dokunmatik davranışı devam eder. Gerçek ETAP üzerinde pilot kontrol gerekir.

# BB Kilit 0.1.16 — Üç aktif ortak master kod

Panelde üç farklı 6 haneli kod belirlenir; herhangi biri tüm güncellenmiş tahtaları açar. Üç salt/hash, tek artan sürüm ve tek HMAC imzasıyla atomik güncellenir. Her kod ayrı PBKDF2-HMAC-SHA256 salt kullanır. Paket kurulumundan sonra oturumu yeniden açın. Google panelinde üç kodu güvenli yere kaydederek güncelleyin; kayıtlı tahtayı internete bağlayıp yaklaşık bir dakika bekleyin. Eski tek master kaydı yeni üçlü alınana kadar çalışır. Çevrimdışı tahtalarda son alınmış kodlar geçerlidir.

0.1.15 cihazlar uyumluluk için yalnız ilk kodu alır. Üç kodun tamamı için 0.1.16 gerekir. Kod değiştirmek açık oturumu yeniden kilitlemez. Üç farklı kod girme kontrolü tarayıcıda uygulanır; sunucu açık kodu görmez ve salt/hash kaydını doğrular. Altı rakam için önceki tahmin saldırısı sınırlamaları korunur. Gerçek ETAP üzerinde uçtan uca eşitleme henüz doğrulanmadı.

# BB Kilit 0.1.15 — Ortak master kurtarma parolası

Google yönetim sayfasında 6 haneli ortak master parola belirlenir. Parola panelde Web Crypto PBKDF2-HMAC-SHA256, 600000 yineleme ve 32 bayt rastgele salt ile türetilir; açık parola sunucuya gönderilmez/saklanmaz. Tahta master.json dosyasında yalnız doğrulama kaydı tutar (root:0600). Master parola, ortak yönetici paneli giriş parolasından ayrıdır. QR giriş kodu 6 haneli kalır.

## Kullanım

Yönetim panelinde Ortak master parola bölümünden 6 rakam belirleyip güvenli yerde saklayın ve güncelleyin. Tahtada paketi mevcut sürümün üzerine kurun. İnternete ve Google hizmetine erişen kayıtlı tahtalar yaklaşık bir dakika içinde kaydı alır. BB Kilit → Yönetici master parolası → 6 rakam → Giriş Yap. İlk eşitleme olmadan master girişi kullanılamaz; QR girişi sürer. İnternetsiz tahtalar son aldıkları parolayı kabul eder. Eski parolayı iptal etme çevrimdışı tahtaya anında ulaşmaz. Doğru master kodundan sonra mevcut kilit penceresi gizlenir; kiosk ayarları aynı kalır.

## Güncelleme güvenliği

Tahta master-sync:v1|tahtaId|128bitNonce isteğini mevcut tahta anahtarıyla HMAC-SHA256 imzalar. Sunucu yalnız kayıtlı tahta için master-response:v1|tahtaId|nonce|version|iterations|salt|hash imzalı yanıt verir. Tahta imzayı, kendi kimliğini, nonce değerini, veri boyutunu ve artan sürümü doğrular. Salt/hash Base64, 32 bayt; HTTPS sertifika doğrulaması açıktır. Yönlendirmeler yalnız script.google.com ve script.googleusercontent.com alanlarına kabul edilir. Hata halinde eski kayıt korunur. Kimlik değiştirilirse yeni kimlik adına yeniden eşitleme gerekir. İmzalı sürüm geri alma kabul edilmez.

Ayrı root tahta-kilit-master-sync.service ve timer internete erişebilir; yerel doğrulayıcı AF_UNIX sınırlamasını korur. Güncelleme servisi yalnız /etc/tahta-kilit dizinine yazabilir. Hizmet kaldırılırsa timer durdurulur. Beş yanlış master denemesinde 60 saniye bekleme vardır. Deneme sayacı doğrulayıcı belleğindedir, root servis yeniden başlatmasında sıfırlanır. Ortak parola sızarsa tüm tahtalar etkilenir. Root tarafından ele geçirilen tahta, doğrulama kaydını çevrimdışı tahmin saldırısına açabilir; 6 rakam ve pahalı türetme kullanılır. QR kimlik doğrulaması olmaması yönündeki önceki sınır değişmez.

Paket oluşturma ve Python kaynak derleme kontrolü yapılabilir; gerçek ETAP donanımı ve Google/Python eşitleme akışı için pilot doğrulama gerekir.

# BB Kilit 0.1.14 — Yönetici onayıyla tahta kimliği değiştirme

BB Kilit Kurulum artık mevcut tahta kimliğini, sistem yönetici onayıyla değiştirebilir. Anahtar korunur, yapılandırma atomik kaydedilir ve doğrulama servisi yeniden başlatılarak eski QR geçersiz hale gelir.

BILISIM-01 için: paketi üzerine kurun; BB Kilit Kurulum uygulamasında tahta kimliğini BILISIM-01 yapıp güncelleyin. Gösterilen yeni gizli JSON kaydını Google tablosundaki BB Kilit → Tahta kaydet paneline ekleyin. Kaydı ekledikten sonra BB Kilit uygulamasını yeniden açın veya oturumu kapatıp açın. Anahtar yenilenmez, mevcut diğer tahta kayıtları otomatik silinmez. Yeni kimlik Google üzerinde farklı anahtarla kayıtlıysa kayıt reddedilir; başka bir tahta kimliği kullanın. Tahta kimliği tüm tahtalar arasında benzersiz olmalıdır.

Paket yüklenmesi tek başına tüm cihazların kimliğini BILISIM-01 yapmaz; her cihazın yöneticisi kurulum ekranından seçer. Tam ekran, otomatik başlangıç ve 0.1.13 dokunmatik düzeltmesi korunur.

# BB Kilit 0.1.13 — Dokunmatik giriş düzeltmesi

0.1.12 içindeki tüm giriş cihazlarını yakalama, dokunmatik/fare olaylarını düğmelerden uzaklaştırabiliyordu. 0.1.13 yalnız klavyeyi yakalar; dokunma ve fare olayları GTK düğmelerine normal biçimde ulaşır. Tam ekran, oturum açılışında otomatik başlangıç, fiziksel klavye filtreleme ve doğru koddan sonra gizlenme korunur.

Güncellemeyi mevcut kurulumun üzerine yükleyin ve oturumu kapatıp açın veya yeniden başlatın. Eski açık sürecin yeni kodla yeniden başlaması gerekir. Anahtar ve Google kaydı korunur. Gerçek tahta dokunmatiğinde henüz doğrulanmadı.

# BB Kilit 0.1.12 — Tam ekran oturum kilidi

0.1.12, normal pencere kararını değiştirir: oturum açıldığında otomatik başlar, tam ekran ve üstte açılır, pencere kapatma düğmesi yoktur. Fiziksel klavye kilitliyken tüketilir; kod ekrandaki tuş takımından girilir. Doğru koddan sonra klavye/fare yakalama bırakılır, arayüz gizlenir ve süre dolunca geri gelmez. BB Kilit başlatıcısı tekrar kilitleyebilir. UI süreci kapanırsa kullanıcı systemd servisi yeniden başlatır.

## Güncelleme

Paketin üzerine kurun, oturumu kapatıp açın. Kayıtlı anahtar, tahta kimliği ve Google bağlantısı korunur. Paket `/etc/xdg/autostart/bb-kilit-session.desktop` kurar; grafik oturum açılışında başlatıcı çalışır. Henüz yapılandırılmamış tahtada yönetici kurulum penceresi açılır.

## Güvenlik sınırları ve yönetici kurtarma

X11 üzerinde GTK giriş yakalama masaüstü kısayollarını uygulamaya yönlendirir. Wayland compositor politikaları aynı korumayı garanti etmez. Yakalama doğrulanamazsa ekranda yönetici uyarısı gösterilir. Tek ekranlı X11 ETAP hedeflenir; çoklu ekran, sanal terminal geçişi, oturum yöneticisi, süreç öldürme, yönetici hesabı veya fiziksel erişime karşı yalnız uygulama yeterli değildir. Öğrenci oturumu yönetici olmayan kısıtlı kiosk hesabı olmalıdır. X sunucusu VT geçişi ve masaüstü kısayolları okul yöneticisi tarafından ayrıca yapılandırılmalıdır. Root yönetici SSH veya yetkili konsoldan ilgili kullanıcının `tahta-kilit-ui.service` birimini durdurabilir; normal öğrenciler için bir çıkış kısayolu eklenmemiştir.

QR kodunu gören herkes webden açma kodu alabilir. Öğretmen kimlik doğrulaması kullanıcının önceki kararıyla kaldırılmıştır; bu akış öğretmen ile öğrenciyi ayırt etmez. Bu nedenle QR akışı öğrencilere karşı yetkilendirme garantisi vermez.

Aşağıdaki önceki sürüm açıklamaları tarihsel bağlamdır; otomatik başlangıç ve tam ekran için yukarıdaki 0.1.12 davranışı geçerlidir.
# BB Kilit — Borusan Bilişim Kilit 0.1.11

## 0.1.11 üzerine güncelleme ve yeni görsel düzen

`tahta-kilit_0.1.11_all.deb` dosyasını mevcut kurulumun üzerine kurun, ardından BB Kilit uygulamasını başlatıcıdan yeniden açın. Tahta anahtarı ve Google site adresi korunur. Küçük ekranlarda içerik kaydırılabilir. Uygulama adı **BB Kilit**, açılımı **Borusan Bilişim Kilit** olarak gösterilir. Ana arayüz siyah arka plan, turuncu vurgu ve beyaz metin kullanır. QR siyah-beyaz bırakılır; kod tuş takımı koyu renk, giriş düğmesi turuncudur. Okulun Instagram profilindeki yuvarlak logosu yerel paket varlığı olarak `/usr/share/tahta-kilit/borusan-mtal-logo.jpg` konumundan yüklenir; logo için internet gerekmez. Kaynak dosya `share/assets/borusan-mtal-logo.jpg` olarak eklenir. Logo kullanıcı tarafından belirtilen https://www.instagram.com/borusanasimkocabiyikmtal/ profilinden alınmıştır; üstte ortalanır. Paket logo dosyasını içerir. Profil görseli 100×100 pikseldir ve arayüzde oranı korunarak 80×80 gösterilir. Sağ alt genişletme alanı sonraki ekleme için boş bırakılmıştır. Kurulum menüsünün görünen adı artık **BB Kilit Kurulum** olur.

## Google Apps Script ile tahta kaydı

0.1.8, `https://script.google.com/macros/s/<deployment-id>/exec` biçimindeki kod sitesi adresini destekler. **BB Kilit Kurulum** uygulamasında tahta kimliğini koruyarak site adresini değiştirip yönetici onayıyla kaydedebilirsiniz; tahta anahtarı değişmez. Kopyalanan gizli JSON kaydını özel Google tablosunda **BB Kilit → Tahta kaydet** sidebar'ına yapıştırın. İlk sürümde bu kayıt işlemi elle yapılır; public kayıt endpoint'i yoktur. Google projesi/deployment'ı önce hazırlanmalıdır; web deposundaki `google-apps-script/README.md` adımları açıklamaktadır. Yeni paketle mevcut Vercel site adresi de çalışır; Google alternatifi zorunlu değildir.

`tahta-kilit_0.1.8_all.deb` paketini üzerine kurun. Mevcut kullanıcı için yeniden anahtar üretmeyin. Site adresi değiştikten sonra BB Kilit'i başlatıcıdan yeniden açın. Tahta günlük kullanımda internetsizdir; Google tablosuna kaydı girme ve telefonun kod alması internet gerektirir.

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
2. **BB Kilit Kurulum** sihirbazını açın. Benzersiz tahta kimliği ve HTTPS site adresini girin.
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

0.1.6'daki yönetici onaylı koruma korunur. **BB Kilit Kurulum → BB Kilit kısayolunu silinmeye karşı koru** ile etkinleştirin. Linux immutable destekleyen dosya sistemlerinde silme/değiştirme/taşıma engellenir. **Kısayol korundu** mesajını görmeden etkin kabul etmeyin. Desteklenmeyen dosya sisteminde hata gösterilir.

Silmek/paketi kaldırmak/masaüstünü taşımak için önce **BB Kilit kısayolunun korumasını kaldır (yönetici)** düğmesiyle sistem yönetici onayını tamamlayın. Dosya yöneticisinin normal Sil işlemi parola penceresi yerine izin hatası gösterebilir. Bu koruma işletim sistemi yöneticisini, masaüstünün gizlenmesini veya alternatif oturumları engellemez.

## Kaynak ve paket oluşturma

Linux ortamında `sh scripts/build-deb.sh` paketi `dist/` altında oluşturur. Kaynak `src/tahta_kilit/`, paket girdileri `share/`, Debian kurulum betikleri `debian/` altındadır. `board.key` `/etc/tahta-kilit/` altında tutulur ve pakete/Git'e eklenmez. Windows WSL/WSLg arayüz geliştirmesi için kullanılabilir; gerçek Pardus kurulumu ve masaüstü entegrasyonu ayrıca doğrulanmalıdır.

0.1.11: Logonun dışındaki kare arka plan kaldırıldı; şeffaf PNG ve yuvarlak rozet kullanılır. İç beyaz alan yazıların okunması için korunur.

0.1.11: Eski Vercel adresi kayıtlı olsa bile QR doğrudan Google Apps Script kod sitesini açar. Yeni kurulumlarda Google adresi varsayılandır. Tahta kimliği ve anahtarı korunur. Güncellemeden sonra açık BB Kilit penceresini kapatıp yeniden açın.

Kullanıcının kararıyla ortak master parola 6 rakamdır: yalnız 1 milyon olası değer olduğundan ele geçirilen doğrulama kaydı çevrimdışı tahmin edilebilir. Bu seçenek yüksek güvenlikli kurtarma parolası sağlamaz. Beş yanlış girişte 60 saniye bekleme çevrimiçi/yerel denemeleri yavaşlatır, çevrimdışı hash saldırısını engellemez.


0.1.17: Master listesi 0-3 aktif kayıt destekler. Tek kod kaldırma sonrası iki kayıt veya son kod kaldırma sonrası boş liste imzalı eşitlemeyle alınır. Son kayıt kaldırıldıysa master girişi kullanılamaz, QR girişi devam eder. İnternetsiz cihazlar eski kodlarını güncelleme alana kadar kabul eder.

