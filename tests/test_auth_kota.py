"""Giriş (Google/PKCE) ve günlük kota testleri. Dış servislere çıkılmaz."""

import io
import pytest


@pytest.fixture
def client(anonim_client):
    """Bu dosyada 'client' girişsiz istemcidir."""
    return anonim_client

from conftest import minimal_pdf

import app as app_modulu
from utils import auth_db

KULLANICI = {"id": "k1", "email": "a@b.c"}


def giris_yapmis(flask_app):
    istemci = flask_app.test_client()
    with istemci.session_transaction() as oturum:
        oturum["kullanici"] = dict(KULLANICI)
    return istemci


# --- Girişsiz erişim -------------------------------------------------------

def test_analiz_girissiz_yonlendirir(client):
    yanit = client.post("/analiz", data={})
    assert yanit.status_code == 302


def test_chat_girissiz_yonlendirir(client):
    yanit = client.post("/chat", json={"soru": "test"})
    assert yanit.status_code == 302


# --- Kota: kota_kullan() ---------------------------------------------------

class SahteRpc:
    def __init__(self, veri):
        self.veri = veri

    def execute(self):
        return type("R", (), {"data": self.veri})()


class SahteIstemci:
    def __init__(self, donen):
        self.donen = donen
        self.cagrilar = []

    def rpc(self, ad, parametreler):
        self.cagrilar.append((ad, parametreler))
        return SahteRpc(self.donen)


def test_kota_hak_varsa_true(monkeypatch):
    sahte = SahteIstemci(True)
    monkeypatch.setattr(auth_db, "sb", lambda: sahte)
    assert auth_db.kota_kullan("u1") is True
    ad, p = sahte.cagrilar[0]
    assert ad == "kota_kullan_atomik"
    assert p["p_user_id"] == "u1"
    assert p["p_limit"] == auth_db.GUNLUK_LIMIT


def test_kota_dolunca_false(monkeypatch):
    monkeypatch.setattr(auth_db, "sb", lambda: SahteIstemci(False))
    assert auth_db.kota_kullan("u1") is False


def test_kota_bos_donerse_false(monkeypatch):
    monkeypatch.setattr(auth_db, "sb", lambda: SahteIstemci(None))
    assert auth_db.kota_kullan("u1") is False


# --- Kota: /analiz entegrasyonu -------------------------------------------

def test_kota_dolunca_analiz_reddedilir_ve_gemini_cagrilmaz(flask_app, monkeypatch):
    monkeypatch.setattr(app_modulu, "kota_kullan", lambda uid: False)

    def olmamali(*a, **k):
        raise AssertionError("Kota doluyken Gemini çağrıldı")

    monkeypatch.setattr(app_modulu, "metni_ozetle", olmamali)
    monkeypatch.setattr(app_modulu, "soru_uret", olmamali)

    istemci = giris_yapmis(flask_app)
    yanit = istemci.post(
        "/analiz",
        data={"pdf_dosya": (io.BytesIO(minimal_pdf()), "a.pdf")},
        content_type="multipart/form-data",
    )
    assert yanit.status_code == 302
    with istemci.session_transaction() as oturum:
        mesajlar = [m for _, m in oturum.get("_flashes", [])]
    assert any("hakkınız doldu" in m for m in mesajlar)


# --- Giriş akışı -----------------------------------------------------------

def test_giris_google_supabase_a_yonlendirir(client, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proje.supabase.co")
    yanit = client.get("/giris/google")
    assert yanit.status_code == 302
    konum = yanit.headers["Location"]
    assert konum.startswith("https://proje.supabase.co/auth/v1/authorize")
    assert "code_challenge=" in konum
    assert "code_verifier" not in konum  # verifier asla URL'ye girmez
    with client.session_transaction() as oturum:
        assert "pkce" in oturum


def test_auth_donus_code_yoksa_giris_olmaz(client):
    client.get("/auth/donus")
    with client.session_transaction() as oturum:
        assert "kullanici" not in oturum


def test_auth_donus_pkce_yoksa_giris_olmaz(client):
    client.get("/auth/donus?code=abc")
    with client.session_transaction() as oturum:
        assert "kullanici" not in oturum


class SahteAuth:
    def __init__(self, hata=False):
        self.hata = hata

    def exchange_code_for_session(self, parametreler):
        if self.hata:
            raise RuntimeError("supabase hatası")
        kullanici = type("U", (), {"id": "k1", "email": "a@b.c"})()
        return type("S", (), {"user": kullanici})()


def test_auth_donus_basarili_giris(client, monkeypatch):
    sahte = type("Sb", (), {"auth": SahteAuth()})()
    monkeypatch.setattr(app_modulu, "sb", lambda: sahte)
    with client.session_transaction() as oturum:
        oturum["pkce"] = "verifier"
    client.get("/auth/donus?code=abc")
    with client.session_transaction() as oturum:
        assert oturum["kullanici"] == {"id": "k1", "email": "a@b.c"}
        assert "pkce" not in oturum  # tek kullanımlık


def test_auth_donus_supabase_hatasinda_giris_olmaz(client, monkeypatch):
    sahte = type("Sb", (), {"auth": SahteAuth(hata=True)})()
    monkeypatch.setattr(app_modulu, "sb", lambda: sahte)
    with client.session_transaction() as oturum:
        oturum["pkce"] = "verifier"
    client.get("/auth/donus?code=abc")
    with client.session_transaction() as oturum:
        assert "kullanici" not in oturum


def test_cikis_oturumu_temizler(flask_app):
    istemci = giris_yapmis(flask_app)
    istemci.get("/cikis")
    with istemci.session_transaction() as oturum:
        assert "kullanici" not in oturum