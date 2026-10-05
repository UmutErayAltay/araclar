"""denetle: dort turun pozitif/negatif testleri.

Her tur icin iki yonlu kural:
- POZITIF: iddia koda aykirisa bulgu uretilir (dogru alanlarla).
- NEGATIF: iddia dogruysa, tolerans icindeyse ya da tur sayilamiyorsa
  BULGU URETILMEZ (yanlis pozitiften kacinmak soyleslesmedir).
"""

from __future__ import annotations

from pathlib import Path

from conftest import argparse_kaynak, py_test_dosyasi, sahte_repo

# Modul ismiyle cagrilir: `test_sayisi` gibi adi test_ ile baslayan islevler
# pytest tarafindan test sanilmasin diye dogrudan import edilmez.
from iddia import denetle as denetim
from iddia.denetle import alt_komut_sayisi, bayrak_var

# `denetle` modulundeki `test_sayisi`/`test_sayisi_bulgu` gibi islevler buraya
# DOGRUDAN import edilmez: adi test_ ile baslayan bir modul seviyesi baglama
# pytest tarafindan test sanilir. Hepsi `denetim.` onekiyle cagrilir.

# --------------------------------------------------------------------------
# Tur 1: test sayisi
# --------------------------------------------------------------------------


def test_test_sayisi_sayilir(tmp_path):
    """`def test_` sayisi gercek test sayisini verir."""
    repo = sahte_repo(tmp_path / "r")
    py_test_dosyasi(repo, "tests/test_a.py", 3)
    py_test_dosyasi(repo, "tests/test_b.py", 2)
    assert denetim.test_sayisi(repo) == 5


def test_test_sayisi_js_test_dosyasi(tmp_path):
    """js test dosyasindaki `it(`/`test(` cagrilari sayilir."""
    repo = sahte_repo(tmp_path / "r")
    (repo / "app.test.js").parent.mkdir(parents=True, exist_ok=True)
    (repo / "app.test.js").write_text("it('a', () => {})\ntest('b', () => {})\n", encoding="utf-8")
    assert denetim.test_sayisi(repo) == 2


def test_test_sayisi_kararli_yok(tmp_path):
    """Test dosyasi olmayan repoda test sayisi None: iddia uretilmez."""
    repo = sahte_repo(tmp_path / "r", {"README.md": "120 test\n"})
    assert denetim.test_sayisi(repo) is None
    assert denetim.test_sayisi_bulgu(repo, repo / "README.md", "120 test\n") == []


def test_test_sayisi_pozitif(tmp_path):
    """README '1000 test' diyor, gercek 10: sapma bulgu uretir."""
    repo = sahte_repo(tmp_path / "r")
    py_test_dosyasi(repo, "tests/test_a.py", 10)
    readme = repo / "README.md"
    metin = "# proje\n\nBiz 1000 test ile kapsiyoruz.\n"
    bulgular = denetim.test_sayisi_bulgu(repo, readme, metin)
    assert len(bulgular) == 1
    b = bulgular[0]
    assert b["tur"] == "test-sayisi"
    assert b["iddia"] == "1000 test"
    assert b["gercek"] == "10 test"
    assert b["readme"] == "README.md:3"


def test_test_sayisi_negatif_tam_dogru(tmp_path):
    """README gercek sayiyi birebir yaziyorsa bulgu YOK."""
    repo = sahte_repo(tmp_path / "r")
    py_test_dosyasi(repo, "tests/test_a.py", 10)
    readme = repo / "README.md"
    assert denetim.test_sayisi_bulgu(repo, readme, "Toplam 10 test var.\n") == []


def test_test_sayisi_negatif_tolerans_icinde(tmp_path):
    """Sapma tolerans icindeyse bulgu YOK (kural: max(2, 0.1*gercek))."""
    repo = sahte_repo(tmp_path / "r")
    py_test_dosyasi(repo, "tests/test_a.py", 100)
    readme = repo / "README.md"
    # gercek 100, tolerans 10 -> 95 fark 5: bulgu olmamali.
    assert denetim.test_sayisi_bulgu(repo, readme, "95 test\n") == []
    # fark 11 > 10 -> bulgu olmali.
    assert len(denetim.test_sayisi_bulgu(repo, readme, "89 test\n")) == 1


