# 📄 PDF Analiz & Özetleme Web Uygulaması

Yüklenen bir PDF'i analiz eden, Google Gemini ile özetleyen, ondan çalışma
soruları (quiz) üreten ve belge hakkında soru-cevap sohbeti yapılmasını
sağlayan bir Flask web uygulaması.

## ✨ Özellikler

- Sürükle-bırak veya dosya seçici ile PDF yükleme (maks. 50 MB)
- 3 seviyede otomatik özet: kısa / orta / detaylı sınav notu
- Google Gemini ile 5 soruluk çoktan seçmeli quiz üretimi
- **PDF ile sohbet** — belge içeriğine dayalı soru-cevap arayüzü
- Sayfa/kelime/karakter sayısı ve tahmini okuma süresi
- En sık geçen anahtar kelimelerin çıkarımı (tamamen yerel, API kullanmaz)
- Koyu mod
- İşlem bitince yüklenen dosyanın sunucudan otomatik silinmesi

> ⚠️ **Gizlilik:** Özet, quiz ve sohbet için PDF'ten çıkarılan metin
> **Google Gemini API'sine gönderilir.** Gizli/kişisel veri içeren belgeleri
> yüklerken bunu göz önünde bulundurun. İstatistikler ve anahtar kelime
> çıkarımı tamamen yerel çalışır, hiçbir yere gönderilmez.

## 🔒 Güvenlik

Bu proje kapsamlı bir güvenlik denetiminden geçti ve aşağıdakiler dahil
birçok koruma içeriyor:

- CSRF token doğrulama (Flask-WTF)
- Endpoint bazlı hız sınırlama (Flask-Limiter) — Gemini çağrıları ücretli
- Dosya içeriğinden PDF imza doğrulaması (uzantıya güvenilmez)
- LLM çıktısının HTML'e basılmadan önce sanitize edilmesi (bleach)
- Belge metninin istemciye değil sunucuya (TTL'li, kapasiteli bir depoya) yazılması
- `SECRET_KEY` olmadan üretimde açılmayan fail-closed tasarım
- Sıkı Content-Security-Policy ve diğer güvenlik header'ları
- PDF ayrıştırmada sayfa/karakter/süre sınırları (DoS koruması)
- `pytest` ile güvenlik regresyon test paketi (`tests/`)

Detaylar ve geliştirici kuralları için **[SECURITY.md](SECURITY.md)** dosyasına bakın.

## 🛠 Kullanılan Teknolojiler

| Katman | Teknoloji |
|---|---|
| Backend | Python 3, Flask 3.0 |
| PDF ayrıştırma | PyMuPDF (`fitz`) |
| Yapay zeka | Google Gemini API (`google-generativeai`, Gemini 3.6 Flash) |
| Güvenlik | Flask-WTF (CSRF), Flask-Limiter (hız sınırı), bleach (sanitizasyon) |
| Sunucu | Gunicorn |
| Arayüz | Jinja2 şablonları, vanilla JS/CSS |
| Test | pytest |
| Dağıtım | Render |

## 📁 Proje Yapısı

```
├── app.py                  # Flask uygulaması, route'lar, güvenlik ayarları
├── requirements.txt        # Python bağımlılıkları
├── Procfile                # Render/gunicorn başlangıç komutu
├── SECURITY.md             # Güvenlik politikası ve geliştirici kuralları
├── env.example             # Ortam değişkeni şablonu
├── utils/
│   ├── pdf_utils.py         # PDF'ten metin çıkarma + süre/sayfa sınırı
│   ├── security.py          # Sanitizasyon, doğrulama, belge deposu
│   └── summarizer.py        # Gemini ile özet/quiz/sohbet
├── templates/
│   ├── index.html            # Yükleme sayfası
│   └── result.html           # Sonuç sayfası + sohbet arayüzü
├── static/
│   └── style.css              # Arayüz stilleri
└── tests/
    ├── conftest.py             # Test yapılandırması
    └── test_security.py        # Güvenlik regresyon testleri
```

## 🚀 Kurulum

```bash
# 1. Sanal ortam oluştur
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. Bağımlılıkları yükle
pip install -r requirements.txt

# 3. Ortam değişkenlerini ayarla (env.example'a bak)
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export GEMINI_API_KEY=senin_api_anahtarin

# 4. Çalıştır
python app.py
```

Tarayıcıdan `http://127.0.0.1:5000` adresini aç.

### Ortam Değişkenleri

| Değişken | Zorunlu mu? | Açıklama |
|---|---|---|
| `SECRET_KEY` | Üretimde zorunlu | Oturum cookie imzalama anahtarı. Yoksa uygulama üretimde açılmaz. |
| `GEMINI_API_KEY` | Özet/quiz/sohbet için zorunlu | Google AI Studio'dan alınır. Yalnızca sunucuda kullanılır. |
| `FLASK_DEBUG` | Opsiyonel | Yerel geliştirmede `1`. Üretimde asla açılmamalı. |
| `UPLOAD_FOLDER` | Opsiyonel | Yüklemelerin geçici yazıldığı klasör. |

## ⚙️ Nasıl Çalışır?

1. **Yükleme** — PDF, dosya imzasından (`%PDF-`) doğrulanır, geçici bir klasöre kaydedilir.
2. **Metin çıkarma** — PyMuPDF ile sayfa sayfa metin çıkarılır; sayfa sayısı, karakter sayısı ve işlem süresi sınırlıdır.
3. **Sunucu tarafı depo** — Çıkarılan metin sunucu belleğinde (TTL'li) tutulur; tarayıcıya yalnızca tahmin edilemez bir kimlik gönderilir.
4. **Özet + quiz** — Metin, eş zamanlı iki Gemini çağrısıyla özetlenir ve 5 soruluk quiz üretilir.
5. **Anahtar kelimeler** — Metin yerel olarak (API'siz) analiz edilip en sık geçen kelimeler çıkarılır.
6. **Sonuç sayfası** — Özet, quiz ve istatistikler gösterilir; kullanıcı ayrıca belge hakkında serbestçe soru sorabilir (`/chat`).
7. **Temizlik** — İşlem bitince (başarılı ya da hatalı) yüklenen dosya sunucudan silinir.

## ⚠️ Sınırlamalar

- Taranmış (görüntü tabanlı) PDF'lerden metin çıkarılamaz — OCR desteği yok.
- Belge deposu ve hız sınırı sunucu belleğinde tutulur; bu yüzden uygulama **tek worker** ile çalışacak şekilde tasarlanmıştır (bkz. `Procfile` ve `SECURITY.md`).
- Ücretsiz Gemini API katmanı kullanılıyorsa, gönderilen içerik Google tarafından ürün geliştirme amacıyla kullanılabilir.

## 🧪 Testler

```bash
pip install pytest
python -m pytest tests/ -q
```

Her test, geçmiş bir güvenlik denetiminde bulunan somut bir bulguya karşılık gelir; bir test kırmızıya dönerse ilgili açık geri gelmiş demektir.
