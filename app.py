"""
PDF Analiz ve Özetleme Web Uygulaması
--------------------------------------
Kullanıcıların yüklediği PDF dosyalarını okuyup:
  - Sayfa/kelime/karakter sayısı gibi temel istatistikleri çıkarır,
  - En sık geçen anahtar kelimeleri bulur,
  - Gemini ile metni özetler ve çalışma soruları üretir.

Çalıştırmak için:
    pip install -r requirements.txt
    python app.py
Sonra tarayıcıdan http://127.0.0.1:5000 adresine gidin.

ÖNEMLİ: Üretimde SECRET_KEY ve GEMINI_API_KEY ortam değişkenleri tanımlı
olmalıdır. Ayrıntı için .env.example ve SECURITY.md dosyalarına bakın.
"""

import logging
import os
import secrets
import tempfile
import uuid

from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename

from utils.pdf_utils import pdf_metnini_cikar, PDFOkumaHatasi
from utils.security import (
    MAKSIMUM_DOSYA_BOYUTU_MB,
    MAKSIMUM_SORU_UZUNLUGU,
    BelgeDeposu,
    llm_ciktisini_temizle,
    pdf_imzasi_gecerli_mi,
    quiz_ciktisini_dogrula,
)
from utils.summarizer import (
    metni_ozetle,
    anahtar_kelimeleri_bul,
    metin_istatistiklerini_hesapla,
    soru_uret,
    pdfye_soru_sor,
)


# ---------------------------------------------------------------------------
# Yapılandırma
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IZIN_VERILEN_UZANTILAR = {"pdf"}

GELISTIRME_MODU = os.environ.get("FLASK_DEBUG", "0") == "1"

# Yüklemeler proje ağacının DIŞINA, geçici dizine yazılır.
# Nedenleri: (1) proje klasöründe kullanıcı belgesi birikmez ve yanlışlıkla
# paylaşılan/commit'lenen bir arşive karışmaz, (2) Vercel gibi salt-okunur
# dosya sistemine sahip ortamlarda uygulama açılışta çökmez.
UPLOAD_KLASORU = os.environ.get(
    "UPLOAD_FOLDER", os.path.join(tempfile.gettempdir(), "ygtpdf_uploads")
)

app = Flask(__name__)

# --- SECRET_KEY: fail-closed ------------------------------------------------
# Sabit/varsayılan bir anahtar, oturum cookie'sinin imzasının taklit
# edilebilmesi demektir. Anahtar yoksa uygulama SESSİZCE güvensiz bir
# varsayılana düşmek yerine hiç açılmamalıdır.
_gizli_anahtar = os.environ.get("SECRET_KEY")
if not _gizli_anahtar:
    if GELISTIRME_MODU:
        # Yalnızca lokal geliştirme. Her yeniden başlatmada değişir, kalıcı değildir.
        _gizli_anahtar = secrets.token_hex(32)
        app.logger.warning(
            "SECRET_KEY tanımlı değil; geliştirme modu için geçici anahtar üretildi. "
            "Uygulama her yeniden başladığında oturumlar sıfırlanır."
        )
    else:
        raise RuntimeError(
            "SECRET_KEY ortam değişkeni tanımlı değil.\n"
            "Üretimde sabit veya varsayılan bir anahtarla çalışmak, oturum "
            "cookie'lerinin taklit edilmesine izin verir.\n"
            "Yeni bir anahtar üretmek için:\n"
            '    python -c "import secrets; print(secrets.token_hex(32))"\n'
            "Ardından bu değeri SECRET_KEY ortam değişkeni olarak tanımlayın."
        )

app.config["SECRET_KEY"] = _gizli_anahtar
app.config["UPLOAD_FOLDER"] = UPLOAD_KLASORU
app.config["MAX_CONTENT_LENGTH"] = MAKSIMUM_DOSYA_BOYUTU_MB * 1024 * 1024  # MB -> byte

# --- Oturum cookie'si sertleştirmesi ----------------------------------------
app.config.update(
    # XSS durumunda cookie'nin JavaScript'ten okunmasını engeller.
    SESSION_COOKIE_HTTPONLY=True,
    # Cookie'nin şifresiz HTTP üzerinden gitmesini engeller.
    # Lokal geliştirme HTTPS kullanmadığı için orada kapalıdır.
    SESSION_COOKIE_SECURE=not GELISTIRME_MODU,
    # Üçüncü taraf sitelerin kullanıcı adına istek attırmasını (CSRF) zorlaştırır.
    SESSION_COOKIE_SAMESITE="Lax",
)

os.makedirs(UPLOAD_KLASORU, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG if GELISTIRME_MODU else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# --- Hız sınırlama ----------------------------------------------------------
# Her /analiz isteği İKİ, her /chat isteği BİR Gemini çağrısı tetikler; yani
# her istek doğrudan para harcar. Sınır olmadan anonim bir saldırgan basit bir
# betikle faturayı istediği kadar şişirebilir.
# NOT: memory:// tek process varsayar. Kod tarafındaki bu sınır saldırıyı
# yavaşlatır; faturayı KESİN olarak durduran şey Google Cloud tarafındaki
# billing hard cap'tir. Bkz. SECURITY.md
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["120 per hour"],
    storage_uri="memory://",
)

