"""hook: push taramasi, hook kurulumu, hook girisi.

Git GERCEK bir gecici depoda calisir. Ag YOK. Ham anahtar hicbir
stdout/stderr/exception metninde gecmemelidir.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from anahtarlik import hook

ANAHTAR = "sk-SENTINEL8fHq2Lp9Zx4Wq7Nb3"
SIFIR = "0" * 40


# --------------------------------------------------------------------------
# Yardimcilar (bu dosya kendi kendine yeter: conftest'ten bagimsiz)
# --------------------------------------------------------------------------


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return proc.stdout


def repo_kur(tmp_path: Path, ad: str = "repo") -> Path:
    """Bos ama GECERLI bir git deposu kurar (`.git` dizini ile).

    KRITIK: bu makinada `core.hooksPath` KULLANICI DUZEYINDE ayarli
    (`~/.git-hooks-beyin`). Depo yerelinde `--unset` ETKISIZDIR (anahtar
    depoda degil, kullanici config'inde) ve `kur()` o dizine yazardi.
    Bu yuzden depo ici gecici bir hook yolu AÇIKÇA AYARLANIR: hicbir test
    kullanicinin hook dizinine YAZAMAZ.
    """
    yol = tmp_path / ad
    yol.mkdir()
    git(yol, "init", "-q", "-b", "main", ".")
    git(yol, "config", "user.email", "test@example.com")
    git(yol, "config", "user.name", "Test")
    git(yol, "config", "commit.gpgsign", "false")
    git(yol, "config", "core.hooksPath", str(yol / ".git" / "hooks"))
    return yol


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return repo_kur(tmp_path)


def commit_at(repo: Path, dosyalar: dict[str, str], mesaj: str = "w") -> str:
    for ad, icerik in dosyalar.items():
        yol = repo / ad
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(icerik, encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", mesaj)
    return git(repo, "rev-parse", "HEAD").strip()


def referans(yerel: str, uzak: str) -> tuple[str, str, str, str]:
    return ("refs/heads/main", yerel, "refs/heads/main", uzak)


# --------------------------------------------------------------------------
# HOOK_ICERIK
# --------------------------------------------------------------------------


def test_hook_icerigi_gecerli_sh_shebang():
    assert hook.HOOK_ICERIK.startswith("#!/bin/sh\n")


def test_hook_isareti_ikinci_satirda():
    """Isaret ilk satir sonrasi: `kur` idempotentligini bu satira bakar."""
    assert hook.HOOK_ICERIK.splitlines()[1] == hook.HOOK_ISARETI


def test_hook_icin_python_yoksa_pusu_ENGELLEMEZ():
    """fail-open DEGIL: cikis kodu 0 ama acik uyari stderr'e yazilir."""
    satirler = hook.HOOK_ICERIK
    assert "python bulunamadi" in satirler
    assert ">&2" in satirler
    # Uyari sonrasi cikis kodu 0 (push gider).
    assert satirler.rstrip().endswith("exit 0")


def test_hook_icin_cikis_kodu_aktarilir():
    """python bulununca `$?` aynen dondurulur: 1 -> push durur."""
    govde = hook.HOOK_ICERIK
    assert '"$_py" -P -m anahtarlik hook-tara' in govde
    assert "exit $?" in govde


# --------------------------------------------------------------------------
# diff_tara
# --------------------------------------------------------------------------


def test_diff_tara_yalniz_eklenen_satirlari():
    diff = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,1 +1,2 @@\n"
        f"-API_KEY=eski\n+API_KEY={ANAHTAR}\n"
    )
    bulgular = hook.diff_tara(diff)
    assert len(bulgular) == 1
    assert bulgular[0]["dosya"] == "app.py"
    assert bulgular[0]["tur"] == "sk-anahtari"


def test_diff_tara_baslik_satirlari_taranmaz():
    """`+++ b/app.py` basligi `+` ile baslar ama `+++` oldugu icin elenir."""
    diff = (
        "diff --git a/uzun-bir-dosya-adi.py b/uzun-bir-dosya-adi.py\n"
        "--- /dev/null\n"
        "+++ b/uzun-bir-dosya-adi.py\n"
        "@@ -0,0 +1 @@\n+x = 1\n"
    )
    assert hook.diff_tara(diff) == []


