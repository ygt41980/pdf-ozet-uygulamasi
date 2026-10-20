"""Geçmiş analizler: listeleme bağlantısı ve kayıt detay sayfası."""

import app as app_modulu


class _Sonuc:
    def __init__(self, data):
        self.data = data


class SahteTablo:
    """Zincirleme sorguyu taklit eder; uygulanan eq() filtrelerini gerçekten uygular."""

    def __init__(self, kayitlar):
        self.kayitlar = kayitlar
        self.filtreler = {}

    def select(self, *a, **k):
        return self

    def eq(self, alan, deger):
        self.filtreler[alan] = deger
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        veri = [k for k in self.kayitlar
                if all(k.get(a) == d for a, d in self.filtreler.items())]
        return _Sonuc(veri)


class SahteSb:
    def __init__(self, kayitlar):
        self.kayitlar = kayitlar

    def table(self, ad):
        return SahteTablo(self.kayitlar)


def kayit(**ek):
    temel = {
        "id": "1",
        "user_id": "test-kullanici",  # conftest.KULLANICI["id"]
        "filename": "ders-notu.pdf",
        "page_count": 3,
        "summary_level": "orta",
        "summary": "Birinci madde<br>İkinci madde",
        "keywords": [["kelime", 4]],
        "questions": [],
        "created_at": "2026-10-20T10:00:00+00:00",
    }
    temel.update(ek)
    return temel


def sb_kur(monkeypatch, *kayitlar):
    monkeypatch.setattr(app_modulu, "sb", lambda: SahteSb(list(kayitlar)))


def test_gecmis_detay_girissiz_yonlendirir(anonim_client):
    yanit = anonim_client.get("/gecmis/1")
    assert yanit.status_code == 302


def test_gecmis_detay_kendi_kaydini_gosterir(client, monkeypatch):
    sb_kur(monkeypatch, kayit())
    yanit = client.get("/gecmis/1")
    assert yanit.status_code == 200
    metin = yanit.get_data(as_text=True)
    assert "ders-notu.pdf" in metin
    assert "Birinci madde" in metin


def test_gecmis_detayda_sohbet_gizlidir(client, monkeypatch):
    """Eski kayıtta belge metni sunucuda yok; sohbet yanlış belgeye cevap vermemeli."""
    sb_kur(monkeypatch, kayit())
    metin = client.get("/gecmis/1").get_data(as_text=True)
    assert "sohbet-form" not in metin


def test_baskasinin_kaydi_gorulmez(client, monkeypatch):
    sb_kur(monkeypatch, kayit(user_id="baska-kullanici"))
    yanit = client.get("/gecmis/1")
    assert yanit.status_code == 302


def test_olmayan_kayit_yonlendirir(client, monkeypatch):
    sb_kur(monkeypatch)
    yanit = client.get("/gecmis/999")
    assert yanit.status_code == 302


def test_gecmis_ozetteki_script_temizlenir(client, monkeypatch):
    sb_kur(monkeypatch, kayit(summary="<script>alert(1)</script>Güvenli metin"))
    metin = client.get("/gecmis/1").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in metin
    assert "Güvenli metin" in metin


def test_anasayfa_gecmis_kaydina_baglanti_verir(client, monkeypatch):
    sb_kur(monkeypatch, kayit())
    metin = client.get("/").get_data(as_text=True)
    assert "/gecmis/1" in metin
    assert "ders-notu.pdf" in metin