def test_test_sayisi_kod_blogu_sayilmaz(tmp_path):
    """Fenced kod blogundaki '0 tests' iddia SAYILMAZ (satir no korunur)."""
    repo = sahte_repo(tmp_path / "r")
    py_test_dosyasi(repo, "tests/test_a.py", 10)
    readme = repo / "README.md"
    metin = "# ornek\n\n```python\n# 0 tests burada\nassert 0\n```\n\n1000 test iddiasi.\n"
    bulgular = denetim.test_sayisi_bulgu(repo, readme, metin)
    assert [b["iddia"] for b in bulgular] == ["1000 test"]
    # Satir no, blok bosaltildiktan SONRA da dogru kalmali (8. satir).
    assert bulgular[0]["readme"] == "README.md:8"


def test_test_sayisi_virgul_ve_nokta_ayrilir(tmp_path):
    """'1200' gibi bir sayi '1' + '200 tests' diye bolunmez."""
    repo = sahte_repo(tmp_path / "r")
    py_test_dosyasi(repo, "tests/test_a.py", 10)
    readme = repo / "README.md"
    bulgular = denetim.test_sayisi_bulgu(repo, readme, "Toplam 1200 tests var.\n")
    assert [b["iddia"] for b in bulgular] == ["1200 tests"]


def test_test_sayisi_monorepo_kapsami(tmp_path):
    """Monorepo'da her arac kendi testlerine karsilik gelir (komsu sayilmaz).

    `harita/README.md` "10 test" dediginde `harita/tests/` sayilir; `denis/`
    komsusunun testleri toplama girmez -- girerse her arac yanlis bulgu alir.
    """
    repo = sahte_repo(tmp_path / "r")
    py_test_dosyasi(repo, "harita/tests/test_a.py", 10)
    py_test_dosyasi(repo, "denis/tests/test_b.py", 900)
    readme = repo / "harita" / "README.md"
    assert denetim.test_sayisi(repo, repo / "harita") == 10
    assert denetim.test_sayisi_bulgu(repo, readme, "10 test var.\n") == []
    assert len(denetim.test_sayisi_bulgu(repo, readme, "1000 test var.\n")) == 1


def test_test_sayisi_negatif_tirnak_ornek_sayilmaz(tmp_path):
    """Tirnak icindeki "1200 test" bir ORNEKTIR, iddia sayilmaz."""
    repo = sahte_repo(tmp_path / "r")
    py_test_dosyasi(repo, "tests/test_a.py", 10)
    readme = repo / "README.md"
    metin = 'Kalip ornegi: "1200 test" ve `test-sayisi` turu.\n'
    assert denetim.test_sayisi_bulgu(repo, readme, metin) == []


def test_test_sayisi_negatif_kok_readme_tum_testleri_sayar(tmp_path):
    """Kokteki README tum repoyu kapsar (kapsam daraltilmaz)."""
    repo = sahte_repo(tmp_path / "r")
    py_test_dosyasi(repo, "harita/tests/test_a.py", 10)
    py_test_dosyasi(repo, "denis/tests/test_b.py", 20)
    readme = repo / "README.md"
    assert denetim.test_sayisi(repo, readme.parent) == 30
    assert denetim.test_sayisi_bulgu(repo, readme, "30 test\n") == []


# --------------------------------------------------------------------------
# Tur 2: dosya/klasor yolu
# --------------------------------------------------------------------------


def test_dosya_yolu_pozitif(tmp_path):
    """README `app/ozel.py` diyor, repoda yok: bulgu uretir."""
    repo = sahte_repo(tmp_path / "r", {"README.md": "Girdi: `app/ozel.py`\n"})
    bulgular = denetim.dosya_yolu_bulgu(repo, repo / "README.md", "Girdi: `app/ozel.py`\n")
    assert len(bulgular) == 1
    assert bulgular[0]["tur"] == "dosya-yolu"
    assert bulgular[0]["iddia"] == "app/ozel.py"
    assert bulgular[0]["gercek"] == "yol yok"