# Belge metni sunucuda tutulur; istemciye yalnızca kimliği gider.
BELGE_DEPOSU = BelgeDeposu()


# ---------------------------------------------------------------------------
# Güvenlik header'ları
# ---------------------------------------------------------------------------

@app.after_request
def guvenlik_basliklari_ekle(response):
    """Her yanıta güvenlik header'larını ekler.

    CSP burada ikinci savunma katmanıdır: LLM çıktısı sanitize edilse bile
    (bkz. utils/security.py) bir enjeksiyon gerçekleşirse, img-src ve
    connect-src 'self' ile sınırlandığı için verinin dışarı sızdırılması
    engellenir.

    'unsafe-inline' şu an gereklidir çünkü template'ler inline <script> ve
    inline style öznitelikleri kullanıyor. Bunlar static/ altında harici
    dosyalara taşındığında bu iki direktiften 'unsafe-inline' kaldırılmalıdır.
    Bilinçli bir tavizdir, unutulmuş bir eksik değil.
    """
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not GELISTIRME_MODU:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


# ---------------------------------------------------------------------------
# Yardımcı fonksiyonlar
# ---------------------------------------------------------------------------

def dosya_uzantisi_izinli_mi(dosya_adi: str) -> bool:
    return (
        "." in dosya_adi
        and dosya_adi.rsplit(".", 1)[1].lower() in IZIN_VERILEN_UZANTILAR
    )


# ---------------------------------------------------------------------------
# Rotalar
# ---------------------------------------------------------------------------

@app.route("/")
def anasayfa():
    """Yükleme formunun gösterildiği ana sayfa."""
    return render_template("index.html", maks_boyut=MAKSIMUM_DOSYA_BOYUTU_MB)


@app.route("/analiz", methods=["POST"])
@limiter.limit("5 per minute; 30 per hour")
def analiz_et():
    """Yüklenen PDF'i işleyip sonuç sayfasını döndürür."""

    if "pdf_dosya" not in request.files:
        flash("Lütfen bir PDF dosyası seçin.", "hata")
        return redirect(url_for("anasayfa"))

    dosya = request.files["pdf_dosya"]

    if dosya.filename == "":
        flash("Herhangi bir dosya seçilmedi.", "hata")
        return redirect(url_for("anasayfa"))

    if not dosya_uzantisi_izinli_mi(dosya.filename):
        flash("Yalnızca .pdf uzantılı dosyalar yüklenebilir.", "hata")
        return redirect(url_for("anasayfa"))

    # Uzantı kontrolü tek başına yetersizdir: uzantı da Content-Type da
    # tamamen istemci kontrolündedir. Dosyanın gerçekten PDF olduğu
    # içeriğinden doğrulanır ve geçersizse parser'a hiç ulaşmaz.
    if not pdf_imzasi_gecerli_mi(dosya.stream):
        app.logger.info("Geçersiz PDF imzası nedeniyle yükleme reddedildi.")
        flash("Dosya geçerli bir PDF değil. Lütfen gerçek bir PDF dosyası yükleyin.", "hata")
        return redirect(url_for("anasayfa"))

    # Aynı isimli dosyaların üzerine yazılmasını önlemek için benzersiz bir ad üret.
    guvenli_ad = secure_filename(dosya.filename)
    benzersiz_ad = f"{uuid.uuid4().hex}_{guvenli_ad}"
    dosya_yolu = os.path.join(app.config["UPLOAD_FOLDER"], benzersiz_ad)

    try:
        dosya.save(dosya_yolu)

        cikti = pdf_metnini_cikar(dosya_yolu)
        metin = cikti["metin"]

        # Belge metni SUNUCUDA tutulur; oturum cookie'sine yalnızca kimliği
        # yazılır. Metnin kendisi imzalı ama şifresiz bir cookie ile tarayıcıya
        # gönderilseydi, cookie'yi görebilen herkes belgeyi okuyabilirdi.
        session["belge_id"] = BELGE_DEPOSU.ekle(metin)

        istatistikler = metin_istatistiklerini_hesapla(metin)
        ozet_seviyesi = request.form.get("ozet_seviyesi", "orta")

        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor() as executor:
            gelecek_ozet = executor.submit(metni_ozetle, metin, ozet_seviyesi)
            gelecek_quiz = executor.submit(soru_uret, metin, 5)

            ozet = llm_ciktisini_temizle(gelecek_ozet.result())
            quiz_sorulari = quiz_ciktisini_dogrula(gelecek_quiz.result())

        anahtar_kelimeler = anahtar_kelimeleri_bul(metin, adet=10)

        return render_template(
            "result.html",
            dosya_adi=guvenli_ad,
            sayfa_sayisi=cikti["sayfa_sayisi"],
            istatistikler=istatistikler,
            ozet=ozet,
            anahtar_kelimeler=anahtar_kelimeler,
            quiz=quiz_sorulari,
        )


        return render_template(
            "result.html",
            dosya_adi=guvenli_ad,
            sayfa_sayisi=cikti["sayfa_sayisi"],
            istatistikler=istatistikler,
            ozet=ozet,
            anahtar_kelimeler=anahtar_kelimeler,
            quiz=quiz_sorulari,
        )

    except PDFOkumaHatasi as hata:
        # PDFOkumaHatasi mesajları kasıtlı olarak kullanıcı dostudur ve iç
        # durum (dosya yolu, kütüphane detayı) sızdırmaz; gösterilebilir.
        flash(str(hata), "hata")
        return redirect(url_for("anasayfa"))

    except Exception:
        # Ham istisna metni kullanıcıya GÖSTERİLMEZ: dosya sistemi yolları,
        # kütüphane sürümleri ve upstream API detayları sızdırabilir.
        # Ayrıntı yalnızca sunucu loguna yazılır.
        app.logger.exception("Analiz sırasında beklenmeyen hata")
        flash("Dosya işlenirken beklenmeyen bir hata oluştu. Lütfen tekrar deneyin.", "hata")
        return redirect(url_for("anasayfa"))

    finally:
        # Gizlilik ve disk alanı için işlem bitince yüklenen dosyayı sil.
        # Hata durumunda da çalışması için finally bloğundadır.
        try:
            if os.path.exists(dosya_yolu):
                os.remove(dosya_yolu)
        except OSError:
            app.logger.warning("Geçici dosya silinemedi.", exc_info=True)


