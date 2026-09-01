"""
Test yapılandırması.

Uygulama SECRET_KEY yoksa bilerek açılmaz (fail-closed, bkz. SEV-001).
Bu yüzden app modülü import EDİLMEDEN ÖNCE ortam değişkeni tanımlanmalıdır.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# app import edilmeden önce ayarlanmalı.
os.environ.setdefault("SECRET_KEY", "test-icin-sabit-anahtar-yalnizca-testte")
os.environ.pop("GEMINI_API_KEY", None)  # Testlerde dış API'ye çıkılmaz.

import pytest  # noqa: E402

import app as app_modulu  # noqa: E402


@pytest.fixture
def flask_app():
    app_modulu.app.config["TESTING"] = True
    # Hız sınırı testleri dışında kapalı tutulur; aksi halde testler
    # birbirinin kotasını tüketir.
    app_modulu.limiter.enabled = False
    yield app_modulu.app
    app_modulu.limiter.enabled = False


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture
def limitli_client(flask_app):
    """Hız sınırının açık olduğu istemci."""
    app_modulu.limiter.enabled = True
    app_modulu.limiter.reset()
    yield flask_app.test_client()
    app_modulu.limiter.enabled = False
    app_modulu.limiter.reset()


def minimal_pdf(metin: str = "Guvenlik testi icin ornek belge metni") -> bytes:
    """Metin çıkarılabilir, geçerli ve minimal bir PDF üretir.

    Harici bir kütüphaneye bağımlı olmamak için xref tablosu elle kurulur.
    """
    icerik = f"BT /F1 24 Tf 72 700 Td ({metin}) Tj ET".encode("latin-1")

    nesneler = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length " + str(len(icerik)).encode() + b">>\nstream\n" + icerik + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]

    cikti = bytearray(b"%PDF-1.4\n")
    ofsetler = []
    for i, govde in enumerate(nesneler, start=1):
        ofsetler.append(len(cikti))
        cikti += f"{i} 0 obj\n".encode() + govde + b"\nendobj\n"

    xref_ofseti = len(cikti)
    cikti += f"xref\n0 {len(nesneler) + 1}\n".encode()
    cikti += b"0000000000 65535 f \n"
    for ofset in ofsetler:
        cikti += f"{ofset:010d} 00000 n \n".encode()
    cikti += f"trailer\n<</Size {len(nesneler) + 1}/Root 1 0 R>>\n".encode()
    cikti += f"startxref\n{xref_ofseti}\n%%EOF\n".encode()

    return bytes(cikti)
