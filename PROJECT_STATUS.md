# RenTR Proje Durumu

## Güncel aşama

**Faz 0–5 otomatik/araştırma kapıları tamamlandı; dış Windows/gerçek oyun
kabulü yarına ayrıldı.**

Sürüm adayı: `1.0.0rc0`.

## Tamamlanan fazlar

### Faz 0 — Temel

- Python 3.12, uv, tek repo, Ruff, mypy, pytest ve tek doğrulama komutu.
- Temiz oda geliştirme, veri güvenliği ve kalıcı karar kayıtları.
- Özgün, üçüncü taraf oyun içeriği olmayan fixture laboratuvarı.

### Faz 1 — Çekirdek CLI MVP

- `source`, `packaged`, `resume` ve `unsupported` oyun tespiti.
- `tl/turkish` klasörünü giriş şartı değil ürün çıktısı kabul eden akış.
- Diyalog, anlatıcı ve `old/new` arayüz metni parser'ı; mevcut insan
  çevirisini ve bölünmüş hedef segmentlerini koruyan alan modeli.
- Deterministik renderer ve parse → render → parse semantik kapısı.
- Ren'Py tag, interpolasyon, `%` biçimi ve kaçışlarını sıralı tokenlarla
  koruyan fail-closed doğrulama.
- SQLite çeviri belleği, insan kilidi, benzerlik adayları, retry/backoff ve
  yarıda kalınca cache'den devam.
- Diff, exact-state önkoşulu, atomik yazma, yedek ve korumalı geri alma.
- Resmî Ren'Py SDK komutunu shell kullanmadan yalnız izole kopyada çalıştıran
  kaynak oyun şablon üretimi.

### Faz 2 — Kullanılabilir Alpha

- Sürümlü Türkçe sözlük, karakter kartı ve `sen/siz` hitap bağlamı.
- Açıklanabilir risk puanlı insan inceleme kuyruğu.
- Çeviri geçmişi ve insan düzeltmesini kilitleyen geri alma.
- Oyun güncelleme envanteri karşılaştırması.
- TOML yapılandırması, ortam değişkeninden sır okuma ve hassas alanları
  reddeden yerel audit günlüğü.
- Üç özgün fixture matrisi, Windows CLI paketleme planı ve kabul kılavuzu.

### Faz 3 — Yerel model ve tek ekran masaüstü Beta

- Anahtarsız Ollama adaptörü; hızlı, dengeli ve yüksek kalite profilleri.
- RAM/donanım/model uygunluk değerlendirmesi.
- Farklı sayfa yığını kullanmayan tek PySide6 ana penceresi.
- Oyun/çalışma alanı/SDK seçimi, sağlayıcı, önizleme ve risk tablosu aynı
  ekranda.
- Bütün Türkçe şablonları tek işte çeviren masaüstü workflow'u.
- `pyside6-deploy` tabanlı Windows masaüstü paketleme planı.

### Faz 4 — Paketli oyun ve Kullanıcı V1 otomatik kapısı

- Standart RPA-3.0 arşiv başlığı, sınırlandırılmış zlib indeks açma ve yalnız
  güvenli container/latin1 bytes yapısına izin veren kısıtlı pickle okuyucu.
- Yol kaçışı, Windows büyük/küçük harf çakışması, boyut, segment ve dosya
  sayısı kapıları; yalnız `.rpy/.rpyc/.rpym/.rpymc` çıkarımı.
- RPYC2 bölüm tablosunu statik doğrulayan ve hiçbir RPYC pickle'ını yüklemeyen
  ön kontrol.
- Build bilgisi ve `lib/py2-*`/`lib/py3-*` kanıtıyla Ren'Py 6/7/8 nesil
  tespiti.
- Paketli oyunun scriptlerini medya kopyalamadan izole alana hazırlama ve
  resmî SDK ile orada Türkçe şablon üretme.
- SDK alt sürecinden API anahtarları ve gereksiz ortam değişkenlerini çıkaran
  daraltılmış yürütme ortamı.
- Deterministik Türkçe ZIP paketi, sürümlü manifest, SHA-256 dosya özeti ve
  paket kimliği.
- Türkçeyi Ren'Py'nin belgelenmiş `config.default_language` ayarıyla yeni
  çalıştırmalarda varsayılan yapan kaldırılabilir yardımcı script.
