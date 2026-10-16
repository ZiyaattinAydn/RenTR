# Değişiklik Günlüğü

## [Unreleased]

### Eklendi

- Sprint 0 Python/uv proje iskeleti
- `TranslationUnit` alan modeli ve kaynak özeti
- `rentr doctor` komutu
- Test, lint ve typecheck doğrulama kapısı
- Proje durumu ve kalıcı karar kayıtları
- A kararına göre diyalog ve `old/new` string kaynaklarını çıkaran ilk parser
- JSON envanter üreten `rentr inventory` komutu
- Mevcut Türkçe hedefi koruyan `translated_text` ve `translated` durum tespiti
- Oyun kökünü `source`, `packaged` ve `resume` modlarına ayıran `inspect-game`
- Seçici dosya planı, disk kontrolü, atomik kopya ve hata temizliği sağlayan
  izole çalışma alanı katmanı
- Windows ve POSIX resmî Ren'Py SDK düzenlerini doğrulayan keşif katmanı
- Shell veya subprocess kullanmadan `translate turkish` argümanlarını üreten
  `rentr translation-plan` dry-run komutu
- Anlatıcı, tek/çift/backtick metinleri ve Ren'Py'ye özgü kaçışları güvenle
  okuyan özel literal parser'ı
- `voice` ifadelerini diyalogdan ayıran blok taraması
- Bir kaynak satırın birden fazla hedef `say` satırına bölündüğü çeviriler için
  `translated_segments` alanı ve tutarlılık denetimi
- Alan modelini sabit çift tırnaklı Ren'Py sözdizimine dönüştüren deterministik
  renderer ve salt okunur `rentr render-template` önizlemesi
- İlk, mevcut çeviri ve parser edge fixture'larında semantik
  parse → render → parse golden kapısı
- Ren'Py kontrol sözdizimi için token koruma ve kapalı geri yükleme
- Yerel SQLite çeviri belleği, insan kilidi ve benzerlik adayları
- Mock/OpenAI uyumlu sağlayıcılar ve yarıda kalınca devam edebilir çeviri motoru
- İzole diff, atomik yazma, yedek ve güvenli geri alma katmanı
- İzole resmî SDK şablon üretimi, iş tahmini ve uçtan uca CLI çeviri akışı
- Sürümlü sözlük, karakter sesi/hitap kartları ve risk puanlı inceleme kuyruğu
- Gizli anahtarsız TOML proje yapılandırması ve yerel güvenli audit günlüğü
- Çeviri geçmişi/geri alma ve oyun güncelleme envanter karşılaştırması
- Örnek proje varlıkları, Windows tek dosya paketleme planı ve kullanıcı kabul kılavuzu
- Üç bağımsız özgün fixture için tam semantik çeviri matrisi
- Yerel Ollama adaptörü, kalite profilleri ve donanım/model uygunluk raporu
- Tek ekranlı PySide6 masaüstü beta workflow'u ve pyside6-deploy Windows planı
- Standart RPA-3.0 için kısıtlı indeks okuyucu ve yalnız script çıkarımı
- Pickle yüklemeyen RPYC2 container ön kontrolü ve Ren'Py 6/7/8 nesil tespiti
- Paketli oyunu izole alanda resmî SDK şablon üretimine bağlayan workflow
- SDK alt süreci için API anahtarlarını miras almayan daraltılmış ortam
- Bütün Türkçe şablonları tek masaüstü işinde çevirip atomik uygulama
- Manifest/SHA-256 doğrulamalı deterministik Türkçe mod ZIP'i
- Dry-run gerçek oyun kurulumu, çakışma yedeği, kurulum kaydı ve korumalı rollback
- Tek ekranda ayrıca onaylanan “Oyuna Kur” ve “Son Kurulumu Geri Al” akışı
- Ren'Py 7 ve 8 paketli fixture matrisi
- Statik/clipboard/OCR/hook seçeneklerini salt okunur değerlendiren runtime raporu
- Ekran yakalamayan, hook yapmayan ve tekrarları bellekte tutan metin akışı simülatörü
- Runtime yaklaşım kararları ve gelecekteki OCR için ölçülebilir araştırma kapıları
- Wheel için `desktop` opsiyonel bağımlılığı ve Linux/Windows GitHub Actions kapısı
- Gerçek oyun ön testi için sağlayıcı bağlamına aynı sahnedeki önceki ve sonraki
  kaynak satırı eklendi; Ollama artık sahne etiketi, benzer çeviri, karakter notu ve
  sözlük bağlamını gerçekten prompt'a taşır ve deyim/argo/explicit tonu korumayı ister.
- Paketli oyun hazırlığında media-only RPA arşivleri çalışma alanına kopyalanmadan
  önce statik indeksle elenir; yalnız script taşıyan arşivler izole alana alınır.
