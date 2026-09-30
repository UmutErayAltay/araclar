"""Dalga C / madde 0: `ozel-anahtar` başlık→gövde kuralı.

Kural: başlığın hemen ardından 1–5 satırda, en az 32 karakterlik ve yalnız
base64 alfabesinden (`[A-Za-z0-9+/=]`) oluşan bir GÖVDE satırı varsa bulgu
`yuksek` ("gövdeli özel anahtar"); yalnızca başlık varsa `bilgi`
("başlık var, gövde yok — elle kontrol et").

`ozel-anahtar` artık `TEST_YOLU_DUSURULEN_TURLER` içinde DEĞİLDİR: gövdeli
bir anahtar `tests/` altında bile `yuksek` kalmalıdır.

Güvenlik: sahte gövde kaynakta TAM LITERAL olarak bulunmaz, çalışma zamanında
parçalardan kurulur; ayrıca snippet'ta gövdenin hiçbir parçası bulunmaz.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import commit_file, make_repo

from atlas import leaks

#: Sahte PEM gövdesi: çalışma zamanında parçalardan kurulur (kaynakta literal
#: YOK — test dosyasının kendisi bir sızıntı taramasını tetiklemesin).
GOVDE = "MII" + "EvQ" + "IB" + "0kl" * 12
GOVDE_UZUN = "MII" + "aB" * 40

BASLIK = "-----BEGIN RSA PRIVATE KEY-----"
SON = "-----END RSA PRIVATE KEY-----"


def _turler(bulgular) -> set[str]:
    return {b["kind"] for b in bulgular}


def _anahtar_bulgusu(bulgular) -> dict:
    return next(b for b in bulgular if b["kind"] == "ozel-anahtar")


# --------------------------------------------------------------------------
# Gövdeli anahtar: her bağlamda `yuksek`
# --------------------------------------------------------------------------


def test_govdeli_anahtar_calisma_agacinda_yuksek(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "id.pem", f"{BASLIK}\n{GOVDE}\n{SON}\n", "ekle")
    bulgu = _anahtar_bulgusu(leaks.tara_calisma_agaci(repo))
    assert bulgu["severity"] == "yuksek"
    assert bulgu["file"] == "id.pem"
    assert bulgu["line"] == 1


def test_govdeli_anahtar_tests_altinda_dusmez(tmp_path: Path):
    """`ozel-anahtar` test yolu düşürmesinden ÇIKARILDI: gövde `yuksek` kalır."""
    assert "ozel-anahtar" not in leaks.TEST_YOLU_DUSURULEN_TURLER

    repo = make_repo(tmp_path / "r")
    commit_file(repo, "tests/fixtures/id.pem", f"{BASLIK}\n{GOVDE}\n{SON}\n", "ekle")
    bulgu = _anahtar_bulgusu(leaks.tara_calisma_agaci(repo))
    assert bulgu["severity"] == "yuksek"
    assert bulgu["file"] == "tests/fixtures/id.pem"


def test_govdeli_anahtar_gecmiste_yuksek(tmp_path: Path):
    """Yalnız çalışma ağacında değil, GEÇMİŞTE de `yuksek` (commit'li dosya)."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "id_rsa.pem", f"{BASLIK}\n{GOVDE}\n{SON}\n", "anahtar ekle")
    bulgular = leaks.tara_gecmis(repo, commit_sayisi=10)
    bulgu = _anahtar_bulgusu(bulgular)
    assert bulgu["severity"] == "yuksek"
    assert bulgu["commit"], "geçmiş bulgusunda commit olmalı"


def test_govdeli_anahtar_gecmiste_tests_altinda_yuksek(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "tests/keys/id.pem", f"{BASLIK}\n{GOVDE}\n{SON}\n", "ekle")
    bulgu = _anahtar_bulgusu(leaks.tara_gecmis(repo, commit_sayisi=10))
    assert bulgu["severity"] == "yuksek"


def test_govdeli_anahtar_hem_agdaki_hem_gecmisteki_kayittan_bulunur(tmp_path: Path):
    """Aynı dosya hem commit'li hem silinmemiş: iki kaynaktan da bulgu gelir."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "id.pem", f"{BASLIK}\n{GOVDE}\n{SON}\n", "ekle")
    agac = _anahtar_bulgusu(leaks.tara_calisma_agaci(repo))
    gecmis = _anahtar_bulgusu(leaks.tara_gecmis(repo, commit_sayisi=10))
    assert agac["commit"] is None  # çalışma ağacı
    assert gecmis["commit"] is not None  # geçmişte
    assert agac["severity"] == gecmis["severity"] == "yuksek"


@pytest.mark.parametrize("gecikme", [0, 1, 2, 3, 4])
def test_govde_penceresi_ici_bes_satira_kadar_gecerli(tmp_path: Path, gecikme: int):
    """1–5. satır: gövde sayılır. (gecikme=0 → gövde başlığın 1. sonrası.)"""
    repo = make_repo(tmp_path / "r")
    aralar = [f"# not {i}" for i in range(gecikme)]
    commit_file(repo, "id.pem", f"{BASLIK}\n" + "\n".join(aralar + [GOVDE, SON]) + "\n", "ekle")
    bulgu = _anahtar_bulgusu(leaks.tara_calisma_agaci(repo))
    assert bulgu["severity"] == "yuksek", f"gecikme={gecikme} pencerede olmalı"


def test_dort_satir_aradan_govde_sayilmaz(tmp_path: Path):
    """5 satır sonrasındaki gövde artık sayılmaz → `bilgi`."""
    repo = make_repo(tmp_path / "r")
    aralar = "\n".join(f"# not {i}" for i in range(5))
    commit_file(repo, "id.pem", f"{BASLIK}\n{aralar}\n{GOVDE}\n{SON}\n", "ekle")
    bulgu = _anahtar_bulgusu(leaks.tara_calisma_agaci(repo))
    assert bulgu["severity"] == "bilgi"


def test_bes_satirdan_sonraki_govde_sayilmaz():
    """Başlıktan 6+ satır sonra gelen gövde YOK sayılır (`bilgi`)."""
    sonraki = ["# not 1", "# not 2", "# not 3", "# not 4", "# not 5", GOVDE]
    bulgu = _anahtar_bulgusu(leaks.satiri_tara(BASLIK, sonraki_satirlar=sonraki))
    assert bulgu["severity"] == "bilgi"


def test_bir_kademe_dusurulmus_govde_da_yuksek():
    """Eşik tam 32 karakter: `=` dolgusu sayılır."""
    tam = "A" * 32
    assert _anahtar_bulgusu(
        leaks.satiri_tara(BASLIK, sonraki_satirlar=[tam])
    )["severity"] == "yuksek"


# --------------------------------------------------------------------------
# Yalnızca başlık: `bilgi`
# --------------------------------------------------------------------------


def test_yalniz_baslik_bilgi(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "not.md", f"{BASLIK}\nbu bir ornek blok\n", "ekle")
    bulgu = _anahtar_bulgusu(leaks.tara_calisma_agaci(repo))
    assert bulgu["severity"] == "bilgi"


def test_yalniz_baslik_gecmiste_bilgi(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "not.md", f"{BASLIK}\naciklama satiri\n", "ekle")
    bulgu = _anahtar_bulgusu(leaks.tara_gecmis(repo, commit_sayisi=10))
    assert bulgu["severity"] == "bilgi"


def test_tests_altindaki_yalniz_baslik_bilgi_kalir(tmp_path: Path):
    """Fixture/örnek başlıklar yanlış pozitif üretmez: `bilgi`."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "tests/ornek.md", f"{BASLIK}\nornek\n", "ekle")
    bulgu = _anahtar_bulgusu(leaks.tara_calisma_agaci(repo))
    assert bulgu["severity"] == "bilgi"


def test_kisa_govde_sayilmaz():
    """32 karakterden kısa base64 satırı gövde DEĞİLDİR."""
    assert _anahtar_bulgusu(
        leaks.satiri_tara(BASLIK, sonraki_satirlar=["A" * 31])
    )["severity"] == "bilgi"


def test_base64_olmayan_satir_govde_sayilmaz():
    """Noktalama/boşluk içeren uzun satır gövde değildir."""
    uzun = "not: " + "x" * 60  # base64 alfabesi dışı karakterler var
    assert _anahtar_bulgusu(
        leaks.satiri_tara(BASLIK, sonraki_satirlar=[uzun])
    )["severity"] == "bilgi"


def test_bos_sonraki_satirlar_bilgi():
    assert _anahtar_bulgusu(leaks.satiri_tara(BASLIK))["severity"] == "bilgi"
    assert _anahtar_bulgusu(leaks.satiri_tara(BASLIK, sonraki_satirlar=[]))["severity"] == "bilgi"


# --------------------------------------------------------------------------
# Güvenlik: gövdenin hiçbir parçası snippet'ta olmaz
# --------------------------------------------------------------------------


def test_snippette_govdenin_parcasi_yok():
    bulgu = _anahtar_bulgusu(
        leaks.satiri_tara(BASLIK, sonraki_satirlar=[GOVDE], dosya="id.pem")
    )
    snip = bulgu["snippet_redacted"] or ""
    assert snip
    for i in range(len(GOVDE) - 5):
        assert GOVDE[i : i + 6] not in snip
    assert GOVDE[:20] not in snip


def test_snippette_govdenin_parcasi_yok_gecmis(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "id.pem", f"{BASLIK}\n{GOVDE_UZUN}\n{SON}\n", "ekle")
    bulgu = _anahtar_bulgusu(leaks.tara_gecmis(repo, commit_sayisi=10))
    snip = bulgu["snippet_redacted"] or ""
    for i in range(len(GOVDE_UZUN) - 5):
        assert GOVDE_UZUN[i : i + 6] not in snip


def test_db_ve_ciktida_govde_parcasi_yok(tmp_path: Path, db_file: Path, capsys):
    """Uçtan uca: gövde DB baytlarında ve CLI çıktısında YOK."""
    from conftest import run_module_cli

    repo = make_repo(tmp_path / "r")
    commit_file(repo, "id.pem", f"{BASLIK}\n{GOVDE}\n{SON}\n", "ekle")
    proc = run_module_cli("sizinti", "--root", str(repo.parent), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    ham = db_file.read_bytes() + proc.stdout.encode() + proc.stderr.encode()
    for i in range(len(GOVDE) - 5):
        assert GOVDE[i : i + 6].encode() not in ham


# --------------------------------------------------------------------------
# Diğer türler etkilenmez
# --------------------------------------------------------------------------


def test_diger_turler_kural_disi(tmp_path: Path):
    """Kural yalnız `ozel-anahtar`'ı etkiler; diğer türler değişmez."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", "anahtar: sk-" + "ab12" * 10 + "\n" + GOVDE + "\n", "ekle")
    bulgular = leaks.tara_calisma_agaci(repo)
    anahtar = next(b for b in bulgular if b["kind"] == "api-anahtari")
    assert anahtar["severity"] == "yuksek"  # dosya kökte: test yolu düşürmesi yok
    # Başlık satırı yok; gövde satırı TEK BAŞINA `ozel-anahtar` üretmez.
    assert "ozel-anahtar" not in _turler(bulgular)
