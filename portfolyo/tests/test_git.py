"""git modülü testleri."""

from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from portfolyo.git import RepoVerisi, repo_verisi


def _git_init(repo: Path) -> None:
    """Geçici repoyu başlat."""
    subprocess.run(
        ["git", "init", "-q"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "t@t.invalid"],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _git_commit(repo: Path, mesaj: str, tarih: str | None = None) -> None:
    """Boş commit oluştur (tarih opsiyonel)."""
    env = os.environ.copy()
    if tarih:
        if "T" not in tarih:  # git yalnızca tam ISO zamanını kabul eder ("2026-01-10" geçersiz)
            tarih += "T12:00:00"
        if "+" not in tarih:
            tarih += "+0000"
        env["GIT_AUTHOR_DATE"] = tarih
        env["GIT_COMMITTER_DATE"] = tarih
    # --allow-empty-message -m x ile boş commit
    subprocess.run(
        # Kimlik ve imza ayarı komutla verilir: geliştirici makinesindeki global
        # `commit.gpgsign=true` testi kırmasın.
        ["git", "-c", "commit.gpgsign=false", "-c", "user.name=t",
         "-c", "user.email=t@t.invalid", "commit", "--allow-empty", "-m", mesaj],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )


def _git_commit_dosya(repo: Path, dosya: str, icerik: str, mesaj: str, tarih: str | None = None) -> None:
    """Dosya ekleyip commit et."""
    (repo / dosya).write_text(icerik)
    subprocess.run(
        ["git", "add", dosya], cwd=repo, check=True, capture_output=True
    )
    _git_commit(repo, mesaj, tarih)


class TestRepoVerisi:
    """repo_verisi fonksiyonu testleri."""

    def test_git_olmayan_dizin_none(self, tmp_path: Path):
        """Git deposu olmayan dizin -> None."""
        sonuc = repo_verisi(tmp_path, date.today())
        assert sonuc is None

    def test_bos_repo(self, tmp_path: Path):
        """Boş repo (commit yok) -> commit_sayisi=0, tarihler None, haftalık 12 sıfır."""
        _git_init(tmp_path)
        bugun = date(2026, 1, 15)
        sonuc = repo_verisi(tmp_path, bugun)
        assert sonuc is not None
        assert sonuc.commit_sayisi == 0
        assert sonuc.ilk_commit is None
        assert sonuc.son_commit is None
        assert sonuc.haftalik == (0,) * 12
        assert sonuc.diller == ()
        assert sonuc.readme_ozeti is None

    def test_tek_commit(self, tmp_path: Path):
        """Tek commit'li repo."""
        _git_init(tmp_path)
        _git_commit(tmp_path, "ilk", "2026-01-10")
        bugun = date(2026, 1, 15)
        sonuc = repo_verisi(tmp_path, bugun)
        assert sonuc is not None
        assert sonuc.commit_sayisi == 1
        assert sonuc.ilk_commit == "2026-01-10"
        assert sonuc.son_commit == "2026-01-10"
        # Son 12 hafta: sadece 1 commit, 2. haftada (bugun 15 Ocak, 10 Ocak 2. haftada)
        assert sum(sonuc.haftalik) == 1

    def test_coklu_commit_sirali_tarihler(self, tmp_path: Path):
        """Birden fazla commit, tarihler ISO formatında."""
        _git_init(tmp_path)
        _git_commit(tmp_path, "c1", "2026-01-01")
        _git_commit(tmp_path, "c2", "2026-01-05")
        _git_commit(tmp_path, "c3", "2026-01-10")
        bugun = date(2026, 1, 15)
        sonuc = repo_verisi(tmp_path, bugun)
        assert sonuc.commit_sayisi == 3
        assert sonuc.ilk_commit == "2026-01-01"
        assert sonuc.son_commit == "2026-01-10"

    def test_haftalik_pencereler_en_eski_basta(self, tmp_path: Path):
        """Haftalık pencereler EN ESKİ baştan başlar (12 eleman)."""
        _git_init(tmp_path)
        # 12 hafta geriye: her haftaya 1 commit
        bugun = date(2026, 3, 29)  # Pazar
        for i in range(12):
            commit_tarih = bugun - timedelta(days=i * 7 + 3)  # Hafta ortası
            _git_commit(tmp_path, f"c{i}", commit_tarih.isoformat())
        sonuc = repo_verisi(tmp_path, bugun)
        assert sonuc is not None
        assert len(sonuc.haftalik) == 12
        # Her haftada 1 commit olmalı (EN ESKİ baştan)
        assert all(v == 1 for v in sonuc.haftalik)

    def test_haftalik_pencere_bugun_dahil(self, tmp_path: Path):
        """Bugünün olduğu hafta pencere son elemanı (index 11)."""
        _git_init(tmp_path)
        bugun = date(2026, 1, 15)  # Perşembe
        # Bu hafta (Pazartesi 13 - Pazar 19) - bugün Perşembe 15
        _git_commit(tmp_path, "bu_hafta", "2026-01-14")
        # Geçen hafta
        _git_commit(tmp_path, "gecen_hafta", "2026-01-07")
        sonuc = repo_verisi(tmp_path, bugun)
        assert sonuc is not None
        # Index 11 = bu hafta (son eleman)
        assert sonuc.haftalik[11] == 1
        # Index 10 = geçen hafta
        assert sonuc.haftalik[10] == 1
        # Diğerleri 0
        assert sum(sonuc.haftalik[:10]) == 0

    def test_diller_dosya_sayisina_gore(self, tmp_path: Path):
        """Diller dosya sayısına göre çoktan aza, eşitlikte ada göre."""
        _git_init(tmp_path)
        # 3 Python, 2 TypeScript, 1 JavaScript, 1 Go, 1 Rust, 1 HTML, 1 CSS
        _git_commit_dosya(tmp_path, "a.py", "x", "c1")
        _git_commit_dosya(tmp_path, "b.py", "x", "c2")
        _git_commit_dosya(tmp_path, "c.py", "x", "c3")
        _git_commit_dosya(tmp_path, "d.ts", "x", "c4")
        _git_commit_dosya(tmp_path, "e.tsx", "x", "c5")
        _git_commit_dosya(tmp_path, "f.js", "x", "c6")
        _git_commit_dosya(tmp_path, "g.go", "x", "c7")
        _git_commit_dosya(tmp_path, "h.rs", "x", "c8")
        _git_commit_dosya(tmp_path, "i.html", "x", "c9")
        _git_commit_dosya(tmp_path, "j.css", "x", "c10")
        bugun = date.today()
        sonuc = repo_verisi(tmp_path, bugun)
        assert sonuc is not None
        # En çok 5 dil, çoktan aza
        assert len(sonuc.diller) == 5
        assert sonuc.diller[0] == ("Python", 3)
        assert sonuc.diller[1] == ("TypeScript", 2)
        # JavaScript, Go, Rust, HTML, CSS -> 1'er tane, ada göre
        kalan = [d for d, _ in sonuc.diller[2:]]
        assert set(kalan) == {"CSS", "Go", "HTML"}  # 1'er dosya: ada göre ilk üçü (JavaScript, Rust dışarıda)

    def test_diller_en_cok_5(self, tmp_path: Path):
        """En çok 5 dil döner."""
        _git_init(tmp_path)
        for i, ext in enumerate([".py", ".ts", ".js", ".go", ".rs", ".kt"]):
            _git_commit_dosya(tmp_path, f"f{i}{ext}", "x", f"c{i}")
        bugun = date.today()
        sonuc = repo_verisi(tmp_path, bugun)
        assert len(sonuc.diller) == 5

    def test_dil_esitlikte_ada_gore(self, tmp_path: Path):
        """Dosya sayısı eşitse ada göre sıralama."""
        _git_init(tmp_path)
        _git_commit_dosya(tmp_path, "z.py", "x", "c1")
        _git_commit_dosya(tmp_path, "a.rs", "x", "c2")
        _git_commit_dosya(tmp_path, "m.go", "x", "c3")
        bugun = date.today()
        sonuc = repo_verisi(tmp_path, bugun)
        # Hepsi 1'er, ada göre: Go, Python, Rust
        assert sonuc.diller == (("Go", 1), ("Python", 1), ("Rust", 1))

    def test_readme_false_iken_okunmaz(self, tmp_path: Path):
        """readme=False iken README.md HIÇ okunmaz."""
        _git_init(tmp_path)
        # README'ye benzersiz işaret koy
        readme_yol = tmp_path / "README.md"
        readme_yol.write_text("BENZERSIZ_ISMET_12345_OKUNMAMALI")
        _git_commit(tmp_path, "c1")
        bugun = date.today()
        sonuc = repo_verisi(tmp_path, bugun, readme=False)
        assert sonuc is not None
        assert sonuc.readme_ozeti is None

    def test_readme_true_kok_readme_md(self, tmp_path: Path):
        """readme=True: yalnız kök README.md okunur."""
        _git_init(tmp_path)
        (tmp_path / "README.md").write_text("# Başlık\n\nBu proje, anlamlı bir ilk paragrafın nasıl çıkarıldığını gösterir.")
        _git_commit(tmp_path, "c1")
        bugun = date.today()
        sonuc = repo_verisi(tmp_path, bugun, readme=True)
        assert sonuc is not None
        assert sonuc.readme_ozeti == "Bu proje, anlamlı bir ilk paragrafın nasıl çıkarıldığını gösterir."

    def test_readme_symlink_atlanır(self, tmp_path: Path):
        """README.md symlink ise atlanır."""
        _git_init(tmp_path)
        hedef = tmp_path / "HEDEF.md"
        hedef.write_text("Hedef içerik")
        (tmp_path / "README.md").symlink_to(hedef)
        _git_commit(tmp_path, "c1")
        bugun = date.today()
        sonuc = repo_verisi(tmp_path, bugun, readme=True)
        assert sonuc.readme_ozeti is None

    def test_readme_buyuk_dosya_atlanır(self, tmp_path: Path):
        """README.md ≥200KB ise atlanır."""
        _git_init(tmp_path)
        buyuk = "x" * (200 * 1024)
        (tmp_path / "README.md").write_text(buyuk)
        _git_commit(tmp_path, "c1")
        bugun = date.today()
        sonuc = repo_verisi(tmp_path, bugun, readme=True)
        assert sonuc.readme_ozeti is None

    def test_readme_ozet_kurallari(self, tmp_path: Path):
        """README özetleme kuralları: başlık/rozet/HTML/kod bloğu atlanır, linkler metin olur."""
        _git_init(tmp_path)
        icerik = """# Başlık

![Rozet](https://img.shields.io/badge/x-y)

<center>HTML atlanmalı</center>

```python
kod = "blok atlanmalı"
```

Anlamlı [paragraf](https://ornek.com) burada ve yeterince uzun bir cümle.

Diğer satır."""
        (tmp_path / "README.md").write_text(icerik)
        _git_commit(tmp_path, "c1")
        bugun = date.today()
        sonuc = repo_verisi(tmp_path, bugun, readme=True)
        assert sonuc is not None
        # "paragraf burada Diğer satır" -> link metin oldu, boşluklar tek
        assert "paragraf burada" in sonuc.readme_ozeti
        assert "Diğer satır" not in sonuc.readme_ozeti  # yalnız İLK paragraf
        assert "Başlık" not in sonuc.readme_ozeti
        assert "Rozet" not in sonuc.readme_ozeti
        assert "HTML" not in sonuc.readme_ozeti
        assert "kod" not in sonuc.readme_ozeti

    def test_readme_ozet_240_karakter_kesme(self, tmp_path: Path):
        """240 karakterde '…' ile kes."""
        _git_init(tmp_path)
        uzun = "a " * 200  # ~400 karakter
        (tmp_path / "README.md").write_text(uzun)
        _git_commit(tmp_path, "c1")
        bugun = date.today()
        sonuc = repo_verisi(tmp_path, bugun, readme=True)
        assert sonuc is not None
        assert len(sonuc.readme_ozeti) == 240
        assert sonuc.readme_ozeti.endswith("…")

    def test_readme_bos_veya_sadece_atlananlar_none(self, tmp_path: Path):
        """README sadece başlık/rozet/kod bloğundan oluşursa None."""
        _git_init(tmp_path)
        icerik = """# Başlık

![Rozet](url)

```kod```
"""
        (tmp_path / "README.md").write_text(icerik)
        _git_commit(tmp_path, "c1")
        bugun = date.today()
        sonuc = repo_verisi(tmp_path, bugun, readme=True)
        assert sonuc.readme_ozeti is None

    def test_hata_durumunda_none_raise_yok(self, tmp_path: Path):
        """Git hatası (ör. bozuk repo) -> None, raise etmez."""
        _git_init(tmp_path)
        # .git'i boz: HEAD geçersizse git "geçerli bir depo değil" der (config bozukluğu
        # git için ölümcül değildir, boş repo gibi davranır)
        (tmp_path / ".git" / "HEAD").write_text("bozuk")
        bugun = date.today()
        sonuc = repo_verisi(tmp_path, bugun)
        assert sonuc is None


class TestGitKomutEnv:
    """GIT_AUTHOR_DATE / GIT_COMMITTER_DATE env testi."""

    def test_commit_tarihi_env_ile_verilir(self, tmp_path: Path):
        """Commit tarihi env değişkenleriyle verilebiliyor mu?"""
        _git_init(tmp_path)
        _git_commit_dosya(tmp_path, "a.py", "x", "c1", "2025-06-15T12:00:00")
        bugun = date(2026, 1, 1)
        sonuc = repo_verisi(tmp_path, bugun)
        assert sonuc is not None
        assert sonuc.ilk_commit == "2025-06-15"

class TestReadmeOzetKalite:
    def test_kisa_paragraf_dil_secici_atlanir_vurgu_temizlenir(self, tmp_path: Path):
        _git_init(tmp_path)
        (tmp_path / "README.md").write_text(
            "# Proje\n\n[English](README.en.md) · *Türkçe*\n\n"
            "> **Bu araç**, `yerel` bir proxy olarak çalışır ve verileri makineden çıkarmaz.\n"
        )
        _git_commit(tmp_path, "c1")
        sonuc = repo_verisi(tmp_path, date.today(), readme=True)
        assert sonuc is not None
        assert sonuc.readme_ozeti == "Bu araç, yerel bir proxy olarak çalışır ve verileri makineden çıkarmaz."
