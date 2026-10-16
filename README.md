# RenTR

RenTR, Ren'Py oyunları için Türkçe öncelikli ve güvenli bir yerelleştirme
yardımcısıdır. Kullanıcı oyun klasörünü seçer; RenTR kaynak, paketli veya önceki
çeviriye devam modunu belirler. `game/tl/turkish` kullanıcıdan hazır beklenmez;
başarılı ilk çalışmanın çıktısıdır.

Teknik geliştirme; oyun yapısını güvenle tespit eden, gerektiğinde çeviri
şablonunu üreten, tag ve interpolasyonları koruyan, çeviri belleği kullanan ve
doğrulanmış Türkçe çıktı oluşturan ortak bir çekirdektir. Tek ekranlı masaüstü
arayüzü, CLI, yerel Ollama ve haricî sağlayıcılar aynı güvenlik hattını kullanır.

## Hızlı başlangıç

Gereksinimler:

- Python 3.12
- uv

Yalnız yayımlanmış wheel kurulacaksa CLI için `pip install rentr`, masaüstü
komutu için `pip install "rentr[desktop]"` kullanılır.

```bash
uv sync --all-groups
uv run rentr doctor
uv run rentr inspect-game /path/to/game-root
uv run rentr workspace-plan /path/to/game-root --destination /path/to/workspace
uv run rentr translation-plan /path/to/game-root \
  --workspace /path/to/workspace --sdk /path/to/renpy-sdk \
  --target-platform windows
uv run rentr prepare-translation /path/to/game-root \
  --workspace /path/to/workspace --sdk /path/to/renpy-sdk \
  --target-platform windows
uv run rentr inventory tests/fixtures/first_choice_a.rpy
uv run rentr render-template tests/fixtures/parser_edge_cases.rpy
uv run rentr translate-estimate template.rpy \
  --memory /path/to/workspace/.rentr/memory.sqlite3
uv run rentr project-check examples/demo-project/rentr.toml
uv run rentr prepare-packaged /path/to/packaged-game \
  --workspace /path/to/workspace --sdk /path/to/renpy-sdk
uv run rentr build-package /path/to/workspace
# Sonraki komut önce yalnız plan gösterir; --apply verilirse gerçek oyuna kurar.
uv run rentr install-package /path/to/workspace/.rentr/packages/PACKAGE.zip \
  /path/to/game-root
uv run python scripts/verify.py
```

Hibrit kalite pilotunda ilk model, bağlamlı repair modeli ve aday hakemi ayrı
seçilebilir. Judge yeni çeviri üretmez; yalnız BASE / REPAIR / REJECT seçer:

```powershell
uv run rentr pilot-translate `
  "C:\path\to\game\tl\turkish" `
  --workspace "C:\path\to\isolated-workspace" `
  --ollama-model "translategemma:12b" `
  --repair-model "aya-expanse:8b" `
  --judge-model "qwen3:8b" `
  --limit 10
```

`verify.py` sırasıyla biçim/lint, tip kontrolü ve testleri çalıştırır. Bir aşama
başarısız olursa işlem hata koduyla durur.

Windows CLI paketleme ortamında:

```powershell
uv sync --group packaging
uv run --group packaging python scripts/build_windows.py
```

Masaüstü beta:

```powershell
uv sync --group desktop
uv run --group desktop rentr-gui
uv run --group desktop python scripts/build_desktop_windows.py
```

Gerçek oyunla son kontrol sırası `docs/YARINKI_KABUL_TESTI.md` dosyasındadır.

## Mevcut kapsam

- Tek repo, tek çekirdek ve tek ekran çalışma akışı
- Temel `TranslationUnit` alan modeli
- Kararlı kaynak özeti üretimi
- `rentr doctor` ortam kontrolü
- Diyalog ve `old/new` kaynaklarını çıkaran ilk salt okunur parser dilimi
- Dolu hedef çevirileri koruyan `translated_text` ve durum tespiti
- Anlatıcı/backtick metinlerini ve Ren'Py kaçışlarını Python kodu çalıştırmadan
  okuyan özel literal çözücüsü
- Bir kaynak diyaloğun birden fazla hedef satıra bölündüğü mevcut çevirileri
  `translated_segments` ile kayıpsız envanterleme
- Desteklenen alan modelini kanonik Ren'Py metnine dönüştüren deterministik,
  dosyaya yazmayan renderer ve `render-template` önizlemesi
- Üç desteklenen fixture için parse → render → parse semantik round-trip kapısı
- Oyun kökünü source, packaged ve resume modlarına ayıran salt okunur tarayıcı
- Orijinal oyuna yazmadan gerekli script/arşivleri planlayan izole çalışma alanı
- Resmî SDK düzenini doğrulayıp `translate turkish` çağrısını çalıştırmadan
  argüman listesi olarak üreten güvenli komut planı
