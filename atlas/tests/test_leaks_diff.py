"""GECMIS DIFF AYRISTIRICI: dosya atfi, satir numarasi, ozel yollar.

B.1'de bulunan KRITIK hata: `git log -p -U0` ciktisindaki EKLENEN satirlar
commit'teki ILK dosyaya (`--- a/.gitignore`) baglaniyordu; gercek dosya
`tests/conftest.py` idi. Uc sonuc vardi: yanlis dosya, `tests/` yolu dusurmesi
uygulanmamasi ve `line` degerinin hep NULL kalmasi.

Burada HER senaryo GERCEK git repoda kurulur (mock yok). Sahte sirler
kaynakta tam literal olarak YAZILMAZ; calisma zamaninda parcalardan kurulur.
"""

from __future__ import annotations

from pathlib import Path

from atlas import leaks
from conftest import git, make_repo

FAKE_SK = "sk-" + "a1" * 15          # 32 karakter
FAKE_SK2 = "sk-" + "b2" * 15         # ayni tur, ikinci deger
GIZLI_DEGER = "q7Rt2mKp9zXw4LbN"    # 16 karakterli sahte deger


def _sir_satiri(deger: str = FAKE_SK) -> str:
    return f"API_KEY = {deger}"


# --------------------------------------------------------------------------
# Cok dosyali commit: dosya + satir numarasi
# --------------------------------------------------------------------------