def test_diff_tara_binary_dosyayi_atlar():
    diff = (
        "diff --git a/gorsel.bin b/gorsel.bin\n"
        "index 0000000..1111111 100644\n"
        "Binary files /dev/null and b/gorsel.bin differ\n"
    )
    assert hook.diff_tara(diff) == []


def test_diff_tara_yeni_dosyada_env_dosyasi_bulgu():
    """`.env` push'a girmesi KENDISI bulgu; satirlari OKUNMAZ."""
    diff = (
        "diff --git a/.env b/.env\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/.env\n"
        "@@ -0,0 +1,2 @@\n" + f"+API_KEY={ANAHTAR}\n" + "+X=1\n"
    )
    bulgular = hook.diff_tara(diff)
    assert [b["tur"] for b in bulgular] == ["env-dosyasi"]
    assert bulgular[0]["dosya"] == ".env"
    assert bulgular[0]["satir"] == 0


def test_diff_tara_env_ornegi_bulgu_degil():
    diff = (
        "diff --git a/.env.example b/.env.example\n"
        "--- /dev/null\n"
        "+++ b/.env.example\n"
        "@@ -0,0 +1 @@\n+x = 1\n"
    )
    assert hook.diff_tara(diff) == []


def test_diff_tara_satir_numarasi_yeni_tarafta():
    """Satir numarasi YENI dosyadaki gercek konumdur (eski hunk degil)."""
    diff = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -10,2 +10,3 @@\n"
        " x = 1\n"          # baglam: yeni dosyada 10. satir
        f"+y = '{ANAHTAR}'\n"  # eklenen: yeni dosyada 11. satir
    )
    bulgular = hook.diff_tara(diff)
    assert bulgular[0]["satir"] == 11
    assert bulgular[0]["dosya"] == "app.py"


def test_diff_tara_baglam_satiri_taranmaz():
    """Yalniz `+` satirlari taranir: degismemis ` ` satiri bulgu DEGILDIR."""
    diff = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,2 +1,2 @@\n"
        f" # eski yorum: {ANAHTAR}\n"
        " x = 2\n"
    )
    assert hook.diff_tara(diff) == []


def test_diff_tara_hata_mesajinda_ham_yok():
    bulgular = hook.diff_tara(f"+++ b/a.py\n@@ -0,0 +1 @@\n+API_KEY={ANAHTAR}\n")
    assert ANAHTAR not in repr(bulgular)
    assert bulgular[0]["onizleme"] == "[maskeli:sk-anahtari]"


# --------------------------------------------------------------------------
# Terminal kacis enjeksiyonu (dosya adi -> ANSI)
# --------------------------------------------------------------------------


def test_diff_tara_dosya_adindaki_ansi_kacisi_temizlenir():
    """Git yollari C-quote eder ama `diff_tara` dogrudan da cagrilabilir:
    bulgu ekrana basilacagi icinde kontrol karakteri KALAMAZ."""
    kotu = "bad\x1b[31mRED\x1b[0m\x07.py"
    bulgular = hook.diff_tara(f"+++ b/a.py\n@@ -0,0 +1 @@\n+API_KEY={ANAHTAR}\n")
    assert bulgular[0]["dosya"] == "a.py"
    bulgu = hook.desen.bulgu(kotu, 3, "sk-anahtari")
    assert bulgu["dosya"] == "bad?[31mRED?[0m?.py"
    assert "\x1b" not in bulgu["dosya"] and "\x07" not in bulgu["dosya"]


def test_diff_tara_env_bulgusu_dosya_adini_temizler():
    """`env-dosyasi` bulgusu `bulgu()`'yu ATLAMAMALI (daha once oyleydi)."""
    kotu = ".env.\x1b[2J"
    diff = f"diff --git a/{kotu} b/{kotu}\n+++ b/{kotu}\n@@ -0,0 +1 @@\n+x=1\n"
    bulgular = hook.diff_tara(diff)
    assert bulgular and bulgular[0]["tur"] == "env-dosyasi"
    assert "\x1b" not in bulgular[0]["dosya"]
    assert "\x1b" not in repr(bulgular)