- Gerçek oyuna varsayılan olarak yazmayan kurulum planı; açık uygulama,
  çakışma onayı, dosya yedeği, kurulum kaydı ve exact-hash geri alma.
- Tek ekran masaüstünde “Onayla ve Oyuna Kur” ile ayrıca onaylanan gerçek oyun
  kurulumu ve “Son Kurulumu Geri Al” işlemi.
- Ren'Py 7 ve 8 düzenini temsil eden paketli fixture matrisi.

### Faz 5 — Runtime araştırması

- Statik paket, Ren'Py clipboard yardımı, OCR overlay ve process hook
  yaklaşımlarını yetki/risk/uyumluluk açısından karşılaştıran salt okunur rapor.
- Oyunu başlatmayan, clipboard okumayan, ekran yakalamayan ve süreç enjeksiyonu
  yapmayan metin akışı simülatörü.
- Ren'Py token koruması ve tekrar eden runtime metnini oturum belleğinden getirme.
- Statik paket önerildi; clipboard/OCR yalnız ayrı araştırma adayı, process hook
  ise güvenlik sınırı dışında reddedildi.
- Wheel için masaüstü opsiyonel bağımlılığı ve Linux/Windows CI doğrulama
  iş akışı eklendi; uzak CI henüz bu yerel ortamdan çalıştırılmadı.

## Güncel otomatik kanıt

- Komut: `UV_CACHE_DIR=/tmp/rentr-uv-cache uv run --group desktop python scripts/verify.py`
- Ruff: geçti.
- mypy: 64 kaynak/test/script dosyasında sorun yok.
- pytest: **187/187 test geçti**.
- Güvenlik kırma testleri: kötü amaçlı pickle globali, RPA yol kaçışı,
  bozuk/taşmış arşiv aralıkları, ZIP manifest uyuşmazlığı, eski kurulum planı,
  symlink ve sonradan değiştirilmiş çıktıda rollback reddi.
- Paketli Ren'Py 7 ve 8 fixture'larında orijinal oyuna yazılmadan izole script
  hazırlığı doğrulandı.

## Doğrulanmış sınır ve açık riskler

- Bu ortam Linux'tur ve `libEGL.so.1` yoktur; gerçek Qt penceresi burada
  açılamadı. UI yapısı ve terminalsiz ortak workflow test edildi, Windows duman
  testi kullanıcı kabulüne bırakıldı.
- Resmî SDK yalnız izole kopyada ve daraltılmış ortamla çalışır; bu, işletim
  sistemi seviyesinde tam sandbox değildir. Yalnız güvenilen resmî Ren'Py SDK
  kullanılmalıdır.
- Statik temiz oda okuyucu standart RPA-3.0 içindir. Eski, şifreli veya oyuna
  özel arşivler sessiz eksik çıktı yerine açık hata verebilir.
- RPYC içeriği RenTR tarafından unpickle/decompile edilmez. Çeviri şablonunu
  üretme yeteneği seçilen resmî SDK'nın oyun sürümüyle gerçek uyumuna bağlıdır.
- `config.default_language = "turkish"` Ren'Py'nin belgelenmiş varsayılan dil
  ayarıdır; daha önce başka dil tercihi kaydedilmiş bir kullanıcıda oyun içi
  dil seçimi ayrıca gerekebilir.
- Gerçek Windows paketleme, Ren'Py lint, oyun açılışı, font ve Türkçe kalite
  değerlendirmesi henüz yapılmadı; otomatik test bunların garantisi değildir.
- Parser'ın karmaşık/özel Ren'Py sözdizimi için destek sınırı vardır ve
  fail-closed davranır.

## Dağıtım kanıtı

- `uv build` ile `rentr-1.0.0rc0-py3-none-any.whl` ve
  `rentr-1.0.0rc0.tar.gz` üretildi.
- Wheel projeden bağımsız temiz Python 3.12 sanal ortamına kuruldu;
  `rentr --version` ve `rentr doctor` geçti.
- `rentr[desktop]` opsiyonel bağımlılığı aynı temiz ortama kuruldu ve PySide6
  6.11.2 bulundu.
- Linux konteynerinde eksik `libEGL.so.1` nedeniyle Qt uygulama importu
  beklendiği gibi dış sistem bağımlılığına takıldı; Windows pencere kabulü
  yapılmadan bu madde tamamlanmış sayılmayacak.