@app.route("/chat", methods=["POST"])
@limiter.limit("10 per minute; 60 per hour")
def chat():
    """Yüklenen PDF hakkında soru yanıtlar.

    NOT: Bu endpoint şu an hiçbir arayüz tarafından çağrılmıyor. Kullanılmaya
    devam edilmeyecekse tamamen kaldırılması en güvenli seçenektir — var
    olmayan bir saldırı yüzeyi en güvenli yüzeydir.
    """
    data = request.get_json(silent=True)

    # Gövde bir JSON nesnesi değilse (örneğin liste), .get() AttributeError
    # fırlatır ve 500 döner. Tip kontrolü bunu engeller.
    if not isinstance(data, dict):
        return jsonify({"cevap": "Geçersiz istek gövdesi."}), 400

    soru = data.get("soru")
    if not isinstance(soru, str) or not (1 <= len(soru.strip()) <= MAKSIMUM_SORU_UZUNLUGU):
        return (
            jsonify({"cevap": f"Soru 1-{MAKSIMUM_SORU_UZUNLUGU} karakter arasında olmalıdır."}),
            400,
        )

    metin = BELGE_DEPOSU.al(session.get("belge_id"))
    if not metin:
        return jsonify({"cevap": "Lütfen önce bir PDF dosyası yükleyin."}), 400

    # Yanıt bugün JSON olarak dönüyor, ancak ileride bir arayüz bunu DOM'a
    # yazarsa sanitize edilmemiş model çıktısı yeniden XSS'e dönüşür.
    cevap = llm_ciktisini_temizle(pdfye_soru_sor(metin, soru.strip()))
    return jsonify({"cevap": cevap})


# ---------------------------------------------------------------------------
# Hata işleyicileri
# ---------------------------------------------------------------------------

@app.errorhandler(413)
def dosya_cok_buyuk(hata):
    app.logger.info("Boyut sınırını aşan yükleme reddedildi.")
    flash(f"Dosya çok büyük. Maksimum boyut {MAKSIMUM_DOSYA_BOYUTU_MB} MB.", "hata")
    return render_template("index.html", maks_boyut=MAKSIMUM_DOSYA_BOYUTU_MB), 413


@app.errorhandler(429)
def hiz_siniri_asildi(hata):
    """Hız sınırı aşımı. Güvenlik olayı olarak loglanır."""
    app.logger.warning("Hız sınırı aşıldı: %s %s", get_remote_address(), request.path)

    if request.path == "/chat":
        return jsonify({"cevap": "Çok fazla istek gönderildi. Lütfen biraz bekleyin."}), 429

    flash("Çok fazla istek gönderildi. Lütfen birkaç dakika sonra tekrar deneyin.", "hata")
    return render_template("index.html", maks_boyut=MAKSIMUM_DOSYA_BOYUTU_MB), 429


if __name__ == "__main__":
    # Yerelde çalıştırırken debug modunu açmak için: FLASK_DEBUG=1 python app.py
    # UYARI: Werkzeug'un debug arayüzü konsol üzerinden kod çalıştırmaya izin
    # verir; üretimde ASLA açılmamalıdır.
    # Render/gunicorn'da bu blok hiç çalışmaz; gunicorn uygulamayı "app:app"
    # importuyla doğrudan çalıştırır (bkz. Procfile).
    app.run(debug=GELISTIRME_MODU)
