import re
import google.generativeai as genai
import json
import os
from collections import Counter

STOPWORDS = {
    # Türkçe
    "ve", "veya", "ile", "bu", "bir", "de", "da", "mı", "mi", "mu", "mü",
    "ki", "ne", "gibi", "için", "çok", "daha", "en", "ama", "fakat",
    "ancak", "çünkü", "eğer", "ise", "olan", "olarak", "üzere", "kadar",
    "sonra", "önce", "her", "hiç", "bütün", "tüm", "biz", "siz", "onlar",
    "ben", "sen", "o", "bunu", "buna", "bunun", "şu", "şey", "diye",
    "göre", "arasında", "sırasında", "rağmen", "dolayı", "yalnızca",
    "sadece", "bazı", "birçok", "hem", "ya", "ya da",
    "ten", "tan", "le", "la", "den", "dan", "dır", "dir", "dur", "dür",
    "sayfa", "page",
    # İngilizce
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on",
    "for", "with", "as", "by", "at", "is", "are", "was", "were", "be",
    "been", "being", "this", "that", "these", "those", "it", "its",
    "from", "which", "who", "whom", "we", "you", "they", "he", "she",
    "not", "no", "so", "than", "then", "there", "their", "have", "has",
    "had", "will", "would", "can", "could", "should", "may", "might"
}

CUMLE_SONU_REGEX = re.compile(r'(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ0-9])')
KELIME_REGEX = re.compile(r'[A-Za-zÇÇğĞıİöÖşŞüÜ0-9]{3,}')

# 1. METİN TEMİZLEME (PREPROCESSING)
def metni_temizle(metin: str) -> str:
    """PDF'ten gelen sayfa numaralarını, altbilgi/üstbilgileri ve gereksiz boşlukları temizler."""
    metin = re.sub(r'(?i)(sayfa|page)\s*\d+(\s*/\s*\d+)?', '', metin)
    metin = re.sub(r'^\s*\d+\s*$', '', metin, flags=re.MULTILINE)
    metin = re.sub(r'\s+', ' ', metin).strip()
    return metin

def _cumlelere_ayir(metin: str) -> list:
    temiz_metin = metni_temizle(metin)
    cumleler = CUMLE_SONU_REGEX.split(temiz_metin)
    return [c.strip() for c in cumleler if len(c.strip()) > 20]

def _kelime_frekanslarini_hesapla(cumleler: list) -> Counter:
    frekanslar = Counter()
    for cumle in cumleler:
        kelimeler = KELIME_REGEX.findall(cumle.lower())
        for kelime in kelimeler:
            if kelime not in STOPWORDS:
                frekanslar[kelime] += 1
    return frekanslar

# 2. AKILLI METİN BÖLME (CHUNKING)
def metni_parcalara_bol(cumleler: list, parca_boyutu: int = 12) -> list:
    """Uzun PDF'leri parçalara bölerek her bölümden eşit oranda önemli bilgi çekilmesini sağlar."""
    return [cumleler[i:i + parca_boyutu] for i in range(0, len(cumleler), parca_boyutu)]

# 3. KATEGORİZE ÖZET FORMATI & ANA İŞLEV
def metni_ozetle(metin: str, cumle_sayisi: int = 5) -> str:
    cumleler = _cumlelere_ayir(metin)
    
    if not cumleler:
        return "Metin özet oluşturmak için çok kısa veya geçersiz."
    
    if len(cumleler) <= cumle_sayisi:
        secilen_cumleler = cumleler
    else:
        # Akıllı Bölme (Chunking) ile metnin sonlarındaki bilgilerin kaybolması engellenir
        parcalar = metni_parcalara_bol(cumleler, parca_boyutu=12)
        secilen_cumleler = []
        
        frekanslar = _kelime_frekanslarini_hesapla(cumleler)
        en_yuksek_frekans = max(frekanslar.values()) if frekanslar else 1

        for parca in parcalar:
            parca_skorlari = []
            for idx, cumle in enumerate(parca):
                kelimeler = KELIME_REGEX.findall(cumle.lower())
                skor = sum(frekanslar.get(k, 0) for k in kelimeler) / en_yuksek_frekans if kelimeler else 0
                skor = skor / (len(kelimeler) ** 0.5) if kelimeler else 0
                parca_skorlari.append((idx, skor, cumle))
            
            parca_skorlari.sort(key=lambda x: x[1], reverse=True)
            if parca_skorlari:
                secilen_cumleler.append(parca_skorlari[0][2])
        
        if len(secilen_cumleler) > cumle_sayisi:
            secilen_cumleler = secilen_cumleler[:cumle_sayisi]

    # Ana Fikir ve Önemli Noktalar
    ana_fikir = secilen_cumleler[0] if secilen_cumleler else ""
    detaylar = secilen_cumleler[1:] if len(secilen_cumleler) > 1 else secilen_cumleler
    maddeler = "\n".join([f"• {c}" for c in detaylar])
    
    # Terimler ve Kavramlar
    terimler_listesi = anahtar_kelimeleri_bul(metin, adet=5)
    terimler_text = "\n".join([f"• *{t[0].capitalize()}*: Metinde en çok öne çıkan anahtar kavram ({t[1]} kez geçiyor)." for t in terimler_listesi])

    formatli_ozet = f"""📌 *Ana Fikir:*
{ana_fikir}

💡 *Önemli Noktalar:*
{maddeler}

🧠 *Terimler ve Kavramlar:*
{terimler_text}
"""
    return formatli_ozet

def anahtar_kelimeleri_bul(metin: str, adet: int = 10) -> list:
    cumleler = _cumlelere_ayir(metin)
    frekanslar = _kelime_frekanslarini_hesapla(cumleler) if cumleler else Counter(KELIME_REGEX.findall(metin.lower()))
    temiz_frekanslar = Counter({k: v for k, v in frekanslar.items() if k not in STOPWORDS})
    return temiz_frekanslar.most_common(adet)

def metin_istatistiklerini_hesapla(metin: str) -> dict:
    temiz = metni_temizle(metin)
    kelime_sayisi = len(re.findall(r'\S+', temiz))
    karakter_sayisi = len(temiz)
    tahmini_okuma_suresi_dk = max(1, round(kelime_sayisi / 200))
    
    return {
        "kelime_sayisi": kelime_sayisi,
        "karakter_sayisi": karakter_sayisi,
        "tahmini_okuma_suresi_dk": tahmini_okuma_suresi_dk
    }
def soru_uret(metin: str, adet: int = 5) -> list:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return []
        
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-3.6-flash')
    
    prompt = f"""
    Aşağıdaki metne dayanarak öğrencinin çalışması için {adet} adet çoktan seçmeli soru üret.
    Çıktıyı kesinlikle her biri şu anahtarları içeren bir JSON listesi olarak ver:
    - "soru": Soru metni
    - "siklar": 4 şıklı bir liste (örneğin ["A) ...", "B) ...", "C) ...", "D) ..."])
    - "cevap": Doğru şık (örneğin "A) ...")
    
    Metin:
    {metin[:4000]}
    """
    try:
       response = model.generate_content(prompt)
        raw_text = response.text.strip()
       if "json" in raw_text:
            raw_text = raw_text.split("json")[1].split("")[0].strip()
        elif "" in raw_text:
            raw_text = raw_text.split("")[1].split("")[0].strip()     
        return json.loads(raw_text)
    except Exception as e:
        print("Soru üretme hatası:", e)
        return []
        
