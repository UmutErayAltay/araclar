from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
class Bulgu:
    """PATH girdisi için saptama türünü temsil eder."""

    YOK = "yok"
    BOS = "bos"
    TEKRAR = "tekrar"
    SISTEMDE_VAR = "sistemde-var"
    GORELI = "goreli"
    UZUN = "uzun"
    MAGAZA_TAKLIDI = "magaza-taklidi"

    def __init__(self, tur: str, aciklama: str, onerilen: str, ozet: str) -> None:
        self.tur = tur
        self.aciklama = aciklama
        self.onerilen = onerilen
        self.ozet = ozet

    @property
    def renk(self) -> str:
        renkler = {
            self.YOK: "red",
            self.BOS: "yellow",
            self.TEKRAR: "red",
            self.SISTEMDE_VAR: "red",
            self.GORELI: "yellow",
            self.UZUN: "yellow",
            self.MAGAZA_TAKLIDI: "yellow",
        }
        return renkler.get(self.tur, "gray")
def _metin_genislet(metin: str, ortam: dict[str, str]) -> str:
    """PATH girdisindeki %DEĞİŞKEN% gibi yer tutucuları, ortam sözlüğünde genişletir."""
    if not metin:
        return metin
    sonuc = metin
    for ad, deger in ortam.items():
        if isinstance(deger, str):
            desen = f"%{ad}%"
            sonuc = sonuc.replace(desen, deger)
    return sonuc
def _absolu_mu(dizin: str) -> bool:
    """PATH girdisinin mutlak bir yol olduğunu döndürür."""
    if os.name == "nt":
        return bool(re.match(r'^[A-Za-z]:\\', dizin)) and not dizin.startswith(".")
    else:
        return dizin.startswith("/") and not dizin.startswith(".")
def _normalleştir(dizin: str) -> str:
    """PATH girdisindeki sondaki ters eğik çizgiyi kaldırır ve dosya adını çıkarır."""
    dizin = dizin.rstrip("\\/")
    if os.name == "nt":
        # Son parçayı al
        parcalar = dizin.split("\\")
        if parcalar:
            dizin = parcalar[-1]
    else:
        parcalar = dizin.split("/")
        if parcalar:
            dizin = parcalar[-1]
    return dizin
def _tekrar_edi_bul(gelen: list[str], ornek: str, ortam: dict[str, str]) -> bool:
    """Geçerli kapsamda, genişletilmiş ve normalleştirilmiş olarak, orneğe eşit herhangi bir girdi var mı diye kontrol eder."""
    for g in gelen:
        genis = _metin_genislet(g, ortam)
        norm = _normalleştir(genis)
        if norm == ornek:
            return True
    return False
