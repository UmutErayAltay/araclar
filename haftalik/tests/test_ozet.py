"""ozet.py: istem kurma, 12000 karakter kisaltma, sahte LLM ile ozet uretme,
LLM hatasinda cikis kodu."""

from __future__ import annotations

from conftest import commit_yap, git_kur, repo_gun_icin, run_cli_yerel

from haftalik.llm import LLMError
from haftalik.ozet import (
    MAKS_REPO_COMMIT,
    MAKS_VERI_KARAKTER,
    ham_markdown,
    ozeti_temizle,
    prompt_olustur,
)
from haftalik.topla import Commit, RepoOzeti

ARALIK = "2026-09-28..2026-10-05"


def _repo(ad: str, adet: int, *, konu_onek: str = "is", uzun: int = 0) -> RepoOzeti:
    """Testte kullanmak icin bellekte bir RepoOzeti kurar (git CALISMAZ).

    Commit'ler `git log` ciktisi gibi EN YENI ONCE siralanir: `topla` boyle
    dondurur ve `ozet.py` kirpmada ilk N'yi (yani en yeniyi) tutar.
    """
    commitler = [
        Commit(
            kisa=f"{i:06x}",
            yazar="Test",
            tarih="2026-10-01",
            konu=f"{konu_onek} {i}" + (" " + "x" * uzun if uzun else ""),
        )
        for i in range(adet - 1, -1, -1)
    ]
    return RepoOzeti(
        yol=None,  # type: ignore[arg-type]  # yol yalniz tanimlama icin; burada okunmaz
        ad=ad,
        commitler=commitler,
        eklenen=adet,
        silinen=0,
    )


class TestPrompt:
    def test_sozlesme_ogeleri_yerinde(self):
        istem = prompt_olustur([_repo("haftalik", 3)], ARALIK)
        assert "Haftalık özet" in istem
        assert ARALIK in istem
        assert "Öne çıkanlar" in istem
        assert "UYDURMA" in istem
        # veri icinde commit konulari da geciyor
        assert "is 0" in istem and "is 1" in istem and "is 2" in istem

    def test_veri_isaretleri_arasinda(self):
        istem = prompt_olustur([_repo("haftalik", 2)], ARALIK)
        bas = istem.index("<<<COMMITLER")
        bit = istem.index("COMMITLER>>>")
        assert bas < bit
        assert "## haftalik" in istem[bas:bit]

    def test_kisa_veride_kisaltma_yok(self):
        istem = prompt_olustur([_repo("haftalik", 5)], ARALIK)
        assert "KISALTILDI" not in istem
        assert len(istem) < MAKS_VERI_KARAKTER

    def test_kisaltma_olunca_not_dusar(self):
        """12000 karakteri asan veri kirpilir ve kisaltma istemde BELIRTILIR."""
        ozetler = [_repo(f"r{i}", 200, uzun=40) for i in range(4)]
        istem = prompt_olustur(ozetler, ARALIK)
        govde = istem.split("<<<COMMITLER", 1)[1]
        assert len(govde) <= MAKS_VERI_KARAKTER
        assert "KISALTILDI" in istem

    def test_kisaltmada_en_yeni_commitler_kalir(self):
        """Kirpma en yeni commit'leri BIRAKIR; eskiler dusurulur."""
        ozetler = [_repo("r", 400, uzun=40)]
        istem = prompt_olustur(ozetler, ARALIK)
        govde = istem.split("<<<COMMITLER", 1)[1]
        assert "is 399" in govde  # en yeni
        assert "is 0" not in govde    # en eski

    def test_limit_tek_repo_commit_sinirinda(self):
        ozetler = [_repo("r", 100, uzun=100)]
        istem = prompt_olustur(ozetler, ARALIK)
        govde = istem.split("<<<COMMITLER", 1)[1]
        # 40'tan az gorunen commit olabilir ama hicbiri 40'tan fazla degil
        assert govde.count("\n- 2026-10-01") <= MAKS_REPO_COMMIT

    def test_bos_ozetler_prompt_uretebilir(self):
        istem = prompt_olustur([], ARALIK)
        assert "Haftalık özet" in istem


class TestHamMarkdown:
    def test_icerik(self):
        metin = ham_markdown([_repo("haftalik", 2)], ARALIK, 7)
        assert metin.startswith("# Haftalık commit raporu")
        assert ARALIK in metin
        assert "## haftalik (2 commit, +2/-0)" in metin
        assert "is 0" in metin

    def test_bos_pencere_mesaji(self):
        metin = ham_markdown([], ARALIK, 7)
        assert "commit'i olan repo yok" in metin


class TestOzetiTemizle:
    def test_baslik_varsa_dokunulmaz(self):
        yanit = "# Haftalık özet (2026-09-28..2026-10-05)\n\ngövde"
        assert ozeti_temizle(yanit, ARALIK) == yanit

    def test_baslik_yoksa_tamamlanir(self):
        sonuc = ozeti_temizle("sadece gövde", ARALIK)
        assert sonuc.startswith("# Haftalık özet")
        assert ARALIK in sonuc.splitlines()[0]
        assert "sadece gövde" in sonuc

    def test_bos_yanit_bos_doner(self):
        assert ozeti_temizle("   ", ARALIK) == ""