- Kaynak ZIP bütünlük testi geçti; wheel, sdist ve kaynak ZIP için SHA-256
  teslim listesi üretildi.

## Aktif tek iş

Kod geliştirme fazları bitti. Sıradaki tek iş Ziyaattin'in
`docs/YARINKI_KABUL_TESTI.md` ile Windows, uyumlu resmî SDK, izinli gerçek oyun,
font ve Türkçe kalite kabulünü yapmasıdır. Bu dış kabul geçmeden `1.0.0` etiketi
verilmeyecek.

## Ziyaattin'in sıradaki katkısı

Ziyaattin diyalog+string kapsamını, mevcut insan çevirisini korumayı, orijinal
oyuna yazmayan çalışma alanını ve bütün fazlarda kesintisiz ilerlemeyi belirledi.
Yarın `docs/YARINKI_KABUL_TESTI.md` ile Windows penceresi, izinli gerçek oyun,
Ren'Py lint ve Türkçe kalite kabulünü yapacak. Bu dış kabul geçmeden `1.0.0`
etiketi verilmeyecek.

## 23 Ağustos 2026 — Gerçek ORS düzeltme modu

- Gerçek Ren'Py 8.0.3 ORS şablonu 146.687 birimle hazırlanıp pilot hattına bağlandı.
- Qwen2.5 7B ve Qwen3 8B teknik olarak çalışsa da Türkçe kalite kabulünü geçmedi.
- Aya Expanse 8B aynı 10 satırlık pilotta şu ana kadarki en güçlü Türkçe aday oldu.
- Phase 2.3 kalite kapısı token konumu, metadata sızıntısı ve beklenmeyen Unicode yazı
  sistemi bozulmalarını cache öncesi reddeder.
- Sıradaki ölçüm: doğrulama kapısı geçtikten sonra Aya Expanse 8B ile 100 satırlık
  temsilî ORS benchmark'ı. Kullanılmayan Ollama modelleri benchmark sonunda temizlenecek.


## 23 Ağustos 2026 — 100 satırlık Aya benchmark sonucu

- Temsilî dağılım: 25 general dialogue, 20 context-sensitive, 20 protected syntax,
  20 ambiguous short, 15 string/UI birimi.
- Aya Expanse 8B: 100 birimde 10 deterministik QC fail verdi. Manuel kalite incelemesi
  context-sensitive satırların otomatik üretim için hâlâ zayıf olduğunu gösterdi; bu nedenle
  Aya henüz final üretim modeli değildir.
- Phase 2.4 yeni QC, gerçek benchmark'ta önceki kapıdan kaçan satır içi wait-token kaymalarını
  ve iki belirgin bağlam-devamı/çıktı şişmesi örneğini fail-closed yakalar.
- Sıradaki model karşılaştırması: TranslateGemma 12B, kendi strict direct-translation adapterı
  üzerinden aynı 100 satırlık pilot seçimiyle ölçülecek.

## 24 Ağustos 2026 — Phase 2.5 Semantic Repair Pipeline

- TranslateGemma 12B aynı 100 ORS satırında 14 teknik QC fail verdi; buna karşın
  Aya'ya göre `hot/no shortage`, `steamy`, `beefcake` gibi anlamları daha iyi çözdü.
- Yeni hibrit hat, TranslateGemma gibi ilk çeviri modelini semantic anchor olarak,
  Aya gibi bağlamlı modeli yalnız riskli satırlarda post-editor olarak kullanabilir.
- Mevcut 100 TranslateGemma sonucunun salt replay analizinde 86 başarılı base
  adayın 35'i risk filtresine takıldı; 51'i ikinci çağrı gerektirmeden tutuldu.
  14 teknik base fail de hybrid gerçek koşusunda repair'e yönlendirilecek.
- Risk kaydı ve pilot JSON audit alanları: `base_translated_text`, `risk_score`,
  `risk_reasons`, `repair_attempted`, `repair_used`, `repair_attempts`,
  `repair_model`, `repair_error`, `post_repair_risk_reasons`.
- Container kanıtı: Python 3.13 üzerinde compileall ve **241/241 pytest** geçti.
  Projenin hedefi Python 3.12 olduğundan Ruff + mypy + Windows pytest için son
  mühür kullanıcı makinesindeki `scripts/verify.py` ile alınacak.