def analiz_girdi(girdi: str, kapsam: str, tum_kapsamlar: dict[str, dict[str, str]], komutlar: dict[str, list[str]]) -> dict[str, Any]:
    """Tek bir PATH girdisi için analiz sonuçlarını hesaplar.

    Argümanlar:
        girdi: PATH girdisi metni (%VAR% yer tutucuları dahil)
        kapsam: girdinin ait olduğu kapsam ("kullanici" veya "sistem")
        tum_kapsamlar: komşu kapsamlar (girdi eşitliğini kontrol etmek için)
        komutlar: PATHEXT uzantıları haritası (ör. {"python": ["python", "py"]})

    Döndürülen:
        Girdi bulgusu ile ilgili ayrıntıları içeren sözlük.
    """
    ortam = {}

    # PATH genişletmesi için ortam değişkenlerini oluştur
    # Önce komşu kapsamdaki PATH değişkenlerini al
    for kapsam_anahtar in ["kullanici", "sistem"]:
        if kapsam_anahtar in tum_kapsamlar:
            for ad, deger in tum_kapsamlar[kapsam_anahtar].items():
                ortam[ad] = deger

    # Girdi var mı?
    if not girdi.strip():
        return {"bulgu": Bulgu(Bulgu.BOS, "Boş girdi (;;)", "Kaldır", "Girdi boş"), "genis": "", "normal": ""}

    genis = _metin_genislet(girdi, ortam)

    # Son sondaki ters eğik çizgiyi kaldır
    genis = genis.rstrip("\\/")

    # Var mı?
    normal = _normalleştir(genis)

    # Bulgu türleri
    sonuc: dict[str, Any] = {"bulgu": None, "genis": genis, "normal": normal, "kapsam": kapsam}

    if not genis:
        sonuc["bulgu"] = Bulgu(Bulgu.BOS, "Boş girdi (;;)", "Kaldır", "Girdi boş")
    elif _tekrar_edi_bul(tum_kapsamlar.get(kapsam, {}).get("diziler", []), normal, ortam):
        sonuc["bulgu"] = Bulgu(Bulgu.TEKRAR, f"Aynı kapsamda zaten var: {normal}", "İlkini koru", "Girdi tekrar")
    elif normal in ["python", "node", "npm", "npx", "git", "java", "javac", "code", "claude", "cor", "docker", "uv", "cargo"]:
        # Standart komutlar kontrolü - PATH'te bulunuyor (komutlar listesinden değil, sadece komut adı)
        sonuc["bulgu"] = Bulgu(Bulgu.SISTEMDE_VAR, f"Sistem PATH'inde zaten var: {normal}", "Kaldır", "Girdi zaten var")
    elif not os.path.isdir(genis) and normal:
        # Genişletilen yol bir dizin değil
        sonuc["bulgu"] = Bulgu(Bulgu.YOK, f"Genişletilmiş yol bir dizin değil: {genis}", "Kaldır", "Genişletilen yol geçersiz")
    else:
        # Komutlar için sistemde-var kontrolü (sistem kapsamında kullanıcı girdisini kontrol et)
        tum_komutlar = []
        for kume in komutlar.values():
            tum_komutlar.extend(kume)
        if normal in tum_komutlar and kapsam == "kullanici":
            sonuc["bulgu"] = Bulgu(Bulgu.SISTEMDE_VAR, f"Sistem PATH'inde zaten var: {normal}", "Kaldır", "Girdi zaten var")
        elif normal and normal in ["python", "node", "npm", "npx", "git", "java", "javac", "code", "claude", "cor", "docker", "uv", "cargo"]:
            # Standart komutlar kontrolü - PATH'te bulunuyor (komutlar listesinden değil, sadece komut adı)
            # Bu komutlar genellikle PATH'te bulunur, bu nedenle sistemde-var olarak işaretleyebiliriz
            sonuc["bulgu"] = Bulgu(Bulgu.SISTEMDE_VAR, f"Sistem PATH'inde zaten var: {normal}", "Kaldır", "Girdi zaten var")
        else:
            # Göreli kontrolü (mutlak değil)
            if not _absolu_mu(girdi):
                sonuc["bulgu"] = Bulgu(Bulgu.GORELI, "Mutlak değil (., bin gibi)", "Uyar", "Girdi göreli")

            # Uzunluk kontrolü (PATH > 2047)
            # PATH genişliği PATH olarak atanacak (sorun yapılmayacak)
            # PATH bu uzunluğa ulaştığında kontrol yapılacak

    # Magaza taklidi kontrolü
    if os.name == "nt":
        magaza_deseni = r"^[A-Za-z]:\\Microsoft\\WindowsApps\\"
        if re.match(magaza_deseni, genis):
            sonuc["bulgu"] = Bulgu(Bulgu.MAGAZA_TAKLIDI,
                                    "Microsoft Store kısayolu gerçek Python'u gölgeliyor",
                                    "Ayarlar → Uygulama yürütme diğer adları'ndan kapat",
                                    "Genişletilen yol WindowsApps içinde")

    return sonuc
def komutlar_olustur(pathext: str) -> dict[str, list[str]]:
    """PATHEXT ortam değişkeninden (virgülle ayrılmış, . ile başlayan) izlenen komutlara ait bir sözlük oluşturur.

    Argümanlar:
        pathext: örn. ".EXE;.COM;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC"

    Döndürülen:
        komutları anahtarlar, uzantı listesini değerler olarak içeren sözlük.
    """
    if not pathext:
        return {}
    # . ile başlayan uzantıları alır ve küçük harfe çevirir
    uzantilar = [ext[1:].lower() for ext in pathext.split(";") if ext.startswith(".")]
    komutlar: dict[str, list[str]] = {}

    # Windows'ta yaygın PATHEXT'teki uzantıları kullanarak komutları ekle
    # Örnek değerler: .exe => python.exe, .com => python.com, .bat => python.bat vb.
    # Bunun yerine, izlenen komutları temel alarak komutları oluştur.
    # Örnek Python komutları - .EXE uzantısına dayalı
    # Komutları ekle - mevcut uzantılara dayalı
    # Python komutları - .EXE ve .PY uzantılarına dayalı
    if "exe" in uzantilar:
        komutlar["python"] = ["python.exe"]
    if "py" in uzantilar:
        komutlar["python"] = komutlar.get("python", []) + ["python.py"]

    # Node komutları - .JS ve .EXE uzantılarına dayalı
    if "js" in uzantilar:
        komutlar["node"] = ["node.js"]
    if "exe" in uzantilar:
        komutlar["node"] = komutlar.get("node", []) + ["node.exe"]
    # Git komutları - .EXE uzantısına dayalı
    if "exe" in uzantilar:
        komutlar["git"] = ["git.exe"]
    # Docker komutları - .EXE uzantısına dayalı
    if "exe" in uzantilar:
        komutlar["docker"] = ["docker.exe"]

    return komutlar
def etki_sırası(kapsam: str) -> list[str]:
    """Verilen kapsam için etki sırasını döndürür (Windows'ta sistem önce, kullanıcı sonra)."""
    if kapsam == "sistem":
        return ["sistem"]
    else:
        return ["sistem", "kullanici"]
