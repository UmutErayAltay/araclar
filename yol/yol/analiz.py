"""PATH analizi: saf fonksiyonlar. Dosya/kayit erisimi yalniz enjekte edilen cagrilarla yapilir."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

UZUN_SINIR = 2047
IZLENEN = ("python", "python3", "py", "pip", "node", "npm", "npx", "git", "java", "javac",
           "code", "claude", "cor", "docker", "uv", "cargo")

SORUNLU_BULGULAR = frozenset({"yok", "bos", "tekrar", "sistemde-var"})
# Kesin sorun degil, yalniz bilgi: temizlik onerisine girmez, sorunlu sayilmaz.
NOTR_BULGULAR = frozenset({"cozumlenemedi", "kontrol-edilemedi"})
GENISLETME_TURU = 8  # ic ice ortam degiskenleri icin ust sinir (%A% -> %B% -> ...)
_PYTHON_ADLARI = ("python", "python3", "py")
_WIN_DEGISKEN = re.compile(r"%([^%]+)%")
_POSIX_DEGISKEN = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
_WIN_MUTLAK = re.compile(r"^[A-Za-z]:[\\/]")
_SURUCU = re.compile(r"^[A-Za-z]:")


@dataclass
class Girdi:
    kapsam: str        # "sistem" | "kullanici" | "surec"
    sira: int          # 0-tabanli, kendi kapsam listesi icinde
    ham: str           # saklanan ham metin (%VAR% icerebilir)
    genis: str         # genisletilmis metin (cift tirnaksiz)
    bulgular: list[str]  # SORUNLU/NOTR altkumeleri ve "goreli"


def _bir_tur(metin: str, ortam: Mapping[str, str], windows: bool) -> str:
    if windows:
        buyuk = {anahtar_ad.upper(): deger for anahtar_ad, deger in ortam.items()}

        def _win(eslesme: re.Match[str]) -> str:
            deger = buyuk.get(eslesme.group(1).upper())
            return eslesme.group(0) if deger is None else deger

        return _WIN_DEGISKEN.sub(_win, metin)

    def _posix(eslesme: re.Match[str]) -> str:
        ad = eslesme.group(1) or eslesme.group(2)
        deger = ortam.get(ad)
        return eslesme.group(0) if deger is None else deger

    return _POSIX_DEGISKEN.sub(_posix, metin)


def genislet(metin: str, ortam: Mapping[str, str], windows: bool) -> str:
    """Windows: %AD% (buyuk/kucuk harf duyarsiz). POSIX: $AD / ${AD}. Bilinmeyen degisken oldugu gibi kalir.

    Degerin icindeki degiskenler de acilir (en fazla GENISLETME_TURU tur); metin degisince durur.
    """
    for _ in range(GENISLETME_TURU):
        yeni = _bir_tur(metin, ortam, windows)
        if yeni == metin:
            break
        metin = yeni
    return metin


def cozumlenmemis_mi(metin: str, windows: bool) -> bool:
    """Genisletmeden sonra hala %AD% (windows) ya da $AD (posix) kalmis mi."""
    desen = _WIN_DEGISKEN if windows else _POSIX_DEGISKEN
    return desen.search(metin) is not None


def _tirnaksiz(metin: str) -> str:
    """Cift tirnakla sarili girdi (\"C:\\Program Files\\x\") icin dis tirnaklar atilir."""
    if len(metin) >= 2 and metin[0] == '"' and metin[-1] == '"':
        return metin[1:-1]
    return metin


def _coz(ham: str, ortam: Mapping[str, str], windows: bool) -> str:
    return _tirnaksiz(genislet(ham, ortam, windows))


def anahtar(yol: str, windows: bool) -> str:
    """Karsilastirma anahtari: sondaki ayiricilar atilir (kok hariç), Windows'ta buyuk/kucuk harf ve '/' -> '\\'."""
    temiz = yol.rstrip("\\/")
    if temiz == "":
        temiz = yol[:1]  # kok: "/" ya da "\\"
    if windows:
        if re.fullmatch(r"[A-Za-z]:", temiz):
            temiz += "\\"
        temiz = temiz.replace("/", "\\").casefold()
    return temiz


def parcala(metin: str, ayirici: str) -> list[str]:
    """PATH metnini boş girdiler dahil ayirir. Tamamen bos metin bos liste doner."""
    if metin == "":
        return []
    return metin.split(ayirici)


def _mutlak_mi(yol: str, windows: bool) -> bool:
    if windows:
        return bool(_WIN_MUTLAK.match(yol)) or yol.startswith("\\\\")
    return yol.startswith("/")


def _windows_yolu_mu(yol: str) -> bool:
    return "\\" in yol or bool(_SURUCU.match(yol))


def _dogrulanabilir(yol: str, windows: bool, kok_var: Callable[[str], bool]) -> bool:
    """Yol bu makinede dogrulanabilir mi? Goreli, UNC ve kok surucusu olmayan yollar dogrulanamaz."""
    if not _mutlak_mi(yol, windows):
        return False  # goreli: hangi dizine gore oldugu bilinmiyor
    if windows:
        if yol.startswith("\\\\"):
            return False  # UNC: ag paylasimi, yerelden kesin degil
        if _SURUCU.match(yol) and not kok_var(yol[:2] + "\\"):
            return False  # surucu yok (cikarilabilir/ag surucusu baglanmamis olabilir)
    return True


def girdileri_analiz(kapsamlar: dict[str, str], ayirici: str, ortam: Mapping[str, str], windows: bool,
                     dizin_var: Callable[[str], bool] = os.path.isdir,
                     kok_var: Callable[[str], bool] | None = None) -> list[Girdi]:
    """Kapsam -> ham PATH metni (etkin sirada). Her girdi icin bulgu listesi uretir.

    Yok bulgusu yalniz yol dogrulanabildiginde verilir; aksi halde "kontrol-edilemedi" ya da
    (degiskeni acilamadiysa) "cozumlenemedi" verilir. `kok_var` verilmezse surucu var sayilir.
    """
    kok_denetle = kok_var if kok_var is not None else (lambda _kok: True)
    sistem_anahtarlari = {
        anahtar(_coz(ham, ortam, windows), windows)
        for ham in parcala(kapsamlar.get("sistem", ""), ayirici)
        if ham.strip()
    }
    girdiler: list[Girdi] = []
    for kapsam, metin in kapsamlar.items():
        gorulen: set[str] = set()
        for sira, ham in enumerate(parcala(metin, ayirici)):
            genis = _coz(ham, ortam, windows)
            bulgular: list[str] = []
            if not ham.strip():
                bulgular.append("bos")
            else:
                if cozumlenmemis_mi(genis, windows):
                    bulgular.append("cozumlenemedi")
                elif not _dogrulanabilir(genis, windows, kok_denetle):
                    bulgular.append("kontrol-edilemedi")
                elif not dizin_var(genis):
                    bulgular.append("yok")
                anahtar_deger = anahtar(genis, windows)
                if anahtar_deger in gorulen:
                    bulgular.append("tekrar")
                gorulen.add(anahtar_deger)
                if kapsam == "kullanici" and anahtar_deger in sistem_anahtarlari:
                    bulgular.append("sistemde-var")
                if not _mutlak_mi(genis, windows):
                    bulgular.append("goreli")
            girdiler.append(Girdi(kapsam, sira, ham, genis, bulgular))
    return girdiler


def etkin_dizinler(girdiler: list[Girdi]) -> list[str]:
    """Bos olmayan girdilerin genis hali, ilk gecis sirasiyla (anahtara gore tekil)."""
    gorulen: set[str] = set()
    sonuc: list[str] = []
    for girdi in girdiler:
        if "bos" in girdi.bulgular:
            continue
        anahtar_deger = anahtar(girdi.genis, _windows_yolu_mu(girdi.genis))
        if anahtar_deger in gorulen:
            continue
        gorulen.add(anahtar_deger)
        sonuc.append(girdi.genis)
    return sonuc


def komut_ara(ad: str, dizinler: list[str], windows: bool, pathext: list[str],
              dosya_var: Callable[[str], bool]) -> list[str]:
    """Komutun tum eslesmeleri, dizin sirasiyla. Windows'ta PATHEXT uzantilari denenir."""
    if windows:
        uzantilar = [e for e in pathext if e]
        if any(ad.casefold().endswith(e.casefold()) for e in uzantilar):
            adaylar = [ad]
        else:
            adaylar = [ad + e for e in uzantilar]
        ayrac = "\\"
        kirp = "\\/"
    else:
        adaylar = [ad]
        ayrac = "/"
        kirp = "/"
    sonuc: list[str] = []
    for dizin in dizinler:
        taban = dizin.rstrip(kirp)
        for aday in adaylar:
            yol = taban + ayrac + aday
            if dosya_var(yol):
                sonuc.append(yol)
    return sonuc


def store_taklidi(yol: str) -> bool:
    """Microsoft Store uygulama yurutme takma adi (WindowsApps) mi?"""
    return "\\microsoft\\windowsapps\\" in yol.replace("/", "\\").casefold()


def komut_raporu(dizinler: list[str], windows: bool, pathext: list[str],
                 dosya_var: Callable[[str], bool], adlar: Iterable[str] = IZLENEN) -> list[dict]:
    """Izlenen komutlar icin kazanan, gölgedekiler ve bulgu."""
    rapor: list[dict] = []
    for ad in adlar:
        bulunanlar = komut_ara(ad, dizinler, windows, pathext, dosya_var)
        kazanan = bulunanlar[0] if bulunanlar else None
        bulgu = None
        if ad.casefold() in _PYTHON_ADLARI and kazanan is not None and store_taklidi(kazanan):
            bulgu = "store-taklidi"
        rapor.append({"ad": ad, "kazanan": kazanan, "golgede": bulunanlar[1:], "bulgu": bulgu})
    return rapor


def temizlik_onerisi(ham_path: str, girdiler: list[Girdi], ayirici: str,
                     kapsam: str = "kullanici") -> str | None:
    """Sorunlu girdiler (yok/bos/tekrar/sistemde-var) cikarilmis yeni ham metin. Degisiklik yoksa None."""
    silinecek = {
        girdi.sira
        for girdi in girdiler
        if girdi.kapsam == kapsam and SORUNLU_BULGULAR.intersection(girdi.bulgular)
    }
    if not silinecek:
        return None
    kalan = [p for i, p in enumerate(parcala(ham_path, ayirici)) if i not in silinecek]
    return ayirici.join(kalan)


def ozet(girdiler: list[Girdi], komutlar: list[dict], toplam_uzunluk: int) -> dict:
    """Kart/satir ozeti: kapsam basina girdi sayisi, sorunlu girdi, golgelenen komut, uzunluk sinirı."""
    sayim: dict[str, int] = {}
    sorunlu = 0
    for girdi in girdiler:
        sayim[girdi.kapsam] = sayim.get(girdi.kapsam, 0) + 1
        if set(girdi.bulgular) - NOTR_BULGULAR:
            sorunlu += 1
    return {
        "girdi": sayim,
        "sorunlu": sorunlu,
        "golgelenen": sum(1 for komut in komutlar if komut.get("golgede")),
        "uzun": toplam_uzunluk > UZUN_SINIR,
    }
