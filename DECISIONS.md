# RenTR Kalıcı Kararlar

## ADR-001 — Tek repo ve tek çekirdek

**Durum:** Kabul edildi

**Tarih:** 20 Ağustos 2026

CLI ve ilerideki PySide6 arayüzü aynı uygulama servislerini ve alan modelini
kullanacaktır. İş mantığı kullanıcı arayüzüne gömülmeyecektir.

## ADR-002 — Python 3.12 ve uv

**Durum:** Kabul edildi; temiz Windows doğrulaması bekleniyor

**Tarih:** 20 Ağustos 2026

Başlangıç çalışma zamanı Python 3.12'dir. Bağımlılık ve sanal ortam yönetimi uv,
`pyproject.toml` ve `uv.lock` ile yapılacaktır.

## ADR-003 — Temiz oda geliştirme

**Durum:** Kabul edildi

**Tarih:** 20 Ağustos 2026

Rakip projelerin davranış ve ürün fikirleri incelenebilir; kaynak kodları lisans
incelemesi olmadan kopyalanmayacaktır. RenTR çekirdeği kendi fixture, test ve
uygulamamızla geliştirilecektir.

## ADR-004 — İlk giriş yalnızca resmî tl şablonları

**Durum:** ADR-008 tarafından geçersiz kılındı

**Tarih:** 20 Ağustos 2026

İlk teknik parser dilimi Ren'Py tarafından üretilmiş çeviri şablonları üzerinde
kanıtlanmıştır. Ancak bu dosyaların kullanıcıdan hazır beklenmesi ürünün gerçek
amacıyla çeliştiği için giriş kararı ADR-008 ile değiştirilmiştir.

## ADR-005 — Güvenli hata yaklaşımı

**Durum:** Kabul edildi

**Tarih:** 20 Ağustos 2026

Desteklenmeyen veya doğrulanamayan yapı sessizce atlanmayacak ve dosyaya
yazılmayacaktır. Açık hata, dry-run, ayrı çıktı ve atomik yazma temel ilkedir.

## ADR-006 — İlk parser diyalog ve arayüz metnini birlikte çıkarır

**Durum:** Ziyaattin tarafından A seçeneğiyle kabul edildi

**Tarih:** 20 Ağustos 2026

İlk parser dilimi hem yorum satırındaki kaynak diyalogu hem `old` kaynak arayüz
metnini çeviri birimi sayacaktır. Boş hedef diyalog ve `new ""` satırları birim
sayılmayacaktır. Konuşmacı, label, dosya ve satır bilgileri korunacaktır.

## ADR-007 — Mevcut insan çevirisi korunur ve envanterlenir

**Durum:** Ziyaattin tarafından A seçeneğiyle kabul edildi

**Tarih:** 20 Ağustos 2026

Dolu hedef metin yok sayılmayacak ve yeniden çevrilecek iş kuyruğuna da
alınmayacaktır. Kaynağıyla birlikte `translated` durumunda envanterlenecek;
mevcut Türkçe metin `translated_text` olarak korunacaktır. Kaynak kimliği hedef
çeviriden bağımsız kalacaktır.

## ADR-008 — Kullanıcı oyun kökünü seçer; tl/turkish çıktıdır

**Durum:** Ziyaattin'in düzeltmesiyle kabul edildi

**Tarih:** 20 Ağustos 2026

Normal giriş mevcut bir `game/tl/turkish` klasörü değildir. Kullanıcı indirilen
veya kaynaklarına erişebildiği Ren'Py oyununun ana klasörünü seçer. RenTR oyun
yapısını salt okunur inceler: `.rpy` varsa resmî çeviri şablonu üretme yoluna,
yalnız `.rpyc/.rpa` varsa izole paket çıkarma yoluna gider. `tl/turkish` ilk
başarılı üretimin çıktısıdır; mevcutsa yalnız devam/güncelleme modu sayılır.

## ADR-009 — Paketli oyun modu nihai ürünün çekirdek hedefidir

**Durum:** Kabul edildi; uyumluluk kanıtı bekleniyor

**Tarih:** 20 Ağustos 2026

Hedeflediğimiz indirilen Ren'Py oyunlarında kaynak `.rpy` veya Türkçe `tl`
klasörü bulunmayabileceği için `.rpa/.rpyc` tespiti ve izinli kullanımda izole
çıkarma nihai kullanıcı ürününün gerekli parçasıdır. Uyumluluk sürüme göre
değiştiğinden önce yalnız tespit yapılacak; çıkarma/decompile gerçek oyun
klasöründe değil ayrı çalışma kopyasında geliştirilecektir.