def test_desen_temiz_yol_normal_yolu_degistirmez():
    from anahtarlik import desen

    assert desen.temiz_yol("src/app.py") == "src/app.py"
    assert desen.temiz_yol("") == ""


# --------------------------------------------------------------------------
# tara_push (GERCEK git deposu)
# --------------------------------------------------------------------------


def test_tara_push_yeni_dal_env_ve_siri_yakalar(repo: Path):
    """remote_sha sifir: `git log --not --remotes` yolu kullanilir."""
    yerel = commit_at(repo, {"app.py": f'API_KEY = "{ANAHTAR}"\n', ".env": "X=1\n"})
    bulgular = hook.tara_push(repo, [referans(yerel, SIFIR)])
    turler = {b["tur"] for b in bulgular}
    assert "sk-anahtari" in turler
    assert "env-dosyasi" in turler
    dosyalar = {b["dosya"] for b in bulgular}
    assert ".env" in dosyalar and "app.py" in dosyalar


def test_tara_push_temiz_commit_gecer(repo: Path):
    yerel = commit_at(repo, {"okuyucu.py": "print('merhaba')\n"})
    assert hook.tara_push(repo, [referans(yerel, SIFIR)]) == []


def test_tara_push_diff_yolu_temiz_taban(repo: Path):
    """Uzak sha dolu: `git diff A..B` yolunda ESKI kod bulunmaz, YENI bulunur."""
    ilk = commit_at(repo, {"app.py": f'API_KEY = "{ANAHTAR}"\n'})
    ikinci = commit_at(repo, {"app.py": "print('temiz')\n"}, "duzelt")
    # Yalniz yeni commit'i push ediyoruz: eski anahtar TARAMAZ.
    assert hook.tara_push(repo, [referans(ikinci, ilk)]) == []
    # Butun araligi push edersek eski anahtar YAKALANIR.
    turler = {b["tur"] for b in hook.tara_push(repo, [referans(ikinci, SIFIR)])}
    assert "sk-anahtari" in turler


def test_tara_push_silme_push_atlanir(repo: Path):
    yerel = commit_at(repo, {"app.py": f'API_KEY = "{ANAHTAR}"\n'})
    # local_sha sifir = dal silme: eklenen satir yok.
    assert hook.tara_push(repo, [("refs/heads/main", SIFIR, "refs/heads/main", yerel)]) == []


def test_tara_push_bos_referans_listesi(repo: Path):
    assert hook.tara_push(repo, []) == []


def test_tara_push_ham_sir_dondurmez(repo: Path):
    yerel = commit_at(repo, {"app.py": f'API_KEY = "{ANAHTAR}"\n'})
    bulgular = hook.tara_push(repo, [referans(yerel, SIFIR)])
    assert bulgular
    assert ANAHTAR not in repr(bulgular)


# --------------------------------------------------------------------------
# kur
# --------------------------------------------------------------------------


def agac(yol: Path) -> list[str]:
    return sorted(p.relative_to(yol).as_posix() for p in yol.rglob("*") if p.is_file())


def test_kur_kuru_calistirma_dosya_sistemini_degistirmez(repo: Path):
    oncesi = agac(repo)
    sonuc = hook.kur(repo, uygula=False)
    assert agac(repo) == oncesi
    assert sonuc["uygulandi"] is False
    assert not (repo / ".git" / "hooks" / "pre-push").exists()


def test_kur_yazar_ve_isareti_icerir(repo: Path):
    sonuc = hook.kur(repo, uygula=True)
    hedef = Path(sonuc["yol"])
    assert sonuc["durum"] == "yazildi" and sonuc["uygulandi"] is True
    assert hedef.is_file()
    assert hook.HOOK_ISARETI in hedef.read_text(encoding="utf-8")


def test_kur_varsayilan_dry_run_dokunmaz(repo: Path):
    """Imza `uygula` almayi zorunlu kilar: kuru calistirma varsayilandir."""
    import inspect

    assert inspect.signature(hook.kur).parameters["uygula"].default is False


