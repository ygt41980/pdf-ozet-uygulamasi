"""
PDF dosyalarından metin ve temel meta veri çıkarmak için yardımcı fonksiyonlar.
Metin çıkarma işlemi için pdfplumber kütüphanesi kullanılır.
"""

import pdfplumber


class PDFOkumaHatasi(Exception):
    """PDF okunurken/parse edilirken oluşan hataları temsil eder."""
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
        PDFOkumaHatasi: Dosya açılamazsa veya hiç metin çıkarılamazsa.
    """
    sayfa_metinleri = []

    try:
        with pdfplumber.open(dosya_yolu) as pdf:
            sayfa_sayisi = len(pdf.pages)

            if sayfa_sayisi == 0:
                raise PDFOkumaHatasi("PDF dosyasında hiç sayfa bulunamadı.")

            for sayfa in pdf.pages:
                sayfa_metni = sayfa.extract_text() or ""
                sayfa_metinleri.append(sayfa_metni)

    except PDFOkumaHatasi:
        raise
    except Exception as hata:
        raise PDFOkumaHatasi(f"PDF dosyası okunurken bir hata oluştu: {hata}")

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
