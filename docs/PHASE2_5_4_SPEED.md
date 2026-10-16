# Phase 2.5.4 — Hybrid Speed Pass

Bu patch kalite kararlarını kaldırmadan yerel Ollama hibrit hattının model
switch maliyetini azaltır.

## Ana değişiklik

Önceki akış her riskli birimde şu sırayı tekrar ediyordu:

`TranslateGemma -> Aya -> Qwen3 -> TranslateGemma -> ...`

Yeni akış seçilen birimleri chunk içinde model bazında gruplar:

1. chunk içindeki bütün BASE çağrıları (TranslateGemma)
2. yalnız gerekli REPAIR çağrıları (Aya)
3. yalnız gerekli JUDGE çağrıları (Qwen3)

Böylece model swap sayısı birim başına değil chunk başına olur. `pilot-translate`
için varsayılan `--hybrid-batch-size 100`, çekirdekte genel varsayılan 256'dır.

## Ollama düşük-risk hız ayarları

- `keep_alive: 30m`
- tek birim üretimlerine `num_predict: 512` üst sınırı
- repair/judge için en fazla 2048 context window
- judge için `num_predict: 128`
- Qwen3 judge'da `think: false`
- judge nedenleri 1–3 kısa etiketle sınırlandı

Bu değişiklikler BASE/REPAIR/REJECT eşiklerini, semantic risk kurallarını veya
Repair Fidelity Gate'i kaldırmaz.

## Telemetri

`pilot-translate` JSON ve terminal özeti artık şunları verir:

- `hybrid_batch_size`
- `elapsed_seconds`
- `units_per_minute`

Böylece hız değişimi aynı örnek üzerinde ölçülebilir.

## Yerel kanıt

- Pipeline + local model + semantic/protection hedefli testleri geçti.
- Geniş test koşusunda 262 test geçti; mevcut snapshot'taki speed patch ile
  ilgisiz tek eski `translate-estimate` assertion'ı deselect edildi.
- Windows hedef Python 3.12, Ruff ve mypy son doğrulaması kullanıcı ortamındaki
  `scripts/verify.py` ile yapılmalıdır.
