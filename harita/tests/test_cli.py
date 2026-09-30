"""CLI ve salt-okunurluk testleri (subprocess ile gerçek çalıştırma)."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import KOK, vault_hashleri

from harita.index import baglan


def calistir(*argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "harita", *argv],
        cwd=str(cwd or KOK),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONPATH": str(KOK), "PYTHONIOENCODING": "utf-8"},
        timeout=120,
    )


def test_indeksle_ozet_basar(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "cli.db"
    sonuc = calistir("indeksle", str(mini_vault), "--db", str(db))
    assert sonuc.returncode == 0, sonuc.stderr
    assert "Not:" in sonuc.stdout
    assert "Kırık link:" in sonuc.stdout
    assert "Etiket:" in sonuc.stdout
    assert "Süzülen gizli satır:" in sonuc.stdout


def test_db_bayragi_iki_konumda_da_calisir(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "cli.db"
    assert calistir("indeksle", str(mini_vault), "--db", str(db)).returncode == 0
    assert calistir("--db", str(db), "kirik").returncode == 0
    assert calistir("kirik", "--db", str(db)).returncode == 0


def test_harita_db_ortam_degiskeni_kullanilir(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "env.db"
    sonuc = subprocess.run(
        [sys.executable, "-m", "harita", "indeksle", str(mini_vault)],
        cwd=str(KOK),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONPATH": str(KOK), "HARITA_DB": str(db), "PYTHONIOENCODING": "utf-8"},
        timeout=120,
    )
    assert sonuc.returncode == 0, sonuc.stderr
    assert db.exists()


def test_kirik_alt_komutu(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "cli.db"
    calistir("indeksle", str(mini_vault), "--db", str(db))
    sonuc = calistir("kirik", "--db", str(db))
    assert sonuc.returncode == 0
    assert "Kırık link:" in sonuc.stdout
    assert "bilinmeyen-not" in sonuc.stdout
    # Çıktı biçimi: kaynak yol (başlık) → [[hedef]]
    assert "🧠 Bilgi/ızgara-notu.md (Izgara Ağı Hakkında) → [[bilinmeyen-not]]" in sonuc.stdout


def test_kirik_gomulu_hedef_tur_kaydini_gostermez(mini_vault: Path, tmp_path: Path) -> None:
    """Gömülü olmayan bir kırık link türü 'link' olarak saklanır."""
    db = tmp_path / "cli.db"
    calistir("indeksle", str(mini_vault), "--db", str(db))
    b = baglan(db)
    try:
        tur = b.execute(
            "SELECT tur FROM links WHERE hedef_metin = 'bilinmeyen-not'"
        ).fetchone()
        assert tur[0] == "link"
    finally:
        b.close()


def test_kirik_ilk_n_siniri(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "cli.db"
    calistir("indeksle", str(mini_vault), "--db", str(db))
    hepsi = calistir("kirik", "--db", str(db)).stdout
    ilk_bir = calistir("kirik", "--db", str(db), "--ilk", "1").stdout
    assert "tane daha" in ilk_bir
    assert ilk_bir.count("→") == 1


def test_yetim_alt_komutu(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "cli.db"
    calistir("indeksle", str(mini_vault), "--db", str(db))
    sonuc = calistir("yetim", "--db", str(db))
    assert sonuc.returncode == 0
    assert "Yetim not:" in sonuc.stdout
    # Alt klasördeki bağlantısız not GERÇEK yetimdir.
    assert "📁 Klasör/ayrilmis-not.md" in sonuc.stdout
    # Dalga B.1 kararı Q2: kökteki tek-bileşenli HER `.md` "yok sayılabilir"dır,
    # sabit isim listesi kalktı — `gizlilik-sırları.md` artık varsayılan
    # çıktının DIŞINDA, yalnız `--tumu` ile görünür.
    assert "gizlilik-sırları.md" not in sonuc.stdout
    assert "yok sayılabilir" in sonuc.stdout
    tumu = calistir("yetim", "--tumu", "--db", str(db))
    assert "gizlilik-sırları.md" in tumu.stdout


def test_etiketler_alt_komutu_ilk_n(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "cli.db"
    calistir("indeksle", str(mini_vault), "--db", str(db))
    sonuc = calistir("etiketler", "--db", str(db), "--ilk", "3")
    assert sonuc.returncode == 0
    assert len([g for g in sonuc.stdout.splitlines() if g.strip().startswith("#")]) <= 3
    assert "#" in sonuc.stdout


def test_etiketler_hepsi_sikliga_gore(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "cli.db"
    calistir("indeksle", str(mini_vault), "--db", str(db))
    satirlar = [g for g in calistir("etiketler", "--db", str(db)).stdout.splitlines() if g.strip()]
    adetler = [int(s.split()[0]) for s in satirlar]
    assert adetler == sorted(adetler, reverse=True)


def test_bos_vault_ve_bos_ciktilar(tmp_path: Path) -> None:
    vault = tmp_path / "bos"
    vault.mkdir()
    db = tmp_path / "bos.db"
    assert calistir("indeksle", str(vault), "--db", str(db)).returncode == 0
    assert "Kırık link yok." in calistir("kirik", "--db", str(db)).stdout
    # Dalga B: varsayılan yalnız GERÇEK yetimleri sorar; `--tumu` hepsini.
    assert "Yetim not yok." in calistir("yetim", "--db", str(db)).stdout
    assert "Yetim not yok." in calistir("yetim", "--tumu", "--db", str(db)).stdout
    assert "Etiket yok." in calistir("etiketler", "--db", str(db)).stdout


def test_olmayan_vault_hata_dondurur(tmp_path: Path) -> None:
    sonuc = calistir("indeksle", str(tmp_path / "yok"), "--db", str(tmp_path / "x.db"))
    assert sonuc.returncode == 2
    assert "vault bulunamadı" in sonuc.stderr


def test_olmayan_db_hata_dondurur(tmp_path: Path) -> None:
    sonuc = calistir("kirik", "--db", str(tmp_path / "yok.db"))
    assert sonuc.returncode != 0
    assert "İndeks bulunamadı" in sonuc.stderr


def test_turkce_cikti_kodlama_bozulmaz(mini_vault: Path, tmp_path: Path) -> None:
    """Windows cp1252 konsolunda çöken Türkçe karakterler burada bozulmamalı."""
    db = tmp_path / "cli.db"
    calistir("indeksle", str(mini_vault), "--db", str(db))
    sonuc = calistir("yetim", "--db", str(db))
    assert "Yetim not" in sonuc.stdout
    assert "�" not in sonuc.stdout


def test_versiyon_bayragi() -> None:
    sonuc = calistir("--versiyon")
    assert sonuc.returncode == 0
    assert "harita" in sonuc.stdout


def test_alt_komut_zorunlu() -> None:
    assert calistir().returncode != 0


# ---------------------------------------------------------------------------
# Salt-okunurluk kanıtı
# ---------------------------------------------------------------------------


def test_indeksleme_vaultu_degistirmez(mini_vault: Path, tmp_path: Path) -> None:
    """İndeksleme öncesi/sonrası tüm vault dosyalarının SHA256'sı aynı olmalı."""
    once = vault_hashleri(mini_vault)
    assert once, "fixture boş görünüyor"

    db = tmp_path / "ro.db"
    calistir("indeksle", str(mini_vault), "--db", str(db))
    sonra = vault_hashleri(mini_vault)
    assert once == sonra

    # İndeks DB'si vault dışında olmalı ve vault'a hiçbir dosya eklenmemeli.
    assert not (mini_vault / "ro.db").exists()
    assert set(once) == set(sonra)