def test_dosya_yolu_negatif_var_olan_yol(tmp_path):
    """README'deki yol repoda varsa bulgu YOK (dosya ve klasor)."""
    repo = sahte_repo(tmp_path / "r", {"app/ozel.py": "x\n", "src/klasor/": ""})
    readme = repo / "README.md"
    metin = "`app/ozel.py` ve `src/klasor` calisir.\n"
    assert denetim.dosya_yolu_bulgu(repo, readme, metin) == []


def test_dosya_yolu_klasor_olusu(tmp_path):
    """README'de geçen bos klasor da "var" sayilir."""
    repo = sahte_repo(tmp_path / "r")
    (repo / "src" / "api").mkdir(parents=True)
    readme = repo / "README.md"
    assert denetim.dosya_yolu_bulgu(repo, readme, "`src/api` altinda.\n") == []


def test_dosya_yolu_negatif_url_glob_yer_tutucu(tmp_path):
    """URL, glob, yer tutucu, komut satiri YOL IDDIASI sayilmaz."""
    repo = sahte_repo(tmp_path / "r")
    readme = repo / "README.md"
    metin = (
        "Baglanti: `https://ornek.com/a/b.py`\n"
        "Calisma: `python -m app`\n"
        "Ornek: `tests/test_*.py`\n"
        "Yer tutucu: `<klasor>/ad.py`\n"
        "Sezim: `{modul}.py`\n"
    )
    assert denetim.dosya_yolu_bulgu(repo, readme, metin) == []


def test_dosya_yolu_negatif_gitignore_yollari(tmp_path):
    """.env/.gitignore gibi gitignore'lu yollar bulgu URETILMEZ."""
    repo = sahte_repo(tmp_path / "r")
    readme = repo / "README.md"
    metin = "`node_modules/paket/index.js` ve `.env.example` kopyalayin.\n"
    assert denetim.dosya_yolu_bulgu(repo, readme, metin) == []


def test_dosya_yolu_negatif_duz_kelime_ve_bayrak(tmp_path):
    """Duz kelime, bayrak, tek eki aritmetigi yol iddiasi DEGILDIR."""
    repo = sahte_repo(tmp_path / "r")
    readme = repo / "README.md"
    metin = "`kullanim` yeterlidir; `--kok` ve `v1.2` calisir.\n"
    assert denetim.dosya_yolu_bulgu(repo, readme, metin) == []


def test_dosya_yolu_negatif_tirnak_ici_yol_sayilir(tmp_path):
    """Tirnak icindeki yol bu turde SAYILIR: "`app/ozel.py`" kalibi iddianin kendisidir."""
    repo = sahte_repo(tmp_path / "r")
    metin = 'Calisma: "`app/ozel.py` acilir."\n'
    bulgular = denetim.dosya_yolu_bulgu(repo, repo / "README.md", metin)
    assert [b["iddia"] for b in bulgular] == ["app/ozel.py"]


def test_dosya_yolu_negatif_veri_dizini_ve_enum(tmp_path):
    """Veri kasasi dizinleri, uzantı listeleri, CIDR ve ortam degiskeni yol degildir."""
    repo = sahte_repo(tmp_path / "r")
    readme = repo / "README.md"
    metin = "`daily/gunluk.md`, `png/jpg/gif`, `127.0.0.0/8`, `ANAHTARLIK_DIR/tuz`.\n"
    assert denetim.dosya_yolu_bulgu(repo, readme, metin) == []


def test_dosya_yolu_kok_disi_yol_reddedilir(tmp_path):
    """`../gizli.py` gibi kok disina cikan yol ASLA bulgu uretmez."""
    repo = sahte_repo(tmp_path / "r", {"README.md": "`../gizli.py` olabilir.\n"})
    assert denetim.dosya_yolu_bulgu(repo, repo / "README.md", "`../gizli.py` olabilir.\n") == []


