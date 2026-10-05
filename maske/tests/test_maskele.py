"""maskele: kuru calistirma dokunmaz, --uygula yazar, CRLF/izin/idempotent korunur."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from maske import maskele

from conftest import (
    GIZLI_AWS,
    GIZLI_SK,
    REPO_ROOT,
    repo_kur,
    run_module_cli,
    tree_hash,
)


def test_kuru_calistirma_dosyaya_dokunmaz(tmp_path: Path, ev_isole):
    """Varsayilan: hicbir dosya yazilmaz (bayt bayt ayni kalir)."""
    dosya = repo_kur(tmp_path / "r", {"a.py": f'KEY="{GIZLI_SK}"\n'}) / "a.py"
    once = tree_hash(tmp_path / "r")
    sonuc = maskele.uygula([tmp_path / "r"], yaz=False)
    assert sonuc["bulgar"] and sonuc["maskelendi"] == []
    assert tree_hash(tmp_path / "r") == once
    assert GIZLI_SK in dosya.read_text(encoding="utf-8")


def test_uygula_maskeler(tmp_path: Path, ev_isole):
    dosya = repo_kur(tmp_path / "r", {"a.py": f'KEY="{GIZLI_SK}"\n'}) / "a.py"
    sonuc = maskele.uygula([tmp_path / "r"], yaz=True)
    icerik = dosya.read_text(encoding="utf-8")
    assert GIZLI_SK not in icerik
    assert icerik == 'KEY="***MASKELENDI:sk-anahtari***"\n'
    assert len(sonuc["maskelendi"]) == 1


def test_ikinci_calistirma_idempotent(tmp_path: Path, ev_isole):
    """Maske bir sir DEGILDIR: ikinci calistirma bulgu bulmaz, dosyaya dokunmaz."""
    repo = repo_kur(tmp_path / "r", {"a.py": f'KEY="{GIZLI_SK}"\n'})
    maskele.uygula([repo], yaz=True)
    bir = tree_hash(repo)
    ikinci = maskele.uygula([repo], yaz=True)
    assert ikinci["bulgar"] == []
    assert tree_hash(repo) == bir


def test_crlf_korunur(tmp_path: Path, ev_isole):
    """CRLF dosya CRLF kalir: satir sonlari yeniden URETILMEZ."""
    ham = f"once\r\nKEY={GIZLI_SK}\r\nson\r\n".encode()
    repo = repo_kur(tmp_path / "r", {"a.txt": ham})
    maskele.uygula([repo], yaz=True)
    yeni = (repo / "a.txt").read_bytes()
    assert b"\r\n" in yeni and yeni.count(b"\r\n") == 3
    assert b"\n\n" not in yeni.replace(b"\r\n", b"")  # yalniz CRLF


def test_son_satirin_satir_sonusu_korunur(tmp_path: Path, ev_isole):
    repo = repo_kur(tmp_path / "r", {"a.txt": f"KEY={GIZLI_SK}".encode()})
    maskele.uygula([repo], yaz=True)
    assert not (repo / "a.txt").read_bytes().endswith(b"\n")


def test_dosya_izni_korunur(tmp_path: Path, ev_isole):
    dosya = repo_kur(tmp_path / "r", {"a.sh": f'KEY="{GIZLI_SK}"\n'}) / "a.sh"
    dosya.chmod(0o755)
    maskele.uygula([tmp_path / "r"], yaz=True)
    assert stat.S_IMODE(dosya.stat().st_mode) == 0o755


def test_bulgusuz_dosya_dokunulmaz(tmp_path: Path, ev_isole):
    """Bulgu yoksa dosya YAZILMAZ (mtime degismez)."""
    dosya = repo_kur(tmp_path / "r", {"a.py": "print('temiz')\n"}) / "a.py"
    os.utime(dosya, (1_000_000, 1_000_000))
    maskele.uygula([tmp_path / "r"], yaz=True)
    assert dosya.stat().st_mtime == 1_000_000


def test_bir_dosyada_birden_fazla_span(tmp_path: Path, ev_isole):
    repo = repo_kur(tmp_path / "r", {"a.py": f'a = {GIZLI_AWS}  b = {GIZLI_SK}\n'})
    maskele.uygula([repo], yaz=True)
    icerik = (repo / "a.py").read_text(encoding="utf-8")
    assert icerik == (
        "a = ***MASKELENDI:aws-anahtari***  b = ***MASKELENDI:sk-anahtari***\n"
    )


def test_hedef_disi_dosya_maskelenmez(tmp_path: Path, ev_isole):
    """Test/ornek dosyalara `--uygala` da dokunmaz."""
    repo = repo_kur(tmp_path / "r", {"tests/test_a.py": f'KEY="{GIZLI_SK}"\n'})
    sonuc = maskele.uygula([repo], yaz=True)
    assert sonuc["maskelendi"] == []
    assert GIZLI_SK in (repo / "tests/test_a.py").read_text(encoding="utf-8")


def test_git_icine_yazilmaz(tmp_path: Path, ev_isole):
    repo = repo_kur(tmp_path / "r", {})
    (repo / ".git").mkdir(exist_ok=True)
    (repo / ".git" / "config").write_text(f'KEY="{GIZLI_SK}"\n', encoding="utf-8")
    once = (repo / ".git" / "config").read_bytes()
    maskele.uygula([repo], yaz=True)
    assert (repo / ".git" / "config").read_bytes() == once


def test_gectici_dosya_kalmaz(tmp_path: Path, ev_isole):
    """Atomik yazma: basarisiz olsa bile .tmp artigi olmaz."""
    repo = repo_kur(tmp_path / "r", {"a.py": f'KEY="{GIZLI_SK}"\n'})
    maskele.uygula([repo], yaz=True)
    artik = [p.name for p in repo.iterdir() if p.name.endswith(".tmp")]
    assert artik == []


def test_rotasyon_ayni_siri_tek_satira_indirir(tmp_path: Path, ev_isole):
    """Ayni deger iki dosyada: rotasyon listesi TEK satir."""
    repo = repo_kur(tmp_path / "r", {"a.py": f'KEY="{GIZLI_SK}"\n', "b.py": f'K2="{GIZLI_SK}"\n'})
    kayitlar = maskele.rotasyon(maskele.uygula([repo], yaz=True)["bulgar"])
    ayni = [k for k in kayitlar if len(k["nerede"]) > 1]
    assert len(ayni) == 1
    assert len(ayni[0]["nerede"]) == 2


def test_rotasyon_deger_tasicamaz(tmp_path: Path, ev_isole):
    repo = repo_kur(tmp_path / "r", {"a.py": f'KEY="{GIZLI_SK}"\n'})
    kayitlar = maskele.rotasyon(maskele.uygula([repo], yaz=True)["bulgar"])
    assert GIZLI_SK not in repr(kayitlar)
    assert kayitlar[0]["ad"] == "KEY" and kayitlar[0]["tur"] == "sk-anahtari"
    # Kardes arac (`envanter.ayni_deger`) ile ayni sozlesme: tek etiket `ad`,
    # butun etiketler `adlar`. `ad` uydurulmaz -- gercek etiketten okunur.
    assert kayitlar[0]["adlar"] == ["KEY"]


def test_cok_etiketli_sirde_ad_ve_adlar(tmp_path: Path, ev_isole):
    """Ayni sir iki etiketle gecerse: `adlar` ikisini de toplar, `ad` biri."""
    repo = repo_kur(
        tmp_path / "r", {"a.py": f'KEY="{GIZLI_SK}"\n', "b.py": f'ZED="{GIZLI_SK}"\n'}
    )
    kayit = maskele.rotasyon(maskele.uygula([repo], yaz=True)["bulgar"])[0]
    assert sorted(kayit["adlar"]) == ["KEY", "ZED"]
    assert kayit["ad"] in kayit["adlar"]
    assert len(kayit["nerede"]) == 2

# --------------------------------------------------------------------------
# TUZ: repo (kaynak agaci) icine ASLA yazilmaz
# --------------------------------------------------------------------------


def _depo_izgara(kok: Path) -> dict[str, tuple[int, bytes]]:
    """`maske/` agacinin (yol -> (boyut, icerik)) haritasi; tuz dahil her sey."""
    return {
        p.relative_to(kok).as_posix(): (p.stat().st_size, p.read_bytes())
        for p in kok.rglob("*")
        if p.is_file() and not p.is_symlink() and "__pycache__" not in p.parts
    }


def test_tuz_repo_disi_kullanici_veri_dizinine_gider(tmp_path: Path, ev_isole):
    """Varsayilan tuz yeri `MASKE_TUZ_DIZINI`, yoksa `~/.maske/`: depo DEGIL."""
    repo = repo_kur(tmp_path / "r", {"a.py": f'KEY="{GIZLI_SK}"\n'})
    maskele.uygula([repo], yaz=True)  # iz uretir -> tuz yazilir
    assert (ev_isole / ".maske" / "tuz").is_file()
    assert not (REPO_ROOT / "_anahtarlik_gecici").exists()


def test_tuz_dizini_env_ustune_biner(tmp_path: Path, ev_isole, monkeypatch):
    """`MASKE_TUZ_DIZINI` acikca yonlendirilirse o kazanir."""
    hedef = tmp_path / "ozel-tuz"
    monkeypatch.setenv("MASKE_TUZ_DIZINI", str(hedef))
    repo = repo_kur(tmp_path / "r", {"a.py": f'KEY="{GIZLI_SK}"\n'})
    maskele.uygula([repo], yaz=True)
    assert (hedef / "tuz").is_file()
    assert not (REPO_ROOT / "_anahtarlik_gecici").exists()


def test_hicbir_test_repo_yazmaz(tmp_path: Path, ev_isole):
    """ISPAT: maske/ agacina hicbir test yazmaz -- tuz dahil bayt bayt ayni.

    In-process (dogrudan `maskele.uygula`) ve alt surec (`python -m maske`)
    yollarinin IKISI de tuz uretir; ikisi de repo agacini degistirmeden gecmelidir.
    Once `_anahtarlik_gecici` toplantiydi: alt surec, tuz icin depo govdesini
    kullanma alani olarak seciyordu.
    """
    before = _depo_izgara(REPO_ROOT)

    repo = repo_kur(tmp_path / "r", {"a.py": f'KEY="{GIZLI_SK}"\n'})
    maskele.uygula([repo], yaz=True)                      # in-process
    run_module_cli("tara", "--kok", str(repo))             # alt surec (cwd verilMEDi)
    run_module_cli("uygula", "--kok", str(repo), "--uygula")

    assert _depo_izgara(REPO_ROOT) == before
    assert not (REPO_ROOT / "_anahtarlik_gecici").exists()
    assert not any("tuz" in p.name for p in REPO_ROOT.rglob("tuz"))
