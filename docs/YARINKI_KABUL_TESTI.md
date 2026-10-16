# RenTR — Yarınki Windows ve Gerçek Oyun Kabul Testi

Bu test Ziyaattin'in izinli bir Ren'Py oyununda yapacağı son dış doğrulamadır.
Önce oyunun klasörünü kopyala veya mağaza istemcisindeki dosya doğrulama
özelliğinin erişilebilir olduğundan emin ol. RenTR varsayılan olarak izole
çalışır; gerçek oyuna kurulum ayrıca onay ister ve geri alma kaydı üretir.

## 1. Otomatik geliştirme kapısı

PowerShell'i RenTR klasöründe aç:

```powershell
$env:UV_CACHE_DIR = "$env:TEMP\rentr-uv-cache"
uv sync --all-groups
uv run --group desktop python scripts/verify.py
```

Beklenen: Ruff ve mypy başarılı; bütün pytest testleri geçer.

## 2. Tek ekran masaüstü duman testi

```powershell
uv run --group desktop rentr-gui
```

Beklenen: Tek pencere açılır. Oyun klasörü, izole çalışma alanı, SDK,
sağlayıcı, kalite, ilerleme ve inceleme tablosu aynı ekrandadır; ayrı sayfalara
geçiş yoktur.

## 3. İlk gerçek oyun — kaynak veya paketli

1. **Oyun klasörü** alanından `.exe` ile `game` klasörünü içeren ana dizini seç.
2. **Oyunu Analiz Et** düğmesine bas. Sonuç `source`, `packaged` veya `resume`
   olmalı; oyunda önceden `game/tl/turkish` bulunması beklenmez.
3. Orijinal oyunun dışında boş bir **izole çalışma alanı** seç.
4. Oyunun Ren'Py nesline uygun resmî **Ren'Py SDK** klasörünü seç.
5. **Güvenli Kopyayı Hazırla** düğmesine bas.

Beklenen:

- Orijinal oyunda bu aşamada hiçbir dosya oluşmaz veya değişmez.
- Paketli oyunda yalnız script dosyaları çalışma alanına alınır; resim/ses
  kopyalanmaz.
- Desteklenmeyen/özel arşiv varsa RenTR açık hata verir; sessiz eksik çıktı
  üretmez.

## 4. Çeviri ve inceleme

Yerel Ollama kullanılacaksa önce Ollama'yı aç ve seçilen modeli indir. Arayüzde
**Yerel Ollama**, kalite profili ve model adını seç; ardından **Çevir ve
Önizle** düğmesine bas.

Haricî OpenAI uyumlu sağlayıcı kullanılacaksa uygulamayı aynı PowerShell'den şu
geçici değişkenlerle başlat:

```powershell
$env:RENTR_API_KEY = "KENDI_ANAHTARIN"
$env:RENTR_PROVIDER_URL = "https://SAGLAYICI/v1"
uv run --group desktop rentr-gui
```

Beklenen:

- Oyun içindeki bütün üretilmiş `.rpy` şablonları işlenir; yalnız ilk dosya
  çevrilmez.
- Önizleme ve risk tablosu görünür.
- `[player_name]`, `{b}`, `{/b}`, `%s`, `\n` gibi yapılar aynen korunur.
- İş kesilip tekrar başlatılırsa tamamlanan satırlar yerel bellekten gelir.

## 5. Oyuna kurulum ve geri alma

Önizleme doğruysa **Onayla ve Oyuna Kur** düğmesine bas. RenTR önce çalışma
alanındaki dosyaları ve ZIP paketini hazırlar, sonra gerçek oyuna yazacağı dosya
sayısını ve mevcut dosya çakışmalarını ayrı bir onay penceresinde gösterir.

1. İlk turda onay penceresinde **Hayır** de. Beklenen: paket çalışma alanında
   hazırdır, gerçek oyun değişmemiştir.
2. Aynı önizlemeyi yeniden hazırla ve bu kez kurulum onayında **Evet** de.
3. Oyunu normal `.exe` dosyasından çalıştır.
4. Türkçe açılmazsa oyunun Preferences/Language menüsünden `turkish` seç. Bu,
   daha önce kaydedilmiş bir dil tercihi olan oyunlarda gerekebilir.
5. Ana menü, diyalog, seçimler, kayıt/yükleme ve en az 10 dakikalık oynanışı
   kontrol et.
6. Oyunu kapat ve **Son Kurulumu Geri Al** düğmesine bas.

Beklenen:

- Kurulumdan önce var olan hedefler `.rentr/backups` altında yedeklenir.
- Türkçe dosyaları `game/tl/turkish` altına kurulur.
- Yeni kullanıcı profili/ilk çalıştırmada Türkçe varsayılan olur.
- Geri alma yeni RenTR dosyalarını kaldırır, eski dosyaları byte düzeyinde geri
  getirir.
- Kurulan bir dosyayı elle değiştirip geri alma denenirse RenTR bu değişikliği
  ezmek yerine işlemi reddeder.

## 6. Ren'Py lint ve kalite kabulü

İzole çalışma alanını uyumlu Ren'Py Launcher'da proje olarak açıp **Lint**
çalıştır. Ardından şu kontrol listesini doldur:

- [ ] Lint kritik hata vermedi.
- [ ] Oyun Türkçe dilinde açıldı veya Language menüsünden seçilebildi.
- [ ] Ana menü ve seçimler Türkçe.
- [ ] Diyaloglarda değişken/tag hatası yok.
- [ ] Türkçe karakterler doğru fontla görünüyor.
- [ ] Kayıt ve yükleme çalışıyor.
- [ ] En az 100 satırlık örnekte doğal Türkçe ortalaması 5 üzerinden en az 4.
- [ ] Kritik anlam kaybı yok.
- [ ] Geri alma başarılı.
- [ ] Oyun güncelleme/mağaza doğrulama işlemiyle özgün hâle döndürülebiliyor.

## 7. Hata olursa kaydedilecek üç bilgi

Parola veya API anahtarı paylaşmadan yalnız şunları kaydet:

1. RenTR'nin ekranda gösterdiği tam hata metni.
2. Oyunun Ren'Py sürümü ve `source/packaged/resume` sonucu.
3. Hatanın hangi düğmede ve hangi adımda oluştuğu.

Bu dış kabul geçmeden sürüm `1.0.0rc0` olarak kalır; “her Ren'Py oyununda
çalışır” garantisi verilmez.
