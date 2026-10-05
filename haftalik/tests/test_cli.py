"""cli.py: --sadece-topla ciktisi, --cikti uzerine yazmaz, kullanim hatalari
(eksik/bilinmeyen arguman, --gun, mevcut dosya) -> cikis kodu."""

from __future__ import annotations

from conftest import git_kur, repo_gun_icin, run_cli, run_cli_yerel


class TestSadeceTopla:
    def test_ham_rapor_stdout_a(self, tmp_path):
        repo_gun_icin(tmp_path / "r", 1, 2)
        sonuc = run_cli("uret", "--kok", str(tmp_path), "--sadece-topla")
        assert sonuc.returncode == 0, sonuc.stderr
        assert "# Haftalık commit raporu" in sonuc.stdout
        assert "## r (2 commit," in sonuc.stdout
        assert "is 0" in sonuc.stdout and "is 1" in sonuc.stdout
        # LLM ciktisi degil: ozet basligi olmamali
        assert "Öne çıkanlar" not in sonuc.stdout

    def test_gun_penceresi_rapora_yazar(self, tmp_path):
        repo_gun_icin(tmp_path / "r", 1, 1)
        sonuc = run_cli("uret", "--kok", str(tmp_path), "--gun", "14", "--sadece-topla")
        assert sonuc.returncode == 0
        assert "son 14 gün" in sonuc.stdout

    def test_commit_olmayan_repo_bos_rapor(self, tmp_path):
        """Hata DEGIL: bos pencere de gecerli bir rapordur (cikis 0)."""
        git_kur(tmp_path / "bos")
        sonuc = run_cli("uret", "--kok", str(tmp_path), "--sadece-topla")
        assert sonuc.returncode == 0, sonuc.stderr
        assert "commit'i olan repo yok" in sonuc.stdout

    def test_cikti_dosyasina_yazar(self, tmp_path):
        repo_gun_icin(tmp_path / "r", 1, 1)
        cikti = tmp_path / "rapor.md"
        sonuc = run_cli(
            "uret", "--kok", str(tmp_path), "--sadece-topla", "--cikti", str(cikti)
        )
        assert sonuc.returncode == 0, sonuc.stderr
        assert "# Haftalık commit raporu" in cikti.read_text(encoding="utf-8")


class TestCiktiEzilmez:
    def test_mevcut_dosya_ezilmez_hata(self, tmp_path):
        repo_gun_icin(tmp_path / "r", 1, 1)
        cikti = tmp_path / "var.md"
        cikti.write_text("ELDE_MEVCUT\n", encoding="utf-8")

        sonuc = run_cli("uret", "--kok", str(tmp_path), "--sadece-topla",
                        "--cikti", str(cikti))

        assert sonuc.returncode == 2
        assert "Hata:" in sonuc.stderr
        assert "Traceback" not in sonuc.stderr
        # DOSYA BITEN HALIYLE KALIR
        assert cikti.read_text(encoding="utf-8") == "ELDE_MEVCUT\n"

    def test_ozet_uretirken_de_ezilmez(self, tmp_path, sahte_llm, telegram_yok):
        repo_gun_icin(tmp_path / "r", 1, 1)
        sahte_llm("SAHTE")
        cikti = tmp_path / "var.md"
        cikti.write_text("ELDE_MEVCUT\n", encoding="utf-8")

        sonuc = run_cli_yerel("uret", "--kok", str(tmp_path), "--cikti", str(cikti))

        assert sonuc.returncode == 2
        assert cikti.read_text(encoding="utf-8") == "ELDE_MEVCUT\n"


class TestKullanimHatasi:
    def test_bilinmeyen_komut(self):
        sonuc = run_cli("olmayan")
        assert sonuc.returncode == 2

    def test_komut_verilmemis(self):
        sonuc = run_cli()
        assert sonuc.returncode == 2

    def test_bilinmeyen_bayrak(self):
        sonuc = run_cli("uret", "--kok", ".", "--olmayan")
        assert sonuc.returncode == 2

    def test_kok_verilmemis(self):
        sonuc = run_cli("uret", "--sadece-topla")
        assert sonuc.returncode == 2

    def test_gun_sifir(self, tmp_path):
        repo_gun_icin(tmp_path / "r", 1, 1)
        sonuc = run_cli("uret", "--kok", str(tmp_path), "--gun", "0", "--sadece-topla")
        assert sonuc.returncode == 2
        assert "Hata:" in sonuc.stderr
        assert "Traceback" not in sonuc.stderr

    def test_gun_sayi_degil(self, tmp_path):
        sonuc = run_cli("uret", "--kok", str(tmp_path), "--gun", "abc")
        assert sonuc.returncode == 2

    def test_kok_yok(self, tmp_path):
        sonuc = run_cli("uret", "--kok", str(tmp_path / "yok"), "--sadece-topla")
        assert sonuc.returncode == 2
        assert "Hata:" in sonuc.stderr
        assert "Traceback" not in sonuc.stderr

    def test_yardim_cikis_bir(self):
        """--help sifirdan farkli kod dondurmez (0)."""
        assert run_cli("uret", "--help").returncode == 0


class TestSifirdanCalistirma:
    def test_yardim_gunceller(self):
        """`--help` metni Turkce ve komutlari listeler."""
        sonuc = run_cli("--help")
        assert sonuc.returncode == 0
        assert "uret" in sonuc.stdout

    def test_uret_hedefi_var(self):
        assert "uret" in run_cli("uret", "--help").stdout