def test_dosya_yolu_negatif_monorepo_paket_ici(tmp_path):
    """Paket ic ice kurulmus monorepo'da son ek olarak eslesen yol kabul edilir.

    `danis/README.md` "`danis/llm.py`" derken gercek dosya `danis/danis/llm.py`.
    """
    repo = sahte_repo(tmp_path / "r", {"danis/danis/llm.py": "x\n"})
    readme = repo / "danis" / "README.md"
    assert denetim.dosya_yolu_bulgu(repo, readme, "`danis/llm.py` vardir.\n") == []


# --------------------------------------------------------------------------
# Tur 2 kesinlik kapisi: duz dosya adi / MIME / model / git ici yol / kardes repo
# --------------------------------------------------------------------------


def test_dosya_yolu_negatif_duz_dosya_adlari(tmp_path):
    """Duz ( "/" icermeyen) dosya adlari yol iddiasi DEGILDIR.

    Bunlar baska konumda da dogru olabilir: hangi dosyadan bahsedildigi
    BELLI DEGILDIR, dolayisiyla dogrulanamaz (yanlis pozitif kaynagi).
    """
    repo = sahte_repo(tmp_path / "r")
    readme = repo / "README.md"
    metin = (
        "`settings.json`, `Core.md`, `Last-Session.md`, `beyin.py`, `config.yaml`, "
        "`index.html`, `notlar.json`, `1.md`, `.mcp.json`, `Cargo.toml`.\n"
    )
    assert denetim.dosya_yolu_bulgu(repo, readme, metin) == []


def test_dosya_yolu_negatif_mime_tipleri(tmp_path):
    """`text/html` bir medya tipidir, yol degil."""
    repo = sahte_repo(tmp_path / "r")
    readme = repo / "README.md"
    metin = "`text/html`, `application/json`, `image/png`, `font/woff2` dondurur.\n"
    assert denetim.dosya_yolu_bulgu(repo, readme, metin) == []


def test_dosya_yolu_negatif_model_kimligi(tmp_path):
    """`stealth/space-bunny-alpha` iki segmentli, uzantisiz: model kimligidir."""
    repo = sahte_repo(tmp_path / "r")
    readme = repo / "README.md"
    assert denetim.dosya_yolu_bulgu(repo, readme, "`stealth/space-bunny-alpha` kullanilir.\n") == []


def test_dosya_yolu_negatif_durum_ve_enum_iki_segmentli(tmp_path):
    """`failed/error`, `github/actions` gibi uzantisiz iki segment yol degildir."""
    repo = sahte_repo(tmp_path / "r")
    readme = repo / "README.md"
    assert denetim.dosya_yolu_bulgu(repo, readme, "`failed/error` durumu.\n") == []


def test_dosya_yolu_negatif_git_ici_yollar(tmp_path):
    """`refs/remotes/` ve `.git/` yollari bu turun konusu degildir."""
    repo = sahte_repo(tmp_path / "r")
    readme = repo / "README.md"
    metin = "`refs/remotes/origin/main` ve `.git/config` dosyalari.\n"
    assert denetim.dosya_yolu_bulgu(repo, readme, metin) == []


def test_dosya_yolu_negatif_yer_tutucu_sozlesme_yolu(tmp_path):
    """`ad-soyad.md`, `Last-Session.md` gibi YER TUTUCU adlar iddia sayilmaz.

    Bunlar sablon/ornek dosya adlaridir; repoda olmamasi bir hata degildir.
    """
    repo = sahte_repo(tmp_path / "r")
    readme = repo / "README.md"
    assert denetim.dosya_yolu_bulgu(repo, readme, "`ad-soyad.md` seklinde olsun.\n") == []


def test_dosya_yolu_negatif_mutlak_yol_ve_sahis(tmp_path):
    """Mutlak yollar (`/` ile baslayan) ve `~/` ile baslayanlar atlanir."""
    repo = sahte_repo(tmp_path / "r")
    readme = repo / "README.md"
    assert denetim.dosya_yolu_bulgu(repo, readme, "`/etc/hosts/x.py` ve `~/gizli/a.py`.\n") == []


