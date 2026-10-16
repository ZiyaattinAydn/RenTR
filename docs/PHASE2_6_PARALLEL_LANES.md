# Phase 2.6 — Parallel Model Lanes + Scalable Memory

Phase 2.5.4, model swap maliyetini satır başına olmaktan çıkarıp base → repair → judge
şeklinde model-gruplu evrelere taşıdı. Phase 2.6 aynı evrenin içinde birden fazla isteğin
eşzamanlı gönderilebilmesini ekler.

Önemli güvenlik sınırı: base, repair ve judge modelleri birbirleriyle paralel çalıştırılmaz.
Yalnız aynı modelin aynı evresindeki bağımsız birimler paralel olabilir. Sonuç sırası giriş
sırasıyla deterministik tutulur; Translation Memory yazımları kilitlenir.

Ollama tarafında paralellik istemci tarafından tek başına zorlanamaz. Sunucunun
OLLAMA_NUM_PARALLEL ayarı da aynı veya daha yüksek olmalıdır. İlk benchmark için 2 worker
önerilir; VRAM/RAM baskısı görülürse 1'e dönülür.

TranslateGemma doğrudan çeviri adapteri TranslationContext.suggestions alanını prompta
koymadığı için, bu yolda fuzzy memory suggestion hesabı kapatılır. Böylece tam oyun belleği
büyürken her birimde bütün SQLite belleğini SequenceMatcher ile tarayan O(N²) ölçeklenme
riski kaldırılır. Genel/OpenAI uyumlu provider yolu suggestion davranışını korur.