def test_kur_idempotent_tekrar_yazmaz(repo: Path):
    sonuc = hook.kur(repo, uygula=True)
    hedef = Path(sonuc["yol"])
    hedef.write_text(hedef.read_text(encoding="utf-8") + "# elle not\n", encoding="utf-8")
    sonuc = hook.kur(repo, uygula=True)
    assert sonuc["durum"] == "guncel" and sonuc["uygulandi"] is False
    assert "# elle not" in hedef.read_text(encoding="utf-8")


def test_kur_yabanci_hook_ustune_yazmaz(repo: Path):
    hedef = repo / ".git" / "hooks" / "pre-push"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    yabanci = "#!/bin/sh\n# baska bir arac\nexit 0\n"
    hedef.write_text(yabanci, encoding="utf-8")
    sonuc = hook.kur(repo, uygula=True)
    assert sonuc["durum"] == "yabanci-hook-var"
    assert sonuc["uygulandi"] is False
    assert hedef.read_text(encoding="utf-8") == yabanci


def test_kur_kuru_calistirma_yabanci_hook_dokunmaz(repo: Path):
    hedef = repo / ".git" / "hooks" / "pre-push"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    yabanci = "#!/bin/sh\n# baska bir arac\nexit 0\n"
    hedef.write_text(yabanci, encoding="utf-8")
    assert hook.kur(repo, uygula=False)["durum"] == "yabanci-hook-var"
    assert hedef.read_text(encoding="utf-8") == yabanci


def test_kur_hooks_path_ayari_goz_onunde(repo: Path):
    """`core.hooksPath` varsa hook dizini O yoldur ve raporlanir."""
    ozel = repo / "ozel-hooks"
    git(repo, "config", "core.hooksPath", str(ozel))
    sonuc = hook.kur(repo, uygula=False)
    assert sonuc["hooks_path"] == str(ozel)
    assert sonuc["yol"] == str(ozel / "pre-push")


def test_kur_depo_degil_olmaz(tmp_path: Path):
    sonuc = hook.kur(tmp_path, uygula=False)
    assert sonuc["durum"] == "git-depo-degil" and sonuc["yol"] is None


def test_kur_uygulamada_gecici_dosya_almaz(repo: Path):
    """Atomik yazim: gecici `.pre-push.*` artigi kalmaz.

    Git `init` hooks dizinine `*.sample` dosyalari koyar; onlar bize ait degildir.
    """
    sonuc = hook.kur(repo, uygula=True)
    dizin = Path(sonuc["yol"]).parent
    artiklar = [p.name for p in dizin.iterdir() if p.name.startswith(".pre-push.")]
    assert artiklar == []


def test_kur_kullanicinin_hook_dizinine_yazmaz(tmp_path: Path):
    """Guvenlik: gecici repo + GLOBAL `core.hooksPath` varken kur() hedefi
    gecici repo icinde kalmalidir (kullanicinin dizini DEGIL)."""
    repo = repo_kur(tmp_path)
    git(repo, "config", "core.hooksPath", str(tmp_path / "ozel-hooks"))
    sonuc = hook.kur(repo, uygula=True)
    assert Path(sonuc["yol"]).is_relative_to(tmp_path)
    assert Path(sonuc["yol"]).parent == tmp_path / "ozel-hooks"


# --------------------------------------------------------------------------
# hook_tara_main
# --------------------------------------------------------------------------


def test_hook_tara_main_bulgu_yok_sifir(repo: Path):
    import io

    yerel = commit_at(repo, {"a.py": "x = 1\n"})
    kod = hook.hook_tara_main(
        io.StringIO(f"refs/heads/main {yerel} refs/heads/main {SIFIR}\n"), repo
    )
    assert kod == 0


def test_hook_tara_main_bulgu_var_bir(repo: Path, capsys):
    import io

    yerel = commit_at(repo, {"a.py": f'API_KEY = "{ANAHTAR}"\n'})
    kod = hook.hook_tara_main(
        io.StringIO(f"refs/heads/main {yerel} refs/heads/main {SIFIR}\n"), repo
    )
    assert kod == 1
    cikti = capsys.readouterr()
    assert "a.py:1" in cikti.err
    assert hook.HOOK_ISARETI not in cikti.err
    assert ANAHTAR not in cikti.err and ANAHTAR not in cikti.out
    assert "--no-verify" in cikti.err