- Gerçek oyun Phase 2.3 kalite kapısı: başlangıç/bitiş kontrol tokenları ve kaynakta
  bitişik Ren'Py token kümeleri yerinden oynatılamaz; bağlam metadatası veya kaynakta
  bulunmayan CJK/Cyrillic/benzeri yazı sistemi karakterleri fail-closed reddedilir ve
  çeviri belleğine kaydedilmez.

### Karar

- Ziyaattin'in A seçimi: diyalog ve arayüz kaynakları birlikte çıkarılır; boş
  hedef alanları çeviri birimi sayılmaz.
- Ziyaattin'in ikinci A seçimi: dolu hedefler envanterlenir, korunur ve yeniden
  çeviri kuyruğuna alınmaz.
- Ziyaattin'in ürün düzeltmesi: `tl/turkish` giriş şartı değil, RenTR'nin
  üreteceği çıktı ve sonraki çalıştırmalarda devam noktasıdır.
- Ziyaattin'in A seçimi: orijinal oyuna yazmadan yalnız gerekli dosyaları alan
  izole ve seçici çalışma alanı kullanılır.
- Resmî Ren'Py komutu önce yalnız argüman listesi olarak planlanır; çalışma ve
  dosya yazma ayrı doğrulama kapısından önce etkinleştirilmez.
- Bölünmüş mevcut çeviri tek metne indirgenmez; hedef segment sınırları alan
  modelinde korunur ve birleşik metin yalnız inceleme görünümü olarak türetilir.
- Round-trip byte eşitliği yerine alan semantiğini korur; tırnak biçimi kanonik
  çift tırnağa normalize edilir ve gerçek dosya yazımı ayrı kapıda kalır.
- ORS 100 satırlık Aya benchmark'ı sonrası Phase 2.4: satır içi `{w=...}` tokenları artık
  çevrilen kelime/ifade bağından koparılamaz; kaynak metne göre aşırı uzayan ve komşu bağlamı
  çevirmeye devam etmiş olabilecek çıktılar cache öncesi reddedilir.
- `translategemma` adlı Ollama modelleri için otomatik strict adapter eklendi. Bu adapter genel
  LLM system/context/JSON promptunu kullanmaz; English (en) -> Turkish (tr) doğrudan çeviri
  promptunu tek user mesajıyla gönderir ve 2K bağlam penceresine sınırlar.
- Phase 2.5 Semantic Repair Pipeline: ilk çeviri sonrası açıklanabilir risk analizi,
  isteğe bağlı ikinci Ollama post-editor'ü, teknik QC'de bozulan ilk adayları
  bağlamla kurtarma, yüksek güvenli semantik riskleri fail-closed reddetme ve yalnız
  final kabul edilen çeviriyi translation memory'ye yazma eklendi.
- `pilot-translate` artık `--repair-model` ile TranslateGemma → Aya gibi hibrit
  benchmark çalıştırabilir; JSON çıktısı risk nedenlerini, base adayı, repair
  kullanımını ve repair sayımlarını kaydeder.
- Phase 2.5.1 Candidate Selector: iki teknik olarak geçerli adayda repair artık
  otomatik kabul edilmez. Yapılandırılabilir Ollama judge BASE / REPAIR / REJECT
  kararı verir; repair için güven eşiği, reject için fail-closed eşik ve düşük güvenli
  kararlarda conservative base fallback uygulanır.
- `pilot-translate --judge-model` ve selector audit alanları eklendi; kısa soru
  seçimlerinde gereksiz `siz/mısınız` hitabı da semantic repair riski sayılır.

## 2026-08-24 — Phase 2.5.2 Hybrid v3 Quality Hardening

- TranslateGemma direct prompt explicit/argo/cinsel tonu sansürlemeden koruyacak şekilde
  sertleştirildi ve placeholder layout contract eklendi.
- Semantic repair ve candidate judge için kaynak-özel semantic guardrails eklendi.
- `pussy/cock`, `anal sex`, negation loss ve genişletilmiş informal-vs-formal register
  sinyalleri eklendi; pseudo-Türkçe explicit transliterasyonlar hard-risk oldu.
- Eksik mutlak boundary `TEXT_TAG` tokenları için deterministik güvenli salvage eklendi;
  internal/data-bearing kontroller fail-closed kalır.
- Hybrid v2 100-result replay'i 14 teknik base fail'in 5'inin boundary salvage ile
  kurtarılabilir olduğunu ve 9 ek kabul edilmiş kalite sorununu yeni guard'ların yakaladığını
  gösterdi.
- Test kapısı 247'den **261 pytest** senaryosuna çıktı.