- Sıradaki ölçüm: aynı deterministik 100 ORS satırında
  `translategemma:12b -> aya-expanse:8b` hybrid benchmark.

## 24 Ağustos 2026 — Phase 2.5.1 Candidate Selector

- İlk hibrit v1 smoke testinde TranslateGemma'nın temiz `Damn...! When did you get so good
  at this?` çevirisinin Aya repair tarafından daha kötü Türkçeye çevrilip otomatik kabul
  edildiği görüldü.
- `CandidateJudgeProvider` eklendi: iki geçerli Türkçe aday arasında BASE / REPAIR / REJECT
  kararı verir; yeni çeviri üretmesi yasaktır.
- Repair, base'i ancak selector `repair` seçer ve güven >= 0.72 ise değiştirebilir.
  Yüksek güvenli `reject` iki adayı da cache dışı bırakır; düşük güven kararlarında geçerli
  base korunur.
- Pilot audit JSON artık selector kararı, model, güven, neden ve hata alanlarını içerir.
- Kısa soru + gereksiz `siz/mısınız` register sinyali speaker olmayan seçim/string
  satırlarında da risk üretir (`Ready? -> Hazır mısınız?` gibi).
- Container kanıtı: Python 3.13 üzerinde compileall ve **247/247 pytest** geçti.
  Hedef Python 3.12 olduğu için Ruff + mypy + Windows pytest son mührü kullanıcı ortamında
  `scripts/verify.py` ile alınacaktır.
- Sıradaki ölçüm: TranslateGemma 12B base + Aya 8B repair + bağımsız Qwen3 8B judge ile
  aynı deterministik 10 ORS satırında `hybrid-v2-selector` smoke testi.

## 24 Ağustos 2026 — Phase 2.5.2 Hybrid v3 Quality Hardening

- Hybrid v2 ORS 100 benchmark özeti: 100 seçili birimde 23 fail, 48 repair denemesi,
  15 repair finali, 10 base seçimi ve 23 selector reject görüldü.
- Fail kök nedenleri yapılandırılmış raporda 14 teknik Ren'Py placeholder/QC problemi,
  7 iki adayda da kalan hard-semantic risk ve 2 pairwise judge reject olarak ayrıştı.
- TranslateGemma direct promptundan `cultural sensitivities` ifadesi çıkarıldı; explicit dil,
  küfür, argo ve cinsel yoğunluğu sansürlemeden koruma talimatı açık hale getirildi.
- TranslateGemma ve Aya repair istekleri artık placeholder konum sözleşmesini taşır.
  Modelin baş/son/inline/bitişik placeholder yapısını görmesi amaçlanır.
- Yalnız mutlak satır başı/sonundaki eksik `TEXT_TAG` kontrolleri deterministik olarak
  geri konabilir. Interpolation/printf/escape, internal token, yerinden oynatılmış mevcut token
  ve model metni araya girmiş token kümeleri fail-closed kalır.
- Semantic guardrail seti sexual `fuck`, `cum`, `sex`, `anal sex`, `slut`, `pussy`,
  `cock/dick`, sexual `hot` ve `no shortage` için kaynak anlamını tarif eder; sabit kelime
  değiştirme yapmaz.
- Risk analyzer `püs/pussy-mi` benzeri pseudo-Türkçe explicit transliterasyonları,
  explicit anatomi kaybını, daha geniş `siz` çekimlerini ve konservatif negation-loss
  sinyalini yakalar.
- Candidate judge promptu explicitliğin kusur olmadığını, kaynak explicit ise doğrudan
  Türkçenin cezalandırılmaması gerektiğini ve pseudo-Türkçe kelimelerin kalite hatası
  sayılacağını açıkça belirtir.
- Eski Hybrid v2 JSON'una model çağrısı yapmadan yapılan replay'de 14 teknik base fail'in
  5'i yeni güvenli boundary salvage ile geri kurulabilir durumda; daha önce kabul edilen
  9 çıktı da yeni register/explicit guard'lara takılıyor. Bu replay yeni model benchmarkı
  değildir; gerçek Hybrid v3 ölçümü hâlâ Windows/Ollama koşusu gerektirir.
- Container doğrulaması: Python 3.13 `compileall` geçti ve **261/261 pytest** başarılı.
  Ruff + mypy + hedef Python 3.12 doğrulaması kullanıcı ortamındaki `scripts/verify.py`
  ile yeniden mühürlenecek.
