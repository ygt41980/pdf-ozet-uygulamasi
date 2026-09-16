import logging
import signal

import fitz  # pdfplumber yerine PyMuPDF kullanıyoruz

from utils.security import (
    MAKSIMUM_METIN_KARAKTER,
    MAKSIMUM_PDF_ISLEME_SANIYE,
    MAKSIMUM_SAYFA_SAYISI,
)

logger = logging.getLogger(__name__)


class PDFOkumaHatasi(Exception):
    pass


class _ZamanAsimi(Exception):
    """Yalnızca bu modül içinde kullanılan, dışarı sızmayan iç sinyal."""


def _zaman_asimi_isaretle(signum, frame):
    raise _ZamanAsimi()


def pdf_metnini_cikar(dosya_yolu: str) -> dict:
    """PDF'i sayfa/karakter sınırları VE gerçek bir üst süre sınırıyla ayrıştırır.

    NEDEN signal.alarm (ayrı process DEĞİL): Önceki sürüm ayrı bir process
    açıyordu (fork) — bu, çalışan process'in belleğini pratikte ikiye
    katlayabilir. Render'ın ücretsiz planındaki 512 MB gibi dar bir bellek
    sınırında bu, worker'ın OOM (out-of-memory) nedeniyle SIGKILL almasına
    yol açabilir — ki tam olarak bu oldu. signal.alarm aynı process içinde
    çalışır, ekstra bellek tüketmez. Bedeli: gerçekten donmuş bir C
    çağrısını (fitz) zorla öldüremez, sadece Python seviyesinde bir istisna
    fırlatır — ama sayfa/karakter limitleri zaten çoğu senaryoyu önlediği
    için bu ölçekli bir dağıtım için yeterli bir denge.

    SINIR: signal.alarm yalnızca ANA thread'de çalışır (Python kısıtlaması).
    gunicorn sync worker (bkz. Procfile: --workers/--threads YOK) her
    isteği ana thread'de işlediği için burada güvenlidir. İleride
    `--threads` ile gthread worker'a geçilirse bu fonksiyon thread'ler
    arasında ValueError fırlatabilir — o noktada tekrar ayrı bir mekanizma
    gerekir.
    """
    onceki_isleyici = signal.signal(signal.SIGALRM, _zaman_asimi_isaretle)
    signal.alarm(MAKSIMUM_PDF_ISLEME_SANIYE)

    try:
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

        except _ZamanAsimi:
            logger.warning("PDF işleme %s saniyeyi aştığı için durduruldu.", MAKSIMUM_PDF_ISLEME_SANIYE)
            raise PDFOkumaHatasi(
                f"PDF işleme {MAKSIMUM_PDF_ISLEME_SANIYE} saniyeyi aştığı için durduruldu. "
                "Dosya aşırı karmaşık olabilir; daha küçük veya daha basit bir belge deneyin."
            )
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
    finally:
        # Alarm'ı iptal et ve önceki isleyiciyi geri yükle — aksi halde bu
        # process'teki bambaşka bir istek, ilgisiz bir anda bu alarm'dan
        # etkilenebilir.
        signal.alarm(0)
        signal.signal(signal.SIGALRM, onceki_isleyici)