def test_dosya_yolu_negatif_baska_repo_yolu(tmp_path):
    """`corclient/anlat/` kardes repo yoludur: bu repoda denetlenmez.

    Taranan `corclient` reposunun README'si kardes `anlat` reposina ait
    yollar yazabilir; "yol yok" demek yanlis pozitiftir.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    kardes = sahte_repo(tmp_path / "anlat", {"README.md": "x\n"})
    repo = sahte_repo(tmp_path / "corclient", {"README.md": "x\n"})
    readme = repo / "README.md"
    metin = "Kardes arac: `corclient/anlat/` ve `corclient/atlas/`.\n"
    assert denetim.dosya_yolu_bulgu(repo, readme, metin) == []
    assert kardes.is_dir()  # kardes gercekten ayri bir repo


def test_dosya_yolu_negatif_kardes_olmayan_ilk_segment_yine_elenir(tmp_path):
    """Sadece GERCEKTEN kardes olan ilk segment atlanir; rastgele bir ad degil.

    `corclient` bir kardes repo DEGILSE, `corclient/orkestra/` gibi bir yol
    ust klasor kurallarina gore degerlendirilir.
    """
    repo = sahte_repo(tmp_path / "r")
    (repo / "klasor").mkdir()
    readme = repo / "README.md"
    # ust klasor ("klasor") repoda var, yol yok -> BAYAT yol, bulgu uretilmeli.
    assert len(denetim.dosya_yolu_bulgu(repo, readme, "`klasor/not.md` vardir.\n")) == 1


def test_dosya_yolu_pozitif_bayat_yol_ust_klasor_var(tmp_path):
    """UST KLASOR VAR ama yol yok: tasinmis/bayat yol, bulgu uretilir."""
    repo = sahte_repo(tmp_path / "r", {"app/__init__.py": "x\n"})
    (repo / "docs").mkdir()
    readme = repo / "README.md"
    metin = "`app/collector.py` ve `docs/ekran/` klasorlerini kullanir.\n"
    bulgular = denetim.dosya_yolu_bulgu(repo, readme, metin)
    assert sorted(b["iddia"] for b in bulgular) == ["app/collector.py", "docs/ekran/"]


def test_dosya_yolu_negatif_klasor_yolu_ust_klasor_yoksa(tmp_path):
    """Ust klasor YOKSA klasor yolu denetlenmez.

    `docs/` gibi bir klasor hic kurulmamissa "`docs/ekran/`" iddiasinin
    dogrulanacak bir zemini yoktur; bu bir yanlis pozitiftir.
    """
    repo = sahte_repo(tmp_path / "r", {"README.md": "x\n"})
    readme = repo / "README.md"
    assert denetim.dosya_yolu_bulgu(repo, readme, "`docs/ekran/` klasoru.\n") == []


def test_dosya_yolu_pozitif_ust_klasor_yok_kaynak_uzantili(tmp_path):
    """Ust klasor yoksa bile kaynak uzantili yol denetlenir (bulgu uretilir)."""
    repo = sahte_repo(tmp_path / "r", {"README.md": "x\n"})
    readme = repo / "README.md"
    metin = "`tools/portfolyo_yayinla.py` ve `app/collectors/durum.py`.\n"
    bulgular = denetim.dosya_yolu_bulgu(repo, readme, metin)
    assert sorted(b["iddia"] for b in bulgular) == [
        "app/collectors/durum.py",
        "tools/portfolyo_yayinla.py",
    ]


def test_dosya_yolu_pozitif_klasor_ve_uzantili_cesitler(tmp_path):
    """Tum kaynak uzantilari gecerli: `.ts .sh .yml .sql .css .go .rs .tsx`."""
    repo = sahte_repo(tmp_path / "r", {"README.md": "x\n"})
    readme = repo / "README.md"
    metin = (
        "`src/stream.ts`, `hooks/session-start.sh`, `ops/alerting_rules.yml`, "
        "`db/schema.sql`, `web/style.css`, `cmd/ara/main.go`, "
        "`core/lib.rs`, `ui/panel.tsx`.\n"
    )
    bulgular = denetim.dosya_yolu_bulgu(repo, readme, metin)
    assert len(bulgular) == 8
    assert all(b["tur"] == "dosya-yolu" for b in bulgular)


def test_dosya_yolu_negatif_kaynak_uzantisi_disi_ve_klasor_disi(tmp_path):
    """.png/.zip/.exe gibi kaynak disi uzantilar ve iki segmentli enum atlanir."""
    repo = sahte_repo(tmp_path / "r")
    readme = repo / "README.md"
    metin = "`og/site.png`, `arsiv/yedek.zip`, `bin/arac.exe`, `github/actions`.\n"
    assert denetim.dosya_yolu_bulgu(repo, readme, metin) == []


# --------------------------------------------------------------------------
# Tur 3: CLI bayragi
# --------------------------------------------------------------------------


def test_bayrak_pozitif(tmp_path):
    """README `--uygula` diyor, kaynakta yok: bulgu uretir."""
    repo = sahte_repo(tmp_path / "r")
    argparse_kaynak(repo, "cli.py", 2)
    readme = repo / "README.md"
    metin = "Silmek icin `iddia sil --uygula` calistirin.\n"
    bulgular = denetim.bayrak_bulgu(repo, readme, metin)
    assert len(bulgular) == 1
    assert bulgular[0]["tur"] == "cli-bayragi"
    assert bulgular[0]["iddia"] == "--uygula"


def test_bayrak_negatif_kaynakta_geciyor(tmp_path):
    """Bayrak argparse kaynaginda geciliyorsa bulgu YOK."""
    repo = sahte_repo(tmp_path / "r")
    argparse_kaynak(repo, "cli.py", 2, bayraklar=["--uygula"])
    readme = repo / "README.md"
    assert bayrak_var(repo, "--uygula")
    assert denetim.bayrak_bulgu(repo, readme, "`--uygula` var.\n") == []


def test_bayrak_negatif_kaynak_disi_dosyada_gecmese_de_olsa(tmp_path):
    """Bayrak yalnizca README'de geciyor, kaynakta hic yokse bulgunun kendisi."""
    repo = sahte_repo(tmp_path / "r", {"notlar.txt": "--gizli-bayrak burada\n"})
    readme = repo / "README.md"
    # .txt kaynak dosya sayilmaz -> bulgu uretilir.
    assert len(denetim.bayrak_bulgu(repo, readme, "`--gizli-bayrak` calisir.\n")) == 1


