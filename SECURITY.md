# Güvenlik

## Güvenlik açığı bildirimi

Bu projede bir güvenlik açığı bulduysan **lütfen herkese açık bir issue açma.**
Bunun yerine proje sahibine doğrudan ulaş ve şunları paylaş:

- Açığın türü ve etkilenen dosya/satır
- Yeniden üretim adımları (silahlandırılmış exploit değil, minimum doğrulama)
- Tahmini etki

Bildirimlere makul sürede dönüş yapılmaya çalışılır. Açık kapatılana kadar
detayları paylaşma.

---

## Dağıtım öncesi zorunlu adımlar

**Mevcut dağıtım ortamı: Render** (`Procfile` → `web: gunicorn app:app`, tek worker).

> ### ⚠️ SIRALAMA
> `SECRET_KEY` ortam değişkeni **yeni kod deploy edilmeden önce** tanımlanmalıdır.
> Ters sırada deploy başarısız olur (uygulama açılmayı reddeder). Render bu durumda
> son çalışan sürümü ayakta tuttuğu için servis düşmez, ancak deploy boşa gider.

### 1. `SECRET_KEY` tanımla (ZORUNLU — ilk adım)

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Çıkan değeri **Render Dashboard → servis → Environment → Add Environment Variable**
altında `SECRET_KEY` adıyla tanımla.

**Bu değişken tanımlı değilse uygulama üretimde bilerek açılmaz.** Bu bir hata
değil, kasıtlı bir `fail-closed` davranıştır: sabit veya varsayılan bir anahtar,
oturum cookie'lerinin taklit edilmesine izin verir.

### 2. `GEMINI_API_KEY` tanımla

Google AI Studio'dan alınır; Render ortam değişkeni olarak tutulur. Yalnızca
sunucuda okunur, tarayıcıya hiçbir şekilde gönderilmez.

### 3. Billing hard cap kur (ÇOK ÖNEMLİ)

Her `/analiz` isteği **iki**, her `/chat` isteği **bir** ücretli Gemini çağrısı
tetikler. Koddaki hız sınırı bir saldırıyı yavaşlatır ama **faturayı kesin
olarak durduran şey Google Cloud tarafındaki limittir.**

- Google Cloud Console → Billing → Budgets & alerts → bütçe alarmı
- Gemini API için günlük istek kotası tanımla

### 4. HTTPS — Render'da ek işlem gerekmiyor

Render `.onrender.com` alan adlarına otomatik TLS sağlar ve HTTP→HTTPS
yönlendirmesini kendisi yapar. Uygulamanın gönderdiği
`Strict-Transport-Security` header'ı ve `SESSION_COOKIE_SECURE=True` ayarı bu
ortamda sorunsuz çalışır. *(Başka bir platforma taşınırsa bu doğrulanmalıdır.)*

### 5. Worker sayısını artırma

`Procfile`'daki başlangıç komutu tek worker ile çalışır ve bu bilinçlidir:
hız sınırı sayacı (`Flask-Limiter memory://`) ve belge deposu
(`utils.security.BelgeDeposu`) process belleğinde tutulur. `-w 2` veya üstü
eklenirse ikisi de worker'lar arasında bölünür ve zayıflar. Ölçeklendirme
gerekirse önce ikisini de Redis'e taşı — bkz. `SECURITY_AUDIT/04-open-risks.md`.

---

## Geliştirici kuralları

Bu kurallar denetimde bulunan gerçek açıklardan türetilmiştir. İhlal edilirse
kapatılan açıklar geri gelir.

### 🔴 LLM çıktısı GÜVENİLMEZ VERİDİR

Modelin ne üreteceğini belirleyen girdi, kullanıcının yüklediği PDF'in
içeriğidir. Bir saldırgan PDF'e görünmez talimatlar gömerek (beyaz zemine beyaz
yazı) modelin çıktısını yönlendirebilir.

- **Model çıktısını asla sanitize etmeden HTML'e basma.**
  Her zaman `utils.security.llm_ciktisini_temizle()` kullan.
