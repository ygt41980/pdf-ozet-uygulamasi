"""
PDF dosyalarından metin ve temel meta veri çıkarmak için yardımcı fonksiyonlar.
Metin çıkarma işlemi için pdfplumber kütüphanesi kullanılır.
"""

import logging

import pdfplumber

from utils.security import MAKSIMUM_METIN_KARAKTER, MAKSIMUM_SAYFA_SAYISI

logger = logging.getLogger(__name__)


class PDFOkumaHatasi(Exception):
    """PDF okunurken/parse edilirken oluşan hataları temsil eder.

    Bu istisnanın mesajı doğrudan son kullanıcıya gösterilir; bu yüzden
    ASLA ham istisna metni, dosya yolu veya kütüphane iç detayı içermemelidir.
    """
    pass


def pdf_metnini_cikar(dosya_yolu: str) -> dict:
    """
    Verilen PDF dosyasından metni ve temel bilgileri çıkarır.

    Args:
        dosya_yolu: Diskteki PDF dosyasının tam yolu.

    Returns:
        Aşağıdaki alanları içeren bir sözlük:
            - "metin": PDF'ten çıkarılan tüm metin (str)
            - "sayfa_sayisi": Toplam sayfa sayısı (int)
            - "sayfa_metinleri": Her sayfanın metnini içeren liste (list[str])

    Raises:
        PDFOkumaHatasi: Dosya açılamazsa, kaynak sınırları aşılırsa veya
        hiç metin çıkarılamazsa.
    """
    sayfa_metinleri = []

    try:
        with pdfplumber.open(dosya_yolu) as pdf:
            sayfa_sayisi = len(pdf.pages)

            if sayfa_sayisi == 0:
                raise PDFOkumaHatasi("PDF dosyasında hiç sayfa bulunamadı.")

            # Sayfa sayısı, dosya boyutundan BAĞIMSIZ bir kaynak tüketimi
            # göstergesidir: boyut sınırına uyan bir PDF on binlerce sayfa
            # içerebilir. pdfplumber sayfa başına ayrıntılı karakter/çizgi
            # nesneleri ürettiği için bu doğrudan bellek ve CPU tüketimidir.
            # gunicorn tek senkron worker ile çalıştığında bir tek istek tüm
            # uygulamayı cevapsız bırakabilir.
            if sayfa_sayisi > MAKSIMUM_SAYFA_SAYISI:
                raise PDFOkumaHatasi(
                    f"PDF çok fazla sayfa içeriyor. En fazla {MAKSIMUM_SAYFA_SAYISI} "
                    f"sayfalık dosyalar işlenebilir (bu dosya: {sayfa_sayisi} sayfa)."
                )

            toplam_karakter = 0
            for sayfa in pdf.pages:
                sayfa_metni = sayfa.extract_text() or ""

                # Az sayfalı ama devasa metin içeren dosyalara karşı ikinci
                # tavan. Sayfa limiti tek başına yeterli değildir.
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
        # Ham istisna metni kullanıcıya SIZDIRILMAZ: pdfminer/pdfplumber
        # istisnaları dosya yolu ve kütüphane iç detayı içerebilir.
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