def test_bayrak_negatif_kisa_bayrak_ve_gurultu(tmp_path):
    """Tek harfli kisa bayrak (`-q`) ve `--` gurultu sayilmaz."""
    repo = sahte_repo(tmp_path / "r")
    readme = repo / "README.md"
    assert denetim.bayrak_bulgu(repo, readme, "Komut: `-q` ve metin `--`.\n") == []


def test_bayrak_negatif_kod_blogu(tmp_path):
    """Kod blogu icindeki bayrak ornegi iddia SAYILMAZ."""
    repo = sahte_repo(tmp_path / "r")
    argparse_kaynak(repo, "cli.py", 1, bayraklar=["--kok"])
    readme = repo / "README.md"
    metin = "```\n# --hayali-bayrak burada ornek\n```\n\n`--kok` zorunludur.\n"
    assert denetim.bayrak_bulgu(repo, readme, metin) == []


# --------------------------------------------------------------------------
# Tur 4: sayi-kaynak ("N komut")
# --------------------------------------------------------------------------


def test_sayi_kaynak_pozitif(tmp_path):
    """README '9 komut' diyor, argparse'ta 3 tane: bulgu uretir."""
    repo = sahte_repo(tmp_path / "r")
    argparse_kaynak(repo, "cli.py", 3)
    assert alt_komut_sayisi(repo) == 3
    readme = repo / "README.md"
    bulgular = denetim.sayi_kaynak_bulgu(repo, readme, "Araç 9 komut sunuyor.\n")
    assert len(bulgular) == 1
    assert bulgular[0]["tur"] == "sayi-kaynak"
    assert bulgular[0]["gercek"] == "3 alt komut"


