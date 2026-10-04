""".env ayristirici: tirnak, export, yorum, CRLF, BOM, bozuk satir, dosya secimi."""

from __future__ import annotations

from anahtarlik import env


def _oku(icerik: str, tmp_path):
    yol = tmp_path / ".env"
    yol.write_text(icerik, encoding="utf-8")
    return dict(env.oku(yol))


def test_duz_atama(tmp_path):
    assert _oku("GITHUB_TOKEN=abc123\n", tmp_path) == {"GITHUB_TOKEN": "abc123"}


def test_export_oneki_atilir(tmp_path):
    assert _oku("export API_KEY=abc123\n", tmp_path) == {"API_KEY": "abc123"}


def test_cift_tirnak(tmp_path):
    assert _oku('KEY="deger iki # kelime"\n', tmp_path) == {"KEY": "deger iki # kelime"}


def test_tek_tirnak(tmp_path):
    assert _oku("KEY='deger # yorum degil'\n", tmp_path) == {"KEY": "deger # yorum degil"}


def test_tirnaksiz_satir_sonu_yorumu(tmp_path):
    """`KEY=deger # yorum`: bosluktan sonraki `#` yorumdur."""
    assert _oku("KEY=deger # yorum burada\n", tmp_path) == {"KEY": "deger"}


def test_deger_ici_bosluksuz_hash_kalır(tmp_path):
    """`abc#def` yorum degil: `#` oncesinde bosluk yok."""
    assert _oku("KEY=abc#def\n", tmp_path) == {"KEY": "abc#def"}


def test_yorum_ve_bos_satirlar_atlanir(tmp_path):
    assert _oku("# yorum\n\n   \nKEY=deger\n", tmp_path) == {"KEY": "deger"}


def test_crlf(tmp_path):
    assert _oku("KEY=deger\r\nDIGER=ikinci\r\n", tmp_path) == {
        "KEY": "deger",
        "DIGER": "ikinci",
    }


def test_bom(tmp_path):
    yol = tmp_path / ".env"
    yol.write_bytes(b"\xef\xbb\xbfKEY=deger\n")
    assert dict(env.oku(yol)) == {"KEY": "deger"}


def test_bozuk_satirlar_atlanir(tmp_path):
    """`=` yoksa, anahtar bos/gecersizse satir yok sayilir; digerleri okunur."""
    icerik = "bu bir cumle\n=DEGER\n1ABC=deger\nKEY=iyidir\n"
    assert _oku(icerik, tmp_path) == {"KEY": "iyidir"}


def test_bozuk_satir_ham_mesaj_sizmaz(tmp_path):
    """Bozuk satirin ham metni ne ciktiya ne hataya gider."""
    yol = tmp_path / ".env"
    yol.write_text("SENTINEL_BOZUK satir\n", encoding="utf-8")
    assert env.oku(yol) == []


def test_bos_deger_izinli(tmp_path):
    assert _oku("KEY=\n", tmp_path) == {"KEY": ""}


def test_okunamayan_dosya_bos_liste(tmp_path):
    assert env.oku(tmp_path / "yok.env") == []


def test_env_dosyasi_mi_kabul():
    for ad in (".env", ".env.local", ".env.production", ".env.test.local"):
        assert env.env_dosyasi_mi(ad), ad


def test_env_dosyasi_mi_ornek_haric():
    for ad in (
        ".env.example",
        ".env.sample",
        ".env.template",
        ".env.dist",
        ".env.defaults",
        "env",
        "environment.yml",
        ".environment",
    ):
        assert not env.env_dosyasi_mi(ad), ad


def test_env_dosyasi_mi_ornek_katmani():
    """.env.production.example da ornek: en son segment yeterli."""
    assert not env.env_dosyasi_mi(".env.production.example")


def test_dosya_uzanti_buyuk_harf_duyarsiz():
    assert not env.env_dosyasi_mi(".ENV")