def test_hook_tara_main_bozuk_girdi(repo: Path):
    import io

    assert hook.hook_tara_main(io.StringIO(""), repo) == 0
    assert hook.hook_tara_main(io.StringIO("tek kelime\n"), repo) == 0


def test_hook_tara_main_git_hatasinda_sessizce_yutar_maz(repo: Path, capsys):
    """Git okunamazsa hata YUTULMAZ: acikca stderr'e yazilir, cikis 0."""
    import io

    kod = hook.hook_tara_main(
        io.StringIO(f"refs/heads/main {'f' * 40} refs/heads/main {SIFIR}\n"), repo
    )
    assert kod == 0
    assert "git" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Uc uca: gercek git deposunda hook kur + push denemesi
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Guvenlik: depodaki sahte `anahtarlik/` paketi CALISTIRILMAMALI (kod yurutme)
# --------------------------------------------------------------------------


def _sh_yok() -> bool:
    return subprocess.run(["sh", "-c", "exit 0"], capture_output=True).returncode != 0


@pytest.mark.skipif(_sh_yok(), reason="sh yok")
def test_kurulan_hook_depodaki_sahte_paketi_calistirmaz(tmp_path: Path):
    """EN KRITIK REGRESYON.

    `python -m anahtarlik` bulunulan dizini sys.path'in BASINA koyar. Hook
    depo KOKUNDA calistigi icin, kotu niyetli (veya yanlislikla) bir depoda
    bulunan `anahtarlik/` klasoru push aninda CALISIRILIRDI. Betik `-P` ile
    bunu kapatir ve modulu kendi dizininden (mutlak PYTHONPATH) yukler.
    """
    repo = repo_kur(tmp_path, ad="kotu")
    sahte = repo / "anahtarlik"
    sahte.mkdir()
    (sahte / "__init__.py").write_text("import sys; print('HIJACKED', file=sys.stderr)\n")
    (sahte / "__main__.py").write_text(
        "import sys; print('HIJACKED', file=sys.stderr); sys.exit(0)\n"
    )
    kanit = tmp_path / "calisti.txt"
    (sahte / "__main__.py").write_text(
        "import pathlib,sys;"
        f"pathlib.Path({str(kanit)!r}).write_text('calisti');"
        "sys.exit(0)\n"
    )
    betik = Path(hook.kur(repo, uygula=True)["yol"])
    icerik = betik.read_text(encoding="utf-8")
    assert hook.YOL_ISARETI not in icerik, "kur() yol yer tutucusu birakmis"
    assert "-P -m anahtarlik" in icerik
    # Gercekten kotu dizinden calistir: sahte paket TETIKLENMEMELI.
    proc = subprocess.run(
        ["sh", str(betik)], cwd=repo, input="", capture_output=True, text=True, timeout=60
    )
    assert not kanit.exists(), "hook, depodaki sahte anahtarlik paketini calistirdi"
    assert "HIJACKED" not in proc.stderr


def test_hook_icerigi_guvenli_cagirma_ve_yol():
    """Betik `-P` kullanir ve modul yolunu dogrudan (mutlak) verir."""
    icerik = hook._betik()
    assert hook.YOL_ISARETI not in icerik
    assert "PYTHONSAFEPATH=1" in icerik
    assert 'export PYTHONPATH=' in icerik
    assert "-P -m anahtarlik hook-tara" in icerik


def test_kur_yol_tirnakli_kaçis_uygular():
    """Yol tek tirnak icinde yazilir: tirnak iceren yol SÖZ dizgisi olmaz."""
    kotu = "C:\\a b\\o'br\\anahtarlik"
    if hook.shlex.quote(kotu) == kotu:
        pytest.skip("bu kabuk icin tirnak kacisi gerekmiyor")
    # shlex.quote TEK tirnakli bir sozu `'\''` ile bozar: sozu kirilmaz.
    assert hook.shlex.quote(kotu).startswith("'") and hook.shlex.quote(kotu).endswith("'")