- **Model çıktısını asla bir JavaScript bağlamına koyma** — `onclick`, `<script>`
  içi, `eval`, `innerHTML`. Değeri `data-*` özniteliğiyle taşı, DOM API ile oku.
- **Model çıktısının yapısına güvenme.** JSON dönüyorsa şema doğrulamasından
  geçir (`utils.security.quiz_ciktisini_dogrula` örneğine bak).

### 🔴 Kullanıcı içeriğini prompt'a çıplak gömme

Güvenilmez metin her zaman `<belge>` / `<soru>` gibi sınırlayıcılarla
çevrelenmeli ve `utils.security.guvenilmez_metni_hazirla()` ile sınırlayıcı
kaçışına karşı temizlenmelidir. Görev talimatı içerikten **sonra** tekrarlanmalı.

Prompt sertleştirmesi tek başına yeterli değildir — asıl savunma çıktı
sanitizasyonudur.

### 🔴 Belge içeriğini oturuma yazma

Flask oturumu client-side bir cookie'dir: **imzalıdır ama şifreli değildir.**
Belge metni sunucuda tutulur (`utils.security.BelgeDeposu`), istemciye yalnızca
tahmin edilemez bir kimlik gider.

### 🔴 Ham istisna metnini kullanıcıya gösterme

Dosya yolları, kütüphane sürümleri ve upstream API detayları sızdırır.
Ayrıntı `logger.exception()` ile loga, kullanıcıya genel mesaj.

### 🔴 Belge içeriğini veya model çıktısını loglama

KVKK/GDPR. `print()` kullanma; `logging` kullan ve yalnızca metrik bilgi yaz
(uzunluk, sayı), içerik değil.

### 🔴 Dosya tipini uzantıdan doğrulama

Uzantı da `Content-Type` da tamamen istemci kontrolündedir.
`utils.security.pdf_imzasi_gecerli_mi()` ile içerikten doğrula.

### 🔴 Yeni endpoint eklerken

- Hız sınırı ekle (`@limiter.limit(...)`) — özellikle LLM çağrısı yapıyorsa
- Girdinin tipini ve uzunluğunu doğrula (`isinstance` + uzunluk kontrolü)
- `request.get_json()` yerine `request.get_json(silent=True)` + tip kontrolü

### Güvenlik limitleri tek yerdedir

Tüm limitler `utils/security.py` içindedir. Yeni bir "sihirli sayı" ekleme,
oraya koy.

---

## Testler

Güvenlik regresyon testleri `tests/test_security.py` içindedir. Her test somut
bir denetim bulgusuna karşılık gelir; bir test kırmızıya dönerse ilgili açık
geri gelmiş demektir.

```bash
pip install pytest
python -m pytest tests/ -q
```

**Kod değişikliğinden sonra bu testleri çalıştırmadan dağıtım yapma.**

---

## Denetim raporları

Bu kod tabanı 1 Eylül 2026'da tam kapsamlı bir güvenlik denetiminden geçti;
23 bulgunun 14'ü (3 Critical, 4 High, 7 Medium) kapatıldı.

Ayrıntılı denetim çıktıları bu depoda **değil**, ayrı bir paket olarak
teslim edilmiştir (`guvenlik-raporlari`):

| Dosya | İçerik |
|---|---|
| `OKU-BENI-ONCE.md` | Teknik olmayan özet — önce bu okunmalı |
| `SECURITY_AUDIT/00-inventory.md` | Envanter, saldırı yüzeyi, veri akışı, güven sınırları |
| `SECURITY_AUDIT/01-threat-model.md` | Saldırgan profilleri ve senaryolar |
| `SECURITY_AUDIT/02-findings.md` | Detaylı bulgu raporu (23 bulgu) |
| `SECURITY_AUDIT/03-remediation-log.md` | Ne düzeltildi, ne düzeltilmedi, neden |
| `SECURITY_AUDIT/04-open-risks.md` | Kabul edilen riskler ve gelecek adımlar |

Bu dosyada geçen "bkz. 04-open-risks.md" gibi atıflar o pakete işaret eder.
