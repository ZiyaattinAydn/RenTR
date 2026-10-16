# Hybrid v2 → Hybrid v3 offline replay

Tarih: 24 Ağustos 2026

Kaynak: `pilot-results-100-hybrid-v2-selector.json` (100 deterministic ORS unit).
Bu replay yeni Ollama çağrısı yapmaz; yalnız Hybrid v3'ün deterministik kurallarını eski
çıktılara uygular. Bu nedenle yeni kalite benchmarkı değildir.

## Hybrid v2 özet

- selected: 100
- failed: 23
- repair attempted: 48
- repaired final: 15
- selector base: 10
- selector repair: 15
- selector reject: 23

Fail kök nedeni:

- 14: teknik Ren'Py placeholder/QC
- 7: base + repair üzerinde unresolved hard semantic risk
- 2: pairwise judge iki adayı da reddetti

## Boundary salvage replay

14 teknik base fail'in 5'i yalnız mutlak prefix/suffix `TEXT_TAG` kaybı olduğu için Hybrid v3
ile LLM tahmini yapmadan geri kurulabilir:

- `strings:733422a32652a610:1` — prefix image
- `gallery_CH09_S13_d517f03d` — suffix emoji
- `v11lenasms_d841ef67` — suffix emoji
- `v12louisesms2_e85dc30a` — suffix emoji
- `strings:7a870ffcf5888c5d:1` — prefix image

Internal `{w}` stutter/timing tokenları, partial inline style tag'leri ve data-bearing
interpolation/format kontrolleri salvage edilmez; fail-closed kalır.

## Yeni risk sinyallerinin eski kabul edilmiş çıktılarda yakaladıkları

Hybrid v3 analyzer, v2'de kabul edilmiş 9 çıktıda ek risk üretir:

- 6 adet beklenmeyen formal `siz`/2. çoğul çekim örneği
- `Cum in my pussy!` repair'inde `pussy` anlamının düşmesi
- `Your pussy feels...` çıktısında uydurma `püsün`
- `tending to my pussy` çıktısında uydurma `pussymi`

Sonuç: v3 daha fazla satırı körlemesine kabul etmek yerine repair/judge'a yönlendirecek.
Gerçek başarı oranı aynı 100 unit yeniden Ollama ile çalıştırılmadan ölçülmüş sayılmaz.