def test_kur_guncel_kontrolu_guvenli_cagriyi_zorunlu_kilar(tmp_path: Path):
    """Eski surum (isareti var ama `-P` yok) `guncel` sayilmaz: yenilenir."""
    repo = repo_kur(tmp_path, ad="eski")
    hedef = repo / ".git" / "hooks" / "pre-push"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(
        f"#!/bin/sh\n{hook.HOOK_ISARETI}\n\"$_py\" -m anahtarlik hook-tara\n", encoding="utf-8"
    )
    assert hook.kur(repo, uygula=False)["durum"] == "eski-surum"
    sonuc = hook.kur(repo, uygula=True)
    assert sonuc["durum"] == "yazildi" and sonuc["uygulandi"] is True
    assert "-P -m anahtarlik" in hedef.read_text(encoding="utf-8")
    assert hook.kur(repo, uygula=True)["durum"] == "guncel"  # artik guncel


@pytest.mark.skipif(_sh_yok(), reason="sh yok")
def test_hook_tara_main_gercek_git_deposunda_calisir(repo: Path):
    """Kurulan betik GERCEKTEN `hook-tara` calistirip bulguyu bloklar.

    `test_kur_*` yalniz dosyaya bakar; bu test betigi `sh` ile calistirir.
    """
    yerel = commit_at(repo, {"a.py": f'API_KEY = "{ANAHTAR}"\n'})
    betik = Path(hook.kur(repo, uygula=True)["yol"])
    proc = subprocess.run(
        ["sh", str(betik)],
        cwd=repo,
        input=f"refs/heads/main {yerel} refs/heads/main {SIFIR}\n",
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 1, proc.stderr
    assert "a.py:1" in proc.stderr and ANAHTAR not in proc.stderr


@pytest.mark.skipif(subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
                    reason="git yok")
def test_kurulan_hook_gereklilikleri_kar_sar(repo: Path):
    """Kurulan betik yalnizca istenen komutu cagirir (ag yok, gh yok)."""
    icerik = Path(hook.kur(repo, uygula=True)["yol"]).read_text(encoding="utf-8")
    assert "hook-tara" in icerik
    assert "curl" not in icerik and "wget" not in icerik
    assert icerik.startswith("#!/bin/sh\n")
    # `sh` altinda calisir: satir sonlari KESINLIKLE LF olmali (CRLF bozardi).
    assert "\r" not in icerik

def test_kur_simgeli_pre_push_a_ziginina_yazmaz(tmp_path: Path):
    """`pre-push` bir sembolik bag ise kurulum ONUN USTUNE yazmaz.

    Yazarsa bagin hedefi (repo disinda olabilir) ezilir. `os.replace` bagi
    izlemez ama kurulumun isi degildir: kullaniciya bildirilir.
    """
    repo = repo_kur(tmp_path, ad="simg")
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    hedef = tmp_path / "diger-arac-pre-push"
    hedef.write_text("#!/bin/sh\n# baska arac\nexit 0\n", encoding="utf-8")
    try:
        os.symlink(hedef, hooks / "pre-push")
    except OSError:
        pytest.skip("sembolik bag olusturulamadi (Windows yetkisi)")
    sonuc = hook.kur(repo, uygula=True)
    assert sonuc["durum"] == "simgeler" and sonuc["uygulandi"] is False
    assert hedef.read_text(encoding="utf-8") == "#!/bin/sh\n# baska arac\nexit 0\n"


def test_kur_simgeli_pre_push_guardi_calisir(repo: Path, monkeypatch):
    """Windows'ta sembolik bag yetkisi yoksa gercek test atlanir; bu test
    `pre-push` bir bag oldugunda kur()un YAZMADIGINI ve durumu bildirdigini dogrular."""
    hedef = repo / ".git" / "hooks" / "pre-push"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    gercek = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == "pre-push")
    try:
        sonuc = hook.kur(repo, uygula=True)
    finally:
        monkeypatch.setattr(Path, "is_symlink", gercek)
    assert sonuc["durum"] == "simgeler" and sonuc["uygulandi"] is False
    assert not hedef.exists()
