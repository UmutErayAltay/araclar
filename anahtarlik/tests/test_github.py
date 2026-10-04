"""github: origin adi, workflow secret referanslari, gh listesi, fark.

Ag YOK ve gercek `gh` CALISTIRILMAZ: `calistir` parametresine sahte bir
cagirici enekte edilir. gh DEGER vermez, burada da deger okunmaz.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from anahtarlik import github


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return proc.stdout


def git_esnek(repo: Path, *args: str) -> str:
    """Cikis kodu kritik olmayan git komutu (`--unset` ayar yoksa 5 doner)."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.stdout


def repo_kur(tmp_path: Path, ad: str = "repo") -> Path:
    yol = tmp_path / ad
    yol.mkdir()
    git(yol, "init", "-q", "-b", "main", ".")
    git(yol, "config", "user.email", "test@example.com")
    git(yol, "config", "user.name", "Test")
    return yol


class SahteCikti:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def sahte_gh(*, rc=0, adlar=(), ham=None, hata=None):
    """gh'yi taklit eden `calistir`. `cagrilan` cagrilari kaydeder."""
    cagrilan: list[list[str]] = []

    def calistir(komut):
        cagrilan.append(list(komut))
        if hata is not None:
            raise hata
        if ham is not None:
            return SahteCikti(rc, ham)
        if rc != 0:
            return SahteCikti(rc, "", "gh: not authenticated")
        return SahteCikti(0, json.dumps([{"name": a} for a in adlar]))

    calistir.cagrilan = cagrilan
    return calistir


def origin_ekle(repo: Path, url: str) -> None:
    git(repo, "remote", "add", "origin", url)


def workflow_yaz(repo: Path, ad: str, icerik: str) -> None:
    dizin = repo / ".github" / "workflows"
    dizin.mkdir(parents=True, exist_ok=True)
    yol = dizin / ad
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(icerik, encoding="utf-8")


# --------------------------------------------------------------------------
# repo_adi
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, beklenen",
    [
        ("https://github.com/umut/atlas.git", "umut/atlas"),
        ("https://github.com/umut/atlas", "umut/atlas"),
        ("http://github.com/umut/atlas.git", "umut/atlas"),
        ("git@github.com:umut/atlas.git", "umut/atlas"),
        ("ssh://git@github.com/umut/atlas.git", "umut/atlas"),
    ],
)
def test_repo_adi_iki_bicim(tmp_path: Path, url: str, beklenen: str):
    repo = repo_kur(tmp_path)
    origin_ekle(repo, url)
    assert github.repo_adi(repo) == beklenen


def test_repo_adi_github_degil_none(tmp_path: Path):
    repo = repo_kur(tmp_path)
    origin_ekle(repo, "https://gitlab.com/umut/atlas.git")
    assert github.repo_adi(repo) is None


def test_repo_adi_origin_yok_none(tmp_path: Path):
    assert github.repo_adi(repo_kur(tmp_path)) is None


# --------------------------------------------------------------------------
# repo_adi: guvenlik (arguman enjeksiyonu / sahte host)
# --------------------------------------------------------------------------

_SAHTE_VEYA_ZARARLI = [
    "https://mygithub.com/umut/atlas.git",      # sahte host
    "https://github.com.evil.com/umut/atlas",   # sahte alt alan adi
    "https://gitlab.com/umut/atlas.git",
    "https://evil.com/?x=https://github.com/umut/atlas",  # URL SONUNDA github degil
    "https://github.com/umut/atlas; rm -rf /",  # kabuk karakteri
    "https://github.com/umut/atlas --json x",   # ek bayrak
    "https://github.com/-x/-y",                 # `-` ile baslayan: gh bayragi olurdu
    "git@github.com:--repo/x",
    "https://github.com/umut/atl as",           # bosluk
    "https://github.com//umut/atlas",           # bos bilesen
]


@pytest.mark.parametrize("url", _SAHTE_VEYA_ZARARLI)
def test_repo_adi_zararli_url_reddedilir(tmp_path: Path, url: str):
    """Bu ad `gh --repo <ad>` degeri olurdu: bayrak/enjeksiyon olmamali."""
    repo = repo_kur(tmp_path)
    origin_ekle(repo, url)
    assert github.repo_adi(repo) is None


def test_gh_cagrisinda_bayrak_enjeksiyonu_yok():
    """`--repo` degeri hicbir bicimde `--` ile baslamamali, `--` ayiric var."""
    class _C:
        returncode = 0
        stdout = "[]"

    cagrilan: list[list[str]] = []

    def calistir(komut):
        cagrilan.append(list(komut))
        return _C()

    github.gh_secretlari("umut/atlas", calistir=calistir)
    assert cagrilan and "--" in cagrilan[0]
    deger = cagrilan[0][cagrilan[0].index("--repo") + 1]
    assert not deger.startswith("-")


