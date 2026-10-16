# Phase 2.5.5 — Boundary Token Recovery

Bu aşama yeni bir LLM kalite katmanı eklemez. Amaç, modelin doğru Türkçe metni üretmesine rağmen
mutlak satır sonundaki Ren'Py kontrol kümesinin arkasına noktalama koyması nedeniyle oluşan teknik
fail'leri deterministik olarak kurtarmaktır.

Örnek kaynak:

```text
I had to-{w=0.5}{nw}
```

Model çıktısı:

```text
Yapmalıydım-__RENTR_0000____RENTR_0001__.
```

Önceki davranışta sondaki kontrol tokenı artık mutlak boundary'de olmadığı için teknik QC fail
oluyor ve hybrid pipeline repair modeline geçiyordu. Yeni davranışta placeholder kümesi mevcut,
doğru sırada ve bitişik olduğundan; ayrıca kaynak kümesi mutlak suffix olduğundan pozisyon
belirsizliği yoktur. Timing suffix bir kesik tireden sonra geliyorsa modelin sonradan eklediği
noktalama kaldırılır ve orijinal Ren'Py tokenları geri yüklenir.

Bu kurtarma internal tokenları, interpolation'ları, printf formatlarını veya escape yapılarını
taşımaya çalışmaz. Belirsiz durumlar fail-closed kalır.
