"""
Harici bir API gerektirmeyen, kelime frekansına dayalı basit bir
"extractive" (metinden cümle seçen) özetleyici.

Yöntem:
1. Metin cümlelere bölünür.
2. Anlamsız/çok sık geçen kelimeler (stopwords) filtrelenir.
3. Kalan kelimelerin frekansına göre bir skor tablosu çıkarılır.
4. Her cümle, içindeki kelimelerin skorlarına göre puanlanır.
5. En yüksek puanlı N cümle, orijinal sıralarıyla özet olarak döndürülür.

Bu yöntem büyük dil modeli veya internet bağlantısı gerektirmez;
bu yüzden hızlı ve bağımlılığı azdır. Uzun/karmaşık metinlerde
gelişmiş bir LLM özetleyicisi kadar başarılı olmayabilir.
"""

import re
from collections import Counter

# Türkçe ve İngilizce için en sık geçen, anlam taşımayan kelimeler.
# Karma dokümanlarda da makul sonuç verebilmesi için iki dil birlikte tutuldu.
STOPWORDS = {
    # Türkçe
    "ve", "veya", "ile", "bu", "bir", "de", "da", "mi", "mı", "mu", "mü",
    "ki", "ne", "gibi", "için", "çok", "daha", "en", "ama", "fakat",
    "ancak", "çünkü", "eğer", "ise", "olan", "olarak", "üzere", "kadar",
    "sonra", "önce", "her", "hiç", "bütün", "tüm", "biz", "siz", "onlar",
    "ben", "sen", "o", "bunu", "buna", "bunun", "şu", "şey", "diye",
    "yani", "değil", "var", "yok", "oldu", "olur", "olmuş", "olarak",
    "göre", "arasında", "sırasında", "rağmen", "dolayı", "yalnızca",
    "sadece", "bazı", "birçok", "hem", "ya", "ya da", "ki", "mı", "mi",
    "nin", "nın", "nun", "nün", "in", "ın", "un", "ün", "den", "dan",
    "ten", "tan", "le", "la",
    # İngilizce
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on",
    "for", "with", "as", "by", "at", "is", "are", "was", "were", "be",
    "been", "being", "this", "that", "these", "those", "it", "its",
    "from", "which", "who", "whom", "we", "you", "they", "he", "she",
    "not", "no", "so", "than", "then", "there", "their", "have", "has",
    "had", "will", "would", "can", "could", "should", "may", "might",
}

CUMLE_SONU_REGEX = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÇĞİÖŞÜ0-9])")
KELIME_REGEX = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü]{3,}")


def _cumlelere_ayir(metin: str) -> list:
    """Metni kabaca cümlelere böler. Çok kısa/anlamsız parçaları eler."""
    temiz_metin = re.sub(r"\s+", " ", metin).strip()
    cumleler = CUMLE_SONU_REGEX.split(temiz_metin)
    return [c.strip() for c in cumleler if len(c.strip()) > 20]


def _kelime_frekanslarini_hesapla(cumleler: list) -> Counter:
    """Stopword'leri çıkararak kelime frekans tablosu oluşturur."""
    frekanslar = Counter()
    for cumle in cumleler:
        kelimeler = KELIME_REGEX.findall(cumle.lower())
        for kelime in kelimeler:
            if kelime not in STOPWORDS:
                frekanslar[kelime] += 1
    return frekanslar


def metni_ozetle(metin: str, cumle_sayisi: int = 5) -> str:
    """
    Verilen metni, en önemli `cumle_sayisi` kadar cümleyi seçerek özetler.

    Args:
        metin: Özetlenecek ham metin.
        cumle_sayisi: Özette yer alacak maksimum cümle sayısı.

    Returns:
        Orijinal sıralamaya sadık, seçilmiş cümlelerden oluşan özet metin.
        Metin çok kısaysa (istenen cümle sayısından azsa) olduğu gibi döner.
    """
    cumleler = _cumlelere_ayir(metin)

    if not cumleler:
        return "Metin çok kısa olduğu için özet oluşturulamadı."

    if len(cumleler) <= cumle_sayisi:
        return " ".join(cumleler)

    frekanslar = _kelime_frekanslarini_hesapla(cumleler)

    if not frekanslar:
        # Hiç anlamlı kelime bulunamadıysa ilk cümleleri döndür.
        return " ".join(cumleler[:cumle_sayisi])

    en_yuksek_frekans = max(frekanslar.values())

    cumle_skorlari = []
    for index, cumle in enumerate(cumleler):
        kelimeler = KELIME_REGEX.findall(cumle.lower())
        if not kelimeler:
            skor = 0.0
        else:
            skor = sum(frekanslar.get(k, 0) for k in kelimeler) / en_yuksek_frekans
            # Çok uzun cümlelerin sırf kelime sayısından ötürü öne çıkmasını
            # engellemek için kelime sayısına bölerek normalize ediyoruz.
            skor = skor / (len(kelimeler) ** 0.5)

        cumle_skorlari.append((index, skor, cumle))

    en_iyi_cumleler = sorted(cumle_skorlari, key=lambda x: x[1], reverse=True)[:cumle_sayisi]
    # Okunabilirlik için orijinal sıraya göre diz.
    en_iyi_cumleler.sort(key=lambda x: x[0])

    return " ".join(c[2] for c in en_iyi_cumleler)


def anahtar_kelimeleri_bul(metin: str, adet: int = 10) -> list:
    """
    Metindeki en sık geçen (stopword olmayan) kelimeleri döndürür.

    Args:
        metin: Analiz edilecek metin.
        adet: Döndürülecek anahtar kelime sayısı.

    Returns:
        (kelime, tekrar_sayisi) çiftlerinden oluşan bir liste,
        en sık geçenden en aza doğru sıralı.
    """
    cumleler = _cumlelere_ayir(metin)
    frekanslar = _kelime_frekanslarini_hesapla(cumleler) if cumleler else Counter()

    if not frekanslar:
        # Cümle bölünmesi başarısız olsa bile kelime frekansını dene.
        kelimeler = KELIME_REGEX.findall(metin.lower())
        frekanslar = Counter(k for k in kelimeler if k not in STOPWORDS)

    return frekanslar.most_common(adet)


def metin_istatistiklerini_hesapla(metin: str) -> dict:
    """Kelime sayısı, karakter sayısı ve tahmini okuma süresini hesaplar."""
    kelime_sayisi = len(re.findall(r"\S+", metin))
    karakter_sayisi = len(metin)
    # Ortalama okuma hızı: dakikada ~200 kelime.
    tahmini_okuma_suresi_dk = max(1, round(kelime_sayisi / 200))

    return {
        "kelime_sayisi": kelime_sayisi,
        "karakter_sayisi": karakter_sayisi,
        "tahmini_okuma_suresi_dk": tahmini_okuma_suresi_dk,
    }