# --------------------------------------------------------------------------
# workflow_secretlari
# --------------------------------------------------------------------------


def test_workflow_secretlari_toplar_ve_token_cikarir(tmp_path: Path):
    repo = repo_kur(tmp_path)
    workflow_yaz(
        repo,
        "ci.yml",
        "jobs:\n"
        "  a:\n"
        "    env:\n"
        "      A: ${{ secrets.OPENAI_API_KEY }}\n"
        "      B: ${{ secrets.SENTRY_DSN }}\n"
        "      C: ${{ secrets.GITHUB_TOKEN }}\n",
    )
    assert github.workflow_secretlari(repo) == {"OPENAI_API_KEY", "SENTRY_DSN"}


def test_workflow_secretlari_yoksa_bos_kume(tmp_path: Path):
    assert github.workflow_secretlari(repo_kur(tmp_path)) == set()


def test_workflow_secretlari_yaml_uzantisi(tmp_path: Path):
    repo = repo_kur(tmp_path)
    workflow_yaz(repo, "d.yaml", "env:\n  X: ${{ secrets.YAML_SIRI }}\n")
    assert github.workflow_secretlari(repo) == {"YAML_SIRI"}


def test_workflow_secretlari_isim_disi_butun_dosyalari_mez(tmp_path: Path):
    repo = repo_kur(tmp_path)
    workflow_yaz(repo, "not.md", "secrets.BULUNMAMALI\n")
    assert github.workflow_secretlari(repo) == set()


def test_workflow_secretlari_derin_yol_taranmaz(tmp_path: Path):
    """GitHub Actions workflow'lari ALT DIZINDE aramaz; yalniz ust duzey."""
    repo = repo_kur(tmp_path)
    workflow_yaz(repo, "alt/ic.yml", "env:\n  X: ${{ secrets.IC_DEGERI }}\n")
    assert github.workflow_secretlari(repo) == set()


def test_workflow_secretlari_gercek_repo_akisi(tmp_path: Path):
    """Uctan uca: workflow yaz -> adlari oku -> fark hesapla."""
    repo = repo_kur(tmp_path)
    origin_ekle(repo, "https://github.com/umut/atlas.git")
    workflow_yaz(repo, "ci.yml", "env:\n  K: ${{ secrets.CANLI_ANAHTAR }}\n")
    adlar = github.workflow_secretlari(repo)
    assert adlar == {"CANLI_ANAHTAR"}
    s = github.fark(repo, adlar, calistir=sahte_gh(adlar=[]))
    assert s["workflow_var_gh_yok"] == ["CANLI_ANAHTAR"]


# --------------------------------------------------------------------------
# gh_secretlari
# --------------------------------------------------------------------------


def test_gh_secretlari_ad_dondurur():
    cagirici = sahte_gh(adlar=["B_SIRI", "A_SIRI"])
    assert github.gh_secretlari("umut/atlas", calistir=cagirici) == {"B_SIRI", "A_SIRI"}


def test_gh_secretlari_komutu_dogru_kurulur():
    cagirici = sahte_gh(adlar=["X"])
    github.gh_secretlari("umut/atlas", calistir=cagirici)
    komut = cagirici.cagrilan[0]
    assert komut[:3] == ["gh", "secret", "list"]
    assert "--repo" in komut and "umut/atlas" in komut
    assert "name" in komut


def test_gh_secretlari_deger_istemez():
    """gh deger vermez: komutta `--json name` var, `--json value` YOK."""
    cagirici = sahte_gh(adlar=["X"])
    github.gh_secretlari("umut/atlas", calistir=cagirici)
    assert "value" not in cagirici.cagrilan[0]


def test_gh_secretlari_yoksa_none():
    assert github.gh_secretlari("umut/atlas", calistir=sahte_gh_yok()) is None


def sahte_gh_yok():
    def calistir(komut):
        raise github.GhYok("gh bulunamadi")

    return calistir


def test_gh_secretlari_yetki_hatasinda_hata_sinifi():
    with pytest.raises(github.GhHata):
        github.gh_secretlari("umut/atlas", calistir=sahte_gh(rc=1))


def test_gh_secretlari_bozuk_json_hata():
    with pytest.raises(github.GhHata):
        github.gh_secretlari("umut/atlas", calistir=sahte_gh(ham="{bozuk"))


def test_gh_secretlari_liste_degil_hata():
    with pytest.raises(github.GhHata):
        github.gh_secretlari("umut/atlas", calistir=sahte_gh(ham='{"name": "X"}'))


