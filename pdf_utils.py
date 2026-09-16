import logging
import multiprocessing as mp

import fitz  # pdfplumber yerine PyMuPDF kullanıyoruz

from utils.security import (
    MAKSIMUM_METIN_KARAKTER,
    MAKSIMUM_PDF_ISLEME_SANIYE,
    MAKSIMUM_SAYFA_SAYISI,
)

logger = logging.getLogger(__name__)


class PDFOkumaHatasi(Exception):
    pass


def _pdf_metnini_cikar_ic(dosya_yolu: str) -> dict:
    """Gerçek ayrıştırma mantığı. Ayrı bir process içinde çalıştırılır
    (bkz. pdf_metnini_cikar) ki aşırı karmaşık bir PDF ayrıştırmayı
    donduramasın; süre aşılırsa bu process'in tamamı sonlandırılabilir.
    """
    sayfa_metinleri = []

    try:
        # fitz (PyMuPDF) ile okuma işlemi başlatılır
        with fitz.open(dosya_yolu) as pdf:
            sayfa_sayisi = len(pdf)

            if sayfa_sayisi == 0:
                raise PDFOkumaHatasi("PDF dosyasında hiç sayfa bulunamadı.")

            if sayfa_sayisi > MAKSIMUM_SAYFA_SAYISI:
                raise PDFOkumaHatasi(
                    f"PDF çok fazla sayfa içeriyor. En fazla {MAKSIMUM_SAYFA_SAYISI} "
                    f"sayfalık dosyalar işlenebilir (bu dosya: {sayfa_sayisi} sayfa)."
                )

            toplam_karakter = 0
            for sayfa in pdf:
                sayfa_metni = sayfa.get_text() or ""
                toplam_karakter += len(sayfa_metni)

                if toplam_karakter > MAKSIMUM_METIN_KARAKTER:
                    raise PDFOkumaHatasi(
                        "PDF içeriği işlenemeyecek kadar büyük. "
                        "Lütfen daha küçük bir belge deneyin."
                    )

                sayfa_metinleri.append(sayfa_metni)

    except PDFOkumaHatasi:
        raise
    except Exception:
        logger.warning("PDF ayrıştırılamadı.", exc_info=True)
        raise PDFOkumaHatasi(
            "PDF dosyası okunamadı. Dosya bozuk, şifreli ya da desteklenmeyen "
            "bir biçimde olabilir."
        )

    tam_metin = "\n".join(sayfa_metinleri).strip()

    if not tam_metin:
        raise PDFOkumaHatasi(
            "PDF içinden metin çıkarılamadı. Dosya taranmış bir görüntü "
            "(scanned) olabilir ya da yalnızca görsellerden oluşuyor olabilir."
        )

    return {
        "metin": tam_metin,
        "sayfa_sayisi": sayfa_sayisi,
        "sayfa_metinleri": sayfa_metinleri,
    }


def _alt_islemde_calistir(dosya_yolu: str, kuyruk: "mp.Queue") -> None:
    """_pdf_metnini_cikar_ic'i çağırıp sonucu/hatayı kuyruğa yazar.
    Modül seviyesinde tanımlı olmalı ki multiprocessing bunu pickle'layıp
    alt process'e aktarabilsin.
    """
    try:
        sonuc = _pdf_metnini_cikar_ic(dosya_yolu)
        kuyruk.put(("ok", sonuc))
    except PDFOkumaHatasi as hata:
        kuyruk.put(("hata", str(hata)))
    except Exception:
        logger.warning("Alt process'te beklenmeyen hata.", exc_info=True)
        kuyruk.put((
            "hata",
            "PDF dosyası okunamadı. Dosya bozuk, şifreli ya da desteklenmeyen "
            "bir biçimde olabilir.",
        ))


def pdf_metnini_cikar(dosya_yolu: str) -> dict:
    """PDF'i ayrı bir process içinde, gerçek bir üst süre sınırıyla ayrıştırır.

    NEDEN AYRI PROCESS: Sayfa sayısı ve toplam karakter sınırı (bkz.
    utils/security.py) çoğu kötü niyetli/bozuk dosyayı yakalar, ama az
    sayfalı/az metinli fakat dahili yapısı aşırı karmaşık bir PDF yine de
    fitz'i uzun süre CPU'da tutabilir. Python'da bir thread'i güvenli şekilde
    zorla durdurmanın yolu yoktur — yalnızca beklemeyi bırakmak, sızan
    thread'i arkada çalışır bırakır ve kaynağı boşaltmaz. Ayrı bir process
    ise `terminate()` ile gerçekten öldürülebilir; bu yüzden gerçek bir
    kaynak-tükenimi (DoS) savunması burada, thread değil process sınırıdır.
    """
    kuyruk: "mp.Queue" = mp.Queue()
    islem = mp.Process(target=_alt_islemde_calistir, args=(dosya_yolu, kuyruk), daemon=True)
    islem.start()
    islem.join(timeout=MAKSIMUM_PDF_ISLEME_SANIYE)

    if islem.is_alive():
        islem.terminate()
        islem.join(timeout=5)
        if islem.is_alive():
            # terminate() SIGTERM gönderir; nadiren yanıt vermeyen bir process
            # için son çare olarak SIGKILL.
            islem.kill()
            islem.join()
        logger.warning("PDF işleme %s saniyeyi aştığı için sonlandırıldı.", MAKSIMUM_PDF_ISLEME_SANIYE)
        raise PDFOkumaHatasi(
            f"PDF işleme {MAKSIMUM_PDF_ISLEME_SANIYE} saniyeyi aştığı için durduruldu. "
            "Dosya aşırı karmaşık olabilir; daha küçük veya daha basit bir belge deneyin."
        )

    if kuyruk.empty():
        # Process normal bitti ama kuyrukta veri yok: OOM-kill, segfault vb.
        raise PDFOkumaHatasi(
            "PDF dosyası okunamadı (işleme süreci beklenmedik şekilde sonlandı)."
        )

    durum, veri = kuyruk.get()
    if durum == "hata":
        raise PDFOkumaHatasi(veri)
    return veri
