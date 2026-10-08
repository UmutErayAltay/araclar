"""analiz.py: bulgu turleri, genisletme, anahtar, sira, PATHEXT, store tespiti, temizlik."""

from __future__ import annotations

from yol.analiz import (
    IZLENEN,
    anahtar,
    etkin_dizinler,
    genislet,
    girdileri_analiz,
    komut_ara,
    komut_raporu,
    ozet,
    parcala,
    store_taklidi,
    temizlik_onerisi,
)

WIN_ORTAM = {"ROOT": "C:\\R", "USERPROFILE": "C:\\Users\\u"}


def _dizin_kumesi(*yollar: str, windows: bool = True):
    anahtarlar = {anahtar(y, windows) for y in yollar}
    return lambda p: anahtar(p, windows) in anahtarlar


def _bulgu_kumeleri(girdiler):
    return [sorted(g.bulgular) for g in girdiler]


def test_genislet_windows_buyuk_kucuk_harf_ve_bilinmeyen():
    sonuc = genislet("%userprofile%\\bin;%NOPE%;%root%\\tools", WIN_ORTAM, True)
    assert sonuc == "C:\\Users\\u\\bin;%NOPE%;C:\\R\\tools"


def test_genislet_posix_ve_bilinmeyen():
    ortam = {"HOME": "/h", "X": "/x"}
    assert genislet("$HOME/bin:${X}/y:$NOPE:$home", ortam, False) == "/h/bin:/x/y:$NOPE:$home"


def test_anahtar_sondaki_ayirici_ve_buyuk_kucuk_harf():
    assert anahtar("C:\\Foo\\", True) == anahtar("c:/foo", True) == "c:\\foo"
    assert anahtar("C:\\", True) == "c:\\"
    assert anahtar("/usr/bin/", False) == "/usr/bin"
    assert anahtar("/", False) == "/"
    assert anahtar("/Usr/Bin", False) != anahtar("/usr/bin", False)


def test_parcala_bos_girdileri_tutar():
    assert parcala("a;;b;", ";") == ["a", "", "b", ""]
    assert parcala("", ";") == []


def test_girdi_bulgulari_tum_turler():
    sistem = "C:\\Sys;C:\\Gone"
    kullanici = "C:\\User;;c:\\user\\;C:\\Sys;C:\\Gone;bin;C:\\User;%ROOT%\\tools"
    dirs = _dizin_kumesi("C:\\Sys", "C:\\User", "C:\\R\\tools")
    girdiler = girdileri_analiz({"sistem": sistem, "kullanici": kullanici}, ";", WIN_ORTAM, True, dirs)
    sistem_g = [g for g in girdiler if g.kapsam == "sistem"]
    kullanici_g = [g for g in girdiler if g.kapsam == "kullanici"]
    assert _bulgu_kumeleri(sistem_g) == [[], ["yok"]]
    assert _bulgu_kumeleri(kullanici_g) == [
        [],                 # 0 C:\User
        ["bos"],            # 1 bos
        ["tekrar"],         # 2 c:\user\ (C:\User ile ayni)
        ["sistemde-var"],   # 3 C:\Sys sistemde zaten var
        ["sistemde-var", "yok"],  # 4 C:\Gone: sistemde var ama dizin degil
        ["goreli", "yok"],  # 5 bin
        ["tekrar"],         # 6 C:\User
        [],                 # 7 %ROOT%\tools genisleyince var
    ]
    assert [g.sira for g in kullanici_g] == list(range(8))
    assert kullanici_g[7].ham == "%ROOT%\\tools"
    assert kullanici_g[7].genis == "C:\\R\\tools"


def test_etkin_sira_sistem_once_ve_ilk_gecis():
    sistem = "C:\\Sys;C:\\Gone"
    kullanici = "C:\\User;;c:\\user\\;C:\\Sys;C:\\Gone;bin;C:\\User;%ROOT%\\tools"
    dirs = _dizin_kumesi("C:\\Sys", "C:\\User", "C:\\R\\tools")
    girdiler = girdileri_analiz({"sistem": sistem, "kullanici": kullanici}, ";", WIN_ORTAM, True, dirs)
    assert etkin_dizinler(girdiler) == ["C:\\Sys", "C:\\Gone", "C:\\User", "bin", "C:\\R\\tools"]


