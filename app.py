"""
PDF Analiz ve Özetleme Web Uygulaması
--------------------------------------
Kullanıcıların yüklediği PDF dosyalarını okuyup:
  - Sayfa/kelime/karakter sayısı gibi temel istatistikleri çıkarır,
  - En sık geçen anahtar kelimeleri bulur,
  - Frekans tabanlı bir yöntemle metni özetler.

Çalıştırmak için:
    pip install -r requirements.txt
    python app.py
Sonra tarayıcıdan http://127.0.0.1:5000 adresine gidin.
"""

import os
import uuid

from flask import Flask, jsonify, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename

from utils.pdf_utils import pdf_metnini_cikar, PDFOkumaHatasi
from utils.summarizer import (
    metni_ozetle,
    anahtar_kelimeleri_bul,
    metin_istatistiklerini_hesapla,
soru_uret,
)

# ---------------------------------------------------------------------------
# Yapılandırma
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_KLASORU = os.path.join(BASE_DIR, "uploads")
IZIN_VERILEN_UZANTILAR = {"pdf"}
MAKSIMUM_DOSYA_BOYUTU_MB = 20

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "gelistirme-icin-gizli-anahtar")
app.config["UPLOAD_FOLDER"] = UPLOAD_KLASORU
app.config["MAX_CONTENT_LENGTH"] = MAKSIMUM_DOSYA_BOYUTU_MB * 1024 * 1024  # MB -> byte

os.makedirs(UPLOAD_KLASORU, exist_ok=True)


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

    # Aynı isimli dosyaların üzerine yazılmasını önlemek için benzersiz bir ad üret.
    guvenli_ad = secure_filename(dosya.filename)
    benzersiz_ad = f"{uuid.uuid4().hex}_{guvenli_ad}"
    dosya_yolu = os.path.join(app.config["UPLOAD_FOLDER"], benzersiz_ad)

    try:
        dosya.save(dosya_yolu)

        cikti = pdf_metnini_cikar(dosya_yolu)
        metin = cikti["metin"]

        istatistikler = metin_istatistiklerini_hesapla(metin)
        ozet = metni_ozetle(metin, cumle_sayisi=6)
        anahtar_kelimeler = anahtar_kelimeleri_bul(metin, adet=10)
      quiz_sorulari = soru_uret(metin, adet=5)
        return render_template(
            "result.html",
            dosya_adi=guvenli_ad,
            sayfa_sayisi=cikti["sayfa_sayisi"],
            istatistikler=istatistikler,
            ozet=ozet,
            anahtar_kelimeler=anahtar_kelimeler,
          quiz=quiz_sorulari
        )

    except PDFOkumaHatasi as hata:
        flash(str(hata), "hata")
        return redirect(url_for("anasayfa"))

    except Exception as hata:
        flash(f"Beklenmeyen bir hata oluştu: {hata}", "hata")
        return redirect(url_for("anasayfa"))

    finally:
        # Gizlilik ve disk alanı için işlem bitince yüklenen dosyayı sil.
        if os.path.exists(dosya_yolu):
            os.remove(dosya_yolu)


@app.errorhandler(413)
def dosya_cok_buyuk(hata):
    flash(f"Dosya çok büyük. Maksimum boyut: {MAKSIMUM_DOSYA_BOYUTU_MB} MB.", "hata")
    return redirect(url_for("anasayfa"))


if __name__ == "__main__":
    # Yerelde çalıştırırken debug modunu açmak için: FLASK_DEBUG=1 python app.py
    # Render'da bu blok hiç çalışmaz; gunicorn uygulamayı "app:app" importuyla
    # doğrudan çalıştırır (bkz. Procfile).
    debug_modu = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_modu)