## ADR-010 — İzole ve seçici çalışma alanı

**Durum:** Ziyaattin tarafından A seçeneğiyle kabul edildi

**Tarih:** 21 Ağustos 2026

Tarama, çıkarma, decompile ve çeviri hazırlığı sırasında orijinal oyun klasörüne
yazılmayacaktır. Yalnız gerekli `.rpy`, `.rpyc`, `.rpa` ve mevcut çeviri
dosyaları ayrı çalışma alanına alınacaktır; görsel, ses ve diğer büyük varlıklar
varsayılan kopyaya dahil edilmeyecektir. Önce dry-run ve disk alanı kontrolü
yapılacak, kopya `.partial` klasöründe hazırlanacak ve ancak tamamlanınca atomik
olarak yayımlanacaktır. Hata durumunda yarım kopya temizlenecektir. Doğrulanmış
Türkçe çıktı ileride ayrı yedek ve kullanıcı onayı kapısından sonra uygulanır.

## ADR-011 — Resmî Ren'Py komutu önce yalnız dry-run planlanır

**Durum:** Kabul edildi

**Tarih:** 21 Ağustos 2026

Kaynak oyunun şablon üretim komutu yalnız izole çalışma alanını hedefleyen bir
argüman listesi olarak oluşturulacaktır. Shell komut metni üretilmeyecek;
subprocess, oyun kodu çalıştırma ve dosya yazma bu dilimde etkin olmayacaktır.
Windows'ta SDK içindeki Python başlatıcısı ile `renpy.py`, POSIX sistemlerde
`renpy.sh` dosya düzeni doğrulanır. Gerçek çalıştırma ayrı test ve güvenlik
kapısından sonra ele alınır.

## ADR-012 — Bölünmüş hedef çeviri segmentleri kayıpsız korunur

**Durum:** Kabul edildi

**Tarih:** 21 Ağustos 2026

Ren'Py bir kaynak diyaloğun çeviride birden fazla `say` satırına bölünmesine
izin verir. RenTR bu satırları tek bir hedefe indirgemeyecek;
`translated_segments` içinde sıralı olarak koruyacaktır. Arayüz ve arama için
`translated_text`, segmentlerin yeni satırla birleştirilmiş görünümüdür ve iki
alanın tutarsız olmasına izin verilmez. Böylece mevcut insan çevirisinin yapısı
gelecekteki güvenli yazıcıya aktarılabilir.

## ADR-013 — Renderer kanonik ve semantik olarak kayıpsızdır

**Durum:** Kabul edildi

**Tarih:** 21 Ağustos 2026

Desteklenen parser alt kümesinde renderer özgün tırnak stilini byte-byte
kopyalamak yerine tek bir çift tırnaklı Ren'Py biçimi üretir. Birim kimliği,
kaynak, konuşmacı, label, hedef segment sırası ve kaynak özeti yeniden parse
edildiğinde aynı kalmalıdır. Geçersiz veya yeniden üretimde veri kaybettirecek
kimlik/segment yapısı açık hatayla reddedilir. Mevcut CLI yalnız standart
çıktıya dry-run önizlemesi verir; dosyaya yazma Safe Writer fazına bırakılır.

## ADR-014 — Sağlayıcıdan önce Ren'Py kontrol sözdizimi korunur

**Durum:** Kabul edildi

**Tarih:** 21 Ağustos 2026

Text tag, interpolasyon, eski `%` biçimi ve kaçışlar deterministik sıralı
placeholder'lara çevrilmeden hiçbir sağlayıcıya gönderilmeyecektir. Sağlayıcı
her placeholder'ı tam bir kez ve aynı sırada döndürmezse hedef belleğe veya
dosyaya yazılmaz.

## ADR-015 — Çeviri belleği cache-first ve insan kilidine saygılıdır

**Durum:** Kabul edildi

**Tarih:** 21 Ağustos 2026

Tam eşleşme `unit_id + source_hash` ile yapılır. Benzer metinler otomatik hedef
değil, yalnız inceleme bağlamıdır. İnsan tarafından kilitlenen hedefler sağlayıcı
sonucu tarafından değiştirilemez. Bellek kullanıcının yerel SQLite dosyasındadır.

## ADR-016 — Güvenli çıktı önkoşul, yedek ve atomik yazma gerektirir

**Durum:** Kabul edildi

**Tarih:** 21 Ağustos 2026