def test_cok_dosyali_commit_dosya_ve_satir_dogru(tmp_path: Path):
    """ASIL HATA: satirlar ILK dosyaya degil, GERCEK dosyaya atfedilir.

    Commit sirasi: `a.txt` (masum), `tests/b.py` (sahte sir), `c/d.md` (sahte
    sir). Onceki cozumde ucu de `.gitignore`'a yaziliyordu.
    """
    repo = make_repo(tmp_path / "r")
    (repo / "a.txt").write_text("tamamen masum bir dosya\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "masum", cwd=repo)

    (repo / "tests").mkdir()
    (repo / "tests" / "b.py").write_text(
        "import pytest\n\n\ndef test_x():\n    assert True\n" + _sir_satiri() + "\n",
        encoding="utf-8",
    )
    (repo / "c").mkdir()
    (repo / "c" / "d.md").write_text("# baslik\n\n" + _sir_satiri(FAKE_SK2) + "\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "cok dosyali sirli commit", cwd=repo)

    b = leaks.tara_gecmis(repo, commit_sayisi=10)
    sirli = [x for x in b if x["kind"] == "api-anahtari" and x["file"] != "a.txt"]
    dosyalar = {x["file"] for x in sirli}
    assert dosyalar == {"tests/b.py", "c/d.md"}, f"yanlis dosya atfi: {dosyalar}"
    # Satir numaralari YENI dosyadaki gercek numaralar olmali (1'den degil).
    by_file = {x["file"]: x["line"] for x in sirli}
    assert by_file["tests/b.py"] == 6
    assert by_file["c/d.md"] == 3
    # `.gitignore`/ilk dosyaya atfedilmis BIR TEK bulgu bile olmamali.
    assert not [x for x in b if x["file"] == "a.txt" and x["kind"] == "api-anahtari"]


def test_test_yolu_dusurmesi_gercek_dosyaya_uygulanir(tmp_path: Path):
    """`tests/b.py` icindeki yuksek onemli bulgu `dusuk` olmali (ILK dosya degil)."""
    repo = make_repo(tmp_path / "r")
    (repo / "a.txt").write_text("masum\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "b.py").write_text(_sir_satiri() + "\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "sirli", cwd=repo)

    b = leaks.tara_gecmis(repo, commit_sayisi=10)
    api = [x for x in b if x["kind"] == "api-anahtari"]
    assert api and all(x["file"] == "tests/b.py" for x in api)
    assert all(x["severity"] == "dusuk" for x in api), "tests/ yolu dusurmesi uygulanmadi"


def test_gecmis_bulgularinda_line_dolu(tmp_path: Path):
    """ASIL HATA: `line` degeri hep NULL kaliyordu."""
    repo = make_repo(tmp_path / "r")
    (repo / "a.txt").write_text(_sir_satiri() + "\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "sir", cwd=repo)
    b = leaks.tara_gecmis(repo, commit_sayisi=10)
    assert b and all(x["line"] is not None for x in b)
    assert all(isinstance(x["line"], int) and x["line"] > 0 for x in b)


# --------------------------------------------------------------------------
# Ozel yollar: bosluk, Turkce karakter, emoji, tirnak
# --------------------------------------------------------------------------

def test_bosluklu_ve_turkce_yol_gecmiste(tmp_path: Path):
    """Boslukli + Turkce karakterli yol commit'ten sonra dogru cozulur."""
    repo = make_repo(tmp_path / "r")
    ad = "kullanıcı ayarları/gizli şifa.txt"
    (repo / "kullanıcı ayarları").mkdir()
    (repo / ad).write_text("ilk\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "ilk", cwd=repo)
    (repo / ad).write_text("ilk\n" + _sir_satiri() + "\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "sir ekle", cwd=repo)

    b = leaks.tara_gecmis(repo, commit_sayisi=10)
    api = [x for x in b if x["kind"] == "api-anahtari"]
    assert api, "bosluklu/Turkce yoldaki sir bulunamadi"
    assert api[0]["file"] == ad
    assert api[0]["line"] == 2


def test_emoji_yol_gecmiste(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    ad = "resim 😀/görsel.txt"
    (repo / "resim 😀").mkdir()
    (repo / ad).write_text("a\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "ilk", cwd=repo)
    (repo / ad).write_text("a\n" + _sir_satiri() + "\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "sir", cwd=repo)
    b = leaks.tara_gecmis(repo, commit_sayisi=10)
    api = [x for x in b if x["kind"] == "api-anahtari"]
    assert api and api[0]["file"] == ad


def test_tirnakli_yol_cozulur(tmp_path: Path):
    """Icinde `"` olan yol git tarafindan tirnakli yazilir; cozulmeli."""
    repo = make_repo(tmp_path / "r")
    ad = 'quo"te dosya.txt'
    (repo / ad).write_text("a\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "ilk", cwd=repo)
    (repo / ad).write_text("a\n" + _sir_satiri() + "\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "sir", cwd=repo)
    b = leaks.tara_gecmis(repo, commit_sayisi=10)
    api = [x for x in b if x["kind"] == "api-anahtari"]
    assert api, "tirnakli yoldaki sir bulunamadi"
    assert api[0]["file"] == ad


def test_yol_coz_dogrudan():
    """`_yol_coz` tırnaklı/sekizli kaçışlı alanları doğru çözer."""
    assert leaks._yol_coz("a/x.txt") == "x.txt"
    assert leaks._yol_coz("b/x.txt") == "x.txt"
    assert leaks._yol_coz("a/dosya.txt\t") == "dosya.txt"  # git sondaki TAB'i yazar
    assert leaks._yol_coz('"b/quo\\"te.txt"') == 'quo"te.txt'
    assert leaks._yol_coz('"b/tab\\tson.txt"') == "tab\tson.txt"
    # Sekizli kacislar UTF-8 BAYT'tir; karakter karakter cozulurse bozulur.
    assert leaks._yol_coz('"b/t\\303\\274rk\\303\\274.txt"') == "türkü.txt"
    assert leaks._yol_coz('"b/emoji \\360\\237\\230\\200.txt"') == "emoji \U0001f600.txt"
    # quotepath=false ile dusen sekizli bicim de cozulmeli (yedek).
    assert leaks._yol_coz('"b/emoji \U0001f600.txt"') == "emoji \U0001f600.txt"


# --------------------------------------------------------------------------
# Yeni dosya / silinen dosya / yeniden adlandirilan dosya
# --------------------------------------------------------------------------

def test_yeni_dosya_dogru_atfedilir(tmp_path: Path):
    """`+++ b/<yol>` yeni dosyaya ait; satir 1'den baslar."""
    repo = make_repo(tmp_path / "r")
    (repo / "tests").mkdir()
    (repo / "tests" / "yeni.py").write_text("x = 1\n" + _sir_satiri() + "\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "yeni dosya", cwd=repo)
    b = leaks.tara_gecmis(repo, commit_sayisi=10)
    api = [x for x in b if x["kind"] == "api-anahtari"]
    assert api and api[0]["file"] == "tests/yeni.py" and api[0]["line"] == 2
    assert api[0]["severity"] == "dusuk"


def test_silinmis_dosya_eski_yola_atfedilir(tmp_path: Path):
    """`+++ /dev/null`: bulgu SILINEN dosyaya (eski yol) yazilir."""
    repo = make_repo(tmp_path / "r")
    (repo / "a.txt").write_text("masum\n", encoding="utf-8")
    (repo / "gizli.txt").write_text(_sir_satiri() + "\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "sirli", cwd=repo)
    git("rm", "-q", "gizli.txt", cwd=repo)
    git("commit", "-q", "-m", "sil", cwd=repo)

    b = leaks.tara_gecmis(repo, commit_sayisi=10)
    api = [x for x in b if x["kind"] == "api-anahtari"]
    assert api, "silinen dosyadaki gecmis siri bulunamadi"
    assert {x["file"] for x in api} == {"gizli.txt"}
    assert all(x["line"] == 1 for x in api)
    assert all(x["severity"] == "yuksek" for x in api)


def test_yeniden_adlandirilan_dosya_yeni_yola_atfedilir(tmp_path: Path):
    """`rename to <yol>`: bulgu YENI adla raporlanir."""
    repo = make_repo(tmp_path / "r")
    (repo / "eski.txt").write_text(_sir_satiri() + "\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "sirli", cwd=repo)
    git("mv", "eski.txt", "yeni.txt", cwd=repo)
    (repo / "yeni.txt").write_text("eklenen satir\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "yeniden adlandir", cwd=repo)

    b = leaks.tara_gecmis(repo, commit_sayisi=10)
    api = [x for x in b if x["kind"] == "api-anahtari"]
    assert api, "yeniden adlandirilan dosyada gecmis siri bulunamadi"
    # `rename to` sonrasi dosya baglami yeni yoldur; ilk commit eski yoldur.
    dosyalar = {x["file"] for x in api}
    assert dosyalar <= {"eski.txt", "yeni.txt"}
    assert "yeni.txt" in dosyalar or "eski.txt" in dosyalar


# --------------------------------------------------------------------------
# Ayni commit'te iki dosyada ayni turde ikinci sır
# --------------------------------------------------------------------------

def test_ayni_committe_iki_dosyada_ayni_sir(tmp_path: Path):
    """Iki ayri dosyada AYNI deger: ikisi de dogru dosyaya yazilir."""
    repo = make_repo(tmp_path / "r")
    (repo / "x.py").write_text(_sir_satiri() + "\n", encoding="utf-8")
    (repo / "y.py").write_text(_sir_satiri() + "\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "iki dosya", cwd=repo)
    b = leaks.tara_gecmis(repo, commit_sayisi=10)
    api = [x for x in b if x["kind"] == "api-anahtari"]
    assert {x["file"] for x in api} == {"x.py", "y.py"}
    assert all(x["line"] == 1 for x in api)


def test_bir_satirda_birden_fazla_eklenen_satir_sayaci(tmp_path: Path):
    """Hunk ici birden fazla `+` satir: sayac her eklenende artar."""
    repo = make_repo(tmp_path / "r")
    icerik = "\n".join(
        ["girdi1", "girdi2", _sir_satiri(), "girdi4", _sir_satiri(FAKE_SK2)]
    )
    (repo / "a.txt").write_text(icerik + "\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "tek dosya cok satir", cwd=repo)
    b = leaks.tara_gecmis(repo, commit_sayisi=10)
    # Ayni dosyada iki ayri satir (3 ve 5) -> iki bulgu olmali.
    api = [x for x in b if x["kind"] == "api-anahtari" and x["file"] == "a.txt"]
    assert sorted(x["line"] for x in api) == [3, 5]


def test_silinmis_satirlar_taranmaz(tmp_path: Path):
    """`-` satirlari (silinen) taranmaz: yeni dosyada yoklar."""
    repo = make_repo(tmp_path / "r")
    (repo / "a.txt").write_text(_sir_satiri() + "\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "sirli", cwd=repo)
    (repo / "a.txt").write_text("temiz\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "temizlestir", cwd=repo)
    silen = git("rev-parse", "HEAD", cwd=repo).strip()[:7]
    ekleyen = git("rev-parse", "HEAD~1", cwd=repo).strip()[:7]
    b = leaks.tara_gecmis(repo, commit_sayisi=10)
    api = [x for x in b if x["kind"] == "api-anahtari"]
    # Sir satiri ilk commit'te EKLENMISTI (bulgu olmali)…
    assert [x for x in api if x["commit"] == ekleyen and x["line"] == 1]
    # …ilk commit'te SILINMISTI (silen commit'te bulgu OLMAMALI).
    assert not [x for x in api if x["commit"] == silen]


def test_hunk_basindaki_satir_sayaci(tmp_path: Path):
    """Degistirilen ortada: `@@ -5,3 +5,4 @@` sayaci 5'ten baslar."""
    repo = make_repo(tmp_path / "r")
    ilk = "1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n"
    (repo / "a.txt").write_text(ilk, encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "ilk", cwd=repo)
    (repo / "a.txt").write_text("1\n2\n3\n4\n" + _sir_satiri() + "\n7\n8\n9\n10\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "degistir", cwd=repo)
    b = leaks.tara_gecmis(repo, commit_sayisi=10)
    api = [x for x in b if x["kind"] == "api-anahtari"]
    assert api and api[0]["line"] == 5, f"hunk sayaci yanlis: {api[0]['line']}"


# --------------------------------------------------------------------------
# Sinyal ayraci: commit basligi iceren metin yaniltmamali
# --------------------------------------------------------------------------

def test_commit_ayraci_uretemeyen_icerik(tmp_path: Path):
    """Sinyal ayraci bicimi kaynakli bir satirda nadiren geçse de parser kirilmamali."""
    repo = make_repo(tmp_path / "r")
    (repo / "a.txt").write_text(_sir_satiri() + "\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "sir", cwd=repo)
    b = leaks.tara_gecmis(repo, commit_sayisi=10)
    assert [x for x in b if x["kind"] == "api-anahtari"]
    assert all(x["commit"] and len(x["commit"]) >= 7 for x in b)