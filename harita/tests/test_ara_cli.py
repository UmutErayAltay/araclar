"""Dalga D — `harita ara` CLI testleri ve `tutarlilik` "Kontrol edilenler".

Kapsam: alt komut çıktısı/çıkış kodu, JSON şekli, terminal vurgusu, hata
yolları, tutarlılık çıktısının "neler kontrol edildi" bölümü (metin + JSON).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import yaz

from harita import tutarlilik as tut
from harita.cli import main as cli_main


# ---------------------------------------------------------------------------
# ara alt komutu
# ---------------------------------------------------------------------------


def _calistir(argv: list[str]) -> tuple[int, str]:
    import io
    from contextlib import redirect_stderr, redirect_stdout

    cikti, hata = io.StringIO(), io.StringIO()
    with redirect_stdout(cikti), redirect_stderr(hata):
        kod = cli_main(argv)
    return kod, cikti.getvalue() + hata.getvalue()


def test_ara_alt_komutu_sonuc_baser(arama_db: Path) -> None:
    kod, cikti = _calistir(["ara", "güvenlik", "--db", str(arama_db)])
    assert kod == 0
    assert "sonuç" in cikti
    assert "Güvenlik" in cikti


def test_ara_sonucsuz_cikis_kodu_sifir(arama_db: Path) -> None:
    """Sonuç yoksa NET MESAJ + çıkış kodu 0 (hata DEĞİL)."""
    kod, cikti = _calistir(["ara", "bulunamayacakkelime", "--db", str(arama_db)])
    assert kod == 0
    assert "sonuç yok" in cikti


def test_ara_bos_sorgu_hata_kodu(arama_db: Path) -> None:
    """Boş sorgu net KULLANIM hatasıdır (sıfırdan farklı çıkış kodu)."""
    kod, cikti = _calistir(["ara", "   ", "--db", str(arama_db)])
    assert kod != 0
    assert "boş" in cikti.lower()


def test_ara_json_sekli(arama_db: Path) -> None:
    kod, cikti = _calistir(["ara", "güvenlik", "--db", str(arama_db), "--json"])
    assert kod == 0
    veri = json.loads(cikti)
    assert veri["sorgu"] == "güvenlik"
    assert veri["sonuc"] >= 1
    ilk = veri["kayitlar"][0]
    assert set(ilk) == {"puan", "baslik", "yol", "etiketler", "alinti", "not_id"}


def test_ara_json_bos_sonuc(arama_db: Path) -> None:
    kod, cikti = _calistir(["ara", "bulunamayacakkelime", "--db", str(arama_db), "--json"])
    assert kod == 0
    assert json.loads(cikti)["kayitlar"] == []


def test_ara_ilk_n_siniri(arama_db: Path) -> None:
    _, cikti = _calistir(["ara", "güvenlik", "--db", str(arama_db), "--ilk", "1", "--json"])
    assert len(json.loads(cikti)["kayitlar"]) <= 1


def test_ara_tam_bayragi(arama_db: Path) -> None:
    """`--tam` kök kesmeyi kapatır: "borsanın" tam biçimle bulunur."""
    kod, cikti = _calistir(["ara", "borsanın", "--db", str(arama_db), "--tam", "--json"])
    assert kod == 0
    yollar = [k["yol"] for k in json.loads(cikti)["kayitlar"]]
    assert "finans/borsa.md" in yollar


def test_ara_etiket_filtresi(arama_db: Path) -> None:
    _, cikti = _calistir(["ara", "borsa", "--db", str(arama_db), "--etiket", "finans", "--json"])
    kayitlar = json.loads(cikti)["kayitlar"]
    assert kayitlar
    for k in kayitlar:
        assert "finans" in k["etiketler"]


def test_ara_klasor_filtresi(arama_db: Path) -> None:
    _, cikti = _calistir(["ara", "borsa", "--db", str(arama_db), "--klasor", "finans", "--json"])
    kayitlar = json.loads(cikti)["kayitlar"]
    assert kayitlar
    for k in kayitlar:
        assert k["yol"].startswith("finans/")


def test_ara_haric_terim(arama_db: Path) -> None:
    _, cikti = _calistir(["ara", "güvenlik", "--db", str(arama_db), "--json"])
    tum = [k["yol"] for k in json.loads(cikti)["kayitlar"]]
    _, cikti2 = _calistir(["ara", "güvenlik -plan", "--db", str(arama_db), "--json"])
    haric = [k["yol"] for k in json.loads(cikti2)["kayitlar"]]
    assert "proje/plan.md" in tum
    assert "proje/plan.md" not in haric


def test_ara_eski_db_net_hata(tmp_path: Path, arama_vault: Path) -> None:
    """Arama tabloları olmayan eski DB'de net hata verir."""
    from harita.index import baglan, indeksle, sema_olustur

    db = tmp_path / "eski.db"
    baglanti = baglan(db)
    sema_olustur(baglanti)
    baglanti.execute("UPDATE ara_meta SET deger='tr-bm25-0' WHERE anahtar='surum'")
    baglanti.commit()
    baglanti.close()

    kod, cikti = _calistir(["ara", "x", "--db", str(db)])
    assert kod != 0
    assert "indeksle" in cikti