class TestUctanUca:
    """Sahte LLM ile gercek toplama + ozet (gercek ag YOK)."""

    def test_ozet_uretilir_ve_yazilir(self, tmp_path, sahte_llm, telegram_yok):
        repo_gun_icin(tmp_path / "r", 1, 2)
        istemci = sahte_llm("SAHTE CEVAP")
        cikti = tmp_path / "ozet.md"

        sonuc = run_cli_yerel("uret", "--kok", str(tmp_path), "--cikti", str(cikti))

        assert sonuc.returncode == 0, sonuc.stderr
        assert len(istemci.istemler) == 1
        assert "is 0" in istemci.istemler[0]
        # Model basligi atlamis olsa bile teslim sozlesmesindeki baslik tamamlanir.
        yazilan = cikti.read_text(encoding="utf-8").strip()
        assert yazilan.startswith("# Haftalık özet")
        assert yazilan.endswith("SAHTE CEVAP")

    def test_ozet_stdout_a_basilir(self, tmp_path, sahte_llm, telegram_yok):
        repo_gun_icin(tmp_path / "r", 1, 1)
        sahte_llm("SAHTE CEVAP")

        sonuc = run_cli_yerel("uret", "--kok", str(tmp_path))

        assert sonuc.returncode == 0, sonuc.stderr
        assert "SAHTE CEVAP" in sonuc.stdout

    def test_sadece_topla_llm_e_gitmez(self, tmp_path, sahte_llm):
        repo_gun_icin(tmp_path / "r", 1, 1)
        istemci = sahte_llm("KULLANILMAMALI")

        sonuc = run_cli_yerel("uret", "--kok", str(tmp_path), "--sadece-topla")

        assert sonuc.returncode == 0, sonuc.stderr
        assert istemci.istemler == []
        assert "KULLANILMAMALI" not in sonuc.stdout
        assert "# Haftalık commit raporu" in sonuc.stdout
        assert "is 0" in sonuc.stdout

    def test_commit_olan_repo_yoksa_hata(self, tmp_path, sahte_llm, telegram_yok):
        """Commit'i olmayan repo varsa LLM HIC cagrilmaz."""
        git_kur(tmp_path / "bos")
        istemci = sahte_llm("KULLANILMAMALI")

        sonuc = run_cli_yerel("uret", "--kok", str(tmp_path))

        assert sonuc.returncode == 1
        assert "Hata:" in sonuc.stderr
        assert istemci.istemler == []

    def test_bos_ozet_hata(self, tmp_path, sahte_llm, telegram_yok):
        repo_gun_icin(tmp_path / "r", 1, 1)
        sahte_llm("   ")

        sonuc = run_cli_yerel("uret", "--kok", str(tmp_path))

        assert sonuc.returncode == 1
        assert "boş özet" in sonuc.stderr


class TestLLMHatasi:
    def test_cor_kapali_cikis_bir(self, tmp_path, sahte_llm, telegram_yok):
        repo_gun_icin(tmp_path / "r", 1, 1)
        sahte_llm(LLMError("cor proxy'ye (http://127.0.0.1:8787) bağlanılamadı"))

        sonuc = run_cli_yerel("uret", "--kok", str(tmp_path))

        assert sonuc.returncode == 1
        assert "cor proxy'sine bağlanılamadı (cor start)" in sonuc.stderr
        assert "Traceback" not in sonuc.stderr

    def test_cor_kapali_ham_dosya_yazmaz(self, tmp_path, sahte_llm, telegram_yok):
        """LLM hatasi: --cikti verilse bile HICbir dosya olusmaz."""
        repo_gun_icin(tmp_path / "r", 1, 1)
        sahte_llm(LLMError("cor proxy'ye bağlanılamadı"))
        cikti = tmp_path / "yok.md"

        sonuc = run_cli_yerel("uret", "--kok", str(tmp_path), "--cikti", str(cikti))

        assert sonuc.returncode == 1
        assert not cikti.exists()
        assert not (tmp_path / "ham.md").exists()
        assert list(tmp_path.glob("*.md")) == []

    def test_sadece_topla_cor_kapaliyken_calisir(self, tmp_path, telegram_yok):
        """--sadece-topla LLM'e gitmez: cor olmasa da calisir."""
        repo_gun_icin(tmp_path / "r", 1, 1)

        sonuc = run_cli_yerel("uret", "--kok", str(tmp_path), "--sadece-topla")

        assert sonuc.returncode == 0, sonuc.stderr
        assert "is 0" in sonuc.stdout


class TestTarihAraligiKullanimi:
    def test_gercek_pencere_etiki(self, tmp_path, sahte_llm, telegram_yok):
        repo = git_kur(tmp_path / "r")
        commit_yap(repo, "yeni.txt", "y\n", gun_once=1, mesaj="yeni")
        commit_yap(repo, "eski.txt", "e\n", gun_once=60, mesaj="eski")
        istemci = sahte_llm("SAHTE")

        assert run_cli_yerel("uret", "--kok", str(tmp_path), "--gun", "7").returncode == 0
        assert "yeni" in istemci.istemler[0]
        assert "eski" not in istemci.istemler[0]