def temizlik_onerisi(kullanici_diziler: list[str], sistem_diziler: list[str], komutlar: dict[str, list[str]]) -> list[dict[str, Any]]:
    """PATH için temizlik önerilerini oluşturur.

    Argümanlar:
        kullanici_diziler: Kullanıcı PATH'sindeki dizi (her giriş bir dizin yolu)
        sistem_diziler: Sistem PATH'sindeki dizi
        komutlar: Komutlar sözlüğü

    Döndürülen:
        Kaldırılacak her girdi için bir sözlük içeren bir liste.
    """
    # Ortam değişkenlerini yükle (PATH ve komşu çevre değişkenleri)
    ortam: dict[str, str] = {}

    # PATH'i ortam olarak ekle
    path_var = os.environ.get("PATH", "")
    if os.name == "nt":
        # Windows'ta PATH bölümlelerini ; ile ayır
        for bölüm in path_var.split(";"):
            if bölüm:
                ortam["PATH"] = bölüm
    else:
        # Linux'ta PATH bölümleri : ile ayrılır, bu nedenle PATH'i ortam olarak eklemiyoruz
        pass

    for ad, deger in os.environ.items():
        ortam[ad] = deger

    # Kapaslar için dizi yapıları oluşturun
    tum_kapsamlar = {"kullanici": {"diziler": kullanici_diziler}, "sistem": {"diziler": sistem_diziler}}

    oneriler: list[dict[str, Any]] = []
    for kapsam in ["kullanici"]:
        dizi = tum_kapsamlar[kapsam]["diziler"]
        for i, girdi in enumerate(dizi):
            analiz = analiz_girdi(girdi, kapsam, tum_kapsamlar, komutlar)
            if analiz["bulgu"] and analiz["bulgu"].tur in [Bulgu.YOK, Bulgu.BOS, Bulgu.TEKRAR, Bulgu.SISTEMDE_VAR]:
                oneriler.append({"kapsam": kapsam, "sira": i + 1, "girdi": girdi, "analiz": analiz})
    return oneriler
def komutlari_bul(komut: str, diziler: dict[str, list[str]], komutlar: dict[str, list[str]]) -> tuple[str, list[str]]:
    """Verilen komut için PATH listesini (diziler sözlüğünden) tarar ve kazananı bulur.

    Argümanlar:
        komut: aranacak komut adını (uzantısız)
        diziler: PATHleri içeren sözlük (her bir anahtar bir kapsam, bir değer bir dizi)
        komutlar: PATHEXT uzantıları haritası

    Döndürülen:
        Kazanan (ilk eşleşen) ve gölgedekiler (daha sonraki eşleşenler) yolları.
    """
    tum_comand_strings: list[str] = []
    for kapsam, dizi in diziler.items():
        for girdi in dizi:
            tum_comand_strings.append(girdi)

    # Komutları genişlet
    tum_comand_strings_genisletmis: list[str] = []
    for girdi in tum_comand_strings:
        tum_comand_strings_genisletmis.append(_metin_genislet(girdi, {"PATH": ";".join(tum_comand_strings)}))

    komut_uzantilar = komutlar.get(komut, [])
    if not komut_uzantilar:
        # Komut listesi boşsa, PATH'te bulunan tüm uzantılarla eşleşen yolları ara
        # Bunun yerine, komutları temel alarak komutları oluştur
        # Örnek: Python komutu için .exe ve .py uzantıları kullan
        if komut == "python":
            komut_uzantilar = ["python.exe", "python.py"]
        elif komut == "node":
            komut_uzantilar = ["node.js", "node.exe"]
        else:
            komut_uzantilar = [komut]

    kazanici = None
    koyuluklar: list[str] = []
    for girdi in tum_comand_strings_genisletmis:
        # Girdi bir dizin değilse (dosya adı gibi), uzantıyı ekle
        # Basit bir kontrol: Girdi bir dizin değilse, dosya olarak kabul edelim
        # Windows'ta, dizinleri dosya olarak kontrol etmek zordur, bu nedenle
        # basit bir kontrol kullanarak girmeyi dosya olarak kabul edelim
        # PATH'te bulunan girdilerin çoğu dosya olarak kabul edilebilir
        # Girdi dosya ise, uzantıyı ekle
        # Girdi bir dizin değilse, yalnızca komutları temel alarak komutları eşleştirelim
        # PATH'teki girdilerin çoğu dizin olarak kabul edilebilir
        # Girdi bir dizin ise, uzantıyı ekle
        if os.path.isdir(girdi):
            continue
        # Girdi bir dosya ise, uzantıyı ekle
        for uzanti in komut_uzantilar:
            hedef = f"{girdi}.{uzanti}"
            if hedef:
                if kazanici is None:
                    kazanici = hedef
                else:
                    koyuluklar.append(hedef)

    if kazanici is None:
        kazanici = ""
        koyuluklar = []

    return kazanici, koyuluklar