def test_sayi_kaynak_negatif_dogru_sayi(tmp_path):
    """Sayi dogrudaysa bulgu YOK."""
    repo = sahte_repo(tmp_path / "r")
    argparse_kaynak(repo, "cli.py", 3)
    readme = repo / "README.md"
    assert denetim.sayi_kaynak_bulgu(repo, readme, "Arac 3 komut sunuyor.\n") == []


def test_sayi_kaynak_negatif_argparse_sayilamazsa(tmp_path):
    """argparse yoksa bu tur EMIN OLUNAMAZ: bulgu URETILMEZ."""
    repo = sahte_repo(tmp_path / "r", {"app.py": "def main(): pass\n"})
    assert alt_komut_sayisi(repo) is None
    readme = repo / "README.md"
    assert denetim.sayi_kaynak_bulgu(repo, readme, "Arac 9 komut sunuyor.\n") == []


def test_sayi_kaynak_negatif_baska_kalem_sayilmaz(tmp_path):
    """'9 kaynak', '8 modul', '5 endpoint' kalipleri URETILMEZ (sadece komut)."""
    repo = sahte_repo(tmp_path / "r")
    argparse_kaynak(repo, "cli.py", 2)
    readme = repo / "README.md"
    metin = "9 kaynak, 8 modül, 5 endpoint, 12 dosya var.\n"
    assert denetim.sayi_kaynak_bulgu(repo, readme, metin) == []


# --------------------------------------------------------------------------
# Genel: denetle() birlesimi
# --------------------------------------------------------------------------


def test_denetle_dort_turu_birlikte_doner(tmp_path):
    """Tek repoda dort turun bulgulari birlikte toplanir."""
    repo = sahte_repo(tmp_path / "r")
    py_test_dosyasi(repo, "tests/test_a.py", 10)
    argparse_kaynak(repo, "cli.py", 3)
    (repo / "README.md").write_text(
        "# r\n"
        "1000 test var.\n"
        "Girdi `app/ozel.py`.\n"
        "`--uygala` ile calisir.\n"
        "9 komut sunuyor.\n",
        encoding="utf-8",
    )
    turler = {b["tur"] for b in denetim.denetle([repo])}
    assert turler == {"test-sayisi", "dosya-yolu", "cli-bayragi", "sayi-kaynak"}


def test_denetle_temiz_repo_bos(tmp_path):
    """Uyumlu bir README'de hicbir bulgu uretilmez."""
    repo = sahte_repo(tmp_path / "r")
    py_test_dosyasi(repo, "tests/test_a.py", 10)
    argparse_kaynak(repo, "cli.py", 3, bayraklar=["--uygula"])
    (repo / "app" / "ozel.py").parent.mkdir(parents=True, exist_ok=True)
    (repo / "app" / "ozel.py").write_text("x\n", encoding="utf-8")
    (repo / "README.md").write_text(
        "10 test var. `app/ozel.py` calisir. `--uygula` ile. 3 komut sunuyor.\n",
        encoding="utf-8",
    )
    assert denetim.denetle([repo]) == []


def test_denetle_readmesiz_repo_atlanir(tmp_path):
    """README'siz repoda bulgu YOK (hata degil)."""
    repo = sahte_repo(tmp_path / "r", {"app.py": "x\n"})
    assert denetim.denetle([repo]) == []


def test_denetle_ikili_readme_atlanir(tmp_path):
    """Ikili (NUL'lu) README okunamaz: bulgu uretilmez, hata da vermez."""
    repo = sahte_repo(tmp_path / "r")
    py_test_dosyasi(repo, "tests/test_a.py", 2)
    (repo / "README.md").write_bytes(b"1000 tests\x00\x00")
    assert denetim.denetle([repo]) == []


def test_denetle_ayni_bulgu_iki_kez_yazilmaz(tmp_path):
    """Ayni iddia ayni satirda iki kez gecerse TEK bulgu."""
    repo = sahte_repo(tmp_path / "r")
    py_test_dosyasi(repo, "tests/test_a.py", 10)
    (repo / "README.md").write_text("1000 test ve `yok.py`.\n", encoding="utf-8")
    bulgular = denetim.denetle([repo])
    assert [b["iddia"] for b in bulgular].count("1000 test") == 1