def test_gh_secretlari_bos_cikti_bos_kume():
    assert github.gh_secretlari("umut/atlas", calistir=sahte_gh(ham="[]")) == set()


# --------------------------------------------------------------------------
# fark
# --------------------------------------------------------------------------


def test_fark_tamam_tur(tmp_path: Path):
    repo = repo_kur(tmp_path)
    origin_ekle(repo, "git@github.com:umut/atlas.git")
    sonuc = github.fark(repo, {"A", "B"}, calistir=sahte_gh(adlar=["A", "B"]))
    assert sonuc["durum"] == "tamam"
    assert sonuc["workflow_var_gh_yok"] == []
    assert sonuc["gh_var_workflow_kullanmiyor"] == []


def test_fark_workflow_var_gh_yok(tmp_path: Path):
    repo = repo_kur(tmp_path)
    origin_ekle(repo, "https://github.com/umut/atlas.git")
    sonuc = github.fark(repo, {"A", "EKSIK"}, calistir=sahte_gh(adlar=["A"]))
    assert sonuc["durum"] == "tamam"
    assert sonuc["workflow_var_gh_yok"] == ["EKSIK"]


def test_fark_gh_var_workflow_kullanmiyor(tmp_path: Path):
    repo = repo_kur(tmp_path)
    origin_ekle(repo, "https://github.com/umut/atlas.git")
    sonuc = github.fark(repo, {"A"}, calistir=sahte_gh(adlar=["A", "Z"]))
    assert sonuc["gh_var_workflow_kullanmiyor"] == ["Z"]


def test_fark_yerel_ve_workflow_ayri_kumeler(tmp_path: Path):
    """Workflow kumesi ile yerel `.env` kumesi BAGIMSIZ hesaplanir."""
    repo = repo_kur(tmp_path)
    origin_ekle(repo, "https://github.com/umut/atlas.git")
    s = github.fark(repo, {"A", "EKSIK"}, calistir=sahte_gh(adlar=["A", "Z"]),
                    yerel_adlar={"Z", "YEREL"})
    assert s["workflow_var_gh_yok"] == ["EKSIK"]
    assert s["gh_var_workflow_kullanmiyor"] == ["Z"]
    assert s["yerel_var_gh_yok"] == ["YEREL"]
    assert s["gh_var_yerel_yok"] == ["A"]


def test_fark_yerel_verilmezse_yerel_kumeler_bos(tmp_path: Path):
    repo = repo_kur(tmp_path)
    origin_ekle(repo, "https://github.com/umut/atlas.git")
    s = github.fark(repo, {"A"}, calistir=sahte_gh(adlar=["Z"]))
    assert s["yerel_var_gh_yok"] == [] and s["gh_var_yerel_yok"] == []


def test_fark_listeleri_sirali(tmp_path: Path):
    repo = repo_kur(tmp_path)
    origin_ekle(repo, "https://github.com/umut/atlas.git")
    s = github.fark(repo, {"c", "a", "b"}, calistir=sahte_gh(adlar=[]))
    assert s["workflow_var_gh_yok"] == ["a", "b", "c"]  # deterministik


def test_fark_github_degil(tmp_path: Path):
    repo = repo_kur(tmp_path)
    origin_ekle(repo, "https://gitlab.com/umut/atlas.git")
    s = github.fark(repo, {"A"}, calistir=sahte_gh(adlar=["A"]))
    assert s["durum"] == "github-degil"
    assert s["workflow_var_gh_yok"] == []


def test_fark_gh_yok(tmp_path: Path):
    repo = repo_kur(tmp_path)
    origin_ekle(repo, "https://github.com/umut/atlas.git")
    s = github.fark(repo, {"A"}, calistir=sahte_gh_yok())
    assert s["durum"] == "gh-yok"
    assert s["workflow_var_gh_yok"] == []


def test_fark_gh_hatasi(tmp_path: Path):
    repo = repo_kur(tmp_path)
    origin_ekle(repo, "https://github.com/umut/atlas.git")
    s = github.fark(repo, {"A"}, calistir=sahte_gh(rc=1))
    assert s["durum"] == "hata"
    assert s["workflow_var_gh_yok"] == []


def test_fark_anahtarlar_her_zaman_var(tmp_path: Path):
    repo = repo_kur(tmp_path)
    origin_ekle(repo, "https://github.com/umut/atlas.git")
    bekle = {"workflow_var_gh_yok", "gh_var_workflow_kullanmiyor",
             "yerel_var_gh_yok", "gh_var_yerel_yok", "durum"}
    for cagirici in (sahte_gh(adlar=[]), sahte_gh(rc=1), sahte_gh_yok()):
        assert set(github.fark(repo, {"A"}, calistir=cagirici)) == bekle