- Ren'Py tag/interpolasyon/format/kaçışlarını koruyan sıralı token sözleşmesi
- Yerel SQLite çeviri belleği, insan kilidi ve inceleme adayları
- Mock ve OpenAI uyumlu sağlayıcı sınırı; bağlam, retry ve cache'den devam etme
- Diff, stale-plan kontrolü, yedek, atomik yazma ve geri alma sağlayan Safe Writer
- `rentr inventory <template.rpy>` JSON envanter komutu
- Standart RPA-3.0 arşivlerini yalnız scriptlerle sınırlı, statik ve fail-closed
  açan temiz oda katmanı; RPYC için pickle yüklemeyen RPC2 ön kontrolü
- Ren'Py 6/7 ile 8 neslini kanıta dayalı ayıran uyumluluk tespiti
- İzole kopyada resmî SDK ile paketli oyun şablonu hazırlama
- Bütün Türkçe şablonları tek masaüstü akışında çevirme
- Deterministik ZIP manifesti, SHA-256 dosya doğrulaması, dry-run kurulum,
  çakışma yedeği, kurulum kaydı ve korumalı geri alma
- Türkçeyi Ren'Py'nin belgelenmiş `config.default_language` ayarıyla yeni
  kurulumlarda varsayılan yapan, paketten bağımsız kaldırılabilen yardımcı dosya
- 187 testlik lint, tip ve davranış kapısı
- Ana üründen ayrı, hook/enjeksiyonu reddeden runtime seçenek raporu ve yalnız
  kullanıcı metniyle çalışan güvenli akış simülatörü

Faz 4'ün otomatik V1 kapısı geçmiştir. Yerel Ollama, kalite/donanım kontrolü,
tek ekranlı PySide6 arayüzü, paketli oyun hazırlığı ve güvenli mod kurulumu
uygulanmıştır. Gerçek Windows penceresi, gerçek Ren'Py SDK lint'i ve izinli oyun
uyumluluğu `docs/YARINKI_KABUL_TESTI.md` ile dış kabul beklemektedir. Güncel
durum ve sıradaki tek görev `PROJECT_STATUS.md` içindedir.

## Güvenlik sınırı

RenTR statik RPA/RPYC incelemesinde oyun Python kodunu veya RPYC pickle
bölümlerini yüklemez. `translation-plan` salt okunur kalır; açık hazırlık
komutları yalnız izole kopyada resmî SDK'yı, daraltılmış bir ortam değişkeni
listesiyle çalıştırır. Bu işlem işletim sistemi seviyesinde tam sandbox değildir;
yalnız güvenilen resmî SDK ile kullanılmalıdır. `translate-template` çalışma
alanına, `install-package` ise gerçek oyuna ancak açık `--apply` ile yazar.
Kurulan dosya sonradan değişmişse otomatik geri alma onu ezmeyi reddeder.

## Deneysel Semantic Repair pilotu

İlk çeviri modelini semantic anchor, ikinci Ollama modelini yalnız riskli satırlar
üzerinde bağlamlı post-editor olarak kullanmak için:

```powershell
uv run rentr pilot-translate `
  "C:\path\to\workspace\game\tl\turkish" `
  --workspace "C:\path\to\workspace" `
  --ollama-model "translategemma:12b" `
  --repair-model "aya-expanse:8b" `
  --limit 100 `
  --quality balanced
```

`--repair-model` verilmezse önceki tek-model davranışı aynen korunur. Hibrit modda
base model çıktısı doğrudan cache'e yazılmaz; risk filtresi ve gerekiyorsa repair
sonrası teknik kalite kapısından geçen final metin saklanır.

## Hybrid v3 kalite sertleştirmesi

Phase 2.5.2, mevcut `--repair-model` + `--judge-model` akışını değiştirmeden üç kalite
koruması ekler: TranslateGemma için açık uncensored/placeholder promptu, Aya/Qwen judge için
kaynak-özel semantic guardrails ve yalnız mutlak satır başı/sonu `TEXT_TAG` kaybında güvenli
deterministik token salvage. Internal Ren'Py kontrolleri için fail-closed davranış aynen sürer.

Önerilen gerçek benchmark komutu:

```powershell
uv run rentr pilot-translate `
  "C:\path\to\workspace\game\tl\turkish" `
  --workspace "C:\path\to\workspace" `
  --ollama-model "translategemma:12b" `
  --repair-model "aya-expanse:8b" `
  --judge-model "qwen3:8b" `
  --limit 100 `
  --quality balanced
```
