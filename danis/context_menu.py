r"""Windows sağ-tık menüsü kurulumunun metin üretim mantığı.

Neden ayrı modül: `shell/install-context-menu.ps1` ince bir sarmalayıcı olsun
diye. Kayıt defteri şablonunu doldurmak ve `.reg` içeriği üretmek saf metin
işlemesidir; Windows'a, `pwsh`'a veya kayıt defterine bağımlı olmadan pytest
ile test edilebilir olmalıdır (docs/API.md'nin istediği gibi).

Bu modül `HKEY_CLASSES_ROOT` altına yazar — bu da HKLM/HKCR gerçekten birleşik
görünüm olduğu anlamına gelir; yani `.exe` kayıtlarını da kapsar. Bu yüzden
`\shell\DanisaSor` DEĞİL, `\shell\exefile\DanisaSor` kullanıyoruz: menü girdisi
yalnızca uygulamalarda görünsün. Şablonu değiştirmek için `ANAHTAR_ADI` yeterli.
"""

from __future__ import annotations

from pathlib import Path

# Kayıt defteri anahtarı. `exefile` altına yazıldığı için menü YALNIZCA
# çalıştırılabilir dosyalarda görünür (tüm dosya türlerinde değil).
ANAHTAR_ADI = r"HKEY_CLASSES_ROOT\*\shell\exefile\DanisaSor"

# Şablonda doldurulacak yer tutucu.
YER_TUTUCU = "<DANIS_EXE_YOLU>"

# Menüde görünecek etiket.
ETIKET = "Bu dosyayı danis'e sor"

# Şablon dosyasının varsayılan yeri (paket kökü/shell/).
SABLON_ADI = "context-menu.reg.template"


class SablonHatasi(ValueError):
    """Şablon eksik/bozuk ya da yer tutucu sayısı beklenen değil."""


def sablon_yolu(shell_dizini: Path) -> Path:
    return Path(shell_dizini) / SABLON_ADI


def sablonu_oku(shell_dizini: Path) -> str:
    yol = sablon_yolu(shell_dizini)
    if not yol.is_file():
        raise SablonHatasi(f"Şablon bulunamadı: {yol}")
    # utf-8-sig: şablon elle düzenlenip BOM eklenmiş olabilir.
    return yol.read_text(encoding="utf-8-sig")


def reg_icerigi_uret(sablon: str, exe_yolu: str) -> str:
    """Şablondaki yer tutucuyu gerçek exe yoluyla doldurur.

    Boş yol sessizce geçilmez: içeriksiz bir .reg üretip `reg import`
    etmek, kullanıcının menüsünü sessizce bozmaktır.
    """
    yol = exe_yolu.strip()
    if not yol:
        raise SablonHatasi("danis.exe yolu boş; .reg içeriği üretilemez.")
    if YER_TUTUCU not in sablon:
        raise SablonHatasi(f"Şablonda {YER_TUTUCU} yer tutucusu bulunamadı.")

    icerik = sablon.replace(YER_TUTUCU, yol)
    kalan = icerik.count(YER_TUTUCU)
    if kalan:
        raise SablonHatasi(f"Şablonda doldurulmamış {kalan} yer tutucu kaldı.")
    return icerik


def reg_dosyasi_yaz(shell_dizini: Path, exe_yolu: str) -> Path:
    """Üretilen .reg dosyasını yazar ve yolunu döndürür.

    Windows reg.exe, düzgün adlandırılmış bir dosyada `reg import` bekler:
    dosya adı Türkçe karakter veya boşluk içerirse Unicode yolu CMD'ye
    kaçırırken bozulur. Bu yüzden hedef her zaman ASCII bir addır.
    """
    icerik = reg_icerigi_uret(sablonu_oku(shell_dizini), exe_yolu)
    hedef = Path(shell_dizini).resolve() / "danis-context-menu.reg"
    hedef.write_text(icerik, encoding="utf-8-sig")
    return hedef


def exe_yolu_coz(hedef: str | None) -> str:
    """`Get-Command danis.exe` çıktısından exe'nin tam yolunu ayıklar.

    PowerShell `Get-Command` birden çok kaynak (uygulama, işlev, diğer ad)
    listeleyebilir; ilk satır alınır ve o satırın KENDİSİ uygulama
    (Application) türünde olmalıdır. Listede ilk satır bir işlev ise (ör.
    profil tanımlı bir `danis` fonksiyonu) yanlış yola kaydedilirdi.
    """
    if not hedef or not hedef.strip():
        raise SablonHatasi("danis.exe PATH'te bulunamadı.")

    satirlar = [sat for sat in hedef.strip().splitlines() if sat.strip()]
    if not satirlar:
        raise SablonHatasi("danis.exe PATH'te bulunamadı.")

    satir = satirlar[0].strip()

    # Get-Command çıktısı "Application  <yol>" biçimindedir; tür sütunu
    # önce atılır (yol kendisi tırnaklı olabilir).
    tur, _, kalan = satir.partition(" ")
    if tur.lower() in {"application", "external", "alias"}:
        satir = kalan.strip()

    if satir.startswith('"'):
        # Tırnaklar sınırdır; içinde boşluklar OLABİLİR (C:\Program Files\...).
        kapanan = satir.find('"', 1)
        if kapanan < 0:
            raise SablonHatasi("Kapatılmamış tırnak içinde bir yol geldi.")
        satir = satir[1:kapanan]
    else:
        # Tırnak yoksa ayırıcı beyaz boşluktur ve yolun içinde boşluk olamaz
        # (olsaydı tırnaklanmış gelirdi). Bu yüzden "ilk boşluktan öncesi"
        # güvenle yoldur; aksi halde Program Files'taki exe yanlışlıkla
        # reddedilirdi.
        satir = satir.split(None, 1)[0]

    if not satir.lower().endswith(".exe"):
        raise SablonHatasi(f"Beklenen yol .exe ile bitmiyor: {satir}")
    return satir
