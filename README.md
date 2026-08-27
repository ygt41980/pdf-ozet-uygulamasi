# PDF Analiz & Özetleme Web Uygulaması

Kullanıcıların yüklediği PDF dosyalarını analiz edip otomatik olarak özetleyen basit bir Flask uygulaması.

## Özellikler

- Sürükle-bırak veya dosya seçici ile PDF yükleme
- Sayfa sayısı, kelime sayısı, karakter sayısı ve tahmini okuma süresi
- Kelime frekansına dayalı, harici API gerektirmeyen otomatik özetleme
- En sık geçen anahtar kelimelerin listelenmesi
- Yüklenen dosyanın işlem bitince sunucudan otomatik silinmesi

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
3. **Özetleme** — Metin cümlelere ayrılır, anlam taşımayan kelimeler (stopwords) filtrelenir, kalan kelimelerin frekansına göre her cümle puanlanır ve en yüksek puanlı cümleler orijinal sırasıyla özet olarak sunulur.
4. **Anahtar kelimeler** — Aynı frekans tablosundan en sık geçen kelimeler listelenir.

Bu özetleme yöntemi tamamen yerel çalışır (internet/API anahtarı gerektirmez), bu yüzden hızlıdır ama bir büyük dil modeli kadar "akıllı" değildir — metindeki en "önemli görünen" cümleleri seçer, yeniden yazmaz.

## Sınırlamalar ve Geliştirme Fikirleri

- **Taranmış (scanned) PDF'ler** desteklenmez; bunlar için OCR (`pytesseract` + `pdf2image`) eklenebilir.
- Özetleme kalitesini artırmak isterseniz `app.py` içinde bir LLM API çağrısı (ör. Anthropic API) ile `utils/summarizer.py`'deki `metni_ozetle` fonksiyonunu değiştirebilirsiniz.
- Şu an her istekte dosya işlenip hemen siliniyor; kullanıcı hesapları veya geçmiş analizler için bir veritabanı eklenebilir.
- Üretim ortamında `debug=True` kapatılmalı ve bir WSGI sunucusu (ör. `gunicorn`) kullanılmalıdır.