Safe Writer yalnız izole çalışma alanının içine yazabilir. Dry-run sonrasında
dosya değiştiyse işlem reddedilir. Üzerine yazma öncesinde yedek alınır; çıktı
aynı dizindeki kısmi dosyadan atomik yayımlanır. Sonradan değiştirilmiş RenTR
çıktısında otomatik geri alma dış değişikliği ezmemek için reddedilir.

## ADR-017 — Resmî SDK yalnız hazırlanmış izole kopyada çalıştırılır

**Durum:** Kabul edildi

**Tarih:** 21 Ağustos 2026

`translation-plan` salt okunur kalır. Ayrı `prepare-translation` komutu seçici
çalışma alanını atomik hazırladıktan sonra doğrulanmış argüman listesini
`shell=False` ile çalıştırabilir. Başarı, `game/tl/<language>` altında gerçekten
`.rpy` şablonu oluşmadan kabul edilmez; orijinal oyun yolu hiçbir zaman hedef
değildir.

## ADR-018 — Gizli sağlayıcı anahtarları proje dosyasında tutulmaz

**Durum:** Kabul edildi

**Tarih:** 21 Ağustos 2026

`rentr.toml` sağlayıcı türü, model, taban URL ve yalnız ortam değişkeninin adını
tutar. `api_key`, `secret`, `token` veya `password` biçimli düz metin alanlar
fail-closed reddedilir. Kontrol çıktısı anahtarın yalnız mevcut olup olmadığını
gösterir; değeri log veya JSON çıktısına koymaz.

## ADR-019 — Benzerlik ve risk otomatik onay değildir

**Durum:** Kabul edildi

**Tarih:** 21 Ağustos 2026

Benzer çeviri, sözlük uyuşmazlığı, uzunluk oranı, kontrol sözdizimi ve bilinmeyen
karakter sinyalleri açıklanabilir inceleme kuyruğu üretir. Bu puanlar çeviriyi
otomatik onaylamaz veya kilitlemez; insan düzeltmesi ayrı ve kalıcı bir işlemdir.

## ADR-020 — Yerel ve haricî sağlayıcı aynı güvenlik hattını kullanır

**Durum:** Kabul edildi

**Tarih:** 21 Ağustos 2026

Ollama adaptörü API anahtarı istemez ancak token koruma, cache, retry, sözlük,
karakter bağlamı ve Safe Writer kurallarını atlayamaz. Hızlı/dengeli/yüksek
profil yalnız model çalışma seçeneklerini değiştirir; yazma doğrulamasını
gevşetmez.

## ADR-021 — Masaüstü ilk beta Qt Widgets ve tek ekran kullanır

**Durum:** Kabul edildi

**Tarih:** 21 Ağustos 2026

İlk beta QML yerine daha küçük riskli Qt Widgets kabuğuyla ilerler. Kullanıcının
farklı sayfalarda kaybolmama tercihi nedeniyle oyun seçimi, durum, sağlayıcı,
ilerleme, önizleme ve inceleme aynı ana pencerede kalır. İş mantığı Qt sınıfları
içine taşınmaz; ortak controller/workflow ve çekirdek servisler kullanılır.

## ADR-022 — Paketli script edinimi statik, sınırlı ve fail-closed olur

**Durum:** Kabul edildi

**Tarih:** 21 Ağustos 2026

İlk temiz oda uyumluluk katmanı yalnız standart RPA-3.0 arşivlerini destekler.
RPA indeksindeki pickle, genel Python sınıflarını çalıştıramayan kısıtlı
okuyucuyla yalnız container/primitif veri olarak açılır. Yalnız Ren'Py script
uzantıları izole çalışma alanına çıkarılır. RPYC dosyalarında yalnız container
başlığı ve bölüm sınırları doğrulanır; RenTR RPYC pickle içeriğini yüklemez veya
oyun AST'sini kendi sürecinde çalıştırmaz. Desteklenmeyen biçim sessiz atlanmaz.

## ADR-023 — SDK yürütmesi sırları miras almaz fakat tam sandbox sayılmaz

**Durum:** Kabul edildi; dış kabul bekleniyor

**Tarih:** 21 Ağustos 2026

Resmî Ren'Py SDK alt süreci yalnız hazırlanmış izole kopyayı hedefler ve API
anahtarları dahil çağıran sürecin genel ortamını miras almaz. `PATH`, Windows
çalışma zamanı değişkenleri ve izole HOME/temp yollarından oluşan dar bir ortam
kullanılır. Buna rağmen Windows/POSIX işletim sistemi seviyesinde ayrı güvenlik
alanı kurulmadığı için bu davranış “tam sandbox” diye sunulmayacak; yalnız
güvenilen resmî SDK ile çalıştırılacaktır.

