# PDF Analiz & Özetleme Web Uygulaması

Kullanıcıların yüklediği PDF dosyalarını analiz edip otomatik olarak özetleyen basit bir Flask uygulaması.

## Özellikler

- Sürükle-bırak veya dosya seçici ile PDF yükleme
- Sayfa sayısı, kelime sayısı, karakter sayısı ve tahmini okuma süresi
- Google Gemini ile otomatik özetleme ve çalışma sorusu (quiz) üretimi
- En sık geçen anahtar kelimelerin listelenmesi (yerel, frekans tabanlı)
- Yüklenen dosyanın işlem bitince sunucudan otomatik silinmesi

> ⚠️ **Gizlilik:** Özet ve quiz üretimi için PDF'ten çıkarılan metin **Google
> Gemini API'sine gönderilir.** Gizli veya kişisel veri içeren belgeleri
> yüklerken bunu göz önünde bulundurun. Yalnızca istatistikler ve anahtar
> kelime çıkarımı tamamen yerel çalışır.

## Proje Yapısı

```
pdf_ozet_uygulamasi/
├── app.py                  # Flask uygulaması ve route'lar
├── requirements.txt        # Python bağımlılıkları
├── utils/
│   ├── pdf_utils.py        # PDF'ten metin çıkarma (pdfplumber)
│   └── summarizer.py       # Frekans tabanlı özetleme ve anahtar kelime çıkarımı
├── templates/
│   ├── index.html          # Yükleme sayfası
│   └── result.html         # Sonuç sayfası
├── static/
│   └── style.css           # Arayüz stilleri
└── uploads/                # Yüklenen dosyaların geçici olarak tutulduğu klasör
```

## Kurulum

1. (Önerilir) Sanal ortam oluşturun:

   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   ```

2. Bağımlılıkları yükleyin:

   ```bash
   pip install -r requirements.txt
   ```

3. Uygulamayı çalıştırın:

   ```bash
   python app.py
   ```

4. Tarayıcınızdan şu adresi açın:

   ```
   http://127.0.0.1:5000
   ```

## Nasıl Çalışır?

1. **Metin çıkarma** — `pdfplumber` kütüphanesi ile PDF'in her sayfasından metin çıkarılır.
2. **İstatistikler** — Kelime/karakter sayısı ve tahmini okuma süresi hesaplanır.
3. **Özetleme ve quiz** — Metnin ilk 4000 karakteri Google Gemini API'sine gönderilir; model kategorize bir özet ve çoktan seçmeli çalışma soruları üretir. Bu adım internet bağlantısı ve `GEMINI_API_KEY` gerektirir.
4. **Anahtar kelimeler** — Metin cümlelere ayrılır, anlam taşımayan kelimeler (stopwords) filtrelenir ve kalan kelimelerin frekansına göre en sık geçenler listelenir. Bu adım tamamen yereldir.

Model çıktısı, sayfaya basılmadan önce sunucuda allow-list tabanlı bir sanitizasyondan geçirilir. Bunun nedeni `SECURITY.md` içinde açıklanmıştır — **bu adım kaldırılmamalıdır.**

## Sınırlamalar ve Geliştirme Fikirleri

- **Taranmış (scanned) PDF'ler** desteklenmez; bunlar için OCR (`pytesseract` + `pdf2image`) eklenebilir.
- Özetleme kalitesini artırmak isterseniz `app.py` içinde bir LLM API çağrısı (ör. Anthropic API) ile `utils/summarizer.py`'deki `metni_ozetle` fonksiyonunu değiştirebilirsiniz.
- Şu an her istekte dosya işlenip hemen siliniyor; kullanıcı hesapları veya geçmiş analizler için bir veritabanı eklenebilir.
- Üretim ortamında `debug=True` kapatılmalı ve bir WSGI sunucusu (ör. `gunicorn`) kullanılmalıdır.
