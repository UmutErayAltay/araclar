"""Denetim 4: `gecmis_secret` -- repoda gizli anahtar izi var mi?

Buradaki sahte degerler TESTTE PARCALARDAN BIRLESTIRILIR: boylece testin kendi
kaynak kodu da bir tespit deseni gibi gorunmez ve dosyada sir gibi yazmaz.
"""

from __future__ import annotations

from mezar import gecmis

from conftest import git, mezar_tasi_repo, yaz

#: Sagde AWS anahtari: parcalardan birlestirilir, duz metin olarak YAZILMAZ.
SAHTE = "AKIA" + "ZZZZZZZZZZZZZZZZZZ"
#: Sagde GitHub tokeni.
SAHTE_GH = "gh" + "p_" + "a" * 36


def _sirli_repo(tmp_path, ad="anlat", *, dosya="ayar.py", icerik=None):
    """Once SIRLI dosyayi commit eder, sonra bosaltma commit'i yapar.

    Boylece secret YALNIZ gecmiste kalir: calisma agaci temizlenir, denetim
    dogru sekilde gecmisi tarar.
    """
    govde = icerik if icerik is not None else f'aws = "{SAHTE}"\n'
    return mezar_tasi_repo(tmp_path, ad, {dosya: govde})


def test_gecmiste_sahte_secret_bulunur(tmp_path):
    """Pozitif: gecmiste gizli anahtar varsa bulgu doner (deger DEGERIL)."""
    repo = _sirli_repo(tmp_path)
    sonuc = gecmis.tara(repo)
    assert sonuc["kismi"] is False
    assert len(sonuc["bulundu"]) == 1
    bulgu = sonuc["bulundu"][0]
    assert bulgu["tur"] == "aws-anahtari"
    assert bulgu["dosya"] == "ayar.py"
    assert len(bulgu["commit"]) == 8
    assert bulgu["izi"] and SAHTE not in bulgu["izi"]


def test_deger_hicbir_alana_girmez(tmp_path):
    """Negatif (guvenlik): ham deger ne bulguda ne de taranan metinde gorunmez."""
    repo = _sirli_repo(tmp_path)
    sonuc = gecmis.tara(repo)
    assert sonuc["bulundu"], "test icin gecmiste secret olmali"
    metin = repr(sonuc)
    assert SAHTE not in metin
    assert "AKIA" not in metin
    # Her bulgunun yalnizca izinli alanlari var.
    for bulgu in sonuc["bulundu"]:
        assert set(bulgu) == {"commit", "dosya", "tur", "izi"}


def test_temiz_gecmis_bulgu_yok(tmp_path):
    """Negatif: sir yoksa 'bulundu' bos ve tarama tam (kismi degil)."""
    repo = mezar_tasi_repo(tmp_path, "anlat", {"kod.py": "print('merhaba')\n"})
    sonuc = gecmis.tara(repo)
    assert sonuc["bulundu"] == []
    assert sonuc["kismi"] is False
    assert sonuc["not"] is None


def test_ornek_ve_test_dosyalari_atlanir(tmp_path):
    """Negatif: `test_`, `tests/`, `.example` ve `EXAMPLE` dosyalari sayilmaz."""
    icerik = f'aws = "{SAHTE}"\n'
    repo = mezar_tasi_repo(
        tmp_path,
        "anlat",
        {
            "tests/test_ayar.py": icerik,
            "test_kod.py": icerik,
            "ayar.env.example": icerik,
            "AYAR_ORNEK.txt": icerik,
            "src/kod.py": "print(1)\n",
        },
    )
    sonuc = gecmis.tara(repo)
    assert sonuc["bulundu"] == [], sonuc["bulundu"]


def test_ornek_dosya_mi_kisa_devre(tmp_path):
    """Yardimci: dosya siniflandirmasi (git log cok dosya verir, kisa devre sart)."""
    assert gecmis.ornek_dosya_mi("tests/test_a.py") is True
    assert gecmis.ornek_dosya_mi("kaynak/test_a.py") is True
    assert gecmis.ornek_dosya_mi("ayar.env.example") is True
    assert gecmis.ornek_dosya_mi("AYAR_ORNEK.txt") is True
    assert gecmis.ornek_dosya_mi("src/kod.py") is False
    assert gecmis.ornek_dosya_mi("tests_not/ilk.py") is False  # yalniz "tests/" dizini


def test_kismi_tarama_satir_siniri(tmp_path):
    """Negatif: kucuk satir siniri asilirsa 'kismi' True olur ve not dusulur."""
    repo = _sirli_repo(tmp_path)
    sonuc = gecmis.tara(repo, satir_limiti=5, sure_limiti=30)
    assert sonuc["kismi"] is True
    assert "satir siniri" in sonuc["not"]
    assert "tarama tamamlanmadi" in sonuc["not"]


def test_kismi_tarama_sure_siniri(tmp_path):
    """Negatif: kucuk sure siniri asilirsa 'kismi' True olur."""
    repo = mezar_tasi_repo(
        tmp_path, "anlat", {f"dosya{i:03d}.py": "x = 1\n" for i in range(200)}
    )
    sonuc = gecmis.tara(repo, satir_limiti=200000, sure_limiti=0.0001)
    assert sonuc["kismi"] is True
    assert "sure siniri" in sonuc["not"]


def test_birden_fazla_tur_bulunur(tmp_path):
    """Pozitif: farkli turler ayri ayri raporlanir."""
    repo = _sirli_repo(
        tmp_path,
        icerik=f'aws = "{SAHTE}"\ngh = "{SAHTE_GH}"\n',
    )
    sonuc = gecmis.tara(repo)
    turler = {b["tur"] for b in sonuc["bulundu"]}
    assert turler == {"aws-anahtari", "github-token"}


def test_silinen_satir_taranmaz(tmp_path):
    """Negatif: yalniz EKLENEN satirlar taranir, silinen kod sayilmaz.

    Commit 1 dosyayi ekler (secret `+` satirinda gorunur), commit 2 dosyayi SILER
    (secret `-` satirinda gorunur). Silme satiri da taransaydi ikinci bir bulgu
    uretilirdi: sonuc tam olarak TEK bulgudur ve commit'i ilk ekleme commit'idir.
    """
    repo = tmp_path / "anlat"
    repo.mkdir()
    git(repo, "init", "-q")
    yaz(repo / "ayar.py", f'aws = "{SAHTE}"\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "ilk")
    ilk = git(repo, "rev-parse", "--short=8", "HEAD").strip()
    (repo / "ayar.py").unlink()
    yaz(repo / "README.md", "# arsiv\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "mezar tasi")
    sonuc = gecmis.tara(repo)
    assert len(sonuc["bulundu"]) == 1, sonuc["bulundu"]
    assert sonuc["bulundu"][0]["commit"] == ilk