## ADR-024 — Gerçek oyun kurulumu manifestli paket ve ayrı onay gerektirir

**Durum:** Kabul edildi

**Tarih:** 21 Ağustos 2026

Çeviri motoru önce yalnız izole çalışma alanına yazar. Gerçek oyuna aktarım;
sürümlü manifest, SHA-256 özetleri ve sınırlandırılmış yollar taşıyan ayrı bir
ZIP paketinden yapılır. CLI varsayılan olarak yalnız plan gösterir; masaüstü
arayüzü de dosya sayısını ve çakışmaları gösteren ayrı bir onay ister. Mevcut
dosyalar yedeklenir, kurulum kaydı tutulur ve rollback yalnız kurulan byte'lar
sonradan değişmemişse uygulanır. Dil yardımcı scripti Ren'Py'nin belgelenmiş
`config.default_language = "turkish"` ayarını kullanır ve aynı kayıttan
kaldırılabilir.

## ADR-025 — Runtime araştırması statik hattı değiştirmez; hook reddedilir

**Durum:** Kabul edildi

**Tarih:** 21 Ağustos 2026

Canlı çeviri ana V1 hattına dahil değildir. Statik paket bağlam, kalite
incelemesi, cache, lint ve geri alma sunduğu için önerilen yöntem olarak kalır.
Ren'Py'nin kullanıcı tarafından açılan clipboard erişilebilirlik modu ile açık
izinli OCR overlay yalnız ayrı araştırma adaylarıdır. Süreç hook'u/enjeksiyonu;
sürüm, çökme, antivirüs ve bütünlük riski nedeniyle reddedilir. Faz 5
simülatörü yalnız kullanıcı tarafından verilen metni işler; clipboard okumaz,
ekran yakalamaz, oyunu başlatmaz ve dosyaya yazmaz.

## ADR-026 — Deterministik kalite bozulmaları cache öncesi fail-closed reddedilir

**Durum:** Kabul edildi

**Tarih:** 23 Ağustos 2026

Gerçek Our Red String pilotları model çıktısının tokenları silmeden de Ren'Py davranışını
bozabildiğini ve bazı küçük modellerin Türkçe çıktıya başka yazı sistemleri karıştırabildiğini
gösterdi. Bu nedenle kaynak başı/sonuna bağlı kontrol tokenları ile kaynakta bitişik token
kümeleri yapısal konumunu korumalıdır. Bağlam prompt metadatası ve kaynakta bulunmayan
CJK/Cyrillic/benzeri beklenmeyen yazı sistemi karakterleri de otomatik reddedilir. Bu kapı
edebî/doğallık puanı vermez; yalnız deterministik bozulmayı engeller ve reddedilen çıktı
translation memory'ye yazılmaz.


## ADR-027 — TranslateGemma modelleri bağlamsız, kendi resmî prompt profiliyle denenir

**Durum:** Deneysel kabul

**Tarih:** 23 Ağustos 2026

Aya Expanse 8B'nin 100 satırlık ORS pilotu teknik olarak 90/100 çıktı üretse de özellikle
context-sensitive grupta anlam ve argo hataları gösterdi. TranslateGemma ayrı sistem promptu,
JSON şeması veya standart LLM bağlam talimatı bekleyen genel bir sohbet modeli gibi
kullanılmayacaktır. Model adı `translategemma` içerdiğinde RenTR tek user mesajlı resmî
English (en) -> Turkish (tr) çeviri promptuna geçer; önceki/sonraki sahne bağlamı bu adaptöre
verilmez. Amaç aynı temsilî pilot üzerinde doğrudan çeviri kalitesini ayrı bir baseline olarak
ölçmektir. Sonuç yeterli değilse sonraki aday hibrit draft + context-aware post-edit hattıdır.

## ADR-028 — Yüksek riskli ilk çeviri bağlamlı semantic repair'den geçer

**Durum:** Deneysel kabul

**Tarih:** 24 Ağustos 2026

100 satırlık ORS karşılaştırmasında TranslateGemma 12B, Aya 8B'ye göre İngilizce
anlamı daha istikrarlı çözmesine rağmen diyalogu resmileştirme, explicit dili
yumuşatma ve bazı Ren'Py tokenlarını bozma eğilimi gösterdi. Aya ise bağlamlı
promptu kullanabilmesine rağmen sıfırdan çeviride daha fazla semantik hata yaptı.
Bu nedenle tek model seçmek yerine ilk aday ile post-edit görevi ayrılır.

