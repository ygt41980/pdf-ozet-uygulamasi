"""
Güvenlik sabitleri ve yardımcıları.
-----------------------------------
Güvenlikle ilgili tüm limitler ve doğrulama fonksiyonları tek dosyada toplanır.
Amaç: bir limiti değiştirmek gerektiğinde kodun her yerini taramak zorunda
kalmamak ve "sihirli sayı"ların kod içinde dağılmasını önlemek.

Buradaki her fonksiyonun üstünde NEDEN böyle yazıldığını anlatan bir not var.
Bu notlar bilerek bırakılmıştır: ileride biri "gereksiz görünüyor" diye
silmesin.
"""

import re
import secrets
import threading
import time
from collections import OrderedDict

import bleach

# ---------------------------------------------------------------------------
# Limitler
# ---------------------------------------------------------------------------

# Yükleme boyutu. Flask'ın MAX_CONTENT_LENGTH ayarını besler; asıl zorlayıcı
# kontrol budur, istemci tarafındaki JS kontrolü yalnızca kullanıcı deneyimi
# içindir ve kolayca atlanabilir.
MAKSIMUM_DOSYA_BOYUTU_MB = 50

# Sayfa sayısı, dosya boyutundan BAĞIMSIZ bir kaynak tüketimi göstergesidir:
# 50 MB sınırına rahatça uyan bir PDF on binlerce sayfa içerebilir ve
# pdfplumber sayfa başına ayrıntılı nesneler ürettiği için bellek patlar.
MAKSIMUM_SAYFA_SAYISI = 300

# Az sayfalı ama devasa metin içeren dosyalara karşı ikinci tavan.
MAKSIMUM_METIN_KARAKTER = 2_000_000

# /chat endpoint'ine gelen sorunun uzunluk sınırı. Sınırsız bırakılırsa
# saldırgan istek başına maksimum token maliyetini dayatabilir.
MAKSIMUM_SORU_UZUNLUGU = 2000

# Sayfa/karakter limitleri kötü niyetli bir PDF'i büyüklük olarak sınırlar,
# ama az sayfalı/az karakterli fakat aşırı karmaşık (iç içe nesneler, ağır
# fontlar vb.) bir PDF yine de ayrıştırma sırasında CPU'yu uzun süre meşgul
# edebilir. Bu, gerçek bir duvar-saati (wall-clock) üst sınırı — aşılırsa
# ayrıştırma ayrı bir process'te gerçekten sonlandırılır (bkz. pdf_utils.py).
MAKSIMUM_PDF_ISLEME_SANIYE = 30

# Sunucu tarafı belge deposunun ömrü ve kapasitesi. Sınırsız bir depo
# doğrudan bir bellek tüketimi (DoS) vektörüdür.
BELGE_TTL_SANIYE = 30 * 60
BELGE_DEPOSU_KAPASITESI = 50

# Tüm geçerli PDF dosyaları bu imza ile başlar.
PDF_IMZASI = b"%PDF-"


# ---------------------------------------------------------------------------
# Dosya doğrulama
# ---------------------------------------------------------------------------

def pdf_imzasi_gecerli_mi(akis) -> bool:
    """Dosyanın gerçekten PDF olup olmadığını içeriğinden doğrular.

    Uzantı (`.pdf`) ve Content-Type header'ı tamamen istemci kontrolündedir;
    ikisi de sahtelenebilir. Dosya tipi doğrulaması dosya ADINA değil, dosyanın
    KENDİSİNE dayanmalıdır. Akış konumu okumadan sonra geri alınır, aksi halde
    dosya diske eksik yazılır.
    """
    baslangic = akis.tell()
    try:
        bas = akis.read(len(PDF_IMZASI))
    finally:
        akis.seek(baslangic)
    return bas == PDF_IMZASI


# ---------------------------------------------------------------------------
# LLM çıktısı sanitizasyonu
# ---------------------------------------------------------------------------

# Model çıktısında YALNIZCA biçimlendirme etiketlerine izin verilir.
# Öznitelik listesi bilerek BOŞTUR: bu sayede on* olay işleyicileri
# (onerror, onload...) ve src/href gibi veri sızdırmaya elverişli alanlar
# yapısal olarak imkânsız hale gelir — kara liste tutmaya gerek kalmaz.
IZIN_VERILEN_ETIKETLER = ["br", "b", "strong", "i", "em", "u", "ul", "ol", "li", "p", "span"]


def llm_ciktisini_temizle(metin: str) -> str:
    """LLM çıktısını HTML'e basmadan önce allow-list ile temizler.

    KRİTİK: Model çıktısı GÜVENİLMEZ VERİDİR. Modelin ne üreteceğini belirleyen
    girdi, kullanıcının yüklediği PDF'in içeriğidir; PDF'e görünmez talimatlar
    gömen bir saldırgan modele istediği HTML'i ürettirebilir (dolaylı prompt
    injection). Sistem prompt'u modelden zaten <br> üretmesini istediği için
    model HTML üretmeye hazır durumdadır — bu, saldırının başarı oranını
    artırır. Bu fonksiyon zincirin son ve en önemli halkasıdır.
    """
    if not isinstance(metin, str):
        return ""
    return bleach.clean(
        metin,
        tags=IZIN_VERILEN_ETIKETLER,
        attributes={},
        protocols=[],
        strip=True,
    )


