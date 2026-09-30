"""Hata özelliğinin iki saf fonksiyonu: prompt inşası ve yanıt ayrıştırma.

Neden ayrı modül: `cli.py` ince kalsın, mantık test edilebilsin.
Neden JSON değil düz metin: çıktı terminalde okunacak, iki satır başlığı
ayrıştırması LLM'in en güvenilir biçim uyumudur (docs/API.md).
"""

from __future__ import annotations

import re

# "yok" çeşitleri düzeltme yok demek — LLM'in sık kullandığı eş anlamlılar.
_YOK_DEGERLER = frozenset(
    {"yok", "yoktur", "yok.", "yok,", "none", "n/a", "-", "—", "gerek yok", "gerekmiyor"}
)

_BASLIKLAR = (("TEŞHİS", "teshis"), ("DÜZELTME", "duzeltme"))

# LLM bazen "DÜZELTME:" satırını unutur; o zaman "şunu deneyin:" ipucu
# satırlarından komutu geri çıkarmaya çalışıyoruz. Uydurma yapmamak için bu
# çıkarım kullanıcıya "ham yanıt" olarak ayrıştırılmış biçimde gösterilir.
_DUZELTME_IPUCU_RE = re.compile(
    r"^\s*(?:şunu\s+)?(?:deneyin|dene|çalıştır|çalıştırmak)\s*[:：]\s*`?(?P<komut>[^`\n]+)`?\s*$",
    re.IGNORECASE,
)


def _tr_kucult(metin: str) -> str:
    """Türkçe'ye duyarlı küçültme.

    Python'un `str.lower()`'ı 'İ' (U+0130) harfini 'i' yapmaz, 'i' + birleşen
    nokta yapar; bu yüzden `re.IGNORECASE` ile "TEŞHİS"/"teshis" eşleşmez.
    Başlık karşılaştırmasında buna güvenmiyoruz.
    """
    return (
        metin.replace("İ", "i")
        .replace("I", "i")  # str.lower() zaten I -> i yapar; yine de açık
        .replace("Ş", "ş")
        .lower()
    )


def prompt_olustur(komut: str, cikis_kodu: int) -> str:
    """Başarısız komut + çıkış kodu için Türkçe teşhis prompt'u kurar.

    Kapsam sınırı (bilerek, docs/API.md): stderr/stdout otomatik
    yakalanmaz — yalnızca komut metni ve çıkış kodu gönderilir.
    """
    return (
        "Sen bir terminal hata asistanısın. Türkçe ve KISA cevap ver.\n"
        "\n"
        f"Komut: {komut}\n"
        f"Çıkış kodu: {cikis_kodu}\n"
        "\n"
        "Sorunun en olası 1-3 cümlelik teşhisini ver. Eğer tek bir komutla "
        "düzeltilebiliyorsa o komutu tek satır olarak yaz; düzeltilemiyorsa "
        "\"yok\" yaz.\n"
        "\n"
        "TAM OLARAK şu biçimde cevap ver, başka hiçbir şey yazma:\n"
        "TEŞHİS: <1-3 cümle>\n"
        "DÜZELTME: <tek satır komut ya da \"yok\">\n"
    )


def _baslik_ayir(satir: str) -> tuple[str | None, str]:
    """Satırı `(tur, kalan_içerik)` biçimine ayırır.

    `TEŞHİS:`, `teshis:`, `**TEŞHİS:**`, `** teşhis **:` — hepsini kabul eder.
    Başlık değilse `(None, "")` döner.
    """
    # Baştaki madde işaretleri / kalınlık işaretleri biçim kalıntısıdır.
    govde = satir.strip().lstrip("*• \t")
    for baslik, tur in _BASLIKLAR:
        hedef = _tr_kucult(baslik)
        if _tr_kucult(govde[: len(hedef)]) != hedef:
            continue
        kalan = govde[len(hedef) :].lstrip("* \t")
        if kalan[:1] not in (":", "："):
            continue
        return tur, kalan[1:].strip()
    return None, ""


def _teshis_temizle(satir: str) -> str:
    """Teşhis satırından biçim kalıntılarını (madde işareti, kalınlık) siler."""
    return satir.strip().lstrip("-*•").strip()


def _duzeltme_temizle(satir: str) -> str:
    """Komut satırından yalnız sarmalayıcı işaretleri siler.

    Baştaki `-` BURADA korunur: düzeltme bir komut olduğu için `--help` gibi
    bayraklar geçerli bir yanıttır.
    """
    return satir.strip().strip("`*").strip()


def _kode_bloklarini_soyle(metin: str) -> str:
    """Metnin çevreleyen ``` kod bloğu işaretlerini atar."""
    if metin.startswith("```"):
        metin = metin[3:]
    if metin.endswith("```"):
        metin = metin[:-3]
    return metin.strip()


def _ipucundan_komut(metin: str) -> str:
    """`şunu deneyin: <komut>` kalıbından komutu çıkarır; bulunamazsa boş döner."""
    for satir in metin.splitlines():
        eslesme = _DUZELTME_IPUCU_RE.match(satir)
        if eslesme:
            return eslesme.group("komut").strip()
    return ""


def yaniti_ayikla(ham_metin: str) -> dict:
    """LLM yanıtını `{"teshis": str, "duzeltme": str | None}` biçimine çevirir.

    Başlıklar bulunamazsa ham metnin tamamı `teshis` olur ve `duzeltme=None`
    döner — format dışı yanıtta bile kullanıcı en azından ham cevabı görür,
    sessiz başarısızlık yok.
    """
    metin = (ham_metin or "").strip()
    if not metin:
        return {"teshis": metin, "duzeltme": None}

    # LLM cevabı Markdown kod bloğuna sarabiliyor; ``` işaretleri ayrıştırmayı bozuyor.
    metin = _kode_bloklarini_soyle(metin)

    teshis_satirlari: list[str] = []
    duzeltme_satirlari: list[str] = []
    hedef: list[str] | None = None
    duzeltme_goruldu = False

    for satir in metin.splitlines():
        tur, kalan = _baslik_ayir(satir)
        if tur == "teshis":
            hedef = teshis_satirlari
            if kalan:
                hedef.append(_teshis_temizle(kalan))
            continue
        if tur == "duzeltme":
            hedef = duzeltme_satirlari
            duzeltme_goruldu = True
            if kalan:
                hedef.append(_duzeltme_temizle(kalan))
            continue
        if hedef is not None:
            # Başlıktan sonraki satırlar aynı alana aittir.
            hedef.append(_duzeltme_temizle(satir) if hedef is duzeltme_satirlari
                         else _teshis_temizle(satir))

    teshis = "\n".join(s for s in teshis_satirlari if s).strip()
    duzeltme = _duzeltme_temizle("\n".join(s for s in duzeltme_satirlari if s))

    if not teshis and not duzeltme_goruldu:
        # Biçim hiç yok: ham metni olduğu gibi göster, uydurma DÜZELTME basma.
        return {"teshis": metin, "duzeltme": None}

    if not teshis:
        teshis = duzeltme
        duzeltme = ""
    if not duzeltme:
        # DÜZELTME satırı yoksa veya boşsa, ipucu kalıbından komut çıkarmayı dene.
        duzeltme = _ipucundan_komut(metin)

    return {
        "teshis": teshis,
        "duzeltme": None if duzeltme.lower() in _YOK_DEGERLER else (duzeltme or None),
    }