RenTR ilk çeviriyi deterministik `TranslationRiskAnalyzer` ile değerlendirir.
Explicit/argo, deyimsel kaynak, beklenmeyen `siz` hitabı, çoklu alternatif çıktı,
`hot -> sıcak`, `sex -> cinsiyet`, `cum` anlam kaybı ve explicit `fuck/slut`
yumuşatması gibi açıklanabilir sinyaller ikinci geçişe yönlendirilir. İlk aday
teknik QC'de token bozmuşsa da repair modeli kaynak placeholder sözleşmesini
yeniden kurmayı deneyebilir. Repair sonrası normal Ren'Py QC tekrar çalışır;
yüksek güvenli semantik hata sinyali devam ederse çıktı cache'e alınmaz.

Translation memory yalnız doğrudan temiz ilk adayı veya repair + QC sonrasında
kabul edilmiş final metni saklar. Riskli base aday, repair başarısızsa sessizce
fallback edilmez; insan incelemesine kalacak şekilde fail-closed sonuç üretilir.

## ADR-029 — Repair adayı base'i yalnız candidate selector onayıyla geçebilir

**Durum:** Deneysel kabul

**Tarih:** 24 Ağustos 2026

İlk 10 satırlık TranslateGemma → Aya hibrit pilotu, semantic repair'in teknik
olarak çalışmasına rağmen iyi bir base çeviriyi daha kötü Türkçeyle değiştirebildiğini
gösterdi. Bu nedenle iki aday da teknik ve yüksek güvenli hard-risk kapılarını
geçtiğinde repair sonucu artık otomatik final sayılmaz.

RenTR `CandidateJudgeProvider` üzerinden BASE, REPAIR veya REJECT kararı alır.
Judge yeni bir çeviri yazamaz; kaynak anlamı, eksik/fazla bilgi, doğal Türkçe,
hitap/register, argo-küfür ve explicit yoğunluğu bakımından yalnız iki adayı
karşılaştırır. REPAIR kararının base'i değiştirebilmesi için en az 0.72 güven
gerekir; düşük güven repair kararı conservative BASE fallback olur. İki adayın
da kötü olduğuna dair REJECT kararı 0.75+ güvenle fail-closed sonuç üretir.

İlk aday teknik olarak geçersizse veya deterministik hard semantic risk taşıyorsa
selector onu güvenli aday gibi kabul etmez. Soft-risk repair veya judge hatasında
ise geçerli base korunabilir; bu davranış translation memory'ye rastgele repair
bozulması yazılmasını engeller. `pilot-translate --judge-model` ayrı bir Ollama
hakemi seçebilir; belirtilmezse repair modeli hakem olarak yeniden kullanılır.

## ADR-030 — Explicit kaynak doğrudan korunur; boundary control salvage yalnız deterministikse yapılır

**Durum:** Deneysel kabul

**Tarih:** 24 Ağustos 2026

Hybrid v2 100 ORS benchmarkı, pairwise selector'ın birçok semantik hatayı doğru seçmesine
rağmen iki ayrı kalite açığı gösterdi. Birincisi, modeller kaynak açıkça cinsel/argo olduğunda
bazen tonu yumuşattı veya pseudo-Türkçe biçimler üretti. İkincisi, mutlak satır başı/sonu
image/style tokenları gibi hedef konumu semantik hizalama gerektirmeyen kontroller bile model
çıktısından düşebildi.

Bu nedenle repair/judge hattına kaynak-özel semantic guardrails verilir. Guardrail sabit bir
Türkçe çeviri dayatmaz; `fuck`, `cum`, `sex`, `anal sex`, `slut`, `pussy`, `cock/dick`,
sexual `hot` ve benzeri kaynak öğelerde korunması gereken anlam/yoğunluğu tarif eder. Judge,
kaynak explicit olduğunda doğrudan explicit Türkçeyi sırf doğrudan olduğu için reddedemez.
İngilizce explicit slang'in uydurma `püs`, `pussy-mi` benzeri biçimlere transliterasyonu
kalite hatasıdır.

Token tarafında yalnız `TEXT_TAG` türündeki ve kaynakta mutlak prefix/suffix konumu olan,
çıktıda tamamen eksik kontroller deterministik olarak yeniden eklenebilir. Veri taşıyan
interpolation/printf/escape tokenları, internal kontroller, çıktıda mevcut ama taşınmış
kontroller ve bitişik tokenların arasına model metni eklenmiş durumlar otomatik düzeltilmez;
önceki fail-closed güvenlik sınırı korunur.