def test_ara_olmayan_db_hata(tmp_path: Path) -> None:
    """Olmayan DB'de `_db_ac` net bir `SystemExit` mesajı verir."""
    import pytest as _pytest

    with _pytest.raises(SystemExit) as exc:
        _calistir(["ara", "x", "--db", str(tmp_path / "yok.db")])
    assert "bulunamadı" in str(exc.value)


def test_ara_tty_disi_vurgu_ust_isaretleri(arama_db: Path) -> None:
    """stdout TTY DEĞİLSE vurgu `«...»` ile gösterilir, ANSI kodu basılmaz."""
    _, cikti = _calistir(["ara", "güvenlik", "--db", str(arama_db)])
    assert "«" in cikti
    assert "\033[" not in cikti


def test_ara_konsol_kontrol_karakterleri_temizlenir(tmp_path: Path) -> None:
    """Not içeriğindeki ANSI/kontrol karakterleri konsolu bozmaz."""
    from harita.index import indeksle

    vault = tmp_path / "kontrol-vault"
    yaz(vault, "v.md", "# V\n\n\x1b[31mkirmizi\x1b[0m ve \x07 zil.\n")
    db = tmp_path / "kontrol.db"
    indeksle(vault, db)
    _, cikti = _calistir(["ara", "kirmizi", "--db", str(db)])
    assert "\x1b" not in cikti
    assert "\x07" not in cikti


def test_ara_gizli_satir_ciktida_yok(arama_db: Path) -> None:
    """Gizli satır içeriği CLI çıktısına girmez."""
    _, cikti = _calistir(["ara", "güvenlik", "--db", str(arama_db), "--ilk", "20"])
    assert "sk-abcdefghij" not in cikti
    assert "password:" not in cikti


def test_ara_haric_tutulan_klasor_ciktida_yok(arama_db: Path) -> None:
    _, cikti = _calistir(["ara", "güvenlik", "--db", str(arama_db), "--ilk", "20"])
    assert "receipts/" not in cikti


def test_ara_vaultu_degistirmez(arama_db: Path, arama_vault: Path) -> None:
    from conftest import vault_hashleri

    once = vault_hashleri(arama_vault)
    _calistir(["ara", "güvenlik", "--db", str(arama_db)])
    assert vault_hashleri(arama_vault) == once


def test_ara_alt_komutu_secenekleri_kayitli() -> None:
    """`ara` alt komutunun beklenen bayrakları argparse'ta tanımlı."""
    from harita.cli import arg_parser

    secenekler = set(arg_parser()._subparsers._group_actions[0].choices["ara"]._actions)
    adlar = {a.dest for a in secenekler}
    assert {"sorgu", "ilk", "etiket", "klasor", "tam", "json"} <= adlar


