"""degisiklik.py: yedek once, cakisma, yetki, hata halinde geri yukleme, tip korunumu, gunluk, geri alma."""

from __future__ import annotations

import json

import pytest

from yol.degisiklik import (
    CakismaHatasi,
    Degisiklik,
    UygulamaHatasi,
    YetkiHatasi,
    geri_al_plani,
    path_farki,
    uygula,
)
from yol.kaynak import Deger, DosyaKaynak, KaynakHatasi
from yol.yedek import yedek_oku, yedekler

ESKI_PATH = Deger("C:\\Users\\umut\\bin;C:\\Tools", True)


class IzleyenKaynak(DosyaKaynak):
    """Her yazmada yedegin o an var olup olmadigini kaydeder."""

    def __init__(self, yol):
        super().__init__(yol)
        self.yedek_var_yazmada: list[bool] = []

    def yaz(self, kapsam, ad, deger):
        self.yedek_var_yazmada.append(bool(yedekler()))
        super().yaz(kapsam, ad, deger)


class HataliKaynak(DosyaKaynak):
    """Belirtilen sira numarali yaz cagrilari hata firlatir (1'den baslar)."""

    def __init__(self, yol, hata_cagrilari):
        super().__init__(yol)
        self.cagri = 0
        self.hata = set(hata_cagrilari)

    def yaz(self, kapsam, ad, deger):
        self.cagri += 1
        if self.cagri in self.hata:
            raise KaynakHatasi("sahte yazma hatasi")
        super().yaz(kapsam, ad, deger)


class Salt(DosyaKaynak):
    def yazilabilir(self, kapsam):
        return kapsam == "kullanici"


class YayinsizKaynak(DosyaKaynak):
    def yayinla(self):
        raise KaynakHatasi("sahte yayin hatasi")


