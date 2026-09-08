import logging
import fitz  # pdfplumber yerine PyMuPDF kullanıyoruz

from utils.security import MAKSIMUM_METIN_KARAKTER, MAKSIMUM_SAYFA_SAYISI

logger = logging.getLogger(__name__)

class PDFOkumaHatasi(Exception):
    pass

def pdf_metnini_cikar(dosya_yolu: str) -> dict:
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