def test_komut_ara_windows_pathext_sirasi():
    dizinler = ["C:\\A", "C:\\B"]
    pathext = [".EXE", ".CMD"]
    dosyalar = {"c:\\a\\python.exe", "c:\\b\\python.cmd"}

    def dosya_var(p: str) -> bool:
        return p.casefold() in dosyalar

    assert komut_ara("python", dizinler, True, pathext, dosya_var) == [
        "C:\\A\\python.EXE",
        "C:\\B\\python.CMD",
    ]
    # Uzantisi zaten varsa yalniz kendisi denenir
    assert komut_ara("python.exe", dizinler, True, pathext, dosya_var) == ["C:\\A\\python.exe"]


def test_komut_ara_posix_ve_kok_dizin():
    dosyalar = {"/usr/bin/python3", "/opt/bin/python3", "/sh"}
    assert komut_ara("python3", ["/usr/bin", "/opt/bin"], False, [], lambda p: p in dosyalar) == [
        "/usr/bin/python3",
        "/opt/bin/python3",
    ]
    assert komut_ara("sh", ["/"], False, [], lambda p: p in dosyalar) == ["/sh"]


def test_store_taklidi_tespiti():
    assert store_taklidi("C:\\Users\\u\\AppData\\Local\\Microsoft\\WindowsApps\\python.exe")
    assert store_taklidi("c:/users/u/appdata/local/microsoft/windowsapps/python.exe")
    assert not store_taklidi("C:\\Python312\\python.exe")


def test_komut_raporu_store_gölgesi():
    store = "C:\\Users\\u\\AppData\\Local\\Microsoft\\WindowsApps"
    gercek = "C:\\Python312"
    dosyalar = {
        f"{store}\\python.exe".casefold(),
        f"{gercek}\\python.exe".casefold(),
        f"{gercek}\\git.exe".casefold(),
    }
    rapor = komut_raporu(
        [store, gercek], True, [".EXE"], lambda p: p.casefold() in dosyalar, adlar=("python", "git")
    )
    assert rapor == [
        {"ad": "python", "kazanan": f"{store}\\python.EXE", "golgede": [f"{gercek}\\python.EXE"],
         "bulgu": "store-taklidi"},
        {"ad": "git", "kazanan": f"{gercek}\\git.EXE", "golgede": [], "bulgu": None},
    ]
    varsayilan = komut_raporu([], True, [".EXE"], lambda p: False)
    assert [r["ad"] for r in varsayilan] == list(IZLENEN)


def test_temizlik_onerisi_ham_metni_ve_sirayi_korur():
    ham = "%ROOT%\\tools;;C:\\Missing;C:\\A;C:\\A\\;C:\\Sys"
    dirs = _dizin_kumesi("C:\\R\\tools", "C:\\A", "C:\\Sys")
    girdiler = girdileri_analiz({"sistem": "C:\\Sys", "kullanici": ham}, ";", WIN_ORTAM, True, dirs)
    assert temizlik_onerisi(ham, girdiler, ";") == "%ROOT%\\tools;C:\\A"


def test_temizlik_onerisi_temizse_none():
    ham = "C:\\A;%ROOT%\\tools"
    dirs = _dizin_kumesi("C:\\A", "C:\\R\\tools")
    girdiler = girdileri_analiz({"kullanici": ham}, ";", WIN_ORTAM, True, dirs)
    assert temizlik_onerisi(ham, girdiler, ";") is None


def test_posix_ayirici_iki_nokta():
    ham = "/a:/b::/a/:rel"
    girdiler = girdileri_analiz(
        {"kullanici": ham}, ":", {}, False, lambda p: anahtar(p, False) == "/a"
    )
    assert _bulgu_kumeleri(girdiler) == [[], ["yok"], ["bos"], ["tekrar"], ["goreli", "yok"]]
    assert temizlik_onerisi(ham, girdiler, ":") == "/a"  # rel: yok -> kaldirilir


def test_ozet_sayilar_ve_uzunluk():
    dirs = _dizin_kumesi("C:\\Sys", "C:\\User")
    girdiler = girdileri_analiz(
        {"sistem": "C:\\Sys;C:\\Gone", "kullanici": "C:\\User;C:\\Sys"}, ";", WIN_ORTAM, True, dirs
    )
    komutlar = [{"ad": "python", "golgede": ["x"]}, {"ad": "git", "golgede": []}]
    sonuc = ozet(girdiler, komutlar, 100)
    assert sonuc == {
        "girdi": {"sistem": 2, "kullanici": 2},
        "sorunlu": 2,  # sistem: C:\Gone (yok); kullanici: C:\Sys (sistemde-var)
        "golgelenen": 1,
        "uzun": False,
    }
    assert ozet(girdiler, komutlar, 2048)["uzun"] is True