# ---------------------------------------------------------------------------
# LLM çıktısı şema doğrulaması
# ---------------------------------------------------------------------------

def quiz_ciktisini_dogrula(veri) -> list:
    """Modelin ürettiği quiz JSON'unu template'e vermeden önce doğrular.

    Dil modeli çıktısının yapısı garanti edilemez. Doğrulama olmadan, beklenen
    şemadan sapan tek bir yanıt (liste yerine nesne, eksik 'siklar' alanı vb.)
    Jinja döngüsünde 500 hatasına yol açar ve başarıyla işlenmiş bir PDF'in
    TÜM sonucu kaybolur. Uymayan elemanlar sessizce atılır ki tek bozuk soru
    sayfanın tamamını düşürmesin.
    """
    if not isinstance(veri, list):
        return []

    gecerli = []
    for oge in veri:
        if not isinstance(oge, dict):
            continue
        soru = oge.get("soru")
        siklar = oge.get("siklar")
        cevap = oge.get("cevap")
        if (
            isinstance(soru, str) and soru.strip()
            and isinstance(siklar, list) and 2 <= len(siklar) <= 8
            and all(isinstance(s, str) for s in siklar)
            and isinstance(cevap, str) and cevap.strip()
        ):
            gecerli.append({"soru": soru, "siklar": siklar, "cevap": cevap})
    return gecerli


# ---------------------------------------------------------------------------
# Prompt sertleştirme
# ---------------------------------------------------------------------------

# Modele gönderilecek güvenilmez içerikten, sınırlayıcı etiketi taklit eden
# metinleri ayıklar. Saldırgan PDF'e "</belge>" yazarak sınırlayıcıdan kaçmayı
# deneyebilir; bu regex o kaçışı kapatır.
_SINIRLAYICI_KACIS = re.compile(r"</?\s*(belge|soru|sistem[^>]*)\s*>", re.IGNORECASE)


def guvenilmez_metni_hazirla(metin: str) -> str:
    """Prompt'a gömülecek güvenilmez metni sınırlayıcı kaçışına karşı temizler."""
    return _SINIRLAYICI_KACIS.sub("", metin or "")


# ---------------------------------------------------------------------------
# Sunucu tarafı belge deposu
# ---------------------------------------------------------------------------

class BelgeDeposu:
    """PDF metnini SUNUCU BELLEĞİNDE tutan, TTL ve kapasite sınırlı depo.

    NEDEN: Flask'ın varsayılan oturumu client-side bir cookie'dir ve İMZALIDIR
    ama ŞİFRELİ DEĞİLDİR. Belge metnini oturuma yazmak, kullanıcının gizli
    belgesini düz okunabilir biçimde tarayıcıya ve her istekte ağa göndermek
    demektir. Ayrıca cookie'ler ~4 KB ile sınırlıdır; birkaç sayfalık herhangi
    bir PDF bu sınırı aşar ve cookie tarayıcı tarafından sessizce atılır.

    Bu depoda istemciye yalnızca tahmin edilemez bir kimlik gider; metin
    sunucudan hiç çıkmaz.

    SINIR: Bellek içi olduğu için tek process varsayar. Mevcut kurulum (Render +
    gunicorn tek worker) bu varsayımı karşılar. Procfile'a -w 2 veya üstü
    eklenirse ya da serverless bir platforma geçilirse istekler farklı
    process'lere düşer ve /chat "önce PDF yükleyin" döner — yani düzeltme
    öncesi davranışa geri dönülür, daha kötüsü olmaz. O noktada kalıcı çözüm
    bu depoyu (ve Flask-Limiter'ı) Redis'e taşımaktır.
    """

    def __init__(self, kapasite: int = BELGE_DEPOSU_KAPASITESI, ttl_saniye: int = BELGE_TTL_SANIYE):
        self._kayitlar: "OrderedDict[str, tuple]" = OrderedDict()
        self._kapasite = kapasite
        self._ttl = ttl_saniye
        self._kilit = threading.Lock()

    def ekle(self, metin: str) -> str:
        """Metni saklar ve tahmin edilemez bir kimlik döndürür."""
        # uuid4 yerine secrets: kimlik oturum tanımlayıcı gibi davrandığı için
        # kriptografik olarak güçlü bir üreteç kullanılır.
        belge_id = secrets.token_urlsafe(24)
        with self._kilit:
            self._suresi_dolanlari_at()
            self._kayitlar[belge_id] = (time.time(), metin)
            # Kapasite aşılırsa en eski kayıt düşer (FIFO).
            while len(self._kayitlar) > self._kapasite:
                self._kayitlar.popitem(last=False)
        return belge_id

    def al(self, belge_id):
        """Kimliğe karşılık gelen metni döndürür; yoksa veya süresi dolduysa None."""
        if not isinstance(belge_id, str) or not belge_id:
            return None
        with self._kilit:
            self._suresi_dolanlari_at()
            kayit = self._kayitlar.get(belge_id)
        return kayit[1] if kayit else None

    def _suresi_dolanlari_at(self) -> None:
        simdi = time.time()
        suresi_dolan = [k for k, (zaman, _) in self._kayitlar.items() if simdi - zaman > self._ttl]
        for anahtar in suresi_dolan:
            self._kayitlar.pop(anahtar, None)