# ---------------------------------------------------------------------------
# tutarlilik — "Kontrol edilenler"
# ---------------------------------------------------------------------------


def test_tutarlilik_kontrol_edilenler_bolumu_metin(tmp_path: Path, capsys) -> None:
    """Çıktı "Kontrol edilenler" bölümünü ve çift sayısını gösterir."""
    from test_tutarlilik import BUGUN, _iso, atlas_kur, repo  # noqa: PLC0415

    vault = tmp_path / "v"
    yaz(vault, "proje/harita.md", "---\nrepo: harita\n---\n# Harita\n\n**Durum:** aktif\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="harita", last_commit_at=_iso(200))])
    kod = cli_main([
        "tutarlilik", str(vault), "--atlas-db", str(db),
        "--esleme", str(tmp_path / "yok.toml"), "--bugun", BUGUN.isoformat(),
    ])
    cikti = capsys.readouterr().out
    assert kod == 0
    assert "Kontrol edilenler:" in cikti
    assert "Eşleşen not↔repo çifti:" in cikti
    assert "Çalıştırılan kural:" in cikti


def test_tutarlilik_kontrol_edilenler_cift_listesi(tmp_path: Path, capsys) -> None:
    """Çift başına: not yolu → repo adı, kaynak ve güven yazılır."""
    from test_tutarlilik import BUGUN, _iso, atlas_kur, repo  # noqa: PLC0415

    vault = tmp_path / "v"
    yaz(vault, "proje/harita.md", "---\nrepo: harita\n---\n# Harita\n\n**Durum:** aktif\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="harita", last_commit_at=_iso(200))])
    cli_main([
        "tutarlilik", str(vault), "--atlas-db", str(db),
        "--esleme", str(tmp_path / "yok.toml"), "--bugun", BUGUN.isoformat(),
    ])
    cikti = capsys.readouterr().out
    assert "proje/harita.md → harita" in cikti
    assert "kaynak: frontmatter" in cikti
    assert "güven: yuksek" in cikti


def test_tutarlistik_kural_sayaclari_metin(tmp_path: Path, capsys) -> None:
    """Her kural kaç çift üzerinde değerlendirildiğini söyler."""
    from test_tutarlilik import BUGUN, _iso, atlas_kur, repo  # noqa: PLC0415

    vault = tmp_path / "v"
    yaz(vault, "proje/harita.md", "---\nrepo: harita\n---\n# Harita\n\n**Durum:** aktif\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="harita", last_commit_at=_iso(200))])
    cli_main([
        "tutarlilik", str(vault), "--atlas-db", str(db),
        "--esleme", str(tmp_path / "yok.toml"), "--bugun", BUGUN.isoformat(),
    ])
    cikti = capsys.readouterr().out
    # Kural adları ve değerlendirme sayıları görünür.
    assert "planli-ama-kod-var" in cikti
    assert "çift üzerinde değerlendirildi" in cikti
    assert "1/1" in cikti  # aktif-ama-durgun tek çift üzerinde çalıştı


def test_tutarlilik_sifir_cift_ve_sifir_bulgu_ayirt_edilir(tmp_path: Path, capsys) -> None:
    """0 uyarı: "tutarlı" mı "hiç eşleşme yok" mu? Çıktı AYIRT EDER."""
    from test_tutarlilik import BUGUN, _iso, atlas_kur, repo  # noqa: PLC0415

    vault = tmp_path / "v"
    # Hiçbir not repo'ya eşleşmiyor.
    yaz(vault, "proje/orphan.md", "---\nrepo: bilinmeyen\n---\n# Orphan\n\n**Durum:** aktif\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="harita", last_commit_at=_iso(200))])
    cli_main([
        "tutarlilik", str(vault), "--atlas-db", str(db),
        "--esleme", str(tmp_path / "yok.toml"), "--bugun", BUGUN.isoformat(),
    ])
    cikti = capsys.readouterr().out
    assert "Eşleşen not↔repo çifti: 0" in cikti
    assert "1 not eşleşmedi" in cikti


def test_tutarlilik_kontrol_edilenler_json(tmp_path: Path, capsys) -> None:
    """`--json` aynı alanları taşır."""
    from test_tutarlilik import BUGUN, _iso, atlas_kur, repo  # noqa: PLC0415

    vault = tmp_path / "v"
    yaz(vault, "proje/harita.md", "---\nrepo: harita\n---\n# Harita\n\n**Durum:** aktif\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="harita", last_commit_at=_iso(200))])
    cli_main([
        "tutarlilik", str(vault), "--atlas-db", str(db),
        "--esleme", str(tmp_path / "yok.toml"), "--bugun", BUGUN.isoformat(), "--json",
    ])
    veri = json.loads(capsys.readouterr().out)
    kontrol = veri["kontrol_edilenler"]
    assert kontrol["cift_sayisi"] == 1
    assert kontrol["guven"] == {"yuksek": 1, "orta": 0}
    assert kontrol["eslesme_yontemi"] == {"frontmatter": 1}
    assert kontrol["ciftler"][0]["not"] == "proje/harita.md"
    assert kontrol["ciftler"][0]["repo"] == "harita"
    assert kontrol["ciftler"][0]["yontem"] == "frontmatter"
    assert kontrol["ciftler"][0]["guven"] == "yuksek"
    kurallar = {k["kural"] for k in kontrol["kurallar"]}
    assert "planli-ama-kod-var" in kurallar
    assert "vaultsuz-aktif-repo" in kurallar
    for k in kontrol["kurallar"]:
        assert set(k) == {"kural", "cift", "degerlendirilen", "bulgu"}


def test_tutarlilik_tahmin_guveni_orta(tmp_path: Path, capsys) -> None:
    """Backtick ile eşleşen çift "orta" güvendir ve (tahmin) işaretlidir."""
    from test_tutarlilik import BUGUN, _iso, atlas_kur, repo  # noqa: PLC0415

    vault = tmp_path / "v"
    yaz(vault, "proje/serbest.md", "# Serbest\n\n`harita` projesine bak.\n\n**Durum:** aktif\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="harita", last_commit_at=_iso(200))])
    cli_main([
        "tutarlilik", str(vault), "--atlas-db", str(db),
        "--esleme", str(tmp_path / "yok.toml"), "--bugun", BUGUN.isoformat(), "--json",
    ])
    veri = json.loads(capsys.readouterr().out)
    ciftler = veri["kontrol_edilenler"]["ciftler"]
    assert ciftler[0]["yontem"] == "backtick"
    assert ciftler[0]["tahmin"] is True
    assert ciftler[0]["guven"] == "orta"
    assert veri["kontrol_edilenler"]["guven"]["orta"] == 1


def test_tutarlilik_bulgular_degismez(tmp_path: Path) -> None:
    """"Kontrol edilenler" eklendi ama BULGULAR değişmedi."""
    from test_tutarlilik import BUGUN, _iso, atlas_kur, repo  # noqa: PLC0415

    vault = tmp_path / "v"
    yaz(vault, "proje/harita.md", "---\nrepo: harita\n---\n# Harita\n\n**Durum:** planlandı\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="harita", last_commit_at=_iso(2))])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    # Planlı + repoda yeni commit → uyarı üretilmeli.
    assert any(b.kural == "planli-ama-kod-var" for b in rapor.uyarilar)
    # Sayaç da bunu görmeli.
    sayac = next(k for k in rapor.kural_sayaclari if k.kural == "planli-ama-kod-var")
    assert sayac.degerlendirilen == 1
    assert sayac.bulgu == 1