def test_sorgular_vaultu_degistirmez(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "ro2.db"
    calistir("indeksle", str(mini_vault), "--db", str(db))
    once = vault_hashleri(mini_vault)
    for komut in ("kirik", "yetim", "etiketler"):
        assert calistir(komut, "--db", str(db)).returncode == 0
    assert once == vault_hashleri(mini_vault)


def test_ayristirma_yalnizca_okuma_modunda(mini_vault: Path) -> None:
    """open() çağrılarında yazma modu kullanılmamalı (kaynak düzeyi kontrol)."""
    kaynak = (KOK / "harita" / "parse.py").read_text(encoding="utf-8")
    assert '"w"' not in kaynak
    assert '"w+"' not in kaynak
    assert '"a"' not in kaynak
    assert ".write_text" not in kaynak
    assert ".write_bytes" not in kaynak
    assert 'open(' not in kaynak  # yalnızca Path.read_bytes


def test_hicbir_modulde_vault_yazma_yolu_yok() -> None:
    """Tüm modüllerde yazma çağrısı aranmaz (indeks DB'si hariç konu dışı).

    Dalga C `harita ozet --yaz DOSYA` ekledi: bu komut kullanıcının ADI
    girdiği bir dosyaya yazar. Bu YAZMA yolunun vault'a ULAŞAMADIĞI
    ayrıca kanıtlanır (aşağıdaki testler); bu yüzden `cli.py`'deki tek
    yazma çağrısı, vault içi yolları REDDEDEN yardımcının İÇİNDEDİR.
    """
    for ad in ("parse.py", "index.py", "ozet.py", "tutarlilik.py"):
        kaynak = (KOK / "harita" / ad).read_text(encoding="utf-8")
        assert ".write_text" not in kaynak, ad
        assert ".write_bytes" not in kaynak, ad
        assert "os.remove" not in kaynak, ad
        assert "shutil" not in kaynak, ad

    # cli.py: yalnız `_ozet_dosyaya_yaz` içinde yazma olmalı, o da vault
    # içi yolu reddeden bir yardımcıdır.
    cli = (KOK / "harita" / "cli.py").read_text(encoding="utf-8")
    yazan = [i for i, satir in enumerate(cli.split("\n")) if ".write_text" in satir]
    assert len(yazan) == 1, f"cli.py'de {len(yazan)} yazma çağrısı (1 olmalı)"
    # Bu çağrı, vault kontrolünden geçen yardımcının içinde olmalı.
    govde = cli.split("def _ozet_dosyaya_yaz")[1].split("\ndef ")[0]
    assert ".write_text" in govde, "yazma `_ozet_dosyaya_yaz` içinde olmalı"
    assert "kok in hedef.parents" in govde, "vault içi yol REDDEDİLMELİ"
    assert "os.remove" not in cli and "shutil" not in cli, ad


def test_dosya_izinleri_degismiyor(mini_vault: Path, tmp_path: Path) -> None:
    once = {p.relative_to(mini_vault).as_posix(): p.stat().st_mode for p in mini_vault.rglob("*") if p.is_file()}
    calistir("indeksle", str(mini_vault), "--db", str(tmp_path / "ro3.db"))
    sonra = {p.relative_to(mini_vault).as_posix(): p.stat().st_mode for p in mini_vault.rglob("*") if p.is_file()}
    assert once == sonra


def test_ozet_not_dosyasi_olusturulmaz(mini_vault: Path, tmp_path: Path) -> None:
    """`--db` verilmemişse yazma ~/.harita'ya gider, vault'a değil."""
    calistir("indeksle", str(mini_vault), "--db", str(tmp_path / "ro4.db"))
    assert not any(p.name.endswith(".db") for p in mini_vault.rglob("*"))


# ---------------------------------------------------------------------------
# Yardımcı: testlerin kurgusal kaldığının kanıtı
# ---------------------------------------------------------------------------


def test_fixture_gercek_vault_icerigi_icermiyor() -> None:
    """Test dosyaları gerçek vault'tan alınmış not içeriği taşımamalı.

    Yasak dizeler parçalardan kurulur; böylece bu testin kendi kaynağı
    taranan metne girmez (kendini yakalamaz).
    """
    parcalar = (
        ("umut", "6"),
        ("Mt3", "Ui5"),
        ("CLAUDE", "_PROJECT_DIR"),
        ("/home/user/", "Mt3"),
    )
    yasaklar = ["".join(p) for p in parcalar]
    for dosya in sorted((KOK / "tests").rglob("*.py")):
        icerik = dosya.read_text(encoding="utf-8")
        # Bu dosyanın kendi kaynağı parçaları içerir; yalnızca fonksiyon
        # govdesinin ALT kısmı taranır.
        if dosya.name == "test_cli.py":
            bas = icerik.find("    for dosya in sorted")
            icerik = icerik[bas:] if bas != -1 else ""
        for yasak in yasaklar:
            assert yasak not in icerik, f"{dosya.name}: {yasak}"