def _gunluk(yol_dir):
    satirlar = (yol_dir / "gunluk.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(s) for s in satirlar]


def _kullanici(kaynak):
    return kaynak.oku("kullanici")


def test_yedek_yazmadan_once_alinir(yol_dir, dosya_kaynak):
    kaynak = IzleyenKaynak(dosya_kaynak.yol)
    d = Degisiklik("kullanici", "Path", ESKI_PATH, Deger("C:\\Yeni", True))
    yedek_id = uygula(kaynak, [d])
    assert kaynak.yedek_var_yazmada == [True]
    assert yedek_oku(yedek_id)["kapsamlar"]["kullanici"]["Path"] == ESKI_PATH
    assert _kullanici(kaynak)["Path"] == Deger("C:\\Yeni", True)


def test_cakisma_hic_yazmaz_ve_yedek_almaz(yol_dir, dosya_kaynak):
    onceki = _kullanici(dosya_kaynak)
    d = Degisiklik("kullanici", "Path", Deger("baska-bir-deger", True), Deger("C:\\Yeni", True))
    with pytest.raises(CakismaHatasi) as hata:
        uygula(dosya_kaynak, [d])
    assert "kullanici/Path" in str(hata.value)
    assert _kullanici(dosya_kaynak) == onceki
    assert yedekler() == []


def test_yetki_hic_yazmaz(yol_dir, tmp_path, dosya_kaynak):
    kaynak = Salt(dosya_kaynak.yol)
    sistem_eski = kaynak.oku("sistem")["Path"]
    karisik = [
        Degisiklik("kullanici", "EDITOR", Deger("code", False), Deger("vim", False)),
        Degisiklik("sistem", "Path", sistem_eski, Deger("C:\\X", True)),
    ]
    with pytest.raises(YetkiHatasi):
        uygula(kaynak, karisik)
    assert kaynak.oku("kullanici")["EDITOR"] == Deger("code", False)
    assert kaynak.oku("sistem")["Path"] == sistem_eski
    assert yedekler() == []


def test_bos_liste_valueerror(yol_dir, dosya_kaynak):
    with pytest.raises(ValueError):
        uygula(dosya_kaynak, [])


def test_ayni_ad_iki_kez_valueerror(yol_dir, dosya_kaynak):
    d = Degisiklik("kullanici", "EDITOR", Deger("code", False), Deger("vim", False))
    with pytest.raises(ValueError):
        uygula(dosya_kaynak, [d, d])


def test_yazma_hatasinda_geri_yuklenir(yol_dir, dosya_kaynak):
    kaynak = HataliKaynak(dosya_kaynak.yol, hata_cagrilari={2})
    d1 = Degisiklik("kullanici", "Path", ESKI_PATH, Deger("C:\\Yeni", True))
    d2 = Degisiklik("kullanici", "EDITOR", Deger("code", False), Deger("vim", False))
    with pytest.raises(UygulamaHatasi) as hata:
        uygula(kaynak, [d1, d2])
    assert hata.value.geri_yuklendi is True
    assert isinstance(hata.value.__cause__, KaynakHatasi)
    kullanici = _kullanici(kaynak)
    assert kullanici["Path"] == ESKI_PATH
    assert kullanici["EDITOR"] == Deger("code", False)


def test_geri_yukleme_basarisizsa_bildirilir(yol_dir, dosya_kaynak):
    # 2. yazma (ileri) ve 3. yazma (d2'nin geri yuklemesi) basarisiz
    kaynak = HataliKaynak(dosya_kaynak.yol, hata_cagrilari={2, 3})
    d1 = Degisiklik("kullanici", "Path", ESKI_PATH, Deger("C:\\Yeni", True))
    d2 = Degisiklik("kullanici", "EDITOR", Deger("code", False), Deger("vim", False))
    with pytest.raises(UygulamaHatasi) as hata:
        uygula(kaynak, [d1, d2])
    assert hata.value.geri_yuklendi is False
    assert "GERI YUKLENEMEDI" in str(hata.value)
    assert len(yedekler()) == 1


def test_genisler_tipi_korunur(yol_dir, dosya_kaynak):
    d1 = Degisiklik("kullanici", "Path", ESKI_PATH, Deger("%USERPROFILE%\\x", True))
    d2 = Degisiklik("kullanici", "EDITOR", Deger("code", False), Deger("code2", False))
    uygula(dosya_kaynak, [d1, d2])
    kullanici = _kullanici(dosya_kaynak)
    assert kullanici["Path"] == Deger("%USERPROFILE%\\x", True)
    assert kullanici["EDITOR"] == Deger("code2", False)


def test_gunlukte_deger_yok(yol_dir, dosya_kaynak):
    gizli_eski = Deger("gizli-DEGER-123", False)
    dosya_kaynak.yaz("kullanici", "API_TOKEN", gizli_eski)
    d = Degisiklik("kullanici", "API_TOKEN", gizli_eski, Deger("baska-GIZLI-456", False))
    uygula(dosya_kaynak, [d])
    metin = (yol_dir / "gunluk.jsonl").read_text(encoding="utf-8")
    assert "gizli-DEGER-123" not in metin
    assert "baska-GIZLI-456" not in metin
    assert "API_TOKEN" in metin


def test_gunlukte_path_farki(yol_dir, dosya_kaynak):
    yeni = Deger("C:\\Users\\umut\\bin;C:\\New", True)
    uygula(dosya_kaynak, [Degisiklik("kullanici", "Path", ESKI_PATH, yeni)])
    kayit = [k for k in _gunluk(yol_dir) if k.get("ad") == "Path"][-1]
    assert kayit["eylem"] == "degistir"
    assert kayit["eklenen"] == ["C:\\New"]
    assert kayit["cikan"] == ["C:\\Tools"]


def test_geri_al_plani_roundtrip(yol_dir, dosya_kaynak):
    orijinal = dict(_kullanici(dosya_kaynak))
    d1 = Degisiklik("kullanici", "Path", ESKI_PATH, Deger("C:\\Yeni", True))
    d2 = Degisiklik("kullanici", "EDITOR", Deger("code", False), None)
    yedek_id = uygula(dosya_kaynak, [d1, d2])

    plan = geri_al_plani(dosya_kaynak, yedek_id)
    assert {d.ad for d in plan} == {"Path", "EDITOR"}
    por = {d.ad: d for d in plan}
    assert por["EDITOR"].eski is None and por["EDITOR"].yeni == Deger("code", False)

    uygula(dosya_kaynak, plan)
    assert _kullanici(dosya_kaynak) == orijinal
    assert geri_al_plani(dosya_kaynak, yedek_id) == []


def test_yayinla_hatasi_geri_almaz_ve_raporlar(yol_dir, dosya_kaynak):
    kaynak = YayinsizKaynak(dosya_kaynak.yol)
    d = Degisiklik("kullanici", "EDITOR", Deger("code", False), Deger("vim", False))
    with pytest.warns(UserWarning):
        yedek_id = uygula(kaynak, [d])
    assert _kullanici(kaynak)["EDITOR"] == Deger("vim", False)
    kayitlar = [k for k in _gunluk(yol_dir) if k.get("eylem") == "yayinla_hatasi"]
    assert kayitlar and kayitlar[0]["yedek"] == yedek_id


def test_path_farki():
    assert path_farki("a;b;c", "b;c;d", ";") == {"eklenen": ["d"], "cikan": ["a"]}
    assert path_farki("a:b", "b:a", ":") == {"eklenen": [], "cikan": []}
    assert path_farki("", "x;x", ";") == {"eklenen": ["x"], "cikan": []}


def test_degisiklik_sozluk_roundtrip():
    d = Degisiklik("kullanici", "Path", ESKI_PATH, None)
    assert Degisiklik.sozlukten(d.sozluk()) == d
    with pytest.raises(ValueError):
        Degisiklik.sozlukten({"kapsam": "kullanici"})
