import pytest

from conftest import minimal_pdf
from utils.pdf_utils import PDFOkumaHatasi, pdf_metnini_cikar


def test_sayfa_limiti_asilinca_reddedilir(tmp_path, monkeypatch):
    import utils.pdf_utils as pdf_utils

    monkeypatch.setattr(pdf_utils, "MAKSIMUM_SAYFA_SAYISI", 0)
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(minimal_pdf())

    with pytest.raises(PDFOkumaHatasi) as hata:
        pdf_metnini_cikar(str(pdf))
    assert "sayfa" in str(hata.value).lower()


def test_zaman_asimi_durdurulur(tmp_path, monkeypatch):
    import time

    from utils import pdf_utils

    monkeypatch.setattr(pdf_utils, "MAKSIMUM_PDF_ISLEME_SANIYE", 1)

    def _yavas_ac(*args, **kwargs):
        time.sleep(5)

    monkeypatch.setattr(pdf_utils.fitz, "open", _yavas_ac)
    pdf = tmp_path / "buyuk.pdf"
    pdf.write_bytes(minimal_pdf())

    with pytest.raises(PDFOkumaHatasi, match="saniyeyi aştığı"):
        pdf_metnini_cikar(str(pdf))