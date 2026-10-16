# RenTR 1.0.0rc0 — Sürüm Adayı Notları

RenTR'nin planlanan Faz 0–4 ürün geliştirmesi ve Faz 5 güvenli runtime
araştırması tamamlandı. Bu paket final `1.0.0` değil, gerçek Windows ve izinli
oyun kabulinden önceki sürüm adayıdır.

## Öne çıkanlar

- Önceden `game/tl/turkish` klasörü olmayan Ren'Py oyununu analiz eder.
- Kaynak ve standart RPA-3.0 paketli oyunları orijinale yazmadan izole alanda
  hazırlar.
- Diyalog ve arayüz metinlerini Ren'Py tokenlarını koruyarak Türkçeleştirir.
- Yerel Ollama veya kullanıcı anahtarlı OpenAI uyumlu sağlayıcı kullanır.
- Bütün şablonları tek ekranlı masaüstü akışında önizler.
- Manifest/SHA-256 doğrulamalı Türkçe paket üretir.
- Gerçek oyuna yalnız ayrıca onayla kurar; çakışmaları yedekler ve kurulum
  kaydıyla güvenli geri alma sunar.
- Runtime hook/enjeksiyonunu reddeden salt okunur araştırma raporu içerir.

## Otomatik doğrulama

- Ruff: geçti.
- mypy: geçti.
- pytest: 187/187 geçti.
- Wheel ve sdist üretildi.
- Wheel temiz Python 3.12 ortamında CLI ve `desktop` opsiyonuyla kuruldu.
- Kaynak ZIP bütünlük kontrolü geçti.

## Final sürümden önce kalan dış kapı

- Windows'ta gerçek Qt penceresi.
- Windows `.exe` üretimi ve temiz bilgisayarda açılış.
- Uyumlu resmî Ren'Py SDK ile gerçek proje lint'i.
- En az bir izinli kaynak ve bir izinli paketli oyun testi.
- Türkçe font, kayıt/yükleme ve 100 satırlık kalite değerlendirmesi.
- Kurulum ve geri alma testi.

Adım adım talimat `docs/YARINKI_KABUL_TESTI.md` dosyasındadır. Bu kapı geçmeden
“her oyunda çalışır” veya final `1.0.0` garantisi verilmez.

## Gerçek oyun kalite benchmark güncellemesi

Aya Expanse 8B ile 100 temsilî Our Red String satırı işlendi; deterministik kapı 10 çıktıyı
reddetti ve manuel inceleme özellikle argo/explicit/context-sensitive satırlarda model
kalitesinin final üretim için yeterli olmadığını gösterdi. Phase 2.4 satır içi kontrol-token
ankrajı ve şüpheli çıktı büyümesi denetimi ekler. TranslateGemma için ayrıca modelin resmî
direct-translation promptuna uyumlu deneysel Ollama adapterı bulunur.

## Phase 2.5 deneysel kalite hattı

`pilot-translate --repair-model <ollama-model>` yüksek riskli ilk çevirileri ikinci
bir bağlamlı modelle post-edit edebilir. Filtre her satırı iki kez çevirmek yerine
explicit/argo, deyim, hitap, çoklu alternatif ve bilinen yüksek güvenli anlam
bozulmalarını açıklanabilir nedenlerle seçer. İlk model Ren'Py placeholderlarını
bozmuşsa post-editor kaynak placeholder sözleşmesini kullanarak kurtarmayı
deneyebilir. Yalnız teknik QC ve semantic hard-guard sonrasında kabul edilen final
metin translation memory'ye kaydedilir.

## Phase 2.5.1 candidate selector

Hibrit hattın ilk smoke testi iyi bir TranslateGemma base adayının gereksiz Aya
post-edit'iyle bozulabildiğini gösterdi. Phase 2.5.1 bu nedenle repair çıktısını
otomatik final yapmaz. İki geçerli aday ayrı bir pairwise judge tarafından
`base`, `repair` veya `reject` olarak değerlendirilir; repair'in base'i geçmesi
için güven eşiği vardır ve düşük güven durumunda temiz base korunur. Teknik veya
yüksek güvenli semantik hard-risk kapıları selector'dan önce çalışmaya devam eder.
Pilot JSON'a selector audit alanları ve `--judge-model` seçeneği eklenmiştir.

## Phase 2.5.2 Hybrid v3 quality hardening

Hybrid v2'nin 100 ORS satırlık sonucu selector mimarisini doğruladı ancak 23 fail'in büyük
kısmının Ren'Py placeholder kaybı ve explicit/argo semantik yumuşatmadan geldiğini gösterdi.
Bu güncelleme yeni bir çeviri modeli eklemek yerine üç mevcut katmanı sıkılaştırır:
TranslateGemma daha açık uncensored + placeholder sözleşmesiyle çağrılır, Aya repair kaynak-
özel semantic guardrails alır ve Qwen3 judge explicitliği kendi başına kusur sayamaz.

RenTR ayrıca yalnız konumu kesin olan satır başı/sonu `TEXT_TAG` tokenlarını modelden bağımsız
geri kurabilir. Internal wait tokenları, interpolation/format/escape verileri ve yerinden
oynatılmış mevcut kontroller için önceki fail-closed davranış korunur. Gerçek kalite sonucu
ancak aynı deterministik 100 satır Hybrid v3 ile tekrar çalıştırıldığında ölçülmüş sayılacaktır.
