# RenTR Faz 5 — Runtime Çeviri Araştırma Sonucu

## Sonuç

Canlı/runtime çeviri, `1.0` statik ürün hattına eklenmemelidir. Ana yöntem;
çeviriyi önceden üretip incelemek, manifestli paketle kurmak ve gerektiğinde
geri almaktır. Bu yöntem bağlam, cache, token doğrulaması, Ren'Py lint ve insan
incelemesi sağlar; oyun sırasında ağ gecikmesi üretmez.

Faz 5 araştırması iki güvenli çıktı üretir:

1. Oyunu başlatmadan dört yaklaşımı raporlayan `runtime-research-report`.
2. Yalnız kullanıcının verdiği metin satırlarını işleyen, ekran yakalamayan ve
   süreç hook'u yapmayan `runtime-simulate` laboratuvarı.

Bu çıktılar canlı overlay özelliği veya tüm oyunlarda çalışma garantisi değildir.

## Karar matrisi

| Yaklaşım | Karar | Oyuna yazma | Ekran yakalama | Süreç enjeksiyonu | Ana sorun |
|---|---|---:|---:|---:|---|
| Statik Türkçe paket | Önerilen V1 | Ayrı onayla | Hayır | Hayır | SDK/oyun sürümü uyumu |
| Ren'Py clipboard yardımı | Yalnız araştırma | Hayır | Hayır | Hayır | Yalnız erişilebilir/görünür metin; kullanıcı Shift+C eylemi |
| OCR overlay | Yalnız araştırma | Hayır | Evet | Hayır | OCR hatası, izin, gizlilik ve gecikme |
| Process hook/enjeksiyon | Reddedildi | Hayır | Hayır | Evet | Çökme, antivirüs, lisans ve sürüm kırılması |

## Kaynak temelli bulgular

- Ren'Py'nin resmî self-voicing belgesi, `Shift+C` ile açılan clipboard modunda
  ekrandan çıkarılabilen metnin panoya kopyalanabildiğini söylüyor. Bu, motor
  içine hook atmadan araştırılabilecek tek yerleşik runtime sinyalidir:
  <https://www.renpy.org/doc/html/self_voicing.html>
- Resmî çeviri belgesi ana dil değiştirme yolunu `Language(language)` eylemi ve
  `renpy.change_language` fonksiyonu olarak tanımlar:
  <https://www.renpy.org/doc/html/translation.html>
- Resmî yapılandırma belgesi `config.default_language` değerini varsayılan
  çeviri dili olarak tanımlar; statik pakette kullanılan yardımcı dosya bu
  belgelenmiş mekanizmaya dayanır:
  <https://www.renpy.org/doc/html/config.html#var-config.default_language>

Clipboard modu her özel ekranı, görsel içindeki yazıyı veya oyunun erişilebilir
metin ağacına koymadığı içeriği yakalayacağı anlamına gelmez. OCR doğruluğu ve
gecikme maddeleri ise henüz gerçek oyun ölçümü değil, prototip öncesi risk
varsayımlarıdır.

## Salt okunur rapor

```powershell
uv run rentr runtime-research-report "C:\OYUN_KLASORU"
```

Komut oyun süreci başlatmaz, dosya yazmaz ve ekran yakalamaz. JSON sonucu her
stratejinin kararını, gerektirdiği yetkiyi ve bilinen sınırlamaları gösterir.

## Zararsız metin akışı simülatörü

`events.txt` her satırda kullanıcının sağladığı bir İngilizce metin içerir.
`mapping.json` test sağlayıcısının korumalı girdi/çıktı eşlemesidir.

```powershell
uv run rentr runtime-simulate events.txt --mock-map mapping.json
```

Simülatör:

- Ren'Py tokenlarını normal çeviri hattıyla korur.
- Aynı metni ikinci kez sağlayıcıya göndermeden oturum içi bellekten getirir.
- En fazla 1.000 olay, olay başına 2.000 karakter ve 1 MiB fixture kabul eder.
- Clipboard okumaz, ekran görüntüsü almaz, oyuna yazmaz ve süreç enjeksiyonu
  yapmaz.

## Bir gün gerçek OCR overlay düşünülürse zorunlu kapılar

Ana üründen ayrı bir deney dalında, kullanıcı açıkça etkinleştirmeden hiçbir
yakalama yapılmamalıdır. Devam kararı için en az şu kanıtlar gerekir:

1. En az üç izinli oyunda konuşmacı/diyalog/seçim yakalama oranı.
2. P50/P95 OCR + çeviri + çizim gecikmesi.
3. Stilize font ve hareketli arka plan doğruluğu.
4. Ekran görüntüsünün diske veya log'a yazılmadığı gizlilik testi.
5. Ağ kesilmesi ve model hatasında oyunu etkilemeyen fail-safe davranış.
6. Overlay'in tıklama, tam ekran, çoklu monitör ve DPI davranışı.
7. Açık kapatma düğmesi ve izin iptali.

Bu ölçümler olmadan OCR “destekleniyor” sayılmayacaktır. Process hook yaklaşımı
ise bu kapılara alınmayacak; RenTR güvenlik sınırı dışında kalacaktır.
